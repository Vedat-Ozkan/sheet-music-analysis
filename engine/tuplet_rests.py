import copy
import xml.etree.ElementTree as ET
from fractions import Fraction

from engine.triplets import _beam, _consistent, _events, _factor


def _simple_serialization(measure, repaired):
    seen, current = set(), None
    headers = set()
    elements = list(measure)
    for i, element in enumerate(elements):
        if element.tag == 'backup':
            current = None
        elif element.tag in ('note', 'forward'):
            key = (element.findtext('staff', '1'), element.findtext('voice', '1'))
            if current is None:
                if key in seen:
                    return False
                seen.add(key)
                current = key
            elif key != current:
                return False
            if key[0] == repaired[0] and key != repaired and (
                    element.find('time-modification') is not None
                    or element.find('notations/tuplet') is not None):
                return False
        elif element.tag == 'direction':
            owner = current
            if owner is None:
                for following in elements[i + 1:]:
                    if following.tag == 'backup':
                        break
                    if following.tag in ('note', 'forward'):
                        owner = (following.findtext('staff', '1'), following.findtext('voice', '1'))
                        break
            if (owner is None or element.findtext('staff', '1') != owner[0]
                    or element.findtext('voice', owner[1]) != owner[1]
                    or Fraction(element.findtext('offset', '0')) != 0
                    or element.find('sound/offset') is not None):
                return False
        elif element.tag in ('attributes', 'print'):
            if seen or element.tag in headers:
                return False
            headers.add(element.tag)
        elif element.tag == 'barline':
            if element.get('location', 'right') not in ('left', 'right'):
                return False
        else:
            return False
    return True


def infer_tuplet_rests(score: bytes) -> bytes:
    root = ET.fromstring(score)
    changed = False
    for part in root.findall('part'):
        divisions, full = 1, None
        for measure in part.findall('measure'):
            divisions = int(measure.findtext('attributes/divisions', divisions))
            time = measure.find('attributes/time')
            if time is not None:
                beats, unit = time.findtext('beats', ''), time.findtext('beat-type', '')
                full = Fraction(int(beats) * 4, int(unit)) if beats.isdigit() and unit.isdigit() and int(unit) else None
            if full is None or measure.get('implicit') == 'yes':
                continue
            repairs = {}
            repaired_voices = []
            voices = _events(measure)
            for key, events in voices.items():
                if not _consistent(events, divisions):
                    continue
                if any(e.tag == 'forward' and (e.findtext('staff', '1'), e.findtext('voice', '1')) == key
                       for e in measure):
                    continue
                candidates = []
                for i, event in enumerate(events[:-5]):
                    rest = event[0]
                    group = events[i + 1:i + 6]
                    if (len(event) == 1 and rest.find('rest') is not None and _factor(rest) == 1
                            and rest.find('dot') is None
                            and [_beam(e) for e in group] == ['begin', 'continue', 'continue', 'continue', 'end']
                            and all(n.findtext('type') == rest.findtext('type') and n.find('dot') is None
                                    and n.findtext('time-modification/actual-notes') == '6'
                                    and n.findtext('time-modification/normal-notes') == '4'
                                    for e in group for n in e)):
                        candidates.append((rest, group[0][0]))
                total = sum(Fraction(e[0].findtext('duration')) / divisions for e in events)
                saving = sum(Fraction(n.findtext('duration')) / divisions / 3 for n, _ in candidates)
                if candidates and total - saving == full:
                    repairs.update(candidates)
                    repaired_voices.append(events)
            if len(repaired_voices) != 1:
                continue
            rest = next(iter(repairs))
            repaired_key = (rest.findtext('staff', '1'), rest.findtext('voice', '1'))
            if not _simple_serialization(measure, repaired_key):
                continue
            cursor, reductions, positions = Fraction(0), [], {}
            for element in measure:
                duration = Fraction(element.findtext('duration', '0'))
                positions[element] = cursor
                if element in repairs:
                    reductions.append((cursor, duration / 3))
                if element.tag == 'backup':
                    cursor -= duration
                elif element.tag == 'forward' or (element.tag == 'note' and element.find('chord') is None
                                                  and element.find('grace') is None):
                    cursor += duration
            if (positions[repaired_voices[0][0][0]] != 0
                    or any(saving.denominator != 1 for _, saving in reductions)):
                continue
            def warped(position):
                return position - sum(saving for onset, saving in reductions if onset < position)
            ordinary = {key for key, events in voices.items() if _consistent(events, divisions)
                        and all(_factor(n) == 1 for e in events for n in e)}
            aligned_staffs = set()
            for staff in {key[0] for key in ordinary}:
                keys = [key for key in voices if key[0] == staff]
                if any(key not in ordinary for key in keys):
                    continue
                intervals = sorted((warped(positions[e[0]]), Fraction(e[0].findtext('duration')))
                                   for key in keys for e in voices[key])
                end = Fraction(0)
                for start, length in intervals:
                    if start != end:
                        break
                    end += length
                else:
                    if end == full * divisions:
                        aligned_staffs.add(staff)
            cursor, repaired_cursor, durations = Fraction(0), Fraction(0), {}
            aligned = True
            for element in measure:
                duration = element.find('duration')
                length = Fraction(duration.text) if duration is not None else Fraction(0)
                if element.tag in ('backup', 'forward'):
                    target = cursor + (-length if element.tag == 'backup' else length)
                    repaired_target = target if element.tag == 'backup' else warped(target)
                    if element.tag == 'forward':
                        if element.findtext('staff', '1') not in aligned_staffs:
                            aligned &= repaired_cursor == cursor
                            repaired_target = repaired_cursor + length
                    durations[duration] = (repaired_cursor - repaired_target if element.tag == 'backup'
                                           else repaired_target - repaired_cursor)
                    cursor = target
                    repaired_cursor = repaired_target
                elif element.tag == 'note' and element.find('chord') is None and element.find('grace') is None:
                    if element.findtext('staff', '1') in aligned_staffs:
                        aligned &= repaired_cursor == warped(cursor)
                    elif (element.findtext('staff', '1'), element.findtext('voice', '1')) != repaired_key:
                        aligned &= repaired_cursor == cursor
                    if element in repairs:
                        durations[duration] = length * Fraction(2, 3)
                    cursor += length
                    repaired_cursor += durations.get(duration, length)
            if not aligned or any(d < 0 or d.denominator != 1 for d in durations.values()):
                continue
            for duration, length in durations.items():
                duration.text = str(int(length))
            for rest, printed in repairs.items():
                tm = copy.deepcopy(printed.find('time-modification'))
                pos = next((i for i, child in enumerate(rest) if child.tag in
                            ('staff', 'notations', 'lyric')), len(rest))
                rest.insert(pos, tm)
            changed = True
    return ET.tostring(root, encoding='utf-8', xml_declaration=True) if changed else score
