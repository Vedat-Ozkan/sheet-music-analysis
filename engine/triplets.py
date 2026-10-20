import itertools
import xml.etree.ElementTree as ET
from fractions import Fraction

_LENGTH = {'whole': 4, 'half': 2, 'quarter': 1, 'eighth': Fraction(1, 2),
           '16th': Fraction(1, 4), '32nd': Fraction(1, 8), '64th': Fraction(1, 16)}
_SHORT = {'eighth', '16th', '32nd'}


def _events(measure):
    voices = {}
    current = None
    for note in measure.findall('note'):
        if note.find('grace') is not None:
            continue
        key = (note.findtext('staff', '1'), note.findtext('voice', '1'))
        if note.find('chord') is not None:
            if current is not None and current[0] == key:
                current[1].append(note)
            else:
                return {}
        else:
            current = (key, [note])
            voices.setdefault(key, []).append(current[1])
    return voices


def _factor(note):
    tm = note.find('time-modification')
    if tm is None:
        return Fraction(1)
    try:
        return Fraction(int(tm.findtext('normal-notes')), int(tm.findtext('actual-notes')))
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _beam(event):
    return event[0].findtext('beam[@number="1"]')


def _consistent(events, divisions):
    for event in events:
        for note in event:
            length = _LENGTH.get(note.findtext('type'))
            factor = _factor(note)
            if length is None or factor is None:
                return False
            dots = len(note.findall('dot'))
            expected = length * (2 - Fraction(1, 2 ** dots)) * factor
            if Fraction(note.findtext('duration', '0')) / divisions != expected:
                return False
            if note.findtext('duration') != event[0].findtext('duration'):
                return False
    return True


def _groups(events):
    result = []
    i = 0
    while i < len(events):
        typ = events[i][0].findtext('type')
        if typ == 'quarter':
            j = i
            while j < len(events) and events[j][0].findtext('type') == typ and _beam(events[j]) is None:
                j += 1
        elif typ in _SHORT and _beam(events[i]) == 'begin':
            j = i + 1
            while j < len(events) and _beam(events[j]) == 'continue':
                j += 1
            if j >= len(events) or _beam(events[j]) != 'end':
                i += 1
                continue
            j += 1
        else:
            i += 1
            continue
        if j == i:
            i += 1
            continue
        run = events[i:j]
        if len(run) % 3 == 0 and all(e[0].findtext('type') == typ and
                                             all(n.find('dot') is None for n in e) for e in run):
            for start in range(i, j, 3):
                group = events[start:start + 3]
                if all(n.find('time-modification') is None for e in group for n in e):
                    result.append(start)
        i = j
    return result


def _aligned(events, divisions, choice):
    pos, chosen = Fraction(0), set(choice)
    for idx, ev in enumerate(events):
        d = Fraction(ev[0].findtext('duration')) / divisions
        if idx in chosen and pos % (2 * d) != 0:
            return False
        pos += d * Fraction(2, 3) if any(idx - c in (0, 1, 2) for c in chosen) else d
    return True


def _printed_types(events):
    types = set()
    for i in range(len(events) - 2):
        group = events[i:i + 3]
        typ = group[0][0].findtext('type')
        if all(e[0].findtext('type') == typ and all(_factor(n) == Fraction(2, 3) and
                   n.find('dot') is None for n in e) for e in group):
            types.add(typ)
    return types


def _rhythm(events, selected=()):
    changed = {i + k for i in selected for k in range(3)}
    return tuple((e[0].findtext('type'), len(e[0].findall('dot')),
                  e[0].find('rest') is not None, len(e),
                  Fraction(2, 3) if i in changed else _factor(e[0]))
                 for i, e in enumerate(events))


def _gaps(measure, divisions):
    gaps, started = {}, set()
    for element in measure:
        if element.tag not in ('note', 'forward') or element.find('grace') is not None:
            continue
        key = (element.findtext('staff', '1'), element.findtext('voice', '1'))
        if key in started:
            continue
        if element.tag == 'forward':
            gaps[key] = gaps.get(key, 0) + Fraction(element.findtext('duration', '0')) / divisions
        else:
            started.add(key)
    return gaps


def _backup_targets(measure):
    cursor, targets = 0, []
    for element in measure:
        if element.tag == 'note' and element.find('chord') is None and element.find('grace') is None:
            cursor += int(element.findtext('duration', '0'))
        elif element.tag == 'forward':
            cursor += int(element.findtext('duration', '0'))
        elif element.tag == 'backup':
            cursor -= int(element.findtext('duration', '0'))
            targets.append(cursor)
    return targets


def _retarget(measure, targets):
    cursor, targets = 0, iter(targets)
    for element in measure:
        if element.tag == 'note' and element.find('chord') is None and element.find('grace') is None:
            cursor += int(element.findtext('duration', '0'))
        elif element.tag == 'forward':
            cursor += int(element.findtext('duration', '0'))
        elif element.tag == 'backup':
            target = next(targets) * 3
            element.find('duration').text = str(cursor - target)
            cursor = target


def infer_triplets(score: bytes) -> bytes:
    root = ET.fromstring(score)
    changed = False
    for part in root.findall('part'):
        measures = part.findall('measure')
        voices = [_events(m) for m in measures]
        divisions, full, compound = 1, None, False
        todo = []
        for mi, measure in enumerate(measures):
            d = measure.findtext('attributes/divisions')
            if d is not None:
                divisions = int(d)
            time = measure.find('attributes/time')
            if time is not None:
                beats, unit = time.findtext('beats', ''), time.findtext('beat-type', '')
                if not beats.isdigit() or not unit.isdigit() or int(unit) == 0:
                    full = None
                else:
                    beats, unit = int(beats), int(unit)
                    full = Fraction(beats * 4, unit)
                    compound = unit >= 8 and beats >= 6 and beats % 3 == 0
            if full is None or compound or measure.get('implicit') == 'yes' or measure.get('number') == '0':
                continue
            targets = _backup_targets(measure)
            gaps = _gaps(measure, divisions)
            for key, events in voices[mi].items():
                if not _consistent(events, divisions):
                    continue
                total = sum(Fraction(e[0].findtext('duration', '0')) / divisions for e in events)
                overflow = total - full
                if overflow <= 0 and key not in gaps:
                    starts = [g for k, g in gaps.items() if k[0] == key[0] and 0 < g < total]
                    overflow = total - min(starts) if starts else overflow
                if overflow <= 0:
                    continue
                nearby = [ev for j in range(max(0, mi - 3), min(len(measures), mi + 4))
                          for k, ev in voices[j].items() if k[0] == key[0]]
                printed = set().union(*(_printed_types(ev) for ev in nearby))
                candidates = [i for i in _groups(events) if events[i][0].findtext('type') in printed]
                if not candidates or len(candidates) > 12:
                    continue
                solutions = []
                for count in range(1, len(candidates) + 1):
                    for choice in itertools.combinations(candidates, count):
                        saving = sum(Fraction(events[i][0].findtext('duration')) / divisions for i in choice)
                        if saving == overflow:
                            solutions.append(choice)
                solutions = [c for c in solutions if _aligned(events, divisions, c)]
                if not solutions:
                    continue
                choice = solutions[0]
                if any(events[i][0].findtext('type') == 'quarter' for i in choice):
                    if not any(_rhythm(events, choice) == _rhythm(ev) and 'quarter' in _printed_types(ev)
                               for ev in nearby):
                        continue
                todo.append((measure, [events[i:i + 3] for i in choice], targets))
        if not todo:
            continue
        changed = True
        for element in part.iter():
            if element.tag in ('duration', 'divisions', 'offset') and element.text:
                element.text = str(int(element.text) * 3)
        for measure, groups, _ in todo:
            for group in groups:
                for event in group:
                    for note in event:
                        duration = note.find('duration')
                        duration.text = str(int(duration.text) * 2 // 3)
                        tm = ET.Element('time-modification')
                        ET.SubElement(tm, 'actual-notes').text = '3'
                        ET.SubElement(tm, 'normal-notes').text = '2'
                        pos = next((i for i, child in enumerate(note) if child.tag in
                                    ('stem', 'notehead', 'notehead-text', 'staff', 'beam', 'notations', 'lyric')), len(note))
                        note.insert(pos, tm)
        for measure, _, targets in todo:
            _retarget(measure, targets)
    return ET.tostring(root, encoding='utf-8', xml_declaration=True) if changed else score
