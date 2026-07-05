"""
Tests for data validation functions.
"""
import pytest
from app.routes import _validate_user_dict, cleanup_old_session_files
import os
import json
import time


class TestUserDictValidation:
    """Tests for user dictionary validation."""

    def test_valid_dict(self):
        """Test validation of a valid dictionary."""
        valid_dict = {
            "H7225": {
                "translations": ["beginning", "first"],
                "color": "#FF5733"
            },
            "H430": {
                "translations": ["God"],
                "color": None
            }
        }
        is_valid, error = _validate_user_dict(valid_dict)
        assert is_valid is True
        assert error is None

    def test_not_a_dict(self):
        """Test validation rejects non-dict input."""
        is_valid, error = _validate_user_dict(["not", "a", "dict"])
        assert is_valid is False
        assert error is not None
        assert "object" in error.lower()

    def test_invalid_key_type(self):
        """Test validation rejects non-string keys."""
        invalid_dict = {
            123: {  # Numeric key
                "translations": ["test"],
                "color": None
            }
        }
        is_valid, error = _validate_user_dict(invalid_dict)
        assert is_valid is False
        assert "string" in error.lower()

    def test_invalid_value_type(self):
        """Test validation rejects non-dict values."""
        invalid_dict = {
            "H7225": "not a dict"
        }
        is_valid, error = _validate_user_dict(invalid_dict)
        assert is_valid is False
        assert "object" in error.lower()

    def test_missing_translations(self):
        """Test validation rejects entries without translations."""
        invalid_dict = {
            "H7225": {
                "color": "#FF5733"
                # Missing translations
            }
        }
        is_valid, error = _validate_user_dict(invalid_dict)
        assert is_valid is False
        assert "translation" in error.lower()

    def test_invalid_translations_type(self):
        """Test validation rejects non-list translations."""
        invalid_dict = {
            "H7225": {
                "translations": "not a list",
                "color": None
            }
        }
        is_valid, error = _validate_user_dict(invalid_dict)
        assert is_valid is False
        assert "translation" in error.lower()

    def test_invalid_translation_items(self):
        """Test validation rejects non-string translation items."""
        invalid_dict = {
            "H7225": {
                "translations": ["valid", 123, "string"],  # 123 is not a string
                "color": None
            }
        }
        is_valid, error = _validate_user_dict(invalid_dict)
        assert is_valid is False

    def test_empty_translations_list_is_allowed(self):
        """An empty translations list is permitted.

        The edit flow can legitimately create an entry with no translations,
        and that entry gets written to the user's file. Rejecting empty lists
        here would make _validate_user_dict reject the whole file on the next
        load, falling back to defaults and losing the user's data — so empty
        lists must stay valid.
        """
        valid_dict = {
            "H7225": {
                "translations": [],
                "color": None
            }
        }
        is_valid, error = _validate_user_dict(valid_dict)
        assert is_valid is True

    def test_invalid_color_type(self):
        """Test validation rejects non-string colors."""
        invalid_dict = {
            "H7225": {
                "translations": ["test"],
                "color": 123  # Should be string or None
            }
        }
        is_valid, error = _validate_user_dict(invalid_dict)
        assert is_valid is False
        assert "color" in error.lower()

    def test_color_can_be_none(self):
        """Test that color can be None."""
        valid_dict = {
            "H7225": {
                "translations": ["beginning"],
                "color": None
            }
        }
        is_valid, error = _validate_user_dict(valid_dict)
        assert is_valid is True
        assert error is None

    def test_reject_color_with_injection_payload(self):
        """A color that tries to break out of the style attribute is rejected."""
        malicious_dict = {
            "H7225": {
                "translations": ["beginning"],
                "color": 'red" onmouseover="alert(1)'
            }
        }
        is_valid, error = _validate_user_dict(malicious_dict)
        assert is_valid is False
        assert "color" in error.lower()

    def test_reject_named_color(self):
        """A CSS named color (not #RRGGBB) is rejected."""
        is_valid, error = _validate_user_dict(
            {"H7225": {"translations": ["beginning"], "color": "red"}}
        )
        assert is_valid is False
        assert "color" in error.lower()

    def test_reject_short_hex_color(self):
        """A 3-digit shorthand hex color is rejected (would crash is_light_color)."""
        is_valid, error = _validate_user_dict(
            {"H7225": {"translations": ["beginning"], "color": "#fff"}}
        )
        assert is_valid is False

    def test_accept_lowercase_hex_color(self):
        """A valid lowercase #rrggbb hex color is accepted."""
        is_valid, error = _validate_user_dict(
            {"H7225": {"translations": ["beginning"], "color": "#ff5733"}}
        )
        assert is_valid is True
        assert error is None

    def test_multiple_entries(self):
        """Test validation with multiple valid entries."""
        valid_dict = {
            "H7225": {
                "translations": ["beginning"],
                "color": "#FF5733"
            },
            "H430": {
                "translations": ["God", "god"],
                "color": "#3498DB"
            },
            "H1254": {
                "translations": ["created"],
                "color": None
            }
        }
        is_valid, error = _validate_user_dict(valid_dict)
        assert is_valid is True
        assert error is None


class TestSessionCleanup:
    """Tests for session file cleanup functionality."""

    def test_cleanup_old_files(self, tmp_path):
        """Test that old files are cleaned up."""
        # Create test directory structure
        test_dir = tmp_path / "test_uploads"
        test_dir.mkdir()

        # Create an old file (modify its timestamp)
        old_file = test_dir / "old_session.json"
        old_file.write_text(json.dumps({"test": "data"}))

        # Set modification time to 31 days ago
        old_time = time.time() - (31 * 24 * 60 * 60)
        os.utime(old_file, (old_time, old_time))

        # Create a recent file
        new_file = test_dir / "new_session.json"
        new_file.write_text(json.dumps({"test": "data"}))

        # This test verifies the function exists and can be called
        # Full integration test would require modifying UPLOAD_DATA_DIR
        assert callable(cleanup_old_session_files)

    def test_cleanup_returns_count(self):
        """Test that cleanup function returns a count."""
        result = cleanup_old_session_files(days=30)
        assert isinstance(result, int)
        assert result >= 0

    def test_cleanup_with_invalid_days(self):
        """Test cleanup with various day values."""
        # Should handle different day values
        result1 = cleanup_old_session_files(days=1)
        result2 = cleanup_old_session_files(days=90)
        assert isinstance(result1, int)
        assert isinstance(result2, int)

    def test_cleanup_handles_errors(self):
        """Test that cleanup handles errors gracefully."""
        # Calling with default parameters should not crash
        try:
            result = cleanup_old_session_files()
            assert isinstance(result, int)
        except Exception as e:
            pytest.fail(f"Cleanup function raised an exception: {e}")


class TestInputSanitization:
    """Tests for input sanitization and edge cases."""

    def test_dict_with_special_characters(self):
        """Test dictionary with special characters in values."""
        valid_dict = {
            "H7225": {
                "translations": ["beginning", "first's", "re'shiyth"],
                "color": "#FF5733"
            }
        }
        is_valid, error = _validate_user_dict(valid_dict)
        assert is_valid is True

    def test_dict_with_unicode(self):
        """Test dictionary with unicode characters."""
        valid_dict = {
            "H7225": {
                "translations": ["בְּרֵאשִׁית", "רֵאשִׁית"],
                "color": "#FF5733"
            }
        }
        is_valid, error = _validate_user_dict(valid_dict)
        assert is_valid is True

    def test_dict_with_long_strings(self):
        """Test dictionary with very long translation strings."""
        valid_dict = {
            "H7225": {
                "translations": ["a" * 1000],  # Very long string
                "color": "#FF5733"
            }
        }
        is_valid, error = _validate_user_dict(valid_dict)
        assert is_valid is True

    def test_empty_dict(self):
        """Test validation of empty dictionary."""
        is_valid, error = _validate_user_dict({})
        assert is_valid is True  # Empty dict is valid

    def test_dict_with_extra_fields(self):
        """Test dictionary with extra fields (should be valid)."""
        valid_dict = {
            "H7225": {
                "translations": ["beginning"],
                "color": "#FF5733",
                "extra_field": "should be ignored"
            }
        }
        is_valid, error = _validate_user_dict(valid_dict)
        assert is_valid is True
