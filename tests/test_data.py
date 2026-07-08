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

    # --- recall expansion (benchmark audit against 1 Chronicles 1 etc.) ---

    def test_gentilic_identification_keyword(self):
        # H687 Ezer: "an Idumaean" must identify via the gentilic pattern.
        desc = "from X; treasure; Etser, an Idumaean; Ezer."
        assert extract_name_gloss(desc) == "treasure"

    def test_greek_christian_identification(self):
        # G751 Archippus: "a Christian" identifies NT names.
        desc = "from X and Y; horse-ruler; Archippus, a Christian:--Archippus."
        assert extract_name_gloss(desc) == "horse-ruler"

    def test_in_the_sense_of_meaning(self):
        # H804 Asshur: the meaning hides inside the derivation parenthetical.
        desc = ("or X; apparently from Y (in the sense of successful); "
                "Ashshur, the second son of Shem; Asshur.")
        assert extract_name_gloss(desc) == "successful"

    def test_hedged_meaning_is_kept_with_its_hedge(self):
        # H3946 Lakum: "perhaps fortification" is a meaning, hedged.
        desc = ("from an unused root thought to mean to stop up by a "
                "barricade; perhaps fortification; Lakkum, a place in "
                "Palestine; Lakum.")
        assert extract_name_gloss(desc) == "perhaps fortification"

    def test_hedged_derivation_is_still_filtered(self):
        desc = ("probably of foreign derivation; Elishah, a son of Javan; "
                "Elishah.")
        assert extract_name_gloss(desc) is None

    def test_hebrew_origin_hop_for_greek_names(self):
        # G1138: Greek NT names hop to their Hebrew base meaning.
        desc = "of Hebrew origin (דָּוִד); Dabid (i.e. David), the Israelite king:--David."

        def resolve(lemma):
            captured_ok = all(0x0590 <= ord(c) <= 0x05FF for c in lemma)
            assert captured_ok, f"expected Hebrew run, got {lemma!r}"
            return "loving"

        assert extract_name_gloss(desc, resolve_reference=resolve) == "loving"

    def test_hop_result_leaking_identification_is_rejected(self):
        # If the hop target's "meaning" is itself an identification, drop it.
        desc = "the same as כַלְנֵה; Kanneh, a place in Assyria; Canneh."

        def resolve(lemma):
            return "Calneh or Calno, a place in Palestine"

        assert extract_name_gloss(desc, resolve_reference=resolve) is None

    def test_patrial_gentilic_identification_as_gloss(self):
        # H721 Arvadite: for tribe/citizen names the identification IS the
        # useful note.
        desc = "patrial from אַרְוַד; an Arvadite or citizen of Arvad; Arvadite."
        assert extract_name_gloss(desc) == "citizen of Arvad"

    def test_glued_lemma_corruption_still_hops(self):
        # H425 Elah: glued "lemma ..." data corruption after the reference.
        desc = ("the same as אֵלָהlemma אִלָה first vowel, corrected to אֵלָה; "
                "Elah, the name of an Edomite, of four Israelites, and also "
                "of a place in Palestine; Elah")
        captured = []

        def resolve(lemma):
            captured.append(lemma)
            return "an oak or other strong tree"

        assert extract_name_gloss(desc, resolve_reference=resolve) == "an oak or other strong tree"
        assert captured and 'lemma' not in captured[0]
