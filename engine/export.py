from __future__ import annotations

import base64
import io
import xml.etree.ElementTree as ET
import zipfile
from fractions import Fraction

from engine.reduce import STEPS
from engine.render import load_toolkit
from engine.score import ScoreIndex, TOLERANCE

_SUPERSCRIPTS = str.maketrans('⁰¹²³⁴⁵⁶⁷⁸⁹', '0123456789')


def _document(data: bytes) -> bytes:
    if not zipfile.is_zipfile(io.BytesIO(data)):
        return data
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        container = ET.fromstring(archive.read('META-INF/container.xml'))
        files = [node for node in container.iter() if node.tag.rsplit('}', 1)[-1] == 'rootfile']
        rootfile = next((node for node in files if node.get('media-type') in (None, 'application/vnd.recordare.musicxml+xml')), None)
        if rootfile is None:
            raise ValueError('MXL container has no MusicXML rootfile')
        return archive.read(rootfile.attrib['full-path'])


def export_musicxml(original: bytes, analysis: dict) -> bytes:
    document = _document(original)
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True, insert_pis=True))
    try:
        root = ET.fromstring(document, parser=parser)
    except ET.ParseError:
        parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True, insert_pis=True))
        root = ET.fromstring(document.decode('latin-1'), parser=parser)
    namespace = root.tag.partition('}')[0] + '}' if root.tag.startswith('{') else ''
    def tag(name):
        return namespace + name
    if root.tag != tag('score-partwise'):
        raise ValueError('Expected score-partwise MusicXML')
    parts = root.findall(tag('part'))
    if not parts:
        raise ValueError('MusicXML has no parts')
    harmonies = sorted((a for a in analysis['annotations'] if a['type'] == 'harmony'),
                       key=lambda a: (a['at']['measure'], a['at'].get('beat', 1)))
    if not harmonies:
        return _document(original)
    index = ScoreIndex(load_toolkit(original).getMEI())
    bass = parts[-1]
    measures = bass.findall(tag('measure'))
    segments = {s.index: (m, s) for m in index.measures for s in m.segments}
    if len(measures) != len(segments):
        raise ValueError('Bottom part measure count differs from the score index')

    existing = list(root.iter(tag('lyric')))
    used_numbers = {lyric.get('number', '1') for lyric in existing}
    used_names = {lyric.get('name') for lyric in existing}
    number = max((int(n) for n in used_numbers if n.isdigit()), default=0) + 1
    name = 'roman-analysis'
    suffix = 2
    while name in used_names:
        name = f'roman-analysis-{suffix}'
        suffix += 1

    candidates = {}
    divisions, staves = 1, 1
    transposition, octave = {}, {}
    measure_info = {}
    for position, measure in enumerate(measures, 1):
        bar, segment = segments[position]
        cursor = previous = Fraction(0)
        notes, shifts = [], []
        insertion_divisions = divisions
        insertion_seen = False
        for element in measure:
            kind = element.tag
            if not insertion_seen:
                if kind in (tag("note"), tag("backup"), tag("forward")):
                    insertion_seen = True
                else:
                    insertion_divisions = int(element.findtext(tag("divisions"), str(insertion_divisions)))
            if kind == tag('attributes'):
                divisions = int(element.findtext(tag('divisions'), str(divisions)))
                staves = int(element.findtext(tag('staves'), str(staves)))
                for transpose in element.findall(tag('transpose')):
                    shift = Fraction(transpose.findtext(tag('chromatic'), '0')) + 12 * int(transpose.findtext(tag('octave-change'), '0'))
                    targets = [int(transpose.get('number'))] if transpose.get('number') else range(1, staves + 1)
                    for staff in targets:
                        transposition[staff] = shift
            elif kind in (tag('backup'), tag('forward')):
                duration = Fraction(element.findtext(tag('duration'), '0')) / divisions
                cursor += -duration if kind == tag('backup') else duration
            elif kind == tag('direction'):
                onset = cursor + Fraction(element.findtext(tag('offset'), '0')) / divisions
                staff = int(element.findtext(tag('staff'), '1'))
                for shift in element.findall(tag('direction-type') + '/' + tag('octave-shift')):
                    shifts.append((onset, staff, shift.get('type'), int(shift.get('size', '8'))))
            elif kind == tag('note'):
                chord = element.find(tag('chord')) is not None
                onset = previous if chord else cursor
                pitch = element.find(tag('pitch'))
                if pitch is not None and element.find(tag('grace')) is None:
                    staff = int(element.findtext(tag('staff'), '1'))
                    sounding = (STEPS[pitch.findtext(tag('step'))] + Fraction(pitch.findtext(tag('alter'), '0'))
                                + 12 * (int(pitch.findtext(tag('octave'))) + 1) + transposition.get(staff, 0))
                    notes.append((onset, sounding, staff, element))
                if not chord:
                    previous = cursor
                    if element.find(tag('grace')) is None:
                        cursor += Fraction(element.findtext(tag('duration'), '0')) / divisions
        shifts.sort(key=lambda item: item[0])
        for onset, sounding, staff, note in notes:
            if staff != staves:
                continue
            active = octave.copy()
            for at, target, kind, size in shifts:
                if at > onset:
                    break
                active[target] = 0 if kind == 'stop' else (12 * ((size - 1) // 7) * (1 if kind == 'down' else -1))
            candidates.setdefault(bar.number, []).append((segment.start + onset, sounding + active.get(staff, 0), note))
        for _, staff, kind, size in shifts:
            octave[staff] = 0 if kind == 'stop' else 12 * ((size - 1) // 7) * (1 if kind == 'down' else -1)
        measure_info[position] = (measure, insertion_divisions, staves)

    attached, key = {}, None
    for annotation in harmonies:
        at = annotation['at']
        bar = index.measure(at['measure'])
        offset = bar.offset_of(at.get('beat', 1))
        text = annotation['label'].translate(_SUPERSCRIPTS)
        new_key = annotation.get('key')
        if new_key and new_key != key:
            text = f'{new_key}: {text}'
            key = new_key
        choices = [item for item in candidates.get(bar.number, []) if abs(item[0] - offset) <= TOLERANCE]
        if choices:
            _, _, note = min(choices, key=lambda item: (item[0], item[1]))
            lyric = attached.get(note)
            if lyric is None:
                lyric = ET.Element(tag('lyric'), number=str(number), name=name, placement='below')
                ET.SubElement(lyric, tag('syllabic')).text = 'single'
                insertion = next((i for i, child in enumerate(note) if child.tag in (tag('play'), tag('listen'))), len(note))
                note.insert(insertion, lyric)
                attached[note] = lyric
            else:
                ET.SubElement(lyric, tag('elision')).text = ' '
            ET.SubElement(lyric, tag('text')).text = text
        else:
            segment = bar.segment_at(offset)
            measure, divisions, staves = measure_info[segment.index]
            direction = ET.Element(tag('direction'), placement='below')
            ET.SubElement(ET.SubElement(direction, tag('direction-type')), tag('words')).text = text
            duration = (offset - segment.start) * divisions
            if duration.denominator != 1:
                value = format(float(duration), '.12g')
            else:
                value = str(duration.numerator)
            ET.SubElement(direction, tag('offset')).text = value
            ET.SubElement(direction, tag('staff')).text = str(staves)
            insertion = next((i for i, child in enumerate(measure) if child.tag in (tag('note'), tag('backup'), tag('forward'))), len(measure))
            measure.insert(insertion, direction)
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


def _in_range(measure: int, measures: tuple[int, int] | None) -> bool:
    return measures is None or measures[0] <= measure <= measures[1] or (measure == 0 and measures[0] == 1)


def export_romantext(original: bytes, analysis: dict, measures: tuple[int, int] | None = None) -> bytes | None:
    harmonies = sorted((a for a in analysis['annotations'] if a['type'] == 'harmony'),
                       key=lambda a: (a['at']['measure'], a['at'].get('beat', 1)))
    if not harmonies:
        return None
    index = ScoreIndex(load_toolkit(original).getMEI())
    lines, key, meter, bar = [], None, None, None
    shown = None
    for annotation in harmonies:
        new_key = annotation.get('key')
        if new_key:
            key = new_key
        number = annotation['at']['measure']
        if not _in_range(number, measures):
            continue
        if key is None:
            return None
        beat = annotation['at'].get('beat', 1)
        measure = index.measure(number)
        if number == 0:
            full = index.measure(1).length
            beat += float((full - measure.length) / measure.beat_length)
        if number != bar:
            bar = number
            current = index.measure(number).meter
            if current != meter:
                meter = current
                lines.append(f'Time Signature: {meter}')
            lines.append(f'm{number}')
        text = annotation['label'].translate(_SUPERSCRIPTS).split()[0]
        if key != shown:
            shown = key
            text = f'{key}: {text}'
        lines[-1] += (f' b{beat:g}' if beat != 1 or len(lines[-1].split()) > 1 else '') + f' {text}'
    return ('\n'.join(lines) + '\n').encode()


def export_midi(original: bytes, measures: tuple[int, int] | None = None) -> bytes:
    toolkit = load_toolkit(original)
    if measures:
        toolkit.select({'measureRange': ScoreIndex(toolkit.getMEI()).measure_range(*measures)})
    return base64.b64decode(toolkit.renderToMIDI())
