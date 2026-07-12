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
import logging
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
    # phrase key (e.g. 'H3801-H6446') -> rare-phrase record (tokens, passages,
    # occurrences, counts); see _build_phrase_index for the record shape
    phrase_index: dict
    # (book_name, chapter) -> [phrase keys], best echoes first, for the panel
    phrases_by_chapter: dict
    # (book_name, chapter) -> illustration scene payload for the visual-guide
    # panel, with steps filtered/clamped to that chapter (see
    # _build_illustration_index); {} when no catalog is present
    illustrations_by_chapter: dict


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


def _build_phrase_index(phrase_data, book_order):
    """Assemble the rare-phrase lookup structures from the generated index.

    ``phrase_data`` is the parsed ``phrase_index.json`` (``{'meta', 'phrases'}``)
    or None. Returns ``(phrases, phrases_by_chapter)`` where:

    - ``phrases``: key -> record with tokens, language, occurrences (canonical
      book order), passages, occurrence/content counts, and a cross-book flag.
      Occurrences are ``[book_name, chapter, verse, start_index]`` where
      start_index is the phrase's first token position among the verse's
      lexical markers.
    - ``phrases_by_chapter``: (book_name, chapter) -> [keys], ordered best
      first (cross-book, more content tokens, longer, more occurrences) for the
      chapter panel and browse page.

    Content-token counts reuse the stopword set recorded in the index's meta so
    they match exactly what the build script used for its all-stopword filter.
    """
    if not phrase_data:
        return {}, {}

    meta = phrase_data.get('meta', {})
    stopwords = set(meta.get('stopwords', []))
    raw_phrases = phrase_data.get('phrases', {})

    def book_rank(name):
        return book_order.get(name, 1 << 30)

    phrases = {}
    by_chapter = {}
    for key, occ in raw_phrases.items():
        tokens = key.split('-')
        occ_sorted = sorted(occ, key=lambda o: (book_rank(o[0]), o[1], o[2], o[3]))
        passages = sorted(
            {(o[0], o[1]) for o in occ_sorted},
            key=lambda p: (book_rank(p[0]), p[1]),
        )
        record = {
            'key': key,
            'tokens': tokens,
            'lang': key[:1],
            'length': len(tokens),
            'occurrences': occ_sorted,
            'passages': passages,
            'occ_count': len(occ_sorted),
            'content_count': sum(1 for t in tokens if t not in stopwords),
            'cross_book': len({p[0] for p in passages}) > 1,
        }
        phrases[key] = record
        for passage in passages:
            by_chapter.setdefault(passage, []).append(key)

    def sort_key(key):
        r = phrases[key]
        return (not r['cross_book'], -r['content_count'], -r['length'],
                -r['occ_count'], key)

    for keys in by_chapter.values():
        keys.sort(key=sort_key)

    return phrases, by_chapter


# Default dim (dark-overlay opacity outside the spotlight) when a step omits it.
DEFAULT_ILLUSTRATION_DIM = 0.55

# Required numeric keys per region kind. Coordinates are percentages (0-100) of
# the image's own pixel space, so a region survives the image being reused at
# any display size.
_ILLUSTRATION_REGION_KEYS = {
    'rect': ('x', 'y', 'w', 'h'),
    'ellipse': ('cx', 'cy', 'rx', 'ry'),
}


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _validate_illustration_region(region):
    """Return (ok, reason) for one region dict (percent coords, 0-100)."""
    if not isinstance(region, dict):
        return False, 'region is not an object'
    kind = region.get('kind')
    required = _ILLUSTRATION_REGION_KEYS.get(kind)
    if not required:
        return False, f'unknown region kind {kind!r}'
    for key in required:
        if not _is_number(region.get(key)):
            return False, f'{kind} region missing numeric {key!r}'
    if kind == 'rect':
        x, y, w, h = region['x'], region['y'], region['w'], region['h']
        if w <= 0 or h <= 0:
            return False, 'rect has non-positive size'
        if x < 0 or y < 0 or x + w > 100 or y + h > 100:
            return False, 'rect out of 0-100 bounds'
    else:  # ellipse
        cx, cy, rx, ry = region['cx'], region['cy'], region['rx'], region['ry']
        if rx <= 0 or ry <= 0:
            return False, 'ellipse has non-positive radius'
        if cx - rx < 0 or cy - ry < 0 or cx + rx > 100 or cy + ry > 100:
            return False, 'ellipse out of 0-100 bounds'
    return True, None


def _validate_illustration_image(image):
    """Return (ok, reason) for a scene's image block (structure only).

    File existence is intentionally NOT checked here — the lenient loader has no
    handle on the static directory. tests/test_illustration_catalog.py performs
    the on-disk check against the shipped catalog so CI fails on a missing file.
    """
    if not isinstance(image, dict):
        return False, 'missing image object'
    if not isinstance(image.get('alt'), str) or not image['alt'].strip():
        return False, 'image missing alt text'
    if not isinstance(image.get('fallback'), str) or not image['fallback']:
        return False, 'image missing fallback path'
    for key in ('width', 'height'):
        value = image.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            return False, f'image missing positive {key}'
    sources = image.get('sources')
    if not isinstance(sources, list) or not sources:
        return False, 'image missing sources'
    for source in sources:
        if not isinstance(source, dict) or not source.get('type'):
            return False, 'image source missing type'
        srcset = source.get('srcset')
        if not isinstance(srcset, list) or not srcset:
            return False, 'image source missing srcset'
        for cand in srcset:
            if (not isinstance(cand, dict) or not cand.get('path')
                    or not isinstance(cand.get('width'), int) or isinstance(cand.get('width'), bool)):
                return False, 'image srcset candidate missing path/width'
    return True, None


def _clamp_illustration_verse(verse, max_verse):
    if max_verse <= 0:
        return int(verse)
    return max(1, min(int(verse), max_verse))


def _resolve_illustration_passage(passage, book_name_lookup, chapter_verse_counts):
    """Expand one passage into {(book, chapter): (start_verse, end_verse)}.

    Multi-chapter passages are split per chapter and clamped to each chapter's
    verse count, mirroring _unit_bounds_for_chapter in routes.py. Returns
    (ok, reason, mapping).
    """
    if not isinstance(passage, dict):
        return False, 'passage is not an object', {}
    raw_book = passage.get('book')
    if not isinstance(raw_book, str) or not raw_book:
        return False, 'passage missing book', {}
    book = book_name_lookup.get(raw_book.lower())
    if not book:
        return False, f'unknown book {raw_book!r}', {}

    start = passage.get('start') or {}
    end = passage.get('end') or start
    try:
        start_ch = int(start['chapter'])
        start_v = int(start['verse'])
        end_ch = int(end.get('chapter', start_ch))
        end_v = int(end.get('verse', start_v))
    except (KeyError, TypeError, ValueError):
        return False, 'passage missing/invalid chapter or verse', {}

    if start_ch > end_ch or (start_ch == end_ch and start_v > end_v):
        return False, 'passage start after end', {}

    chapter_counts = chapter_verse_counts.get(book, {})
    resolved = {}
    for chapter in range(start_ch, end_ch + 1):
        max_verse = chapter_counts.get(chapter, 0)
        if max_verse <= 0:
            return False, f'{book} has no chapter {chapter}', {}
        sv = start_v if chapter == start_ch else 1
        ev = end_v if chapter == end_ch else max_verse
        sv = _clamp_illustration_verse(sv, max_verse)
        ev = max(sv, _clamp_illustration_verse(ev, max_verse))
        resolved[(book, chapter)] = (sv, ev)
    return True, None, resolved


def _prepare_illustration_step(step, book_name_lookup, chapter_verse_counts):
    """Validate a step; return (ok, reason, {(book, chapter): (start_v, end_v)})."""
    if not isinstance(step, dict):
        return False, 'step is not an object', {}
    if not isinstance(step.get('id'), str) or not step['id']:
        return False, 'missing string id', {}

    regions = step.get('regions')
    if not isinstance(regions, list) or not regions:
        return False, 'missing regions', {}
    for region in regions:
        ok, reason = _validate_illustration_region(region)
        if not ok:
            return False, reason, {}

    dim = step.get('dim', DEFAULT_ILLUSTRATION_DIM)
    if not _is_number(dim) or not (0 < dim <= 1):
        return False, f'dim {dim!r} out of range (0, 1]', {}

    passages = step.get('passages')
    if not isinstance(passages, list) or not passages:
        return False, 'missing passages', {}

    ranges = {}
    for passage in passages:
        ok, reason, resolved = _resolve_illustration_passage(
            passage, book_name_lookup, chapter_verse_counts)
        if not ok:
            return False, reason, {}
        for key, (sv, ev) in resolved.items():
            if key in ranges:
                prev_sv, prev_ev = ranges[key]
                ranges[key] = (min(prev_sv, sv), max(prev_ev, ev))
            else:
                ranges[key] = (sv, ev)
    return True, None, ranges


def _render_illustration_step(step, chapter, start_verse, end_verse):
    """Reduce a raw step to the render-ready payload for a single chapter."""
    if step.get('label'):
        ref = step['label']
    elif start_verse == end_verse:
        ref = f'{chapter}:{start_verse}'
    else:
        ref = f'{chapter}:{start_verse}–{end_verse}'  # en dash
    return {
        'id': step['id'],
        'ref': ref,
        'hebrew': step.get('hebrew', ''),
        'translit': step.get('translit', ''),
        'gloss': step.get('gloss', ''),
        'note': step.get('note', ''),
        'regions': step['regions'],
        'dim': step.get('dim', DEFAULT_ILLUSTRATION_DIM),
        'start_verse': start_verse,
        'end_verse': end_verse,
    }


def _prepare_illustration_scene(scene, book_name_lookup, chapter_verse_counts):
    """Validate a raw scene; return (ok, reason, {(book, chapter): payload}).

    The scene is accepted or rejected as a whole so a half-valid scene never
    renders. Each payload is {id, title, image, steps} where steps are only the
    steps that touch that chapter, sorted by start verse.
    """
    if not isinstance(scene, dict):
        return False, 'scene is not an object', {}
    scene_id = scene.get('id')
    if not isinstance(scene_id, str) or not scene_id:
        return False, 'missing string id', {}

    image = scene.get('image')
    ok, reason = _validate_illustration_image(image)
    if not ok:
        return False, reason, {}

    steps = scene.get('steps')
    if not isinstance(steps, list) or not steps:
        return False, 'missing steps', {}

    prepared_steps = []
    touched = set()
    for step in steps:
        ok, reason, ranges = _prepare_illustration_step(
            step, book_name_lookup, chapter_verse_counts)
        if not ok:
            sid = step.get('id') if isinstance(step, dict) else None
            return False, f'step {sid!r}: {reason}', {}
        prepared_steps.append((step, ranges))
        touched.update(ranges.keys())

    if not touched:
        return False, 'no resolvable passages', {}

    title = scene.get('title') or scene_id
    payloads = {}
    for (book, chapter) in touched:
        chapter_steps = []
        for step, ranges in prepared_steps:
            if (book, chapter) not in ranges:
                continue
            sv, ev = ranges[(book, chapter)]
            chapter_steps.append(_render_illustration_step(step, chapter, sv, ev))
        chapter_steps.sort(key=lambda s: (s['start_verse'], s['end_verse']))
        payloads[(book, chapter)] = {
            'id': scene_id,
            'title': title,
            'image': image,
            'steps': chapter_steps,
        }
    return True, None, payloads


def _build_illustration_index(illustration_data, book_name_lookup, chapter_verse_counts):
    """(book_name, chapter) -> chapter-localized illustration scene payload.

    Lenient by design: a structurally invalid scene is logged and skipped so a
    bad catalog entry can never take down startup (matching the optional-file
    convention used elsewhere in this module). Strict, build-failing validation
    of the shipped catalog lives in tests/test_illustration_catalog.py.
    """
    log = logging.getLogger(__name__)
    if not illustration_data:
        return {}

    scenes = illustration_data.get('scenes', []) if isinstance(illustration_data, dict) else None
    if not isinstance(scenes, list):
        log.warning('Illustration catalog has no scenes list; ignoring')
        return {}

    index = {}
    claimed = {}  # (book, chapter) -> scene_id, for collision reporting
    for scene in scenes:
        scene_id = scene.get('id') if isinstance(scene, dict) else None
        ok, reason, payloads = _prepare_illustration_scene(
            scene, book_name_lookup, chapter_verse_counts)
        if not ok:
            log.warning('Skipping illustration scene %r: %s', scene_id, reason)
            continue
        for key, payload in payloads.items():
            if key in claimed:
                log.warning(
                    'Illustration scene %r skips %s %s: already claimed by %r',
                    scene_id, key[0], key[1], claimed[key])
                continue
            index[key] = payload
            claimed[key] = scene_id
    return index


def build_bible_data(
    strongs_data,
    kjv_data,
    default_strongs_dict=None,
    outline_data=None,
    hebrew_to_greek=None,
    greek_to_hebrew=None,
    phrase_data=None,
    illustration_data=None,
) -> BibleData:
    """Assemble a BibleData from already-parsed structures.

    Used by load_bible_data (from files) and by tests (from in-memory fixtures).
    """
    verses_by_book, book_order, book_chapter_count, chapter_verse_counts, book_name_lookup = (
        _build_verse_indexes(kjv_data)
    )
    strongs_by_number = _build_strongs_index(strongs_data)
    phrase_index, phrases_by_chapter = _build_phrase_index(phrase_data, book_order)
    illustrations_by_chapter = _build_illustration_index(
        illustration_data, book_name_lookup, chapter_verse_counts)
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
        phrase_index=phrase_index,
        phrases_by_chapter=phrases_by_chapter,
        illustrations_by_chapter=illustrations_by_chapter,
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

    phrase_data = None
    phrase_path = os.path.join(data_dir, 'phrase_index.json')
    if os.path.exists(phrase_path):
        phrase_data = _load_json(phrase_path)
        if logger:
            logger.info(
                f"Loaded {len(phrase_data.get('phrases', {}))} rare "
                f"original-language phrases"
            )
    elif logger:
        logger.warning(f"Phrase index not found at {phrase_path}")

    illustration_data = None
    illustrations_path = os.path.join(data_dir, 'illustrations.json')
    if os.path.exists(illustrations_path):
        illustration_data = _load_json(illustrations_path)
        if logger:
            scene_count = len(illustration_data.get('scenes', [])) if isinstance(illustration_data, dict) else 0
            logger.info(f"Loaded {scene_count} illustration scene(s)")
    elif logger:
        logger.warning(f"Illustration catalog not found at {illustrations_path}")

    return build_bible_data(
        strongs_data,
        kjv_data,
        default_strongs_dict=default_strongs_dict,
        outline_data=outline_data,
        hebrew_to_greek=hebrew_to_greek,
        greek_to_hebrew=greek_to_hebrew,
        phrase_data=phrase_data,
        illustration_data=illustration_data,
    )
