import hashlib
import html
import io
import os
import json
import re
import uuid
import time
from collections import Counter
from datetime import datetime, timedelta
from functools import lru_cache
from flask import render_template, request, jsonify, session, send_file, redirect, url_for, g, abort
from app import app
from .transliteration import (
    transliterate_chapter,
    count_strongs_in_verses,
    is_valid_hex_color,
)
from .data import load_bible_data

# Get logger
logger = app.logger

# Paths
current_file_path = os.path.abspath(__file__)
current_dir = os.path.dirname(current_file_path)
UPLOAD_DATA_DIR = os.path.join(current_dir, 'uploads')
os.makedirs(UPLOAD_DATA_DIR, exist_ok=True)
# Shared (link-shareable) word lists live in a subfolder, content-addressed by
# a hash of their JSON so identical lists dedupe and links are idempotent.
SHARED_DATA_DIR = os.path.join(UPLOAD_DATA_DIR, 'shared')
os.makedirs(SHARED_DATA_DIR, exist_ok=True)
SHARE_CODE_REGEX = re.compile(r'[0-9a-f]{12}')
SHARE_MAX_BYTES = 256 * 1024
SHARED_TTL_DAYS = 90  # mtime is refreshed on access, so active links persist

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

CLEANUP_INTERVAL_SECONDS = 24 * 60 * 60
_CLEANUP_STAMP_PATH = os.path.join(UPLOAD_DATA_DIR, '.last_cleanup')


def _maybe_cleanup_uploads(days=30):
    """Run cleanup at most once per 24h, guarded by a timestamp file.

    cleanup_old_session_files previously ran only at import, so a long-lived
    server never pruned the uploads directory again. Piggybacking on write
    traffic (save_user_dict) keeps it pruning without adding a scheduler; the
    stamp file throttles it and is written first so concurrent workers don't
    all sweep at once. The stamp isn't a .json file, so cleanup skips it.
    """
    try:
        last = os.path.getmtime(_CLEANUP_STAMP_PATH)
    except OSError:
        last = 0
    if time.time() - last < CLEANUP_INTERVAL_SECONDS:
        return
    try:
        with open(_CLEANUP_STAMP_PATH, 'w') as f:
            f.write(str(time.time()))
    except OSError:
        pass
    cleanup_old_session_files(days=days)
    _cleanup_shared_lists(days=SHARED_TTL_DAYS)


def _cleanup_shared_lists(days=SHARED_TTL_DAYS):
    """Prune shared word-list files not accessed in `days` days.

    Shared files get their mtime refreshed each time a share link is opened,
    so only genuinely abandoned links expire.
    """
    try:
        cutoff = time.time() - (days * 24 * 60 * 60)
        for filename in os.listdir(SHARED_DATA_DIR):
            if not filename.endswith('.json'):
                continue
            filepath = os.path.join(SHARED_DATA_DIR, filename)
            try:
                if os.path.isfile(filepath) and os.path.getmtime(filepath) < cutoff:
                    os.remove(filepath)
            except OSError:
                continue
    except OSError:
        pass


# Prune once at startup, then again on traffic at most daily (see save_user_dict).
_maybe_cleanup_uploads(days=30)

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
        if not re.fullmatch(r'[HG]\d+', key):
            return False, f"Invalid Strong's number \"{key}\": use H#### or G#### (e.g., \"H7225\")."
        if not isinstance(val, dict):
            return False, f"Entry for {key} must be an object."
        translations = val.get("translations")
        if translations is None or not isinstance(translations, list) or not all(isinstance(t, str) for t in translations):
            return False, f"Entry for {key} must include a list of translations."
        color = val.get("color", None)
        if color is not None and not isinstance(color, str):
            return False, f"Color for {key} must be a string (hex) or null."
        if color is not None and not is_valid_hex_color(color):
            return False, f"Color for {key} must be a valid hex color like #RRGGBB or null."
    return True, None


def _user_dict_path():
    return os.path.join(UPLOAD_DATA_DIR, f"{get_session_id()}.json")


def save_user_dict(user_dict: dict):
    # The per-user JSON file is the source of truth. Only the user_id lives in
    # the session cookie (see get_session_id); the dictionary itself is far too
    # large for the ~4KB signed-cookie limit and would be silently dropped by
    # the browser, taking the user_id with it. Cache on flask.g for the rest of
    # this request so repeated reads don't re-hit disk.
    g.user_strongs_dict = user_dict
    try:
        with open(_user_dict_path(), 'w', encoding='utf-8') as f:
            json.dump(user_dict, f, ensure_ascii=False, indent=2)
    except OSError as e:
        # If persisting to disk fails, we still keep the in-request copy.
        logger.warning(f"Failed to persist user dictionary to disk: {e}")
    # Opportunistically prune stale session files (throttled to once/day).
    _maybe_cleanup_uploads(days=30)


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
    # Serve from the per-request cache if we've already loaded/saved this request.
    if 'user_strongs_dict' in g:
        return g.user_strongs_dict

    default_dict = {k: {"translations": v, "color": None} for k, v in default_strongs_dict.items()}

    user_file = _user_dict_path()
    if os.path.exists(user_file):
        try:
            with open(user_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            valid, error = _validate_user_dict(data)
            if valid:
                g.user_strongs_dict = data
                return data
            else:
                logger.warning(f"Invalid user dictionary file: {error}")
        except (OSError, json.JSONDecodeError) as e:
            logger.error(f"Failed to load user dictionary from {user_file}: {e}")

    g.user_strongs_dict = default_dict
    return default_dict

# Load all bulk data once at startup and build the shared indexes. The data
# files live in app/data/ (non-routable); the loader builds the per-book and
# per-Strong's maps a single time instead of on every request.
outlines_path = os.path.abspath(os.path.join(current_dir, '..', 'bible_bsb_book_outlines_with_ranges.json'))
bible_data = load_bible_data(outlines_path=outlines_path, logger=logger)
app.extensions['bible_data'] = bible_data

# Read-only module-level views into the loaded data so the rest of this module
# (and its many references to these maps) stays readable.
default_strongs_dict = bible_data.default_strongs_dict
outline_data = bible_data.outline_data
hebrew_to_greek = bible_data.hebrew_to_greek
greek_to_hebrew = bible_data.greek_to_hebrew
book_order = bible_data.book_order
book_chapter_count = bible_data.book_chapter_count
chapter_verse_counts = bible_data.chapter_verse_counts
book_name_lookup = bible_data.book_name_lookup

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
    'names': True,
    'phrases': True,
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
                result = transliterate_chapter(book, chapter, user_strongs_dict, bible_data, active_units=active_units)
                active_unit = get_active_unit(book, chapter)

    # Only show book overview and progress for valid requests
    total_chapters = book_chapter_count.get(book) if is_valid_request else None
    book_progress = (chapter / total_chapters * 100) if total_chapters and chapter else None
    verses = build_verses_for_render(result, active_units) if result else []
    chapter_phrases = get_chapter_phrases(book, chapter) if is_valid_request else []

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
        chapter_phrases=chapter_phrases,
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
    result = transliterate_chapter(book, chapter, user_strongs_dict, bible_data, active_units=active_units)
    active_unit = get_active_unit(book, chapter)
    total_chapters = book_chapter_count.get(book)
    book_progress = (chapter / total_chapters * 100) if total_chapters and chapter else None
    verses = build_verses_for_render(result, active_units) if result else []
    chapter_phrases = get_chapter_phrases(book, chapter)

    user_strongs_keys = list(user_strongs_dict.keys())

    # Generate book data for autocomplete (same as home route)
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
        focus_strong='',
        from_heatmap=False,
        context_defaults=DEFAULT_CONTEXT_OPTIONS,
        user_strongs_keys=user_strongs_keys,
        book_data=book_data,
        chapter_phrases=chapter_phrases,
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
            # Silently drop anything that isn't a strict #RRGGBB hex value so a
            # bad color can never be persisted or later rendered into a style
            # attribute.
            return raw if is_valid_hex_color(raw) else None

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
    # Use the canonical accessor so the exported file always has the wrapped
    # {"translations": [...], "color": ...} shape that _validate_user_dict (and
    # therefore /upload_dict) expects. Reading the raw default dict here used to
    # produce a file the app's own importer rejected. Stream from memory rather
    # than a NamedTemporaryFile(delete=False) that was never cleaned up.
    user_strongs_dict = get_user_strongs_dict()
    payload = json.dumps(user_strongs_dict, ensure_ascii=False, indent=2).encode('utf-8')
    return send_file(
        io.BytesIO(payload),
        mimetype='application/json',
        as_attachment=True,
        download_name='my_strongs_dict.json',
    )


def _strong_sort_key(sn):
    """Canonical ordering for Strong's numbers: Hebrew first, then numeric."""
    match = re.fullmatch(r'([HG])(\d+)', sn or '')
    if not match:
        return (2, 0, sn or '')
    return (0 if match.group(1) == 'H' else 1, int(match.group(2)), sn)


@app.route('/share_dict', methods=['POST'])
def share_dict():
    """Publish the caller's current word list as a shareable link.

    The list is written content-addressed (sha256 of its canonical JSON), so
    sharing the same list twice yields the same link and nothing is
    overwritten. No accounts needed: the link itself is the capability.
    """
    user_strongs_dict = get_user_strongs_dict()
    if not user_strongs_dict:
        return jsonify({'success': False, 'error': 'Your list is empty — nothing to share.'}), 400
    valid, message = _validate_user_dict(user_strongs_dict)
    if not valid:
        return jsonify({'success': False, 'error': message}), 400

    payload = json.dumps(user_strongs_dict, ensure_ascii=False, sort_keys=True, indent=2).encode('utf-8')
    if len(payload) > SHARE_MAX_BYTES:
        return jsonify({'success': False, 'error': 'This list is too large to share.'}), 400

    code = hashlib.sha256(payload).hexdigest()[:12]
    path = os.path.join(SHARED_DATA_DIR, f'{code}.json')
    if not os.path.exists(path):
        try:
            with open(path, 'wb') as f:
                f.write(payload)
        except OSError as e:
            logger.error(f"Failed to write shared list {code}: {e}")
            return jsonify({'success': False, 'error': 'Could not save the shared list.'}), 500

    return jsonify({'success': True, 'code': code, 'url': url_for('import_list', code=code)})


def _load_shared_list(code):
    """Load and validate a shared list by code; returns None if unusable."""
    if not SHARE_CODE_REGEX.fullmatch(code or ''):
        return None
    path = os.path.join(SHARED_DATA_DIR, f'{code}.json')
    if not os.path.isfile(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(f"Failed to load shared list {code}: {e}")
        return None
    valid, _ = _validate_user_dict(data)
    if not valid:
        return None
    try:
        # Refresh mtime so links that are still being opened outlive the TTL.
        os.utime(path, None)
    except OSError:
        pass
    return data


@app.route('/import')
def import_list():
    """Preview a shared word list before merging it into your own."""
    code = (request.args.get('code') or '').strip().lower()
    shared = _load_shared_list(code)
    if shared is None:
        return render_template('import_list.html', code=code, entries=None, overlap=0), 404

    user_dict = get_user_strongs_dict()
    entries = []
    for sn in sorted(shared.keys(), key=_strong_sort_key):
        item = shared[sn]
        meta = bible_data.strongs_by_number.get(sn, {})
        entries.append({
            'strong': sn,
            'translations': item.get('translations', []),
            'color': item.get('color'),
            'xlit': meta.get('xlit', ''),
            'lemma': meta.get('lemma', ''),
            'already': sn in user_dict,
        })
    overlap = sum(1 for e in entries if e['already'])
    return render_template('import_list.html', code=code, entries=entries, overlap=overlap)


@app.route('/import', methods=['POST'])
def import_list_apply():
    """Merge or replace the caller's list with a shared one."""
    code = (request.form.get('code') or '').strip().lower()
    mode = request.form.get('mode', 'merge')
    shared = _load_shared_list(code)
    if shared is None:
        return redirect(url_for('edit_dict', upload_error='That shared list link is invalid or has expired.'))

    if mode == 'replace':
        new_dict = dict(shared)
        summary = f"replaced your list with {len(shared)} shared words"
    else:
        new_dict = dict(get_user_strongs_dict())
        new_dict.update(shared)
        summary = f"merged {len(shared)} shared words into your list"
    save_user_dict(new_dict)
    return redirect(url_for('edit_dict', upload_success=f'Shared list imported — {summary}.'))


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
    verses_by_book = bible_data.verses_by_book
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
    (168, 85, 247),   # Purple (violet)
    (236, 72, 153),   # Pink
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
    top_books = []  # Precomputed list of (book, count) tuples sorted by count

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
        # Combine primary and secondary crossrefs (primary takes precedence)
        all_crossrefs = crossrefs['primary'] + crossrefs['secondary']
        if show_crossrefs and all_crossrefs:
            active_crossrefs = all_crossrefs[:4]  # Limit to 4 crossrefs in combined view
            data = generate_combined_heatmap(strong, active_crossrefs)
        else:
            data = generate_heatmap(strong)

        # Compute top books by total count (moved from template to avoid Jinja2 limitations)
        if data:
            book_totals = {}
            for book, chapters in data.items():
                total = sum(cell.get('count', 0) for cell in chapters)
                if total > 0:
                    book_totals[book] = total
            # Sort by count descending and take top 8
            top_books = sorted(book_totals.items(), key=lambda x: x[1], reverse=True)[:8]

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
        top_books=top_books,
        crossref_colors=['#4285f4', '#34a853', '#fbbc04', '#a855f7', '#ec4899']  # For legend
    )


STRONG_FORMAT_REGEX = re.compile(r'[HG]\d+')
# Any Strong's / grammar marker: {H7225}, {(H8804)}, and the {H8804)} data quirk.
ANY_MARKER_REGEX = re.compile(r'\{\(?[HG]\d+\)?\}')
# A single plain lexical marker (no grammar codes) — enumerated in text order,
# its index is the lexical-token position used by the phrase index.
PLAIN_MARKER_REGEX = re.compile(r'\{([HG]\d+)\}')
# The rendered English word immediately preceding a marker (highlight target).
WORD_BEFORE_MARKER_REGEX = re.compile(r"[A-Za-z][A-Za-z']*$")
PHRASES_PER_PAGE = 25


def _render_occurrence_html(text, strong):
    """Render a verse's raw marked-up text as clean HTML with the target word
    wrapped in <mark>. Escapes first, so only our own tags survive."""
    escaped = html.escape(text, quote=False)
    marked = re.sub(
        r"([A-Za-z][A-Za-z']*)\{" + re.escape(strong) + r'\}',
        r'<mark class="occ-hit">\1</mark>',
        escaped,
    )
    # A bare marker with no attached word (untranslated particles): drop it.
    marked = marked.replace('{' + strong + '}', '')
    return ANY_MARKER_REGEX.sub('', marked)


@lru_cache(maxsize=32)
def generate_occurrences(strong_number):
    """Collect every verse containing a Strong's number, grouped by book.

    Returns (books, total) where books is a tuple of
    (book_name, occurrence_count, ((chapter, verse, html), ...)) in canonical
    book order. Cached like generate_heatmap_counts: the scan walks all 31k
    verses, repeats are instant.
    """
    strong = (strong_number or '').strip('{}').upper()
    if not STRONG_FORMAT_REGEX.fullmatch(strong):
        return (), 0

    marker = '{' + strong + '}'
    books = []
    total = 0
    for book, _ in sorted(book_order.items(), key=lambda x: x[1]):
        rows = []
        book_count = 0
        for verse in bible_data.verses_by_book.get(book, []):
            text = verse.get('text', '')
            hits = text.count(marker)
            if not hits:
                continue
            book_count += hits
            rows.append((int(verse['chapter']), int(verse['verse']), _render_occurrence_html(text, strong)))
        if rows:
            books.append((book, book_count, tuple(rows)))
            total += book_count
    return tuple(books), total


@app.route('/occurrences')
def occurrences():
    """Concordance view: every verse where a Strong's number occurs."""
    strong = (request.args.get('strong') or '').strip().strip('{}').upper()
    error = None
    word_meta = None
    books = []
    total = 0

    if strong:
        if not STRONG_FORMAT_REGEX.fullmatch(strong):
            error = "Invalid Strong's number format. Use H#### or G#### (e.g., H7225)."
        else:
            book_data, total = generate_occurrences(strong)
            books = [
                {
                    'name': name,
                    'count': count,
                    'verses': [{'chapter': ch, 'verse': v, 'html': h} for ch, v, h in rows],
                }
                for name, count, rows in book_data
            ]
            entry = bible_data.strongs_by_number.get(strong, {})
            description = entry.get('description', '') or ''
            word_meta = {
                'lemma': entry.get('lemma', ''),
                'xlit': entry.get('xlit', ''),
                'pronounce': entry.get('pronounce', ''),
                'description': description[:220] + '…' if len(description) > 220 else description,
            }

    return render_template(
        'occurrences.html',
        strong=strong,
        error=error,
        word_meta=word_meta,
        books=books,
        total=total,
        # Small result sets read best fully expanded; big ones start collapsed.
        open_all=bool(total) and total <= 120,
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
        """Add metadata from the Strong's lexicon for a Strong's number."""
        # O(1) lookup instead of scanning the full lexicon per cross-reference.
        entry = bible_data.strongs_by_number.get(sn, {})
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


@app.route('/api/word_lookup')
def api_word_lookup():
    """Reverse lookup: English word -> ranked Strong's number candidates.

    Backs the "find a word" box on the dictionary editor, so readers can add
    e.g. "mercy" without knowing H2617 first. Uses the startup-built inverted
    index over the KJV's word{H####} pairs; exact word match first, prefix
    aggregation as a fallback.
    """
    q = (request.args.get('q') or '').strip().lower()
    if len(q) < 2:
        return jsonify({'error': 'Type at least 2 letters to search.'}), 400

    index = bible_data.english_word_index
    counts = Counter()
    matched_word = {}  # strong -> the KJV word form that matched

    exact = index.get(q)
    if exact:
        counts.update(exact)
        for sn in exact:
            matched_word[sn] = q
    else:
        for word, word_counts in index.items():
            if word.startswith(q):
                counts.update(word_counts)
                for sn in word_counts:
                    matched_word.setdefault(sn, word)

    results = []
    for sn, count in counts.most_common(8):
        entry = bible_data.strongs_by_number.get(sn, {})
        description = entry.get('description', '') or ''
        results.append({
            'strong': sn,
            'count': count,
            'word': matched_word.get(sn, q),
            'lemma': entry.get('lemma', ''),
            'xlit': entry.get('xlit', ''),
            'gloss': description[:100] + '…' if len(description) > 100 else description,
        })

    return jsonify({'query': q, 'exact': bool(exact), 'results': results})


# --- Rare original-language phrases ------------------------------------------
# A phrase is an ordered run of 2–5 original-language lexical tokens (Strong's
# numbers) taken from the KJV's own marker stream. "Echoes" recur in exactly
# two book-chapter passages. The index is built offline (scripts/
# build_phrase_index.py) and loaded onto BibleData at startup; these routes only
# read it, keeping phrase identity out of the English-rendering tokenizer.

@lru_cache(maxsize=None)
def _verse_text_map(book):
    """(chapter, verse) -> raw marked-up text for one book, built once."""
    return {
        (int(v['chapter']), int(v['verse'])): v.get('text', '')
        for v in bible_data.verses_by_book.get(book, [])
    }


def _render_phrase_verse_html(text, highlight_positions):
    """Render a verse as clean HTML with the phrase's rendered words in <mark>.

    ``highlight_positions`` are 0-based lexical-marker indices; the English word
    immediately before each such marker (if any) is wrapped. Markers and grammar
    codes are stripped and text is escaped first, so only our own tags survive.
    Tokens with no rendered word (untranslated particles) simply add no
    highlight — the plan's "show the whole verse when alignment is ambiguous".
    """
    highlight = set(highlight_positions)
    parts = []
    cursor = 0
    for idx, m in enumerate(PLAIN_MARKER_REGEX.finditer(text)):
        segment = text[cursor:m.start()]
        word_match = WORD_BEFORE_MARKER_REGEX.search(segment) if idx in highlight else None
        if word_match:
            parts.append(html.escape(segment[:word_match.start()], quote=False))
            parts.append(
                '<mark class="phrase-hit">'
                + html.escape(segment[word_match.start():], quote=False)
                + '</mark>'
            )
        else:
            parts.append(html.escape(segment, quote=False))
        cursor = m.end()
    parts.append(html.escape(text[cursor:], quote=False))
    return ANY_MARKER_REGEX.sub('', ''.join(parts))


def _phrase_english_span(text, start, span):
    """The KJV English rendering of a phrase occurrence.

    Returns the marker-free text from the first phrase-token's rendered word
    through the last (e.g. "coat of many colours" for H3801-H6446 in Gen 37:3),
    so readers see the phrase in English without opening the detail page. Empty
    if none of the phrase's tokens rendered a word (untranslated particles).
    """
    last = start + span - 1
    cleaned_parts = []
    length = 0          # running length of the cleaned (marker-free) text
    first_start = None
    last_end = None
    cursor = 0
    for idx, m in enumerate(PLAIN_MARKER_REGEX.finditer(text)):
        segment = ANY_MARKER_REGEX.sub('', text[cursor:m.start()])
        if start <= idx <= last:
            word = WORD_BEFORE_MARKER_REGEX.search(segment)
            if word:
                if first_start is None:
                    first_start = length + word.start()
                last_end = length + len(segment)
        cleaned_parts.append(segment)
        length += len(segment)
        cursor = m.end()
    cleaned_parts.append(ANY_MARKER_REGEX.sub('', text[cursor:]))
    if first_start is None or last_end is None:
        return ''
    return ''.join(cleaned_parts)[first_start:last_end].strip()


def _phrase_summary(record, current_passage=None):
    """Build the display view of a phrase record for panel/browse/detail.

    ``english`` and ``verse_ref`` describe how/where the phrase reads in the
    current chapter (or, for the detail page where ``current_passage`` is None,
    its first occurrence overall) so a reader can recognize the phrase before
    navigating. When ``current_passage`` (a (book, chapter) tuple) is given,
    ``other_passage`` is the echo's *other* passage, for "also 2 Samuel 13".
    """
    tokens = [
        {
            'strong': sn,
            'lemma': bible_data.strongs_by_number.get(sn, {}).get('lemma', ''),
            'xlit': bible_data.strongs_by_number.get(sn, {}).get('xlit', ''),
        }
        for sn in record['tokens']
    ]
    other_passage = None
    if current_passage is not None:
        others = [p for p in record['passages'] if p != current_passage]
        other_passage = others[0] if others else None

    # English rendering + verse references, from the occurrences in the current
    # chapter (panel/browse) or the first occurrence overall (detail header).
    if current_passage is not None:
        here = [o for o in record['occurrences'] if (o[0], o[1]) == current_passage]
    else:
        here = record['occurrences'][:1]
    english = ''
    verse_ref = ''
    if here:
        book, chapter, verse, start = here[0]
        english = _phrase_english_span(
            _verse_text_map(book).get((chapter, verse), ''), start, len(record['tokens'])
        )
        verses = sorted({o[2] for o in here})
        verse_ref = f"{chapter}:" + ', '.join(str(v) for v in verses)

    return {
        'key': record['key'],
        'lang': record['lang'],
        'tokens': tokens,
        'english': english,
        'verse_ref': verse_ref,
        'lemma_seq': ' '.join(t['lemma'] for t in tokens if t['lemma']),
        'xlit_seq': ' '.join(t['xlit'] for t in tokens if t['xlit']),
        'strong_seq': ' '.join(record['tokens']),
        'passage_count': len(record['passages']),
        'occ_count': record['occ_count'],
        'passages': record['passages'],
        'other_passage': other_passage,
    }


def get_chapter_phrases(book, chapter, limit=8):
    """Top rare-phrase echoes for a chapter, best first, for the reading panel."""
    keys = bible_data.phrases_by_chapter.get((book, chapter), [])
    current = (book, chapter)
    return [
        _phrase_summary(bible_data.phrase_index[key], current)
        for key in keys[:limit]
    ]


@app.route('/phrases')
def phrases_browse():
    """Browse every rare-phrase echo in a chapter, paged. Echoes only in v1."""
    raw_book = (request.args.get('book') or '').strip()
    book = normalize_book_name(raw_book) if raw_book else ''
    error = None

    chapter = None
    chapter_str = (request.args.get('chapter') or '').strip()
    if chapter_str:
        try:
            chapter = int(chapter_str)
        except ValueError:
            error = "Chapter must be a valid number"

    try:
        page = max(1, int(request.args.get('page', '1')))
    except ValueError:
        page = 1

    phrases = []
    total = 0
    total_pages = 1
    if book and chapter is not None and not error:
        is_valid, validation_error = validate_book_chapter(book, chapter)
        if not is_valid:
            error = validation_error
        else:
            keys = bible_data.phrases_by_chapter.get((book, chapter), [])
            total = len(keys)
            total_pages = max(1, (total + PHRASES_PER_PAGE - 1) // PHRASES_PER_PAGE)
            page = min(page, total_pages)
            start = (page - 1) * PHRASES_PER_PAGE
            current = (book, chapter)
            phrases = [
                _phrase_summary(bible_data.phrase_index[key], current)
                for key in keys[start:start + PHRASES_PER_PAGE]
            ]

    return render_template(
        'phrases_browse.html',
        book=book,
        chapter=chapter,
        error=error,
        phrases=phrases,
        total=total,
        page=page,
        total_pages=total_pages,
    )


@app.route('/phrases/<key>')
def phrase_detail(key):
    """Detail for one phrase: every occurrence grouped by passage, with the
    matched words highlighted. Unknown/malformed/mixed-language keys 404."""
    record = bible_data.phrase_index.get((key or '').strip().upper())
    if not record:
        abort(404)

    span = len(record['tokens'])
    grouped = {}
    for book, chapter, verse, start in record['occurrences']:
        text = _verse_text_map(book).get((chapter, verse), '')
        grouped.setdefault((book, chapter), []).append({
            'chapter': chapter,
            'verse': verse,
            'html': _render_phrase_verse_html(text, range(start, start + span)),
        })
    passages = [
        {'book': book, 'chapter': chapter, 'verses': grouped[(book, chapter)]}
        for (book, chapter) in record['passages']
    ]

    return render_template(
        'phrase_detail.html',
        phrase=_phrase_summary(record),
        passages=passages,
    )
