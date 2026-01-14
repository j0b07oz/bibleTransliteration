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

## Running the Application

To run the development server:
```bash
python run.py
```

The application will be available at `http://localhost:5000`

## Configuration

Set the `SECRET_KEY` environment variable for production:
```bash
export SECRET_KEY="your-production-secret-key"
```

## Testing

This project uses pytest for testing. To run the tests:

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=app --cov-report=term-missing

# Run specific test file
pytest tests/test_transliteration.py

# Run tests in verbose mode
pytest -v

# Generate HTML coverage report
pytest --cov=app --cov-report=html
```

The HTML coverage report will be available in `htmlcov/index.html`

### Test Structure

- `tests/test_transliteration.py` - Tests for core transliteration logic
- `tests/test_routes.py` - Tests for Flask routes and API endpoints
- `tests/test_validation.py` - Tests for data validation functions
