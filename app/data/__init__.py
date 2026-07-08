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
import unicodedata
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
    r'spring|well|pool|garden|tower|gate|fountain|capital|'
    r'patriarch|patriach|antediluvian|prophet|prophetess|priest|king|queen|'
    r'prince|princess|chief|chieftain|duke|lawgiver|judge|apostle|disciple|'
    r'satrap|governor|ruler|treasurer|cupbearer|'
    r'son of|sons of|daughter of|daughters of|son a|'
    r'father of|mother of|wife of|husband of|brother of|twin-brother|'
    r'grandson of|servant of|member of|one of the|epithet|surname|'
    r'first man|name of|national name|people|tribe|nation|inhabitants|'
    r'native|citizen|deity|goddess|idol|angel|giant|eunuch|officer|captain|'
    r'scribe|harlot|concubine|ancestor|descendant|spy|warrior|shepherd|'
    r'herdsman|musician|singer|porter|'
    r"'s (?:wife|husband|son|daughter|father|mother|brother|"
    r'sister|servant|handmaid|steward|uncle|nephew|firstborn))\b',
    re.IGNORECASE,
)

# Gentilic / ethnic adjectives ("an Idumaean", "a Macedonian", "a Christian",
# "the Caphthorim") identify names too; the leading capital keeps common
# nouns out.
GENTILIC_REGEX = re.compile(
    r'\b[A-Z][a-z]+(?:ite|ites|itish|aean|ean|ian|ians|im|iote|iotes)\b'
)

# Segments that describe where the word comes from rather than what it means.
# NOTE: no blanket 'see ' prefix here — that would eat real meanings like
# Reuben's "see ye a son"; cross-references are caught by SEE_REFERENCE_REGEX.
DERIVATION_PREFIXES = (
    'from', 'of ', 'contracted', 'the same', 'a form', 'for ', 'probably',
    'perhaps', 'apparently', 'patronymic', 'patrial', 'denominative',
    'feminine', 'masculine', 'plural', 'dual', 'compare', 'or ', 'rarely',
    'abbreviated', 'derived', 'prolonged', 'prolongation', 'irregular',
    'originally', 'intensive', 'a primitive', 'shortened', 'also ', 'used ',
    'including', 'in the sense', 'akin', 'with ', 'i.e.', 'by ',
    'participle', 'active participle', 'passive participle', 'infinitive',
    'a variation', 'an orthographical', 'a collateral', 'second form',
    'transmuted', 'a doubtful', 'lemma', 'corrected', 'an unused', 'formed',
    'reduplicated', 'a contraction', 'contraction', 'a shorter form',
    'a rare form', 'a prolonged form', 'full form', 'another form',
    'only in the plural', 'only in plural',
)

# Identification vocabulary that must never appear in a *meaning* gloss —
# if it does, an identification segment leaked through a side path.
IDENTIFICATION_LEAK_REGEX = re.compile(
    r'palestine|israelite|a christian|the famous|asia minor|'
    r'babylonian name|egyptian king|the berites',
    re.IGNORECASE,
)

# "see H1234" / "see Genesis 25:25" / "see הַר" are cross-references; a
# lowercase continuation ("see ye a son") is a meaning and is kept.
SEE_REFERENCE_REGEX = re.compile(r'^see\s+[^a-z\s]')

# Reference forms that point at another entry whose meaning applies to this
# name: "the same as X" (Sarah -> H8282), "of Hebrew origin (X)" (Greek NT
# names hopping to their Hebrew base, e.g. G1138 David -> H1732 "loving"),
# and contracted/abbreviated forms. The lemma is captured as the first
# contiguous run of non-ASCII script — robust against glued data corruption
# like "the same as אֵלָהlemma ...".
REFERENCE_HOP_REGEX = re.compile(
    r'^(?:(?:probably |perhaps |apparently )?'
    r'(?:the same(?: \([^)]*\))? as|(?:a|another) form (?:of|for)|for|'
    r'contracted from|contraction (?:for|of)|abbreviated from|'
    r'of Hebrew origin|of Chaldee origin))'
    r'[\s(]+.*?([^\x00-\x7f]+)'
)

# A meaning tucked inside a derivation segment, e.g. H804 Asshur:
# "apparently from X (in the sense of successful)".
IN_THE_SENSE_OF_REGEX = re.compile(r'\(in the sense of ([^)]{3,50})\)')

# A hedged meaning like "perhaps fortification" (H3946 Lakum) — kept with its
# hedge, unlike hedged derivations ("probably of foreign origin").
HEDGED_MEANING_REGEX = re.compile(r'^(perhaps|probably|apparently)\s+(.+)$')
DERIVATION_SIGNALS = re.compile(
    r'\b(?:from|of|origin|derivation|derivative|root|compare|unused|same as|'
    r'for)\b'
)


def _is_meaning_segment(seg):
    """Shared filter: does this description segment state a meaning?"""
    low = seg.lower()
    # Test derivation prefixes both as-is and with a leading parenthetical
    # (e.g. "(Aramaic) of foreign origin ..." or "(Nehemiah 12:14), from X").
    unwrapped = re.sub(r'^\([^)]*\)[\s,]*', '', low)
    if low.startswith(DERIVATION_PREFIXES) or unwrapped.startswith(DERIVATION_PREFIXES):
        return False
    if SEE_REFERENCE_REGEX.match(seg):
        return False
    # Lexicon bookkeeping and reference segments, not meanings.
    if any(marker in low for marker in (
        'name of', 'of foreign', 'of uncertain', 'of doubtful',
        'corrected to', 'xlit ', 'as if from',
    )):
        return False
    if '{' in seg or '}' in seg:
        return False
    # Segments that are (mostly) Hebrew/Greek script.
    ascii_letters = len(re.findall(r'[a-zA-Z]', seg))
    if ascii_letters < max(3, len(seg) // 4):
        return False
    return True


def _find_identification(segments):
    """Index of the segment that identifies a proper name, or None.

    A qualifying segment starts with a capitalized name, "as a name, ...",
    or an article followed by a capitalized gentilic ("an Arvadite or citizen
    of Arvad"), and contains an identification keyword. KJV renderings lists
    (marked by [idiom]/[phrase] or after ':--') never qualify.
    """
    for i, seg in enumerate(segments):
        if i == 0:
            # The first segment is always derivation/headword info.
            continue
        if '[idiom]' in seg or '[phrase]' in seg:
            continue
        candidate = seg.split(':--')[0]
        lead_ok = (
            candidate[:1].isupper()
            or candidate.lower().startswith('as a name')
            or (re.match(r'(?:an?|the|also)\b', candidate)
                and re.search(r'\b[A-Z][a-z]', candidate))
        )
        if lead_ok and (NAME_ID_KEYWORDS.search(candidate) or GENTILIC_REGEX.search(candidate)):
            return i
    return None


def _hedged_meaning(segments, id_idx):
    """Recover a hedged meaning like "perhaps fortification" (H3946)."""
    for seg in segments[:id_idx]:
        m = HEDGED_MEANING_REGEX.match(seg)
        if not m:
            continue
        remainder = m.group(2).strip().rstrip('.')
        if DERIVATION_SIGNALS.search(remainder.lower()):
            continue  # "probably of foreign origin" etc.
        if re.search(r'[^\x00-\x7f]', remainder):
            continue
        if 2 < len(remainder) <= 50:
            return f"{m.group(1)} {remainder}"
    return None


def _gentilic_identification(description, segments, id_idx):
    """For patrial/patronymic entries, the identification IS the meaning:
    "an Arvadite or citizen of Arvad" -> "citizen of Arvad"."""
    first = segments[0].lower()
    if 'patrial' not in first and 'patronymic' not in first:
        return None
    ident = segments[id_idx].split(':--')[0]
    # Prefer the explanatory half after " or "; else after the first comma.
    if ' or ' in ident:
        phrase = ident.split(' or ', 1)[1]
    elif ',' in ident:
        phrase = ident.split(',', 1)[1]
    else:
        return None
    phrase = re.sub(r'\([^)]*\)', '', phrase).strip().rstrip('.').strip()
    if re.search(r'\b(?:citizen|native|inhabitant|descendant|tribe|member)s?\b', phrase.lower()) \
            and 5 < len(phrase) <= 60 \
            and not IDENTIFICATION_LEAK_REGEX.search(phrase):
        return phrase
    return None


def extract_name_gloss(description, resolve_reference=None):
    """Pull the meaning of a proper name out of a Strong's description.

    Returns e.g. "well of a living (One) my Seer" for H883 (Beer-lahai-roi),
    or None when the entry is not confidently a proper name with a stated
    meaning. Precision is favored over recall: a missing note is better than
    a wrong one.

    Sources, in priority order:
    1. the description's own meaning segment(s);
    2. a meaning tucked into the derivation: "(in the sense of successful)";
    3. a hedged meaning: "perhaps fortification";
    4. via resolve_reference(lemma), the meaning of the entry this name is
       said to equal ("the same as X", "of Hebrew origin (X)", "contracted
       from X", ...);
    5. for patrial/patronymic gentilics, the identification itself
       ("citizen of Arvad").
    """
    if not description:
        return None
    segments = [s.strip() for s in description.split(';') if s.strip()]

    id_idx = _find_identification(segments)
    if not id_idx:
        return None

    def clean(gloss):
        if not gloss or not 2 < len(gloss) <= 100:
            return None
        if IDENTIFICATION_LEAK_REGEX.search(gloss):
            return None
        return gloss

    meaning_parts = [seg for seg in segments[:id_idx] if _is_meaning_segment(seg)]
    if meaning_parts:
        return clean('; '.join(meaning_parts).strip().rstrip('.').strip())

    for seg in segments[:id_idx]:
        sense = IN_THE_SENSE_OF_REGEX.search(seg)
        if sense:
            return clean(sense.group(1).strip())

    hedged = _hedged_meaning(segments, id_idx)
    if hedged:
        return clean(hedged)

    if resolve_reference:
        for seg in segments[:id_idx]:
            ref = REFERENCE_HOP_REGEX.match(seg)
            if ref:
                hopped = clean(resolve_reference(ref.group(1)))
                if hopped:
                    return hopped
                break  # one reference pattern per entry; don't scan on

    return _gentilic_identification(description, segments, id_idx)


def _first_meaning_segment(description):
    """The first stated meaning in a (typically common-noun) description.

    Used as the hop target for "the same as <lemma>" name references. The
    final segment is the KJV renderings list, so it never qualifies.
    """
    if not description:
        return None
    segments = [s.strip() for s in description.split(';') if s.strip()]
    for i, seg in enumerate(segments):
        if i == 0 or i == len(segments) - 1:
            continue
        if not _is_meaning_segment(seg):
            continue
        # The hop target may itself be a name; its identification segment
        # ("Elisha, the famous prophet") is not a meaning.
        candidate = seg.split(':--')[0]
        if candidate[:1].isupper() and (
            NAME_ID_KEYWORDS.search(candidate) or GENTILIC_REGEX.search(candidate)
        ):
            continue
        meaning = seg.strip().rstrip('.')
        if len(meaning) > 60:
            # Long entries elaborate in parentheses or after "i.e." — try
            # the stripped/head form, otherwise pass.
            stripped = re.sub(r'\s*\([^)]*\)', '', meaning).strip().rstrip(',')
            head = re.split(r',? i\.e\.', stripped)[0].strip()
            if 2 < len(stripped) <= 60:
                meaning = stripped
            elif 2 < len(head) <= 60:
                meaning = head
            else:
                return None
        return meaning if 2 < len(meaning) else None
    return None


def _build_name_glosses(strongs_by_number):
    # Lemma -> numbers index so reference hops ("the same as <lemma>",
    # "of Hebrew origin (<lemma>)", ...) can be resolved to the referenced
    # entry's meaning. NFC-normalized on both sides: Hebrew niqqud can be
    # encoded with differing combining-mark orders across entries.
    by_lemma = {}
    for sn, entry in strongs_by_number.items():
        lemma = entry.get('lemma')
        if lemma:
            by_lemma.setdefault(unicodedata.normalize('NFC', lemma), set()).add(sn)

    def _number_value(sn):
        try:
            return int(sn[1:])
        except (TypeError, ValueError):
            return None

    glosses = {}
    for sn, entry in strongs_by_number.items():
        def resolve(lemma, _self=sn):
            targets = by_lemma.get(unicodedata.normalize('NFC', lemma), set()) - {_self}
            if not targets:
                return None
            if len(targets) > 1:
                # Same-lemma entries cluster (Strong's numbers follow the
                # alphabet), and "the same as" points at the base entry next
                # door — take the nearest number, but only if unambiguous.
                self_val = _number_value(_self)
                vals = sorted(
                    (abs(_number_value(t) - self_val), t)
                    for t in targets
                    if _number_value(t) is not None and self_val is not None
                    and t[0] == _self[0]  # same language (H vs G)
                )
                if len(vals) < 1 or (len(vals) > 1 and vals[0][0] == vals[1][0]):
                    return None  # no candidate or tied distance: stay silent
                targets = {vals[0][1]}
            target = strongs_by_number.get(next(iter(targets)), {})
            return _first_meaning_segment(target.get('description') or '')

        gloss = extract_name_gloss(entry.get('description') or '', resolve_reference=resolve)
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
