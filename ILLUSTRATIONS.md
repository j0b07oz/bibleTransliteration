# Visual Guide Illustrations (scrollytelling panel)

The chapter reader can "uncover" specification-heavy passages with a sticky
illustration panel. On a chapter that has a scene (the seed is **Exodus 25 —
the Ark of the Covenant**), a single master image sits beside the text and, as
the reader scrolls, a soft spotlight highlights the region of the image the
current verses describe, alongside the key Hebrew word, transliteration, gloss,
and a short note.

The whole feature is **data + one image per scene** — adding a new scene (the
Temple, the priestly garments, Golgotha…) is authoring work, never code:

1. Generate a master image with an AI model.
2. Post-process it into `app/static/img/illustrations/<scene-id>/`.
3. Annotate the regions with the region editor.
4. Add a scene entry to `app/data/illustrations.json`.
5. Run `pytest tests/test_illustration_catalog.py`.

The panel is **on by default** on illustrated chapters and can be toggled in the
"Literary Context ▾" menu ("Visual guide illustration"); the choice persists in
`localStorage`. It never affects any other page or any non-illustrated chapter,
and it degrades gracefully — with JavaScript off (or an image 404) the panel is
a static image plus the full annotated step list, and Bible reading is
unchanged.

---

## How it works (architecture)

| Piece | Location |
|---|---|
| Catalog (the only content you edit) | `app/data/illustrations.json` |
| Loader + `(book, chapter)` index (lenient: bad scene → warn + skip) | `app/data/__init__.py` (`_build_illustration_index`) |
| Runtime field | `BibleData.illustrations_by_chapter` |
| Server accessor + context | `app/routes.py` (`get_illustration_scene`, `build_home_context`) |
| Panel markup | `app/templates/home.html` |
| Styles (grid, sticky strip, spotlight) | `app/static/css/main.css` |
| Scroll-sync + SVG spotlight controller | `app/static/js/illustration-panel.js` |
| Region authoring tool | `scripts/tools/region-editor.html` |
| Strict catalog validation | `tests/test_illustration_catalog.py` |

Region coordinates are **percentages (0–100) of the image**, drawn in a 0–100
space with `preserveAspectRatio="none"`, so a region survives the image being
displayed at any size and never needs re-measuring.

---

## Step 1 — Generate the master image with AI

**Principles**

1. **One master image per scene, never one per step.** Every step spotlights a
   region of the *same* image, so the single generation must show every element
   the steps reference. (Generating a consistent object across many frames is
   the thing AI image models are worst at — this design avoids it entirely.)
2. **Write the shot list first.** From the passage, list every element a step
   will highlight. For the Ark (Exodus 25): the chest, the crown molding, the
   four rings at the feet, the two poles, the gold cover, the two cherubim,
   their wing span, and the empty space above the cover. The composition must
   show all of them, visibly separated.
3. **One canonical aspect ratio for the whole series** — 4:3 is the seed
   (1200×900). Keeping every scene the same ratio makes panel height predictable.
4. **No text, labels, numbers, or watermarks in the image.** All labels live in
   the app overlay (accessible, translatable, editable).
5. **Reuse a style block** across every scene prompt for a consistent look.

**Model** — pick one and stay with it for the series: Midjourney v7
(`--ar 4:3 --style raw`, reuse `--seed` for consistency), OpenAI `gpt-image-1`
(strong at "show all parts" compositions), Google Imagen 4, or Flux 1.1 Pro
(cheap API via Replicate / fal.ai).

**Prompt template**

```
[SUBJECT with an explicit part list], [MATERIALS per the text],
[COMPOSITION / CAMERA angle], [LIGHTING], [BACKGROUND],
[STYLE BLOCK], no text, no labels, no watermark
```

**Worked example — the Ark seed image**

> Museum-quality studio photograph of the Ark of the Covenant on a dark earthen
> floor: a rectangular acacia-wood chest completely overlaid with gold, an
> ornamental gold crown molding around the upper rim, four cast gold rings at
> the four feet, two gold-covered carrying poles passing through the rings and
> extending toward the viewer, a solid-gold lid, and two hammered-gold cherubim
> kneeling on the lid with wings stretched upward and inward, faces turned
> toward each other looking down at the cover. Three-quarter front view showing
> the front, one long side, and the top. Single warm key light from upper left,
> dark bronze-paneled wall behind, subtle floor shadow. Photorealistic, warm
> gold tones, dark moody backdrop. No text, no labels, no watermark.

**Composition rules that make annotation possible**

- **Three-quarter view** (front + one side + top) so each named part gets its
  own non-overlapping screen region.
- **Keep a 5–8% margin** — nothing a step spotlights may touch the frame edge
  (the spotlight blur feathers outward).
- **Dark / neutral background** — the dim overlay reads best when the subject is
  brighter than its surroundings.
- **Architectural scenes** (tabernacle court, temple): use an elevated cutaway
  or isometric view so every named part is visible at once.

**Acceptance checklist before annotating**

- [ ] Every shot-list element is visible and unambiguous
- [ ] Faithful to the details you'll spotlight (e.g. cherubim wings covering the
      seat, faces toward each other — Ex 25:20; correct ring/pole counts)
- [ ] No embedded text, labels, or watermark
- [ ] No obvious AI artifacts inside a region you'll spotlight
- [ ] Canonical aspect ratio for the series

## Step 2 — Post-process and export

1. Generate at the largest resolution available; upscale to ≥1600px wide if
   needed (the generator's upscaler, or Real-ESRGAN).
2. Crop to the canonical aspect ratio.
3. Export three files into `app/static/img/illustrations/<scene-id>/`:
   - `<name>-1600.webp` and `<name>-800.webp` (quality ≈ 80) — the responsive
     WebP sources,
   - `<name>-1600.jpg` (quality ≈ 85) — the universal `<img>` fallback.
   Target ≤ 400 KB per served file; strip metadata. (The seed uses `-1200`
   sizes because its source is 1200×900 — match the sizes to your export.)
4. Keep a note of the model + full prompt + date (the catalog `credit` stays
   user-facing, e.g. "AI-generated illustration"; keep the prompt in this file's
   change log for reproducibility).

A quick Pillow recipe (no external tools needed):

```python
from PIL import Image
im = Image.open("master.png").convert("RGB")
im.save("ark-1600.jpg", quality=85, optimize=True)
im.save("ark-1600.webp", quality=80, method=6)
im.resize((800, round(800 * im.height / im.width))).save("ark-800.webp", quality=80, method=6)
```

## Step 3 — Annotate the regions

Open **`scripts/tools/region-editor.html`** directly in a browser (no server
needed — `File ▸ Open`, or double-click it).

1. Load your image with the file picker.
2. For each named part: set the **step id** (e.g. `keruvim`), pick Rectangle or
   Ellipse, and drag over the part. Repeat the same step id for parts that
   belong together (e.g. the four rings all get `tabbaot`).
3. Drag a shape to move it; drag its corner handle to resize; select and
   Delete to remove. Adjust the **dim** value (overlay darkness outside the
   spotlight; 0.55–0.75 works well).
4. Click **Copy steps JSON**. You get a `{ image: {width, height}, steps: [...] }`
   payload with each step's `id`, `dim`, and `regions` in percentage coords.

## Step 4 — Add the scene to the catalog

Edit `app/data/illustrations.json`. Merge the editor output into a scene, and
add the human-readable fields (`hebrew`, `translit`, `gloss`, `note`) and the
`passages` each step should appear on. A step may list **multiple passages** so
the same annotation appears in parallel accounts — e.g. the Ark steps map to
both Exodus 25 (instructions) and Exodus 37 (construction).

```jsonc
{
  "version": 1,
  "scenes": [
    {
      "id": "ark-of-the-covenant",
      "title": "The Ark of the Covenant",
      "image": {
        "alt": "Full sentence describing the whole image for screen readers.",
        "credit": "AI-generated illustration",
        "width": 1200,
        "height": 900,
        "fallback": "img/illustrations/ark-of-the-covenant/ark-1200.jpg",
        "sources": [
          { "type": "image/webp", "srcset": [
            { "path": "img/illustrations/ark-of-the-covenant/ark-1200.webp", "width": 1200 },
            { "path": "img/illustrations/ark-of-the-covenant/ark-800.webp",  "width": 800 }
          ]}
        ]
      },
      "steps": [
        {
          "id": "keruvim",
          "hebrew": "כְּרֻבִים",
          "translit": "keruvim",
          "gloss": "cherubim",
          "note": "Two cherubim of hammered gold rise from the two ends of the cover.",
          "dim": 0.7,
          "passages": [
            { "book": "Exodus", "start": {"chapter": 25, "verse": 18}, "end": {"chapter": 25, "verse": 19} },
            { "book": "Exodus", "start": {"chapter": 37, "verse": 7},  "end": {"chapter": 37, "verse": 8} }
          ],
          "regions": [
            { "kind": "rect", "x": 29.5, "y": 6.5, "w": 24, "h": 32, "rx": 6 },
            { "kind": "rect", "x": 53,   "y": 7.5, "w": 21, "h": 31, "rx": 6 }
          ]
        }
      ]
    }
  ]
}
```

**Field reference**

- `image.width` / `image.height` — the master's real pixel size (drives the
  responsive `sizes`/aspect and the panel strip height).
- `passages[].book` — any casing; normalized to the canonical book name.
- Region `kind` is `rect` (`x, y, w, h`, optional `rx` corner radius) or
  `ellipse` (`cx, cy, rx, ry`); **all values are percentages 0–100** and must
  stay in bounds (`x + w ≤ 100`, `cx ± rx` within 0–100, …).
- `dim` — optional, default 0.55, range (0, 1].
- `label` — optional per-step override for the reference string (otherwise it's
  computed per chapter, e.g. `25:18–19` vs `37:7–8`).

## Step 5 — Validate

```bash
pytest tests/test_illustration_catalog.py
```

This strictly checks the committed catalog: unique ids, real book names,
in-bounds chapters/verses and regions, `dim` range, and that **every image file
exists**. The runtime loader is lenient (a bad scene is logged and skipped so it
can't crash startup), so this test is what turns an authoring mistake into a red
build instead of a silently missing panel.

Then run the app and scroll the chapter to see it:

```bash
python run.py    # http://localhost:5000/?book=Exodus&chapter=25
```
