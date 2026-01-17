# Hebrew-Greek (Septuagint) Cross-Reference Implementation Plan

## Executive Summary

This document outlines the implementation of Hebrew-Greek cross-referencing in the Bible transliteration Flask app. The feature will show users the LXX (Septuagint) Greek equivalents when studying Hebrew words, and vice versa.

---

## 1. DATA ACQUISITION AND STORAGE

### 1.1 Data Source: CATSS Database

**Recommended Source**: CATSS (Computer-Assisted Tools for Septuagint Studies)
- **Repository**: https://github.com/openscriptures/GreekResources (or CCAT archives)
- **Format**: Parallel text alignment files
- **Coverage**: Complete Hebrew-Greek word alignment for the Old Testament

**Alternative Sources**:
1. **OpenScriptures Lexicon Data**: https://github.com/openscriptures/HebrewLexicon
2. **STEP Bible Data**: https://github.com/STEPBible/STEPBible-Data (contains TBESH - Tyndale Brief lexicon with Septuagint mappings)
3. **Groves-Wheeler Westminster Hebrew Morphology**: Academic-quality with LXX links

**Recommended Approach**: Use **STEP Bible's TBESH data** (Tyndale Brief lexicon entries for Strongs Hebrew) as the primary source because:
- It's openly licensed (CC BY-NC 4.0)
- Already includes Strongs-to-Strongs mappings
- Well-maintained and documented
- Specifically designed for digital Bible tools

### 1.2 Data Extraction Process

```bash
# Download STEP Bible data
curl -O https://raw.githubusercontent.com/STEPBible/STEPBible-Data/master/TBESH%20-%20Tyndale%20Brief%20lexicon%20of%20Extended%20Strongs%20for%20Hebrew.txt

# Or CATSS parallel alignment
# (requires parsing CATSS format which is more complex)
```

### 1.3 Storage Format

Create a new JSON file: `app/static/hebrew_greek_crossref.json`

```json
{
  "metadata": {
    "source": "STEP Bible TBESH + Manual Curation",
    "version": "1.0",
    "created": "2025-01-17",
    "description": "Hebrew-Greek LXX alignment mappings"
  },
  "hebrew_to_greek": {
    "H7225": {
      "primary": ["G746"],
      "secondary": ["G4413"],
      "notes": "Usually 'arche' (beginning), occasionally 'protos' (first)"
    },
    "H430": {
      "primary": ["G2316"],
      "secondary": ["G2304"],
      "notes": "Elohim -> theos (God)"
    },
    "H1254": {
      "primary": ["G2936", "G4160"],
      "secondary": [],
      "notes": "bara (create) -> ktizo or poieo"
    }
  },
  "greek_to_hebrew": {
    "G746": {
      "primary": ["H7225"],
      "secondary": ["H6924", "H1"],
      "notes": "arche usually translates reshit"
    },
    "G2316": {
      "primary": ["H430", "H410"],
      "secondary": ["H3068"],
      "notes": "theos translates elohim, el, sometimes YHWH"
    }
  },
  "statistics": {
    "total_hebrew_entries": 8674,
    "total_greek_entries": 5624,
    "mapped_hebrew": 3500,
    "mapped_greek": 3200
  }
}
```

**Key Design Decisions**:
1. **Bidirectional storage**: Both H→G and G→H for fast lookups (no need to scan inverse)
2. **Primary vs Secondary**: Primary = most common LXX translation; Secondary = less common alternatives
3. **Notes field**: Brief context for why multiple mappings exist (helps users understand)
4. **Lightweight**: Single JSON file loaded at startup (similar to existing architecture)

### 1.4 Data Processing Script

Create: `scripts/build_crossref_data.py`

```python
#!/usr/bin/env python3
"""
Build Hebrew-Greek cross-reference JSON from source data.
Run once during setup, or when updating source data.
"""

import json
import re
from collections import defaultdict
from pathlib import Path

def parse_tbesh_file(filepath):
    """Parse STEP Bible TBESH format."""
    hebrew_to_greek = defaultdict(lambda: {"primary": [], "secondary": [], "notes": ""})

    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            if line.startswith('#') or not line.strip():
                continue

            # TBESH format: StrongH<tab>...<tab>LXX:G####<tab>...
            parts = line.split('\t')
            if len(parts) < 2:
                continue

            hebrew_num = parts[0].strip()  # e.g., "H7225"

            # Find LXX column (contains Greek Strongs)
            for part in parts:
                if 'LXX:' in part or part.startswith('G'):
                    greek_matches = re.findall(r'G\d+', part)
                    if greek_matches:
                        # First match is primary
                        hebrew_to_greek[hebrew_num]["primary"].extend(greek_matches[:1])
                        hebrew_to_greek[hebrew_num]["secondary"].extend(greek_matches[1:])

    return dict(hebrew_to_greek)

def build_reverse_mapping(hebrew_to_greek):
    """Build Greek→Hebrew from Hebrew→Greek."""
    greek_to_hebrew = defaultdict(lambda: {"primary": [], "secondary": [], "notes": ""})

    for h_num, data in hebrew_to_greek.items():
        for g_num in data["primary"]:
            if h_num not in greek_to_hebrew[g_num]["primary"]:
                greek_to_hebrew[g_num]["primary"].append(h_num)
        for g_num in data["secondary"]:
            if h_num not in greek_to_hebrew[g_num]["secondary"]:
                greek_to_hebrew[g_num]["secondary"].append(h_num)

    return dict(greek_to_hebrew)

def main():
    # Parse source data
    hebrew_to_greek = parse_tbesh_file('data/TBESH.txt')
    greek_to_hebrew = build_reverse_mapping(hebrew_to_greek)

    # Build output
    output = {
        "metadata": {
            "source": "STEP Bible TBESH",
            "version": "1.0",
            "created": "2025-01-17"
        },
        "hebrew_to_greek": hebrew_to_greek,
        "greek_to_hebrew": greek_to_hebrew,
        "statistics": {
            "mapped_hebrew": len(hebrew_to_greek),
            "mapped_greek": len(greek_to_hebrew)
        }
    }

    # Write output
    output_path = Path('app/static/hebrew_greek_crossref.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"Created {output_path} with {len(hebrew_to_greek)} Hebrew entries")

if __name__ == '__main__':
    main()
```

---

## 2. DATABASE/DATA SCHEMA

### 2.1 Cross-Reference Data Structure

```
hebrew_greek_crossref.json
├── metadata
│   ├── source: string
│   ├── version: string
│   └── created: string (ISO date)
├── hebrew_to_greek
│   └── {H####}: { primary: [G####...], secondary: [G####...], notes: string }
├── greek_to_hebrew
│   └── {G####}: { primary: [H####...], secondary: [H####...], notes: string }
└── statistics
    ├── total_hebrew_entries: number
    ├── total_greek_entries: number
    ├── mapped_hebrew: number
    └── mapped_greek: number
```

### 2.2 Memory Loading Strategy

Similar to existing `Strongs.json` loading in `routes.py`:

```python
# In app/routes.py - Add to startup loading

# Load cross-reference data
crossref_path = os.path.join(app.static_folder, 'hebrew_greek_crossref.json')
if os.path.exists(crossref_path):
    with open(crossref_path, 'r', encoding='utf-8') as f:
        crossref_data = json.load(f)
    hebrew_to_greek = crossref_data.get('hebrew_to_greek', {})
    greek_to_hebrew = crossref_data.get('greek_to_hebrew', {})
else:
    hebrew_to_greek = {}
    greek_to_hebrew = {}
```

### 2.3 Integration with Existing Strongs.json

**Option A (Recommended)**: Keep separate files
- Pro: Clean separation, easier to update crossref data independently
- Pro: No changes to existing Strongs.json structure
- Con: Two lookups instead of one

**Option B**: Merge into Strongs.json
- Pro: Single lookup
- Con: Larger file, harder to maintain
- Con: Would need to modify existing data structure

**Decision**: Use Option A (separate file) for cleaner architecture.

---

## 3. API ENDPOINTS

### 3.1 New Endpoints

#### `GET /api/crossref/<strong_number>`

Get cross-references for a single Strong's number.

**Request**:
```
GET /api/crossref/H7225
```

**Response**:
```json
{
  "strong": "H7225",
  "language": "hebrew",
  "cross_refs": {
    "primary": [
      {
        "strong": "G746",
        "lemma": "ἀρχή",
        "xlit": "arche",
        "gloss": "beginning",
        "occurrences": 55
      }
    ],
    "secondary": [
      {
        "strong": "G4413",
        "lemma": "πρῶτος",
        "xlit": "protos",
        "gloss": "first",
        "occurrences": 96
      }
    ]
  },
  "notes": "Usually 'arche' (beginning), occasionally 'protos' (first)"
}
```

**Implementation** (`routes.py`):

```python
@app.route('/api/crossref/<strong_number>')
def get_crossref(strong_number):
    """Get cross-references for a Strong's number."""
    strong_number = strong_number.upper()

    if not re.match(r'^[HG]\d+$', strong_number):
        return jsonify({'error': 'Invalid Strong\'s number format'}), 400

    # Determine direction
    if strong_number.startswith('H'):
        source_map = hebrew_to_greek
        language = 'hebrew'
    else:
        source_map = greek_to_hebrew
        language = 'greek'

    crossref = source_map.get(strong_number)
    if not crossref:
        return jsonify({
            'strong': strong_number,
            'language': language,
            'cross_refs': {'primary': [], 'secondary': []},
            'notes': ''
        })

    # Enrich with Strong's metadata
    def enrich_strong(sn):
        entry = strongs_lookup.get(sn, {})
        return {
            'strong': sn,
            'lemma': entry.get('lemma', ''),
            'xlit': entry.get('xlit', ''),
            'gloss': entry.get('description', '')[:50] + '...' if entry.get('description') else '',
            'occurrences': global_strongs_counts.get(sn, 0)
        }

    return jsonify({
        'strong': strong_number,
        'language': language,
        'cross_refs': {
            'primary': [enrich_strong(sn) for sn in crossref.get('primary', [])],
            'secondary': [enrich_strong(sn) for sn in crossref.get('secondary', [])]
        },
        'notes': crossref.get('notes', '')
    })
```

#### `GET /api/crossref/batch`

Get cross-references for multiple Strong's numbers (for dictionary editor).

**Request**:
```
GET /api/crossref/batch?strongs=H7225,H430,G2316
```

**Response**:
```json
{
  "results": {
    "H7225": { "primary": ["G746"], "secondary": ["G4413"] },
    "H430": { "primary": ["G2316"], "secondary": ["G2304"] },
    "G2316": { "primary": ["H430", "H410"], "secondary": ["H3068"] }
  }
}
```

**Implementation**:

```python
@app.route('/api/crossref/batch')
def get_crossref_batch():
    """Get cross-references for multiple Strong's numbers."""
    strongs_param = request.args.get('strongs', '')
    strongs_list = [s.strip().upper() for s in strongs_param.split(',') if s.strip()]

    if len(strongs_list) > 100:
        return jsonify({'error': 'Maximum 100 Strong\'s numbers per request'}), 400

    results = {}
    for sn in strongs_list:
        if not re.match(r'^[HG]\d+$', sn):
            continue

        source_map = hebrew_to_greek if sn.startswith('H') else greek_to_hebrew
        crossref = source_map.get(sn, {'primary': [], 'secondary': []})
        results[sn] = {
            'primary': crossref.get('primary', []),
            'secondary': crossref.get('secondary', [])
        }

    return jsonify({'results': results})
```

### 3.2 Modified Endpoints

#### Enhance `/heatmap` route

Add cross-reference data to heatmap context:

```python
@app.route('/heatmap')
def heatmap():
    strong = request.args.get('strong', '').upper()
    show_crossrefs = request.args.get('show_crossrefs', 'false') == 'true'

    # Existing heatmap generation
    heatmap_data = generate_heatmap(strong)

    # Get cross-references
    source_map = hebrew_to_greek if strong.startswith('H') else greek_to_hebrew
    crossrefs = source_map.get(strong, {'primary': [], 'secondary': []})

    # Optionally generate heatmaps for cross-referenced words
    crossref_heatmaps = {}
    if show_crossrefs:
        for ref_strong in crossrefs.get('primary', [])[:3]:  # Limit to top 3
            crossref_heatmaps[ref_strong] = generate_heatmap(ref_strong)

    return render_template('heatmap.html',
        strong=strong,
        heatmap_data=heatmap_data,
        crossrefs=crossrefs,
        crossref_heatmaps=crossref_heatmaps,
        show_crossrefs=show_crossrefs,
        # ... existing context
    )
```

---

## 4. FRONTEND CHANGES

### 4.1 Strong's Popup Enhancement

**File**: `app/templates/home.html`

Add cross-reference section to popup:

```html
<!-- Add inside .word-popup after .word-popup__info -->
<div class="word-popup__crossref" id="word-popup-crossref" style="display: none;">
  <div class="word-popup__crossref-divider"></div>
  <div class="word-popup__crossref-header">
    <span class="word-popup__crossref-icon">⇄</span>
    <span id="crossref-label">LXX Equivalents:</span>
  </div>
  <div class="word-popup__crossref-list" id="crossref-list">
    <!-- Populated by JavaScript -->
  </div>
</div>
```

**File**: `app/static/js/chapter-view.js`

Add cross-reference fetching and display:

```javascript
// Add after existing popup population logic

async function loadCrossReferences(strongNumber) {
  const crossrefSection = document.getElementById('word-popup-crossref');
  const crossrefList = document.getElementById('crossref-list');
  const crossrefLabel = document.getElementById('crossref-label');

  try {
    const response = await fetch(`/api/crossref/${strongNumber}`);
    const data = await response.json();

    const allRefs = [...(data.cross_refs.primary || []), ...(data.cross_refs.secondary || [])];

    if (allRefs.length === 0) {
      crossrefSection.style.display = 'none';
      return;
    }

    // Set label based on language
    crossrefLabel.textContent = data.language === 'hebrew'
      ? 'LXX typically uses:'
      : 'Hebrew equivalent:';

    // Build list HTML
    crossrefList.innerHTML = allRefs.slice(0, 4).map((ref, idx) => `
      <div class="word-popup__crossref-item ${idx >= data.cross_refs.primary.length ? 'secondary' : 'primary'}">
        <a href="#" class="crossref-link" data-strong="${ref.strong}">
          <span class="crossref-strong">${ref.strong}</span>
          <span class="crossref-lemma">${ref.lemma}</span>
          <span class="crossref-xlit">(${ref.xlit})</span>
        </a>
      </div>
    `).join('');

    // Add click handlers
    crossrefList.querySelectorAll('.crossref-link').forEach(link => {
      link.addEventListener('click', (e) => {
        e.preventDefault();
        const targetStrong = link.dataset.strong;
        // Navigate to that Strong's entry (could open new popup or go to heatmap)
        window.location.href = `/heatmap?strong=${targetStrong}&from_crossref=1`;
      });
    });

    crossrefSection.style.display = 'block';

  } catch (err) {
    console.error('Failed to load cross-references:', err);
    crossrefSection.style.display = 'none';
  }
}

// Call from showWordPopup function
function showWordPopup(event, token) {
  // ... existing popup logic ...

  const strongNumber = token.dataset.strongs;
  loadCrossReferences(strongNumber);
}
```

**File**: `app/static/css/main.css`

Add styles:

```css
/* Cross-reference section in popup */
.word-popup__crossref {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid #e0e0e0;
}

.word-popup__crossref-header {
  font-size: 11px;
  color: #666;
  margin-bottom: 4px;
  display: flex;
  align-items: center;
  gap: 4px;
}

.word-popup__crossref-icon {
  font-size: 12px;
}

.word-popup__crossref-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.word-popup__crossref-item {
  font-size: 12px;
}

.word-popup__crossref-item.secondary {
  opacity: 0.7;
}

.crossref-link {
  display: flex;
  align-items: center;
  gap: 4px;
  color: #1a73e8;
  text-decoration: none;
  padding: 2px 4px;
  border-radius: 3px;
  transition: background-color 0.15s;
}

.crossref-link:hover {
  background-color: #e8f0fe;
}

.crossref-strong {
  font-weight: 500;
  font-family: monospace;
}

.crossref-lemma {
  font-family: "SBL Hebrew", "SBL Greek", serif;
}

.crossref-xlit {
  color: #666;
  font-style: italic;
}
```

### 4.2 Heatmap Enhancement

**File**: `app/templates/heatmap.html`

Add cross-reference toggle and display:

```html
<!-- Add after existing heatmap header -->
<div class="heatmap-controls">
  <h2>Word Frequency: {{ strong }}</h2>

  {% if crossrefs and (crossrefs.primary or crossrefs.secondary) %}
  <div class="heatmap-crossref-toggle">
    <label class="toggle-label">
      <input type="checkbox" id="show-crossrefs-toggle"
             {% if show_crossrefs %}checked{% endif %}
             onchange="toggleCrossrefHeatmaps(this.checked)">
      <span class="toggle-text">
        {% if strong.startswith('H') %}
          Show LXX equivalents
        {% else %}
          Show Hebrew sources
        {% endif %}
      </span>
    </label>
  </div>
  {% endif %}
</div>

<!-- Cross-reference info panel -->
{% if crossrefs and (crossrefs.primary or crossrefs.secondary) %}
<div class="heatmap-crossref-info">
  <span class="crossref-info-label">
    {% if strong.startswith('H') %}LXX translations:{% else %}Hebrew sources:{% endif %}
  </span>
  {% for ref in crossrefs.primary %}
  <a href="/heatmap?strong={{ ref }}&show_crossrefs={{ 'true' if show_crossrefs else 'false' }}"
     class="crossref-chip primary">
    {{ ref }}
  </a>
  {% endfor %}
  {% for ref in crossrefs.secondary[:2] %}
  <a href="/heatmap?strong={{ ref }}&show_crossrefs={{ 'true' if show_crossrefs else 'false' }}"
     class="crossref-chip secondary">
    {{ ref }}
  </a>
  {% endfor %}
</div>
{% endif %}

<!-- Cross-reference heatmaps (when toggle is on) -->
{% if show_crossrefs and crossref_heatmaps %}
<div class="crossref-heatmaps-container">
  {% for ref_strong, ref_heatmap in crossref_heatmaps.items() %}
  <div class="crossref-heatmap-section">
    <h3 class="crossref-heatmap-title">
      <a href="/heatmap?strong={{ ref_strong }}">{{ ref_strong }}</a>
      <span class="crossref-heatmap-subtitle">
        ({{ strongs_lookup.get(ref_strong, {}).get('xlit', '') }})
      </span>
    </h3>
    <!-- Render mini heatmap table for this cross-ref -->
    {{ render_heatmap_table(ref_heatmap, ref_strong) }}
  </div>
  {% endfor %}
</div>
{% endif %}
```

**JavaScript** (add to heatmap.html or separate file):

```javascript
function toggleCrossrefHeatmaps(show) {
  const url = new URL(window.location.href);
  url.searchParams.set('show_crossrefs', show ? 'true' : 'false');
  window.location.href = url.toString();
}
```

**CSS additions**:

```css
/* Heatmap cross-reference controls */
.heatmap-controls {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 12px;
}

.heatmap-crossref-toggle {
  display: flex;
  align-items: center;
}

.toggle-label {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  font-size: 14px;
}

.heatmap-crossref-info {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: #f5f5f5;
  border-radius: 6px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.crossref-info-label {
  font-size: 13px;
  color: #666;
}

.crossref-chip {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 16px;
  font-size: 12px;
  font-family: monospace;
  text-decoration: none;
  transition: all 0.15s;
}

.crossref-chip.primary {
  background: #e3f2fd;
  color: #1565c0;
}

.crossref-chip.secondary {
  background: #f5f5f5;
  color: #666;
}

.crossref-chip:hover {
  transform: translateY(-1px);
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.crossref-heatmaps-container {
  margin-top: 24px;
  padding-top: 24px;
  border-top: 2px solid #e0e0e0;
}

.crossref-heatmap-section {
  margin-bottom: 24px;
}

.crossref-heatmap-title {
  font-size: 16px;
  margin-bottom: 8px;
}

.crossref-heatmap-subtitle {
  font-weight: normal;
  color: #666;
  font-style: italic;
}
```

### 4.3 Dictionary Editor Enhancement

**File**: `app/templates/edit_dict.html`

Add cross-reference column:

```html
<!-- Modify the table header -->
<thead>
  <tr>
    <th class="dict-col-checkbox"><input type="checkbox" id="select-all"></th>
    <th class="dict-col-strong">Strong's #</th>
    <th class="dict-col-translations">Translations</th>
    <th class="dict-col-crossref">LXX/Hebrew Links</th>  <!-- NEW -->
    <th class="dict-col-color">Color</th>
    <th class="dict-col-actions">Actions</th>
  </tr>
</thead>

<!-- Modify entry template -->
<template id="dict-entry-template">
  <tr class="dict-entry" data-strong="">
    <td class="dict-col-checkbox">
      <input type="checkbox" class="entry-checkbox">
    </td>
    <td class="dict-col-strong">
      <span class="strong-number"></span>
    </td>
    <td class="dict-col-translations">
      <input type="text" class="translation-input">
    </td>
    <td class="dict-col-crossref">
      <span class="crossref-badges"></span>  <!-- NEW -->
    </td>
    <td class="dict-col-color">
      <input type="color" class="color-picker">
      <button class="reset-color-btn" title="Reset to default">↺</button>
    </td>
    <td class="dict-col-actions">
      <button class="save-btn">Save</button>
      <button class="delete-btn">Delete</button>
      <a class="heatmap-link" href="#" title="View Heatmap">📊</a>
    </td>
  </tr>
</template>
```

**File**: `app/static/js/dictionary-edit.js`

Add cross-reference loading:

```javascript
// Cache for cross-references
const crossrefCache = new Map();

async function loadCrossrefsForEntries(strongNumbers) {
  // Filter out already cached
  const uncached = strongNumbers.filter(sn => !crossrefCache.has(sn));

  if (uncached.length === 0) return;

  // Batch fetch
  const response = await fetch(`/api/crossref/batch?strongs=${uncached.join(',')}`);
  const data = await response.json();

  // Cache results
  for (const [sn, refs] of Object.entries(data.results)) {
    crossrefCache.set(sn, refs);
  }
}

function renderCrossrefBadges(strongNumber) {
  const refs = crossrefCache.get(strongNumber);
  if (!refs || (refs.primary.length === 0 && refs.secondary.length === 0)) {
    return '<span class="no-crossrefs">—</span>';
  }

  const badges = refs.primary.slice(0, 2).map(ref =>
    `<a href="/heatmap?strong=${ref}" class="crossref-badge primary" title="Primary LXX equivalent">${ref}</a>`
  );

  if (refs.secondary.length > 0) {
    badges.push(`<span class="crossref-more" title="${refs.secondary.join(', ')}">+${refs.secondary.length}</span>`);
  }

  return badges.join(' ');
}

// Modify renderEntries to include cross-refs
async function renderEntries() {
  // ... existing filter/sort logic ...

  // Load cross-refs for visible entries
  const visibleStrongs = filteredEntries.map(e => e.dataset.strong);
  await loadCrossrefsForEntries(visibleStrongs);

  // Render each entry
  filteredEntries.forEach(entry => {
    const strongNum = entry.dataset.strong;
    const crossrefCell = entry.querySelector('.crossref-badges');
    if (crossrefCell) {
      crossrefCell.innerHTML = renderCrossrefBadges(strongNum);
    }
  });
}

// Add filter by cross-reference availability
let showOnlyWithCrossrefs = false;

document.getElementById('filter-crossrefs')?.addEventListener('change', (e) => {
  showOnlyWithCrossrefs = e.target.checked;
  renderEntries();
});

function matchesCrossrefFilter(entry) {
  if (!showOnlyWithCrossrefs) return true;
  const refs = crossrefCache.get(entry.dataset.strong);
  return refs && (refs.primary.length > 0 || refs.secondary.length > 0);
}
```

**CSS additions for dictionary**:

```css
/* Dictionary cross-reference column */
.dict-col-crossref {
  width: 120px;
}

.crossref-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.crossref-badge {
  display: inline-block;
  padding: 2px 6px;
  border-radius: 10px;
  font-size: 11px;
  font-family: monospace;
  text-decoration: none;
}

.crossref-badge.primary {
  background: #e3f2fd;
  color: #1565c0;
}

.crossref-more {
  color: #999;
  font-size: 11px;
  cursor: help;
}

.no-crossrefs {
  color: #ccc;
}
```

---

## 5. FILE STRUCTURE AND IMPLEMENTATION APPROACH

### 5.1 New Files to Create

```
app/
├── static/
│   ├── hebrew_greek_crossref.json    # Cross-reference data (generated)
│   └── js/
│       └── crossref-utils.js          # Shared cross-ref functions (optional)
scripts/
├── build_crossref_data.py             # Data generation script
├── validate_crossref_data.py          # Validation script
└── data/
    └── TBESH.txt                       # Source data (downloaded)
```

### 5.2 Modified Files

| File | Changes |
|------|---------|
| `app/routes.py` | Add crossref data loading, new API endpoints |
| `app/templates/home.html` | Add crossref section to popup |
| `app/templates/heatmap.html` | Add toggle, crossref display |
| `app/templates/edit_dict.html` | Add crossref column |
| `app/static/js/chapter-view.js` | Add crossref fetching for popup |
| `app/static/js/dictionary-edit.js` | Add crossref loading/display |
| `app/static/css/main.css` | Add crossref styling |

### 5.3 Implementation Order

**Phase 1: Data Layer** (Foundation)
1. Download and process source data (TBESH)
2. Create `build_crossref_data.py` script
3. Generate `hebrew_greek_crossref.json`
4. Add loading to `routes.py` startup

**Phase 2: API Endpoints**
1. Implement `/api/crossref/<strong>` endpoint
2. Implement `/api/crossref/batch` endpoint
3. Add tests for new endpoints

**Phase 3: Strong's Popup**
1. Add HTML structure for crossref section
2. Implement JavaScript fetching and display
3. Add CSS styling
4. Test with various Hebrew/Greek words

**Phase 4: Heatmap Enhancement**
1. Modify `/heatmap` route to include crossref data
2. Add toggle control to template
3. Implement crossref heatmap display
4. Add interactive chip links
5. Add CSS styling

**Phase 5: Dictionary Editor**
1. Add crossref column to table
2. Implement batch loading of crossrefs
3. Add filter option
4. Add CSS styling

**Phase 6: Testing & Polish**
1. Write integration tests
2. Performance testing (ensure no slowdown)
3. Edge case handling (missing data)
4. Documentation update

---

## 6. TECHNICAL CONSIDERATIONS

### 6.1 Performance

- **Data size**: Cross-ref JSON estimated at ~500KB-1MB
- **Startup impact**: Minimal (single JSON load)
- **API latency**: In-memory lookups, <10ms response time
- **Heatmap impact**: Each additional crossref heatmap adds ~2-3s if uncached

### 6.2 Caching Strategy

```python
# Add to existing LRU cache setup
@lru_cache(maxsize=256)
def get_enriched_crossref(strong_number):
    """Cache enriched cross-reference data."""
    # ... lookup and enrich ...
```

### 6.3 Error Handling

- Missing crossref data: Show empty state, don't error
- Invalid Strong's numbers: Validate format, return 400
- Partial data: Gracefully handle missing fields

### 6.4 Future Enhancements

1. **Verse-level alignment**: Show specific verse parallels (requires more data)
2. **Confidence scores**: Indicate how reliable each mapping is
3. **User annotations**: Let users suggest/correct mappings
4. **Export cross-ref data**: Add to dictionary export

---

## 7. TESTING PLAN

### 7.1 Unit Tests

```python
# tests/test_crossref.py

def test_crossref_data_loading():
    """Verify cross-reference data loads correctly."""
    assert len(hebrew_to_greek) > 0
    assert len(greek_to_hebrew) > 0

def test_crossref_api_valid_hebrew():
    """Test API returns data for valid Hebrew Strong's."""
    response = client.get('/api/crossref/H7225')
    assert response.status_code == 200
    data = response.get_json()
    assert data['language'] == 'hebrew'
    assert 'cross_refs' in data

def test_crossref_api_valid_greek():
    """Test API returns data for valid Greek Strong's."""
    response = client.get('/api/crossref/G2316')
    assert response.status_code == 200
    data = response.get_json()
    assert data['language'] == 'greek'

def test_crossref_api_invalid_format():
    """Test API rejects invalid Strong's format."""
    response = client.get('/api/crossref/invalid')
    assert response.status_code == 400

def test_crossref_batch_api():
    """Test batch API returns multiple results."""
    response = client.get('/api/crossref/batch?strongs=H7225,G2316')
    assert response.status_code == 200
    data = response.get_json()
    assert 'H7225' in data['results']
    assert 'G2316' in data['results']

def test_crossref_bidirectional():
    """Verify bidirectional mapping consistency."""
    # If H7225 -> G746, then G746 should include H7225
    h_refs = hebrew_to_greek.get('H7225', {})
    for g_num in h_refs.get('primary', []):
        g_refs = greek_to_hebrew.get(g_num, {})
        all_hebrew = g_refs.get('primary', []) + g_refs.get('secondary', [])
        assert 'H7225' in all_hebrew
```

### 7.2 Integration Tests

- Test popup shows crossref section
- Test heatmap toggle works
- Test dictionary column displays
- Test navigation between cross-referenced words

---

## 8. SUMMARY

This implementation plan provides a complete roadmap for adding Hebrew-Greek cross-referencing to the Bible transliteration app. The approach:

1. **Uses existing architecture patterns** (JSON data, in-memory lookup, Flask routes)
2. **Minimizes changes to existing code** (additive enhancements)
3. **Provides clear user value** (clickable links between languages)
4. **Maintains performance** (in-memory lookups, caching)
5. **Allows incremental implementation** (phased approach)

The estimated effort is approximately:
- Data layer: 4-6 hours
- API endpoints: 2-3 hours
- Popup enhancement: 3-4 hours
- Heatmap enhancement: 4-5 hours
- Dictionary enhancement: 3-4 hours
- Testing & polish: 4-6 hours

**Total: 20-28 hours of development time**
