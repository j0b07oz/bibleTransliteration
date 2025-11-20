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
