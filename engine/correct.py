from __future__ import annotations

import copy
import io
import math
import re
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from dataclasses import dataclass
from fractions import Fraction

from music21 import meter, note as m21note
from music21.duration import Duration

from engine import notes, tint
from engine.overlay import Box, PageLayout
from engine.render import Engraving, incoming_ties, load_toolkit, shorten_ties
from engine.score import ScoreIndex


class CorrectionError(ValueError):
    pass


def _read(score: bytes, part: str | None):
    if score[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(score)) as archive:
            container = ET.fromstring(archive.read("META-INF/container.xml"))
            name = next(e.get("full-path") for e in container.iter() if e.tag.endswith("rootfile"))
            score = archive.read(name)
    root = ET.fromstring(score)
    if root.tag != "score-partwise":
        raise CorrectionError("Corrections require unnamespaced partwise MusicXML")
    parts = root.findall("part")
    names = {sp.get("id"): sp.findtext("part-name", "").strip() for sp in root.iter("score-part")}
    choices = ", ".join(f"{p.get('id')} {names.get(p.get('id'), '')}".strip() for p in parts)
    if part is None and len(parts) != 1:
        raise CorrectionError(f"Choose a part for this score with multiple parts: {choices}")
    selected = next((p for p in parts if part is None or part.casefold() in (
        p.get("id", "").casefold(), names.get(p.get("id"), "").casefold())), None)
    if selected is None:
        raise CorrectionError(f"Part {part!r} does not exist; choose one of: {choices}")
    isolated = copy.deepcopy(root)
    for p in isolated.findall("part"):
        if p.get("id") != selected.get("id"):
            isolated.remove(p)
    index = ScoreIndex(load_toolkit(ET.tostring(isolated)).getMEI())
    bars = selected.findall("measure")
    if [s.index for m in index.measures for s in m.segments] != list(range(1, len(bars) + 1)):
        raise CorrectionError("XML measures cannot be mapped to indexed segments")
    if selected.find(".//transpose") is not None:
        raise CorrectionError("Corrections of transposed parts are not supported")
    return root, selected, index


def bars_from_musicxml(score: bytes, first: int, last: int | None = None, *, part: str | None = None) -> str:
    _, selected, index = _read(score, part)
    return _bars_from_index(selected, index, first, last)


def _bars_from_index(selected, index, first, last=None):
    staves = max([int(e.text) for e in selected.findall("measure/attributes/staves")] or [1])
    text = notes.encode(index, first, last if last is not None else first)
    div = index.ppq
    lines = []
    measure = None
    seen = set()

    def finish():
        if measure is not None:
            for staff in range(1, staves + 1):
                if staff not in seen:
                    lines.append(f"{staff}.1: {int(measure.length * div)} r")

    for line in text.splitlines():
        if line.startswith("m"):
            finish()
            measure = index.measure(int(line.split()[0][1:]))
            seen = set()
        elif ":" in line:
            staff, voice = map(int, line.split(":")[0].split("."))
            seen.add(staff)
            events = [e for e in measure.events if e.staff == staff and e.layer == voice and e.pitch]
            end = max((e.onset + e.duration for e in events), default=Fraction(0))
            if end < measure.length:
                line += f" {int((measure.length - end) * div)} r"
        lines.append(line)
    finish()
    return "\n".join(lines)


def replace_bars(score: bytes, corrected: str, *, part: str | None = None) -> bytes:
    root, selected, index = _read(score, part)
    corrected = corrected.strip()
    try:
        div = int(corrected.splitlines()[0].split("div=", 1)[1].split()[0])
    except (IndexError, ValueError) as error:
        raise CorrectionError('Start with "N1 div=24 ts=4/4 ks=0"; div must be a positive integer') from error
    try:
        if div <= 0:
            raise CorrectionError("div must be positive")
        decoded = notes.decode(corrected)
        replacements = {}
        current = None
        for line in corrected.strip().splitlines()[1:]:
            line = line.strip()
            if not line:
                continue
            if line.startswith("m"):
                current = int(line.split()[0][1:])
                if current in replacements:
                    raise CorrectionError(f"Bar {current} is repeated")
                replacements[current] = {}
            else:
                label, body = line.split(":", 1)
                staff, voice = map(int, label.split("."))
                if staff <= 0 or voice <= 0 or (staff, voice) in replacements[current]:
                    raise CorrectionError(f"Bar {current}: invalid or repeated voice {label}")
                duration, total, groups = Fraction(0), Fraction(0), []
                for token in body.split():
                    if token.isdigit():
                        duration = Fraction(int(token), div)
                        if duration <= 0:
                            raise CorrectionError(f"Bar {current}: duration must be positive")
                        continue
                    grace = token[0] if token.startswith(("g", "u")) else False
                    names = token[1:] if grace else token
                    if not grace and duration <= 0:
                        raise CorrectionError(f"Bar {current}: note/rest has no duration")
                    if names != "r" and any(not re.fullmatch(r"[A-G](?:#+|b+)?[0-9]~?", n) for n in names.split("+")):
                        raise CorrectionError(f"Bar {current}: invalid pitch {names!r}")
                    if grace and names == "r":
                        raise CorrectionError("Grace rests are not supported")
                    groups.append((names, Fraction(0) if grace else duration, grace))
                    if not grace:
                        total += duration
                replacements[current][(staff, voice)] = (total, groups)
        staves = max([int(e.text) for e in selected.findall("measure/attributes/staves")] or [1])
        unchanged = set()
        for number, voices in replacements.items():
            original = index.measure(number)
            canonical = _bars_from_index(selected, index, number)
            supplied = decoded.measure(number)
            reference = notes.decode(canonical).measure(number)
            def signature(bar):
                return [(e.staff, e.layer, e.onset, e.duration, e.pitch, e.grace, e.tied, e.attack) for e in bar.events]
            canonical_voices = {line.split(":", 1)[0] for line in canonical.splitlines() if ":" in line}
            if (signature(supplied) == signature(reference) and supplied.length == reference.length
                    and {f"{staff}.{voice}" for staff, voice in voices} == canonical_voices):
                unchanged.add(number)
                continue
            for segment in original.segments:
                timed = False
                for element in selected.findall("measure")[segment.index - 1]:
                    if timed and element.tag == "attributes" and any(child.tag != "divisions" for child in element):
                        raise CorrectionError(f"Bar {number}: mid-bar attributes cannot be corrected")
                    timed = timed or element.tag in {"note", "backup", "forward"}
            if set(s for s, _ in voices) != set(range(1, staves + 1)):
                raise CorrectionError(f"Bar {number}: include all {staves} staves")
            for label, (total, _) in voices.items():
                if total != original.length:
                    raise CorrectionError(f"Bar {number}, voice {label[0]}.{label[1]} adds up to {total}; expected {original.length} quarter notes")
            if decoded.measure(number).length != original.length:
                raise CorrectionError(f"Bar {number}: len must match the existing bar length")
    except CorrectionError:
        raise
    except ZeroDivisionError as error:
        raise CorrectionError("Use a positive meter denominator, e.g. ts=4/4") from error
    except ValueError as error:
        raise CorrectionError(str(error)) from error

    for number in unchanged:
        del replacements[number]
    if not replacements:
        return ET.tostring(root, encoding="utf-8", xml_declaration=True)

    changed_numbers = set(replacements)
    replacements = _segment_replacements(index, replacements)
    owners = {segment.index: m for m in index.measures for segment in m.segments}
    _drop_crossings(selected, set(replacements))
    pending_voices = {}
    divisions = math.lcm(div, *[int(e.text) for e in selected.findall("measure/attributes/divisions")])
    if selected.find("measure/attributes/divisions") is None:
        first = selected.find("measure")
        attributes = first.find("attributes")
        if attributes is None:
            attributes = ET.Element("attributes")
            first.insert(0, attributes)
        ET.SubElement(attributes, "divisions").text = "1"
    old = 1
    for position_in_file, bar in enumerate(selected.findall("measure"), 1):
        for element in bar:
            change = element.find("divisions") if element.tag == "attributes" else None
            if change is not None:
                old = int(change.text)
                change.text = str(divisions)
            for duration in element.findall("duration") + list(element.iter("offset")):
                value = Fraction(duration.text) * divisions / old
                if value.denominator != 1:
                    raise CorrectionError("Existing durations are not on an integer divisions grid")
                duration.text = str(int(value))
        number = position_in_file
        if number not in replacements:
            continue
        cursor = Fraction(0)
        for element in bar:
            if element.tag in {"direction", "harmony"}:
                offset = element.find("offset")
                onset = cursor + Fraction(offset.text if offset is not None else "0")
                if offset is None:
                    offset = ET.Element("offset")
                    insertion_offset = next((i for i, child in enumerate(element)
                                             if child.tag in {"voice", "staff", "sound"}), len(element))
                    element.insert(insertion_offset, offset)
                offset.text = str(onset)
            elif element.tag in {"backup", "forward"}:
                cursor += Fraction(element.findtext("duration", "0")) * (-1 if element.tag == "backup" else 1)
            elif element.tag == "note" and element.find("chord") is None and element.find("grace") is None:
                cursor += Fraction(element.findtext("duration", "0"))
        for element in list(bar):
            if element.tag in {"note", "backup", "forward"}:
                bar.remove(element)
        insertion = len(bar)
        if len(bar) and bar[-1].tag == "barline" and bar[-1].get("location", "right") == "right":
            insertion -= 1
        content = []
        for position, ((staff, voice), (length, groups)) in enumerate(sorted(replacements[number].items())):
            if position:
                backup = ET.Element("backup")
                ET.SubElement(backup, "duration").text = str(int(length * divisions))
                content.append(backup)
            pending = pending_voices.setdefault((owners[number].number, staff, voice), {})
            voice_notes = []
            expanded = []
            for names, duration, grace in groups:
                d = Duration(duration) if not grace else None
                components = d.components if d is not None and d.type == "complex" else []
                if components:
                    for i, component in enumerate(components):
                        split_names = "+".join(name if i == len(components) - 1 or name == "r"
                                               else name.rstrip("~") + "~" for name in names.split("+"))
                        expanded.append((split_names, Fraction(component.quarterLength), False))
                else:
                    expanded.append((names, duration, grace))
            for names, duration, grace in expanded:
                if not grace:
                    next_pitches = {name.rstrip("~") for name in names.split("+")} - {"r"}
                    for pitch in list(pending):
                        if pitch not in next_pitches:
                            dangling = pending.pop(pitch)
                            for parent in [dangling, dangling.find("notations")]:
                                if parent is not None:
                                    for tie in list(parent):
                                        if tie.tag in {"tie", "tied"} and tie.get("type") == "start":
                                            parent.remove(tie)
                for chord, name in enumerate(names.split("+")):
                    note = ET.Element("note")
                    if grace:
                        ET.SubElement(note, "grace", {"slash": "yes"} if grace == "u" else {})
                    if chord:
                        ET.SubElement(note, "chord")
                    pitch = name.rstrip("~")
                    if name == "r":
                        ET.SubElement(note, "rest")
                    else:
                        match = re.fullmatch(r"([A-G])([#b]*)([0-9])", pitch)
                        p = ET.SubElement(note, "pitch")
                        ET.SubElement(p, "step").text = match[1]
                        ET.SubElement(p, "alter").text = str(match[2].count("#") - match[2].count("b"))
                        ET.SubElement(p, "octave").text = match[3]
                    if not grace:
                        ET.SubElement(note, "duration").text = str(int(duration * divisions))
                    ties = (["stop"] if pitch in pending else []) + (["start"] if name.endswith("~") else [])
                    pending.pop(pitch, None)
                    if name.endswith("~"):
                        pending[pitch] = note
                    for kind in ties:
                        ET.SubElement(note, "tie", type=kind)
                    ET.SubElement(note, "voice").text = str(staff * 1000 + voice)
                    d = Duration(duration if not grace else Fraction(1, 2))
                    if d.type == "complex":
                        raise CorrectionError(f"Bar {number}: duration {duration} needs tied notes")
                    ET.SubElement(note, "type").text = d.type
                    for _ in range(d.dots):
                        ET.SubElement(note, "dot")
                    if d.tuplets:
                        t = d.tuplets[0]
                        mod = ET.SubElement(note, "time-modification")
                        ET.SubElement(mod, "actual-notes").text = str(t.numberNotesActual)
                        ET.SubElement(mod, "normal-notes").text = str(t.numberNotesNormal)
                        ET.SubElement(mod, "normal-type").text = t.durationNormal.type
                    ET.SubElement(note, "staff").text = str(staff)
                    if ties:
                        notations = ET.SubElement(note, "notations")
                        for kind in ties:
                            ET.SubElement(notations, "tied", type=kind)
                    content.append(note)
                    voice_notes.append(note)
            for note in (pending.values() if number == owners[number].last_index else []):
                for parent in [note, note.find("notations")]:
                    if parent is not None:
                        for tie in list(parent):
                            if tie.tag in {"tie", "tied"} and tie.get("type") == "start":
                                parent.remove(tie)
            run = []
            for note in voice_notes + [None]:
                mod = note.find("time-modification") if note is not None else None
                ratio = ET.tostring(mod) if mod is not None else None
                if run and (ratio != run[0][0] or len(run) == int(run[0][1].findtext("time-modification/actual-notes"))):
                    for endpoint, kind in [(run[0][1], "start"), (run[-1][1], "stop")]:
                        notations = endpoint.find("notations")
                        if notations is None:
                            notations = ET.SubElement(endpoint, "notations")
                        ET.SubElement(notations, "tuplet", type=kind, number="1")
                    run = []
                if ratio and note.find("chord") is None:
                    run.append((ratio, note))
            _beam_voice(voice_notes, owners[number], number, divisions)
        bar[insertion:insertion] = content
    result = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    _, _, after = _read(result, part)
    def timing(bar):
        return [(e.staff, e.layer, e.onset, e.duration, e.pitch, e.grace) for e in bar.events]
    for original in index.measures:
        if original.number not in changed_numbers and timing(original) != timing(after.measure(original.number)):
            raise CorrectionError("Divisions normalization would change untouched bars' imported timing")
    return result


def _beam_voice(voice_notes, measure, segment, divisions):
    signature = meter.TimeSignature(measure.meter)
    offset = next(s.start for s in measure.segments if s.index == segment)
    if measure.number == 0:
        offset += Fraction(signature.barDuration.quarterLength) - measure.length
    run, start, ratio = [], offset, None

    def finish():
        if not run:
            return
        rhythm = []
        for element in run:
            value = m21note.Rest() if element.find("rest") is not None else m21note.Note()
            value.duration = Duration(Fraction(element.findtext("duration")) / divisions)
            rhythm.append(value)
        try:
            beams = signature.getBeams(rhythm, measureStartOffset=0 if ratio else start)
        except meter.MeterException:
            return
        if ratio and len(run) > 1 and all(b is not None for b in beams):
            for i, beam in enumerate(beams):
                beam.setByNumber(1, "start" if i == 0 else "stop" if i == len(run) - 1 else "continue")
        for element, group in zip(run, beams):
            if group is None or element.find("rest") is not None:
                continue
            insertion = next((i for i, child in enumerate(element) if child.tag == "notations"), len(element))
            for beam in group:
                value = {"start": "begin", "stop": "end", "continue": "continue",
                         "partial": "forward hook" if beam.direction == "right" else "backward hook"}[beam.type]
                mark = ET.Element("beam", number=str(beam.number))
                mark.text = value
                element.insert(insertion, mark)
                insertion += 1

    for element in voice_notes:
        if element.find("chord") is not None or element.find("grace") is not None:
            continue
        mod = element.find("time-modification")
        current = ET.tostring(mod) if mod is not None else None
        if run and (current != ratio or element.find("notations/tuplet[@type=\"start\"]") is not None):
            finish()
            run = []
        if not run:
            start, ratio = offset, current
        run.append(element)
        offset += Fraction(element.findtext("duration")) / divisions
        if element.find("notations/tuplet[@type=\"stop\"]") is not None:
            finish()
            run = []
    finish()


@dataclass
class CorrectionReview:
    changed_bars: list[int]
    ranges: list[tuple[int, int]]
    engravings: list[Engraving]
    notes: dict[int, str]


def review_correction(before: bytes, after: bytes, *, part: str | None = None) -> CorrectionReview:
    _, _, old = _read(before, part)
    root, selected, new = _read(after, part)
    if [m.number for m in old.measures] != [m.number for m in new.measures]:
        raise CorrectionError("A correction review requires the same bars before and after")

    def events(bar):
        return (Counter((e.staff, e.onset, e.duration, e.pitch, e.tied)
                        for e in bar.events if not e.grace), _grace_attacks(bar))

    above = 0
    for other in root.findall("part"):
        if other is selected:
            break
        above += max((int(s.text) for s in other.iterfind("measure/attributes/staves")), default=1)
    changed, descriptions, marked = [], {}, set()
    for original, corrected in zip(old.measures, new.measures):
        if events(original) == events(corrected) and original.length == corrected.length:
            continue
        changed.append(corrected.number)
        descriptions[corrected.number] = _change_note(original, corrected)
        marked |= {(corrected.number, e.staff + above, e.onset, e.duration, e.pitch, e.tied, e.grace)
                   for e in _changed_events(original, corrected)}
    ranges = []
    for number in changed:
        if ranges and number == ranges[-1][1] + 1:
            ranges[-1] = (ranges[-1][0], number)
        else:
            ranges.append((number, number))
    return CorrectionReview(changed, ranges, [_engrave_marked(after, bounds, marked) for bounds in ranges], descriptions)


def _changed_events(old_bar, new_bar):
    key = lambda e: (e.staff, e.onset, e.duration, e.pitch, e.tied, e.grace)
    unused = Counter(key(e) for e in old_bar.events)
    added = []
    for event in new_bar.events:
        if unused[key(event)]:
            unused[key(event)] -= 1
        else:
            added.append(event)
    added = [e for e in added if e.pitch is not None] or added
    return added or new_bar.events


def _engrave_marked(after: bytes, bounds: tuple[int, int], marked: set) -> Engraving:
    toolkit = load_toolkit(after, {**tint.BOXES, "adjustPageHeight": True, "pageHeight": 60000})
    index = ScoreIndex(toolkit.getMEI())
    ties = incoming_ties(toolkit, index, bounds[0], include_pickup=False)
    toolkit.select({"measureRange": index.measure_range(*bounds, include_pickup=False)})
    toolkit.redoLayout()
    ids = {e.id for m in index.measures for e in m.events
           if (m.number, e.staff, e.onset, e.duration, e.pitch, e.tied, e.grace) in marked}
    layouts = []
    for page in range(1, toolkit.getPageCount() + 1):
        layout = PageLayout(shorten_ties(toolkit.renderToSVG(page), ties), index)
        for id in ids & layout.boxes.keys():
            box = layout.boxes[id]
            pad = 40
            tint.tint(layout, Box(box.x - pad, box.y - pad, box.width + 2 * pad, box.height + 2 * pad), tint.CHANGED)
        layouts.append(layout)
    return tint.finish(layouts, trim=True)


def _grace_attacks(bar):
    groups = {}
    for e in bar.events:
        if e.grace:
            groups.setdefault((e.staff, e.layer, e.attack), (e.onset, []))[1].append(e.pitch)
    staves = {}
    for (staff, _, _), (onset, pitches) in groups.items():
        staves.setdefault(staff, []).append((onset, tuple(sorted(pitches))))
    return staves


def _change_note(before, after):
    def attacks(bar):
        groups = {}
        for e in bar.events:
            if e.grace:
                continue
            groups.setdefault((e.staff, e.layer), {}).setdefault((e.onset, e.duration, e.grace, e.tied), []).append(e.pitch)
        return {voice: [(at, duration, grace, tied, sorted(pitches, key=lambda p: p or ""))
                        for (at, duration, grace, tied), pitches in sorted(group.items())]
                for voice, group in groups.items()}

    def pitch_name(pitches):
        if pitches == [None]:
            return "a rest"
        return " + ".join(p.replace("#", " sharp ").replace("b", " flat ") for p in pitches if p)

    old, new = attacks(before), attacks(after)
    changes = []
    old_graces, new_graces = _grace_attacks(before), _grace_attacks(after)
    for staff in sorted(old_graces.keys() | new_graces.keys()):
        a, b = old_graces.get(staff, []), new_graces.get(staff, [])
        if a != b:
            def grace_names(groups):
                return " then ".join(pitch_name(pitches) + (" together" if len(pitches) > 1 else "")
                                     for _, pitches in groups) or "none"
            if [pitches for _, pitches in a] == [pitches for _, pitches in b]:
                changes.append("grace notes start at different times")
            else:
                changes.append(f"grace notes changed from {grace_names(a)} to {grace_names(b)}")
    for staff in sorted({e.staff for e in before.events + after.events}):
        a = sorted([item for voice, items in old.items() if voice[0] == staff for item in items if item[4] != [None]])
        b = sorted([item for voice, items in new.items() if voice[0] == staff for item in items if item[4] != [None]])
        triplets = set()
        for i in range(len(b) - 2):
            group = b[i:i + 3]
            if (all(item[1] == Fraction(1, 3) and not item[2] for item in group)
                    and group[1][0] == group[0][0] + Fraction(1, 3)
                    and group[2][0] == group[0][0] + Fraction(2, 3)
                    and len(a) == len(b)
                    and all(a[j][1] == Fraction(1, 2) and a[j][4] == b[j][4] for j in range(i, i + 3))):
                changes.append("three eighth notes are now a triplet")
                triplets.update(range(i, i + 3))
        if len(a) == len(b):
            for i, (previous, current) in enumerate(zip(a, b)):
                if previous[4] != current[4]:
                    changes.append(f"{pitch_name(previous[4])} changed to {pitch_name(current[4])}")
                if i not in triplets and previous[1] != current[1]:
                    changes.append("note lengths changed")
                if i not in triplets and previous[0] != current[0]:
                    changes.append("notes start at different times")
                if previous[2] != current[2]:
                    changes.append("grace notes changed")
                if previous[3] != current[3]:
                    changes.append("ties changed")
        elif len(a) != len(b):
            changes.append(f"the number of note groups on staff {staff} changed from {len(a)} to {len(b)}")
    def rests(bar):
        spans = {}
        for e in sorted((e for e in bar.events if e.pitch is None), key=lambda e: e.onset):
            voice = spans.setdefault((e.staff, e.layer), [])
            if voice and voice[-1][1] >= e.onset:
                voice[-1][1] = max(voice[-1][1], e.onset + e.duration)
            else:
                voice.append([e.onset, e.onset + e.duration])
        return spans
    old_rests, new_rests = rests(before), rests(after)
    if any(old_rests[voice] != new_rests.get(voice) for voice in old_rests) or (
            not old_rests and new_rests):
        changes.append("rests changed")
    if before.length != after.length:
        changes.append("the bar length changed")
    text = "; ".join(dict.fromkeys(changes)) or "the notes changed"
    return f"Bar {after.number}: {text}."


def _segment_replacements(index, replacements):
    result = {}
    for number, voices in replacements.items():
        measure = index.measure(number)
        segments = measure.segments
        for i, segment in enumerate(segments):
            end = segments[i + 1].start if i + 1 < len(segments) else measure.length
            result[segment.index] = {}
            for label, (_, groups) in voices.items():
                cursor = Fraction(0)
                pieces = []
                for names, duration, grace in groups:
                    if grace:
                        if segment.start <= cursor < end or cursor == end == measure.length:
                            pieces.append((names, duration, grace))
                    else:
                        left, right = max(cursor, segment.start), min(cursor + duration, end)
                        if left < right:
                            if right < cursor + duration and names != "r":
                                split_names = "+".join(n.rstrip("~") + "~" for n in names.split("+"))
                            else:
                                split_names = names
                            pieces.append((split_names, right - left, False))
                        cursor += duration
                result[segment.index][label] = (end - segment.start, pieces)
    return result


def _drop_crossings(part: ET.Element, replaced: set[int]) -> None:
    starts = {}
    for number, bar in enumerate(part.findall("measure"), 1):
        for note in bar.findall("note"):
            for parent in [note, note.find("notations")]:
                if parent is None:
                    continue
                for mark in list(parent):
                    if mark.tag not in {"tie", "tied", "slur"}:
                        continue
                    key = (mark.tag, mark.get("number", "1"))
                    if mark.tag != "slur":
                        key += (note.findtext("staff", "1"), note.findtext("voice", "1"),
                                note.findtext("pitch/step"), note.findtext("pitch/alter", "0"),
                                note.findtext("pitch/octave"))
                    if mark.get("type") == "start":
                        starts[key] = (number, parent, mark)
                    elif mark.get("type") == "stop" and key in starts:
                        first, owner, start = starts.pop(key)
                        if first != number and any(first <= bar <= number for bar in replaced):
                            owner.remove(start)
                            parent.remove(mark)
    for key, (number, owner, start) in starts.items():
        if key[0] in {"tie", "tied"} and number + 1 in replaced:
            owner.remove(start)
