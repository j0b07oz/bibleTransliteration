"""
Tests for the data layer: proper-name gloss extraction.
"""
from app.data import extract_name_gloss


class TestNameGlossExtraction:
    """extract_name_gloss favors precision: no gloss beats a wrong gloss."""

    def test_place_name(self):
        desc = ("from X and Y (with prefix) and Z; well of a living (One) my Seer; "
                "Beer-Lachai-Roi, a place in the Desert; Beer-lahai-roi.")
        assert extract_name_gloss(desc) == "well of a living (One) my Seer"

    def test_person_name(self):
        desc = ("contracted from X and an unused root (probably meaning to be "
                "populous); father of a multitude; Abraham, the later name of "
                "Abram; Abraham.")
        assert extract_name_gloss(desc) == "father of a multitude"

    def test_extra_segments_before_derivation(self):
        # H1732 David: leading "rarely (fully)" and a Hebrew-script segment.
        desc = ("rarely (fully); דָּוִיד; from the same as X; loving; "
                "David, the youngest son of Jesse; David.")
        assert extract_name_gloss(desc) == "loving"

    def test_divine_name(self):
        desc = ("from X; (the) self-Existent or Eternal; "
                "Jehovah, Jewish national name of God; Jehovah, the Lord.")
        assert extract_name_gloss(desc) == "(the) self-Existent or Eternal"

    def test_common_noun_returns_none(self):
        # H2617 hesed: no capital-led identification segment.
        desc = ("from X; kindness; by implication (towards God) piety; "
                "favour, good deed, kindly, lovingkindness, mercy, pity.")
        assert extract_name_gloss(desc) is None

    def test_common_noun_mentioning_place_returns_none(self):
        # A common noun whose renderings mention 'place' must not qualify:
        # the identification segment must start with a capitalized name.
        desc = ("from X; properly, a standing, i.e. a spot; "
                "country, home, open, place, room, space, whither(-soever).")
        assert extract_name_gloss(desc) is None

    def test_reference_only_name_returns_none(self):
        # H121 Adam: derivation reference only, no stated meaning.
        desc = "the same as X; Adam the name of the first man; Adam."
        assert extract_name_gloss(desc) is None

    def test_leaked_derivation_segments_are_filtered(self):
        desc = ("(Aramaic) of foreign origin and doubtful significance; "
                "name of X; Meshak, the Babylonian name of one of Daniel's "
                "companions; Meshach.")
        assert extract_name_gloss(desc) is None

    def test_empty_and_none(self):
        assert extract_name_gloss('') is None
        assert extract_name_gloss(None) is None
