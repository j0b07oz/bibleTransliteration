"""Central data layer for the Bible transliteration app.

All bulk data (the KJV text, the Strong's lexicon, the default word list, the
book outlines, and the Hebrew<->Greek cross-references) is loaded once at
startup by ``load_bible_data`` and exposed as a single immutable-ish
``BibleData`` instance. Routes read from that instance (stored on
``app.extensions['bible_data']``) instead of rebuilding per-book indexes on
every request, and tests can build an instance directly from in-memory sample
data via ``build_bible_data``.

The JSON data files live alongside this module in ``app/data/`` (a non-routable
directory) rather than under ``app/static/`` so they are never served to the
browser — the frontend only ever talks to ``/edit_dict`` and ``/api/crossref``.
"""
import json
import os
import re
from collections import Counter
from dataclasses import dataclass

from ..transliteration import count_strongs_in_verses

# Directory that holds the bundled JSON data files (this package's own folder).
DATA_DIR = os.path.dirname(os.path.abspath(__file__))

# An English word immediately followed by its Strong's marker, e.g.
# "beginning{H7225}". Grammar codes like {(H8804)} have no preceding word and
# are skipped, as are bare particles like ...{H1254}{H853} where {H853} is
# preceded by '}' rather than a word.
WORD_STRONGS_REGEX = re.compile(r"([A-Za-z][A-Za-z']*)\{([HG]\d+)\}")

# --- Proper-name meaning extraction -----------------------------------------
# Strong's descriptions for proper nouns follow a stable shape:
#   <derivation>; <meaning>; <Name>, <identification>; <KJV renderings>.
# e.g. H883: "from X and Y; well of a living (One) my Seer;
#             Beer-Lachai-Roi, a place in the Desert; Beer-lahai-roi."
# We only accept an entry as a name when a segment BOTH starts with a
# capitalized name (or "as a name, ...") AND identifies what it names — this
# keeps common nouns whose glosses merely mention "a place" etc. out.
NAME_ID_KEYWORDS = re.compile(
    r'\b(?:place|city|town|region|mountain|mount|hill|river|brook|stream|'
    r'valley|plain|desert|wilderness|island|district|province|land|country|'
    r'spring|well|capital|Israelite|Levite|Benjamite|Ephrathite|Egyptian|'
    r'Canaanite|Philistine|Syrian|Moabite|Ammonite|Edomite|Midianite|'
    r'Amalekite|Assyrian|Babylonian|Persian|Chaldean|Amorite|Hittite|Hivite|'
    r'Jebusite|patriarch|prophet|prophetess|priest|king|queen|prince|'
    r'princess|chief|duke|lawgiver|judge|apostle|disciple|son of|sons of|'
    r'daughter of|father of|mother of|wife of|husband of|brother of|'
    r'grandson of|servant of|name of|national name|people|tribe|nation|'
    r'deity|goddess|idol|angel|giant|eunuch|officer|captain|scribe|harlot|'
    r'concubine|ancestor|descendant|spy|warrior|shepherd|herdsman|musician|'
    r'singer|porter)\b',
    re.IGNORECASE,
)

# Segments that describe where the word comes from rather than what it means.
DERIVATION_PREFIXES = (
    'from', 'of ', 'contracted', 'the same', 'a form', 'for ', 'probably',
    'perhaps', 'apparently', 'patronymic', 'patrial', 'denominative',
    'feminine', 'masculine', 'plural', 'dual', 'compare', 'or ', 'rarely',
    'abbreviated', 'derived', 'prolonged', 'prolongation', 'irregular',
    'originally', 'intensive', 'a primitive', 'shortened', 'also ', 'used ',
    'including', 'in the sense', 'akin', 'with ', 'see ', 'i.e.', 'by ',
    'participle', 'active participle', 'passive participle', 'infinitive',
    'a variation', 'an orthographical', 'a collateral', 'second form',
    'transmuted', 'a doubtful', 'lemma', 'corrected', 'an unused', 'formed',
    'reduplicated', 'a contraction', 'contraction', 'a shorter form',
    'a rare form', 'a prolonged form', 'full form',
)


def extract_name_gloss(description):
    """Pull the meaning of a proper name out of a Strong's description.

    Returns e.g. "well of a living (One) my Seer" for H883 (Beer-lahai-roi),
    or None when the entry is not confidently a proper name with a stated
    meaning. Precision is favored over recall: a missing note is better than
    a wrong one.
    """
    if not description:
        return None
    segments = [s.strip() for s in description.split(';') if s.strip()]

    id_idx = None
    for i, seg in enumerate(segments):
        if i == 0:
            # The first segment is always derivation/headword info.
            continue
        lead_ok = seg[:1].isupper() or seg.lower().startswith('as a name')
        if lead_ok and NAME_ID_KEYWORDS.search(seg):
            id_idx = i
            break
    if not id_idx:
        return None

    meaning_parts = []
    for seg in segments[:id_idx]:
        low = seg.lower()
        # Test derivation prefixes both as-is and with a leading parenthetical
        # (e.g. "(Aramaic) of foreign origin ...") removed.
        unwrapped = re.sub(r'^\([^)]*\)[\s,]*', '', low)
        if low.startswith(DERIVATION_PREFIXES) or unwrapped.startswith(DERIVATION_PREFIXES):
            continue
        # Lexicon bookkeeping and reference segments, not meanings.
        if any(marker in low for marker in (
            'name of', 'of foreign', 'of uncertain', 'of doubtful',
            'corrected to', 'xlit ', 'as if from',
        )):
            continue
        if '{' in seg or '}' in seg:
            continue
        # Skip segments that are (mostly) Hebrew/Greek script.
        ascii_letters = len(re.findall(r'[a-zA-Z]', seg))
        if ascii_letters < max(3, len(seg) // 4):
            continue
        meaning_parts.append(seg)
    if not meaning_parts:
        return None

    gloss = '; '.join(meaning_parts).strip().rstrip('.').strip()
    if not 2 < len(gloss) <= 100:
        return None
    return gloss


def _build_name_glosses(strongs_by_number):
    glosses = {}
    for sn, entry in strongs_by_number.items():
        gloss = extract_name_gloss(entry.get('description') or '')
        if gloss:
            glosses[sn] = gloss
    return glosses


@dataclass
class BibleData:
    """Precomputed indexes over the KJV text and Strong's lexicon."""

    # number -> lexicon entry ({'number','xlit','lemma','pronounce','description'})
    strongs_by_number: dict
    # book_name -> list of raw verse dicts (shared, treated read-only by callers)
    verses_by_book: dict
    # Strong's number -> whole-Bible occurrence count
    global_strongs_counts: Counter
    # book_name -> canonical book order index (verse['book'])
    book_order: dict
    # book_name -> highest chapter number
    book_chapter_count: dict
    # book_name -> {chapter: highest verse number}
    chapter_verse_counts: dict
    # lowercased book_name -> canonical book_name (case-insensitive lookup)
    book_name_lookup: dict
    # lowercased English word -> Counter({Strong's number: occurrence count}),
    # built from the word{H####} pairs in the KJV text (reverse lookup)
    english_word_index: dict
    # Strong's number -> extracted proper-name meaning (e.g. H883 ->
    # "well of a living (One) my Seer"), for the name-uncovering feature
    name_glosses: dict
    # default (raw) Strong's -> [translations] word list
    default_strongs_dict: dict
    # book_name -> list of literary-unit outline dicts
    outline_data: dict
    # Hebrew Strong's -> {'primary','secondary',...} Greek cross-references
    hebrew_to_greek: dict
    # Greek Strong's -> {'primary','secondary',...} Hebrew cross-references
    greek_to_hebrew: dict


def _build_strongs_index(strongs_data):
    return {
        entry.get('number'): entry
        for entry in (strongs_data or [])
        if isinstance(entry, dict) and entry.get('number')
    }


def _build_verse_indexes(kjv_data):
    """Build the per-book verse list and the book/chapter/verse count maps.

    Mirrors the loops that previously lived inline in routes.py so behavior is
    unchanged: book order comes from the first verse of each book, chapter and
    verse counts are the running maxima.
    """
    verses_by_book = {}
    book_order = {}
    book_chapter_count = {}
    chapter_verse_counts = {}

    for verse in kjv_data.get('verses', []):
        name = verse.get('book_name')
        verses_by_book.setdefault(name, []).append(verse)

        if name not in book_order:
            book_order[name] = verse['book']
        chapter = int(verse['chapter'])
        if name not in book_chapter_count or chapter > book_chapter_count[name]:
            book_chapter_count[name] = chapter
        chapter_verse_counts.setdefault(name, {})
        chapter_verse_counts[name][chapter] = max(
            int(verse['verse']), chapter_verse_counts[name].get(chapter, 0)
        )

    book_name_lookup = {name.lower(): name for name in book_chapter_count.keys()}
    return verses_by_book, book_order, book_chapter_count, chapter_verse_counts, book_name_lookup


def _build_english_word_index(kjv_data):
    """Map each lowercased KJV word to the Strong's numbers it translates.

    Powers the "I know the word, not the number" reverse lookup: one pass over
    the text collecting word{H####} pairs, so e.g. index['mercy'] counts how
    often each Strong's number appears rendered as "mercy".
    """
    index = {}
    for verse in kjv_data.get('verses', []):
        for word, strong in WORD_STRONGS_REGEX.findall(verse.get('text', '')):
            index.setdefault(word.lower(), Counter())[strong] += 1
    return index


def build_bible_data(
    strongs_data,
    kjv_data,
    default_strongs_dict=None,
    outline_data=None,
    hebrew_to_greek=None,
    greek_to_hebrew=None,
) -> BibleData:
    """Assemble a BibleData from already-parsed structures.

    Used by load_bible_data (from files) and by tests (from in-memory fixtures).
    """
    verses_by_book, book_order, book_chapter_count, chapter_verse_counts, book_name_lookup = (
        _build_verse_indexes(kjv_data)
    )
    strongs_by_number = _build_strongs_index(strongs_data)
    return BibleData(
        strongs_by_number=strongs_by_number,
        verses_by_book=verses_by_book,
        global_strongs_counts=count_strongs_in_verses(kjv_data.get('verses', [])),
        book_order=book_order,
        book_chapter_count=book_chapter_count,
        chapter_verse_counts=chapter_verse_counts,
        book_name_lookup=book_name_lookup,
        english_word_index=_build_english_word_index(kjv_data),
        name_glosses=_build_name_glosses(strongs_by_number),
        default_strongs_dict=default_strongs_dict or {},
        outline_data=outline_data or {},
        hebrew_to_greek=hebrew_to_greek or {},
        greek_to_hebrew=greek_to_hebrew or {},
    )


def _load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_bible_data(data_dir=DATA_DIR, outlines_path=None, logger=None) -> BibleData:
    """Load every data file once and return the assembled BibleData.

    Args:
        data_dir: directory holding Strongs.json, kjv_strongs.json,
            strongs_dict.json, and hebrew_greek_crossref.json (defaults to this
            package's own directory).
        outlines_path: absolute path to the book-outline JSON at the repo root.
        logger: optional logger for a startup summary line.
    """
    default_strongs_dict = _load_json(os.path.join(data_dir, 'strongs_dict.json'))
    strongs_data = _load_json(os.path.join(data_dir, 'Strongs.json'))
    kjv_data = _load_json(os.path.join(data_dir, 'kjv_strongs.json'))

    outline_data = {}
    if outlines_path and os.path.exists(outlines_path):
        outline_data = _load_json(outlines_path)

    hebrew_to_greek = {}
    greek_to_hebrew = {}
    crossref_path = os.path.join(data_dir, 'hebrew_greek_crossref.json')
    if os.path.exists(crossref_path):
        crossref_data = _load_json(crossref_path)
        hebrew_to_greek = crossref_data.get('hebrew_to_greek', {})
        greek_to_hebrew = crossref_data.get('greek_to_hebrew', {})
        if logger:
            logger.info(
                f"Loaded {len(hebrew_to_greek)} Hebrew→Greek and "
                f"{len(greek_to_hebrew)} Greek→Hebrew cross-references"
            )
    elif logger:
        logger.warning(f"Cross-reference data not found at {crossref_path}")

    return build_bible_data(
        strongs_data,
        kjv_data,
        default_strongs_dict=default_strongs_dict,
        outline_data=outline_data,
        hebrew_to_greek=hebrew_to_greek,
        greek_to_hebrew=greek_to_hebrew,
    )
