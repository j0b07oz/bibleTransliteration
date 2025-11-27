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
    saturation = 0.35 + (digest[1] / 255) * 0.2
    lightness = 0.35 + (digest[2] / 255) * 0.15
    base_color = hls_to_hex(hue, lightness, saturation)
    accent_lightness = min(0.85, lightness + 0.22)
    accent_saturation = min(0.45, saturation + 0.1)
    accent_color = hls_to_hex(hue, accent_lightness, accent_saturation)
    return base_color, accent_color

def transliterate_chapter(
    book,
    chapter,
    strongs_dict_path,
    strongs_path,
    kjv_path,
    sound_annotations=None,
    max_repeated_highlights=10,
):
    replacement_mapping = {}

    stop_strongs = {
        # Common articles, conjunctions, and pronouns that add noise when highlighted
        "H1931", "H1933", "H3068", "H853", "H854", "H3588", "H834", "H4480",
        "H413", "H5921", "H5973", "H1571", "H518", "H3808", "H1961", "H1992",
        "G2532", "G1161", "G1510", "G3588", "G2532", "G3754", "G3777", "G1063",
        "G1223", "G2531", "G1722", "G1519", "G1909", "G3326", "G3756", "G1163",
    }
    english_stopwords = {
        "a", "an", "and", "as", "at", "but", "by", "for", "from", "he", "her",
        "his", "i", "in", "is", "it", "nor", "not", "of", "on", "or", "our",
        "she", "so", "that", "the", "their", "them", "then", "they", "this",
        "those", "to", "was", "we", "were", "when", "which", "who", "with",
        "you", "your",
    }
    min_english_highlight_length = 4
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

    active_annotations = (sound_annotations or {}).get(book, {}).get(str(chapter), {})

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
    repeated_candidates = [
        (num, count)
        for num, count in strongs_counter.items()
        if count >= min_repeat_count and num not in stop_strongs
    ]
    repeated_sorted = sorted(repeated_candidates, key=lambda item: (-item[1], item[0]))
    repeated_strongs = {
        num for num, _ in repeated_sorted[:max_repeated_highlights]
    }
    repeated_colors = {num: generate_repeat_colors(num) for num in repeated_strongs}

    def should_skip_english_highlight(display_text, has_transliteration):
        if has_transliteration:
            return False

        normalized = re.sub(r"[^A-Za-z']", "", display_text).lower()
        return (
            len(normalized) < min_english_highlight_length
            or normalized in english_stopwords
        )

    def build_span(
        strongs_number,
        display_text,
        original_text,
        base_color,
        has_transliteration,
        token_index,
        sound_map,
    ):
        classes = ["highlighted-word"]
        data_original_attr = (
            f' data-original="{html.escape(original_text)}"' if has_transliteration else ""
        )
        data_sound_attr = ""

        if sound_detail:
            classes.append("sound-annotated")
            try:
                encoded = html.escape(json.dumps(sound_detail))
                data_sound_attr = f' data-sound-detail="{encoded}"'
            except (TypeError, ValueError):
                data_sound_attr = ""

        sound_attrs = []
        if token_index is not None:
            sound_attrs.append(f' data-sound-index="{token_index}"')
        if sound_map:
            roots = sound_map.get(token_index, {}).get('roots', [])
            initials = sound_map.get(token_index, {}).get('initials', [])
            if roots:
                sound_attrs.append(
                    f' data-sound-roots="{html.escape(",".join(roots))}"'
                )
            if initials:
                sound_attrs.append(
                    f' data-sound-initials="{html.escape(",".join(initials))}"'
                )
            if roots or initials:
                sound_attrs.append(' data-sound-annotated="true"')

        if has_transliteration:
            classes.append("transliterated")

        style_parts = []

        if base_color:
            text_color = '#ffffff' if not is_light_color(base_color[1:]) else '#000000'
            style_parts.append(f"background-color: {base_color}; color: {text_color};")

        if strongs_number in repeated_colors:
            classes.append("repeated")
            repeat_color, shadow_color = repeated_colors[strongs_number]
            style_parts.append(
                f"color: #1f0f0b; background-color: {shadow_color}; border: 1px solid {repeat_color};"
            )

        style_attr = f" style=\"{' '.join(style_parts)}\"" if style_parts else ""
        return (
            f'<span class="{" ".join(classes)}"{data_original_attr}{style_attr}'
            f'{"".join(sound_attrs)}>{display_text}</span>'
        )

    #----------------------------------------------------------------------
    result = []
    for verse in chapter_data:
        verse_annotations = {}
        if sound_annotations:
            verse_annotations = sound_annotations.get(str(verse['verse']), {})

        sound_map = {}
        for root, positions in verse_annotations.get("local_roots", {}).items():
            for idx in positions:
                sound_map.setdefault(idx, {'roots': set(), 'initials': set()})['roots'].add(root)
        for initial, positions in verse_annotations.get("local_initials", {}).items():
            for idx in positions:
                sound_map.setdefault(idx, {'roots': set(), 'initials': set()})['initials'].add(initial)

        sound_map = {
            idx: {
                'roots': sorted(list(info.get('roots', []))),
                'initials': sorted(list(info.get('initials', []))),
            }
            for idx, info in sound_map.items()
        }

        for token_index, strongs_number_braced in enumerate(verse['strongs']):
            strongs_number = strongs_number_braced.strip('{}')
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
                xlit_info = replacement_mapping.get(strongs_number)

                replaced = False
                for translation in sorted_translations:
                    translation = translation.lower()
                    num_words_translation = len(translation.split())

                    # Look for the full phrase
                    phrase_match = re.search(r'\b' + re.escape(translation) + r'\s*\{' + re.escape(strongs_number) + r'\}', verse['text'], re.IGNORECASE)

                    if phrase_match:
                        matched_text = phrase_match.group(0)
                        display_value = html.escape(xlit_info['xlit']) if xlit_info else html.escape(matched_text.split("{")[0].strip())
                        color = xlit_info['color'] if xlit_info else None
                        if should_skip_english_highlight(display_value, bool(xlit_info)) and strongs_number in repeated_strongs:
                            verse['text'] = verse['text'].replace(matched_text, matched_text.split("{")[0].strip())
                            replaced = True
                            break

                        replacement = build_span(
                            strongs_number,
                            display_value,
                            matched_text.split("{")[0].strip(),
                            color,
                            bool(xlit_info),
                            token_index,
                            sound_map,
                        )
                        verse['text'] = verse['text'].replace(matched_text, replacement)
                        replaced = True
                        break

                # If no phrase match found, fall back to single word replacement
                if not replaced:
                    display_value = html.escape(xlit_info['xlit']) if xlit_info else html.escape(word)
                    color = xlit_info['color'] if xlit_info else None
                    if should_skip_english_highlight(display_value, bool(xlit_info)) and strongs_number in repeated_strongs:
                        verse['text'] = verse['text'].replace(word + f"{{{strongs_number}}}", word)
                        token_index += 1
                        continue

                    replacement = build_span(
                        strongs_number,
                        display_value,
                        word,
                        color,
                        bool(xlit_info),
                        token_index,
                        sound_map,
                    )
                    verse['text'] = verse['text'].replace(word + f"{{{strongs_number}}}", replacement)
            token_index += 1
        verse['text'] = re.sub(r'\{[HG]\d+\}', '', verse['text'])
        verse['text'] = re.sub(r'\{(\([HG]\d+\))\}', '', verse['text'])
        verse['text'] = re.sub(r'\{[HG]\d+\)\}', '', verse['text'])
        result.append(f"{verse['verse']} {verse['text']}")
    return '\n'.join(result)
