import hashlib
import os
import json
import uuid
import tempfile
from flask import render_template, request, jsonify, session, send_file, redirect, url_for
from app import app
from .transliteration import transliterate_chapter

# Paths
current_file_path = os.path.abspath(__file__)
current_dir = os.path.dirname(current_file_path)
STATIC_DATA_DIR = os.path.join(current_dir, 'static')
UPLOAD_DATA_DIR = os.path.join(current_dir, 'uploads')
os.makedirs(UPLOAD_DATA_DIR, exist_ok=True)

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
    except OSError:
        # If persisting to disk fails, we still keep the session copy.
        pass


def get_user_strongs_dict():
    default_dict = {k: {"translations": v, "color": None} for k, v in default_strongs_dict.items()}
    if 'user_strongs_dict' in session:
        return session['user_strongs_dict']

    user_file = _user_dict_path()
    if os.path.exists(user_file):
        try:
            with open(user_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            valid, _ = _validate_user_dict(data)
            if valid:
                session['user_strongs_dict'] = data
                return data
        except (OSError, json.JSONDecodeError):
            pass

    session['user_strongs_dict'] = default_dict
    return default_dict

strongs_dict_path = os.path.join(STATIC_DATA_DIR, 'strongs_dict.json')
strongs_path = os.path.join(STATIC_DATA_DIR, 'Strongs.json')
kjv_path = os.path.join(STATIC_DATA_DIR, 'kjv_strongs.json')
sound_annotations_path = os.path.join(STATIC_DATA_DIR, 'sound_annotations.json')
outlines_path = os.path.abspath(os.path.join(current_dir, '..', 'bible_bsb_book_outlines_with_ranges.json'))


def _load_sound_annotations_from_disk(path: str) -> dict:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict) and data:
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def _build_sound_annotations_if_configured(target_path: str) -> dict:
    """Attempt to build sound annotations when source data is provided.

    The builder runs once at startup when the packaged file is empty and the
    environment exposes the required assets for `build_sound_annotations.py`.
    """

    bible_source = os.environ.get('SOUND_ANNOTATIONS_BIBLE_PATH')
    lexicon_source = os.environ.get('SOUND_ANNOTATIONS_LEXICON_PATH')
    units_source = os.environ.get('SOUND_ANNOTATIONS_UNITS_PATH', outlines_path)

    if not (bible_source and lexicon_source):
        app.logger.info(
            'Sound annotations unavailable; set SOUND_ANNOTATIONS_BIBLE_PATH and '
            'SOUND_ANNOTATIONS_LEXICON_PATH to auto-build.'
        )
        return {}

    if not (os.path.exists(bible_source) and os.path.exists(lexicon_source) and os.path.exists(units_source)):
        app.logger.warning('Sound annotation inputs are missing; skipping build step.')
        return {}

    try:
        from build_sound_annotations import (
            load_bible_tokens,
            load_literary_units,
            load_lexicon_roots,
            build_index_by_book_chapter_verse,
            build_sound_annotations as compute_sound_annotations,
        )

        bible_tokens = load_bible_tokens(bible_source)
        lexicon = load_lexicon_roots(lexicon_source)
        units = load_literary_units(units_source)
        bible_index = build_index_by_book_chapter_verse(bible_tokens)
        annotations = compute_sound_annotations(bible_index, units, lexicon)

        with open(target_path, 'w', encoding='utf-8') as handle:
            json.dump(annotations, handle, ensure_ascii=False, indent=2)
            handle.write('\n')

        app.logger.info('Built sound_annotations.json from configured sources.')
        return annotations
    except Exception as exc:  # noqa: BLE001
        app.logger.warning('Failed to build sound annotations: %s', exc)
        return {}


def _load_sound_annotations():
    annotations = _load_sound_annotations_from_disk(sound_annotations_path)
    if annotations:
        return annotations
    return _build_sound_annotations_if_configured(sound_annotations_path)


with open(strongs_dict_path, 'r', encoding='utf-8') as f:
    default_strongs_dict = json.load(f)
with open(strongs_path, 'r', encoding='utf-8') as f:
    strongs_data = json.load(f)
with open(kjv_path, 'r', encoding='utf-8') as f:
    kjv_data = json.load(f)
sound_annotations = _load_sound_annotations()
with open(outlines_path, 'r', encoding='utf-8') as f:
    outline_data = json.load(f)

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
    start = unit.get('range_start', {})
    end = unit.get('range_end', {})
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

    start = unit.get('range_start', {})
    end = unit.get('range_end', {})
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
        start = unit.get('range_start', {})
        end = unit.get('range_end', {})
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
            })

    return active


def get_chapter_sound_annotations(book: str, chapter: int) -> dict:
    """Return sound annotations for a specific chapter, if available."""

    if not book or not chapter:
        return {}

    book_data = sound_annotations.get(book) or {}
    return book_data.get(str(chapter)) or {}


def get_active_unit(book: str, chapter: int):
    if not book or not chapter:
        return None

    units = outline_data.get(book)
    if not units:
        return None

    for unit in units:
        start = unit.get('range_start', {})
        end = unit.get('range_end', {})
        start_ch = int(start.get('chapter', 0))
        end_ch = int(end.get('chapter', 0))

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

@app.route('/', methods=['GET', 'POST'])
def home():
    book = request.form.get('book', '') or request.args.get('book', '')
    chapter_str = request.form.get('chapter', '') or request.args.get('chapter', '')

    chapter = None
    if chapter_str:
        try:
            chapter = int(chapter_str)
        except ValueError:
            chapter = None

    result = ""
    active_unit = None
    sound_slice = {}
    sound_summary = {
        'has_annotations': False,
        'verse_count': 0,
        'token_count': 0,
    }
    if request.method == 'POST' or (book and chapter):
        if book and chapter:
            user_strongs_dict = get_user_strongs_dict()
            sound_slice = sound_annotations.get(book, {}).get(str(chapter), {})
            if sound_slice:
                verse_count = 0
                token_count = 0
                for verse_data in sound_slice.values():
                    positions = set()
                    for positions_list in verse_data.get('local_roots', {}).values():
                        positions.update(positions_list)
                    for positions_list in verse_data.get('local_initials', {}).values():
                        positions.update(positions_list)
                    if positions:
                        verse_count += 1
                        token_count += len(positions)

                sound_summary = {
                    'has_annotations': verse_count > 0,
                    'verse_count': verse_count,
                    'token_count': token_count,
                }
            result = transliterate_chapter(
                book, chapter, user_strongs_dict, strongs_data, kjv_data, sound_slice
            )
            active_unit = get_active_unit(book, chapter)

    total_chapters = book_chapter_count.get(book)
    book_progress = (chapter / total_chapters * 100) if total_chapters and chapter else None
    active_units = get_active_units(book, chapter) if book and chapter else []
    verses = build_verses_for_render(result, active_units) if result else []

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
        sound_annotations=sound_slice,
        sound_summary=sound_summary,
    )

@app.route('/navigate', methods=['POST'])
def navigate():
    book = request.form.get('book', '')
    chapter_str = request.form.get('chapter', '')
    try:
        chapter = int(chapter_str)
    except ValueError:
        chapter = 1
    direction = request.form.get('direction', '')

    if direction == 'next':
        chapter += 1
    elif direction == 'prev':
        chapter = max(1, chapter - 1)

    # Here you might want to add logic to handle book transitions

    user_strongs_dict = session.get('user_strongs_dict', default_strongs_dict)
    sound_slice = sound_annotations.get(book, {}).get(str(chapter), {})
    sound_summary = {
        'has_annotations': False,
        'verse_count': 0,
        'token_count': 0,
    }
    if sound_slice:
        verse_count = 0
        token_count = 0
        for verse_data in sound_slice.values():
            positions = set()
            for positions_list in verse_data.get('local_roots', {}).values():
                positions.update(positions_list)
            for positions_list in verse_data.get('local_initials', {}).values():
                positions.update(positions_list)
            if positions:
                verse_count += 1
                token_count += len(positions)

        sound_summary = {
            'has_annotations': verse_count > 0,
            'verse_count': verse_count,
            'token_count': token_count,
        }
    result = transliterate_chapter(
        book, chapter, user_strongs_dict, strongs_data, kjv_data, sound_slice
    )
    active_unit = get_active_unit(book, chapter)
    active_units = get_active_units(book, chapter)
    total_chapters = book_chapter_count.get(book)
    book_progress = (chapter / total_chapters * 100) if total_chapters and chapter else None
    verses = build_verses_for_render(result, active_units) if result else []

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
        sound_annotations=sound_slice,
        sound_summary=sound_summary,
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
        # Update the dictionary based on user input
        strong_number = request.form.get('strong_number')
        action = request.form.get('action')

        if action == 'delete':
            user_strongs_dict.pop(strong_number, None)
        elif action == 'update':
            translations = request.form.get('translations')#, '').split(',')
            color = request.form.get('color')
            #user_strongs_dict[strong_number] = {"translations": translations, "color": color}
            #if the null values don't work, remove these next few lines and put the split back above
            if translations:
                user_strongs_dict[strong_number]["translations"] = translations.split(',')
            if color is not None:
                if color == 'null':
                    user_strongs_dict[strong_number]["color"] = None
                else:
                    user_strongs_dict[strong_number]["color"] = color
        elif action == 'add':
            translations = request.form.get('translations', '').split(',')
            color = request.form.get('color')
            user_strongs_dict[strong_number] = {"translations": translations, "color": color}
        # Save the updated dictionary to the session
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


def generate_heatmap(strong_number):
    counts = {}
    max_count = 0
    for verse in kjv_data.get('verses', []):
        if f'{{{strong_number}}}' in verse['text']:
            book = verse['book_name']
            chapter = int(verse['chapter'])
            counts.setdefault(book, {})
            counts[book][chapter] = counts[book].get(chapter, 0) + 1
            if counts[book][chapter] > max_count:
                max_count = counts[book][chapter]

    heatmap = {}
    for book in book_order:
        max_chapter = book_chapter_count.get(book, 0)
        row = []
        chapters = counts.get(book, {})
        for ch in range(1, max_chapter + 1):
            cnt = chapters.get(ch, 0)
            if max_count:
                alpha = cnt / max_count
            else:
                alpha = 0
            r = 255
            g = int(255 * (1 - alpha))
            b = int(255 * (1 - alpha))
            color = f'#{r:02x}{g:02x}{b:02x}'
            row.append({'count': cnt, 'color': color})
        heatmap[book] = row

    return heatmap


@app.route('/heatmap')
def heatmap():
    strong = request.args.get('strong', '').strip()
    data = None
    if strong:
        data = generate_heatmap(strong)
    ordered_books = [b for b, _ in sorted(book_order.items(), key=lambda x: x[1])]
    return render_template('heatmap.html', strong=strong, data=data, ordered_books=ordered_books)
