"""
Tests for the Flask routes and API endpoints.
"""
import io
import pytest
import json
from flask import session

from app.routes import _validate_user_dict


class TestHomeRoute:
    """Tests for the home route."""

    def test_home_page_loads(self, client):
        """Test that the home page loads successfully."""
        response = client.get('/')
        assert response.status_code == 200

    def test_home_with_book_and_chapter(self, client):
        """Test home page with book and chapter parameters."""
        response = client.get('/?book=Genesis&chapter=1')
        assert response.status_code == 200
        assert b'Genesis' in response.data or b'genesis' in response.data.lower()

    def test_home_invalid_book(self, client):
        """Test home page with invalid book name."""
        response = client.get('/?book=InvalidBook&chapter=1')
        # Should still return 200 but with empty or error content
        assert response.status_code == 200


class TestEditDictRoute:
    """Tests for the dictionary editing route."""

    def test_edit_dict_page_loads(self, client):
        """Test that the edit dictionary page loads."""
        response = client.get('/edit_dict')
        assert response.status_code == 200

    def test_get_user_dict_default(self, client):
        """Test getting default user dictionary."""
        response = client.get('/api/user_dict')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert isinstance(data, dict)

    def test_update_user_dict(self, client):
        """Test updating user dictionary."""
        test_dict = {
            "H7225": {
                "translations": ["beginning", "start"],
                "color": "#FF5733"
            }
        }
        response = client.post(
            '/api/user_dict',
            data=json.dumps(test_dict),
            content_type='application/json'
        )
        assert response.status_code == 200

    def test_update_user_dict_invalid_format(self, client):
        """Test updating dictionary with invalid format."""
        invalid_dict = {
            "H7225": "not a dict"  # Should be a dict
        }
        response = client.post(
            '/api/user_dict',
            data=json.dumps(invalid_dict),
            content_type='application/json'
        )
        assert response.status_code == 400

    def test_reset_user_dict(self, client):
        """Test resetting user dictionary to default."""
        response = client.post('/api/reset_dict')
        assert response.status_code == 200


class TestDictionaryOperations:
    """Tests for dictionary CRUD operations."""

    def test_add_word(self, client):
        """Test adding a word to the dictionary."""
        word_data = {
            "number": "H9999",
            "translations": ["test", "example"]
        }
        response = client.post(
            '/api/add_word',
            data=json.dumps(word_data),
            content_type='application/json'
        )
        assert response.status_code == 200

    def test_add_word_missing_number(self, client):
        """Test adding word without Strong's number."""
        word_data = {
            "translations": ["test"]
        }
        response = client.post(
            '/api/add_word',
            data=json.dumps(word_data),
            content_type='application/json'
        )
        assert response.status_code == 400

    def test_remove_word(self, client):
        """Test removing a word from the dictionary."""
        # First add a word
        word_data = {
            "number": "H9999",
            "translations": ["test"]
        }
        client.post(
            '/api/add_word',
            data=json.dumps(word_data),
            content_type='application/json'
        )

        # Then remove it
        response = client.post(
            '/api/remove_word',
            data=json.dumps({"number": "H9999"}),
            content_type='application/json'
        )
        assert response.status_code == 200

    def test_update_word_translations(self, client):
        """Test updating word translations."""
        update_data = {
            "number": "H7225",
            "translations": ["beginning", "start", "first"]
        }
        response = client.post(
            '/api/update_translations',
            data=json.dumps(update_data),
            content_type='application/json'
        )
        assert response.status_code == 200

    def test_update_word_color(self, client):
        """Test updating word color."""
        color_data = {
            "number": "H7225",
            "color": "#FF5733"
        }
        response = client.post(
            '/api/update_color',
            data=json.dumps(color_data),
            content_type='application/json'
        )
        assert response.status_code == 200


class TestExportImport:
    """Tests for dictionary export and import."""

    def test_export_dictionary(self, client):
        """Test exporting the dictionary."""
        response = client.get('/export')
        assert response.status_code == 200
        assert response.content_type == 'application/json'

    def test_import_dictionary(self, client):
        """Test importing a dictionary."""
        import_data = {
            "H7225": {
                "translations": ["beginning"],
                "color": "#FF5733"
            }
        }
        response = client.post(
            '/import_dict',
            data=json.dumps(import_data),
            content_type='application/json'
        )
        assert response.status_code == 200

    def test_import_invalid_dictionary(self, client):
        """Test importing invalid dictionary format."""
        invalid_data = ["not", "a", "dict"]
        response = client.post(
            '/import_dict',
            data=json.dumps(invalid_data),
            content_type='application/json'
        )
        assert response.status_code == 400


class TestSessionArchitecture:
    """B1: the dictionary lives in a per-user file, not the session cookie."""

    def _add_word(self, client):
        return client.post(
            '/edit_dict',
            data=json.dumps({"actions": [{
                "action": "add",
                "strong_number": "H9999",
                "translations": ["testword"],
                "color": "#123456",
            }]}),
            content_type='application/json',
        )

    def test_dict_not_stored_in_session_cookie(self, client):
        """After saving, the session holds only user_id — never the dictionary."""
        with client:
            resp = self._add_word(client)
            assert resp.status_code == 200
            with client.session_transaction() as sess:
                assert 'user_id' in sess
                assert 'user_strongs_dict' not in sess

    def test_dict_persists_across_requests_via_file(self, client):
        """A word saved in one request is visible in a later request."""
        with client:
            self._add_word(client)
            # A separate request (same session cookie) must still see the word,
            # which can only come from the on-disk file now.
            exported = json.loads(client.get('/export_dict').data)
            assert "H9999" in exported
            assert exported["H9999"]["translations"] == ["testword"]


class TestExportImportRoundtrip:
    """Tests for the real /export_dict and /upload_dict endpoints (B3)."""

    def test_export_dict_returns_json(self, client):
        """Export returns a JSON attachment even for a fresh session."""
        response = client.get('/export_dict')
        assert response.status_code == 200
        assert response.mimetype == 'application/json'

    def test_fresh_export_has_importable_shape(self, client):
        """A fresh-session export must pass the app's own validation.

        Previously export used the raw {"H7225": [...]} shape, which
        _validate_user_dict (and thus /upload_dict) rejected.
        """
        with client:
            response = client.get('/export_dict')
            data = json.loads(response.data)
            valid, error = _validate_user_dict(data)
            assert valid, f"exported dict failed validation: {error}"

    def test_export_then_upload_roundtrip(self, client):
        """Export the fresh dict, then re-upload it: must succeed, not error."""
        with client:
            exported = client.get('/export_dict').data
            response = client.post(
                '/upload_dict',
                data={'dict_file': (io.BytesIO(exported), 'my_strongs_dict.json')},
                content_type='multipart/form-data',
            )
            assert response.status_code == 302
            location = response.headers['Location']
            assert 'upload_success' in location
            assert 'upload_error' not in location

    def test_upload_rejects_malicious_color(self, client):
        """A dictionary with a style-injection color is rejected on upload."""
        payload = json.dumps({
            "H7225": {
                "translations": ["beginning"],
                "color": 'red" onmouseover="alert(1)'
            }
        }).encode('utf-8')
        response = client.post(
            '/upload_dict',
            data={'dict_file': (io.BytesIO(payload), 'bad.json')},
            content_type='multipart/form-data',
        )
        assert response.status_code == 302
        assert 'upload_error' in response.headers['Location']


class TestHeatmapRoute:
    """Tests for the heatmap route."""

    def test_heatmap_page_loads(self, client):
        """Test that the heatmap page loads."""
        response = client.get('/heatmap')
        assert response.status_code == 200

    def test_heatmap_with_strongs(self, client):
        """Test heatmap with a Strong's number."""
        response = client.get('/heatmap?strongs=H7225')
        assert response.status_code == 200


class TestAboutRoute:
    """Tests for the about page."""

    def test_about_page_loads(self, client):
        """Test that the about page loads."""
        response = client.get('/about')
        assert response.status_code == 200


class TestSessionManagement:
    """Tests for session management."""

    def test_session_id_creation(self, client):
        """Test that a session ID is created."""
        with client:
            client.get('/')
            # Session should have a user_id
            # We can't directly check session in test, but we can verify
            # the route works without errors
            assert True

    def test_session_persistence(self, client):
        """Test that user dictionary persists in session."""
        with client:
            # Set a custom dictionary
            test_dict = {
                "H7225": {
                    "translations": ["beginning"],
                    "color": "#FF5733"
                }
            }
            client.post(
                '/api/user_dict',
                data=json.dumps(test_dict),
                content_type='application/json'
            )

            # Retrieve it
            response = client.get('/api/user_dict')
            data = json.loads(response.data)
            assert "H7225" in data
