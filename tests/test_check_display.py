import hashlib
import io
from pathlib import Path
import xml.etree.ElementTree as ET

from PIL import Image
import pytest

from engine.annotate import render
from engine.annotations import AnnotationList
from engine.check_analysis import from_text
from engine.check_display import compare
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
    assert {'different_key', 'different_chord', 'unlabelled'} <= {r['classification'] for r in results}
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
    assert sum("a chord you didn't label" in t for t in strings) == 1
    assert any('the tool reads the key' in t if name == 'bach' else 'a different chord' in t for t in strings)
    # The key is written at the start and where it changes, never before every label.
    keys = [t for t in strings if t.endswith(':') and len(t) <= 3]
    assert len(keys) == 3, keys
    assert 'a:' in strings if name == 'bach' else 'E♭:' in strings
    assert any(t.get('class') == 'agreement-mark' for t in overlay.iter())
    # Numerals are typeset with raised figures and the diminished sign, not as typed.
    assert not any(t in strings for t in ('viio7', 'I53', 'V65/vi', 'ii7'))
    assert '°' in strings


CHOPIN = 'tests/data/chopin_nocturne_op9_no2.mxl', 'examples/chopin_op9_no2_m1-8.json'


def typed_page(text, bars=(1, 8)):
    """Typed Chopin answer -> the drawn page: its results, text strings, size and whether it is clear of collisions."""
    from tools import engraving_check
    score, reviewed = (ROOT / CHOPIN[0]).read_bytes(), AnnotationList.model_validate_json((ROOT / CHOPIN[1]).read_text())
    index = ScoreIndex(load_toolkit(score).getMEI())
    labels = from_text(text, index=index)
    engraving_check._layouts.clear()
    page = render(score, reviewed, measures=bars, student_labels=labels)
    found = engraving_check.collisions(page.page_count)
    assert not (found['overlapping'] or found['tight'] or found['music']), found
    svg = ET.fromstring(page.svgs[0])
    overlay = next(g for g in svg.iter() if g.get('class') == 'analysis-over')
    strings = [t.text for t in overlay.iter() if t.tag.endswith('text')]
    return compare(labels, reviewed.model_dump(exclude_none=True), index), strings, engraving_check._layouts[-1], svg


WRONG = ('key: Eb major; bar 1 V beat 2 ii beat 3 IV; bar 2 vi beat 3 V; bar 3 ii beat 2 I beat 3 V beat 4 IV; '
         'bar 4 vi beat 3 ii')
DENSE = ('key: Eb major; bar 1 I beat 1.5 V65 beat 2 viio7 beat 2.5 I6 beat 3 in G: V7/ii beat 3.5 vi beat 4 in Eb: IV6; '
         'bar 2 ii7 beat 1.5 V beat 2 in Bb: I beat 2.5 V6 beat 3 in Eb: ii beat 3.5 V7 beat 4 I')


def test_many_notes_keep_clear_of_the_next_system_and_the_legend_fits():
    results, strings, drawn, svg = typed_page(WRONG, (1, 4))
    assert sum(t.startswith('[') and 'Bar' in t for t in strings) == 11
    page_bottom = float(next(e for e in svg.iter() if e.get('class') == 'definition-scale').get('viewBox').split()[3])
    assert all(box.bottom < page_bottom for _, box in drawn.labels)
    assert any("blue: the tool" in t for t in strings)


def test_dense_answer_keeps_every_label_and_reading_on_the_page():
    results, strings, drawn, svg = typed_page(DENSE, (1, 2))
    right = max(system.right for system in drawn.systems)
    assert all(box.x >= 0 and box.right <= right for _, box in drawn.labels + drawn.harmony_labels)
    blue = [t.get('fill') for t in svg.iter() if t.tag.endswith('text')].count('#4477AA')
    assert blue >= sum(1 for r in results if r['classification'] in ('different_chord', 'different_key', 'different_inversion'))


def test_pickup_label_before_the_tools_first_chord_is_shown_unmarked():
    results, strings, *_ = typed_page('key: Eb major; bar 0 V; bar 1 I', (0, 2))
    assert results[0]['at']['measure'] == 0 and results[0]['classification'] == 'unchecked'
    assert results[1]['classification'] == 'agrees'


def test_key_notes_are_numbered_per_run_not_per_passage():
    results, strings, *_ = typed_page('key: Eb major; bar 1 in Bb: IV beat 2 in Eb: viio7 beat 3 in Bb: IV', (1, 2))
    assert [r['classification'] for r in results[:3]] == ['different_key', 'agrees', 'different_key']
    assert [t[:3] for t in strings if t.startswith('[') and 'Bar' in t] == ['[1]', '[2]']


def test_chord_and_key_both_different_is_a_chord_difference():
    results, *_ = typed_page('key: Eb major; bar 1 in Bb: V; bar 4 beat 3 in Bb: IV', (1, 4))
    written = [r['classification'] for r in results if r['student']]
    assert written == ['different_chord', 'different_key']  # F major is not E-flat major; the same E-flat chord named in another key


def test_legend_lists_only_marks_on_the_page():
    results, strings, *_ = typed_page('key: Eb major; bar 1 I beat 2 viio7 beat 3 I', (1, 1))
    legend = [t for t in strings if 'agrees with the tool' in t or 'blue' in t or 'check the bass' in t or 'see note' in t]
    assert legend == ['agrees with the tool']


def test_default_comparison_disabled_bytes(chopin, chopin_annotations):
    page = render(chopin, chopin_annotations, measures=(1, 8))
    assert hashlib.sha256(page.png()).hexdigest() == PNG_HASH


PNG_HASH = 'da3b71e23d93d351c5821f691ef7756b3241f33f48cfdf63fc9095d857e6f6fa'
