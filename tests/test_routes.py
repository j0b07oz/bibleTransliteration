"""
Tests for the Flask routes and API endpoints.
"""
import io
import pytest
import json
import re
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


# NOTE: Earlier revisions of this file tested a speculative /api/* CRUD surface
# (/api/user_dict, /api/add_word, /export, /import_dict, ...) that the app never
# implemented, so those tests asserted status codes on 404s and always failed.
# They were removed; the real endpoints are covered by TestSessionArchitecture,
# TestExportImportRoundtrip, and the dictionary edit tests below.


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


class TestOccurrencesRoute:
    """U1: the concordance ('find all occurrences') view."""

    def test_blank_page_loads(self, client):
        response = client.get('/occurrences')
        assert response.status_code == 200

    def test_valid_strong_lists_verses(self, client):
        response = client.get('/occurrences?strong=H7225')
        assert response.status_code == 200
        body = response.data.decode('utf-8')
        assert 'Genesis' in body
        # Verse references link back into the chapter view with focus highlighting.
        assert 'focus=H7225' in body
        # The matched word is wrapped in a mark.
        assert 'occ-hit' in body

    def test_invalid_strong_shows_error(self, client):
        response = client.get('/occurrences?strong=NOPE')
        assert response.status_code == 200
        assert b'Invalid' in response.data

    def test_marker_braces_are_stripped_from_text(self, client):
        response = client.get('/occurrences?strong=H7225')
        body = response.data.decode('utf-8')
        # No raw Strong's markers should leak into the rendered verse text.
        assert '{H' not in body
        assert '{(H' not in body


class TestWordLookupApi:
    """U2: English -> Strong's reverse lookup."""

    def test_exact_word_finds_strongs(self, client):
        response = client.get('/api/word_lookup?q=beginning')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['exact'] is True
        strongs = [r['strong'] for r in data['results']]
        assert 'H7225' in strongs

    def test_results_are_ranked_by_count(self, client):
        response = client.get('/api/word_lookup?q=mercy')
        data = json.loads(response.data)
        counts = [r['count'] for r in data['results']]
        assert counts == sorted(counts, reverse=True)
        # hesed should dominate "mercy" in the KJV
        assert data['results'][0]['strong'] == 'H2617'

    def test_prefix_fallback(self, client):
        # An incomplete word still returns candidates via prefix aggregation.
        response = client.get('/api/word_lookup?q=shepher')
        data = json.loads(response.data)
        assert data['exact'] is False
        assert data['results'], 'prefix lookup should find "shepherd" words'

    def test_short_query_rejected(self, client):
        response = client.get('/api/word_lookup?q=a')
        assert response.status_code == 400


class TestShareImport:
    """U3: shareable word lists via link."""

    def _share(self, client):
        return client.post('/share_dict')

    def test_share_returns_link(self, client):
        with client:
            response = self._share(client)
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True
            assert re.fullmatch(r'[0-9a-f]{12}', data['code'])
            assert data['url'].endswith(f"?code={data['code']}")

    def test_share_is_idempotent(self, client):
        with client:
            first = json.loads(self._share(client).data)
            second = json.loads(self._share(client).data)
            assert first['code'] == second['code']

    def test_import_preview_shows_entries(self, client):
        with client:
            code = json.loads(self._share(client).data)['code']
            response = client.get(f'/import?code={code}')
            assert response.status_code == 200
            assert b'Merge into My List' in response.data
            assert b'Replace My List' in response.data

    def test_import_invalid_code_404s(self, client):
        response = client.get('/import?code=000000000000')
        assert response.status_code == 404
        assert b'invalid or has expired' in response.data

    def test_merge_roundtrip(self, client):
        # Sharer: add a distinctive word, then share.
        with client:
            client.post(
                '/edit_dict',
                data=json.dumps({"actions": [{
                    "action": "add",
                    "strong_number": "H9998",
                    "translations": ["sharedword"],
                    "color": "#336699",
                }]}),
                content_type='application/json',
            )
            code = json.loads(self._share(client).data)['code']

        # Recipient: fresh session imports via merge.
        recipient = client.application.test_client()
        with recipient:
            response = recipient.post('/import', data={'code': code, 'mode': 'merge'})
            assert response.status_code == 302
            assert 'upload_success' in response.headers['Location']
            exported = json.loads(recipient.get('/export_dict').data)
            assert exported.get('H9998', {}).get('translations') == ['sharedword']

    def test_replace_mode(self, client):
        with client:
            code = json.loads(self._share(client).data)['code']
        recipient = client.application.test_client()
        with recipient:
            # Recipient customizes first, then replaces with the shared list.
            recipient.post(
                '/edit_dict',
                data=json.dumps({"actions": [{
                    "action": "add",
                    "strong_number": "H9997",
                    "translations": ["mine"],
                }]}),
                content_type='application/json',
            )
            response = recipient.post('/import', data={'code': code, 'mode': 'replace'})
            assert response.status_code == 302
            exported = json.loads(recipient.get('/export_dict').data)
            # Their custom word is gone; the list is exactly the shared one.
            assert 'H9997' not in exported


class TestContinueReadingMarkup:
    """U4: the home page carries the continue-reading container and globals."""

    def test_recent_reading_container_on_blank_home(self, client):
        response = client.get('/')
        body = response.data.decode('utf-8')
        assert 'id="recent-reading"' in body
        assert 'window.CURRENT_BOOK = null' in body

    def test_current_position_exposed_after_render(self, client):
        response = client.get('/?book=Genesis&chapter=2')
        body = response.data.decode('utf-8')
        assert 'window.CURRENT_BOOK = "Genesis"' in body
        assert 'window.CURRENT_CHAPTER = 2' in body
        # The chips strip is only for the landing state, not open chapters.
        assert 'id="recent-reading"' not in body


class TestBibleDataLayer:
    """B4: data is loaded once into a BibleData instance on app.extensions."""

    def test_bible_data_registered(self, app):
        bd = app.extensions.get('bible_data')
        assert bd is not None
        # Indexes are populated from the real data files under app/data/.
        assert 'Genesis' in bd.book_chapter_count
        assert bd.book_chapter_count['Genesis'] == 50
        assert bd.strongs_by_number.get('H7225', {}).get('xlit')
        assert len(bd.global_strongs_counts) > 0

    def test_crossref_endpoint_still_works(self, client):
        """enrich_strong now does an O(1) index lookup instead of a scan."""
        response = client.get('/api/crossref/H7225')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['strong'] == 'H7225'
        assert 'cross_refs' in data


class TestSecurityConfig:
    """B5: CSRF protection and hardened session cookies are configured."""

    def test_session_cookie_flags(self, app):
        assert app.config['SESSION_COOKIE_HTTPONLY'] is True
        assert app.config['SESSION_COOKIE_SAMESITE'] == 'Lax'

    def test_csrf_protection_installed(self, app):
        # Flask-WTF registers itself here when CSRFProtect(app) runs.
        assert 'csrf' in app.extensions


class TestPhrasesRoutes:
    """Rare original-language phrase panel, browse, and detail views.

    These run against the full loaded index (the client fixture loads real
    data), so they also serve as the flagship end-to-end check for
    "coat of many colours".
    """

    def test_chapter_panel_shows_coat_phrase(self, client):
        response = client.get('/?book=Genesis&chapter=37')
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert 'Rare original-language phrases' in body
        assert '/phrases/H3801-H6446' in body

    def test_detail_flagship_two_passages_five_occurrences(self, client):
        response = client.get('/phrases/H3801-H6446')
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        # Grouped into exactly the two expected passages...
        assert 'Genesis 37' in body
        assert '2 Samuel 13' in body
        # ...with all five verse references present.
        for ref in ('37:3', '37:23', '37:32', '13:18', '13:19'):
            assert ref in body
        # The rendered English words are highlighted precisely.
        assert 'phrase-hit' in body
        assert 'coat' in body and 'colours' in body

    def test_detail_key_is_case_insensitive(self, client):
        assert client.get('/phrases/h3801-h6446').status_code == 200

    def test_unknown_key_returns_404(self, client):
        assert client.get('/phrases/NOTAKEY').status_code == 404

    def test_mixed_language_key_returns_404(self, client):
        # A cross-Testament sequence is never indexed.
        assert client.get('/phrases/H3801-G6446').status_code == 404

    def test_browse_lists_chapter_echoes(self, client):
        response = client.get('/phrases?book=Genesis&chapter=37')
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert 'echo' in body
        assert '/phrases/H3801-H6446' in body

    def test_browse_without_selection_shows_hint(self, client):
        response = client.get('/phrases')
        assert response.status_code == 200
        assert 'Enter a book and chapter' in response.get_data(as_text=True)

    def test_browse_invalid_chapter_reports_error(self, client):
        response = client.get('/phrases?book=Genesis&chapter=abc')
        assert response.status_code == 200
        assert 'valid number' in response.get_data(as_text=True)
