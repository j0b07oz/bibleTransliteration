"""
Pytest configuration and fixtures for testing the Bible transliteration application.
"""
import os
import sys
import pytest
import json
import tempfile

# Add parent directory to path to import app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app as flask_app
from app import routes  # Import routes to register them with Flask


@pytest.fixture
def app():
    """Create and configure a test Flask application instance."""
    flask_app.config.update({
        'TESTING': True,
        'SECRET_KEY': 'test-secret-key',
        'WTF_CSRF_ENABLED': False
    })
    yield flask_app


@pytest.fixture
def client(app):
    """Create a test client for the Flask application."""
    return app.test_client()


@pytest.fixture
def runner(app):
    """Create a test CLI runner for the Flask application."""
    return app.test_cli_runner()


@pytest.fixture
def sample_strongs_dict():
    """Sample Strong's dictionary for testing."""
    return {
        "H7225": {
            "translations": ["beginning", "first"],
            "color": "#FF5733"
        },
        "H430": {
            "translations": ["God", "god"],
            "color": "#3498DB"
        },
        "H1254": {
            "translations": ["created", "create"],
            "color": "#2ECC71"
        }
    }


@pytest.fixture
def sample_strongs_data():
    """Sample Strong's concordance data for testing."""
    return [
        {
            "number": "H7225",
            "xlit": "re'shiyth",
            "lemma": "רֵאשִׁית",
            "pronounce": "ray-sheeth",
            "description": "the first, in place, time, order or rank"
        },
        {
            "number": "H430",
            "xlit": "'elohiym",
            "lemma": "אֱלֹהִים",
            "pronounce": "el-o-heem",
            "description": "gods in the ordinary sense; but specifically used of the supreme God"
        },
        {
            "number": "H1254",
            "xlit": "bara'",
            "lemma": "בָּרָא",
            "pronounce": "baw-raw",
            "description": "to create; to cut down"
        }
    ]


@pytest.fixture
def sample_kjv_data():
    """Sample KJV Bible data for testing."""
    return {
        "verses": [
            {
                "book": 1,
                "book_name": "Genesis",
                "chapter": 1,
                "verse": 1,
                "text": "In the beginning{H7225} God{H430} created{H1254} the heaven and the earth."
            },
            {
                "book": 1,
                "book_name": "Genesis",
                "chapter": 1,
                "verse": 2,
                "text": "And the earth was without form, and void; and darkness was upon the face of the deep."
            }
        ]
    }


@pytest.fixture
def sample_bible_data(sample_strongs_data, sample_kjv_data):
    """A BibleData instance built from the in-memory sample fixtures.

    Lets transliteration tests exercise the real code path (which now takes a
    BibleData) without loading the full 14 MB of on-disk data.
    """
    from app.data import build_bible_data
    return build_bible_data(sample_strongs_data, sample_kjv_data)


@pytest.fixture
def temp_session_file():
    """Create a temporary session file for testing."""
    fd, path = tempfile.mkstemp(suffix='.json', dir='.')
    os.close(fd)
    yield path
    # Cleanup
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture(autouse=True)
def clean_uploads():
    """Remove any files a test writes to app/uploads/ (incl. shared lists).

    With the dictionary now persisted to disk (not the session cookie),
    routes like /edit_dict and /upload_dict create {user_id}.json files, and
    /share_dict creates content-addressed files under uploads/shared/.
    Snapshot both directories before the test and delete anything new after,
    so the suite doesn't accumulate stray files between runs.
    """
    from app.routes import UPLOAD_DATA_DIR, SHARED_DATA_DIR

    def snapshot(directory):
        return set(os.listdir(directory)) if os.path.isdir(directory) else set()

    def sweep(directory, before):
        if not os.path.isdir(directory):
            return
        for name in os.listdir(directory):
            if name not in before:
                path = os.path.join(directory, name)
                try:
                    if os.path.isfile(path):
                        os.remove(path)
                except OSError:
                    pass

    before_uploads = snapshot(UPLOAD_DATA_DIR)
    before_shared = snapshot(SHARED_DATA_DIR)
    yield
    sweep(UPLOAD_DATA_DIR, before_uploads)
    sweep(SHARED_DATA_DIR, before_shared)
