"""Replay genuine cached recognition through the PDF reader and engraving engine."""

from collections import Counter
from fractions import Fraction
import io
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

import pytest

from engine.read_pdf import SETTINGS, clean, read_pdf
from engine.render import load_toolkit
from engine.score import ScoreIndex
from engine.triplets import infer_triplets
from engine.tuplet_rests import infer_tuplet_rests

DATA = Path(__file__).parent / 'data/tuplet_rests'


@pytest.mark.parametrize('production', [False, True])
@pytest.mark.parametrize('position', ['before', 'within', 'end'])
@pytest.mark.parametrize('element', [
    '<direction><direction-type><dynamics><p/></dynamics></direction-type>'
    '<offset>6</offset><voice>2</voice><staff>2</staff></direction>',
    '<direction><direction-type><words>dolce</words></direction-type>'
    '<staff>2</staff></direction>',
    '<direction><direction-type><wedge type="crescendo"/></direction-type>'
    '<voice>2</voice><staff>1</staff></direction>',
    '<direction><direction-type><dynamics><p/></dynamics></direction-type>'
    '<offset>-6</offset><voice>1</voice><staff>1</staff></direction>',
    '<sound tempo="72"/>',
    '<harmony><root><root-step>C</root-step></root><kind>major</kind></harmony>',
    '<attributes><divisions>24</divisions></attributes>',
    '<barline location="middle"><bar-style>regular</bar-style></barline>',
])
def test_unproven_cursor_elements_leave_bar_exactly_as_read(production, position, element):
    root = ET.fromstring((DATA / 'independent_voice.musicxml').read_bytes())
    measure = root.find('part/measure')
    index = (list(measure).index(measure.find('note')) if position == 'before'
             else list(measure).index(measure.findall('note')[1]) if position == 'within'
             else list(measure).index(measure.find('backup')))
    measure.insert(index, ET.fromstring(element))
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w') as container:
        container.writestr('score.musicxml', ET.tostring(root))
    mxl = archive.getvalue()
    before = clean(mxl)
    reading = (read_pdf((DATA / 'ave_maria.pdf').read_bytes(), raw=lambda *args: (mxl, [])).musicxml
               if production else infer_tuplet_rests(before))
    assert reading == before


@pytest.mark.parametrize('production', [False, True])
@pytest.mark.parametrize('position', ['before', 'within', 'end', 'independent'])
def test_directions_follow_only_their_own_voice_segment(production, position):
    root = ET.fromstring((DATA / 'independent_voice.musicxml').read_bytes())
    measure = root.find('part/measure')
    independent = position == 'independent'
    index = (list(measure).index(measure.find('note')) if position == 'before'
             else list(measure).index(measure.findall('note')[1]) if position == 'within'
             else list(measure).index(measure.find('forward')) + 1 if independent
             else list(measure).index(measure.find('backup')))
    staff = 2 if independent else 1
    measure.insert(index, ET.fromstring(f'''<direction><direction-type><dynamics><p/></dynamics>
        </direction-type><voice>{staff}</voice><staff>{staff}</staff></direction>'''))
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w') as container:
        container.writestr('score.musicxml', ET.tostring(root))
    mxl = archive.getvalue()
    before = clean(mxl)
    reading = (read_pdf((DATA / 'ave_maria.pdf').read_bytes(), raw=lambda *args: (mxl, [])).musicxml
               if production else infer_tuplet_rests(before))
    assert ET.fromstring(reading).findtext('.//note/duration') == '4'
    def timestamp(score):
        mei = ET.fromstring(load_toolkit(score).getMEI())
        return next(e.get('tstamp') for e in mei.iter() if e.tag.endswith('}dynam'))
    assert timestamp(reading) == {'before': '1', 'within': '1.1667',
                                  'end': '5', 'independent': '1.5'}[position]
    if independent:
        assert timestamp(reading) == timestamp(before)


@pytest.mark.parametrize('production', [False, True])
@pytest.mark.parametrize('mark', ['time-modification', 'notations'])
def test_other_tuplet_on_repaired_staff_leaves_bar_exactly_as_read(production, mark):
    root = ET.fromstring((DATA / 'independent_voice.musicxml').read_bytes())
    for element in root.find('part/measure'):
        if element.findtext('voice') == '2':
            element.find('staff').text = '1'
    note = root.find('part/measure').findall('note')[-2]
    if mark == 'time-modification':
        note.append(ET.fromstring('''<time-modification><actual-notes>3</actual-notes>
            <normal-notes>2</normal-notes></time-modification>'''))
        note.find('duration').text = '8'
    else:
        note.append(ET.fromstring('<notations><tuplet type="start" number="1"/></notations>'))
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w') as container:
        container.writestr('score.musicxml', ET.tostring(root))
    mxl = archive.getvalue()
    before = clean(mxl)
    reading = (read_pdf((DATA / 'ave_maria.pdf').read_bytes(), raw=lambda *args: (mxl, [])).musicxml
               if production else infer_tuplet_rests(before))
    assert reading == before


@pytest.mark.parametrize('production', [False, True])
def test_interleaved_reading_preserves_independent_note_at_thirteen_twelfths(production):
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w') as container:
        container.writestr('score.musicxml', (DATA / 'interleaved_voices.musicxml').read_bytes())
    mxl = archive.getvalue()
    before = clean(mxl)
    reading = (read_pdf((DATA / 'ave_maria.pdf').read_bytes(), raw=lambda *args: (mxl, [])).musicxml
               if production else infer_tuplet_rests(before))
    assert reading == before
    assert [(e.pitch, e.onset) for e in _bar(reading, 1).events if e.pitch == 'G3'] == [
        ('G3', Fraction(13, 12)),
    ]


@pytest.mark.parametrize('production', [False, True])
@pytest.mark.parametrize('layout', ['interleaved', 'resumed', 'other_interleaved'])
@pytest.mark.parametrize('element', ['note', 'rest', 'forward', 'grace'])
def test_ambiguous_voice_serialization_leaves_bar_exactly_as_read(production, layout, element):
    root = ET.fromstring((DATA / 'independent_voice.musicxml').read_bytes())
    measure = root.find('part/measure')
    if element == 'forward':
        extra = ET.fromstring('<forward><duration>12</duration><voice>3</voice><staff>2</staff></forward>')
    else:
        extra = ET.fromstring('''<note><pitch><step>G</step><octave>3</octave></pitch>
            <duration>12</duration><voice>3</voice><type>eighth</type><staff>2</staff></note>''')
        if element == 'rest':
            extra.remove(extra.find('pitch'))
            extra.insert(0, ET.Element('rest'))
        elif element == 'grace':
            extra.remove(extra.find('duration'))
            extra.insert(0, ET.Element('grace'))
    if layout == 'interleaved':
        # A second voice interrupts the tuplets before the repaired voice's final rest.
        position = list(measure).index(measure.findall('note')[6])
        measure.insert(position, extra)
        measure.insert(position + 1, ET.fromstring('<backup><duration>12</duration></backup>'))
    elif layout == 'resumed':
        position = list(measure).index(measure.findall('note')[6])
        measure.insert(position, ET.fromstring('<backup><duration>12</duration></backup>'))
        measure.insert(position + 1, extra)
        measure.insert(position + 2, ET.fromstring('<backup><duration>12</duration></backup>'))
    else:
        measure.append(extra)
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w') as container:
        container.writestr('score.musicxml', ET.tostring(root))
    mxl = archive.getvalue()
    before = clean(mxl)
    reading = (read_pdf((DATA / 'ave_maria.pdf').read_bytes(), raw=lambda *args: (mxl, [])).musicxml
               if production else infer_tuplet_rests(before))
    assert reading == before


@pytest.mark.parametrize('production', [False, True])
def test_independent_partial_backup_keeps_its_onset_after_rest_repair(production):
    root = ET.fromstring((DATA / 'independent_voice.musicxml').read_bytes())
    measure = root.find('part/measure')
    measure.append(ET.fromstring('<backup><duration>72</duration></backup>'))
    measure.append(ET.fromstring('''<note><pitch><step>E</step><octave>3</octave></pitch>
        <duration>72</duration><voice>3</voice><type>half</type><dot/><staff>2</staff></note>'''))
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w') as container:
        container.writestr('score.musicxml', ET.tostring(root))
    mxl = archive.getvalue()
    before = clean(mxl)
    reading = (read_pdf((DATA / 'ave_maria.pdf').read_bytes(), raw=lambda *args: (mxl, [])).musicxml
               if production else infer_tuplet_rests(before))
    repaired = ET.fromstring(reading)
    assert repaired.findtext('.//note/duration') == '4'
    bass = lambda xml: [(e.pitch, e.onset) for e in _bar(xml, 1).events if e.pitch == 'E3']
    assert bass(reading) == bass(before) == [('E3', Fraction(1))]
    assert [b.findtext('duration') for b in repaired.findall('.//backup')] == ['96', '72']
    assert infer_tuplet_rests(reading) == reading


@pytest.mark.parametrize('complete', [True, False])
def test_independent_bass_forward_keeps_its_onset_after_rest_repair(complete):
    root = ET.fromstring((DATA / 'independent_voice.musicxml').read_bytes())
    measure = root.find('part/measure')
    if not complete:
        measure.remove(measure.findall('note')[-1])
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w') as container:
        container.writestr('score.musicxml', ET.tostring(root))
    mxl = archive.getvalue()
    before = clean(mxl)
    reading = read_pdf((DATA / 'ave_maria.pdf').read_bytes(), raw=lambda *args: (mxl, [])).musicxml
    repaired = ET.fromstring(reading)
    assert repaired.findtext('.//note/duration') == '4'
    assert repaired.findtext('.//backup/duration') == '96'
    assert repaired.findtext('.//forward/duration') == '12'
    bass = lambda xml: [(e.pitch, e.onset) for e in _bar(xml, 1).events if e.pitch == 'G3']
    assert bass(reading) == bass(before) == [('G3', Fraction(1, 2))]
    assert infer_tuplet_rests(reading) == reading


@pytest.mark.parametrize('production', [False, True])
@pytest.mark.parametrize('trailing', [0, 30])
@pytest.mark.parametrize('staff', [1, 2])
def test_offset_tuplet_voice_keeps_its_onsets_after_rest_repair(production, trailing, staff):
    root = ET.fromstring((DATA / 'independent_voice.musicxml').read_bytes())
    measure = root.find('part/measure')
    for element in list(measure)[list(measure).index(measure.find('backup')) + 1:]:
        measure.remove(element)
    measure.append(ET.fromstring(
        '<forward><duration>18</duration><voice>2</voice><staff>2</staff></forward>'))
    for _ in range(3):
        measure.append(ET.fromstring('''<note><pitch><step>G</step><octave>3</octave></pitch>
            <duration>16</duration><voice>2</voice><type>quarter</type>
            <time-modification><actual-notes>3</actual-notes><normal-notes>2</normal-notes></time-modification>
            <staff>2</staff></note>'''))
    if trailing:
        measure.append(ET.fromstring(
            f'<forward><duration>{trailing}</duration><voice>2</voice><staff>2</staff></forward>'))
    for element in measure:
        if element.findtext('voice') == '2':
            element.find('staff').text = str(staff)
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w') as container:
        container.writestr('score.musicxml', ET.tostring(root))
    mxl = archive.getvalue()
    before = clean(mxl)
    reading = (read_pdf((DATA / 'ave_maria.pdf').read_bytes(), raw=lambda *args: (mxl, [])).musicxml
               if production else infer_tuplet_rests(before))
    repaired = ET.fromstring(reading)
    if staff == 1:
        assert reading == before
        return
    assert repaired.findtext('.//note/duration') == '4'
    assert [e.findtext('duration') for e in repaired.findall('.//forward')] == (
        ['18', '30'] if trailing else ['18'])
    bass = lambda xml: [(e.pitch, e.onset) for e in _bar(xml, 1).events if e.pitch == 'G3']
    assert bass(reading) == bass(before) == [
        ('G3', Fraction(3, 4)), ('G3', Fraction(17, 12)), ('G3', Fraction(25, 12)),
    ]
    assert infer_tuplet_rests(reading) == reading


@pytest.mark.parametrize('production', [False, True])
@pytest.mark.parametrize('staff', [1, 2])
@pytest.mark.parametrize('count,trailing,leading', [(14, 4, 0), (14, 0, 0), (15, 0, 0), (14, 0, 6)])
def test_ordinary_offset_voice_keeps_its_timeline_after_rest_repair(production, staff, count, trailing, leading):
    root = ET.fromstring((DATA / 'independent_voice.musicxml').read_bytes())
    measure = root.find('part/measure')
    for element in list(measure)[list(measure).index(measure.find('backup')) + 1:]:
        measure.remove(element)
    if leading:
        measure.append(ET.fromstring(f'''<note><rest/><duration>{leading}</duration>
            <voice>2</voice><type>16th</type><staff>{staff}</staff></note>'''))
    measure.append(ET.fromstring(
        f'<forward><duration>8</duration><voice>2</voice><staff>{staff}</staff></forward>'))
    for _ in range(count):
        measure.append(ET.fromstring(f'''<note><pitch><step>G</step><octave>3</octave></pitch>
            <duration>6</duration><voice>2</voice><type>16th</type><staff>{staff}</staff></note>'''))
    if trailing:
        measure.append(ET.fromstring(
            f'<forward><duration>{trailing}</duration><voice>2</voice><staff>{staff}</staff></forward>'))
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w') as container:
        container.writestr('score.musicxml', ET.tostring(root))
    mxl = archive.getvalue()
    before = clean(mxl)
    reading = (read_pdf((DATA / 'ave_maria.pdf').read_bytes(), raw=lambda *args: (mxl, [])).musicxml
               if production else infer_tuplet_rests(before))
    repaired = ET.fromstring(reading)
    assert repaired.findtext('.//note/duration') == '4'
    assert [e.findtext('duration') for e in repaired.findall('.//forward')] == (
        ['8', str(trailing)] if trailing else ['8'])
    bass = lambda xml: [(e.pitch, e.onset) for e in _bar(xml, 1).events if e.pitch == 'G3']
    assert bass(reading) == bass(before)
    cursor, onsets = 0, []
    for element in repaired.find('part/measure'):
        if element.findtext('pitch/step') == 'G':
            onsets.append(cursor)
        length = int(element.findtext('duration', '0'))
        if element.tag == 'backup':
            cursor -= length
        elif element.tag in ('note', 'forward'):
            cursor += length
    assert onsets == [leading + 8 + i * 6 for i in range(count)]
    assert cursor == leading + 8 + count * 6 + trailing
    assert infer_tuplet_rests(reading) == reading


def _reading():
    variants = [(DATA / f'ave_maria_variant{i}.mxl').read_bytes() for i in range(3)]

    def raw(data, audiveris, options, deadline):
        return variants[SETTINGS.index(options)], []

    return read_pdf((DATA / 'ave_maria.pdf').read_bytes(), raw=raw).musicxml


def _bar(score, number):
    index = ScoreIndex(load_toolkit(score).getMEI())
    return next(m for m in index.measures if m.number == number)


def test_real_sextuplet_rests_reach_engine_on_the_correct_sixth():
    reading = _reading()
    bar = _bar(reading, 6)
    notes = [e for e in bar.events if e.staff == 2 and e.pitch]
    assert [(e.pitch, e.onset) for e in notes[:4]] == [
        ('E4', Fraction(1, 6)), ('G4', Fraction(1, 6)),
        ('G4', Fraction(1, 3)), ('Bb4', Fraction(1, 3)),
    ]
    truth = _bar((DATA / 'ave_maria_truth.mxl').read_bytes(), 6)
    events = lambda m: Counter((e.staff, e.pitch, e.onset) for e in m.events if e.pitch)
    # Recognition also loses a bass rest, so its later hidden forwards need the repaired targets.
    assert events(bar) == events(truth)
    assert infer_tuplet_rests(reading) == reading
    before = infer_triplets(clean((DATA / 'ave_maria_variant2.mxl').read_bytes()))
    pitches = lambda m: Counter(e.pitch for e in m.events if e.pitch)
    assert pitches(bar) == pitches(_bar(before, 6))


def test_real_hidden_forwards_preserve_bass_beats_after_rest_repair():
    bar = _bar(_reading(), 6)
    assert [(e.pitch, e.onset) for e in bar.events if e.staff == 3 and e.pitch] == [
        ('A1', 0), ('A2', 0), ('A1', 1), ('A2', 1),
        ('F#1', 2), ('F#2', 2), ('F#1', 3), ('F#2', 3),
    ]


def test_real_reading_without_exact_rest_saving_is_left_alone():
    score = infer_triplets(clean((DATA / 'ave_maria_variant2.mxl').read_bytes()))
    root = ET.fromstring(score)
    part = root.findall('part')[1]
    measure = part.findall('measure')[5]
    # A further missed duration makes the sextuplet explanation insufficient for this real bar.
    note = measure.find('note')
    note.find('duration').text = str(int(note.findtext('duration')) * 2)
    note.find('type').text = 'eighth'
    isolated = ET.Element('score-partwise')
    isolated.append(root.find('part-list'))
    extracted = ET.SubElement(isolated, 'part', id=part.get('id'))
    # Keep the original opening attributes inside a measure so divisions and meter are inherited.
    opening = ET.SubElement(extracted, 'measure', number='0', implicit='yes')
    opening.append(part.find('measure/attributes'))
    extracted.append(measure)
    xml = ET.tostring(isolated)
    assert infer_tuplet_rests(xml) == xml
