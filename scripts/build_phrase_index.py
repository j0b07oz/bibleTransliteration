#!/usr/bin/env python3
"""
Build the rare original-language phrase index from the app's own KJV+Strong's
text.

Phrase identity is the ordered sequence of original-language lexical tokens
(Strong's numbers) as they appear in ``kjv_strongs.json``. The KJV is tagged
against its own underlying Hebrew/Greek, so the marker stream already carries
the original wording and its (translation-literal) order — no external tagged
corpus is required. Grammar/morphology codes are parenthesized (``{(H8804)}``)
and are naturally skipped by the plain-marker pattern, so only true lexical
tokens enter a sequence.

A phrase is 2–5 contiguous lexical tokens within a single verse. We keep
"echoes": sequences that occur in exactly two book-chapter passages, after
minimal-distinctive suppression (drop a phrase if a shorter contiguous
subphrase is already just as rare) and all-stopword exclusion (drop phrases
made only of the most common tokens, e.g. the object marker H853).

The result reproduces the flagship case exactly:
    H3801-H6446  ->  2 passages / 5 occurrences
    Genesis 37:3, 37:23, 37:32  and  2 Samuel 13:18, 13:19

Run once to (re)generate app/data/phrase_index.json, then commit the artifact
so the server never rebuilds it at startup:

    python scripts/build_phrase_index.py
"""
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
KJV_PATH = SCRIPT_DIR.parent / "app" / "data" / "kjv_strongs.json"
OUTPUT_PATH = SCRIPT_DIR.parent / "app" / "data" / "phrase_index.json"

# A single plain lexical marker: {H7225} / {G976}. Parenthesized grammar codes
# ({(H8804)}) and the malformed {H8804)} shape never match, so a verse's
# findall is exactly its ordered original-language lexical-token sequence.
PLAIN_MARKER_REGEX = re.compile(r"\{([HG]\d+)\}")

SCHEMA_VERSION = 1
MIN_LEN = 2
MAX_LEN = 5
# The two-passage rarity threshold that defines an "echo".
ECHO_PASSAGES = 2
# Tokens this common carry no phrase signal on their own (object marker H853,
# relative H834, conjunctions, articles, ...). Derived from the text, not a
# hand-curated list, so it tracks the corpus. Stored in meta so the loader
# uses the identical set when it recomputes content-token counts.
STOPWORD_COUNT = 60


def load_verse_sequences(kjv_path):
    """Return [(book_name, chapter, verse, [strongs, ...]), ...] and token freq.

    Only verses that carry at least one lexical token are included; the
    per-verse list preserves marker order (i.e. KJV/translation order).
    """
    with open(kjv_path, encoding="utf-8") as f:
        kjv = json.load(f)

    sequences = []
    freq = Counter()
    for verse in kjv.get("verses", []):
        seq = PLAIN_MARKER_REGEX.findall(verse.get("text", ""))
        if not seq:
            continue
        sequences.append(
            (verse["book_name"], int(verse["chapter"]), int(verse["verse"]), seq)
        )
        freq.update(seq)
    return sequences, freq


def build_ngram_occurrences(sequences):
    """Map each 2–5-token phrase key to its occurrences.

    An occurrence is [book, chapter, verse, start_index] where start_index is
    the 0-based position of the phrase's first token among the verse's lexical
    markers — enough to highlight the exact rendered words later.
    """
    occurrences = defaultdict(list)
    for book, chapter, verse, seq in sequences:
        n_tokens = len(seq)
        for length in range(MIN_LEN, MAX_LEN + 1):
            for i in range(n_tokens - length + 1):
                key = "-".join(seq[i : i + length])
                occurrences[key].append([book, chapter, verse, i])
    return occurrences


def passages_of(occ_list):
    """Distinct (book, chapter) passages an occurrence list touches."""
    return {(book, chapter) for book, chapter, _verse, _pos in occ_list}


def build_index():
    sequences, freq = load_verse_sequences(KJV_PATH)
    occurrences = build_ngram_occurrences(sequences)

    # Passage count per phrase key drives both the echo test and the
    # minimal-distinctive suppression below.
    passage_counts = {key: len(passages_of(occ)) for key, occ in occurrences.items()}
    stopwords = {tok for tok, _c in freq.most_common(STOPWORD_COUNT)}

    def has_rare_subphrase(tokens):
        """True if some strictly-shorter contiguous subphrase is already an
        echo-or-rarer (<= 2 passages). Such a phrase is a mere extension of an
        already-rare core and adds noise, so it is suppressed."""
        length = len(tokens)
        for sub_len in range(MIN_LEN, length):
            for i in range(length - sub_len + 1):
                sub_key = "-".join(tokens[i : i + sub_len])
                if passage_counts.get(sub_key, 0) <= ECHO_PASSAGES:
                    return True
        return False

    phrases = {}
    for key, occ in occurrences.items():
        if passage_counts[key] != ECHO_PASSAGES:
            continue
        tokens = key.split("-")
        if all(tok in stopwords for tok in tokens):
            continue
        if has_rare_subphrase(tokens):
            continue
        # Occurrences sorted for deterministic output (canonical book order is
        # applied at load time via BibleData.book_order).
        occ.sort(key=lambda o: (o[0], o[1], o[2], o[3]))
        phrases[key] = occ

    meta = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "kjv_strongs.json",
        "min_len": MIN_LEN,
        "max_len": MAX_LEN,
        "echo_passages": ECHO_PASSAGES,
        "kind": "echo",
        "stopwords": sorted(stopwords),
        "phrase_count": len(phrases),
        "note": (
            "Derived from the public-domain KJV+Strong's text. A phrase is an "
            "ordered run of original-language lexical tokens; an echo occurs in "
            "exactly two book-chapter passages."
        ),
    }
    return {"meta": meta, "phrases": phrases}


def main():
    index = build_index()
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, separators=(",", ":"))

    phrases = index["phrases"]
    total_occ = sum(len(o) for o in phrases.values())
    print(f"Wrote {OUTPUT_PATH.relative_to(SCRIPT_DIR.parent)}")
    print(f"  echoes: {len(phrases)}   occurrences: {total_occ}")
    flagship = phrases.get("H3801-H6446")
    if flagship:
        passages = sorted(passages_of(flagship))
        print(f"  H3801-H6446: {len(passages)} passages / {len(flagship)} occurrences")
        for book, chapter in passages:
            print(f"    - {book} {chapter}")
    else:
        print("  WARNING: flagship phrase H3801-H6446 missing from index!")


if __name__ == "__main__":
    main()
