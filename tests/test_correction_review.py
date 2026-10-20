from fractions import Fraction
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from engine import correct, tint
from engine.read_pdf import without_slurs
from engine.render import engrave, load_toolkit
from engine.score import MEI, ScoreIndex

SVG = '{http://www.w3.org/2000/svg}'
READING = Path(__file__).parent / 'data/chopin_prelude_op28_no4_reading.musicxml'


@pytest.mark.parametrize('changed', [[1], [0], [0, 1]])
def test_review_real_pickup_only_draws_changed_bars(changed):
    before = (READING.parents[2] / 'spike/omr/truth/bach-269.mxl').read_bytes()
    text = correct.bars_from_musicxml(before, 1, part='P1')
    pickup, bar1 = text.split('m1 len=', 1)
    if 0 in changed:
        pickup = pickup.replace('G4', 'C5')
    if 1 in changed:
        bar1 = bar1.replace('G4', 'C5')
    after = correct.replace_bars(before, pickup + 'm1 len=' + bar1, part='P1')
    review = correct.review_correction(before, after, part='P1')
    assert review.changed_bars == changed
    assert review.ranges == [(changed[0], changed[-1])]
    assert review.notes == {number: f'Bar {number}: G4 changed to C5.' for number in changed}
    index = ScoreIndex(load_toolkit(after).getMEI())

    def rendered_bars(engraving):
        ids = {g.get('id') for svg in engraving.svgs for g in ET.fromstring(svg).iter()
               if g.get('class') == 'measure'}
        return [m.number for m in index.measures if any(s.id in ids for s in m.segments)]

    assert len(review.engravings) == 1
    assert rendered_bars(review.engravings[0]) == changed
    assert review.engravings[0].png().startswith(b'\x89PNG')
    assert rendered_bars(engrave(after, (1, 1))) == [0, 1]


@pytest.mark.parametrize('replacement', ['gF5 gE5', 'gE5+F5'])
def test_review_real_grace_order_and_chord_corrections(replacement):
    before = (READING.parent / 'chopin_nocturne_op9_no2.mxl').read_bytes()
    text = correct.bars_from_musicxml(before, 7)
    assert 'gE5 gF5' in text
    after = correct.replace_bars(before, text.replace('gE5 gF5', replacement))
    assert replacement in correct.bars_from_musicxml(after, 7)
    review = correct.review_correction(before, after)
    assert review.changed_bars == [7]
    assert review.ranges == [(7, 7)]
    assert review.notes == {7: 'Bar 7: grace notes changed from E5 then F5 to '
                            + ('F5 then E5.' if replacement == 'gF5 gE5' else 'E5 + F5 together.')}
    assert len(review.engravings) == 1
    assert same_music(review.engravings[0], engrave(after, (7, 7)))
    unchanged = correct.review_correction(before, correct.replace_bars(before, text))
    assert unchanged.changed_bars == unchanged.ranges == unchanged.engravings == []
    assert unchanged.notes == {}


def same_music(review, plain):
    def glyphs(engraving):
        found = []
        for svg in engraving.svgs:
            root = ET.fromstring(svg)
            for group in root.iter(f'{SVG}g'):
                if group.get('class') in {'note', 'rest'}:
                    found.append((group.get('class'), group.get('id'),
                                  [use.get('transform') for use in group.iter(f'{SVG}use')]))
        return found

    backings = lambda engraving: sum(svg.count(f'fill="{tint.CHANGED}"') for svg in engraving.svgs)
    assert backings(review) > 0 and backings(plain) == 0
    return glyphs(review) == glyphs(plain) and len(glyphs(plain)) > 0


def corrected_bar18():
    before = READING.read_bytes()
    lines = correct.bars_from_musicxml(before, 18).splitlines()
    text = '\n'.join(lines[:2] + ['1.1: 12 D5 C5 8 E5 E4 A4 36 F#4 12 A4']
                     + [line for line in lines if line.startswith('2.')])
    return before, correct.replace_bars(before, text)


def test_real_triplet_correction_beams_and_bass_alignment():
    before, after = corrected_bar18()
    toolkit = load_toolkit(after)
    index = ScoreIndex(toolkit.getMEI())
    bar = index.measure(18)
    xml = ET.fromstring(after).findall('part/measure')[bar.index - 1]
    melody = [n for n in xml.findall('note') if n.findtext('staff') == '1']
    assert [n.findtext('beam') for n in melody] == [
        'begin', 'end', 'begin', 'continue', 'end', None, None]
    original = ScoreIndex(load_toolkit(before).getMEI()).measure(18)
    bass = lambda m: sorted((e.onset, e.duration, e.pitch) for e in m.events if e.staff == 2)
    assert bass(bar) == bass(original)
    assert {e.onset for e in bar.events if e.staff == 1 and e.pitch in {'E5', 'E4', 'A4'}} >= {
        Fraction(1), Fraction(4, 3), Fraction(5, 3)}
    assert any(e.staff == 2 and e.onset == Fraction(3, 2) and e.pitch == 'F#3' for e in bar.events)
    assert len(ET.fromstring(toolkit.getMEI()).findall(f'.//{MEI}beam')) > 0
    assert engrave(after, (18, 18)).png().startswith(b'\x89PNG')


def test_review_only_changed_bars_and_triplet_note():
    before, after = corrected_bar18()
    review = correct.review_correction(before, after)
    assert review.changed_bars == [18]
    assert review.ranges == [(18, 18)]
    assert 'three eighth notes are now a triplet' in review.notes[18]
    assert 'pitch' not in review.notes[18]
    assert len(review.engravings) == 1
    assert review.engravings[0].png().startswith(b'\x89PNG')
    assert same_music(review.engravings[0], engrave(after, (18, 18)))


def test_review_ranges_pitch_rest_and_no_change():
    before = READING.read_bytes()
    texts = [correct.bars_from_musicxml(before, n) for n in (2, 3, 18)]
    edits = [texts[0].replace('B4', 'A4'), texts[1].replace('B4', 'r'),
             texts[2].replace('D5', 'D#5')]
    after = correct.replace_bars(before, edits[0] + '\n' + '\n'.join(
        line for text in edits[1:] for line in text.splitlines()[1:]))
    review = correct.review_correction(before, after)
    assert review.changed_bars == [2, 3, 18]
    assert review.ranges == [(2, 3), (18, 18)]
    assert 'B4 changed to A4' in review.notes[2]
    assert 'rest' in review.notes[3]
    assert 'D5 changed to D sharp 5' in review.notes[18]
    assert len(review.engravings) == 2
    for image, bounds in zip(review.engravings, review.ranges):
        assert same_music(image, engrave(after, bounds))
    unchanged = correct.review_correction(before, correct.replace_bars(before, texts[0]))
    assert unchanged.changed_bars == unchanged.ranges == unchanged.engravings == []
    assert unchanged.notes == {}


def test_simple_and_compound_meter_beams_on_real_scores():
    simple = READING.read_bytes().replace(b'<beats>2</beats>', b'<beats>4</beats>').replace(
        b'<beat-type>2</beat-type>', b'<beat-type>4</beat-type>')
    compound = (READING.parent / 'chopin_nocturne_op9_no2.mxl').read_bytes()
    for source, old_pitch, new_pitch, expected in [
        (simple, 'B4', 'A4', ['begin', 'end'] * 4),
        (compound, 'G5', 'F5', ['begin', 'continue', 'end'] * 4),
    ]:
        text = correct.bars_from_musicxml(source, 2).replace(old_pitch, new_pitch)
        result = correct.replace_bars(source, text)
        index = ScoreIndex(load_toolkit(result).getMEI())
        bar = ET.fromstring(result).findall('part/measure')[index.measure(2).index - 1]
        bass = [n for n in bar.findall('note') if n.findtext('staff') == '2' and n.find('chord') is None]
        assert [n.findtext('beam') for n in bass] == expected
        assert engrave(result, (2, 2)).png().startswith(b'\x89PNG')


def test_repeated_tuplets_and_sixteenth_hooks():
    source = READING.read_bytes()
    lines = correct.bars_from_musicxml(source, 18).splitlines()
    for melody, expected in [
        ('1.1: 8 D5 C5 E5 E4 A4 F#4 12 A4 36 r',
         ['begin', 'continue', 'end'] * 2 + [None, None]),
        ('1.1: 6 D5 12 C5 6 E5 72 E4', ['begin', 'continue', 'end', None]),
    ]:
        text = '\n'.join(lines[:2] + [melody] + [line for line in lines if line.startswith('2.')])
        result = correct.replace_bars(source, text)
        index = ScoreIndex(load_toolkit(result).getMEI())
        bar = ET.fromstring(result).findall('part/measure')[index.measure(18).index - 1]
        notes = [n for n in bar.findall('note') if n.findtext('staff') == '1']
        assert [n.findtext('beam') for n in notes] == expected
        if melody.startswith('1.1: 6'):
            assert [n.findtext('beam[@number="2"]') for n in notes] == [
                'forward hook', None, 'backward hook', None]
        else:
            assert len(bar.findall('note/notations/tuplet[@type="start"]')) == 2
        assert engrave(result, (18, 18)).png().startswith(b'\x89PNG')


def test_triplet_beam_crosses_meter_beat():
    source = READING.read_bytes()
    lines = correct.bars_from_musicxml(source, 18).splitlines()
    text = '\n'.join(lines[:2] + ['1.1: 12 D5 C5 E5 6 E4 8 A4 F#4 E4 24 A4 6 r']
                     + [line for line in lines if line.startswith('2.')])
    result = correct.replace_bars(source, text)
    index = ScoreIndex(load_toolkit(result).getMEI())
    bar = ET.fromstring(result).findall('part/measure')[index.measure(18).index - 1]
    triplet = [n for n in bar.findall('note') if n.find('time-modification') is not None]
    assert [n.findtext('beam') for n in triplet] == ['begin', 'continue', 'end']
    assert engrave(result, (18, 18)).png().startswith(b'\x89PNG')


def test_review_does_not_back_rests_the_user_left_alone():
    before = (READING.parent / 'pdf_warnings/haydn_she_never_told_audiveris.musicxml').read_bytes()
    before = without_slurs(before)
    text = correct.bars_from_musicxml(before, 18, part='P2')
    after = correct.replace_bars(before, text.replace('C4+Ab4', 'C4+Bb4', 1), part='P2')
    review = correct.review_correction(before, after, part='P2')
    assert review.changed_bars == [18]
    assert review.engravings[0].svgs[0].count(f'fill="{tint.CHANGED}"') == 1
    assert 'rests changed' not in review.notes[18]
