import hashlib
import os
from flask import render_template, request, jsonify, session, send_file
from app import app
from .transliteration import transliterate_chapter
import json
import uuid
import tempfile

def get_session_id():
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())
    return session['user_id']

def get_user_strongs_dict():
    default_dict = {k: {"translations": v, "color": None} for k, v in default_strongs_dict.items()}
    return session.get('user_strongs_dict', default_dict)

current_file_path = os.path.abspath(__file__)
current_dir = os.path.dirname(current_file_path)

STATIC_DATA_DIR = os.path.join(current_dir, 'static')

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
    if request.method == 'POST' or (book and chapter):
        if book and chapter:
            user_strongs_dict = get_user_strongs_dict()
            result = transliterate_chapter(book, chapter, user_strongs_dict, strongs_data, kjv_data)
            active_unit = get_active_unit(book, chapter)

    return render_template('home.html', result=result, book=book, chapter=chapter, active_unit=active_unit)

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
    result = transliterate_chapter(book, chapter, user_strongs_dict, strongs_data, kjv_data)
    active_unit = get_active_unit(book, chapter)

    return render_template('home.html', result=result, book=book, chapter=chapter, active_unit=active_unit)

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
        session['user_strongs_dict'] = user_strongs_dict
        return jsonify({"success": True})
    
    sorted_dict = dict(sorted(user_strongs_dict.items(), key=lambda x: int(x[0][1:])))

    # For GET requests, render the edit page
    return render_template('edit_dict.html', strongs_dict=sorted_dict)

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
