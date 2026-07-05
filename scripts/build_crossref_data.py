#!/usr/bin/env python3
"""
Build Hebrew-Greek cross-reference JSON from STEP Bible lexicon data.

This script parses TBESG (Greek lexicon) and TBESH (Hebrew lexicon) files
to extract bidirectional Hebrew ↔ Greek Strong's number mappings.

Data sources:
- TBESG: Contains explicit "= the Greek of H####" mappings
- TBESG: Contains "[in LXX chiefly for XXX ;]" Hebrew word references in definitions
- TBESH: Contains Hebrew lexicon data for Hebrew word → Strong's number lookup

Extraction Methods:
1. Explicit: Direct "= the Greek of H####" mappings (highest confidence)
2. LXX Chiefly: "[in LXX chiefly for XXX]" patterns (high confidence)
3. LXX Freq: "[in LXX freq. for XXX]" patterns (high confidence)
4. LXX Simple: "[in LXX ... for XXX]" patterns (medium confidence)
5. H-References: Direct H#### numbers in definition text (low confidence)

Run once to generate app/data/hebrew_greek_crossref.json
"""

import json
import re
import os
import unicodedata
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# Paths
SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR / "data"
OUTPUT_PATH = SCRIPT_DIR.parent / "app" / "data" / "hebrew_greek_crossref.json"

# =============================================================================
# Regex Patterns
# =============================================================================

# Pattern for explicit Greek→Hebrew mapping in dStrong column
# e.g., "G0002 = the Greek of H0175" or "G0005 = a Name of H3068G"
EXPLICIT_CROSSREF_PATTERN = re.compile(
    r'= (?:the Greek of|a Name of|the Aramaic of|a Hebrew of)\s+(H\d+[A-Z]?)'
)

# Pattern to extract the full [in LXX...] block
LXX_BLOCK_PATTERN = re.compile(r'\[in LXX[^\]]*\]')

# Patterns for different confidence levels within LXX blocks
# Primary mappings (high confidence - common LXX usage)
LXX_CHIEFLY_FOR_PATTERN = re.compile(r'chiefly for\s+([א-ת][א-תְֿ\u0590-\u05FF]*)')
LXX_FREQ_FOR_PATTERN = re.compile(r'freq\.\s+for\s+([א-ת][א-תְֿ\u0590-\u05FF]*)')

# Secondary mappings (medium confidence)
# Match "for" followed by Hebrew, but not if preceded by "chiefly" or "freq."
LXX_SIMPLE_FOR_PATTERN = re.compile(r'(?<!chiefly )(?<!freq\. )for\s+([א-ת][א-תְֿ\u0590-\u05FF]*)')

# Also capture Hebrew words with verb forms like "אהב pi." or "שׁיר hi."
HEBREW_WORD_WITH_FORM = re.compile(r'([א-ת][א-תְֿ\u0590-\u05FF]*)\s*(?:q\.|ni\.|pi\.|pu\.|hi\.|ho\.|hith\.)?')

# Pattern to extract Hebrew Strong's from reference like "(יטב hi.)" or "(H1234)"
HEBREW_IN_PARENS_PATTERN = re.compile(r'\(H(\d+)\)')

# Pattern for any H#### reference in text (bracketed or standalone)
ANY_HEBREW_REF_PATTERN = re.compile(r'\bH(\d{3,5})\b')

# Pattern for Strong's numbers
STRONGS_PATTERN = re.compile(r'^([HG]\d+)')

# Hebrew unicode ranges for niqqud (vowel points)
HEBREW_NIQQUD_RANGE = '\u0591-\u05BD\u05BF-\u05C2\u05C4-\u05C7'


def normalize_strongs(strongs: str) -> str:
    """Normalize Strong's number by removing suffix letters and leading zeroes.

    Examples:
        G0005 -> G5
        H0175 -> H175
        G0005A -> G5
        H07225 -> H7225
    """
    match = STRONGS_PATTERN.match(strongs.strip())
    if match:
        raw = match.group(1)
        # Extract prefix (H or G) and number
        prefix = raw[0]
        num_str = raw[1:]
        # Remove leading zeroes but keep at least one digit
        num = int(num_str)
        return f"{prefix}{num}"
    return strongs.strip()


def strip_niqqud(hebrew_word: str) -> str:
    """Remove vowel points (niqqud) from Hebrew word to get consonants only.

    Examples:
        טוֹב -> טוב
        אָהַב -> אהב
        מַלְאָךְ -> מלאך
    """
    # Remove niqqud (vowel points) - Unicode range U+0591-U+05C7
    result = re.sub(f'[{HEBREW_NIQQUD_RANGE}]', '', hebrew_word)
    return result


def build_hebrew_lookup(filepath: Path) -> tuple[dict, dict, dict]:
    """Build Hebrew word → Strong's number lookup tables from TBESH.

    Creates lookup tables for mapping Hebrew words found in TBESG definitions
    back to their Strong's numbers. The tables support both exact matches
    (with vowel points) and consonant-only fallback matches.

    Returns:
        (hebrew_voweled, hebrew_consonants, hebrew_metadata)
        - hebrew_voweled: exact match lookup {טוֹב: [H2896]}
        - hebrew_consonants: consonants only fallback {טוב: [H2896, H2895]}
        - hebrew_metadata: metadata for each Strong's number
    """
    hebrew_voweled = defaultdict(list)
    hebrew_consonants = defaultdict(list)
    hebrew_metadata = {}

    print(f"Building Hebrew word lookup from {filepath}...")

    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    data_started = False
    entries_parsed = 0

    for line in lines:
        # Skip header until we see the data delimiter
        if '==============' in line:
            data_started = True
            continue

        if not data_started or line.startswith('#') or not line.strip():
            continue

        # Skip lines that don't start with H (data lines)
        if not line.startswith('H'):
            continue

        # Parse tab-separated fields
        parts = line.split('\t')
        if len(parts) < 7:
            continue

        estrong = parts[0].strip()  # e.g., H0001
        hebrew = parts[3].strip() if len(parts) > 3 else ""
        xlit = parts[4].strip() if len(parts) > 4 else ""
        gloss = parts[6].strip() if len(parts) > 6 else ""

        # Normalize the Strong's number
        hebrew_num = normalize_strongs(estrong)
        if not hebrew_num.startswith('H'):
            continue

        entries_parsed += 1

        # Store metadata (only first occurrence for each number)
        if hebrew_num not in hebrew_metadata:
            hebrew_metadata[hebrew_num] = {
                "lemma": hebrew,
                "xlit": xlit,
                "gloss": gloss
            }

        # Skip if no Hebrew word
        if not hebrew:
            continue

        # Handle multiple forms separated by comma or space
        # e.g., "אֲבִיָּ֫הוּ, אֲבִיָּה" or "אֲבִיגַ֫יִל, אֲבִיגַ֫ל"
        hebrew_forms = re.split(r'[,\s]+', hebrew)

        for form in hebrew_forms:
            form = form.strip()
            if not form or not re.search(r'[א-ת]', form):
                continue

            # Clean up the form - remove any non-Hebrew characters
            # but keep the Hebrew letters and niqqud
            clean_form = re.sub(r'[^\u0590-\u05FF]', '', form)
            if not clean_form:
                continue

            # Add to voweled lookup (exact match)
            if hebrew_num not in hebrew_voweled[clean_form]:
                hebrew_voweled[clean_form].append(hebrew_num)

            # Add to consonants-only lookup (fallback)
            consonants = strip_niqqud(clean_form)
            if consonants and hebrew_num not in hebrew_consonants[consonants]:
                hebrew_consonants[consonants].append(hebrew_num)

    print(f"  Parsed {entries_parsed} Hebrew entries")
    print(f"  Created {len(hebrew_voweled)} voweled word lookups")
    print(f"  Created {len(hebrew_consonants)} consonant-only lookups")

    return dict(hebrew_voweled), dict(hebrew_consonants), hebrew_metadata


def lookup_hebrew_strongs(
    hebrew_word: str,
    hebrew_voweled: dict,
    hebrew_consonants: dict
) -> list:
    """Look up Strong's number(s) for a Hebrew word.

    First tries exact match with vowel points, then falls back to
    consonant-only matching.

    Args:
        hebrew_word: Hebrew word to look up (may include niqqud)
        hebrew_voweled: Voweled lookup table
        hebrew_consonants: Consonants-only lookup table

    Returns:
        List of matching Strong's numbers (e.g., ["H2896", "H2895"])
    """
    # Clean up the word
    clean_word = re.sub(r'[^\u0590-\u05FF]', '', hebrew_word)
    if not clean_word:
        return []

    # Try exact match first
    if clean_word in hebrew_voweled:
        return hebrew_voweled[clean_word]

    # Fall back to consonants only
    consonants = strip_niqqud(clean_word)
    if consonants in hebrew_consonants:
        return hebrew_consonants[consonants]

    return []


def parse_tbesg_file(filepath: Path, hebrew_voweled: dict, hebrew_consonants: dict) -> tuple[dict, dict]:
    """
    Parse the TBESG (Greek lexicon) file to extract:
    1. Explicit Greek→Hebrew mappings from dStrong column + uStrong column
    2. LXX-based mappings from "[in LXX ... for XXX]" patterns in definitions
    3. Greek metadata (lemma, transliteration, gloss)

    The file format is tab-separated:
    Column 0: eStrong (e.g., "G0108")
    Column 1: dStrong (e.g., "G0108 = the Greek of")
    Column 2: uStrong - contains Hebrew ref when col1 has "= the Greek of" (e.g., "H0795")
    Column 3: Greek word
    Column 4: Transliteration
    Column 5: Morph
    Column 6: Gloss
    Column 7: Meaning/Definition

    Returns:
        (greek_to_hebrew, greek_metadata)
    """
    # Track mappings with confidence levels
    greek_to_hebrew = defaultdict(lambda: {
        "primary": set(),
        "secondary": set(),
        "confidence": "",
        "notes": ""
    })
    greek_metadata = {}

    print(f"Parsing {filepath}...")

    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    data_started = False
    entries_parsed = 0

    # Statistics
    stats = {
        "explicit_mappings": 0,
        "lxx_chiefly_mappings": 0,
        "lxx_freq_mappings": 0,
        "lxx_simple_mappings": 0,
        "h_ref_mappings": 0,
        "hebrew_words_resolved": 0,
        "hebrew_words_unresolved": 0,
    }

    unresolved_words = set()

    # Patterns to detect cross-reference type in dStrong column
    crossref_patterns = [
        "= the Greek of",
        "= a Name of",
        "= the Aramaic of",
        "= a Hebrew of",
        "= the Hebrew of",
    ]

    for line_num, line in enumerate(lines, 1):
        # Skip header until we see the data delimiter
        if '==============' in line:
            data_started = True
            continue

        if not data_started or line.startswith('#') or not line.strip():
            continue

        # Skip lines that don't start with G (data lines)
        if not line.startswith('G'):
            continue

        # Parse tab-separated fields
        parts = line.split('\t')
        if len(parts) < 7:
            continue

        estrong = parts[0].strip()  # e.g., G0108
        dstrong = parts[1].strip()  # e.g., "G0108 = the Greek of"
        ustrong = parts[2].strip() if len(parts) > 2 else ""  # e.g., "H0795"
        greek = parts[3].strip() if len(parts) > 3 else ""
        xlit = parts[4].strip() if len(parts) > 4 else ""
        morph = parts[5].strip() if len(parts) > 5 else ""
        gloss = parts[6].strip() if len(parts) > 6 else ""
        meaning = parts[7].strip() if len(parts) > 7 else ""

        # Normalize the Strong's number
        greek_num = normalize_strongs(estrong)
        if not greek_num.startswith('G'):
            continue

        entries_parsed += 1

        # Store metadata
        if greek_num not in greek_metadata:
            greek_metadata[greek_num] = {
                "lemma": greek,
                "xlit": xlit,
                "gloss": gloss
            }

        # =================================================================
        # 1. EXPLICIT MAPPINGS (highest confidence)
        # =================================================================
        has_crossref_pattern = any(pattern in dstrong for pattern in crossref_patterns)
        if has_crossref_pattern and ustrong.startswith('H'):
            hebrew_num = normalize_strongs(ustrong)
            greek_to_hebrew[greek_num]["primary"].add(hebrew_num)
            if not greek_to_hebrew[greek_num]["confidence"]:
                greek_to_hebrew[greek_num]["confidence"] = "explicit"
            stats["explicit_mappings"] += 1

        # =================================================================
        # 2. LXX PATTERN MAPPINGS
        # =================================================================
        if meaning:
            # Find all [in LXX...] blocks
            lxx_blocks = LXX_BLOCK_PATTERN.findall(meaning)

            for block in lxx_blocks:
                # 2a. "chiefly for" - high confidence, primary
                chiefly_matches = LXX_CHIEFLY_FOR_PATTERN.findall(block)
                for hebrew_word in chiefly_matches:
                    strongs_nums = lookup_hebrew_strongs(
                        hebrew_word, hebrew_voweled, hebrew_consonants
                    )
                    if strongs_nums:
                        for h_num in strongs_nums[:3]:  # Limit to first 3 matches
                            greek_to_hebrew[greek_num]["primary"].add(h_num)
                        stats["lxx_chiefly_mappings"] += 1
                        stats["hebrew_words_resolved"] += 1
                        # Set confidence if not already set by explicit
                        if greek_to_hebrew[greek_num]["confidence"] in ("", "lxx_for"):
                            greek_to_hebrew[greek_num]["confidence"] = "lxx_chiefly"
                    else:
                        unresolved_words.add(hebrew_word)
                        stats["hebrew_words_unresolved"] += 1

                # 2b. "freq. for" - high confidence, primary
                freq_matches = LXX_FREQ_FOR_PATTERN.findall(block)
                for hebrew_word in freq_matches:
                    strongs_nums = lookup_hebrew_strongs(
                        hebrew_word, hebrew_voweled, hebrew_consonants
                    )
                    if strongs_nums:
                        for h_num in strongs_nums[:3]:
                            greek_to_hebrew[greek_num]["primary"].add(h_num)
                        stats["lxx_freq_mappings"] += 1
                        stats["hebrew_words_resolved"] += 1
                        if greek_to_hebrew[greek_num]["confidence"] in ("", "lxx_for"):
                            greek_to_hebrew[greek_num]["confidence"] = "lxx_chiefly"
                    else:
                        unresolved_words.add(hebrew_word)
                        stats["hebrew_words_unresolved"] += 1

                # 2c. Simple "for" - medium confidence, secondary
                simple_matches = LXX_SIMPLE_FOR_PATTERN.findall(block)
                for hebrew_word in simple_matches:
                    # Skip if already captured by chiefly/freq patterns
                    if hebrew_word in chiefly_matches or hebrew_word in freq_matches:
                        continue

                    strongs_nums = lookup_hebrew_strongs(
                        hebrew_word, hebrew_voweled, hebrew_consonants
                    )
                    if strongs_nums:
                        for h_num in strongs_nums[:3]:
                            # Add to secondary if not already primary
                            if h_num not in greek_to_hebrew[greek_num]["primary"]:
                                greek_to_hebrew[greek_num]["secondary"].add(h_num)
                        stats["lxx_simple_mappings"] += 1
                        stats["hebrew_words_resolved"] += 1
                        if not greek_to_hebrew[greek_num]["confidence"]:
                            greek_to_hebrew[greek_num]["confidence"] = "lxx_for"
                    else:
                        unresolved_words.add(hebrew_word)
                        stats["hebrew_words_unresolved"] += 1

            # =================================================================
            # 3. DIRECT H#### REFERENCES (low confidence)
            # =================================================================
            any_h_matches = ANY_HEBREW_REF_PATTERN.findall(meaning)
            for h_num_str in any_h_matches:
                hebrew_num = f"H{h_num_str}"
                # Only add if not already in primary
                if hebrew_num not in greek_to_hebrew[greek_num]["primary"]:
                    greek_to_hebrew[greek_num]["secondary"].add(hebrew_num)
                    stats["h_ref_mappings"] += 1
                    if not greek_to_hebrew[greek_num]["confidence"]:
                        greek_to_hebrew[greek_num]["confidence"] = "h_ref"

    # Print statistics
    print(f"  Parsed {entries_parsed} Greek entries")
    print(f"\n  Mapping Statistics:")
    print(f"    Explicit '= the Greek of' mappings: {stats['explicit_mappings']}")
    print(f"    LXX 'chiefly for' mappings: {stats['lxx_chiefly_mappings']}")
    print(f"    LXX 'freq. for' mappings: {stats['lxx_freq_mappings']}")
    print(f"    LXX simple 'for' mappings: {stats['lxx_simple_mappings']}")
    print(f"    Direct H#### reference mappings: {stats['h_ref_mappings']}")
    print(f"\n  Hebrew Word Resolution:")
    print(f"    Resolved to Strong's: {stats['hebrew_words_resolved']}")
    print(f"    Unresolved: {stats['hebrew_words_unresolved']}")

    if unresolved_words and len(unresolved_words) <= 20:
        print(f"\n  Sample unresolved Hebrew words:")
        for word in list(unresolved_words)[:10]:
            print(f"    - {word}")

    # Convert sets to sorted lists
    result = {}
    for g_num, data in greek_to_hebrew.items():
        if data["primary"] or data["secondary"]:
            result[g_num] = {
                "primary": sorted(list(data["primary"])),
                "secondary": sorted(list(data["secondary"])),
                "confidence": data["confidence"],
                "notes": data["notes"]
            }

    return result, greek_metadata


def build_reverse_mapping(greek_to_hebrew: dict) -> dict:
    """
    Build Hebrew→Greek mapping from Greek→Hebrew mapping.

    Returns:
        hebrew_to_greek dict
    """
    hebrew_to_greek = defaultdict(lambda: {"primary": set(), "secondary": set(), "notes": ""})

    for g_num, data in greek_to_hebrew.items():
        for h_num in data.get("primary", []):
            hebrew_to_greek[h_num]["primary"].add(g_num)
        for h_num in data.get("secondary", []):
            hebrew_to_greek[h_num]["secondary"].add(g_num)

    # Convert sets to sorted lists
    result = {}
    for h_num, data in hebrew_to_greek.items():
        result[h_num] = {
            "primary": sorted(list(data["primary"])),
            "secondary": sorted(list(data["secondary"])),
            "notes": data["notes"]
        }

    return result


def load_existing_strongs(strongs_path: Path) -> dict:
    """Load existing Strongs.json to get occurrence counts."""
    if not strongs_path.exists():
        return {}

    print(f"Loading {strongs_path}...")
    with open(strongs_path, 'r', encoding='utf-8') as f:
        strongs_data = json.load(f)

    # Build lookup by number
    lookup = {}
    for entry in strongs_data:
        num = entry.get("number", "")
        if num:
            lookup[num] = entry

    print(f"  Loaded {len(lookup)} Strong's entries")
    return lookup


def enrich_crossref_data(crossref: dict, metadata: dict, strongs_lookup: dict) -> dict:
    """
    Enrich cross-reference data with metadata (lemma, xlit, gloss, confidence).
    """
    enriched = {}

    for num, data in crossref.items():
        # Get metadata from parsed lexicon or Strongs.json
        meta = metadata.get(num, strongs_lookup.get(num, {}))

        enriched[num] = {
            "primary": data.get("primary", []),
            "secondary": data.get("secondary", []),
            "confidence": data.get("confidence", ""),
            "notes": data.get("notes", ""),
            "lemma": meta.get("lemma", ""),
            "xlit": meta.get("xlit", ""),
            "gloss": meta.get("gloss", meta.get("description", "")[:50] if meta.get("description") else "")
        }

    return enriched


def validate_mappings(
    greek_to_hebrew: dict,
    hebrew_metadata: dict,
    max_mappings_per_entry: int = 8
) -> tuple[dict, dict]:
    """
    Validate cross-reference mappings.

    Performs the following validations:
    1. Verifies all H#### numbers exist in TBESH
    2. Limits each Greek word to max_mappings_per_entry Hebrew mappings
    3. Filters out mappings to non-existent Strong's numbers

    Args:
        greek_to_hebrew: The Greek→Hebrew mappings to validate
        hebrew_metadata: Hebrew metadata from TBESH
        max_mappings_per_entry: Maximum mappings per Greek entry

    Returns:
        (validated_mappings, validation_stats)
    """
    validated = {}
    stats = {
        "total_entries": 0,
        "valid_entries": 0,
        "invalid_h_numbers": set(),
        "entries_truncated": 0,
        "mappings_removed": 0,
    }

    valid_h_numbers = set(hebrew_metadata.keys())

    for g_num, data in greek_to_hebrew.items():
        stats["total_entries"] += 1

        # Validate primary mappings
        valid_primary = []
        for h_num in data.get("primary", []):
            if h_num in valid_h_numbers:
                valid_primary.append(h_num)
            else:
                stats["invalid_h_numbers"].add(h_num)
                stats["mappings_removed"] += 1

        # Validate secondary mappings
        valid_secondary = []
        for h_num in data.get("secondary", []):
            if h_num in valid_h_numbers:
                valid_secondary.append(h_num)
            else:
                stats["invalid_h_numbers"].add(h_num)
                stats["mappings_removed"] += 1

        # Truncate if too many mappings
        total_mappings = len(valid_primary) + len(valid_secondary)
        if total_mappings > max_mappings_per_entry:
            stats["entries_truncated"] += 1
            # Keep primary mappings, truncate secondary
            remaining = max_mappings_per_entry - len(valid_primary)
            if remaining > 0:
                valid_secondary = valid_secondary[:remaining]
            else:
                valid_primary = valid_primary[:max_mappings_per_entry]
                valid_secondary = []

        if valid_primary or valid_secondary:
            validated[g_num] = {
                "primary": valid_primary,
                "secondary": valid_secondary,
                "confidence": data.get("confidence", ""),
                "notes": data.get("notes", "")
            }
            stats["valid_entries"] += 1

    # Convert set to list for JSON serialization
    stats["invalid_h_numbers"] = sorted(list(stats["invalid_h_numbers"]))

    return validated, stats


def main():
    """Main function to build cross-reference data."""
    print("=" * 60)
    print("Hebrew-Greek Cross-Reference Data Builder (Enhanced)")
    print("=" * 60)
    print()

    # Check for data files
    tbesg_path = DATA_DIR / "TBESG.txt"
    tbesh_path = DATA_DIR / "TBESH.txt"
    strongs_path = SCRIPT_DIR.parent / "app" / "data" / "Strongs.json"

    if not tbesg_path.exists():
        print(f"ERROR: Greek lexicon not found at {tbesg_path}")
        print("Please download TBESG from STEPBible:")
        print("  curl -L 'https://raw.githubusercontent.com/STEPBible/STEPBible-Data/master/Lexicons/TBESG%20-%20Translators%20Brief%20lexicon%20of%20Extended%20Strongs%20for%20Greek%20-%20STEPBible.org%20CC%20BY.txt' -o scripts/data/TBESG.txt")
        return 1

    if not tbesh_path.exists():
        print(f"ERROR: Hebrew lexicon not found at {tbesh_path}")
        print("Please download TBESH from STEPBible:")
        print("  curl -L 'https://raw.githubusercontent.com/STEPBible/STEPBible-Data/master/Lexicons/TBESH%20-%20Translators%20Brief%20lexicon%20of%20Extended%20Strongs%20for%20Hebrew%20-%20STEPBible.org%20CC%20BY.txt' -o scripts/data/TBESH.txt")
        return 1

    # =================================================================
    # Phase 1: Build Hebrew word lookup table
    # =================================================================
    print("\n" + "=" * 60)
    print("Phase 1: Building Hebrew Word Lookup Table")
    print("=" * 60)
    hebrew_voweled, hebrew_consonants, hebrew_metadata = build_hebrew_lookup(tbesh_path)

    # =================================================================
    # Phase 2: Parse TBESG with enhanced LXX extraction
    # =================================================================
    print("\n" + "=" * 60)
    print("Phase 2: Parsing Greek Lexicon with LXX Extraction")
    print("=" * 60)
    greek_to_hebrew, greek_metadata = parse_tbesg_file(
        tbesg_path, hebrew_voweled, hebrew_consonants
    )

    # =================================================================
    # Phase 4: Validate mappings
    # =================================================================
    print("\n" + "=" * 60)
    print("Phase 4: Validating Mappings")
    print("=" * 60)
    validated_g2h, validation_stats = validate_mappings(
        greek_to_hebrew, hebrew_metadata, max_mappings_per_entry=8
    )

    print(f"  Total entries: {validation_stats['total_entries']}")
    print(f"  Valid entries: {validation_stats['valid_entries']}")
    print(f"  Entries truncated (>8 mappings): {validation_stats['entries_truncated']}")
    print(f"  Mappings to invalid H numbers removed: {validation_stats['mappings_removed']}")

    if validation_stats['invalid_h_numbers']:
        print(f"  Sample invalid H numbers: {validation_stats['invalid_h_numbers'][:5]}")

    # Use validated mappings
    greek_to_hebrew = validated_g2h

    # Load existing Strongs.json for additional metadata
    strongs_lookup = load_existing_strongs(strongs_path)

    # Build reverse mapping
    print("\n" + "=" * 60)
    print("Building Reverse Mapping (Hebrew→Greek)")
    print("=" * 60)
    hebrew_to_greek = build_reverse_mapping(greek_to_hebrew)
    print(f"  Created {len(hebrew_to_greek)} H→G entries")

    # Combine metadata
    all_metadata = {**hebrew_metadata, **greek_metadata}

    # Enrich with metadata
    print("\nEnriching cross-reference data with metadata...")
    enriched_g2h = enrich_crossref_data(greek_to_hebrew, all_metadata, strongs_lookup)
    enriched_h2g = enrich_crossref_data(hebrew_to_greek, all_metadata, strongs_lookup)

    # Count confidence levels
    confidence_counts = defaultdict(int)
    for data in greek_to_hebrew.values():
        conf = data.get("confidence", "unknown")
        if conf:
            confidence_counts[conf] += 1

    # Build output structure
    output = {
        "metadata": {
            "source": "STEPBible TBESG/TBESH Lexicons (CC BY 4.0)",
            "source_url": "https://github.com/STEPBible/STEPBible-Data",
            "version": "2.0",
            "created": datetime.now().strftime("%Y-%m-%d"),
            "description": "Hebrew-Greek LXX alignment mappings derived from STEPBible lexicon data",
            "confidence_levels": {
                "explicit": "Direct '= the Greek of H####' mapping (highest confidence)",
                "lxx_chiefly": "LXX 'chiefly for' or 'freq. for' patterns (high confidence)",
                "lxx_for": "LXX simple 'for' patterns (medium confidence)",
                "h_ref": "Direct H#### reference in definition (low confidence)"
            }
        },
        "hebrew_to_greek": enriched_h2g,
        "greek_to_hebrew": enriched_g2h,
        "statistics": {
            "total_hebrew_mapped": len(hebrew_to_greek),
            "total_greek_mapped": len(greek_to_hebrew),
            "total_mappings": sum(
                len(d.get("primary", [])) + len(d.get("secondary", []))
                for d in greek_to_hebrew.values()
            ),
            "primary_mappings": sum(
                len(d.get("primary", []))
                for d in greek_to_hebrew.values()
            ),
            "secondary_mappings": sum(
                len(d.get("secondary", []))
                for d in greek_to_hebrew.values()
            ),
            "by_confidence": dict(confidence_counts)
        }
    }

    # Write output
    print(f"\nWriting output to {OUTPUT_PATH}...")
    os.makedirs(OUTPUT_PATH.parent, exist_ok=True)

    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # Print summary
    file_size = OUTPUT_PATH.stat().st_size / 1024
    print(f"\nDone! Created {OUTPUT_PATH.name} ({file_size:.1f} KB)")
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Hebrew→Greek mappings: {output['statistics']['total_hebrew_mapped']}")
    print(f"  Greek→Hebrew mappings: {output['statistics']['total_greek_mapped']}")
    print(f"  Total cross-references: {output['statistics']['total_mappings']}")
    print(f"    - Primary: {output['statistics']['primary_mappings']}")
    print(f"    - Secondary: {output['statistics']['secondary_mappings']}")
    print()
    print("  By confidence level:")
    for conf, count in sorted(confidence_counts.items()):
        print(f"    - {conf}: {count}")

    # Estimate coverage
    # Typical Hebrew lexicon has ~8,700 entries
    hebrew_coverage = (len(hebrew_to_greek) / 8700) * 100
    print(f"\n  Estimated Hebrew vocabulary coverage: ~{hebrew_coverage:.1f}%")

    # Show some example mappings for verification
    print()
    print("=" * 60)
    print("VERIFICATION EXAMPLES")
    print("=" * 60)

    # Check for specific expected mappings
    test_cases = [
        ("G18", "H2896", "ἀγαθός (good) → טוֹב"),
        ("G25", "H157", "ἀγαπάω (love) → אָהֵב"),
        ("G32", "H4397", "ἄγγελος (angel) → מַלְאָךְ"),
    ]

    for g_num, expected_h, description in test_cases:
        if g_num in greek_to_hebrew:
            data = greek_to_hebrew[g_num]
            all_h = data.get("primary", []) + data.get("secondary", [])
            if expected_h in all_h:
                print(f"  ✓ {description}")
            else:
                print(f"  ✗ {description} - {expected_h} not found (got: {all_h[:3]})")
        else:
            print(f"  ✗ {description} - {g_num} not found")

    # Show some sample mappings
    print()
    print("Sample Hebrew→Greek mappings:")
    sample_h = list(hebrew_to_greek.items())[:5]
    for h_num, data in sample_h:
        primaries = ", ".join(data.get("primary", [])[:3])
        meta = hebrew_metadata.get(h_num, {})
        gloss = meta.get("gloss", "")[:20]
        print(f"  {h_num} ({gloss}) → {primaries}")

    print()
    print("Sample Greek→Hebrew mappings:")
    sample_g = list(greek_to_hebrew.items())[:5]
    for g_num, data in sample_g:
        primaries = ", ".join(data.get("primary", [])[:3])
        meta = greek_metadata.get(g_num, {})
        gloss = meta.get("gloss", "")[:20]
        print(f"  {g_num} ({gloss}) → {primaries}")

    return 0


if __name__ == '__main__':
    exit(main())
