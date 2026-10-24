import json
from pathlib import Path

import pytest

from engine.draft import Chord
from engine.part_writing import as_text, check
from engine.render import load_toolkit
from engine.score import ScoreIndex

DATA = Path(__file__).parent / 'data/part_writing_ap'
SPANS = json.loads((DATA / 'spans.json').read_text())


def read(name):
    return ScoreIndex(load_toolkit((DATA / f'{name}.musicxml').read_bytes()).getMEI())


def spans(name):
    return [Chord(1 if name.startswith('beat_to') else n, n if name.startswith('beat_to') else 1,
                  'c' if name.endswith('_minor') else 'C', label, n, 4, None)
            for n, label in enumerate(SPANS[name], 1)]


@pytest.mark.parametrize('explicit', [False, True])
@pytest.mark.parametrize('name,rule', [
    ('unequal_upper_forbidden', 'unequal_fifths'),
    ('unequal_bass_up', 'unequal_fifths'),
    ('unequal_bass_down', 'unequal_fifths'),
    ('contrary_fifths', 'parallel_fifths'),
    ('contrary_octaves', 'parallel_octaves'),
    ('beat_to_beat_fifths', 'parallel_fifths'),
    ('cad64_fourth_up', 'unresolved_cadential_tone'),
    ('cad64_sixth_up', 'unresolved_cadential_tone'),
    ('unresolved_diminished_lt', 'unresolved_leading_tone'),
    ('doubled_seventh', 'doubled_seventh'),
])
def test_ap_investigation_misses(name, rule, explicit):
    hits = check(read(name), spans(name) if explicit else None)
    assert rule in {h.rule for h in hits}
    if name.startswith('contrary'):
        assert any('by contrary motion' in h.why for h in hits if h.rule == rule)


@pytest.mark.parametrize('explicit', [False, True])
@pytest.mark.parametrize('name', [
    'ascending_v43', 'ascending_v43_minor', 'ascending_viio6',
    'descending_d5_p5', 'p5_d5_up', 'p5_d5_down', 'cad64_good',
])
def test_ap_accepted_motions(name, explicit):
    hits = check(read(name), spans(name) if explicit else None)
    assert not {h.rule for h in hits} & {'unequal_fifths', 'unresolved_seventh', 'unresolved_cadential_tone'}


def test_bwv85_unequal_fifths():
    path = DATA.parent / 'part_writing_bwv85.6.musicxml'
    index = ScoreIndex(load_toolkit(path.read_bytes()).getMEI())
    found = [h for h in check(index) if h.rule == 'unequal_fifths']
    assert found == []


def test_ap_severity_sentences():
    assert 'Moderate:' in as_text(read('contrary_fifths'))
    assert any(h.why.startswith('Minor:') for h in check(read('doubled_seventh'), spans('doubled_seventh'))
               if h.rule == 'doubled_seventh')


def test_explicit_cad64_must_resolve_even_when_dominant_is_missing():
    index = read('cad64_to_tonic')
    chords = [Chord(n, 1, 'C', label, n, 4, None)
              for n, label in enumerate(('Cad64', 'I', 'I'), 1)]
    found = [h for h in check(index, chords) if h.rule == 'unresolved_cadential_tone']
    assert {(h.voices, h.bars) for h in found} == {
        (((1, 1),), (1, 2)), (((2, 1),), (1, 2)),
    }
    assert all(h.why.startswith('Serious:') for h in found)
    assert any("dominant's third" in h.why for h in found)
    assert any("dominant's fifth" in h.why for h in found)
    assert not any(h.rule == 'unresolved_cadential_tone' for h in check(index))


def test_forbidden_unequal_fifths_have_moderate_severity():
    index = read('unequal_upper_forbidden')
    found = [h for h in check(index) if h.rule == 'unequal_fifths']
    assert found
    assert all(h.why.startswith('Moderate:') for h in found)
    assert all('Moderate:' in line for line in as_text(index).splitlines() if 'Unequal fifths:' in line)


@pytest.mark.parametrize('explicit', [False, True])
def test_diminished_seventh_outer_leading_tone(explicit):
    import xml.etree.ElementTree as ET
    xml = ET.parse(DATA / 'unresolved_diminished_lt.musicxml')
    pitch = xml.getroot().findall('part')[2].find('measure/note/pitch')
    pitch.find('step').text = 'A'
    ET.SubElement(pitch, 'alter').text = '-1'
    pitch.find('octave').text = '3'
    index = ScoreIndex(load_toolkit(ET.tostring(xml.getroot())).getMEI())
    chords = [Chord(1, 1, 'C', 'viio65', 1, 4, None), Chord(2, 1, 'C', 'I6', 2, 4, None)]
    assert any(h.rule == 'unresolved_leading_tone' and h.voices == ((1, 1),)
               for h in check(index, chords if explicit else None))


def test_passing_v43_with_an_ornamental_seventh():
    from music21 import corpus
    from music21.musicxml.m21ToXml import GeneralObjectExporter
    index = ScoreIndex(load_toolkit(GeneralObjectExporter(corpus.parse('bach/bwv133.6')).parse()).getMEI())
    assert not any(h.rule == 'unequal_fifths' and h.bars == (0, 1) for h in check(index))


def test_unequal_fifths_rule_includes_leaps():
    import xml.etree.ElementTree as ET
    xml = ET.parse(DATA / 'unequal_upper_forbidden.musicxml')
    xml.getroot().findall('part')[0].findall('measure')[1].find('note/pitch/octave').text = '6'
    index = ScoreIndex(load_toolkit(ET.tostring(xml.getroot())).getMEI())
    assert any(h.rule == 'unequal_fifths' for h in check(index))


@pytest.mark.parametrize('pitches,figure', [
    (('C5', 'C4', 'F3', 'D3'), 'ii7'),
    (('C5', 'C4', 'D3', 'F3'), 'ii65'),
    (('E5', 'E4', 'A3', 'F3'), 'IV7'),
    (('A4', 'A3', 'D3', 'B2'), 'viiø7'),
])
def test_incomplete_doubled_seventh_without_explicit_spans(pitches, figure):
    import xml.etree.ElementTree as ET
    xml = ET.parse(DATA / 'doubled_ii7.musicxml')
    for part, value in zip(xml.getroot().findall('part'), pitches):
        pitch = part.find('measure/note/pitch')
        pitch.find('step').text = value[0]
        pitch.find('octave').text = value[1]
    index = ScoreIndex(load_toolkit(ET.tostring(xml.getroot())).getMEI())
    chords = [Chord(n, 1, 'C', label, n, 4, None)
              for n, label in enumerate([figure, 'V', 'I'], 1)]
    for supplied in (chords, None):
        assert any(h.rule == 'doubled_seventh' and h.bars == (1,)
                   and h.voices == ((1, 1), (2, 1)) for h in check(index, supplied))


def test_incomplete_seventh_with_doubled_root_is_accepted():
    import xml.etree.ElementTree as ET
    xml = ET.parse(DATA / 'doubled_ii7.musicxml')
    for part in xml.getroot().findall('part')[:2]:
        part.find('measure/note/pitch/step').text = 'D'
    index = ScoreIndex(load_toolkit(ET.tostring(xml.getroot())).getMEI())
    assert not any(h.rule == 'doubled_seventh' for h in check(index))
