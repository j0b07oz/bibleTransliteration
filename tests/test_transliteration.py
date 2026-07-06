"""
Tests for the transliteration module.
"""
import re

import pytest
from app.transliteration import (
    extract_strongs_numbers,
    generate_color_from_strongs,
    generate_repeat_colors,
    is_valid_hex_color,
    transliterate_chapter
)


class TestExtractStrongsNumbers:
    """Tests for extracting Strong's numbers from text."""

    def test_extract_single_strongs(self):
        """Test extracting a single Strong's number."""
        text = "In the beginning{H7225}"
        result = extract_strongs_numbers(text)
        assert result == ["H7225"]

    def test_extract_multiple_strongs(self):
        """Test extracting multiple Strong's numbers."""
        text = "In{H1234} the beginning{H7225} God{H430} created{H1254}"
        result = extract_strongs_numbers(text)
        assert result == ["H1234", "H7225", "H430", "H1254"]

    def test_extract_greek_strongs(self):
        """Test extracting Greek Strong's numbers."""
        text = "In{G1722} the beginning{G746}"
        result = extract_strongs_numbers(text)
        assert result == ["G1722", "G746"]

    def test_extract_mixed_strongs(self):
        """Test extracting both Hebrew and Greek Strong's numbers."""
        text = "Word{H1234} and{G2532} word"
        result = extract_strongs_numbers(text)
        assert result == ["H1234", "G2532"]

    def test_extract_no_strongs(self):
        """Test text with no Strong's numbers."""
        text = "Plain text with no markup"
        result = extract_strongs_numbers(text)
        assert result == []

    def test_extract_duplicate_strongs(self):
        """Test that duplicate numbers are preserved."""
        text = "Word{H1234} and{H1234} word{H1234}"
        result = extract_strongs_numbers(text)
        assert result == ["H1234", "H1234", "H1234"]


class TestColorGeneration:
    """Tests for color generation functions."""

    def test_generate_color_consistency(self):
        """Test that same Strong's number generates same color."""
        color1 = generate_color_from_strongs("H7225")
        color2 = generate_color_from_strongs("H7225")
        assert color1 == color2

    def test_generate_different_colors(self):
        """Test that different Strong's numbers generate different colors."""
        color1 = generate_color_from_strongs("H7225")
        color2 = generate_color_from_strongs("H430")
        assert color1 != color2

    def test_generate_color_format(self):
        """Test that generated colors are valid hex format."""
        color = generate_color_from_strongs("H7225")
        assert isinstance(color, str)
        assert color.startswith("#")
        assert len(color) == 7  # #RRGGBB

    def test_generate_repeat_colors(self):
        """Test generation of base and accent colors for repeated words."""
        base, accent = generate_repeat_colors("H7225")
        assert isinstance(base, str)
        assert isinstance(accent, str)
        assert base.startswith("#")
        assert accent.startswith("#")
        assert len(base) == 7
        assert len(accent) == 7

    def test_repeat_colors_different(self):
        """Test that base and accent colors are different."""
        base, accent = generate_repeat_colors("H7225")
        assert base != accent


class TestTransliterateChapter:
    """Tests for the main transliterate_chapter function."""

    def test_basic_transliteration(self, sample_strongs_dict, sample_bible_data):
        """Test basic chapter transliteration."""
        result = transliterate_chapter(
            book="Genesis",
            chapter=1,
            strongs_dict=sample_strongs_dict,
            bible_data=sample_bible_data
        )
        # Should return HTML string
        assert isinstance(result, str)
        assert len(result) > 0

    def test_transliteration_contains_verses(self, sample_strongs_dict, sample_bible_data):
        """Test that transliteration includes verse content."""
        result = transliterate_chapter(
            book="Genesis",
            chapter=1,
            strongs_dict=sample_strongs_dict,
            bible_data=sample_bible_data
        )
        # Should contain verse numbers and text
        assert "1" in result  # Verse 1
        assert "beginning" in result.lower() or "re'shiyth" in result.lower()

    def test_invalid_book(self, sample_strongs_dict, sample_bible_data):
        """Test transliteration with invalid book name."""
        result = transliterate_chapter(
            book="InvalidBook",
            chapter=1,
            strongs_dict=sample_strongs_dict,
            bible_data=sample_bible_data
        )
        # Should return empty or minimal HTML
        assert isinstance(result, str)

    def test_invalid_chapter(self, sample_strongs_dict, sample_bible_data):
        """Test transliteration with invalid chapter number."""
        result = transliterate_chapter(
            book="Genesis",
            chapter=999,
            strongs_dict=sample_strongs_dict,
            bible_data=sample_bible_data
        )
        # Should return empty or minimal HTML
        assert isinstance(result, str)

    def test_empty_strongs_dict(self, sample_bible_data):
        """Test transliteration with empty Strong's dictionary."""
        result = transliterate_chapter(
            book="Genesis",
            chapter=1,
            strongs_dict={},
            bible_data=sample_bible_data
        )
        # Should still return valid HTML
        assert isinstance(result, str)
        assert len(result) > 0

    def test_max_repeated_highlights(self, sample_strongs_dict, sample_bible_data):
        """Test that max_repeated_highlights parameter works."""
        result1 = transliterate_chapter(
            book="Genesis",
            chapter=1,
            strongs_dict=sample_strongs_dict,
            bible_data=sample_bible_data,
            max_repeated_highlights=5
        )
        result2 = transliterate_chapter(
            book="Genesis",
            chapter=1,
            strongs_dict=sample_strongs_dict,
            bible_data=sample_bible_data,
            max_repeated_highlights=10
        )
        # Both should return valid HTML
        assert isinstance(result1, str)
        assert isinstance(result2, str)

    def test_active_units_parameter(self, sample_strongs_dict, sample_bible_data):
        """Test transliteration with active units."""
        # Active units should be a list of dicts or empty list
        result = transliterate_chapter(
            book="Genesis",
            chapter=1,
            strongs_dict=sample_strongs_dict,
            bible_data=sample_bible_data,
            active_units=[]
        )
        # Should return valid HTML
        assert isinstance(result, str)
        assert len(result) > 0

    def test_malformed_color_does_not_crash_or_inject(self, sample_bible_data):
        """A bad color left over in a dict must not 500 or break out of the style attr.

        Strict validation now blocks such colors at the door, but an older
        upload file could still hold one; build_span's guard is the safety net.
        """
        malicious_dict = {
            "H7225": {
                "translations": ["beginning"],
                "color": 'red" onmouseover="alert(1)'
            }
        }
        # Must not raise ValueError from is_light_color on the non-hex string.
        result = transliterate_chapter(
            book="Genesis",
            chapter=1,
            strongs_dict=malicious_dict,
            bible_data=sample_bible_data,
        )
        assert isinstance(result, str)
        # The injected handler must not appear in the rendered HTML.
        assert "onmouseover" not in result


class TestSinglePassTokenizer:
    """Regression tests for the single-pass rewrite (B7).

    These pin the behaviors verified by the full-Bible parity run against the
    old engine, including the corruption classes the rewrite fixes.
    """

    def _render(self, text, strongs_dict=None, strongs_data=None):
        from app.data import build_bible_data
        kjv = {"verses": [{
            "book": 1, "book_name": "Genesis", "chapter": 1, "verse": 1,
            "text": text,
        }]}
        bd = build_bible_data(strongs_data or [], kjv)
        return transliterate_chapter("Genesis", 1, strongs_dict or {}, bd)

    def test_no_substring_corruption(self):
        """'maid' and 'handmaid' with the same number must both stay whole.

        The old engine's replace-all split 'handmaid' into 'hand' + a span
        around 'maid' (and rendered 'shewlechem' in 1 Sam 21:6).
        """
        result = self._render("his maid{H8198} for an handmaid{H8198}.")
        assert '>maid</span>' in result
        assert '>handmaid</span>' in result
        assert 'hand<span' not in result

    def test_glued_particle_is_dropped(self):
        """{H853} glued after another marker never renders a span."""
        result = self._render("created{H1254}{(H8804)}{H853} the heaven.")
        assert 'data-strongs="H1254"' in result
        assert 'data-strongs="H853"' not in result
        assert '{' not in result

    def test_grammar_code_first_run_renders_plain(self):
        """A word attached to a grammar-code-first run stays plain text.

        Matches the original engine for e.g. 'hosts{(H8675)}{H6635}'
        (2 Kings 19:31).
        """
        result = self._render("the LORD of hosts{(H8675)}{H6635} shall do this.")
        assert 'hosts' in result
        assert 'data-strongs' not in result
        assert '{' not in result

    def test_malformed_marker_shape_is_stripped(self):
        """The {H8799)} data quirk neither renders nor leaks braces."""
        result = self._render("at unawares{H3045}{H8799)}{H3808}; and let him fall.")
        assert 'data-strongs="H3045"' in result
        assert 'data-strongs="H3808"' not in result
        assert '{' not in result

    def test_first_marker_of_run_wins(self):
        """A word with two glued plain markers takes the first (data order)."""
        result = self._render("his birthday{H3117}{H3205}{(H8715)}, that day.")
        assert re.search(r'data-strongs="H3117"[^>]*>birthday</span>', result)
        assert 'data-strongs="H3205"' not in result

    def test_variant_alt_attaches_only_to_variant_instance(self):
        """{(G5625)} alternates land on the marked token, not every instance."""
        result = self._render(
            "he shall{G91} not hurt, whither{G3757}{(G5625)}{G3739} he would come."
        )
        whither = re.search(r'<span[^>]*data-strongs="G3757"[^>]*>', result).group(0)
        shall = re.search(r'<span[^>]*data-strongs="G91"[^>]*>', result).group(0)
        assert 'data-alt-strongs="G3739"' in whither
        assert 'data-alt-strongs' not in shall

    def test_multiword_phrase_consumes_gap(self):
        """A multi-word dictionary translation wraps the whole phrase."""
        strongs_dict = {"H5828": {"translations": ["help meet"], "color": None}}
        strongs_data = [{"number": "H5828", "xlit": "ezer", "lemma": "עֵזֶר",
                         "pronounce": "ay-zer", "description": "aid"}]
        result = self._render(
            "I will make him an help meet{H5828} for him.", strongs_dict, strongs_data
        )
        # (renders as <button> here because a one-verse corpus makes it "uncommon")
        assert re.search(r'>ezer</(span|button)>', result)
        assert 'data-original="help meet"' in result
        # The phrase words must not be duplicated outside the span.
        assert 'help meet ezer' not in result and 'an help ' not in result

    def test_repeated_stopword_renders_plain(self):
        """Short/stopword repeat candidates render as plain text, not spans."""
        text = "and the day{H3117} and the day{H3117} and the day{H3117}."
        result = self._render(text)
        # 'day' is only 3 letters -> skipped from spanning when repeated.
        assert 'data-strongs="H3117"' not in result
        assert result.count('day') == 3


class TestNameMeanings:
    """The name-uncovering feature layered on the tokenizer."""

    NAME_DATA = [{
        "number": "H883",
        "xlit": "Bᵉ'êr la-Chay Rô'îy",
        "lemma": "בְּאֵר לַחַי רֹאִי",
        "pronounce": "be-ayr' lakh-ah'ee ro-ee'",
        "description": "from X and Y; well of a living (One) my Seer; "
                       "Beer-Lachai-Roi, a place in the Desert; Beer-lahai-roi.",
    }]

    def _bible_data(self, text):
        from app.data import build_bible_data
        kjv = {"verses": [{
            "book": 1, "book_name": "Genesis", "chapter": 16, "verse": 14,
            "text": text,
        }]}
        return build_bible_data(self.NAME_DATA, kjv)

    def test_name_gets_dagger_and_note(self):
        bd = self._bible_data("the well was called Beerlahairoi{H883}; behold.")
        result = transliterate_chapter("Genesis", 16, {}, bd)
        assert 'data-name-meaning="well of a living (One) my Seer"' in result
        assert 'name-mark' in result
        assert '[that is, <em>well of a living (One) my Seer</em>]' in result

    def test_dagger_only_on_first_occurrence(self):
        bd = self._bible_data(
            "Beerlahairoi{H883} was there, even Beerlahairoi{H883} itself."
        )
        result = transliterate_chapter("Genesis", 16, {}, bd)
        assert result.count('name-mark') == 1
        # Both instances still carry the popup meaning.
        assert result.count('data-name-meaning') == 2

    def test_lowercase_word_gets_no_name_markup(self):
        bd = self._bible_data("a common well{H883} of water.")
        result = transliterate_chapter("Genesis", 16, {}, bd)
        assert 'data-name-meaning' not in result
        assert 'name-mark' not in result


class TestHexColorValidation:
    """Tests for the is_valid_hex_color guard."""

    def test_accepts_six_digit_hex(self):
        assert is_valid_hex_color("#FF5733")
        assert is_valid_hex_color("#ff5733")

    def test_rejects_non_hex(self):
        assert not is_valid_hex_color("red")
        assert not is_valid_hex_color("#fff")
        assert not is_valid_hex_color('#fff" onmouseover="x')
        assert not is_valid_hex_color(None)
        assert not is_valid_hex_color(123)

    def test_rejects_trailing_content(self):
        # fullmatch must reject a valid prefix followed by an injection.
        assert not is_valid_hex_color("#ff5733; background: url(x)")
        assert not is_valid_hex_color("#ff5733\n")
