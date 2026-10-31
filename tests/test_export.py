from copy import deepcopy
from fractions import Fraction
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest
from music21 import converter

from engine import correct
from engine.check_analysis import from_musicxml
from engine.comparison import from_annotations
from engine.export import export_musicxml, export_romantext, _document
from engine.render import load_toolkit
from engine.score import ScoreIndex, beat_length

ROOT = Path(__file__).resolve().parents[1]


def note_content(data):
    index = ScoreIndex(load_toolkit(data).getMEI())
    return [(m.number, m.beat_length, m.length,
             [(e.measure, e.staff, e.onset, e.duration, e.pitch, e.grace, e.layer, e.tied)
              for e in m.events]) for m in index.measures]


def test_bach_full_score():
    original = (ROOT / 'out/engraving/scores/bach-269.mxl').read_bytes()
    reviewed = json.loads((ROOT / 'examples/engraving/bach-269.json').read_text())
    exported = export_musicxml(original, reviewed)
    assert note_content(original) == note_content(exported)
    assert load_toolkit(exported).renderToSVG(1).startswith('<svg')
    before, after = ET.fromstring(_document(original)), ET.fromstring(exported)
    lyrics = after.findall(".//lyric[@name='roman-analysis']")
    assert len(lyrics) == 22
    assert lyrics[0].findtext('text') == 'G: I'
    assert [l.findtext('text') for l in lyrics].count('ii65') == 1
    clean = deepcopy(after)
    for note in clean.findall('.//note'):
        for lyric in note.findall("lyric[@name='roman-analysis']"):
            note.remove(lyric)
    assert ET.tostring(clean) == ET.tostring(before)

    labels = from_musicxml(exported)
    assert labels == from_annotations(reviewed)
    assert len(labels) == len(lyrics)


def test_placement_and_existing_lyrics():
    original = (ROOT / 'tests/data/export_placement.musicxml').read_bytes()
    analysis = {'annotations': [
        {'type': 'harmony', 'at': {'measure': 1, 'beat': 1}, 'key': 'G', 'label': 'V⁶⁵'},
        {'type': 'harmony', 'at': {'measure': 1, 'beat': 2}, 'label': 'viiø7/V'},
        {'type': 'harmony', 'at': {'measure': 1, 'beat': 3}, 'key': 'D', 'label': 'I'},
        {'type': 'harmony', 'at': {'measure': 1, 'beat': 4}, 'label': 'V7'},
        {'type': 'cadence', 'at': {'measure': 1, 'beat': 4}, 'label': 'HC'},
    ]}
    exported = export_musicxml(original, analysis)
    assert note_content(original) == note_content(exported)
    root = ET.fromstring(exported)
    added = root.findall(".//lyric[@name='roman-analysis-2']")
    assert [lyric.findtext('text') for lyric in added] == ['G: V65']
    assert all(lyric.get('number') == '4' for lyric in added)
    bass = root.findall('part')[-1]
    targets = [n for n in bass.findall('.//note') if n.find("lyric[@name='roman-analysis-2']") is not None]
    assert targets[0].findtext('pitch/octave') == '3'
    words = bass.findall('measure/direction')
    assert [(d.findtext('direction-type/words'), d.findtext('offset'), d.findtext('staff')) for d in words] == [
        ('viiø7/V', '4', '2'), ('D: I', '8', '2'), ('V7', '12', '2')]
    assert root.find(".//lyric[@name='roman-analysis']/text").text == 'song'
    assert 'HC' not in exported.decode()
    analysis['annotations'][0]['label'] = 'V65'
    assert from_musicxml(exported) == from_annotations(analysis)


def test_compound_meter_and_split_bar():
    original = (ROOT / 'tests/data/chopin_nocturne_op9_no2.mxl').read_bytes()
    analysis = {'annotations': [
        {'type': 'harmony', 'at': {'measure': 1, 'beat': 2}, 'label': 'V65'},
    ]}
    exported = export_musicxml(original, analysis)
    assert note_content(original) == note_content(exported)
    labels = from_musicxml(exported, default_key='Eb')
    assert len(labels) == 1
    assert labels[0].beat == 2
    bach = (ROOT / 'out/engraving/scores/bach-269.mxl').read_bytes()
    analysis['annotations'][0]['at'] = {'measure': 7, 'beat': 3}
    result = export_musicxml(bach, analysis)
    root = ET.fromstring(result)
    assert root.findall('part')[-1].find("measure[@number='7a']/note/lyric/text").text == 'V65'
    assert note_content(bach) == note_content(result)
    analysis['annotations'][0]['key'] = 'G'
    assert from_musicxml(result) == from_annotations(analysis)


@pytest.mark.parametrize('at', [{'measure': 99}, {'measure': 1, 'beat': 5}])
def test_bad_position(at):
    with pytest.raises(ValueError):
        export_musicxml((ROOT / 'tests/data/export_placement.musicxml').read_bytes(),
                        {'annotations': [{'type': 'harmony', 'at': at, 'label': 'I'}]})


def test_no_harmony_is_unchanged():
    data = (ROOT / 'tests/data/export_placement.musicxml').read_bytes()
    assert export_musicxml(data, {'annotations': []}) == data


def test_sounding_pitch_and_shared_anchor():
    root = ET.parse(ROOT / 'tests/data/export_placement.musicxml').getroot()
    bass = root.findall('part')[-1]
    transpose = ET.SubElement(bass.find('measure/attributes'), 'transpose', number='1')
    ET.SubElement(transpose, 'diatonic').text = '0'
    ET.SubElement(transpose, 'chromatic').text = '0'
    ET.SubElement(transpose, 'octave-change').text = '-2'
    original = ET.tostring(root)
    analysis = {'annotations': [
        {'type': 'harmony', 'at': {'measure': 1, 'beat': 1}, 'key': 'G', 'label': 'I'},
        {'type': 'harmony', 'at': {'measure': 1, 'beat': 2.5}, 'key': 'G', 'label': 'V'},
        {'type': 'harmony', 'at': {'measure': 1, 'beat': 2.5}, 'label': 'I6'},
    ]}
    exported = export_musicxml(original, analysis)
    assert note_content(exported) == note_content(original)
    bass = ET.fromstring(exported).findall('part')[-1]
    assert bass.find("measure/note[staff='2']/lyric[@name='roman-analysis-2']/text").text == 'G: I'
    lyric = bass.find(".//lyric[@name='roman-analysis-2'][text='V']")
    assert [text.text for text in lyric.findall('text')] == ['V', 'I6']
    assert lyric.findtext('elision') == ' '


def test_debussy_rest_onset_stays_at_reviewed_beat():
    original = (ROOT / 'tests/data/export-debussy-clair.musicxml').read_bytes()
    reviewed = json.loads((ROOT / 'examples/engraving/debussy-clair.json').read_text())
    reviewed['annotations'] = [a for a in reviewed['annotations']
                               if a['type'] == 'harmony' and a['at']['measure'] == 1]
    exported = export_musicxml(original, reviewed)
    assert from_musicxml(exported) == from_annotations(reviewed)
    assert note_content(original) == note_content(exported)
    root = ET.fromstring(exported)
    direction = next(d for d in root.findall('part/measure/direction')
                     if d.findtext('direction-type/words') == 'Db: I6')
    assert direction is not None
    assert direction.findtext('offset') == '0'
    assert direction.findtext('staff') == '2'


def test_debussy_upper_attack_during_bass_sustain_stays_on_bass_staff():
    original = (ROOT / 'tests/data/export-debussy-clair.musicxml').read_bytes()
    analysis = {'annotations': [
        {'type': 'harmony', 'at': {'measure': 2, 'beat': 2},
         'key': 'Db', 'label': 'viiø42/vi'},
    ]}
    exported = export_musicxml(original, analysis)
    bass = ET.fromstring(exported).findall('part')[-1]
    assert not bass.findall(".//lyric[@name='roman-analysis']")
    direction = next(d for d in bass.findall('measure/direction')
                     if d.findtext('direction-type/words') == 'Db: viiø42/vi')
    assert direction.findtext('staff') == '2'
    assert direction.findtext('offset') == '6'
    assert from_musicxml(exported) == from_annotations(analysis)
    assert note_content(original) == note_content(exported)


def test_brahms_cross_staff_low_pitch_stays_on_bass_staff():
    original = (ROOT / 'tests/data/export-brahms-118-2.musicxml').read_bytes()
    reviewed = json.loads((ROOT / 'examples/engraving/brahms-118-2.json').read_text())
    reviewed['annotations'] = [a for a in reviewed['annotations']
                               if a['type'] == 'harmony' and a['at']['measure'] == 7]
    exported = export_musicxml(original, reviewed)
    targets = [n for n in ET.fromstring(exported).findall('.//note')
               if n.find("lyric[@name='roman-analysis']") is not None]
    assert targets
    assert all(n.findtext('staff') == '2' for n in targets)
    assert note_content(original) == note_content(exported)


def test_mozart_rounded_triplet_uses_existing_onset():
    original = (ROOT / 'tests/data/export-mozart-k458.musicxml').read_bytes()
    reviewed = json.loads((ROOT / 'examples/engraving/mozart-k458.json').read_text())
    reviewed['annotations'] = [a for a in reviewed['annotations']
                               if a['type'] == 'harmony' and a['at']['measure'] == 7
                               and a['at'].get('beat') == 2.67]
    assert reviewed['annotations'][0]['at']['beat'] == 2.67
    exported = export_musicxml(original, reviewed)
    bass = ET.fromstring(exported).findall('part')[-1]
    assert bass.find("measure[@number='7']/note/lyric/text").text == 'V'
    assert not bass.findall("measure[@number='7']/direction")
    labels = from_musicxml(exported, default_key='Bb')
    assert len(labels) == 1
    assert labels[0].beat == pytest.approx(8 / 3)
    assert note_content(original) == note_content(exported)


def one_part(*bars, time='<time><beats>4</beats><beat-type>4</beat-type></time>'):
    body = ''.join(f'<measure number="{n}">'
                   + (f'<attributes><divisions>4</divisions>{time}<clef><sign>G</sign><line>2</line></clef></attributes>' if n == 1 else '')
                   + bar + '</measure>' for n, bar in enumerate(bars, 1))
    return (f'<score-partwise version="3.1"><part-list><score-part id="P1"><part-name>Piano</part-name></score-part></part-list>'
            f'<part id="P1">{body}</part></score-partwise>').encode()


@pytest.mark.parametrize('count', [2, 3, 4, 6, 9, 12])
@pytest.mark.parametrize('unit', [2, 4, 8, 16])
def test_romantext_beats_are_music21_beats(count, unit):
    whole_bar = f'<note><rest measure="yes"/><duration>{16 * count // unit}</duration></note>'
    score = one_part(whole_bar, whole_bar, time=f'<time><beats>{count}</beats><beat-type>{unit}</beat-type></time>')
    second = Fraction(3, 2) if count == 2 else 2
    analysis = {'annotations': [{'type': 'harmony', 'at': {'measure': 1, 'beat': 1}, 'label': 'I', 'key': 'C'},
                                {'type': 'harmony', 'at': {'measure': 1, 'beat': float(second)}, 'label': 'V'},
                                {'type': 'harmony', 'at': {'measure': 2, 'beat': 1}, 'label': 'I'}]}
    parsed = converter.parse(export_romantext(score, analysis).decode(), format='romanText')
    offsets = [(rn.measureNumber, rn.offset) for rn in parsed.recurse().getElementsByClass('RomanNumeral')]
    assert offsets == [(1, 0), (1, pytest.approx(float((second - 1) * beat_length(count, unit)), abs=0.01)), (2, 0)]


def test_romantext_skips_empty_labels_and_a_missing_time_signature():
    score = one_part('<note><pitch><step>C</step><octave>4</octave></pitch><duration>16</duration><type>whole</type></note>', time='')
    analysis = {'annotations': [{'type': 'harmony', 'at': {'measure': 1, 'beat': 1}, 'label': 'I', 'key': 'C'},
                                {'type': 'harmony', 'at': {'measure': 1, 'beat': 3}, 'label': ''}]}
    assert export_romantext(score, analysis).decode() == 'm1 C: I\n'


def test_multi_bar_rests_keep_every_bar():
    whole = '<note><pitch><step>C</step><octave>4</octave></pitch><duration>16</duration><type>whole</type></note>'
    rest = '<note><rest measure="yes"/><duration>16</duration><voice>1</voice></note>'
    score = one_part(whole, '<attributes><measure-style><multiple-rest>3</multiple-rest></measure-style></attributes>' + rest,
                     rest, rest, whole)
    assert [m.number for m in ScoreIndex(load_toolkit(score).getMEI()).measures] == [1, 2, 3, 4, 5]
    exported = export_musicxml(score, {'annotations': [{'type': 'harmony', 'at': {'measure': 5, 'beat': 1}, 'label': 'I', 'key': 'C'}]})
    assert ET.fromstring(exported).find("part/measure[@number='5']/note/lyric/text").text == 'C: I'
    assert correct.bars_from_musicxml(score, 5).splitlines()[1] == 'm5 len=4'
    assert load_toolkit(score).getMEI().count('<measure ') == 3
    assert load_toolkit(score, labelled_bars={3}).getMEI().count('<measure ') == 5
    assert ScoreIndex(load_toolkit(score).getMEI()).measure_range(5, 5) == '3-3'


@pytest.mark.parametrize('path', sorted(p for p in (ROOT / 'tests/data').iterdir() if p.suffix in ('.mxl', '.musicxml')), ids=lambda p: p.name)
def test_every_xml_measure_has_one_indexed_segment(path):
    data = path.read_bytes()
    counts = {len(part.findall('measure')) for part in ET.fromstring(_document(data)).findall('part')}
    if len(counts) > 1:
        pytest.skip('parts of different lengths')
    assert counts == {sum(len(m.segments) for m in ScoreIndex(load_toolkit(data).getMEI()).measures)}
