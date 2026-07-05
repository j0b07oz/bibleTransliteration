# Upgrade Recommendations — Architecture Review

This document is a senior-architect review of the Bible Transliteration project. It is based on the README, the About page (`app/templates/about.html`), the full backend (`app/routes.py`, `app/transliteration.py`, `app/__init__.py`), the frontend modules (`app/static/js/chapter-view.js`, `app/static/js/dictionary-edit.js`), the tests, and the deployment setup (`Procfile`, `requirements.txt`).

**What this project is, from the user's perspective:** a reading tool. A reader curates a personal list of Strong's numbers, and when they open a KJV chapter, those English words are replaced inline with their Hebrew/Greek transliterations — the goal (in the About page's words) is "seamlessly blending languages and allowing readers to make new connections with familiar verses." Around that core loop sit literary-unit overlays with progress bars, repeated/uncommon word highlighting, client-side phonetic device detection, a whole-Bible frequency heatmap with Hebrew↔Greek cross-references, and dictionary import/export. The author states they are "not a web developer" and hopes the idea is picked up by others — so the recommendations below favor pragmatic, incremental changes over framework rewrites, and they call out where a change unblocks the project's stated goal of spreading.

The review produced two sets of recommendations:

- **Part 1 — Backend code improvements**, ranked by impact. The first three are fixes for genuine bugs found during the review.
- **Part 2 — User-facing feature additions**, grounded in the app's purpose and the author's own stated favorites, and checked against what already exists (e.g., a click-a-word "Add to My List" popup already ships in `chapter-view.js`, so it is *not* recommended again here).

---

## Part 1 — Backend code improvements

### B1. Stop storing the whole user dictionary in the session cookie

**What.** `save_user_dict()` writes the entire user dictionary into the Flask session (`app/routes.py:86`, also read/written at lines 140 and 147). Flask's default session is a **client-side signed cookie**, not server-side storage — `ARCHITECTURE.md` §12.2 ("Why Server-Side Sessions? … No 4KB cookie limit") is unfortunately describing a mechanism the app doesn't use. The default dictionary alone is ~8 KB of JSON; once the serialized session exceeds ~4093 bytes, browsers **silently drop the entire cookie**. When that happens the user loses not just the in-session dictionary but also their `user_id` — which orphans the on-disk copy in `app/uploads/{user_id}.json`, so the disk-persistence fallback can never rescue them.

This is a silent data-loss bug that hits exactly the most engaged users: the bigger your word list, the more likely you lose it.

**How.**
1. Keep only `user_id` in the session cookie (that's what `get_session_id()` at `app/routes.py:58` already provides).
2. Make the per-user file (`_user_dict_path()`) the single source of truth. In `get_user_strongs_dict()`, remove the `session['user_strongs_dict']` fast path and instead cache the loaded dict on `flask.g` so each request reads the file at most once:

   ```python
   def get_user_strongs_dict():
       if 'user_strongs_dict' in g:
           return g.user_strongs_dict
       # ... existing file-load + validation logic ...
       g.user_strongs_dict = data_or_default
       return g.user_strongs_dict
   ```
3. In `save_user_dict()`, drop the `session[...] = user_dict` line; write the file and update `g`.
4. Update `export_dict()` to call `get_user_strongs_dict()` (see B3 — it currently reads the session directly).
5. Correct `ARCHITECTURE.md` §5 and §12.2 to describe the real mechanism (cookie holds an ID; data lives in per-user JSON files).

**Why.** It converts a silent, hard-to-reproduce data-loss failure into a durable design; it removes ~8 KB of payload from every request/response; and it is the root cause behind the inconsistency fixed in B3. It also makes future features (sharing, reading history) safe to build on the per-user file.

---

### B2. Validate colors strictly and escape attribute values in `build_span`

**What.** A dictionary entry's `color` is only validated as "must be a string" (`app/routes.py:75-77`), and the form/JSON edit paths pass any string through (`_normalize_color`, `app/routes.py:503-506`). That string is then interpolated **unescaped** into an HTML `style` attribute during chapter rendering (`app/transliteration.py:309-311` builds `background-color: {base_color}; …` and line 320 wraps it in `style="…"`). Two concrete consequences:

1. **Stored XSS via shared dictionaries.** A color value like `red" onmouseover="…` breaks out of the attribute and injects arbitrary attributes/handlers. Because import/export files are explicitly meant to be passed between users (README: "Import/export functionality for custom dictionaries"), a crafted dictionary file is a stored-XSS vector against anyone who imports it. This becomes critical if link-based sharing (U3) ever ships.
2. **A 500 on every chapter view.** Any color that isn't `#RRGGBB` (e.g. `"blue"`, `"#fff"`) crashes `is_light_color()` (`app/transliteration.py:109-111` does `int(hex_color[i:i+2], 16)` → `ValueError`), bricking the core reading view until the offending entry is removed.

**How.**
1. Add one validator and use it at all the entry points — `_validate_user_dict` (upload path) and `_normalize_color` (form and JSON action paths):

   ```python
   HEX_COLOR_RE = re.compile(r'#[0-9a-fA-F]{6}$')

   def _valid_color(c):
       return c is None or (isinstance(c, str) and HEX_COLOR_RE.fullmatch(c))
   ```
   Reject uploads containing invalid colors with a clear message; coerce invalid colors to `None` on the edit paths.
2. Defense in depth inside `build_span` (`app/transliteration.py`): skip the style block when the color doesn't match the pattern, and run every interpolated attribute value — including the assembled `style` string — through the existing `safe_attr()` helper (`app/transliteration.py:181-184`), which is already used for the `data-*` attributes but not for `style`.
3. Add regression tests in `tests/test_validation.py`: a dictionary with `"color": "red\" onmouseover=\"x"` is rejected on upload; a chapter render with a malformed color in the dict returns 200, not 500.

**Why.** This is the only real injection surface in the app, the fix is ~20 lines, and it must land **before** any feature that moves dictionaries between users. The crash variant is also the app's easiest self-inflicted outage.

---

### B3. Fix the export→import roundtrip and the temp-file leak in `export_dict`

**What.** `export_dict` (`app/routes.py:597-606`) has two defects:

1. **Roundtrip failure.** It reads `session.get('user_strongs_dict', default_strongs_dict.copy())`. For a fresh session the fallback is the *raw* file shape `{"H7225": ["beginning"]}` — but everywhere else the app uses the wrapped shape `{"H7225": {"translations": [...], "color": null}}` (see the wrapping at `app/routes.py:129`). `_validate_user_dict` requires the wrapped shape, so a user who exports before making any edit gets a file that **their own upload endpoint rejects**. Backup-then-restore — the primary reason to export — fails in the most common first-touch case.
2. **Temp-file leak.** It writes a `NamedTemporaryFile(delete=False)` and never deletes it: one leaked file per export for the life of the dyno/host.

**How.** Replace the body with an in-memory send using the canonical accessor:

```python
@app.route('/export_dict')
def export_dict():
    user_strongs_dict = get_user_strongs_dict()
    payload = json.dumps(user_strongs_dict, ensure_ascii=False, indent=2).encode('utf-8')
    return send_file(
        io.BytesIO(payload),
        mimetype='application/json',
        as_attachment=True,
        download_name='my_strongs_dict.json',
    )
```

Add a roundtrip test to `tests/test_routes.py`: fresh client → `GET /export_dict` → `POST /upload_dict` with the downloaded bytes → assert success redirect, not the validation-error redirect.

**Why.** Import/export is a headline README feature; today its main use case fails silently for new users, and every export leaks disk. The fix is small, removes the filesystem entirely from the path, and (with B1) makes export consistent with the single source of truth.

---

### B4. Build data indexes once at startup instead of per request

**What.** Three related inefficiencies, all stemming from data access being scattered rather than centralized:

- `transliterate_chapter` rebuilds `strongs_lookup` — a dict comprehension over the **entire** Strong's list (3.8 MB, ~14k entries) — on **every chapter render** (`app/transliteration.py:144-146`).
- `api_crossref`'s `enrich_strong` does a linear `next((s for s in strongs_data if s.get('number') == sn), {})` scan over that same list **per cross-reference** (`app/routes.py:885`) — up to ~12 full scans per popup open.
- `app/transliteration.py` keeps hidden module-global caches (`_global_strongs_counts`, `_verses_by_book`, lines 10-11) that ignore which `kjv_data` was passed in. Any test (or future caller) that passes fixture data gets silently-stale results from whichever dataset touched the cache first.

**How.** Introduce `app/data.py` with a single object built once at startup:

```python
@dataclass
class BibleData:
    strongs_by_number: dict          # number -> entry
    verses_by_book: dict             # book_name -> [verse, ...]
    global_strongs_counts: Counter   # number -> whole-Bible count
    book_order: dict
    book_chapter_count: dict
    chapter_verse_counts: dict

def load_bible_data(static_dir, outlines_path) -> BibleData: ...
```

- Move the JSON loading (`app/routes.py:155-162`) and the book/chapter mapping loops (`app/routes.py:177-192`) into `load_bible_data`.
- Store the instance on `app.extensions['bible_data']`; routes read it from there, and tests can inject a fixture instance instead of monkeypatching module globals.
- Pass `strongs_by_number` into `transliterate_chapter` (replacing the raw list) and delete the per-call comprehension; delete the two module globals in `transliteration.py` in favor of the precomputed fields; replace `enrich_strong`'s scan with `bible_data.strongs_by_number.get(sn, {})`.

**Why.** It removes measurable work from the hot path (every chapter view), turns an O(n)-per-ref API into O(1), eliminates a latent test-pollution trap, and gives the app an explicit, injectable data layer — the single highest-leverage refactor for making the codebase approachable to the outside contributors the About page hopes for.

---

### B5. Add CSRF protection, session-cookie flags, and restore the HTTPS redirect

**What.** All state-changing routes — `/edit_dict` (JSON and form), `/upload_dict`, `/navigate` — accept cookie-authenticated POSTs with no CSRF token. The HTTPS redirect middleware is commented out (`app/__init__.py:43-51`), and `config.py` sets no session-cookie hardening flags.

**How.**
1. Add `flask-wtf` to `requirements.txt` and enable `CSRFProtect(app)` in `app/__init__.py`.
2. Expose the token in a `<meta name="csrf-token" content="{{ csrf_token() }}">` tag in the four templates; send it as an `X-CSRFToken` header from the two `fetch()` call sites (`app/static/js/chapter-view.js:963`, `app/static/js/dictionary-edit.js:39`); add hidden `csrf_token` inputs to the navigate and upload forms.
3. In `Config` (`config.py`): `SESSION_COOKIE_SAMESITE = 'Lax'`, `SESSION_COOKIE_HTTPONLY = True`, and `SESSION_COOKIE_SECURE = True` gated on an env flag so local HTTP development still works.
4. Replace the commented-out hand-rolled redirect with the standard pattern: wrap the app in `werkzeug.middleware.proxy_fix.ProxyFix(app.wsgi_app, x_proto=1, x_host=1)` so `request.scheme` reflects the original protocol behind the reverse proxy, then a three-line `before_request` that 301s `http`→`https` when not in debug/testing. (This is why the original attempt was hard to verify: without `ProxyFix`, `X-Forwarded-Proto` handling is manual and error-prone.)

**Why.** Today the blast radius is "someone can vandalize your word list via a hostile page" — annoying but bounded. B1 makes the per-user file durable and U3 introduces cross-user content; the standard protections should be in place *before* the data becomes worth protecting. `SameSite=Lax` also mitigates most CSRF for free in modern browsers, making this cheap insurance.

---

### B6. Operational hygiene: CI, ongoing upload cleanup, and un-serving 13 MB of data

**What.** Three small operational gaps:

1. **No CI.** The project has a real pytest suite (`tests/`, with a documented coverage workflow in the README) but nothing runs it automatically — and notably, the bugs in B2/B3 are exactly the kind a CI-gated regression test would have caught.
2. **Uploads grow forever.** `cleanup_old_session_files()` runs only once, at import time (`app/routes.py:56`). A long-lived server never prunes `app/uploads/` again.
3. **Server-only data is publicly served.** `kjv_strongs.json` (9.1 MB) and `Strongs.json` (3.8 MB) live in `app/static/`, so they are downloadable by anyone/anything that guesses the URL — yet no frontend code fetches them (verified: the only JSON requests in the JS are `/edit_dict` and `/api/crossref/*`).

**How.**
1. Add `.github/workflows/ci.yml`: on push/PR, matrix over Python 3.10 and 3.12, `pip install -r requirements.txt`, `pytest --cov=app --cov-report=term-missing`.
2. Piggyback cleanup on traffic instead of adding a scheduler (Heroku-friendly): in `save_user_dict()`, call `cleanup_old_session_files()` at most once per 24 h, guarded by a `.last_cleanup` timestamp file in the uploads dir.
3. Move the server-only JSON files from `app/static/` to a non-routable `app/data/` directory and update the path constants (`app/routes.py:150-165`). Keep only genuinely client-served assets (CSS/JS) in `static/`.

**Why.** Each is a sub-hour change: CI prevents the regression class this review found; lazy cleanup bounds disk usage without new infrastructure; moving the data files stops paying bandwidth for crawler downloads of 13 MB and makes the public surface of the app explicit.

---

### B7. (Larger, optional) Rewrite `transliterate_chapter` as a single-pass tokenizer

**What.** The rendering engine (`app/transliteration.py:140-425`) works by repeatedly running `re.search` and **global** `str.replace` against a `verse['text']` string that it is simultaneously mutating. Consequences: replaced HTML is rescanned by later iterations; `.replace()` hits *all* duplicate occurrences of a word+marker at once; behavior depends on the iteration order of Strong's markers; and edge cases (the `{(H5625)}` alternate-number pattern, empty word matches, repeated words) are each handled by special-case patches (e.g. lines 327-332, 344-352) rather than structurally.

**How.** Tokenize each verse **once**: a single regex pass over the marker grammar (`word{H####}` plus trailing `{(H5625)}{H####}` alternates) yields a token stream of `(english_word, strongs_number, alt_number)` plus plain-text gaps; then render each token to a span through the existing `build_span` and join. The output contract (verse-number-prefixed HTML lines) stays identical, so `build_verses_for_render` (`app/routes.py:457`) and all frontend code are untouched. Sequence the work safely: first add golden-output tests to `tests/test_transliteration.py` for a handful of tricky verses (duplicate words, multi-word phrase translations, `H5625` alternates), then swap the implementation behind them.

**Why.** This is the most complex code in the repo and the heart of the product. A single-pass design eliminates the rescan/duplicate-replace corruption class outright, cuts per-chapter rendering cost (the current approach re-searches an ever-growing HTML string), and — most importantly for a project whose About page hopes others will pick it up — turns the core algorithm into something a new contributor can read and extend.

---

## Part 2 — User-facing feature additions

These follow from the app's purpose — helping readers make new connections with familiar verses — and from the author's own words on the About page. Ranked by expected value to the reader.

### U1. Concordance view — "find all occurrences" of a word

**What.** A `/occurrences?strong=H2617` page that lists every verse containing a Strong's number, grouped by book with per-book counts, each verse linking into the existing chapter view with the existing focus highlight (`/?book=Genesis&chapter=24&focus=H2617`).

**How.**
- New route reusing what's already in memory: `get_verses_by_book()` + `extract_strongs_numbers()` (both in `app/transliteration.py`) to select matching verses; strip the `{H####}` markers for display with the same two `re.sub` cleanup patterns already used at `app/transliteration.py:421-423`.
- Cache per Strong's number with `@lru_cache(maxsize=128)`, exactly like the existing `generate_heatmap_counts` (`app/routes.py:613`) — same data-scan shape, same caching profile.
- Entry points: a "View all N occurrences →" link in the existing word popup (`chapter-view.js` word context menu), and per-book links from heatmap rows.

**Why.** The About page *explicitly praises* this exact feature in eBible ("I like the 'find all occurrences' feature"). The heatmap already answers "*where* does this word cluster?" but there is currently no way to read the actual verses — the study loop dead-ends at colored cells. This closes the loop using data structures and caching patterns the codebase already has; it's mostly plumbing plus one template.

### U2. English→Strong's reverse lookup ("I know the word, not the number")

**What.** A search box (on `/edit_dict`, optionally the home page) where a reader types an English word — "mercy" — and gets ranked Strong's candidates (lemma, transliteration, whole-Bible count, sample gloss) each with a one-click **Add to my list** button.

**How.**
- At startup, build an inverted index in one pass over the 31k verses using the existing `STRONGS_REGEX` word+marker pairs: `index[english_word.lower()][strongs_number] += 1`. It fits naturally as another field on the `BibleData` object from B4.
- New endpoint `GET /api/word_lookup?q=mercy` returning candidates sorted by count, enriched from `strongs_by_number` (lemma/xlit/description).
- Frontend: reuse the autocomplete pattern already implemented for book names in `chapter-view.js` (prefix/contains/fuzzy matching is already written there), and post adds through the **existing** `/edit_dict` JSON `actions` API (`app/routes.py:532-544`) — the same call the word popup already makes.

**Why.** Today there are only two ways to add a word: already know its Strong's number (the About page literally instructs users to go look numbers up on BibleHub), or stumble across the word while reading and click it. For the app's core loop — "pick out a few words you already know and add them" — the missing piece is starting from the English word. This is the single biggest onboarding gap, and the server already holds every byte of data needed to close it.

### U3. Shareable word lists via link

**What.** A "Share my list" button that produces a URL like `/import?code=ab12cd34ef56`. The recipient sees a preview — the words, transliterations, and colors in the list — and chooses **Merge into my list** or **Replace my list**.

**How.**
- `POST /share_dict`: validate the current dict with the existing `_validate_user_dict`, write it to `app/uploads/shared/{sha256(content)[:12]}.json` (content-addressed, so identical lists dedupe and links are idempotent; no accounts or auth needed), return the link. Cap payload size (~256 KB).
- `GET /import?code=…`: render a preview page from the stored file; the confirm button merges (or replaces) via the existing `save_user_dict()`.
- Reuse the 30-day `cleanup_old_session_files` policy for the shared directory (or a longer TTL, refreshed on access).
- **Hard prerequisite: B2.** Shared dictionaries turn the color-injection bug from self-XSS into cross-user stored XSS; the validation/escaping fix must land first.

**Why.** The About page says the author's hope is that this idea spreads. Today, sharing a word list means export-a-file-and-email-it. A link is the natural growth loop for a passion project — "look what Ruth 1 looks like with *hesed* and *shub* transliterated, here's my list" — and roughly 90% of the machinery (validation, persistence, upload/merge semantics, preview rendering from the edit page) already exists.

### U4. Continue-reading: restore last position and recent chapters

**What.** When a returning reader opens the home page, show "**Continue reading: Genesis 12 →**" plus their few most recent chapters, instead of a blank book/chapter form.

**How.** Purely client-side to start — zero backend changes:
- After each successful chapter render, `chapter-view.js` writes `{book, chapter, ts}` into a small `localStorage` ring buffer (last 5 distinct chapters). The book and chapter are already available to the script on the rendered page.
- `home.html` renders the resume button(s) from that buffer on load; clicking one submits the existing form programmatically (or navigates to `/?book=…&chapter=…`, which the home route already accepts via query args).
- Later, once B1 lands, the same structure can move into the per-user JSON file (e.g. `{"dict": …, "recent": […]}`) so history follows the session cookie rather than the browser profile.

**Why.** This is a *reader*, and the app already cares about position — it draws per-book progress bars and literary-unit progress on every chapter — yet every visit starts from a blank form. "Resume where I left off" is the most-felt everyday friction in the product and the cheapest item on this list: an afternoon of JavaScript, no backend risk at all.

---

## Suggested sequencing

| Order | Item | Effort | Rationale |
|-------|------|--------|-----------|
| 1 | B2 (color validation/escaping) | Small | Fixes a 500-crash and the only injection surface; prerequisite for U3 |
| 2 | B3 (export roundtrip) | Small | User-visible bug in a headline feature |
| 3 | B1 (session architecture) | Medium | Silent data loss; foundation for U3/U4 server-side history |
| 4 | B6 (CI, cleanup, data dir) | Small | Locks in the above with regression tests |
| 5 | U4 (continue reading) | Small | Highest value-per-effort feature |
| 6 | B4 (startup indexes) | Medium | Enables U2 cleanly; performance + testability |
| 7 | U1 (concordance) | Medium | Author's own most-wanted feature |
| 8 | U2 (reverse lookup) | Medium | Closes the onboarding gap |
| 9 | B5 (CSRF/HTTPS) | Small-Medium | Land before U3 makes data cross-user |
| 10 | U3 (shareable lists) | Medium | The growth loop, once B2/B5 are in |
| 11 | B7 (tokenizer rewrite) | Large | Optional; do behind golden tests when touching the engine next |
