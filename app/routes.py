import hashlib
import os
import json
import uuid
import tempfile
import time
from datetime import datetime, timedelta
from functools import lru_cache
from flask import render_template, request, jsonify, session, send_file, redirect, url_for
from app import app
from .transliteration import transliterate_chapter, count_strongs_in_verses, get_verses_by_book

# Get logger
logger = app.logger

# Paths
current_file_path = os.path.abspath(__file__)
current_dir = os.path.dirname(current_file_path)
STATIC_DATA_DIR = os.path.join(current_dir, 'static')
UPLOAD_DATA_DIR = os.path.join(current_dir, 'uploads')
os.makedirs(UPLOAD_DATA_DIR, exist_ok=True)

def cleanup_old_session_files(days=30):
    """
    Delete session files older than the specified number of days.

    Args:
        days: Number of days to keep session files (default: 30)

    Returns:
        Number of files deleted
    """
    try:
        cutoff_time = time.time() - (days * 24 * 60 * 60)
        deleted_count = 0

        for filename in os.listdir(UPLOAD_DATA_DIR):
            if not filename.endswith('.json'):
                continue

            filepath = os.path.join(UPLOAD_DATA_DIR, filename)
            try:
                if os.path.isfile(filepath) and os.path.getmtime(filepath) < cutoff_time:
                    os.remove(filepath)
                    deleted_count += 1
            except OSError:
                # Skip files we can't access or delete
                continue

        return deleted_count
    except OSError:
        # If we can't read the directory, return 0
        return 0

# Run cleanup on startup (delete files older than 30 days)
cleanup_old_session_files(days=30)

def get_session_id():
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())
    return session['user_id']

def _validate_user_dict(data):
    if not isinstance(data, dict):
        return False, "Uploaded JSON must be an object mapping Strong's numbers to entries."

    for key, val in data.items():
        if not isinstance(key, str):
            return False, "Strong's numbers must be string keys (e.g., \"H7225\")."
        if not isinstance(val, dict):
            return False, f"Entry for {key} must be an object."
        translations = val.get("translations")
        if translations is None or not isinstance(translations, list) or not all(isinstance(t, str) for t in translations):
            return False, f"Entry for {key} must include a list of translations."
        color = val.get("color", None)
        if color is not None and not isinstance(color, str):
            return False, f"Color for {key} must be a string (hex) or null."
    return True, None


def _user_dict_path():
    return os.path.join(UPLOAD_DATA_DIR, f"{get_session_id()}.json")


def save_user_dict(user_dict: dict):
    session['user_strongs_dict'] = user_dict
    try:
        with open(_user_dict_path(), 'w', encoding='utf-8') as f:
            json.dump(user_dict, f, ensure_ascii=False, indent=2)
    except OSError as e:
        # If persisting to disk fails, we still keep the session copy.
        logger.warning(f"Failed to persist user dictionary to disk: {e}")


def validate_book_chapter(book, chapter):
    """
    Validate book name and chapter number.

    Args:
        book: Book name string
        chapter: Chapter number (int or None)

    Returns:
        tuple: (is_valid: bool, error_message: str or None)
    """
    if not book:
        return False, "Book name is required"

    # Check if book exists
    if book not in book_chapter_count:
        return False, f"Unknown book: {book}"

    if chapter is None:
        return False, "Chapter number is required"

    # Check if chapter is a positive integer
    if not isinstance(chapter, int) or chapter < 1:
        return False, "Chapter must be a positive integer"

    # Check if chapter exists in the book
    max_chapters = book_chapter_count.get(book, 0)
    if chapter > max_chapters:
        return False, f"{book} only has {max_chapters} chapter{'s' if max_chapters != 1 else ''}"

    return True, None


def get_user_strongs_dict():
    default_dict = {k: {"translations": v, "color": None} for k, v in default_strongs_dict.items()}
    if 'user_strongs_dict' in session:
        return session['user_strongs_dict']

    user_file = _user_dict_path()
    if os.path.exists(user_file):
        try:
            with open(user_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            valid, error = _validate_user_dict(data)
            if valid:
                session['user_strongs_dict'] = data
                return data
            else:
                logger.warning(f"Invalid user dictionary file: {error}")
        except (OSError, json.JSONDecodeError) as e:
            logger.error(f"Failed to load user dictionary from {user_file}: {e}")

    session['user_strongs_dict'] = default_dict
    return default_dict

strongs_dict_path = os.path.join(STATIC_DATA_DIR, 'strongs_dict.json')
strongs_path = os.path.join(STATIC_DATA_DIR, 'Strongs.json')
kjv_path = os.path.join(STATIC_DATA_DIR, 'kjv_strongs.json')
outlines_path = os.path.abspath(os.path.join(current_dir, '..', 'bible_bsb_book_outlines_with_ranges.json'))

with open(strongs_dict_path, 'r', encoding='utf-8') as f:
    default_strongs_dict = json.load(f)
with open(strongs_path, 'r', encoding='utf-8') as f:
    strongs_data = json.load(f)
with open(kjv_path, 'r', encoding='utf-8') as f:
    kjv_data = json.load(f)
with open(outlines_path, 'r', encoding='utf-8') as f:
    outline_data = json.load(f)

# Load Hebrew-Greek cross-reference data
crossref_path = os.path.join(STATIC_DATA_DIR, 'hebrew_greek_crossref.json')
if os.path.exists(crossref_path):
    with open(crossref_path, 'r', encoding='utf-8') as f:
        crossref_data = json.load(f)
    hebrew_to_greek = crossref_data.get('hebrew_to_greek', {})
    greek_to_hebrew = crossref_data.get('greek_to_hebrew', {})
    logger.info(f"Loaded {len(hebrew_to_greek)} Hebrew→Greek and {len(greek_to_hebrew)} Greek→Hebrew cross-references")
else:
    hebrew_to_greek = {}
    greek_to_hebrew = {}
    logger.warning(f"Cross-reference data not found at {crossref_path}")

# Build mappings for book order and chapter counts
book_order = {}
book_chapter_count = {}
chapter_verse_counts = {}
for verse in kjv_data.get('verses', []):
    name = verse['book_name']
    if name not in book_order:
        book_order[name] = verse['book']
    chapter = int(verse['chapter'])
    if name not in book_chapter_count or chapter > book_chapter_count[name]:
        book_chapter_count[name] = chapter
    chapter_verse_counts.setdefault(name, {})
    chapter_verse_counts[name][chapter] = max(int(verse['verse']), chapter_verse_counts[name].get(chapter, 0))

# Build case-insensitive lookup for book names
book_name_lookup = {name.lower(): name for name in book_chapter_count.keys()}

def normalize_book_name(book_input):
    """
    Normalize book name input to match exact book name in data.
    Handles case-insensitive matching.

    Args:
        book_input: User-provided book name string

    Returns:
        str: Normalized book name if found, original input otherwise
    """
    if not book_input:
        return book_input
    # Try exact match first
    if book_input in book_chapter_count:
        return book_input
    # Try case-insensitive match
    normalized = book_name_lookup.get(book_input.lower())
    return normalized if normalized else book_input


def _get_unit_color(unit: dict) -> str:
    seed = f"{unit.get('marker', '')}-{unit.get('title', '')}"
    digest = hashlib.md5(seed.encode('utf-8')).hexdigest()
    return f"#{digest[:6]}"


def _count_verses_in_range(book: str, start_chapter: int, start_verse: int, end_chapter: int, end_verse: int) -> int:
    total = 0
    chapter_counts = chapter_verse_counts.get(book, {})
    for ch in range(start_chapter, end_chapter + 1):
        max_verse = chapter_counts.get(ch, 0)
        if not max_verse:
            continue
        range_start = start_verse if ch == start_chapter else 1
        range_end = end_verse if ch == end_chapter else max_verse
        total += max(0, range_end - range_start + 1)
    return total


def _calculate_unit_progress(unit: dict, book: str, chapter: int) -> float:
    start = unit.get('range_start') or {}
    end = unit.get('range_end') or {}
    start_ch = int(start.get('chapter', 0) or 0)
    start_v = int(start.get('verse', 1) or 1)
    end_ch = int(end.get('chapter', 0) or 0)
    end_v = int(end.get('verse', 0) or 0)

    total = _count_verses_in_range(book, start_ch, start_v, end_ch, end_v)
    if not total:
        return 0.0

    current_max_verse = chapter_verse_counts.get(book, {}).get(chapter, 0)
    current_end = end_v if (chapter == end_ch and end_v) else current_max_verse
    completed = _count_verses_in_range(book, start_ch, start_v, chapter, current_end)
    return min(100.0, (completed / total) * 100)

def _unit_bounds_for_chapter(unit: dict, book: str, chapter: int):
    """Return (start_verse, end_verse) for this unit within the current chapter."""
    chapter_counts = chapter_verse_counts.get(book, {})
    max_verse = chapter_counts.get(chapter, 0)

    start = unit.get('range_start') or {}
    end = unit.get('range_end') or {}
    start_ch = int(start.get('chapter', 0) or 0)
    end_ch = int(end.get('chapter', 0) or 0)
    start_v = int(start.get('verse', 1) or 1)
    end_v = int(end.get('verse', 0) or 0)

    chapter_start = start_v if chapter == start_ch else 1
    chapter_end = end_v if (chapter == end_ch and end_v) else max_verse
    return max(1, chapter_start), max(chapter_start, chapter_end)


def get_active_units(book: str, chapter: int):
    """Return all outline units that include the given chapter, with progress."""
    if not book or not chapter:
        return []

    units = outline_data.get(book, [])
    active = []
    for unit in units:
        start = unit.get('range_start') or {}
        end = unit.get('range_end') or {}
        start_ch = int(start.get('chapter', 0) or 0)
        end_ch = int(end.get('chapter', 0) or 0)

        if start_ch and end_ch and start_ch <= chapter <= end_ch:
            label = f"{unit.get('marker', '').strip()} {unit.get('title', '').strip()}".strip()
            start_v, end_v = _unit_bounds_for_chapter(unit, book, chapter)
            active.append({
                'label': label or unit.get('title') or 'Unit',
                'range': unit.get('range'),
                'percent_complete': _calculate_unit_progress(unit, book, chapter),
                'color': _get_unit_color(unit),
                'start_verse': start_v,
                'end_verse': end_v,
                'marker': unit.get('marker', '').strip(),
                'start_chapter': start_ch,
                'end_chapter': end_ch,
                'start_verse_absolute': int(start.get('verse', 1) or 1),
                'end_verse_absolute': int(end.get('verse', 0) or 0),
                'range_start': start,
                'range_end': end,
            })

    return active


def get_active_unit(book: str, chapter: int):
    if not book or not chapter:
        return None

    units = outline_data.get(book)
    if not units:
        return None

    for unit in units:
        start = unit.get('range_start') or {}
        end = unit.get('range_end') or {}
        start_ch = int(start.get('chapter', 0) or 0)
        end_ch = int(end.get('chapter', 0) or 0)

        if start_ch <= chapter <= end_ch:
            label = f"{unit.get('marker', '').strip()} {unit.get('title', '').strip()}".strip()
            percent = _calculate_unit_progress(unit, book, chapter)
            return {
                'label': label or unit.get('title'),
                'range': unit.get('range'),
                'percent_complete': percent,
                'color': _get_unit_color(unit),
            }

    return None

DEFAULT_CONTEXT_OPTIONS = {
    'bolded': True,
    'repeats': True,
    'phonetics': True,
    'overview': True,
    'units': True,
    'uncommon': True,
}

@app.route('/', methods=['GET', 'POST'])
def home():
    raw_book = request.form.get('book', '') or request.args.get('book', '')
    # Normalize book name for case-insensitive matching
    book = normalize_book_name(raw_book)
    chapter_str = request.form.get('chapter', '') or request.args.get('chapter', '')
    focus_strong = (request.args.get('focus') or '').strip().upper()
    from_heatmap = (request.args.get('from_heatmap') or '').lower() in {'1', 'true', 'yes', 'on'}

    chapter = None
    error_message = None
    if chapter_str:
        try:
            chapter = int(chapter_str)
        except ValueError:
            error_message = "Chapter must be a valid number"
            logger.warning(f"Invalid chapter format: {chapter_str}")

    active_units = get_active_units(book, chapter) if book and chapter else []
    result = ""
    active_unit = None
    is_valid_request = False
    if request.method == 'POST' or (book and chapter):
        if book and chapter:
            # Validate inputs
            is_valid, validation_error = validate_book_chapter(book, chapter)
            if not is_valid:
                error_message = validation_error
                logger.warning(f"Invalid book/chapter request: {validation_error} (book={book}, chapter={chapter})")
                result = f'<div class="error-message">{validation_error}</div>'
            else:
                is_valid_request = True
                user_strongs_dict = get_user_strongs_dict()
                result = transliterate_chapter(book, chapter, user_strongs_dict, strongs_data, kjv_data, active_units=active_units)
                active_unit = get_active_unit(book, chapter)

    # Only show book overview and progress for valid requests
    total_chapters = book_chapter_count.get(book) if is_valid_request else None
    book_progress = (chapter / total_chapters * 100) if total_chapters and chapter else None
    verses = build_verses_for_render(result, active_units) if result else []

    user_strongs_keys = list(user_strongs_dict.keys()) if 'user_strongs_dict' in dir() else []
    # Generate book data for autocomplete
    ordered_books = sorted(book_order.items(), key=lambda x: x[1])
    book_data = [{'name': name, 'chapters': book_chapter_count.get(name, 0)} for name, _ in ordered_books]
    return render_template(
        'home.html',
        result=result,
        book=book,
        chapter=chapter,
        active_unit=active_unit,
        active_units=active_units,
        total_chapters=total_chapters,
        book_progress=book_progress,
        verses=verses,
        focus_strong=focus_strong,
        from_heatmap=from_heatmap,
        context_defaults=DEFAULT_CONTEXT_OPTIONS,
        user_strongs_keys=user_strongs_keys,
        book_data=book_data,
    )

@app.route('/navigate', methods=['POST'])
def navigate():
    book = request.form.get('book', '')
    chapter_str = request.form.get('chapter', '')
    try:
        chapter = int(chapter_str)
    except ValueError:
        chapter = 1
        logger.warning(f"Invalid chapter in navigation: {chapter_str}")

    direction = request.form.get('direction', '')
    max_chapters = book_chapter_count.get(book, 1)

    if direction == 'next':
        chapter = min(chapter + 1, max_chapters)
    elif direction == 'prev':
        chapter = max(1, chapter - 1)

    # Validate the resulting chapter
    is_valid, validation_error = validate_book_chapter(book, chapter)
    if not is_valid:
        logger.error(f"Navigation resulted in invalid state: {validation_error}")
        # Redirect back to home with error
        return redirect(url_for('home'))

    active_units = get_active_units(book, chapter)
    user_strongs_dict = get_user_strongs_dict()
    result = transliterate_chapter(book, chapter, user_strongs_dict, strongs_data, kjv_data, active_units=active_units)
    active_unit = get_active_unit(book, chapter)
    total_chapters = book_chapter_count.get(book)
    book_progress = (chapter / total_chapters * 100) if total_chapters and chapter else None
    verses = build_verses_for_render(result, active_units) if result else []

    user_strongs_keys = list(user_strongs_dict.keys())
    return render_template(
        'home.html',
        result=result,
        book=book,
        chapter=chapter,
        active_unit=active_unit,
        active_units=active_units,
        total_chapters=total_chapters,
        book_progress=book_progress,
        verses=verses,
        focus_strong='',
        from_heatmap=False,
        context_defaults=DEFAULT_CONTEXT_OPTIONS,
        user_strongs_keys=user_strongs_keys,
    )


def build_verses_for_render(result_html: str, active_units: list):
    """Split transliterated HTML into per-verse chunks and attach matching unit colors."""
    if not result_html:
        return []

    verses = []
    for line in result_html.split('\n'):
        if not line.strip():
            continue
        parts = line.split(' ', 1)
        try:
            num = int(parts[0])
        except (ValueError, IndexError):
            continue
        text_html = parts[1] if len(parts) > 1 else ''
        bars = [
            {
                'color': unit['color'],
                'label': unit['label'],
                'marker': unit.get('marker'),
                'is_start': num == unit.get('start_verse', 1),
                'is_end': num == unit.get('end_verse', 0),
                'start_verse': unit.get('start_verse', 1),
                'end_verse': unit.get('end_verse', 0),
            }
            for unit in active_units
            if num >= unit.get('start_verse', 1) and num <= unit.get('end_verse', 0)
        ]
        verses.append({'num': num, 'html': text_html, 'bars': bars})
    return verses

# Route for handling the user's strongs_dict
@app.route('/edit_dict', methods=['GET', 'POST'])
def edit_dict():
    user_strongs_dict = get_user_strongs_dict()

    if request.method == 'POST':
        def _normalize_translations(raw):
            if raw is None:
                return None
            if isinstance(raw, list):
                return [str(item).strip() for item in raw if str(item).strip()]
            if isinstance(raw, str):
                return [part.strip() for part in raw.split(',') if part.strip()]
            return None

        def _normalize_color(raw):
            if raw is None or raw == 'null':
                return None
            return raw

        def _process_action(item: dict):
            strong_number = (item.get('strong_number') or '').strip()
            if not strong_number:
                return None
            action = item.get('action')
            if action == 'delete':
                user_strongs_dict.pop(strong_number, None)
                return {'strong_number': strong_number, 'deleted': True}
            if action in ('update', 'add'):
                translations = _normalize_translations(item.get('translations'))
                color = _normalize_color(item.get('color')) if 'color' in item else None
                if strong_number not in user_strongs_dict:
                    user_strongs_dict[strong_number] = {"translations": [], "color": None}
                if translations is not None:
                    user_strongs_dict[strong_number]["translations"] = translations
                if 'color' in item:
                    user_strongs_dict[strong_number]["color"] = color
                return {
                    'strong_number': strong_number,
                    'translations': user_strongs_dict[strong_number]["translations"],
                    'color': user_strongs_dict[strong_number].get("color"),
                }
            return None

        if request.is_json:
            payload = request.get_json(silent=True) or {}
            actions = payload.get('actions')
            if isinstance(actions, list):
                results = []
                for item in actions:
                    if not isinstance(item, dict):
                        continue
                    result = _process_action(item)
                    if result:
                        results.append(result)
                save_user_dict(user_strongs_dict)
                return jsonify({"success": True, "results": results})

        # Fallback for form submissions
        strong_number = request.form.get('strong_number')
        action = request.form.get('action')

        if action == 'delete':
            user_strongs_dict.pop(strong_number, None)
        elif action == 'update':
            translations = _normalize_translations(request.form.get('translations'))
            color = request.form.get('color')
            if strong_number not in user_strongs_dict:
                user_strongs_dict[strong_number] = {"translations": [], "color": None}
            if translations is not None:
                user_strongs_dict[strong_number]["translations"] = translations
            if color is not None:
                user_strongs_dict[strong_number]["color"] = _normalize_color(color)
        elif action == 'add':
            translations = _normalize_translations(request.form.get('translations', '')) or []
            color = _normalize_color(request.form.get('color'))
            user_strongs_dict[strong_number] = {"translations": translations, "color": color}
        save_user_dict(user_strongs_dict)
        return jsonify({"success": True})
    
    sorted_dict = dict(sorted(user_strongs_dict.items(), key=lambda x: int(x[0][1:])))

    # For GET requests, render the edit page
    return render_template(
        'edit_dict.html',
        strongs_dict=sorted_dict,
        upload_error=request.args.get('upload_error'),
        upload_success=request.args.get('upload_success'),
    )


@app.route('/upload_dict', methods=['POST'])
def upload_dict():
    file = request.files.get('dict_file')
    if not file or not file.filename:
        return redirect(url_for('edit_dict', upload_error="Please choose a JSON file to upload."))
    try:
        data = json.load(file.stream)
    except json.JSONDecodeError:
        return redirect(url_for('edit_dict', upload_error="Invalid JSON. Please upload a valid my_strongs_dict JSON file."))

    valid, message = _validate_user_dict(data)
    if not valid:
        return redirect(url_for('edit_dict', upload_error=message))

    save_user_dict(data)
    return redirect(url_for('edit_dict', upload_success="Custom Strong's list uploaded and saved."))

# Route for exporting your current list
@app.route('/export_dict')
def export_dict():
    user_strongs_dict = session.get('user_strongs_dict', default_strongs_dict.copy())
    
    # Create a temporary file
    with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.json') as temp_file:
        json.dump(user_strongs_dict, temp_file, indent=2)
    
    # Send the file
    return send_file(temp_file.name, as_attachment=True, download_name='my_strongs_dict.json')

@app.route('/about')
def about():
    return render_template('about.html')


@lru_cache(maxsize=128)
def generate_heatmap_counts(strong_number):
    """
    Generate raw count data for a Strong's number across all Bible chapters.

    Results are cached to improve performance on repeated requests.

    Args:
        strong_number: Strong's number (e.g., "H7225" or "G2316")

    Returns:
        tuple: (counts dict, max_count) where counts is {book: {chapter: count}}
    """
    strong = (strong_number or '').strip('{}').upper()
    if not strong:
        return {}, 0

    counts = {}
    max_count = 0
    verses_by_book = get_verses_by_book(kjv_data)
    for book, verses in verses_by_book.items():
        chapter_groups = {}
        for verse in verses:
            ch = int(verse.get('chapter', 0) or 0)
            chapter_groups.setdefault(ch, []).append(verse)

        counts[book] = {}
        for ch, verses_in_chapter in chapter_groups.items():
            chapter_counts = count_strongs_in_verses(verses_in_chapter, allowed={strong})
            cnt = chapter_counts.get(strong, 0)
            counts[book][ch] = cnt
            if cnt > max_count:
                max_count = cnt

    return counts, max_count


def generate_heatmap(strong_number):
    """
    Generate heatmap data for a Strong's number across all Bible chapters.

    Args:
        strong_number: Strong's number (e.g., "H7225" or "G2316")

    Returns:
        dict: Heatmap data with counts and colors for each book/chapter
    """
    counts, max_count = generate_heatmap_counts(strong_number)
    if not counts:
        return {}

    heatmap = {}
    for book in book_order:
        max_chapter = book_chapter_count.get(book, 0)
        row = []
        chapters = counts.get(book, {})
        for ch in range(1, max_chapter + 1):
            cnt = chapters.get(ch, 0)
            alpha = (cnt / max_count) if max_count else 0
            r = 255
            g = int(255 * (1 - alpha))
            b = int(255 * (1 - alpha))
            color = f'#{r:02x}{g:02x}{b:02x}'
            row.append({'count': cnt, 'color': color, 'chapter': ch})
        heatmap[book] = row

    return heatmap


# Color palette for cross-referenced words (distinct from red primary)
CROSSREF_COLORS = [
    (66, 133, 244),   # Blue
    (52, 168, 83),    # Green
    (251, 188, 4),    # Yellow/Gold
    (234, 67, 53),    # Red (alternative shade)
    (154, 66, 244),   # Purple
]


def generate_combined_heatmap(primary_strong, crossref_strongs):
    """
    Generate a combined heatmap with primary word and cross-referenced words.

    Args:
        primary_strong: Primary Strong's number
        crossref_strongs: List of cross-referenced Strong's numbers

    Returns:
        dict: Combined heatmap with multiple bars per cell (only when overlap exists)
    """
    # Get counts for primary word
    primary_counts, primary_max = generate_heatmap_counts(primary_strong)

    # Get counts for cross-referenced words
    crossref_data = []
    for i, ref_strong in enumerate(crossref_strongs[:4]):  # Limit to 4 crossrefs
        ref_counts, ref_max = generate_heatmap_counts(ref_strong)
        color_rgb = CROSSREF_COLORS[i % len(CROSSREF_COLORS)]
        crossref_data.append({
            'strong': ref_strong,
            'counts': ref_counts,
            'max_count': ref_max,
            'base_color': color_rgb
        })

    # Build combined heatmap
    heatmap = {}
    for book in book_order:
        max_chapter = book_chapter_count.get(book, 0)
        row = []
        primary_chapters = primary_counts.get(book, {})

        for ch in range(1, max_chapter + 1):
            # Primary word data
            primary_cnt = primary_chapters.get(ch, 0)
            primary_alpha = (primary_cnt / primary_max) if primary_max else 0
            r, g, b = 255, int(255 * (1 - primary_alpha)), int(255 * (1 - primary_alpha))
            primary_color = f'#{r:02x}{g:02x}{b:02x}'

            # Cross-reference data
            crossref_bars = []
            any_crossref_count = False
            for cref in crossref_data:
                ref_cnt = cref['counts'].get(book, {}).get(ch, 0)
                if ref_cnt > 0:
                    any_crossref_count = True
                ref_alpha = (ref_cnt / cref['max_count']) if cref['max_count'] else 0
                cr, cg, cb = cref['base_color']
                # Blend with white based on alpha
                br = int(255 - (255 - cr) * ref_alpha)
                bg = int(255 - (255 - cg) * ref_alpha)
                bb = int(255 - (255 - cb) * ref_alpha)
                ref_color = f'#{br:02x}{bg:02x}{bb:02x}'
                crossref_bars.append({
                    'strong': cref['strong'],
                    'count': ref_cnt,
                    'color': ref_color,
                    'base_color': f'#{cr:02x}{cg:02x}{cb:02x}'
                })

            # Determine if there's overlap (primary AND any crossref both have counts)
            has_overlap = primary_cnt > 0 and any_crossref_count

            row.append({
                'chapter': ch,
                'count': primary_cnt,
                'color': primary_color,
                'crossrefs': crossref_bars,
                'has_overlap': has_overlap,
                'any_crossref_count': any_crossref_count
            })
        heatmap[book] = row

    return heatmap


@app.route('/heatmap')
def heatmap():
    strong = request.args.get('strong', '').strip().upper()
    show_crossrefs = request.args.get('show_crossrefs', 'false') == 'true'
    from_crossref = request.args.get('from_crossref', '') == '1'

    data = None
    crossrefs = {'primary': [], 'secondary': []}
    crossref_metadata = {}
    active_crossrefs = []  # List of crossrefs being shown in combined view

    if strong:
        # Get cross-references for this Strong's number
        if strong.startswith('H'):
            source_map = hebrew_to_greek
        else:
            source_map = greek_to_hebrew

        entry = source_map.get(strong, {})
        crossrefs = {
            'primary': entry.get('primary', []),
            'secondary': entry.get('secondary', [])
        }

        # Build metadata for cross-referenced words
        all_refs = crossrefs['primary'] + crossrefs['secondary']
        target_map = greek_to_hebrew if strong.startswith('H') else hebrew_to_greek
        for ref in all_refs[:6]:  # Limit to 6 cross-refs
            ref_entry = target_map.get(ref, {})
            # Also check the source map for the ref's own entry if target doesn't have it
            if not ref_entry:
                ref_entry = source_map.get(ref, {})
            crossref_metadata[ref] = {
                'lemma': ref_entry.get('lemma', ''),
                'xlit': ref_entry.get('xlit', ''),
                'gloss': ref_entry.get('gloss', '')
            }

        # Generate heatmap - combined if crossrefs toggled on
        if show_crossrefs and crossrefs['primary']:
            active_crossrefs = crossrefs['primary'][:4]  # Limit to 4 crossrefs in combined view
            data = generate_combined_heatmap(strong, active_crossrefs)
        else:
            data = generate_heatmap(strong)

    ordered_books = [b for b, _ in sorted(book_order.items(), key=lambda x: x[1])]
    return render_template(
        'heatmap.html',
        strong=strong,
        data=data,
        ordered_books=ordered_books,
        crossrefs=crossrefs,
        crossref_metadata=crossref_metadata,
        active_crossrefs=active_crossrefs,
        show_crossrefs=show_crossrefs,
        from_crossref=from_crossref,
        crossref_colors=['#4285f4', '#34a853', '#fbbc04', '#ea4335', '#9a42f4']  # For legend
    )


@app.route('/api/books')
def api_books():
    """
    Return list of books with their chapter counts for frontend autocomplete.
    Books are ordered by their position in the Bible.
    """
    ordered_books = sorted(book_order.items(), key=lambda x: x[1])
    return jsonify({
        'books': [
            {'name': name, 'chapters': book_chapter_count.get(name, 0)}
            for name, _ in ordered_books
        ]
    })


@app.route('/api/crossref/<strong_number>')
def api_crossref(strong_number):
    """
    Get cross-references for a Strong's number.
    Returns Greek equivalents for Hebrew numbers and vice versa.
    """
    import re
    strong_number = strong_number.upper().strip()

    # Validate format
    if not re.match(r'^[HG]\d+$', strong_number):
        return jsonify({'error': "Invalid Strong's number format. Use H#### or G####"}), 400

    # Determine direction and get cross-references
    if strong_number.startswith('H'):
        source_map = hebrew_to_greek
        language = 'hebrew'
    else:
        source_map = greek_to_hebrew
        language = 'greek'

    crossref = source_map.get(strong_number, {})

    # Build response with metadata
    def enrich_strong(sn):
        """Add metadata from strongs_data for a Strong's number."""
        # Find entry in strongs_data
        entry = next((s for s in strongs_data if s.get('number') == sn), {})
        return {
            'strong': sn,
            'lemma': entry.get('lemma', crossref.get('lemma', '')),
            'xlit': entry.get('xlit', crossref.get('xlit', '')),
            'gloss': entry.get('description', '')[:80] + '...' if len(entry.get('description', '')) > 80 else entry.get('description', ''),
        }

    primary = [enrich_strong(sn) for sn in crossref.get('primary', [])]
    secondary = [enrich_strong(sn) for sn in crossref.get('secondary', [])]

    return jsonify({
        'strong': strong_number,
        'language': language,
        'cross_refs': {
            'primary': primary,
            'secondary': secondary
        },
        'notes': crossref.get('notes', '')
    })


@app.route('/api/crossref/batch')
def api_crossref_batch():
    """
    Get cross-references for multiple Strong's numbers at once.
    Used by dictionary editor to show cross-refs for all entries.
    """
    import re
    strongs_param = request.args.get('strongs', '')
    strongs_list = [s.strip().upper() for s in strongs_param.split(',') if s.strip()]

    if len(strongs_list) > 100:
        return jsonify({'error': 'Maximum 100 Strong\'s numbers per request'}), 400

    results = {}
    for sn in strongs_list:
        if not re.match(r'^[HG]\d+$', sn):
            continue

        source_map = hebrew_to_greek if sn.startswith('H') else greek_to_hebrew
        crossref = source_map.get(sn, {})
        results[sn] = {
            'primary': crossref.get('primary', []),
            'secondary': crossref.get('secondary', [])
        }

    return jsonify({'results': results})
