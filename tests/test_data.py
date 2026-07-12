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


class TestPhraseIndexBuild:
    """Build-script primitives: lexical-token extraction and n-gram windows."""

    def _module(self):
        import importlib.util
        import os
        path = os.path.join(
            os.path.dirname(__file__), '..', 'scripts', 'build_phrase_index.py'
        )
        spec = importlib.util.spec_from_file_location('build_phrase_index', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_grammar_codes_are_not_lexical_tokens(self):
        # "made{H6213}{(H8804)}" -> only H6213; the {(H8804)} morphology code
        # and the malformed {H8804)} shape never enter the sequence.
        mod = self._module()
        seq = mod.PLAIN_MARKER_REGEX.findall(
            "he made{H6213}{(H8804)} him a coat{H3801} of many colours{H6446}."
        )
        assert seq == ['H6213', 'H3801', 'H6446']

    def test_one_word_two_lexemes_is_a_valid_two_token_phrase(self):
        # A single English word backed by two markers ("created{H1254}{H853}")
        # yields a two-token phrase H1254-H853.
        mod = self._module()
        seqs = [('Genesis', 1, 1, ['H1254', 'H853', 'H430'])]
        occ = mod.build_ngram_occurrences(seqs)
        assert 'H1254-H853' in occ

    def test_ngrams_never_cross_verses(self):
        mod = self._module()
        seqs = [
            ('Genesis', 1, 1, ['H1', 'H2']),
            ('Genesis', 1, 2, ['H3', 'H4']),
        ]
        occ = mod.build_ngram_occurrences(seqs)
        # In-verse pairs exist; the cross-verse pair H2-H3 must not.
        assert 'H1-H2' in occ and 'H3-H4' in occ
        assert 'H2-H3' not in occ

    def test_ngram_length_bounds_and_positions(self):
        mod = self._module()
        seqs = [('Genesis', 1, 1, ['H1', 'H2', 'H3'])]
        occ = mod.build_ngram_occurrences(seqs)
        # 2- and 3-grams only (MIN_LEN=2, MAX_LEN=5); positions are token index.
        assert occ['H1-H2'] == [['Genesis', 1, 1, 0]]
        assert occ['H2-H3'] == [['Genesis', 1, 1, 1]]
        assert occ['H1-H2-H3'] == [['Genesis', 1, 1, 0]]
        assert 'H1' not in occ  # single tokens are never phrases


class TestPhraseIndexLoad:
    """_build_phrase_index derives records and per-chapter ordering."""

    def _bible(self):
        from app.data import build_bible_data
        strongs = [
            {'number': 'H3801', 'lemma': 'כְּתֹנֶת', 'xlit': 'kᵉthôneth'},
            {'number': 'H6446', 'lemma': 'פַּס', 'xlit': 'paç'},
            {'number': 'H853', 'lemma': 'אֵת', 'xlit': "'êth"},
        ]
        kjv = {'verses': [
            {'book': 1, 'book_name': 'Genesis', 'chapter': 37, 'verse': 3,
             'text': 'a coat{H3801} of many colours{H6446}.'},
        ]}
        phrase_data = {
            'meta': {'schema_version': 1, 'stopwords': ['H853']},
            'phrases': {
                'H3801-H6446': [
                    ['2 Samuel', 13, 18, 6],
                    ['Genesis', 37, 3, 7],
                ],
            },
        }
        return build_bible_data(strongs, kjv, phrase_data=phrase_data)

    def test_record_fields_and_canonical_passage_order(self):
        bd = self._bible()
        rec = bd.phrase_index['H3801-H6446']
        assert rec['tokens'] == ['H3801', 'H6446']
        assert rec['lang'] == 'H'
        assert rec['occ_count'] == 2
        assert rec['content_count'] == 2  # neither token is a stopword
        assert rec['cross_book'] is True
        # Genesis (book 1) sorts before 2 Samuel despite input order.
        assert rec['passages'][0] == ('Genesis', 37)

    def test_stopwords_reduce_content_count(self):
        from app.data import build_bible_data
        kjv = {'verses': []}
        phrase_data = {
            'meta': {'stopwords': ['H853']},
            'phrases': {'H853-H3801': [['Genesis', 1, 1, 0], ['Exodus', 2, 2, 0]]},
        }
        bd = build_bible_data([], kjv, phrase_data=phrase_data)
        rec = bd.phrase_index['H853-H3801']
        assert rec['content_count'] == 1  # H853 is a stopword, H3801 is not

    def test_by_chapter_lookup_registers_both_passages(self):
        bd = self._bible()
        assert 'H3801-H6446' in bd.phrases_by_chapter[('Genesis', 37)]
        assert 'H3801-H6446' in bd.phrases_by_chapter[('2 Samuel', 13)]

    def test_absent_phrase_data_yields_empty_structures(self):
        from app.data import build_bible_data
        bd = build_bible_data([], {'verses': []})
        assert bd.phrase_index == {}
        assert bd.phrases_by_chapter == {}


class TestIllustrationIndex:
    """_build_illustration_index maps (book, chapter) -> chapter-localized scene."""

    def _kjv(self):
        # Two chapters with known verse counts so range clamping is testable:
        # Genesis 1 has 5 verses, Genesis 2 has 3 verses.
        verses = []
        for v in range(1, 6):
            verses.append({'book': 1, 'book_name': 'Genesis', 'chapter': 1,
                           'verse': v, 'text': f'Verse {v}.'})
        for v in range(1, 4):
            verses.append({'book': 1, 'book_name': 'Genesis', 'chapter': 2,
                           'verse': v, 'text': f'Verse {v}.'})
        return {'verses': verses}

    def _image(self):
        return {
            'alt': 'A test illustration.',
            'width': 1200, 'height': 900,
            'fallback': 'img/x/x.jpg',
            'sources': [{'type': 'image/webp',
                         'srcset': [{'path': 'img/x/x.webp', 'width': 1200}]}],
        }

    def _bible(self, scenes):
        from app.data import build_bible_data
        return build_bible_data([], self._kjv(),
                                illustration_data={'version': 1, 'scenes': scenes})

    def _scene(self, steps, scene_id='scene-a', title='Scene A'):
        return {'id': scene_id, 'title': title, 'image': self._image(), 'steps': steps}

    def test_scene_indexed_for_every_touched_chapter(self):
        step = {'id': 's1', 'regions': [{'kind': 'rect', 'x': 10, 'y': 10, 'w': 20, 'h': 20}],
                'passages': [{'book': 'Genesis', 'start': {'chapter': 1, 'verse': 1},
                              'end': {'chapter': 2, 'verse': 2}}]}
        bd = self._bible([self._scene([step])])
        assert ('Genesis', 1) in bd.illustrations_by_chapter
        assert ('Genesis', 2) in bd.illustrations_by_chapter

    def test_steps_filtered_to_chapter(self):
        ch1_only = {'id': 'ch1', 'regions': [{'kind': 'ellipse', 'cx': 50, 'cy': 50, 'rx': 5, 'ry': 5}],
                    'passages': [{'book': 'Genesis', 'start': {'chapter': 1, 'verse': 1},
                                  'end': {'chapter': 1, 'verse': 2}}]}
        ch2_only = {'id': 'ch2', 'regions': [{'kind': 'ellipse', 'cx': 40, 'cy': 40, 'rx': 5, 'ry': 5}],
                    'passages': [{'book': 'Genesis', 'start': {'chapter': 2, 'verse': 1},
                                  'end': {'chapter': 2, 'verse': 1}}]}
        bd = self._bible([self._scene([ch1_only, ch2_only])])
        ch1_ids = [s['id'] for s in bd.illustrations_by_chapter[('Genesis', 1)]['steps']]
        ch2_ids = [s['id'] for s in bd.illustrations_by_chapter[('Genesis', 2)]['steps']]
        assert ch1_ids == ['ch1']
        assert ch2_ids == ['ch2']

    def test_multi_passage_step_localized_per_chapter(self):
        step = {'id': 'shared', 'label': None,
                'regions': [{'kind': 'rect', 'x': 0, 'y': 0, 'w': 10, 'h': 10}],
                'passages': [
                    {'book': 'Genesis', 'start': {'chapter': 1, 'verse': 3}, 'end': {'chapter': 1, 'verse': 4}},
                    {'book': 'Genesis', 'start': {'chapter': 2, 'verse': 1}, 'end': {'chapter': 2, 'verse': 1}},
                ]}
        bd = self._bible([self._scene([step])])
        s1 = bd.illustrations_by_chapter[('Genesis', 1)]['steps'][0]
        s2 = bd.illustrations_by_chapter[('Genesis', 2)]['steps'][0]
        assert (s1['start_verse'], s1['end_verse']) == (3, 4)
        assert s1['ref'] == '1:3–4'   # en dash for a range
        assert (s2['start_verse'], s2['end_verse']) == (1, 1)
        assert s2['ref'] == '2:1'          # single verse, no dash

    def test_verse_bounds_clamped_to_chapter(self):
        # End verse 99 exceeds Genesis 1's 5 verses -> clamps to 5.
        step = {'id': 's', 'regions': [{'kind': 'rect', 'x': 0, 'y': 0, 'w': 10, 'h': 10}],
                'passages': [{'book': 'Genesis', 'start': {'chapter': 1, 'verse': 1},
                              'end': {'chapter': 1, 'verse': 99}}]}
        bd = self._bible([self._scene([step])])
        s = bd.illustrations_by_chapter[('Genesis', 1)]['steps'][0]
        assert s['end_verse'] == 5

    def test_book_name_normalized(self):
        step = {'id': 's', 'regions': [{'kind': 'rect', 'x': 0, 'y': 0, 'w': 10, 'h': 10}],
                'passages': [{'book': 'genesis', 'start': {'chapter': 1, 'verse': 1},
                              'end': {'chapter': 1, 'verse': 1}}]}
        bd = self._bible([self._scene([step])])
        assert ('Genesis', 1) in bd.illustrations_by_chapter

    def test_steps_sorted_by_start_verse(self):
        late = {'id': 'late', 'regions': [{'kind': 'rect', 'x': 0, 'y': 0, 'w': 5, 'h': 5}],
                'passages': [{'book': 'Genesis', 'start': {'chapter': 1, 'verse': 4}, 'end': {'chapter': 1, 'verse': 4}}]}
        early = {'id': 'early', 'regions': [{'kind': 'rect', 'x': 0, 'y': 0, 'w': 5, 'h': 5}],
                 'passages': [{'book': 'Genesis', 'start': {'chapter': 1, 'verse': 1}, 'end': {'chapter': 1, 'verse': 1}}]}
        bd = self._bible([self._scene([late, early])])
        ids = [s['id'] for s in bd.illustrations_by_chapter[('Genesis', 1)]['steps']]
        assert ids == ['early', 'late']

    def test_malformed_scene_skipped_valid_sibling_kept(self, caplog):
        import logging
        bad_unknown_book = {'id': 'bad', 'regions': [{'kind': 'rect', 'x': 0, 'y': 0, 'w': 5, 'h': 5}],
                            'passages': [{'book': 'Narnia', 'start': {'chapter': 1, 'verse': 1},
                                          'end': {'chapter': 1, 'verse': 1}}]}
        good = {'id': 'ok', 'regions': [{'kind': 'rect', 'x': 0, 'y': 0, 'w': 5, 'h': 5}],
                'passages': [{'book': 'Genesis', 'start': {'chapter': 1, 'verse': 1},
                              'end': {'chapter': 1, 'verse': 1}}]}
        with caplog.at_level(logging.WARNING):
            bd = self._bible([self._scene([bad_unknown_book], scene_id='bad-scene'),
                              self._scene([good], scene_id='good-scene')])
        # The good scene still indexes; the bad one is dropped with a warning.
        assert bd.illustrations_by_chapter[('Genesis', 1)]['id'] == 'good-scene'
        assert any('bad-scene' in r.message for r in caplog.records)

    def test_bad_region_kind_skips_scene(self):
        step = {'id': 's', 'regions': [{'kind': 'triangle', 'x': 0, 'y': 0}],
                'passages': [{'book': 'Genesis', 'start': {'chapter': 1, 'verse': 1},
                              'end': {'chapter': 1, 'verse': 1}}]}
        bd = self._bible([self._scene([step])])
        assert bd.illustrations_by_chapter == {}

    def test_out_of_bounds_region_skips_scene(self):
        step = {'id': 's', 'regions': [{'kind': 'rect', 'x': 90, 'y': 10, 'w': 30, 'h': 10}],
                'passages': [{'book': 'Genesis', 'start': {'chapter': 1, 'verse': 1},
                              'end': {'chapter': 1, 'verse': 1}}]}
        bd = self._bible([self._scene([step])])  # x+w = 120 > 100
        assert bd.illustrations_by_chapter == {}

    def test_absent_catalog_yields_empty_index(self):
        from app.data import build_bible_data
        bd = build_bible_data([], self._kjv())
        assert bd.illustrations_by_chapter == {}
