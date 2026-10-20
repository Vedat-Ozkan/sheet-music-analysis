import importlib
import io
from fractions import Fraction
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

from engine.render import load_toolkit
from engine.score import ScoreIndex
from engine.triplets import infer_triplets

DATA = Path(__file__).parent / 'data'
reader = importlib.import_module('engine.read_pdf')


def _read_cached(monkeypatch, name):
    xml = (DATA / name).read_bytes()

    def cached_run(audiveris, options, source, work, env, deadline):
        with zipfile.ZipFile(Path(work) / 'score.mxl', 'w') as archive:
            archive.writestr('score.musicxml', xml)
        return ''

    monkeypatch.setattr(reader, 'run', cached_run)
    pdf = (DATA / 'chopin-28-4-mutopia.pdf').read_bytes()
    return xml, reader.read_pdf(pdf, audiveris='cached-audiveris').musicxml


def test_real_partly_tagged_beam_reaches_engine_with_correct_timing(monkeypatch):
    before, after = _read_cached(monkeypatch, 'triplet_mayer.musicxml')
    index = ScoreIndex(load_toolkit(after).getMEI())
    notes = [e for m in index.measures if m.number == 8 for e in m.events if e.staff == 2 and e.pitch]
    assert [(e.pitch, e.onset, e.duration) for e in notes[2:8]] == [
        ('A4', Fraction(1), Fraction(1, 6)),
        ('Bb4', Fraction(7, 6), Fraction(1, 6)),
        ('C5', Fraction(4, 3), Fraction(1, 6)),
        ('Bb4', Fraction(3, 2), Fraction(1, 6)),
        ('F4', Fraction(5, 3), Fraction(1, 6)),
        ('D4', Fraction(11, 6), Fraction(1, 6)),
    ]
    assert notes[-1].onset == 3
    assert sum(e.pitch is not None for m in index.measures for e in m.events) == sum(
        e.pitch is not None for m in ScoreIndex(load_toolkit(before).getMEI()).measures for e in m.events)
    assert infer_triplets(after) == after


def test_real_compound_meter_merged_voice_is_left_alone(monkeypatch):
    before, after = _read_cached(monkeypatch, 'triplet_hensel.musicxml')
    cleaned = io.BytesIO()
    with zipfile.ZipFile(cleaned, 'w') as archive:
        archive.writestr('score.musicxml', before)
    before = reader.clean(cleaned.getvalue())
    assert ET.tostring(ET.fromstring(after)) == ET.tostring(ET.fromstring(before))
    a = ScoreIndex(load_toolkit(before).getMEI())
    b = ScoreIndex(load_toolkit(after).getMEI())
    events = lambda index: [(m.number, e.staff, e.pitch, e.onset, e.duration)
                            for m in index.measures for e in m.events]
    assert events(a) == events(b)


def _note(typ, duration, triplet=False, beam=None):
    note = ET.Element('note')
    pitch = ET.SubElement(note, 'pitch')
    ET.SubElement(pitch, 'step').text = 'C'
    ET.SubElement(pitch, 'octave').text = '4'
    ET.SubElement(note, 'duration').text = str(duration)
    ET.SubElement(note, 'voice').text = '1'
    ET.SubElement(note, 'type').text = typ
    if triplet:
        tm = ET.SubElement(note, 'time-modification')
        ET.SubElement(tm, 'actual-notes').text = '3'
        ET.SubElement(tm, 'normal-notes').text = '2'
    if beam:
        ET.SubElement(note, 'beam', number='1').text = beam
    return note


def _score(measures, divisions=6):
    root = ET.Element('score-partwise')
    part = ET.SubElement(root, 'part', id='P1')
    for i, notes in enumerate(measures):
        measure = ET.SubElement(part, 'measure', number=str(i + 1))
        if i == 0:
            attributes = ET.SubElement(measure, 'attributes')
            ET.SubElement(attributes, 'divisions').text = str(divisions)
            time = ET.SubElement(attributes, 'time')
            ET.SubElement(time, 'beats').text = '4'
            ET.SubElement(time, 'beat-type').text = '4'
        measure.extend(notes)
    return ET.tostring(root)


def test_quarter_triplets_need_matching_printed_voice_rhythm():
    printed = [_note('quarter', 4, True) for _ in range(3)] + [_note('half', 12)]
    missing = [_note('quarter', 6) for _ in range(3)] + [_note('half', 12)]
    score = _score([printed, missing])
    fixed = ET.fromstring(infer_triplets(score))
    assert len(fixed.findall('.//time-modification')) == 6
    printed[-1] = _note('quarter', 6)
    printed.append(_note('quarter', 6))
    score = _score([printed, missing])
    assert infer_triplets(score) == score


def test_first_printed_triplet_in_wide_beam_and_backup_reset():
    beam = [_note('eighth', 2 if i < 3 else 3, i < 3,
                  'begin' if i == 0 else 'end' if i == 5 else 'continue') for i in range(6)]
    backup = ET.Element('backup')
    ET.SubElement(backup, 'duration').text = '27'
    second = _note('whole', 24)
    second.find('voice').text = '2'
    score = _score([beam + [_note('half', 12), backup, second]])
    fixed = ET.fromstring(infer_triplets(score))
    assert len(fixed.findall('.//time-modification')) == 6
    assert fixed.findtext('.//backup/duration') == '72'
    assert fixed.findtext('.//note[voice="2"]/duration') == '72'
    assert infer_triplets(ET.tostring(fixed)) == ET.tostring(fixed)


def test_sixteenth_triplets_found_by_beat_not_only_eighths():
    def bar(each, tagged):
        beam = ['begin', 'continue', 'end'] * 2
        return [_note('half', 24), _note('quarter', 12)] + [
            _note('16th', each, tagged, beam[i]) for i in range(6)]
    printed, missing = bar(2, True), bar(3, False)
    fixed = ET.fromstring(infer_triplets(_score([printed, missing], divisions=12)))
    second = fixed.findall('part/measure')[1]
    assert len(second.findall('.//time-modification')) == 6
    assert sum(int(n.findtext('duration')) for n in second.findall('note')) == 48 * 3
    plain = _score([[_note('half', 24), _note('half', 24)], missing], divisions=12)
    assert infer_triplets(plain) == plain


def test_real_brahms_reading_with_forwards_gets_exact_bars(monkeypatch):
    before, after = _read_cached(monkeypatch, 'triplet_brahms_fruhlingstrost.musicxml')
    count = lambda xml: len(ET.fromstring(xml).findall('.//time-modification'))
    assert count(after) - count(before) == 144
    notes = lambda xml: len(ET.fromstring(xml).findall('.//note'))
    assert notes(after) == notes(before)
    def span(xml):
        out = []
        for part in ET.fromstring(xml).findall('part'):
            div = 1
            for m in part.findall('measure'):
                div = int(m.findtext('attributes/divisions', div))
                cursor = 0
                for e in m:
                    if e.tag == 'note' and e.find('chord') is None and e.find('grace') is None:
                        cursor += int(e.findtext('duration'))
                    elif e.tag in ('forward',):
                        cursor += int(e.findtext('duration'))
                    elif e.tag == 'backup':
                        cursor -= int(e.findtext('duration'))
                        out.append(Fraction(cursor, div))
        return out
    assert span(after) == span(before)
    assert infer_triplets(after) == after
