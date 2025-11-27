# Bible Transliteration

This repository contains a Flask application for transliterating Bible content.

## Installation

1. Create and activate a Python 3.10+ virtual environment.
2. Upgrade packaging tools to ensure wheels are preferred over source builds:
   ```bash
   pip install --upgrade pip setuptools wheel
   ```
3. Install project dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Precomputing sound annotations

The UI can highlight repeated sounds when `app/static/sound_annotations.json` is
populated. If that file is missing or empty and you have the source datasets
available, the app will attempt to auto-build annotations at startup when the
following environment variables are set:

* `SOUND_ANNOTATIONS_BIBLE_PATH` – tokenized Bible JSON input
* `SOUND_ANNOTATIONS_LEXICON_PATH` – lexicon JSON that provides roots/initials
* `SOUND_ANNOTATIONS_UNITS_PATH` (optional) – literary unit ranges; defaults to
  `bible_bsb_book_outlines_with_ranges.json`

You can also run the builder directly:

```bash
python build_sound_annotations.py \
  --bible "$SOUND_ANNOTATIONS_BIBLE_PATH" \
  --lexicon "$SOUND_ANNOTATIONS_LEXICON_PATH" \
  --units "$SOUND_ANNOTATIONS_UNITS_PATH" \
  --out app/static/sound_annotations.json
```

### Windows note: Microsoft Visual C++ build tools
Some dependencies (for example, `cryptography` and `cffi`) compile C extensions when
prebuilt wheels are unavailable. On Windows, pip may emit an error like:
`DistutilsPlatformError: Microsoft Visual C++ 14.0 or greater is required.`

If you see this message:
1. Install the **Microsoft C++ Build Tools** from the official download page:
   https://visualstudio.microsoft.com/visual-cpp-build-tools/
2. During installation, select the "Desktop development with C++" workload to get the
   required compiler and Windows SDK.
3. Restart your terminal and re-run the installation command:
   ```bash
   pip install -r requirements.txt
   ```

This provides the MSVC toolchain needed for pip to build any packages that ship C
extensions when wheels are not available for your Python version or platform.
