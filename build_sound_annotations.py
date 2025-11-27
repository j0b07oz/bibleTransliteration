"""
Utility to precompute sound annotations for repeated Hebrew roots and initial root letters.

The script expects pre-tokenized Bible data, a literary unit outline, and a lexicon mapping
Strong's numbers to their roots. It produces a nested JSON structure keyed by book, chapter,
and verse to allow the frontend to highlight sound patterns without heavy runtime work.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, DefaultDict, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

VerseTokens = List[Mapping[str, Any]]
BibleIndex = Dict[str, Dict[int, Dict[int, VerseTokens]]]
Lexicon = Mapping[str, Mapping[str, Any]]


@dataclass
class VerseStats:
    """Root and initial counts for a single verse."""

    roots: Dict[str, List[int]]
    initials: Dict[str, List[int]]


@dataclass
class UnitStats:
    """Aggregated counts of roots and initials for a literary unit."""

    book: str
    verses: List[str]
    verse_refs: List[str]
    root_counts: Counter
    initial_counts: Counter
    root_verses: DefaultDict[str, set]
    initial_verses: DefaultDict[str, set]


_STRONGS_PATTERN = re.compile(r"[GH]\d+")


def normalize_strongs_number(value: Any) -> Optional[str]:
    """Return a cleaned Strong's number if one can be inferred.

    The function accepts either a string or a list of strings, returning the first
    match that resembles the pattern ``[GH]\\d+``.
    """

    def _extract(candidate: str) -> Optional[str]:
        match = _STRONGS_PATTERN.search(candidate.upper())
        return match.group(0) if match else None

    if isinstance(value, str):
        return _extract(value)
    if isinstance(value, Iterable):
        for item in value:
            if isinstance(item, str):
                extracted = _extract(item)
                if extracted:
                    return extracted
    return None


def load_json_file(path: str) -> Any:
    """Load a JSON file with UTF-8 encoding."""

    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def load_bible_tokens(path: str) -> List[Mapping[str, Any]]:
    """Load tokenized Bible data.

    The function accepts either a list of verse dictionaries or a mapping with a
    ``"verses"`` key containing such a list. No validation of the token schema is
    enforced beyond the presence of book/chapter/verse keys and a ``tokens`` list.
    """

    data = load_json_file(path)
    if isinstance(data, Mapping) and "verses" in data:
        verses = data["verses"]
    else:
        verses = data
    if not isinstance(verses, list):
        raise ValueError("Expected a list of verse entries in the Bible tokens file")
    return verses


def load_literary_units(path: str) -> Mapping[str, List[Mapping[str, Any]]]:
    """Load literary unit ranges keyed by book name."""

    data = load_json_file(path)
    if not isinstance(data, Mapping):
        raise ValueError("Literary units file must contain an object keyed by book name")
    return data


def load_lexicon_roots(path: str) -> Lexicon:
    """Load a lexicon that maps Strong's numbers to root metadata."""

    data = load_json_file(path)
    if not isinstance(data, Mapping):
        raise ValueError("Lexicon file must be a mapping of Strong's numbers to root data")
    return data


def build_index_by_book_chapter_verse(bible_tokens: Sequence[Mapping[str, Any]]) -> BibleIndex:
    """Organize verse entries by book, chapter, and verse for quick lookup."""

    index: BibleIndex = defaultdict(lambda: defaultdict(dict))
    for entry in bible_tokens:
        book_raw = entry.get("book_name") or entry.get("book")
        if book_raw is None:
            raise ValueError("Each verse entry must include a 'book_name' or 'book' field")
        book = str(book_raw)

        try:
            chapter = int(entry["chapter"])
            verse = int(entry["verse"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Each verse entry must include integer 'chapter' and 'verse' fields") from exc

        tokens = entry.get("tokens") or entry.get("tokenized") or entry.get("words") or []
        if not isinstance(tokens, list):
            raise ValueError("Verse tokens must be provided as a list")

        index[book][chapter][verse] = tokens

    return {book: {chapter: dict(verses) for chapter, verses in chapters.items()} for book, chapters in index.items()}


def collect_verse_stats(tokens: VerseTokens, lexicon: Lexicon) -> VerseStats:
    """Collect root and initial occurrences for a single verse."""

    roots: DefaultDict[str, List[int]] = defaultdict(list)
    initials: DefaultDict[str, List[int]] = defaultdict(list)

    for idx, token in enumerate(tokens):
        strongs_value = None
        if isinstance(token, Mapping):
            strongs_value = token.get("strongs") or token.get("strong") or token.get("s")
        elif isinstance(token, str):
            strongs_value = token

        strongs_number = normalize_strongs_number(strongs_value)
        if not strongs_number:
            continue

        lex_entry = lexicon.get(strongs_number)
        if not lex_entry:
            continue

        root = lex_entry.get("root")
        if root:
            roots[str(root)].append(idx)

        initial = lex_entry.get("first_root_letter") or lex_entry.get("first_root")
        if initial:
            initials[str(initial)].append(idx)

    return VerseStats(roots=dict(roots), initials=dict(initials))


def make_verse_id(book: str, chapter: int, verse: int) -> str:
    """Create a stable verse identifier useful for lookups."""

    return f"{book}|{chapter}|{verse}"


def tuple_from_range_point(point: Mapping[str, Any]) -> Tuple[int, int]:
    """Convert a range point object with chapter and verse into a tuple."""

    return int(point.get("chapter", 0)), int(point.get("verse", 0))


def compute_unit_stats(
    bible_index: BibleIndex,
    units: Mapping[str, List[Mapping[str, Any]]],
    verse_stats: Mapping[str, VerseStats],
) -> Tuple[List[UnitStats], DefaultDict[str, List[UnitStats]]]:
    """Aggregate root data for each literary unit and map verses to their units."""

    unit_results: List[UnitStats] = []
    verse_to_units: DefaultDict[str, List[UnitStats]] = defaultdict(list)

    for book, book_units in units.items():
        if book not in bible_index:
            continue

        book_data = bible_index[book]
        ordered_chapters = sorted(book_data.keys())
        ordered_verses = [
            (chapter, verse)
            for chapter in ordered_chapters
            for verse in sorted(book_data[chapter].keys())
        ]

        for unit in book_units:
            start = tuple_from_range_point(unit.get("range_start", {}))
            end = tuple_from_range_point(unit.get("range_end", {}))

            verses_in_unit: List[Tuple[int, int]] = [
                (chapter, verse)
                for chapter, verse in ordered_verses
                if start <= (chapter, verse) <= end
            ]

            verse_ids: List[str] = []
            verse_refs: List[str] = []
            root_counts: Counter = Counter()
            initial_counts: Counter = Counter()
            root_verses: DefaultDict[str, set] = defaultdict(set)
            initial_verses: DefaultDict[str, set] = defaultdict(set)

            for chapter, verse in verses_in_unit:
                verse_id = make_verse_id(book, chapter, verse)
                verse_ref = f"{chapter}:{verse}"
                verse_ids.append(verse_id)
                verse_refs.append(verse_ref)

                stats = verse_stats.get(verse_id)
                if not stats:
                    continue

                for root, indices in stats.roots.items():
                    root_counts[root] += len(indices)
                    root_verses[root].add(verse_ref)

                for initial, indices in stats.initials.items():
                    initial_counts[initial] += len(indices)
                    initial_verses[initial].add(verse_ref)

            unit_stat = UnitStats(
                book=book,
                verses=verse_ids,
                verse_refs=verse_refs,
                root_counts=root_counts,
                initial_counts=initial_counts,
                root_verses=root_verses,
                initial_verses=initial_verses,
            )
            unit_results.append(unit_stat)

            for verse_id in verse_ids:
                verse_to_units[verse_id].append(unit_stat)

    return unit_results, verse_to_units


def should_include_unit_item(
    verses_with_item: Iterable[str],
    first_verse: Optional[str],
    last_verse: Optional[str],
) -> bool:
    """Determine whether a root or initial qualifies for unit clustering."""

    verses_list = sorted(set(verses_with_item))
    if len(verses_list) >= 2:
        return True
    if verses_list and first_verse and last_verse:
        return first_verse in verses_list and last_verse in verses_list
    return False


def build_sound_annotations(
    bible_index: BibleIndex,
    units: Mapping[str, List[Mapping[str, Any]]],
    lexicon: Lexicon,
) -> Dict[str, Dict[str, Dict[str, Dict[str, Dict[str, List[Any]]]]]]:
    """Build the nested sound annotations structure keyed by book/chapter/verse."""

    verse_stats: Dict[str, VerseStats] = {}
    for book, chapters in bible_index.items():
        for chapter, verses in chapters.items():
            for verse, tokens in verses.items():
                verse_id = make_verse_id(book, chapter, verse)
                verse_stats[verse_id] = collect_verse_stats(tokens, lexicon)

    _, verse_to_units = compute_unit_stats(bible_index, units, verse_stats)

    annotations: Dict[str, Dict[str, Dict[str, Dict[str, Dict[str, List[Any]]]]]] = {}

    for book in sorted(bible_index.keys()):
        book_output: Dict[str, Dict[str, Dict[str, Dict[str, List[Any]]]]] = {}
        for chapter in sorted(bible_index[book].keys()):
            chapter_output: Dict[str, Dict[str, Dict[str, List[Any]]]] = {}
            for verse in sorted(bible_index[book][chapter].keys()):
                verse_id = make_verse_id(book, chapter, verse)
                stats = verse_stats.get(verse_id, VerseStats(roots={}, initials={}))

                candidate_units = verse_to_units.get(verse_id, [])
                primary_unit = min(candidate_units, key=lambda u: len(u.verses)) if candidate_units else None

                local_roots: Dict[str, List[int]] = {}
                for root, positions in stats.roots.items():
                    if len(positions) < 2:
                        continue
                    unit_total = primary_unit.root_counts.get(root, 0) if primary_unit else 0
                    if unit_total >= 3:
                        local_roots[root] = positions

                local_initials: Dict[str, List[int]] = {}
                for initial, positions in stats.initials.items():
                    if len(positions) < 2:
                        continue
                    unit_total = primary_unit.initial_counts.get(initial, 0) if primary_unit else 0
                    if unit_total >= 3:
                        local_initials[initial] = positions

                unit_clusters: DefaultDict[str, set] = defaultdict(set)
                for unit in candidate_units:
                    first_ref = unit.verse_refs[0] if unit.verse_refs else None
                    last_ref = unit.verse_refs[-1] if unit.verse_refs else None

                    for root, verses_with_root in unit.root_verses.items():
                        if should_include_unit_item(verses_with_root, first_ref, last_ref):
                            unit_clusters[root].update(verses_with_root)

                    for initial, verses_with_initial in unit.initial_verses.items():
                        if should_include_unit_item(verses_with_initial, first_ref, last_ref):
                            unit_clusters[initial].update(verses_with_initial)

                unit_clusters_sorted = {key: sorted(values) for key, values in sorted(unit_clusters.items())}

                chapter_output[str(verse)] = {
                    "local_roots": dict(sorted(local_roots.items())),
                    "local_initials": dict(sorted(local_initials.items())),
                    "unit_clusters": unit_clusters_sorted,
                }

            book_output[str(chapter)] = dict(sorted(chapter_output.items(), key=lambda item: int(item[0])))

        annotations[book] = dict(sorted(book_output.items(), key=lambda item: int(item[0])))

    return annotations


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the script."""

    parser = argparse.ArgumentParser(description="Build sound annotations for Hebrew roots.")
    parser.add_argument("--bible", required=True, help="Path to tokenized Bible JSON file")
    parser.add_argument("--units", required=True, help="Path to literary units JSON file")
    parser.add_argument("--lexicon", required=True, help="Path to lexicon roots JSON file")
    parser.add_argument("--out", required=True, help="Output path for the sound annotations JSON file")
    return parser.parse_args()


def main() -> None:
    """Entry point for building and saving sound annotations."""

    args = parse_args()

    bible_tokens = load_bible_tokens(args.bible)
    lexicon = load_lexicon_roots(args.lexicon)
    units = load_literary_units(args.units)
    bible_index = build_index_by_book_chapter_verse(bible_tokens)

    annotations = build_sound_annotations(bible_index, units, lexicon)

    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(annotations, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


if __name__ == "__main__":
    main()
