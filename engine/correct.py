"""Replace complete bars of a PDF reading using the N1 notes format.

Only note/rest/forward/backup content is replaced; bar metadata is retained.
Bars with unchanged N1 content retain their original notation.
Divisions and duration integers in the selected part may be rescaled together
(the same music in finer units), because Verovio cannot index changing divisions
reliably. Other parts are retained. Crossing ties/slurs lose both endpoints;
internal ties from N1 are rebuilt, and slurs inside changed bars are lost.
N1 and MusicXML pitches are sounding pitches: octave-shift directions change
engraving, not the pitch written to XML. Their original onsets are retained,
even when a shift starts/stops within a corrected bar (also within a note).
Split bars use ScoreIndex/N1 addresses and retain each XML segment's length.
Corrections are rejected if divisions rescaling changes untouched imported timing.
"""

from __future__ import annotations

import copy
import io
import math
import re
import xml.etree.ElementTree as ET
import zipfile
from fractions import Fraction

from music21.duration import Duration

from engine import notes
from engine.render import load_toolkit
from engine.score import ScoreIndex


class CorrectionError(ValueError):
    """A correction cannot safely replace the requested bars."""


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
    if part is None and len(parts) != 1:
        raise CorrectionError("Choose a part id for a score with multiple parts")
    selected = next((p for p in parts if part is None or p.get("id") == part), None)
    if selected is None:
        raise CorrectionError(f"Part {part!r} does not exist")
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
    """N1 for a range in one part, including explicit trailing rests.

    Like encode, a range starting at 1 includes the pickup. Staff numbers are
    local to the selected part. Silent staves are included as full-bar rests.
    """
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
    """Replace all voices/staves of listed bars; return plain MusicXML bytes.

    Every supplied voice must explicitly fill the meter, or the original bar's
    length for a pickup/incomplete bar. Header key/meter never change the score.
    A correction must include every staff, but may change its voice count.
    """
    root, selected, index = _read(score, part)
    try:
        div = int(corrected.splitlines()[0].split("div=", 1)[1].split()[0])
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
                    grace = token.startswith("g")
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
            # Keep notation absent from N1, including complex durations and ties
            # across bar boundaries, when the supplied text is unchanged.
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
    except ValueError as error:
        raise CorrectionError(str(error)) from error

    for number in unchanged:
        del replacements[number]
    if not replacements:
        return ET.tostring(root, encoding="utf-8", xml_declaration=True)

    changed_numbers = set(replacements)
    # Partition logical voices at the original repeat/fermata boundaries. A note
    # crossing a boundary becomes tied pieces, with pending ties shared below.
    replacements = _segment_replacements(index, replacements)
    owners = {segment.index: m for m in index.measures for segment in m.segments}
    _drop_crossings(selected, set(replacements))
    pending_voices = {}
    # A uniform integer grid avoids Verovio's changing-divisions import bug.
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
        # Retained directions/harmonies will sit at the bar's initial cursor.
        # Translate their relative offsets before removing the original timeline.
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
        # Initial attributes and left barlines must remain before the notes.
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
            # Complex lengths need several printable values; pitched pieces
            # join with ties, while rests simply occupy consecutive spans.
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
                    # A tie can only stop on the next attack; rests break it too.
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
                        ET.SubElement(note, "grace")
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
                    # MusicXML voice ids must be distinct across staves.
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
            # N1 cannot identify a tie's outside endpoint. Drop terminal starts.
            for note in (pending.values() if number == owners[number].last_index else []):
                for parent in [note, note.find("notations")]:
                    if parent is not None:
                        for tie in list(parent):
                            if tie.tag in {"tie", "tied"} and tie.get("type") == "start":
                                parent.remove(tie)
            # Group adjacent equal tuplets so the correction prints its bracket/3.
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
        bar[insertion:insertion] = content
    result = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    _, _, after = _read(result, part)
    def timing(bar):
        return [(e.staff, e.layer, e.onset, e.duration, e.pitch, e.grace) for e in bar.events]
    for original in index.measures:
        if original.number not in changed_numbers and timing(original) != timing(after.measure(original.number)):
            raise CorrectionError("Divisions normalization would change untouched bars' imported timing")
    return result


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
                        # Grace attacks on a boundary belong to the following segment.
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
    # An already dangling incoming tie has no stop to pair with. Do not let
    # Verovio search through the correction for a more distant matching pitch.
    for key, (number, owner, start) in starts.items():
        if key[0] in {"tie", "tied"} and number + 1 in replaced:
            owner.remove(start)
