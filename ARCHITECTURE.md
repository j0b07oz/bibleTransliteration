# Architecture Documentation

This document provides a comprehensive overview of the Bible Transliteration application architecture, including system design, data flow, and component interactions.

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Architecture Diagrams](#architecture-diagrams)
3. [Component Breakdown](#component-breakdown)
4. [Data Flow](#data-flow)
5. [Directory Structure](#directory-structure)
6. [Technology Stack](#technology-stack)
7. [Data Models](#data-models)
8. [Core Algorithms](#core-algorithms)
9. [Deployment Architecture](#deployment-architecture)

---

## System Overview

The Bible Transliteration application is a Flask-based web application that overlays Hebrew and Greek transliterations onto the King James Bible text. It includes phonetic device detection, literary unit visualization, and customizable transliteration dictionaries.

### Key Features

- **Chapter-by-chapter Bible viewing** with KJV transliteration
- **Customizable Strong's word dictionary** with user CRUD operations
- **Phonetic literary device detection** (alliteration, assonance, consonance, etc.)
- **Uncommon word highlighting** (statistical analysis)
- **Literary unit visualization** with progress tracking
- **Heatmap view** for word frequency analysis
- **Dictionary import/export** functionality

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                       Client (Browser)                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │   home.html  │  │ edit_dict.html│  │   heatmap.html   │  │
│  └──────────────┘  └────────────────┘  └──────────────────┘  │
│         │                  │                      │            │
│         └──────────────────┴──────────────────────┘            │
│                           │                                      │
│                    Jinja2 Templates                            │
│                           │                                    │
│                           ↓                                    │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │          JavaScript Modules (Client-Side)                │  │
│  │  ┌────────────────────────────────────────────────────┐ │
│  │  │  chapter-view.js                                  │ │
│  │  │  - Context menu & options management             │ │
│  │  │  - Phonetic device detection (Levenshtein, etc) │ │
│  │  - Literary unit overlays                        │ │
│  │  - Heatmap focus highlighting                     │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                            │
│  ┌──────────────────────────────────────────────────────┐ │
│  │ dictionary-edit.js (~401 lines)                       │ │
│  │  - CRUD operations                                    │ │
│  │  - Search & filtering                                 │ │
│  │  - Bulk actions (delete, reset colors)               │ │
│  │  - Toast notifications                                │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                               │
└───────────────────────────────────────────────────────────┘

## Key Features

- **Phonetic Device Detection**: Levenshtein distance, root matching, alliteration
- **Literary Unit Overlays**: Visual progress bars for book sections
- **Context Menu**: Toggle visibility of different text features
- **Responsive Design**: Works on desktop and mobile browsers

---

## 3. Data Flow

### Request Lifecycle

```
┌─────────────┐
│   Browser   │
└──────┬──────┘
       │ HTTP Request
       ↓
┌──────────────────────────────────────┐
│         Flask Application            │
│  ┌────────────────────────────────┐ │
│  │         routes.py              │ │
│  │  ┌──────────────────────────┐ │
│  │  │  1. Input Validation     │ │
│  │  │  2. Session Management    │ │
│  │  └──────────────────────────┘ │
│  └──────────────────────────────────┘
│                 ↓
│   ┌──────────────────────────────┐
│   │  transliteration.py          │
│   │  - extract_strongs_numbers() │
│   │  - transliterate_chapter()   │
│   │  - generate_colors()          │
│   │  - detect_uncommon_words()   │
│   └──────────────────────────────┘
│
└─→ [Response] HTML with transliteration
```

---

## 4. Data Flow

### 4.1 Chapter View Request Flow

```
┌─────────────┐
│   Browser   │
└──────┬──────┘
       │ GET /?book=Genesis&chapter=1
       ▼
┌──────────────────────────────────────────┐
│         Flask App (routes.py)            │
│  ┌────────────────────────────────────┐ │
│  │ 1. Validate book & chapter        │ │
│  │    - Check book exists             │ │
│  │    - Check chapter in range        │ │
│  └────────────────────────────────────┘ │
│                │                         │
│                ▼                         │
│        ┌──────────────────┐              │
│        │  Load User Dict  │              │
│        │  (from session)  │              │
│        └──────────────────┘              │
│                 │                        │
│                 ▼                        │
│    ┌─────────────────────────────┐      │
│    │  transliterate_chapter()    │      │
│    │  (app/transliteration.py)   │      │
│    └─────────────────────────────┘      │
│                 │                        │
│                 ▼                        │
│    ┌─────────────────────────────┐      │
│    │  Load Chapter Data          │      │
│    │  - Extract verses           │      │
│    │  - Extract Strong's numbers │      │
│    └─────────────────────────────┘      │
│                 │                        │
│                 ▼                        │
│    ┌─────────────────────────────┐       │
│    │  Process Transliterations   │       │
│    │  - Match Strong's numbers   │       │
│    │  - Apply translations       │       │
│    │  - Generate colors           │       │
│    └─────────────────────────────┘       │
│                 │                          │
│                 v                          │
│    ┌────────────────────────────┐         │
│    │  Detect Repeated Words     │         │
│    │  (count >= 3 in chapter)   │         │
│    └────────────────────────────┘         │
│                 │                          │
│                 v                          │
│    ┌─────────────────────────────────┐    │
│    │   Identify Uncommon Words       │    │
│    │   - Global frequency < 10       │    │
│    │   - Unit clustering analysis    │    │
│    └─────────────────────────────────┘    │
│                                            │
└────────────────────────────────────────────┘
                      │
                      ▼
            ┌──────────────────┐
            │  Generate HTML   │
            │  with semantic   │
            │    attributes    │
            └──────────────────┘
                      │
                      ▼
            ┌──────────────────┐
            │   Return HTML    │
            │   to Template    │
            └──────────────────┘
```

---

## 3. Frontend Architecture

### 3.1 JavaScript Module Structure

```
app/static/js/
├── chapter-view.js       # Main chapter display logic
└── dictionary-edit.js    # Dictionary management UI
```

### 3.2 Chapter View Module (`chapter-view.js`)

```
┌─────────────────────────────────────────────────┐
│           Chapter View Module (627 lines)       │
├─────────────────────────────────────────────────┤
│                                                 │
│  ┌──────────────────────────────────────────┐  │
│  │  Context Options Management              │  │
│  │  - localStorage persistence              │  │
│  │  - Toggle bolded/repeats/phonetics       │  │
│  │  - Apply CSS classes to body             │  │
│  └──────────────────────────────────────────┘  │
│                                                 │
│  ┌──────────────────────────────────────────┐  │
│  │  Literary Unit Overlay                   │  │
│  │  - Render colored bars beside verses    │  │
│  │  - ResizeObserver for dynamic updates   │  │
│  │  - Calculate positions from verse rows  │  │
│  └──────────────────────────────────────────┘  │
│                                                 │
│  ┌──────────────────────────────────────────┐  │
│  │  Phonetic Device Detection               │  │
│  │  - Token normalization (diacritics)      │  │
│  │  - Levenshtein distance calculation      │  │
│  │  - Root letter matching                  │  │
│  │  - Device classification                 │  │
│  │  - Interactive cards with hover effects │  │
│  └──────────────────────────────────────────┘  │
│                                                 │
│  ┌──────────────────────────────────────────┐  │
│  │  Event Handlers                          │  │
│  │  - Context menu toggle                   │  │
│  │  - Uncommon word clicks → heatmap        │  │
│  │  - Phonetic chip hover → highlight       │  │
│  │  - Window resize → redraw overlay        │  │
│  └──────────────────────────────────────────┘  │
│                                                 │
└─────────────────────────────────────────────────┘
```

### 3.3 Dictionary Edit Module (`dictionary-edit.js`)

```
┌─────────────────────────────────────────────────┐
│        Dictionary Edit Module (401 lines)       │
├─────────────────────────────────────────────────┤
│                                                 │
│  ┌──────────────────────────────────────────┐  │
│  │  Entry Management                        │  │
│  │  - Add/Update/Delete entries             │  │
│  │  - Color picker integration              │  │
│  │  - Translation comma-separated parsing   │  │
│  └──────────────────────────────────────────┘  │
│                                                 │
│  ┌──────────────────────────────────────────┐  │
│  │  Filtering & Sorting                     │  │
│  │  - Search by Strong's # or translation   │  │
│  │  - Language filter (Hebrew/Greek)        │  │
│  │  - Sort by Strong's number (asc/desc)    │  │
│  └──────────────────────────────────────────┘  │
│                                                 │
│  ┌──────────────────────────────────────────┐  │
│  │  Bulk Operations                         │  │
│  │  - Select visible/clear selection        │  │
│  │  - Bulk delete                           │  │
│  │  - Bulk color reset                      │  │
│  └──────────────────────────────────────────┘  │
│                                                 │
│  ┌──────────────────────────────────────────┐  │
│  │  API Communication                       │  │
│  │  - fetch() to /edit_dict endpoint        │  │
│  │  - Action batching                       │  │
│  │  - Toast notifications                   │  │
│  └──────────────────────────────────────────┘  │
│                                                 │
└─────────────────────────────────────────────────┘
```

---

## 4. Data Flow Diagrams

### 4.1 Chapter View Request Flow

```
┌──────────┐
│  User    │
└────┬─────┘
     │
     │ GET /?book=Genesis&chapter=1
     ▼
┌─────────────────┐
│  Flask Routes   │
│   (routes.py)   │
└────┬────────────┘
     │
     │ 1. Validate book/chapter
     ▼
┌─────────────────────┐      NO      ┌──────────────────┐
│ validate_book_      │─────────────▶│ Return error     │
│ chapter()           │              │ message in HTML  │
└────┬────────────────┘              └──────────────────┘
     │ YES
     │
     │ 2. Get user dictionary
     ▼
┌─────────────────────┐
│ get_user_strongs_   │
│ dict()              │
└────┬────────────────┘
     │
     │ 3. Process chapter
     ▼
┌─────────────────────┐
│ transliterate_      │◀──── Loads: strongs_data
│ chapter()           │      kjv_data, active_units
└────┬────────────────┘
     │
     │ Returns HTML with semantic markup
     ▼
┌─────────────────────┐
│ render_template()   │
│ 'home.html'         │
└────┬────────────────┘
     │
     │ HTML + config injection
     ▼
┌──────────────────────┐
│  Browser             │
└────┬─────────────────┘
     │
     │ DOMContentLoaded
     ▼
┌──────────────────────┐
│ chapter-view.js      │
│ - Render overlays    │
│ - Detect phonetics   │
│ - Bind events        │
└──────────────────────┘
```

### 4.2 Dictionary Update Flow

```
┌──────────┐
│  User    │
└────┬─────┘
     │
     │ Click "Update" button
     ▼
┌────────────────────┐
│ dictionary-edit.js │
└────┬───────────────┘
     │
     │ 1. Collect form data
     ▼
┌──────────────────────┐
│ sendActions([        │
│   {action: 'update', │
│    strong_number,    │
│    translations,     │
│    color}            │
│ ])                   │
└────┬─────────────────┘
     │
     │ 2. POST /edit_dict
     ▼
┌─────────────────────────┐
│  Flask Routes           │
│  @app.route('/edit_dict')│
└────┬────────────────────┘
     │
     │ 3. Validate actions
     ▼
┌──────────────────────────┐     INVALID    ┌──────────────┐
│ _validate_user_dict()    │───────────────▶│ Return error │
└────┬─────────────────────┘                └──────────────┘
     │ VALID
     │
     │ 4. Execute actions
     ▼
┌──────────────────────────┐
│ Process each action:     │
│ - add: Add to dict       │
│ - update: Modify entry   │
│ - delete: Remove entry   │
└────┬─────────────────────┘
     │
     │ 5. Save to session & disk
     ▼
┌──────────────────────────┐
│ save_user_dict()         │
│ - session storage        │
│ - uploads/{uuid}.json    │
└────┬─────────────────────┘
     │
     │ 6. Return success
     ▼
┌──────────────────────────┐
│ {"success": true}        │
└────┬─────────────────────┘
     │
     │ 7. Update UI
     ▼
┌──────────────────────────┐
│ dictionary-edit.js       │
│ - Show toast notification│
│ - Re-render entry list   │
│ - Update selection UI    │
└──────────────────────────┘
```

### 4.3 Heatmap Generation Flow (with Caching)

```
┌──────────┐
│  User    │
└────┬─────┘
     │
     │ GET /heatmap?strong=H7225
     ▼
┌─────────────────────┐
│  Flask Routes       │
│  @app.route(...)    │
└────┬────────────────┘
     │
     │ Call generate_heatmap(strong)
     ▼
┌──────────────────────────────────────┐
│  @lru_cache(maxsize=128)             │
│  generate_heatmap(strong_number)     │
└────┬─────────────────────────────────┘
     │
     │ Check cache
     ▼
  ┌──────┐
  │Cache?│
  └──┬───┘
     │
     ├─YES─▶ ┌────────────────────┐
     │       │ Return cached data │ (< 1ms)
     │       └────────────────────┘
     │
     └─NO──▶ ┌─────────────────────────────┐
             │ Iterate all Bible verses    │ (2-3s)
             │ - Group by book/chapter     │
             │ - Count Strong's occurrences│
             │ - Calculate color intensity │
             │ - Build heatmap grid        │
             └────┬────────────────────────┘
                  │
                  │ Store in cache
                  ▼
             ┌────────────────────┐
             │ Return heatmap data│
             └────────────────────┘
```

---

## 5. Session Management Architecture

### 5.1 Session Lifecycle

```
┌──────────────────────────────────────────────────┐
│           Session Lifecycle                      │
├──────────────────────────────────────────────────┤
│                                                  │
│  1. First Request                                │
│     ┌─────────────────┐                         │
│     │ User visits /   │                         │
│     └────┬────────────┘                         │
│          │                                       │
│          │ No session cookie                    │
│          ▼                                       │
│     ┌─────────────────────────┐                │
│     │ get_session_id()        │                │
│     │ - Generate UUID         │                │
│     │ - Store in session      │                │
│     │ - Set cookie            │                │
│     └────┬────────────────────┘                │
│          │                                       │
│  2. Load/Create Dictionary                      │
│     ┌─────────────────────────┐                │
│     │ get_user_strongs_dict() │                │
│     │                         │                │
│     │ Check uploads/{uuid}.   │                │
│     │ json exists?            │                │
│     └────┬────────────────────┘                │
│          │                                       │
│     ┌────┴────┐                                 │
│  YES│         │NO                               │
│     │         │                                  │
│     ▼         ▼                                  │
│  ┌────┐  ┌──────────┐                          │
│  │Load│  │Use default│                         │
│  │file│  │dictionary │                         │
│  └────┘  └──────────┘                          │
│     │         │                                  │
│     └────┬────┘                                 │
│          │                                       │
│          │ Store in session                     │
│          ▼                                       │
│     ┌─────────────────┐                        │
│     │ session['user_  │                        │
│     │  strongs_dict'] │                        │
│     └─────────────────┘                        │
│                                                  │
│  3. Subsequent Requests                         │
│     ┌──────────────────┐                       │
│     │ Load from session│ (fast, in-memory)     │
│     └──────────────────┘                       │
│                                                  │
│  4. Dictionary Updates                          │
│     ┌──────────────────────┐                   │
│     │ save_user_dict()     │                   │
│     │ - Update session     │                   │
│     │ - Write to disk      │                   │
│     └──────────────────────┘                   │
│                                                  │
│  5. Session Expiry (30 days)                   │
│     ┌──────────────────────┐                   │
│     │ cleanup_old_session_ │                   │
│     │ files()              │                   │
│     │ - Runs on startup    │                   │
│     │ - Deletes old files  │                   │
│     └──────────────────────┘                   │
│                                                  │
└──────────────────────────────────────────────────┘
```

### 5.2 Session Storage

```
┌──────────────────────────────────────────┐
│          Session Storage                 │
├──────────────────────────────────────────┤
│                                          │
│  Client-Side                             │
│  ┌────────────────────────────┐         │
│  │  Cookie:                   │         │
│  │  - Name: "session"         │         │
│  │  - Value: encrypted UUID   │         │
│  │  - HttpOnly: true          │         │
│  │  - Secure: true (prod)     │         │
│  └────────────────────────────┘         │
│                                          │
│  Server-Side (Flask Session)             │
│  ┌────────────────────────────┐         │
│  │  session = {               │         │
│  │    'user_id': '<uuid>',    │         │
│  │    'user_strongs_dict': {} │         │
│  │  }                         │         │
│  └────────────────────────────┘         │
│                                          │
│  Disk Persistence                        │
│  ┌──────────────────────────────┐       │
│  │  app/uploads/<uuid>.json     │       │
│  │  {                           │       │
│  │    "H7225": {                │       │
│  │      "translations": [...],  │       │
│  │      "color": "#FF5733"      │       │
│  │    }                         │       │
│  │  }                           │       │
│  └──────────────────────────────┘       │
│                                          │
└──────────────────────────────────────────┘
```

---

## 6. Security Architecture

### 6.1 Security Layers

```
┌────────────────────────────────────────────────┐
│            Security Layers                     │
├────────────────────────────────────────────────┤
│                                                │
│  1. Input Validation                           │
│     ┌──────────────────────────────┐          │
│     │ validate_book_chapter()      │          │
│     │ - Book name validation       │          │
│     │ - Chapter bounds checking    │          │
│     │ - Type validation            │          │
│     └──────────────────────────────┘          │
│                                                │
│  2. Session Security                           │
│     ┌──────────────────────────────┐          │
│     │ - Secret key from env var    │          │
│     │ - Server-side sessions       │          │
│     │ - UUID filenames (guessing   │          │
│     │   resistant)                 │          │
│     └──────────────────────────────┘          │
│                                                │
│  3. Output Sanitization                        │
│     ┌──────────────────────────────┐          │
│     │ - Jinja2 auto-escaping       │          │
│     │ - html.escape() for attrs    │          │
│     │ - No eval() or exec()        │          │
│     └──────────────────────────────┘          │
│                                                │
│  4. Data Validation                            │
│     ┌──────────────────────────────┐          │
│     │ _validate_user_dict()        │          │
│     │ - Schema validation          │          │
│     │ - Type checking              │          │
│     │ - Required field validation  │          │
│     └──────────────────────────────┘          │
│                                                │
│  5. File System Security                       │
│     ┌──────────────────────────────┐          │
│     │ - Restricted upload directory│          │
│     │ - UUID-based filenames       │          │
│     │ - Automatic cleanup          │          │
│     └──────────────────────────────┘          │
│                                                │
│  ⚠️ Missing (Recommended for Production)       │
│     ┌──────────────────────────────┐          │
│     │ - CSRF protection            │          │
│     │ - Rate limiting              │          │
│     │ - File upload size limits    │          │
│     │ - Malware scanning           │          │
│     └──────────────────────────────┘          │
│                                                │
└────────────────────────────────────────────────┘
```

---

## 7. Logging Architecture

### 7.1 Logging Flow

```
┌────────────────────────────────────────────┐
│         Logging Configuration              │
├────────────────────────────────────────────┤
│                                            │
│  app/__init__.py                           │
│  ┌──────────────────────────┐             │
│  │ if production:           │             │
│  │   - RotatingFileHandler  │             │
│  │   - 10MB max size        │             │
│  │   - 10 backup files      │             │
│  │   - logs/bible_trans...  │             │
│  │                          │             │
│  │ else (development):      │             │
│  │   - StreamHandler        │             │
│  │   - Console output       │             │
│  │   - DEBUG level          │             │
│  └──────────────────────────┘             │
│                                            │
│  Application Code                          │
│  ┌──────────────────────────┐             │
│  │ logger = app.logger      │             │
│  │                          │             │
│  │ logger.info(...)         │             │
│  │ logger.warning(...)      │             │
│  │ logger.error(...)        │             │
│  └──────────────────────────┘             │
│                                            │
│  Log Events                                │
│  ┌──────────────────────────────────┐     │
│  │ - Application startup            │     │
│  │ - Validation failures            │     │
│  │ - File I/O errors                │     │
│  │ - Dictionary save failures       │     │
│  │ - Navigation errors              │     │
│  │ - Invalid user dictionary files  │     │
│  └──────────────────────────────────┘     │
│                                            │
│  Log Format                                │
│  ┌──────────────────────────────────┐     │
│  │ YYYY-MM-DD HH:MM:SS LEVEL:       │     │
│  │ message [in path:line]           │     │
│  └──────────────────────────────────┘     │
│                                            │
└────────────────────────────────────────────┘
```

---

## 8. Performance Optimization

### 8.1 Optimization Strategies

| Strategy | Implementation | Impact |
|----------|----------------|--------|
| **Startup Data Loading** | Load all JSON files once at startup | 14.3 MB in memory, avoid disk I/O |
| **Heatmap Caching** | `@lru_cache(maxsize=128)` | 2-3s → <1ms for cached requests |
| **Session Persistence** | Store user dict in session + disk | Avoid repeated file reads |
| **JavaScript Extraction** | Separate .js files | Browser caching, parallel loading |
| **Resize Observer** | Debounce overlay rendering | Smooth resize performance |

### 8.2 Performance Bottlenecks

```
┌───────────────────────────────────────────────┐
│        Performance Characteristics            │
├───────────────────────────────────────────────┤
│                                               │
│  Fast Operations (< 100ms)                    │
│  ✓ Chapter view (cached session)             │
│  ✓ Dictionary CRUD operations                │
│  ✓ Navigation between chapters               │
│  ✓ Heatmap view (cached)                     │
│                                               │
│  Moderate Operations (100ms - 1s)             │
│  ⚠ First chapter view (load + process)       │
│  ⚠ Phonetic device detection (client-side)   │
│                                               │
│  Slow Operations (> 1s)                       │
│  ⚠ Heatmap generation (first request)        │
│  ⚠ Full Bible iteration (31,102 verses)      │
│  ⚠ Application startup (data loading)        │
│                                               │
│  Optimization Opportunities                   │
│  🔧 Async data loading at startup            │
│  🔧 Progressive phonetic detection           │
│  🔧 Pre-generate common heatmaps             │
│  🔧 Add Redis for distributed caching        │
│                                               │
└───────────────────────────────────────────────┘
```

---

## 9. Testing Architecture

### 9.1 Test Structure

```
tests/
├── conftest.py              # Fixtures and configuration
├── test_transliteration.py  # Core logic tests (36 tests)
│   ├── TestExtractStrongsNumbers
│   ├── TestColorGeneration
│   └── TestTransliterateChapter
├── test_routes.py           # API endpoint tests (29 tests)
│   ├── TestHomeRoute
│   ├── TestEditDictRoute
│   ├── TestDictionaryOperations
│   ├── TestExportImport
│   └── TestHeatmapRoute
└── test_validation.py       # Validation tests (23 tests)
    ├── TestUserDictValidation
    ├── TestSessionCleanup
    └── TestInputSanitization
```

### 9.2 Testing Strategy

```
┌────────────────────────────────────────────┐
│          Testing Pyramid                   │
├────────────────────────────────────────────┤
│                                            │
│              /\                            │
│             /  \     E2E Tests             │
│            /    \    (Future)              │
│           /──────\                         │
│          /        \  Integration Tests     │
│         /          \ (29 route tests)      │
│        /────────────\                      │
│       /              \ Unit Tests          │
│      /                \ (59 tests)         │
│     /──────────────────\                   │
│                                            │
│  Coverage Target: 70%+                     │
│  Current: Foundation laid (88 tests)       │
│                                            │
└────────────────────────────────────────────┘
```

---

## 10. Deployment Architecture

### 10.1 Production Deployment

```
┌────────────────────────────────────────────────┐
│           Production Stack                     │
├────────────────────────────────────────────────┤
│                                                │
│  ┌──────────────────────────────┐             │
│  │  Reverse Proxy (Nginx)       │             │
│  │  - SSL/TLS termination       │             │
│  │  - Static file serving       │             │
│  │  - Load balancing (optional) │             │
│  └───────────┬──────────────────┘             │
│              │                                 │
│              ▼                                 │
│  ┌──────────────────────────────┐             │
│  │  WSGI Server (Gunicorn)      │             │
│  │  - Multiple workers          │             │
│  │  - Process management        │             │
│  └───────────┬──────────────────┘             │
│              │                                 │
│              ▼                                 │
│  ┌──────────────────────────────┐             │
│  │  Flask Application           │             │
│  │  - Python 3.10+              │             │
│  │  - Secret key from env       │             │
│  │  - Logging to file           │             │
│  └───────────┬──────────────────┘             │
│              │                                 │
│              ▼                                 │
│  ┌──────────────────────────────┐             │
│  │  File System                 │             │
│  │  - Static data (14.3 MB)     │             │
│  │  - Session files             │             │
│  │  - Log files                 │             │
│  └──────────────────────────────┘             │
│                                                │
│  Environment Variables                         │
│  - SECRET_KEY (required)                       │
│  - FLASK_ENV=production                        │
│                                                │
└────────────────────────────────────────────────┘
```

### 10.2 Heroku Deployment

**Files**:
- `Procfile`: `web: gunicorn run:app`
- `requirements.txt`: All dependencies
- `runtime.txt`: Python version (optional)

**Configuration**:
```bash
heroku config:set SECRET_KEY="your-secret-key"
heroku config:set FLASK_ENV=production
```

---

## 11. Future Architecture Considerations

### 11.1 Scalability Improvements

```
Current → Future

┌──────────────┐      ┌──────────────┐
│ File-based   │  →   │  Database    │
│ sessions     │      │  (PostgreSQL)│
└──────────────┘      └──────────────┘

┌──────────────┐      ┌──────────────┐
│ In-memory    │  →   │  Redis cache │
│ LRU cache    │      │  (distributed)│
└──────────────┘      └──────────────┘

┌──────────────┐      ┌──────────────┐
│ Synchronous  │  →   │  Async/await │
│ Flask        │      │  (FastAPI?)  │
└──────────────┘      └──────────────┘

┌──────────────┐      ┌──────────────┐
│ Single       │  →   │  Microservices│
│ monolith     │      │  - API service│
│              │      │  - Worker queue│
└──────────────┘      └──────────────┘
```

### 11.2 Feature Expansion

- **User Accounts**: Authentication, saved preferences
- **API Endpoints**: RESTful API for mobile apps
- **Real-time Collaboration**: WebSocket support
- **Advanced Search**: Full-text search across Bible
- **Verse Comparison**: Compare translations side-by-side
- **Notes & Annotations**: User-generated content
- **Export Formats**: PDF, EPUB, DOCX generation

---

## 12. Key Design Decisions

### 12.1 Why Flask?

- **Lightweight**: Minimal overhead for small application
- **Flexible**: Easy to customize and extend
- **Well-documented**: Mature ecosystem
- **Jinja2**: Powerful templating engine

### 12.2 Why Server-Side Sessions?

- **Security**: Sensitive data not exposed to client
- **Capacity**: No 4KB cookie limit
- **Flexibility**: Can store complex data structures

### 12.3 Why LRU Cache?

- **Simplicity**: Built-in Python decorator
- **Effectiveness**: Heatmaps are frequently repeated
- **No dependencies**: No Redis/Memcached required

### 12.4 Why Separate JavaScript Files?

- **Maintainability**: Easier to edit and test
- **Caching**: Browser can cache static files
- **Development**: Better IDE support and linting

---

## 13. Monitoring & Observability

### 13.1 Current Logging

```
logs/bible_transliteration.log
├── Startup events
├── Validation errors
├── File I/O failures
└── Navigation errors
```

### 13.2 Future Monitoring

- **Application metrics**: Request count, latency
- **Error tracking**: Sentry or similar
- **Performance monitoring**: New Relic, DataDog
- **User analytics**: Page views, feature usage
- **Uptime monitoring**: Pingdom, UptimeRobot

---

## Glossary

**Strong's Number**: Unique identifier for Hebrew/Greek words in Bible concordance
**Transliteration**: Representation of words from one script to another (e.g., Hebrew → Latin)
**Literary Unit**: Structural division of Bible text (e.g., narrative, poetry, discourse)
**Phonetic Device**: Literary technique using sound patterns (alliteration, assonance, etc.)
**Heatmap**: Visual representation of word frequency across Bible chapters
**LRU Cache**: Least Recently Used cache eviction strategy

---

## References

- [Flask Documentation](https://flask.palletsprojects.com/)
- [Jinja2 Templates](https://jinja.palletsprojects.com/)
- [Strong's Concordance](https://www.blueletterbible.org/study/misc/strongs.cfm)
- [Python Logging](https://docs.python.org/3/library/logging.html)
- [functools.lru_cache](https://docs.python.org/3/library/functools.html#functools.lru_cache)
