"""Editor export checks against real MusicXML scores (no mocked toolkit)."""
from copy import deepcopy
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from engine.check_analysis import from_musicxml
from engine.comparison import from_annotations
from engine.export import export_musicxml, _document
from engine.render import load_toolkit
from engine.score import ScoreIndex

ROOT = Path(__file__).resolve().parents[1]


def note_content(data):
    index = ScoreIndex(load_toolkit(data).getMEI())
    # Check musical identity; checksum-derived element IDs change with the XML.
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
    assert len(lyrics) == 22  # Includes the original pickup, unlike the spike.
    assert lyrics[0].findtext('text') == 'G: I'
    assert [l.findtext('text') for l in lyrics].count('ii65') == 1
    # Removing only the additions leaves every original XML element unchanged.
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
    assert [lyric.findtext('text') for lyric in added] == ['G: V65', 'viiø7/V']
    assert all(lyric.get('number') == '4' for lyric in added)
    bass = root.findall('part')[-1]
    targets = [n for n in bass.findall('.//note') if n.find("lyric[@name='roman-analysis-2']") is not None]
    assert targets[0].findtext('pitch/octave') == '3'  # chord's lowest note
    assert targets[1].findtext('voice') == '2'  # next onset wins across voices
    assert targets[1].findtext('staff') == '2'
    words = bass.findall('measure/direction')
    assert [(d.findtext('direction-type/words'), d.findtext('offset'), d.findtext('staff')) for d in words] == [
        ('D: I', '8', '2'), ('V7', '12', '2')]
    assert root.find(".//lyric[@name='roman-analysis']/text").text == 'song'
    assert 'HC' not in exported.decode()
    # The exporter anchors beat 2 to the next bass onset, at beat 2.5.
    analysis['annotations'][1]['at']['beat'] = 2.5
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
    # A label in the second repeat fragment of Bach bar 7 remains in that fragment.
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
    # Real fixture with an octave-transposing upper staff: written G4 sounds G2.
    root = ET.parse(ROOT / 'tests/data/export_placement.musicxml').getroot()
    bass = root.findall('part')[-1]
    transpose = ET.SubElement(bass.find('measure/attributes'), 'transpose', number='1')
    ET.SubElement(transpose, 'diatonic').text = '0'
    ET.SubElement(transpose, 'chromatic').text = '0'
    ET.SubElement(transpose, 'octave-change').text = '-2'
    original = ET.tostring(root)
    analysis = {'annotations': [
        {'type': 'harmony', 'at': {'measure': 1, 'beat': 1}, 'key': 'G', 'label': 'I'},
        {'type': 'harmony', 'at': {'measure': 1, 'beat': 1.5}, 'key': 'G', 'label': 'V'},
        {'type': 'harmony', 'at': {'measure': 1, 'beat': 2}, 'label': 'I6'},
    ]}
    exported = export_musicxml(original, analysis)
    assert note_content(exported) == note_content(original)
    bass = ET.fromstring(exported).findall('part')[-1]
    assert bass.find("measure/note[staff='1']/lyric[@name='roman-analysis-2']/text").text == 'G: I'
    lyric = bass.find(".//lyric[@name='roman-analysis-2'][text='V']")
    assert [text.text for text in lyric.findall('text')] == ['V', 'I6']
    assert lyric.findtext('elision') == ' '
