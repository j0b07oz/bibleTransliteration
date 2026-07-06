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

    # --- regressions from real-reading feedback ---

    def test_see_ye_a_son_is_a_meaning_not_a_reference(self):
        # H7205 Reuben: a blanket 'see ' filter once ate this meaning.
        desc = ("from the imperative of X and Y; see ye a son; "
                "Reuben, a son of Jacob; Reuben.")
        assert extract_name_gloss(desc) == "see ye a son"

    def test_see_reference_is_still_filtered(self):
        # "see Genesis 25:25" style cross-references are not meanings.
        desc = ("from X; see Genesis 25:25; red; "
                "Edom, the elder twin-brother of Jacob; Edom.")
        assert extract_name_gloss(desc) == "red"

    def test_renderings_segment_never_identifies_a_name(self):
        # H410 'el: the KJV renderings list contains 'idol'/'might' keywords
        # and starts with a capital, but its [idiom] markers give it away.
        desc = ("shortened from X; strength; as adjective, mighty; "
                "especially the Almighty (but used also of any deity); "
                "God (god), [idiom] goodly, [idiom] great, idol, "
                "might(-y one), power, strong. Compare names in '-el.'")
        assert extract_name_gloss(desc) is None

    def test_possessive_identification(self):
        # H8283 Sarah: identified as "Sarah, Abraham's wife".
        desc = "the same as X; dominative; Sarah, Abraham's wife; Sarah."
        assert extract_name_gloss(desc) == "dominative"

    def test_uncertain_derivation_yields_none(self):
        # H1904 Hagar: the lexicon offers no meaning at all.
        desc = ("of uncertain (perhaps foreign) derivation; "
                "Hagar, the mother of Ishmael; Hagar.")
        assert extract_name_gloss(desc) is None

    def test_same_as_reference_hop(self):
        # A name defined only by "the same as <lemma>" takes the referenced
        # entry's meaning when a resolver is supplied.
        desc = "the same as שָׂרָה; Sarah, Abraham's wife; Sarah."

        def resolve(lemma):
            assert lemma == "שָׂרָה"
            return "a mistress, i.e. female noble"

        assert extract_name_gloss(desc, resolve_reference=resolve) == "a mistress, i.e. female noble"
        assert extract_name_gloss(desc) is None
