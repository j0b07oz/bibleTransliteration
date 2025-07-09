import os
from flask import render_template, request, jsonify, session, send_file, url_for, redirect
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

with open(strongs_dict_path, 'r', encoding='utf-8') as f:
    default_strongs_dict = json.load(f)
with open(strongs_path, 'r', encoding='utf-8') as f:
    strongs_data = json.load(f)
with open(kjv_path, 'r', encoding='utf-8') as f:
    kjv_data = json.load(f)

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
    if request.method == 'POST' or (book and chapter):
        if book and chapter:
            user_strongs_dict = get_user_strongs_dict()
            result = transliterate_chapter(book, chapter, user_strongs_dict, strongs_data, kjv_data)

    return render_template('home.html', result=result, book=book, chapter=chapter)

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

    return render_template('home.html', result=result, book=book, chapter=chapter)

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