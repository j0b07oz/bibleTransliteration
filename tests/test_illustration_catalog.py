"""Strict validation of the real shipped illustration catalog.

The data-layer loader is deliberately lenient (a malformed scene is logged and
skipped so a bad entry can never crash startup). This test is the strict half:
it fails CI if the committed app/data/illustrations.json has a schema error, an
out-of-bounds verse or region, or a missing image file — so bad authoring is
caught before deploy instead of silently dropping a scene in production.
"""
import json
import os

import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'app'))
CATALOG_PATH = os.path.join(APP_DIR, 'data', 'illustrations.json')
STATIC_DIR = os.path.join(APP_DIR, 'static')


@pytest.fixture(scope='module')
def catalog():
    assert os.path.exists(CATALOG_PATH), 'illustrations.json is missing'
    with open(CATALOG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


@pytest.fixture(scope='module')
def bible_data():
    from app import app
    return app.extensions['bible_data']


def _iter_regions(step):
    return step.get('regions', [])


def test_catalog_parses_and_has_scenes(catalog):
    assert isinstance(catalog.get('scenes'), list) and catalog['scenes']


def test_scene_ids_unique(catalog):
    ids = [s['id'] for s in catalog['scenes']]
    assert len(ids) == len(set(ids)), 'duplicate scene ids'


def test_step_ids_unique_within_scene(catalog):
    for scene in catalog['scenes']:
        ids = [s['id'] for s in scene['steps']]
        assert len(ids) == len(set(ids)), f"duplicate step ids in {scene['id']}"


def test_image_metadata_well_formed(catalog):
    for scene in catalog['scenes']:
        image = scene['image']
        assert image.get('alt', '').strip(), f"{scene['id']} missing alt"
        assert isinstance(image['width'], int) and image['width'] > 0
        assert isinstance(image['height'], int) and image['height'] > 0
        assert image.get('fallback')
        assert image.get('sources')


def test_image_files_exist(catalog):
    """Every fallback and srcset path resolves to a real file under app/static."""
    for scene in catalog['scenes']:
        image = scene['image']
        paths = [image['fallback']]
        for source in image['sources']:
            paths += [c['path'] for c in source['srcset']]
        for rel in paths:
            assert not os.path.isabs(rel) and '..' not in rel.split('/'), \
                f"unsafe asset path {rel!r}"
            full = os.path.join(STATIC_DIR, rel)
            assert os.path.exists(full), f"missing asset file: {rel}"


def test_passages_reference_real_books_and_verses(catalog, bible_data):
    lookup = bible_data.book_name_lookup
    chapter_counts = bible_data.book_chapter_count
    verse_counts = bible_data.chapter_verse_counts
    for scene in catalog['scenes']:
        for step in scene['steps']:
            for p in step['passages']:
                book = lookup.get(p['book'].lower())
                assert book, f"unknown book {p['book']!r} in {scene['id']}/{step['id']}"
                for key in ('start', 'end'):
                    ch = p[key]['chapter']
                    v = p[key]['verse']
                    assert 1 <= ch <= chapter_counts[book], \
                        f"{book} has no chapter {ch}"
                    assert 1 <= v <= verse_counts[book][ch], \
                        f"{book} {ch} has no verse {v}"
                assert (p['start']['chapter'], p['start']['verse']) <= \
                       (p['end']['chapter'], p['end']['verse']), \
                    f"passage start after end in {scene['id']}/{step['id']}"


def test_regions_within_bounds(catalog):
    for scene in catalog['scenes']:
        for step in scene['steps']:
            assert _iter_regions(step), f"{step['id']} has no regions"
            for r in _iter_regions(step):
                if r['kind'] == 'rect':
                    assert 0 <= r['x'] and 0 <= r['y']
                    assert r['w'] > 0 and r['h'] > 0
                    assert r['x'] + r['w'] <= 100 and r['y'] + r['h'] <= 100, \
                        f"rect out of bounds in {scene['id']}/{step['id']}"
                elif r['kind'] == 'ellipse':
                    assert r['rx'] > 0 and r['ry'] > 0
                    assert r['cx'] - r['rx'] >= 0 and r['cy'] - r['ry'] >= 0
                    assert r['cx'] + r['rx'] <= 100 and r['cy'] + r['ry'] <= 100, \
                        f"ellipse out of bounds in {scene['id']}/{step['id']}"
                else:
                    pytest.fail(f"unknown region kind {r['kind']!r}")


def test_dim_in_range(catalog):
    for scene in catalog['scenes']:
        for step in scene['steps']:
            if 'dim' in step:
                assert 0 < step['dim'] <= 1, f"dim out of range in {step['id']}"


def test_every_scene_loaded_not_lenient_skipped(catalog, bible_data):
    """Every scene in the file actually made it into the runtime index.

    If the lenient loader silently dropped a scene, its id would be absent from
    illustrations_by_chapter and this fails — the safety net that turns a
    silent production skip into a red build.
    """
    loaded_ids = {payload['id'] for payload in bible_data.illustrations_by_chapter.values()}
    for scene in catalog['scenes']:
        assert scene['id'] in loaded_ids, \
            f"scene {scene['id']} was skipped by the loader (schema error?)"
