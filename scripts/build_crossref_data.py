#!/usr/bin/env python3
"""
Build Hebrew-Greek cross-reference JSON from STEP Bible lexicon data.

This script parses TBESG (Greek lexicon) and TBESH (Hebrew lexicon) files
to extract bidirectional Hebrew ↔ Greek Strong's number mappings.

Data sources:
- TBESG: Contains explicit "= the Greek of H####" mappings
- TBESG: Contains implicit "[in LXX for XXX ;]" Hebrew word references in definitions
- TBESH: Contains Hebrew lexicon data

Run once to generate app/static/hebrew_greek_crossref.json
"""

import json
import re
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# Paths
SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR / "data"
OUTPUT_PATH = SCRIPT_DIR.parent / "app" / "static" / "hebrew_greek_crossref.json"

# Regex patterns
# Pattern for explicit Greek→Hebrew mapping in dStrong column
# e.g., "G0002 = the Greek of H0175" or "G0005 = a Name of H3068G"
EXPLICIT_CROSSREF_PATTERN = re.compile(
    r'= (?:the Greek of|a Name of|the Aramaic of|a Hebrew of)\s+(H\d+[A-Z]?)'
)

# Pattern for implicit Hebrew references in "[in LXX ... for XXX ;]" sections
# e.g., "[in LXX chiefly for טוֹב ;]" or "[in LXX for אהב ;]"
LXX_HEBREW_PATTERN = re.compile(
    r'\[in LXX[^\]]*?(?:for|chiefly for|freq\. for)\s+([^\];,]+)'
)

# Pattern to extract Hebrew Strong's from reference like "(יטב hi.)" or "(H1234)"
HEBREW_IN_PARENS_PATTERN = re.compile(r'\(H(\d+)\)')

# Pattern for any H#### reference in text (bracketed or standalone)
ANY_HEBREW_REF_PATTERN = re.compile(r'\bH(\d{3,5})\b')

# Pattern for Strong's numbers
STRONGS_PATTERN = re.compile(r'^([HG]\d+)')


def normalize_strongs(strongs: str) -> str:
    """Normalize Strong's number by removing suffix letters."""
    match = STRONGS_PATTERN.match(strongs.strip())
    if match:
        return match.group(1)
    return strongs.strip()


def parse_tbesg_file(filepath: Path) -> tuple[dict, dict]:
    """
    Parse the TBESG (Greek lexicon) file to extract:
    1. Explicit Greek→Hebrew mappings from dStrong column + uStrong column
    2. Greek metadata (lemma, transliteration, gloss)

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
        (greek_to_hebrew_explicit, greek_metadata)
    """
    greek_to_hebrew = defaultdict(lambda: {"primary": set(), "secondary": set(), "notes": ""})
    greek_metadata = {}

    print(f"Parsing {filepath}...")

    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    data_started = False
    entries_parsed = 0
    explicit_mappings = 0
    implicit_mappings = 0

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

        # 1. Check for explicit mapping: dStrong contains crossref pattern and uStrong has Hebrew ref
        has_crossref_pattern = any(pattern in dstrong for pattern in crossref_patterns)
        if has_crossref_pattern and ustrong.startswith('H'):
            hebrew_num = normalize_strongs(ustrong)
            greek_to_hebrew[greek_num]["primary"].add(hebrew_num)
            explicit_mappings += 1

        # 2. Check for implicit mappings in meaning/definition field
        # e.g., "[in LXX chiefly for טוֹב ;]" or "[in LXX for אהב ;]"
        if meaning:
            lxx_matches = LXX_HEBREW_PATTERN.findall(meaning)
            for hebrew_text in lxx_matches:
                # Check if there's a Hebrew Strong's reference in parentheses
                h_match = HEBREW_IN_PARENS_PATTERN.search(hebrew_text)
                if h_match:
                    hebrew_num = f"H{h_match.group(1)}"
                    if hebrew_num not in greek_to_hebrew[greek_num]["primary"]:
                        greek_to_hebrew[greek_num]["secondary"].add(hebrew_num)
                        implicit_mappings += 1

            # 3. Also check for any H#### references in the meaning text (bracketed or standalone)
            # This catches cases like "[H609]" or references to H numbers in definitions
            any_h_matches = ANY_HEBREW_REF_PATTERN.findall(meaning)
            for h_num_str in any_h_matches:
                hebrew_num = f"H{h_num_str}"
                if hebrew_num not in greek_to_hebrew[greek_num]["primary"]:
                    greek_to_hebrew[greek_num]["secondary"].add(hebrew_num)
                    implicit_mappings += 1

    print(f"  Parsed {entries_parsed} Greek entries")
    print(f"  Found {explicit_mappings} explicit G→H mappings")
    print(f"  Found {implicit_mappings} implicit G→H mappings from definitions")

    # Convert sets to lists
    result = {}
    for g_num, data in greek_to_hebrew.items():
        if data["primary"] or data["secondary"]:
            result[g_num] = {
                "primary": sorted(list(data["primary"])),
                "secondary": sorted(list(data["secondary"])),
                "notes": data["notes"]
            }

    return result, greek_metadata


def parse_tbesh_file(filepath: Path) -> dict:
    """
    Parse the TBESH (Hebrew lexicon) file to extract Hebrew metadata.

    Returns:
        hebrew_metadata dict
    """
    hebrew_metadata = {}

    print(f"Parsing {filepath}...")

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
        dstrong = parts[1].strip()
        ustrong = parts[2].strip() if len(parts) > 2 else ""
        hebrew = parts[3].strip() if len(parts) > 3 else ""
        xlit = parts[4].strip() if len(parts) > 4 else ""
        morph = parts[5].strip() if len(parts) > 5 else ""
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

    print(f"  Parsed {entries_parsed} Hebrew entries")

    return hebrew_metadata


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
    Enrich cross-reference data with metadata (lemma, xlit, gloss).
    """
    enriched = {}

    for num, data in crossref.items():
        # Get metadata from parsed lexicon or Strongs.json
        meta = metadata.get(num, strongs_lookup.get(num, {}))

        enriched[num] = {
            "primary": data.get("primary", []),
            "secondary": data.get("secondary", []),
            "notes": data.get("notes", ""),
            "lemma": meta.get("lemma", ""),
            "xlit": meta.get("xlit", ""),
            "gloss": meta.get("gloss", meta.get("description", "")[:50] if meta.get("description") else "")
        }

    return enriched


def main():
    """Main function to build cross-reference data."""
    print("=" * 60)
    print("Hebrew-Greek Cross-Reference Data Builder")
    print("=" * 60)
    print()

    # Check for data files
    tbesg_path = DATA_DIR / "TBESG.txt"
    tbesh_path = DATA_DIR / "TBESH.txt"
    strongs_path = SCRIPT_DIR.parent / "app" / "static" / "Strongs.json"

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

    # Parse lexicon files
    greek_to_hebrew, greek_metadata = parse_tbesg_file(tbesg_path)
    hebrew_metadata = parse_tbesh_file(tbesh_path)

    # Load existing Strongs.json for additional metadata
    strongs_lookup = load_existing_strongs(strongs_path)

    # Build reverse mapping
    print("\nBuilding Hebrew→Greek mapping...")
    hebrew_to_greek = build_reverse_mapping(greek_to_hebrew)
    print(f"  Created {len(hebrew_to_greek)} H→G entries")

    # Combine metadata
    all_metadata = {**hebrew_metadata, **greek_metadata}

    # Enrich with metadata
    print("\nEnriching cross-reference data with metadata...")
    enriched_g2h = enrich_crossref_data(greek_to_hebrew, all_metadata, strongs_lookup)
    enriched_h2g = enrich_crossref_data(hebrew_to_greek, all_metadata, strongs_lookup)

    # Build output structure
    output = {
        "metadata": {
            "source": "STEPBible TBESG/TBESH Lexicons (CC BY 4.0)",
            "source_url": "https://github.com/STEPBible/STEPBible-Data",
            "version": "1.0",
            "created": datetime.now().strftime("%Y-%m-%d"),
            "description": "Hebrew-Greek LXX alignment mappings derived from STEPBible lexicon data"
        },
        "hebrew_to_greek": enriched_h2g,
        "greek_to_hebrew": enriched_g2h,
        "statistics": {
            "total_hebrew_mapped": len(hebrew_to_greek),
            "total_greek_mapped": len(greek_to_hebrew),
            "total_mappings": sum(
                len(d.get("primary", [])) + len(d.get("secondary", []))
                for d in greek_to_hebrew.values()
            )
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
    print("Summary:")
    print(f"  Hebrew→Greek mappings: {output['statistics']['total_hebrew_mapped']}")
    print(f"  Greek→Hebrew mappings: {output['statistics']['total_greek_mapped']}")
    print(f"  Total cross-references: {output['statistics']['total_mappings']}")
    print()

    # Show some examples
    print("Sample Hebrew→Greek mappings:")
    sample_h = list(hebrew_to_greek.items())[:5]
    for h_num, data in sample_h:
        primaries = ", ".join(data.get("primary", [])[:3])
        print(f"  {h_num} → {primaries}")

    print()
    print("Sample Greek→Hebrew mappings:")
    sample_g = list(greek_to_hebrew.items())[:5]
    for g_num, data in sample_g:
        primaries = ", ".join(data.get("primary", [])[:3])
        print(f"  {g_num} → {primaries}")

    return 0


if __name__ == '__main__':
    exit(main())
