from collections import Counter
from fractions import Fraction
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from engine import correct, notes
from engine.check_analysis import from_musicxml
from engine.export import export_musicxml, _document
from engine.render import load_toolkit
from engine.score import ScoreIndex

ROOT = Path(__file__).resolve().parents[1]


def score(body, divisions=1):
    return f'''<score-partwise version="4.0"><part-list><score-part id="P1"><part-name>Piano</part-name></score-part></part-list><part id="P1"><measure number="1"><attributes><divisions>{divisions}</divisions><time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>G</sign><line>2</line></clef></attributes>{body}</measure></part></score-partwise>'''.encode()


def note(pitch='C', duration=2, kind='half'):
    return f'<note><pitch><step>{pitch}</step><octave>4</octave></pitch><duration>{duration}</duration><type>{kind}</type></note>'


def index(data):
    return ScoreIndex(load_toolkit(data).getMEI())


def summary(data):
    return [(m.number, m.length, [(e.staff, e.layer, e.onset, e.duration, e.pitch, e.grace)
                                 for e in m.events if e.pitch]) for m in index(data).measures]


def timeline(data):
    result = []
    for part in ET.fromstring(_document(data)).findall('part'):
        divisions = 1
        for bar in part.findall('measure'):
            cursor = previous = Fraction(0)
            for child in bar:
                if child.tag == 'attributes':
                    divisions = int(child.findtext('divisions', str(divisions)))
                elif child.tag in {'direction', 'harmony'}:
                    result.append((part.get('id'), bar.get('number'), child.tag,
                                   cursor + Fraction(child.findtext('offset', '0')) / divisions,
                                   ET.tostring(child.find('direction-type') if child.tag == 'direction' else child.find('root'))))
                elif child.tag in {'backup', 'forward'}:
                    cursor += Fraction(child.findtext('duration')) / divisions * (-1 if child.tag == 'backup' else 1)
                elif child.tag == 'note':
                    chord = child.find('chord') is not None
                    onset = previous if chord else cursor
                    if child.find('grace') is not None:
                        result.append((part.get('id'), bar.get('number'), 'grace', onset,
                                       child.findtext('pitch/step'), child.findtext('pitch/alter', '0'),
                                       child.findtext('pitch/octave'), chord))
                    elif not chord:
                        previous = cursor
                        cursor += Fraction(child.findtext('duration', '0')) / divisions
    return result


def test_retained_direction_and_harmony_onsets():
    original = score(note() + '<direction><direction-type><words>middle</words></direction-type></direction>'
                     + '<harmony><root><root-step>C</root-step></root><kind>major</kind><offset>1</offset></harmony>' + note('D'))
    text = correct.bars_from_musicxml(original, 1)
    for corrected in [text, text.replace('C4', 'E4')]:
        result = correct.replace_bars(original, corrected)
        assert timeline(result) == timeline(original)
    assert summary(correct.replace_bars(original, text)) == summary(original)


def test_sequential_graces_and_grace_chord():
    grace = '<note><grace/>{}<pitch><step>{}</step><octave>4</octave></pitch><type>eighth</type></note>'
    original = score(grace.format('', 'D') + grace.format('', 'E') + grace.format('<chord/>', 'G') + note('C', 4, 'whole'))
    text = correct.bars_from_musicxml(original, 1)
    assert 'gD4 gE4+G4' in text
    assert notes.encode(notes.decode(text)) == text
    for corrected in [text, text.replace('C4', 'F4')]:
        result = correct.replace_bars(original, corrected)
        assert timeline(result) == timeline(original)


def test_export_mid_bar_divisions():
    original = score(note() + '<attributes><divisions>2</divisions></attributes><note><rest/><duration>4</duration><type>half</type></note>')
    result = export_musicxml(original, {'annotations': [{'type': 'harmony', 'at': {'measure': 1, 'beat': 4}, 'label': 'V'}]})
    assert from_musicxml(result, default_key='C')[0].beat == 4
    assert timeline(result)[0][3] == 3


def test_complex_rest_and_pitched_duration():
    original = (ROOT / 'spike/omr/truth/mozart-k545-1.mxl').read_bytes()
    text = correct.bars_from_musicxml(original, 31)
    assert '10 r' in text
    assert summary(correct.replace_bars(original, text)) == summary(original)
    changed = correct.replace_bars(original, text.replace("G4", "A4"))
    assert index(changed).measure(31).events[0].pitch == "A4"
    original = score(note('C', 16, 'whole'), divisions=4)
    text = 'N1 div=4 ts=4/4 ks=0\nm1 len=16\n1.1: 5 r 11 C4'
    result = correct.replace_bars(original, text)
    bar = index(result).measure(1)
    assert sum(e.duration for e in bar.events) == 4
    assert sum(e.duration for e in bar.events if e.pitch) == Fraction(11, 4)
    assert any(e.tied for e in bar.events)


def test_tie_cannot_cross_rest_or_different_attack():
    original = score(note('C', 4, 'whole'))
    for body in ['1 C4~ r C4 r', '1 C4~ D4 C4 r']:
        result = correct.replace_bars(original, 'N1 div=1 ts=4/4 ks=0\nm1 len=4\n1.1: ' + body)
        assert ET.fromstring(result).find('.//tie') is None


def test_normalization_does_not_change_untouched_imported_timing():
    original = score(note() + '<attributes><divisions>2</divisions></attributes>' + note('D', 4))
    root = ET.fromstring(original)
    ET.SubElement(root.find('part'), 'measure', number='2').extend(ET.fromstring('<body>' + note('E', 8, 'whole') + '</body>'))
    original = ET.tostring(root)
    assert index(original).measure(1).events[-1].duration == 4
    with pytest.raises(correct.CorrectionError, match="untouched bars' imported timing"):
        correct.replace_bars(original, 'N1 div=2 ts=4/4 ks=0\nm2 len=8\n1.1: 8 F4')


FILES = sorted((ROOT / 'spike/omr/truth').glob('*.mxl')) + sorted((ROOT / 'tests/data').glob('*.mxl'))


@pytest.mark.parametrize('path', FILES, ids=lambda p: p.name)
def test_every_real_bar_round_trips(path):
    original = path.read_bytes()
    before = summary(original)
    retained = timeline(original)
    part = ET.fromstring(_document(original)).find("part").get("id")
    accepted, rejected = 0, Counter()
    for bar in index(original).measures:
        try:
            text = correct.bars_from_musicxml(original, bar.number, part=part)
            result = correct.replace_bars(original, text, part=part)
        except correct.CorrectionError as error:
            rejected[str(error)] += 1
        else:
            accepted += 1
            assert summary(result) == before
            assert timeline(result) == retained
    print(f'ROUNDTRIP {path.name}: accepted={accepted}, rejected={sum(rejected.values())}, reasons={dict(rejected)}')
    expected = {
        'bach-269.mxl': (22, 0, ''),
        'chopin-prelude-4.mxl': (26, 0, ''),
        'mozart-k545-1.mxl': (73, 0, ''),
        'chopin_nocturne_op9_no2.mxl': (38, 0, ''),
        'chopin_prelude_op28_no4_audiveris.mxl': (26, 0, ''),
    }
    passed, failed, reason = expected[path.name]
    assert (accepted, sum(rejected.values())) == (passed, failed)
    assert all(reason in message for message in rejected)
    assert accepted + sum(rejected.values()) == len(index(original).measures)


@pytest.mark.parametrize('number', [30, 31, 35, 36])
def test_real_octave_span_edit(number):
    original = (ROOT / 'tests/data/chopin_nocturne_op9_no2.mxl').read_bytes()
    text = correct.bars_from_musicxml(original, number)
    pitch = next(e.pitch for e in notes.decode(text).measure(number).events if e.pitch)
    changed_pitch = 'D' + pitch[-1]
    result = correct.replace_bars(original, text.replace(pitch, changed_pitch))
    expected = notes.decode(text.replace(pitch, changed_pitch)).measure(number)
    def pitched(bar):
        return [(e.staff, e.layer, e.onset, e.duration, e.pitch, e.grace) for e in bar.events if e.pitch]
    assert pitched(index(result).measure(number)) == pitched(expected)
    assert timeline(result) == timeline(original)
    assert [ET.tostring(e) for e in ET.fromstring(result).iter('octave-shift')] == [
        ET.tostring(e) for e in ET.fromstring(_document(original)).iter('octave-shift')]


@pytest.mark.parametrize('kind,size', [('down', '8'), ('up', '8'), ('down', '15')])
def test_octave_shift_within_note_and_across_bars(kind, size):
    start = f'<direction><direction-type><octave-shift type="{kind}" size="{size}"/></direction-type><offset>1</offset></direction>'
    stop = '<direction><direction-type><octave-shift type="stop" size="' + size + '"/></direction-type><offset>2</offset></direction>'
    original = score(start + note('C', 4, 'whole'))
    root = ET.fromstring(original)
    second = ET.SubElement(root.find('part'), 'measure', number='2')
    second.extend(ET.fromstring('<body>' + stop + note('D', 4, 'whole') + '</body>'))
    original = ET.tostring(root)
    text = correct.bars_from_musicxml(original, 1, 2)
    assert 'C4' in text and 'D4' in text
    result = correct.replace_bars(original, text.replace('C4', 'E4').replace('D4', 'F4'))
    assert [e.pitch for m in index(result).measures for e in m.events if e.pitch] == ['E4', 'F4']
    assert timeline(result) == timeline(original)


def test_real_split_bar_edit_and_range_after_split():
    original = (ROOT / 'spike/omr/truth/bach-269.mxl').read_bytes()
    text = correct.bars_from_musicxml(original, 7, part='P1')
    assert 'm7 len=6' in text and '4 G4 2 B4' in text
    result = correct.replace_bars(original, text.replace('B4', 'C5'), part='P1')
    root = ET.fromstring(result)
    assert root.find("part/measure[@number='7']/note/pitch/step").text == 'G'
    assert root.find("part/measure[@number='7a']/note/pitch/step").text == 'C'
    assert root.find("part/measure[@number='7a']/note/pitch/octave").text == '5'
    assert [(e.onset, e.pitch) for e in index(result).measure(7).events if e.staff == 1 and e.pitch] == [
        (Fraction(0), 'G4'), (Fraction(2), 'C5')]
    assert timeline(result) == timeline(original)
    assert [m.number for m in notes.decode(correct.bars_from_musicxml(original, 8, 15, part='P1')).measures] == list(range(8, 16))
    sustained = correct.replace_bars(original, text.replace('4 G4 2 B4', '6 C5'), part='P1')
    assert [(e.onset, e.duration, e.pitch, e.tied) for e in index(sustained).measure(7).events if e.staff == 1 and e.pitch] == [
        (Fraction(0), Fraction(2), 'C5', True), (Fraction(2), Fraction(1), 'C5', False)]
    for before, after in zip(ET.fromstring(_document(original)).findall('part'), root.findall('part')):
        if before.get('id') != 'P1':
            assert ET.tostring(before) == ET.tostring(after)
    for before, after in zip(ET.fromstring(_document(original)).findall('part/measure'), root.findall('part/measure')):
        assert [ET.tostring(e) for e in before.findall('barline')] == [ET.tostring(e) for e in after.findall('barline')]


def test_renumbered_xml_addresses():
    root = ET.fromstring(score(note('C', 4, 'whole')))
    first = root.find('part/measure')
    first.set('number', '5')
    second = ET.SubElement(root.find('part'), 'measure', number='5')
    second.extend(ET.fromstring('<body>' + note('D', 4, 'whole') + '</body>'))
    original = ET.tostring(root)
    assert index(original).renumbered
    text = correct.bars_from_musicxml(original, 2)
    result = correct.replace_bars(original, text.replace('D4', 'F4'))
    assert [e.pitch for m in index(result).measures for e in m.events if e.pitch] == ['C4', 'F4']
    assert [m.get('number') for m in ET.fromstring(result).findall('part/measure')] == ['5', '5']
