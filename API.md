# API Documentation

This document provides comprehensive documentation for all API endpoints in the Bible Transliteration application.

## Base URL

- **Development**: `http://localhost:5000`
- **Production**: `https://uncoverthebible.com`

---

## Endpoints

### 1. Home / Chapter View

**Endpoint**: `/`
**Methods**: `GET`, `POST`
**Description**: Display a Bible chapter with transliteration overlay.

#### Request Parameters

**Query/Form Parameters**:
- `book` (string, optional): Book name (e.g., "Genesis", "Matthew")
- `chapter` (integer, optional): Chapter number (1-based)
- `focus` (string, optional): Strong's number to highlight (e.g., "H7225")
- `from_heatmap` (boolean, optional): Flag indicating navigation from heatmap view

#### Response

**Success (200 OK)**:
- Returns HTML page with:
  - Bible chapter text with transliteration
  - Literary units and progress bars
  - Phonetic device detection cards
  - Context menu options
  - Navigation controls

**Validation Errors**:
- Invalid book name: Error message displayed
- Invalid chapter number: Error message displayed
- Chapter out of range: Error message displayed

#### Example Usage

```bash
# View Genesis chapter 1
GET /?book=Genesis&chapter=1

# View with Strong's number focus
GET /?book=Genesis&chapter=1&focus=H7225&from_heatmap=true
```

#### Logged Events
- Invalid chapter format warnings
- Book/chapter validation failures

---

### 2. Chapter Navigation

**Endpoint**: `/navigate`
**Method**: `POST`
**Description**: Navigate to previous or next chapter within a book.

#### Request Parameters

**Form Data**:
- `book` (string, required): Current book name
- `chapter` (integer, required): Current chapter number
- `direction` (string, required): Navigation direction (`"prev"` or `"next"`)

#### Response

**Success (200 OK)**:
- Returns HTML page with the navigated chapter
- Automatically bounds navigation within book limits

**Errors**:
- Invalid state: Redirects to home page

#### Behavior
- **Previous**: Navigates to previous chapter (minimum: chapter 1)
- **Next**: Navigates to next chapter (maximum: last chapter of book)
- Validates resulting chapter before rendering

#### Example Usage

```html
<form method="POST" action="/navigate">
    <input type="hidden" name="book" value="Genesis">
    <input type="hidden" name="chapter" value="1">
    <button name="direction" value="next">Next Chapter</button>
</form>
```

#### Logged Events
- Invalid chapter in navigation
- Navigation validation failures

---

### 3. Dictionary Editor

**Endpoint**: `/edit_dict`
**Methods**: `GET`, `POST`
**Description**: Manage Strong's transliteration dictionary entries.

#### GET Request

**Description**: Display dictionary editor interface.

**Response**:
- Returns HTML page with:
  - List of all dictionary entries
  - Search and filter controls
  - Add entry form
  - Bulk action controls

#### POST Request

**Description**: Execute dictionary CRUD operations.

**Request Body** (JSON):
```json
{
  "actions": [
    {
      "action": "add|update|delete",
      "strong_number": "H7225",
      "translations": ["beginning", "first"],
      "color": "#FF5733"
    }
  ]
}
```

**Action Types**:
- `add`: Add new Strong's entry
- `update`: Update existing entry (translations, color)
- `delete`: Remove entry from dictionary

**Response**:
```json
{
  "success": true
}
```

**Error Response**:
```json
{
  "success": false,
  "error": "Error message"
}
```

#### Validation Rules

1. **Strong's Number**:
   - Must be string (e.g., "H7225", "G2316")
   - Required for all operations

2. **Translations**:
   - Must be array of strings
   - At least one translation required
   - Required for add/update operations

3. **Color**:
   - Must be hex color string (e.g., "#FF5733")
   - Can be `null` to use default coloring

#### Example Usage

```javascript
// Add a new entry
fetch('/edit_dict', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    actions: [{
      action: 'add',
      strong_number: 'H7225',
      translations: ['beginning', 'first'],
      color: '#FF5733'
    }]
  })
});

// Update multiple entries
fetch('/edit_dict', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    actions: [
      { action: 'update', strong_number: 'H7225', color: null },
      { action: 'delete', strong_number: 'H430' }
    ]
  })
});
```

#### Logged Events
- Invalid user dictionary files
- Dictionary update failures

---

### 4. Dictionary Upload

**Endpoint**: `/upload_dict`
**Method**: `POST`
**Description**: Upload a complete dictionary file to replace user dictionary.

#### Request Parameters

**Form Data**:
- `dict_file` (file, required): JSON file containing dictionary entries

**Expected File Format**:
```json
{
  "H7225": {
    "translations": ["beginning", "first"],
    "color": "#FF5733"
  },
  "H430": {
    "translations": ["God"],
    "color": null
  }
}
```

#### Response

**Success**:
- Redirects to `/edit_dict` with success message

**Validation Errors**:
- Invalid JSON format
- Missing required fields
- Invalid data types

#### Validation Rules

1. Root must be object/dictionary
2. Keys must be strings (Strong's numbers)
3. Values must be objects with:
   - `translations`: array of strings (required)
   - `color`: string or null (optional)

#### Example Usage

```html
<form method="POST" action="/upload_dict" enctype="multipart/form-data">
    <input type="file" name="dict_file" accept=".json">
    <button type="submit">Upload</button>
</form>
```

#### Logged Events
- File upload validation errors

---

### 5. Dictionary Export

**Endpoint**: `/export_dict`
**Method**: `GET`
**Description**: Download current user dictionary as JSON file.

#### Response

**Success (200 OK)**:
- Content-Type: `application/json`
- Content-Disposition: `attachment; filename="strongs_dict.json"`
- Body: JSON file containing user's dictionary

**Response Format**:
```json
{
  "H7225": {
    "translations": ["beginning", "first"],
    "color": "#FF5733"
  },
  "H430": {
    "translations": ["God"],
    "color": null
  }
}
```

#### Example Usage

```html
<a href="/export_dict" download>Export Dictionary</a>
```

```javascript
// Programmatic download
window.location.href = '/export_dict';
```

---

### 6. About Page

**Endpoint**: `/about`
**Method**: `GET`
**Description**: Display application information and usage instructions.

#### Response

**Success (200 OK)**:
- Returns HTML page with:
  - Application description
  - Usage instructions
  - Feature explanations
  - External resource links

#### Example Usage

```html
<a href="/about">About</a>
```

---

### 7. Heatmap View

**Endpoint**: `/heatmap`
**Method**: `GET`
**Description**: Display frequency heatmap for a Strong's number across all Bible chapters.

#### Request Parameters

**Query Parameters**:
- `strong` (string, optional): Strong's number to visualize (e.g., "H7225")

#### Response

**Success (200 OK)**:
- Returns HTML page with:
  - Heatmap visualization grid (books × chapters)
  - Color-coded frequency indicators
  - Interactive chapter navigation
  - Search input for Strong's numbers

**Caching**:
- Results cached using `@lru_cache(maxsize=128)`
- First request: Full Bible scan (~2-3 seconds)
- Subsequent requests: Near-instant (cached)

#### Heatmap Data Structure

Each cell represents a chapter with:
- `count`: Number of occurrences in chapter
- `color`: RGB hex color (red intensity based on frequency)
- `chapter`: Chapter number

Color calculation:
- `R = 255` (fixed)
- `G = 255 * (1 - alpha)` where `alpha = count / max_count`
- `B = 255 * (1 - alpha)`

Result: White (0 occurrences) → Red (maximum occurrences)

#### Example Usage

```bash
# View heatmap for H7225 (beginning)
GET /heatmap?strong=H7225

# Empty heatmap (no Strong's specified)
GET /heatmap
```

#### Logged Events
- Heatmap generation performance metrics (if enabled)

---

### 8. Word Occurrences (Concordance)

**Endpoint**: `GET /occurrences`

Lists every verse containing a Strong's number, grouped by book in canonical
order, with the matched English word highlighted. Each verse reference links
into the chapter view with `focus` highlighting.

#### Request Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `strong` | string | No | Strong's number (e.g., "H2617"). Blank shows the search form. |

#### Example Usage

```
# All occurrences of hesed
GET /occurrences?strong=H2617

# Jump straight to one book's section (anchors are #book-<Name>)
GET /occurrences?strong=H2617#book-Psalms
```

Results are cached per Strong's number (LRU, 32 entries), so repeated lookups
are instant.

---

### 9. English Word Lookup

**Endpoint**: `GET /api/word_lookup`

Reverse lookup from an English KJV word to ranked Strong's number candidates.
Exact word match first; if no exact match, words starting with the query are
aggregated.

#### Request Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `q` | string | Yes | English word, minimum 2 characters |

#### Response

```json
{
  "query": "mercy",
  "exact": true,
  "results": [
    {
      "strong": "H2617",
      "count": 137,
      "word": "mercy",
      "lemma": "חֵסֵד",
      "xlit": "chêçêd",
      "gloss": "from חָסַד; kindness; ..."
    }
  ]
}
```

Results are sorted by how often the Strong's number is rendered as the queried
word (max 8). Queries under 2 characters return HTTP 400.

---

### 10. Share Word List

**Endpoint**: `POST /share_dict`

Publishes the caller's current word list as a shareable link. The list is
stored content-addressed (SHA-256 of its canonical JSON, first 12 hex chars),
so sharing the same list twice returns the same link. Requires the CSRF token
via the `X-CSRFToken` header.

#### Response

```json
{
  "success": true,
  "code": "c5d009aa0669",
  "url": "/import?code=c5d009aa0669"
}
```

Errors (empty list, list larger than 256 KB, invalid entries) return HTTP 400
with `{"success": false, "error": "..."}`.

Shared lists expire after 90 days without access; opening a share link
refreshes its timer.

---

### 11. Import Shared List

**Endpoints**: `GET /import`, `POST /import`

`GET /import?code=<code>` renders a preview of the shared list (words,
transliterations, colors, and which entries you already have) with
**Merge into My List** and **Replace My List** actions. Unknown or expired
codes return HTTP 404.

`POST /import` applies the list:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `code` | string | Yes | 12-hex-char share code |
| `mode` | string | No | `merge` (default) or `replace` |
| `csrf_token` | string | Yes | CSRF token |

Redirects to the dictionary editor with a success (or error) message.

---

## Data Models

### User Dictionary Entry

```typescript
{
  translations: string[],  // List of translation strings
  color: string | null     // Hex color (e.g., "#FF5733") or null for default
}
```

### Strong's Number Format

- **Hebrew**: `H` + 1-5 digits (e.g., "H7225", "H1")
- **Greek**: `G` + 1-5 digits (e.g., "G2316", "G25")

### Book Names

Valid book names include:
- Old Testament: "Genesis", "Exodus", "Leviticus", etc.
- New Testament: "Matthew", "Mark", "Luke", "John", etc.

Full list available via `book_chapter_count` dictionary in backend.

---

## Error Handling

### Error Response Format

```json
{
  "success": false,
  "error": "Human-readable error message"
}
```

### Common Errors

| Error | Cause | HTTP Status |
|-------|-------|-------------|
| Invalid book name | Book not in Bible | 200 (with error message) |
| Invalid chapter | Chapter out of range | 200 (with error message) |
| Validation error | Invalid request data | 400 |
| Missing file | File upload missing | 400 |
| Invalid JSON | Malformed JSON in upload | 400 |

---

## Session Management

### Session Data

- **Storage**: The signed session cookie holds only the user's ID; the
  dictionary itself lives on disk (the cookie's ~4 KB limit cannot hold it)
- **Cookie**: HttpOnly, SameSite=Lax; `Secure` when `SESSION_COOKIE_SECURE=true`
- **Persistence**: User dictionary saved to `app/uploads/{user_id}.json`
- **Cleanup**: Files older than 30 days deleted on startup and at most once
  per day thereafter (piggybacked on save traffic); shared lists expire after
  90 days without access

### Session Schema

```python
{
  'user_id': str,  # UUID v4 — key into app/uploads/{user_id}.json
}
```

---

## Performance Considerations

### Caching Strategy

1. **Heatmap Generation**:
   - Function-level LRU cache (128 entries)
   - Cache key: Strong's number
   - Cache hit: ~1ms response time
   - Cache miss: ~2-3s processing time

2. **Static Data**:
   - Bible text, Strong's concordance loaded at startup
   - ~14.3 MB in memory
   - Never reloaded during runtime

### Rate Limiting

- **Not implemented**: Consider adding for production
- **Recommended**: 100 requests/minute per IP for dictionary operations

---

## Security Considerations

### Input Validation

- All book/chapter inputs validated before processing
- Dictionary uploads validated against schema
- HTML output auto-escaped by Jinja2

### Session Security

- Secret key required (environment variable: `SECRET_KEY`)
- Session files stored server-side with UUID filenames
- Automatic cleanup prevents disk exhaustion

### Known Limitations

- No CSRF protection (recommended for production)
- No rate limiting (recommended for production)
- File uploads not scanned for malware

---

## Logging

### Log Levels

- **INFO**: Application startup, normal operations
- **WARNING**: Validation failures, non-critical errors
- **ERROR**: Critical failures, unexpected exceptions

### Log Location

- **Production**: `logs/bible_transliteration.log`
- **Development**: Console output

### Logged Events

- Application startup/shutdown
- Validation failures (book/chapter/dictionary)
- File I/O errors
- Navigation errors
- Dictionary operation failures

---

## API Versioning

**Current Version**: 1.0 (implicit)

No explicit versioning implemented. Breaking changes should increment version and be documented.

---

## Support

For issues, questions, or contributions:
- **GitHub**: https://github.com/j0b07oz/bibleTransliteration/issues
- **Documentation**: README.md, ARCHITECTURE.md

