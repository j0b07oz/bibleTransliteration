# Description: This script is used to replace words with their respective transliterations.
import re
import html
import colorsys
import hashlib
import unicodedata
from collections import Counter

STRONGS_REGEX = re.compile(r'{([HG]\d+)}')
HEX_COLOR_REGEX = re.compile(r'#[0-9a-fA-F]{6}')

# --- Single-pass tokenizer grammar -----------------------------------------
# A token is an optional word (letters/digits/apostrophes) followed by a
# contiguous run of markers. The run may mix plain Strong's markers {H7225},
# grammar codes {(H8804)}, and the malformed {H8804)} shape that appears in
# the source data. The whole run is consumed in one match; which marker (if
# any) renders is decided by parsing the run:
#   - the token renders only when the run STARTS with a plain {H####}/{G####}
#     marker and the word contains at least one word character — markers glued
#     after other markers (e.g. the untranslated particle in
#     "created{H1254}{(H8804)}{H853}") and grammar-code-first runs (e.g.
#     "hosts{(H8675)}{H6635}") never render, matching the original engine.
TOKEN_RUN_REGEX = re.compile(r"([\w']*)((?:\{\(?[HG]\d+\)?\})+)")
PRIMARY_MARKER_REGEX = re.compile(r'^\{([HG]\d+)\}')

# Names with a meaning gloss get an inline "that is, ..." note marker, but
# only for names rare enough that a reader plausibly forgot them — very
# common names (LORD, Israel, David, ...) would turn every verse into a
# footnote field. The meaning still reaches the word popup for all names.
NAME_MARK_MAX_COUNT = 500


def is_valid_hex_color(color) -> bool:
    """Return True only for strict #RRGGBB hex color strings.

    Used to guard color styling: any other value (a named color, a short
    hex, or an injection attempt) is treated as "no color" rather than
    interpolated into a style attribute or fed to is_light_color().
    """
    return isinstance(color, str) and bool(HEX_COLOR_REGEX.fullmatch(color))


def extract_strongs_numbers(text: str):
    return STRONGS_REGEX.findall(text or '')


def count_strongs_in_verses(verses, allowed=None):
    allowed_set = set(allowed) if allowed else None
    counts = Counter()
    for verse in verses or []:
        matches = extract_strongs_numbers(verse.get('text', ''))
        if allowed_set is not None:
            matches = [m for m in matches if m in allowed_set]
        counts.update(matches)
    return counts


def _unit_bounds(unit: dict):
    start = unit.get('range_start', {})
    end = unit.get('range_end', {})
    start_ch = int(unit.get('start_chapter') or start.get('chapter') or 0)
    end_ch = int(unit.get('end_chapter') or end.get('chapter') or 0)
    start_v = int(unit.get('start_verse_absolute') or start.get('verse') or 1)
    end_v = int(unit.get('end_verse_absolute') or end.get('verse') or 0)
    return start_ch, start_v, end_ch, end_v


def _verses_for_unit(verses_by_book, book: str, unit: dict):
    book_verses = verses_by_book.get(book, [])
    start_ch, start_v, end_ch, end_v = _unit_bounds(unit)
    if not start_ch or not end_ch:
        return []

    selected = []
    for verse in book_verses:
        ch = int(verse.get('chapter', 0))
        vs = int(verse.get('verse', 0))
        if ch < start_ch or ch > end_ch:
            continue
        if ch == start_ch and vs < start_v:
            continue
        if ch == end_ch and end_v and vs > end_v:
            continue
        selected.append(verse)
    return selected


def _rule_global_rare(ctx):
    return ctx['global_count'] <= 10


def _rule_unit_cluster(ctx):
    return ctx['global_count'] <= 50 and ctx['unit_peak'] >= 3


# Add new callables here to extend uncommon-word detection logic. Each rule
# receives a context dict with Strong's number, global_count, unit_peak, and lemma.
UNCOMMON_RULES = [
    ('global', _rule_global_rare),
    ('unit', _rule_unit_cluster),
]


def classify_uncommon(context: dict) -> dict:
    """Return rule match and counts for uncommon highlighting."""
    for name, fn in UNCOMMON_RULES:
        if fn(context):
            return {
                'is_uncommon': True,
                'rule': name,
                'global_count': context.get('global_count', 0),
                'unit_peak': context.get('unit_peak', 0),
            }
    return {
        'is_uncommon': False,
        'rule': None,
        'global_count': context.get('global_count', 0),
        'unit_peak': context.get('unit_peak', 0),
    }

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


def generate_color_from_strongs(strongs_number):
    """Generate a consistent color for a given Strong's number using hash-based approach."""
    base_color, _ = generate_repeat_colors(strongs_number)
    return base_color


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
    book, chapter, strongs_dict, bible_data, max_repeated_highlights=10, active_units=None
):
    # bible_data is a BibleData instance (app/data): its indexes are built once
    # at startup instead of rebuilt per request.
    replacement_mapping = {}
    strongs_lookup = bible_data.strongs_by_number

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

    def strip_diacritics(text: str) -> str:
        normalized = unicodedata.normalize('NFKD', text or '')
        return ''.join(ch for ch in normalized if not unicodedata.combining(ch))

    def consonant_key(text: str) -> str:
        letters_only = ''.join(ch for ch in strip_diacritics(text) if ch.isalpha())
        return re.sub(r'[AEIOUaeiou]', '', letters_only).upper()

    def derive_root(entry: dict, fallback_xlit: str = '') -> str:
        if not isinstance(entry, dict):
            entry = {}
        root = consonant_key(entry.get('lemma', '') or '')
        if not root:
            root = consonant_key(fallback_xlit or entry.get('xlit', ''))
        return root[:6]

    def safe_attr(val) -> str:
        if val is None:
            return ''
        return html.escape(str(val), quote=True)

    chapter_int = int(chapter)
    chapter_data = [{
        'text': verse['text'],
        'strongs': extract_strongs_numbers(verse['text']),
        'verse': str(verse['verse'])
    }
    for verse in bible_data.verses_by_book.get(book, [])
    if int(verse['chapter']) == chapter_int]

    for strongs_number in strongs_dict:
        strong_entry = strongs_lookup.get(strongs_number, {})
        xlit_value = strong_entry.get('xlit')
        # Adding the xlit value and color to the replacement_mapping dictionary
        if xlit_value:
            replacement_mapping[strongs_number] = {
                'xlit': xlit_value,
                'color': strongs_dict[strongs_number].get("color"),
                'lemma': strong_entry.get('lemma') or '',
                'pronounce': strong_entry.get('pronounce') or '',
                'description': strong_entry.get('description') or '',
                'root': derive_root(strong_entry, xlit_value),
            }

    strongs_counter = Counter(
        sn
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

    chapter_strongs_set = {
        sn
        for verse in chapter_data
        for sn in verse['strongs']
    }
    global_strongs_counts = bible_data.global_strongs_counts
    unit_max_counts = {}
    if active_units and chapter_strongs_set:
        for unit in active_units:
            unit_verses = _verses_for_unit(bible_data.verses_by_book, book, unit)
            if not unit_verses:
                continue
            counts = count_strongs_in_verses(unit_verses, allowed=chapter_strongs_set)
            for num, cnt in counts.items():
                if cnt > unit_max_counts.get(num, 0):
                    unit_max_counts[num] = cnt

    uncommon_lookup = {}
    for num in chapter_strongs_set:
        strong_meta = strongs_lookup.get(num, {}) or {}
        context = {
            'strongs': num,
            'global_count': global_strongs_counts.get(num, 0),
            'unit_peak': unit_max_counts.get(num, 0),
            'lemma': strong_meta.get('lemma', ''),
        }
        uncommon_lookup[num] = classify_uncommon(context)

    def should_skip_english_highlight(display_text, has_transliteration):
        if has_transliteration:
            return False

        normalized = re.sub(r"[^A-Za-z']", "", display_text).lower()
        return (
            len(normalized) < min_english_highlight_length
            or normalized in english_stopwords
        )

    def build_span(strongs_number, display_text, original_text, base_color, has_transliteration, metadata=None, uncommon_meta=None, alt_strongs=None):
        is_uncommon = bool(has_transliteration and uncommon_meta and uncommon_meta.get('is_uncommon'))
        tag_name = "button" if is_uncommon else "span"
        classes = ["strongs-token"]
        data_original_attr = (
            f' data-original="{html.escape(original_text)}"' if has_transliteration else ""
        )

        if has_transliteration:
            classes.append("highlighted-word")
            classes.append("transliterated")
        uncommon_label = None
        if is_uncommon:
            classes.append("uncommon-word")

        data_attrs = [f'data-strongs="{safe_attr(strongs_number)}"']
        if alt_strongs and isinstance(alt_strongs, str) and alt_strongs.strip():
            data_attrs.append(f'data-alt-strongs="{safe_attr(alt_strongs)}"')
        if is_uncommon:
            data_attrs.append('data-uncommon="true"')
            counts_suffix = ""
            if uncommon_meta:
                if uncommon_meta.get('rule') == 'global':
                    counts_suffix = f" · {uncommon_meta.get('global_count', 0)}x"
                elif uncommon_meta.get('rule') == 'unit':
                    counts_suffix = f" · {uncommon_meta.get('global_count', 0)}x · {uncommon_meta.get('unit_peak', 0)}x"
            uncommon_label = f"Strong's {strongs_number} · {(metadata or {}).get('xlit') or original_text or display_text}{counts_suffix}"
            data_attrs.append(f'data-uncommon-info="{safe_attr(uncommon_label)}"')

        if metadata:
            if metadata.get('xlit'):
                data_attrs.append(f'data-xliteral="{safe_attr(metadata.get("xlit"))}"')
            if metadata.get('lemma'):
                data_attrs.append(f'data-lemma="{safe_attr(metadata.get("lemma"))}"')
            if metadata.get('pronounce'):
                data_attrs.append(f'data-pronounce="{safe_attr(metadata.get("pronounce"))}"')
            if metadata.get('root'):
                data_attrs.append(f'data-rootkey="{safe_attr(metadata.get("root"))}"')
            if metadata.get('description'):
                short_desc = metadata.get('description')[:180]
                data_attrs.append(f'data-description="{safe_attr(short_desc)}"')
            if metadata.get('gloss'):
                data_attrs.append(f'data-gloss="{safe_attr(metadata.get("gloss"))}"')
            if metadata.get('name_meaning'):
                data_attrs.append(f'data-name-meaning="{safe_attr(metadata.get("name_meaning"))}"')

        data_attr_str = f" {' '.join(data_attrs)}" if data_attrs else ""
        style_parts = []

        # Only apply a user/entry color when it is a strict #RRGGBB hex value.
        # Anything else (named colors, malformed hex, injection attempts) is
        # ignored so it can neither crash is_light_color() nor break out of the
        # style attribute.
        if base_color and has_transliteration and is_valid_hex_color(base_color):
            text_color = '#ffffff' if not is_light_color(base_color[1:]) else '#000000'
            style_parts.append(f"background-color: {base_color}; color: {text_color};")

        if has_transliteration and strongs_number in repeated_colors:
            classes.append("repeated")
            repeat_color, shadow_color = repeated_colors[strongs_number]
            style_parts.append(
                f"color: #1f0f0b; background-color: {shadow_color}; border: 1px solid {repeat_color};",
            )

        # Escape the assembled style value as defense in depth even though the
        # inputs above are validated hex.
        style_attr = f' style="{safe_attr(" ".join(style_parts))}"' if style_parts else ''
        type_attr = ' type="button"' if tag_name == "button" else ""
        return f'<{tag_name} class="{" ".join(classes)}"{data_original_attr}{data_attr_str}{style_attr}{type_attr}>{display_text}</{tag_name}>'
    #----------------------------------------------------------------------
    # Single-pass rendering: tokenize each verse once into
    # [gap text][word + marker run] segments and render each token in place.
    # Inserted HTML is never rescanned, so replacements cannot corrupt or
    # re-match earlier output.

    name_glosses = getattr(bible_data, 'name_glosses', None) or {}

    def find_phrase(text, marker_start, candidates):
        """Return the longest dictionary translation ending exactly at the
        marker, in its actual casing, or None.

        Mirrors the original engine's `\\b<translation>{sn}` search
        (case-insensitive, word boundary before the phrase), evaluated
        against this token's own preceding text.
        """
        before = text[:marker_start]
        before_l = before.lower()
        for translation in candidates:
            t = translation.lower()
            if not t or not before_l.endswith(t):
                continue
            start = len(before) - len(t)
            if start > 0 and re.match(r'\w', before[start - 1]):
                continue  # phrase would begin mid-word
            return before[start:]
        return None

    result = []
    # Print-Bible convention: the inline dagger marks only a name's FIRST
    # occurrence in the chapter; later instances stay clean (the meaning is
    # still one click away in the word popup on every instance).
    daggered_names = set()
    for verse in chapter_data:
        text = verse['text']
        out = []
        last_end = 0
        for token in TOKEN_RUN_REGEX.finditer(text):
            gap = text[last_end:token.start()]
            word, run = token.group(1), token.group(2)
            last_end = token.end()

            primary = PRIMARY_MARKER_REGEX.match(run)
            if not primary or not re.search(r'\w', word):
                # Glued particles ({H853} after another marker), grammar-code
                # -first runs, and wordless markers never rendered in the
                # original engine: keep the text, drop the markers.
                out.append(gap)
                out.append(word)
                continue

            strongs_number = primary.group(1)
            strongs_entry = strongs_dict.get(strongs_number, {})
            strongs_meta = strongs_lookup.get(strongs_number, {}) or {}
            translations = strongs_entry.get("translations", [word])
            sorted_translations = sorted(translations, key=lambda x: len(x.split()), reverse=True)
            xlit_info = replacement_mapping.get(strongs_number)

            # Alternative Strong's number: a {(H5625)}/{(G5625)} variant
            # marker inside this token's run, followed by the alternate
            # number. Same greedy pattern as before, anchored to the run.
            alt_strongs_number = None
            if '5625)' in run:
                alt_pattern = re.match(
                    r'\{' + re.escape(strongs_number) + r'\}(?:\{[^}]+\})*\{\([HG]5625\)\}\{([HG]\d+)\}',
                    run,
                )
                if alt_pattern:
                    alt_strongs_number = alt_pattern.group(1)

            phrase = find_phrase(text, token.start(2), sorted_translations)
            display_source = phrase if phrase is not None else word
            display_value = html.escape(xlit_info['xlit']) if xlit_info else html.escape(display_source)
            color = xlit_info['color'] if xlit_info else strongs_entry.get("color")
            meta = {
                'xlit': (xlit_info.get('xlit') if xlit_info else '') or strongs_meta.get('xlit'),
                'lemma': (xlit_info.get('lemma') if xlit_info else '') or strongs_meta.get('lemma'),
                'pronounce': (xlit_info.get('pronounce') if xlit_info else '') or strongs_meta.get('pronounce'),
                'description': (xlit_info.get('description') if xlit_info else '') or strongs_meta.get('description'),
                'root': (xlit_info.get('root') if xlit_info else '') or derive_root(strongs_meta, display_value),
                'gloss': display_source,
            }

            # Proper-name meaning: available to the popup for every
            # capitalized name the lexicon glosses.
            name_gloss = None
            if name_glosses and len(word) > 1 and word[:1].isupper():
                name_gloss = name_glosses.get(strongs_number)
                if name_gloss:
                    meta['name_meaning'] = name_gloss

            # A multi-word phrase consumed the tail of the preceding gap.
            if phrase is not None and len(phrase) > len(word):
                extra = len(phrase) - len(word)
                gap = gap[:-extra]
            out.append(gap)

            if should_skip_english_highlight(display_value, bool(xlit_info)) and strongs_number in repeated_strongs:
                # Short/stopword repeated candidates render as plain text.
                out.append(display_source)
                continue

            out.append(build_span(
                strongs_number,
                display_value,
                display_source,
                color,
                bool(xlit_info),
                meta,
                uncommon_lookup.get(strongs_number),
                alt_strongs_number,
            ))

            # Inline "that is, ..." footnote marker: first occurrence in the
            # chapter, for names uncommon enough that the reminder helps.
            if (
                name_gloss
                and strongs_number not in daggered_names
                and global_strongs_counts.get(strongs_number, 0) <= NAME_MARK_MAX_COUNT
            ):
                daggered_names.add(strongs_number)
                note = html.escape(name_gloss, quote=False)
                out.append(
                    '<sup class="name-mark" role="button" tabindex="0"'
                    ' title="Uncover name meaning">&dagger;</sup>'
                    f'<span class="name-note" hidden>[that is, <em>{note}</em>]</span>'
                )

        out.append(text[last_end:])
        rendered = ''.join(out)
        # Safety net: the tokenizer consumes every marker shape, so these are
        # no-ops on current data, but keep the old cleanup as a guarantee.
        rendered = re.sub(r'\{[HG]\d+\}', '', rendered)
        rendered = re.sub(r'\{(\([HG]\d+\))\}', '', rendered)
        rendered = re.sub(r'\{[HG]\d+\)\}', '', rendered)
        result.append(f"{verse['verse']} {rendered}")
    return '\n'.join(result)
