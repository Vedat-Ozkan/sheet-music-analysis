import hashlib
import io
import re
from pathlib import Path
import xml.etree.ElementTree as ET

from PIL import Image
import pytest

from engine.annotate import render
from engine.annotations import AnnotationList
from engine.check_analysis import from_text
from engine.check_display import DIFFERS, compare
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
    assert height < 1.25 * normal_height(name)
    svg = ET.fromstring(page.svgs[0])
    overlay = next(g for g in svg.iter() if g.get('class') == 'analysis-over')
    strings = [t.text for t in overlay.iter() if t.tag.endswith('text')]
    assert not any('Your reading' in t for t in strings)
    assert strings.count('agrees') == 1
    assert sum("you didn't label this chord" in t for t in strings) == 1
    assert any('the tool hears this in' in t if name == 'bach' else 'a different chord' in t for t in strings)
    keys = [t for t in strings if t.endswith(':') and len(t) <= 3]
    assert len(keys) == (4 if name == 'bach' else 3), keys
    assert 'a:' in strings if name == 'bach' else 'E♭:' in strings
    assert any(t.get('class') == 'agreement-mark' for t in overlay.iter())
    assert not any(t in strings for t in ('viio7', 'I53', 'V65/vi', 'ii7'))
    assert '°' in strings


CHOPIN = 'tests/data/chopin_nocturne_op9_no2.mxl', 'examples/chopin_op9_no2_m1-8.json'


def typed_page(text, bars=(1, 8)):
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
    assert sum(t.startswith('Bar') for t in strings) == 11
    page_bottom = float(next(e for e in svg.iter() if e.get('class') == 'definition-scale').get('viewBox').split()[3])
    assert all(box.bottom < page_bottom for _, box in drawn.labels)
    assert any(t.startswith('ring = a different chord') for t in strings)
    assert not any('numbered note under' in t for t in strings)


def test_dense_answer_keeps_every_label_and_reading_on_the_page():
    results, strings, drawn, svg = typed_page(DENSE, (1, 2))
    right = max(system.right for system in drawn.systems)
    assert all(box.x >= 0 and box.right <= right for _, box in drawn.labels + drawn.harmony_labels)
    tool_row = [name for name, _ in drawn.harmony_labels if name.startswith('tool ')]
    assert len(tool_row) == sum(1 for r in results if r['at']['measure'] <= 2 and r['reviewed'] and (not r['student'] or r['classification'] in DIFFERS))
    assert len(tool_row) >= 10


def test_pickup_label_before_the_tools_first_chord_is_shown_unmarked():
    results, strings, *_ = typed_page('key: Eb major; bar 0 V; bar 1 I', (0, 2))
    assert results[0]['at']['measure'] == 0 and results[0]['classification'] == 'unchecked'
    assert results[1]['classification'] == 'agrees'
    assert 'no mark = the tool has no chord there to compare' in strings


def test_key_notes_are_numbered_per_run_not_per_passage():
    results, strings, *_ = typed_page('key: Eb major; bar 1 in Bb: IV beat 2 in Eb: viio7 beat 3 in Bb: IV', (1, 2))
    assert [r['classification'] for r in results[:3]] == ['different_key', 'agrees', 'different_key']
    assert sum(t.startswith('Bar') for t in strings) == 2
    assert {'1', '2'} <= set(strings) and '3' not in strings


def test_chord_and_key_both_different_is_a_chord_difference():
    results, *_ = typed_page('key: Eb major; bar 1 in Bb: V; bar 4 beat 3 in Bb: IV', (1, 4))
    written = [r['classification'] for r in results if r['student']]
    assert written == ['different_chord', 'different_key']


def test_legend_lists_only_marks_on_the_page():
    results, strings, *_ = typed_page('key: Eb major; bar 1 I beat 2 viio7 beat 3 I', (1, 1))
    legend = [t for t in strings if t == 'agrees' or t.startswith(('ring =', 'underline ='))]
    assert legend == ['agrees']


def bach_texts(answer=None, measures=(1, 8)):
    score, annotations, index, labels = passage('bach')
    if answer:
        labels = from_text(answer, index=index)
    svg = ET.fromstring(render(score, annotations, measures=measures, student_labels=labels).svgs[0])
    return [(t.get('fill'), t.text) for g in svg.iter() if g.get('class') == 'analysis-over' for t in g.iter() if t.tag.endswith('text')]


def test_key_only_difference_has_no_ring_and_no_tick_and_a_grey_reading():
    score, annotations, index, labels = passage('bach')
    results = compare(labels, annotations.model_dump(exclude_none=True), index)
    from tools import engraving_check
    engraving_check._layouts.clear()
    page = render(score, annotations, measures=(1, 8), student_labels=labels)
    svg = ET.fromstring(page.svgs[0])
    overlay = next(g for g in svg.iter() if g.get('class') == 'analysis-over')
    assert sum(r['classification'] == 'different_key' for r in results) == 6
    assert sum(t.get('class') == 'wrong-label-ring' for t in overlay.iter()) == 3
    grey = [t.text for t in overlay.iter() if t.tag.endswith('text') and t.get('fill') == '#555555']
    assert 'C:' in grey and grey.count('I') >= 2
    assert any('in A minor = I in C' in t for t in [t.text for t in overlay.iter() if t.tag.endswith('text')])


def test_no_red_key_under_a_key_the_student_writes_and_the_tool_agrees_with():
    texts = bach_texts('key: a minor; bar 3 i beat 2 V6 beat 4 III; bar 4 in C: V65/V beat 2 V beat 3 I; '
                       'bar 5 V beat 2 IV6 beat 3 V6 beat 4 I; bar 6 in a: viio beat 2 i beat 3 V', (3, 6))
    assert [t for fill, t in texts if fill == '#D50000' and t == 'a:'] == []


def test_a_run_of_key_differences_is_one_note_that_spans_the_run():
    texts = [t for _, t in bach_texts()]
    assert '5' in texts and any(t.startswith('Bar 5, beats 1–4: ') for t in texts)


def test_the_last_label_of_a_system_stays_inside_the_barline():
    text = 'key: Eb major; ' + '; '.join(f'bar {n} in Bb: V beat 2 vi beat 3 in Eb: IV' for n in range(1, 33))
    results, strings, drawn, svg = typed_page(text, (1, 32))
    right = max(system.right for system in drawn.systems)
    assert all(box.right <= right for _, box in drawn.labels + drawn.harmony_labels)


def test_a_score_with_no_reviewed_harmony_is_refused():
    score = (ROOT / CHOPIN[0]).read_bytes()
    index = ScoreIndex(load_toolkit(score).getMEI())
    with pytest.raises(ValueError, match='No Roman numeral labels'):
        compare(from_text('key: Eb major; bar 1 I', index=index), {'version': 1, 'annotations': []}, index)


def test_default_comparison_disabled_bytes(chopin, chopin_annotations):
    page = render(chopin, chopin_annotations, measures=(1, 8))
    assert hashlib.sha256(page.png()).hexdigest() == PNG_HASH


PNG_HASH = '2bcb4833c27458aeb85afe3ea3c2b063ec5266d5915adcaa8dc28eed7f6e5a8c'


def test_coloured_marks_print_in_colour_not_black():
    score, annotations, index, labels = passage('bach')
    image = Image.open(io.BytesIO(render(score, annotations, measures=(1, 8), student_labels=labels).png())).convert('RGB')
    green = sum(1 for r, g, b in image.getdata() if abs(r - 0x22) < 40 and abs(g - 0x88) < 40 and abs(b - 0x33) < 40)
    assert green > 50


def test_rings_and_underlines_print_red_and_notes_never_end_on_one_word():
    score, annotations, index, labels = passage('bach')
    labels = from_text('key: a minor; bar 1 i beat 3 iv; bar 2 i; bar 3 i beat 2 V6 beat 4 III', index=index)
    page = render(score, annotations, measures=(1, 4), student_labels=labels)
    image = Image.open(io.BytesIO(page.png())).convert('RGB')
    red = sum(1 for r, g, b in image.getdata() if r > 180 and g < 60 and b < 60)
    assert red > 500
    svg = ET.fromstring(page.svgs[0])
    overlay = next(g for g in svg.iter() if g.get('class') == 'analysis-over')
    assert any(t.get('class') == 'wrong-label-ring' for t in overlay.iter())
    from engine.check_display import _wrap
    assert all(' ' in line for line in _wrap('Bar 4, beat 1: the tool reads a different chord and key here. Check the notes of the chord, then to.', 3000))


def test_note_numbers_are_discs_and_key_labels_are_regular_weight():
    score, annotations, index, labels = passage('bach')
    svg = render(score, annotations, measures=(1, 8), student_labels=labels).svgs[0]
    assert 'class="note-number"' in svg
    assert not re.search(r'font-weight="bold"[^>]*>[^<]*:</text>', svg)
