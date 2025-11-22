# Description: This script is used to replace words with their respective transliterations.
import os
import re
import json
import jmespath
import html
import colorsys
import hashlib
from collections import Counter

def is_light_color(hex_color):
    # Convert hex to RGB
    rgb = tuple(int(hex_color[i:i+2], 16) / 255 for i in (1, 3, 5))
    # Convert RGB to HSL
    h, l, s = colorsys.rgb_to_hls(*rgb)
    # Check if the color is light (you can adjust the threshold)
    return l > 0.65


def hls_to_hex(h, l, s):
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return '#{:02x}{:02x}{:02x}'.format(int(r * 255), int(g * 255), int(b * 255))


def generate_repeat_colors(strongs_number):
    digest = hashlib.sha256(strongs_number.encode('utf-8')).digest()
    hue = digest[0] / 255
    saturation = 0.55 + (digest[1] / 255) * 0.25
    lightness = 0.45 + (digest[2] / 255) * 0.15
    base_color = hls_to_hex(hue, lightness, saturation)
    shadow_color = hls_to_hex(hue, max(0, lightness - 0.18), min(0.95, saturation + 0.1))
    return base_color, shadow_color

def transliterate_chapter(book,chapter, strongs_dict_path, strongs_path, kjv_path):
    replacement_mapping = {}

    stop_strongs = {
        # Common articles, conjunctions, and pronouns that add noise when highlighted
        "H1931", "H1933", "H3068", "H853", "H854", "H3588", "H834",
        "G2532", "G1161", "G1510", "G3588", "G2532", "G3754", "G3777",
        "G1063", "G1223",
    }
    min_repeat_count = 3

    pattern = r'{[HG]\d+}'
    alt_pattern = r'{[HG]\d+}{'

    def extract_strongs(text):
        return re.findall(pattern, text)

    chapter_data = [{
        'text': verse['text'],
        'strongs': extract_strongs(verse['text']),
        'verse': str(verse['verse'])
    }
    for verse in kjv_path['verses']
    if verse['book_name'] == book and verse['chapter'] == int(chapter)] #and verse['verse'] == int(verse_num)]

    for strongs_number in strongs_dict_path:
        search_string = f"[?number == '{strongs_number}'].xlit"
        xlit_value = jmespath.search(search_string, strongs_path)
        # Adding the xlit value and color to the replacement_mapping dictionary
        if xlit_value:
            replacement_mapping[strongs_number] = {
                'xlit': xlit_value[0],
                'color': strongs_dict_path[strongs_number].get("color")
            }

    strongs_counter = Counter(
        sn.strip('{}')
        for verse in chapter_data
        for sn in verse['strongs']
    )
    repeated_strongs = {
        num for num, count in strongs_counter.items()
        if count >= min_repeat_count and num not in stop_strongs
    }
    repeated_colors = {num: generate_repeat_colors(num) for num in repeated_strongs}

    def build_span(strongs_number, display_text, original_text, base_color):
        classes = ["transliterated"]
        style_parts = []

        if base_color:
            text_color = '#ffffff' if not is_light_color(base_color[1:]) else '#000000'
            style_parts.append(f"background-color: {base_color}; color: {text_color};")

        if strongs_number in repeated_colors:
            classes.append("repeated")
            repeat_color, shadow_color = repeated_colors[strongs_number]
            style_parts.append(f"color: {repeat_color}; text-shadow: 0 0 6px {shadow_color};")

        style_attr = f" style=\"{' '.join(style_parts)}\"" if style_parts else ""
        return f'<span class="{" ".join(classes)}" data-original="{html.escape(original_text)}"{style_attr}>{display_text}</span>'

    #----------------------------------------------------------------------
    result = []
    for verse in chapter_data:
        for strongs_number_braced in verse['strongs']:
            strongs_number = strongs_number_braced.strip('{}')
            if strongs_number in replacement_mapping.keys():
                match = re.search(r'\b([\w\']*)\{' + re.escape(strongs_number) + r'\}', verse['text'])
                alt_match = re.search(r'{' + re.escape(strongs_number) + r'\}\'{[HG]\d+}', verse['text'])
                if alt_match:
                    strongs_group = alt_match.group(1)
                    verse['text'] = verse['text'].replace(f"{{{strongs_number}}}", "")
                    continue
                if match:
                    word = match.group(1)
                    strongs_entry = strongs_dict_path.get(strongs_number, {})
                    translations = strongs_entry.get("translations", [word])
                    sorted_translations = sorted(translations, key=lambda x: len(x.split()), reverse=True)

                    replaced = False
                    for translation in sorted_translations:
                        translation = translation.lower()
                        num_words_translation = len(translation.split())
                        
                        # Look for the full phrase
                        phrase_match = re.search(r'\b' + re.escape(translation) + r'\s*\{' + re.escape(strongs_number) + r'\}', verse['text'], re.IGNORECASE)
                        
                        if phrase_match:
                            matched_text = phrase_match.group(0)
                            xlit = html.escape(replacement_mapping[strongs_number]['xlit'])
                            color = replacement_mapping[strongs_number]['color']
                            replacement = build_span(
                                strongs_number,
                                xlit,
                                matched_text.split("{")[0].strip(),
                                color,
                            )
                            verse['text'] = verse['text'].replace(matched_text, replacement)
                            replaced = True
                            break
                    
                    # If no phrase match found, fall back to single word replacement
                    if not replaced:
                        xlit = html.escape(replacement_mapping[strongs_number]['xlit'])
                        color = replacement_mapping[strongs_number]['color']
                        replacement = build_span(strongs_number, xlit, word, color)
                        verse['text'] = verse['text'].replace(word + f"{{{strongs_number}}}", replacement)
        verse['text'] = re.sub(r'\{[HG]\d+\}', '', verse['text'])
        verse['text'] = re.sub(r'\{(\([HG]\d+\))\}', '', verse['text'])
        verse['text'] = re.sub(r'\{[HG]\d+\)\}', '', verse['text'])
        result.append(f"{verse['verse']} {verse['text']}")
    return '\n'.join(result)
