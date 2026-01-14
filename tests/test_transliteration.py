"""
Tests for the transliteration module.
"""
import pytest
from app.transliteration import (
    extract_strongs_numbers,
    generate_color_from_strongs,
    generate_repeat_colors,
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

    def test_basic_transliteration(self, sample_strongs_dict, sample_strongs_data, sample_kjv_data):
        """Test basic chapter transliteration."""
        result = transliterate_chapter(
            book="Genesis",
            chapter=1,
            strongs_dict=sample_strongs_dict,
            strongs_data=sample_strongs_data,
            kjv_data=sample_kjv_data
        )
        # Should return HTML string
        assert isinstance(result, str)
        assert len(result) > 0

    def test_transliteration_contains_verses(self, sample_strongs_dict, sample_strongs_data, sample_kjv_data):
        """Test that transliteration includes verse content."""
        result = transliterate_chapter(
            book="Genesis",
            chapter=1,
            strongs_dict=sample_strongs_dict,
            strongs_data=sample_strongs_data,
            kjv_data=sample_kjv_data
        )
        # Should contain verse numbers and text
        assert "1" in result  # Verse 1
        assert "beginning" in result.lower() or "re'shiyth" in result.lower()

    def test_invalid_book(self, sample_strongs_dict, sample_strongs_data, sample_kjv_data):
        """Test transliteration with invalid book name."""
        result = transliterate_chapter(
            book="InvalidBook",
            chapter=1,
            strongs_dict=sample_strongs_dict,
            strongs_data=sample_strongs_data,
            kjv_data=sample_kjv_data
        )
        # Should return empty or minimal HTML
        assert isinstance(result, str)

    def test_invalid_chapter(self, sample_strongs_dict, sample_strongs_data, sample_kjv_data):
        """Test transliteration with invalid chapter number."""
        result = transliterate_chapter(
            book="Genesis",
            chapter=999,
            strongs_dict=sample_strongs_dict,
            strongs_data=sample_strongs_data,
            kjv_data=sample_kjv_data
        )
        # Should return empty or minimal HTML
        assert isinstance(result, str)

    def test_empty_strongs_dict(self, sample_strongs_data, sample_kjv_data):
        """Test transliteration with empty Strong's dictionary."""
        result = transliterate_chapter(
            book="Genesis",
            chapter=1,
            strongs_dict={},
            strongs_data=sample_strongs_data,
            kjv_data=sample_kjv_data
        )
        # Should still return valid HTML
        assert isinstance(result, str)
        assert len(result) > 0

    def test_max_repeated_highlights(self, sample_strongs_dict, sample_strongs_data, sample_kjv_data):
        """Test that max_repeated_highlights parameter works."""
        result1 = transliterate_chapter(
            book="Genesis",
            chapter=1,
            strongs_dict=sample_strongs_dict,
            strongs_data=sample_strongs_data,
            kjv_data=sample_kjv_data,
            max_repeated_highlights=5
        )
        result2 = transliterate_chapter(
            book="Genesis",
            chapter=1,
            strongs_dict=sample_strongs_dict,
            strongs_data=sample_strongs_data,
            kjv_data=sample_kjv_data,
            max_repeated_highlights=10
        )
        # Both should return valid HTML
        assert isinstance(result1, str)
        assert isinstance(result2, str)

    def test_active_units_parameter(self, sample_strongs_dict, sample_strongs_data, sample_kjv_data):
        """Test transliteration with active units."""
        result = transliterate_chapter(
            book="Genesis",
            chapter=1,
            strongs_dict=sample_strongs_dict,
            strongs_data=sample_strongs_data,
            kjv_data=sample_kjv_data,
            active_units=["unit1", "unit2"]
        )
        # Should return valid HTML
        assert isinstance(result, str)
        assert len(result) > 0
