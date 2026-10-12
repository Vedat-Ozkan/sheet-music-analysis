import hashlib
import io
from pathlib import Path
import xml.etree.ElementTree as ET

from PIL import Image
import pytest

from engine.annotate import render
from engine.annotations import AnnotationList
from engine.check_analysis import compare, from_text
from engine.render import load_toolkit
from engine.score import ScoreIndex

ROOT = Path(__file__).parent.parent
FIXTURES = ROOT / 'tests/data/check_display'
PIECES = {
    'chopin': ('tests/data/chopin_nocturne_op9_no2.mxl', 'examples/chopin_op9_no2_m1-8.json'),
    'bach': ('tests/data/part_writing_bwv404.musicxml', 'tests/data/check_display/bach-reviewed.json'),
}


def passage(name):
    score, reviewed = PIECES[name]
    score = (ROOT / score).read_bytes()
    annotations = AnnotationList.model_validate_json((ROOT / reviewed).read_text())
    index = ScoreIndex(load_toolkit(score).getMEI())
    labels = from_text((FIXTURES / f'{name}.txt').read_text(), index=index)
    return score, annotations, index, labels


def normal_height(name):
    score, annotations, *_ = passage(name)
    return Image.open(io.BytesIO(render(score, annotations, measures=(1, 8)).png())).height


@pytest.mark.parametrize('name', PIECES)
def test_typed_comparison_page(name):
    score, annotations, index, labels = passage(name)
    results = compare(labels, annotations.model_dump(exclude_none=True), index)
    assert {label.measure for label in labels} == set(range(1, 9))
    assert {'agrees', 'same_chord_different_spelling', 'different_inversion'} <= {r['classification'] for r in results}
    assert {'different_key', 'different_chord'} <= {r['classification'] for r in results}
    from tools import engraving_check
    engraving_check._layouts.clear()
    page = render(score, annotations, measures=(1, 8), student_labels=labels)
    collisions = engraving_check.collisions(page.page_count)
    assert not collisions['overlapping']
    assert not collisions['tight']
    assert not collisions['music']
    drawn = engraving_check._layouts[-1]
    assert all(box.x >= 0 and box.right <= max(s.right for s in drawn.systems)
               for _, box in drawn.labels + drawn.harmony_labels)
    assert page.page_count == 1
    height = Image.open(io.BytesIO(page.png())).height
    assert Image.open(io.BytesIO(page.png())).width == 1400
    # The label rows add height, but the page lays out like a normal one: same systems, no empty gaps.
    assert height < 1.25 * normal_height(name)
    svg = ET.fromstring(page.svgs[0])
    overlay = next(g for g in svg.iter() if g.get('class') == 'analysis-over')
    strings = [t.text for t in overlay.iter() if t.tag.endswith('text')]
    assert not any('Your reading' in t for t in strings)
    assert sum('agrees with the tool' in t for t in strings) == 1
    assert any('the tool reads the key' in t if name == 'bach' else 'a different chord' in t for t in strings)
    # The key is written at the start and where it changes, never before every label.
    keys = [t for t in strings if t.endswith(':') and len(t) <= 3]
    assert len(keys) == 3, keys
    assert 'a:' in strings if name == 'bach' else 'E♭:' in strings
    assert any(t.get('class') == 'agreement-mark' for t in overlay.iter())
    # Numerals are typeset with raised figures and the diminished sign, not as typed.
    assert not any(t in strings for t in ('viio7', 'I53', 'V65/vi', 'ii7'))
    assert '°' in strings


def test_default_comparison_disabled_bytes(chopin, chopin_annotations):
    page = render(chopin, chopin_annotations, measures=(1, 8))
    assert hashlib.sha256(page.png()).hexdigest() == PNG_HASH


PNG_HASH = 'da3b71e23d93d351c5821f691ef7756b3241f33f48cfdf63fc9095d857e6f6fa'
