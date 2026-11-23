from __future__ import annotations

import copy
import io
import math
import re
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from dataclasses import dataclass, replace
from fractions import Fraction

from music21 import meter, note as m21note
from music21.duration import Duration

from engine import notes, tint
from engine.errors import UserError
from engine.overlay import Box, PageLayout
from engine.render import Engraving, incoming_ties, load_toolkit, shorten_ties
from engine.score import ScoreIndex, alteration


class CorrectionError(UserError):
    pass


ACCIDENTALS = {-3: "triple-flat", -2: "flat-flat", -1: "flat", 0: "natural", 1: "sharp", 2: "double-sharp", 3: "triple-sharp"}
AFTER_ACCIDENTAL = {"time-modification", "stem", "notehead", "staff", "beam", "notations", "lyric"}
SLUR_NUMBERS = range(1, 17)


@dataclass(frozen=True)
class Group:
    names: str
    duration: Fraction
    grace: str | bool
    slurs_opened: int = 0
    slurs_closed: int = 0
    staccato: bool = False
    accent: bool = False
    clef: str = ""
    word: str = ""

    def piece(self, names: str, duration: Fraction, first: bool, last: bool) -> Group:
        return Group(names, duration, False, self.slurs_opened if first else 0, self.slurs_closed if last else 0,
                     self.staccato and first, self.accent and first, self.clef if first else "", self.word if first else "")


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
    _drop_absent_parts(isolated.find("part-list"), selected.get("id"))
    index = ScoreIndex(load_toolkit(ET.tostring(isolated)).getMEI())
    bars = selected.findall("measure")
    if [s.index for m in index.measures for s in m.segments] != list(range(1, len(bars) + 1)):
        raise CorrectionError("XML measures cannot be mapped to indexed segments")
    if selected.find(".//transpose") is not None:
        raise CorrectionError("Corrections of transposed parts are not supported")
    return root, selected, index


def _drop_absent_parts(part_list: ET.Element | None, kept: str) -> None:
    if part_list is None:
        return
    for entry in list(part_list):
        if entry.tag == "score-part" and entry.get("id") != kept:
            part_list.remove(entry)
    open_groups: list[tuple[ET.Element, bool]] = []
    empty: list[ET.Element] = []
    for entry in list(part_list):
        if entry.tag == "score-part":
            open_groups = [(group, True) for group, _ in open_groups]
        elif entry.tag == "part-group" and entry.get("type") == "start":
            open_groups.append((entry, False))
        elif entry.tag == "part-group" and open_groups:
            group, filled = open_groups.pop()
            if not filled:
                empty += [group, entry]
    for entry in empty:
        part_list.remove(entry)


def bars_from_musicxml(score: bytes, first: int, last: int | None = None, *, part: str | None = None) -> str:
    _, selected, index = _read(score, part)
    return _bars_from_index(selected, index, first, last)


def _durations(note_list: str) -> set[Fraction]:
    lines = note_list.splitlines()
    div = int(lines[0].split("div=", 1)[1].split()[0])
    return {Fraction(int(token), div) for line in lines[1:] if ":" in line and not line.startswith("x:")
            for token in line.split(":", 1)[1].split() if token.isdigit()}


def _bars_from_index(selected, index, first, last=None):
    staves = max([int(e.text) for e in selected.findall("measure/attributes/staves")] or [1])
    text = notes.encode(index, first, last if last is not None else first)
    div = index.ppq
    lines = []
    measure = None
    seen = set()

    def finish():
        if measure is not None and measure.length:
            for staff in range(1, staves + 1):
                if staff not in seen:
                    lines.append(f"{staff}.1: {int(measure.length * div)} r")

    for line in text.splitlines():
        if line.startswith("m"):
            finish()
            measure = index.bar(notes.bar_line_name(line))
            seen = set()
        elif ":" in line:
            staff, voice = notes.voice_label(line.split(":")[0])
            seen.add(staff)
            events = [e for e in measure.events if e.staff == staff and e.layer == voice and e.pitch]
            end = max((e.onset + e.duration for e in events), default=Fraction(0))
            if end < measure.length:
                line += f" {int((measure.length - end) * div)} r"
        lines.append(line)
    finish()
    return "\n".join(lines)


def _read_voice(body: str, div: int, name: str, label: str) -> tuple[Fraction, list[Group]]:
    duration, total, groups, clef = Fraction(0), Fraction(0), [], ""
    for written in body.split():
        if written.isdigit():
            duration = Fraction(int(written), div)
            if duration <= 0:
                raise CorrectionError(f"Bar {name}: duration must be positive")
            continue
        if change := notes.CLEF.fullmatch(written):
            clef = change[1]
            continue
        token = notes.token(written)
        grace = token.sounding[0] if token.sounding.startswith(("g", "u")) else False
        names = token.sounding[1:] if grace else token.sounding
        if not grace and duration <= 0:
            raise CorrectionError(f"Bar {name}: note/rest has no duration")
        if names != "r" and any(not re.fullmatch(r"[A-G](?:#+|b+)?[0-9]~?", n) for n in names.split("+")):
            raise CorrectionError(f"Bar {name}: invalid pitch {names!r}")
        if grace and names == "r":
            raise CorrectionError("Grace rests are not supported")
        groups.append(Group(names, Fraction(0) if grace else duration, grace, token.slurs_opened, token.slurs_closed,
                            token.staccato, token.accent, clef))
        clef = ""
        if not grace:
            total += duration
    if clef:
        raise CorrectionError(f"Bar {name}, voice {label}: clef={clef} is written after the last note; write it "
                              "in the next bar, before the first note it applies to")
    return total, groups


def _handed_out_voices(canonical: str, div: int, name: str) -> dict[tuple[int, int], tuple[Fraction, list]]:
    voices = {}
    for line in canonical.splitlines():
        if ":" in line and not line.startswith("x:"):
            label, body = line.split(":", 1)
            voices[notes.voice_label(label)] = _read_voice(body, div, name, label)
    return voices


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
        held = {}
        for line in corrected.strip().splitlines()[1:]:
            line = line.strip()
            if not line or line.startswith("x:"):
                continue
            if line.startswith("m"):
                bar = index.bar(notes.bar_line_name(line))
                current, name = bar.number, bar.name
                if current in replacements:
                    raise CorrectionError(f"Bar {name} is repeated")
                replacements[current] = {}
                continue
            label, body = line.split(":", 1)
            if notes.WORDS_LABEL.fullmatch(label):
                staff, voice = notes.voice_label(label[:-1])
                if (staff, voice) not in replacements[current]:
                    raise CorrectionError(f"Bar {name}: the words line {label} needs its voice line {label[:-1]} before it")
                total, groups = replacements[current][(staff, voice)]
                replacements[current][(staff, voice)] = (total, _with_words(groups, body.split(), held.get((staff, voice, "before"), False), f"Bar {name}, {label}"))
                continue
            staff, voice = notes.voice_label(label)
            if staff <= 0 or voice <= 0 or (staff, voice) in replacements[current]:
                raise CorrectionError(f"Bar {name}: invalid or repeated voice {label}")
            total, groups = _read_voice(body, div, name, label)
            held[staff, voice, "before"] = held.get((staff, voice), False)
            held[staff, voice] = _held_after(groups, held[staff, voice, "before"])
            replacements[current][(staff, voice)] = (total, groups)
        staves = max([int(e.text) for e in selected.findall("measure/attributes/staves")] or [1])
        unchanged = set()
        for number, voices in replacements.items():
            original = index.measure(number)
            name = original.name
            canonical = _bars_from_index(selected, index, number)
            supplied = decoded.bar(name)
            reference = notes.decode(canonical).bar(name)
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
                        raise CorrectionError(f"Bar {name}: mid-bar attributes cannot be corrected")
                    timed = timed or element.tag in {"note", "backup", "forward"}
            if set(s for s, _ in voices) != set(range(1, staves + 1)):
                raise CorrectionError(f"Bar {name}: include all {staves} staves")
            as_read = _durations(canonical)
            handed_out = _handed_out_voices(canonical, index.ppq, name)
            for label, (total, groups) in voices.items():
                handed = handed_out.get(label)
                if handed == (total, groups):
                    continue
                if total != original.length and not (handed and total == handed[0]):
                    raise CorrectionError(f"Bar {name}, voice {label[0]}.{label[1]} adds up to {total}; expected {original.length} quarter notes")
                for group in groups:
                    duration, grace = group.duration, group.grace
                    written = Duration(duration)
                    if not grace and duration not in as_read and (written.type == "inexpressible"
                                      or any(t.durationNormal.type != written.type for t in written.tuplets)):
                        raise CorrectionError(
                            f"Bar {name}: a duration of {duration * div} at div={div} cannot be written as one note; use plain "
                            "or dotted note values, notes of a simple tuplet such as a triplet, or tied notes")
            if supplied.length != original.length:
                raise CorrectionError(f"Bar {name}: len must match the existing bar length")
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
    written_voices = {(e.staff, e.layer) for m in index.measures for e in m.events}
    open_slurs, slur_numbers_taken = {}, set()
    clefs, fifths, keys, lyrics = {}, 0, {}, []
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
            if element.tag == "attributes":
                fifths = int(element.findtext("key/fifths", str(fifths)))
                for clef in element.findall("clef"):
                    clefs[int(clef.get("number", "1"))] = (clef.findtext("sign"), int(clef.findtext("line", "0")),
                                                          int(clef.findtext("clef-octave-change", "0")))
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
        keys[number] = fifths
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
        previous_length = None
        for (staff, voice), (length, groups) in sorted(replacements[number].items()):
            if previous_length is not None:
                backup = ET.Element("backup")
                ET.SubElement(backup, "duration").text = str(int(previous_length * divisions))
                content.append(backup)
            previous_length = length
            pending = pending_voices.setdefault((owners[number].number, staff, voice), {})
            voice_notes = []
            expanded = []
            for group in groups:
                d = Duration(group.duration) if not group.grace else None
                components = d.components if d is not None and d.type == "complex" else []
                if components:
                    for i, component in enumerate(components):
                        split_names = "+".join(name if i == len(components) - 1 or name == "r"
                                               else name.rstrip("~") + "~" for name in group.names.split("+"))
                        expanded.append(group.piece(split_names, Fraction(component.quarterLength), i == 0, i == len(components) - 1))
                else:
                    expanded.append(group)
            for group in expanded:
                names, duration, grace = group.names, group.duration, group.grace
                if group.clef and clefs.get(staff) != notes.CLEFS[group.clef]:
                    clefs[staff] = notes.CLEFS[group.clef]
                    content.append(_clef_change(staff, *clefs[staff]))
                if not grace:
                    next_pitches = {name.rstrip("~") for name in names.split("+")} - {"r"}
                    for pitch in list(pending):
                        if pitch not in next_pitches:
                            _remove_tie(pending.pop(pitch), "start")
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
                        ET.SubElement(p, "alter").text = str(alteration(match[2]))
                        ET.SubElement(p, "octave").text = match[3]
                    if not grace:
                        ET.SubElement(note, "duration").text = str(int(duration * divisions))
                    ties = (["stop"] if pitch in pending else []) + (["start"] if name.endswith("~") else [])
                    pending.pop(pitch, None)
                    if name.endswith("~"):
                        pending[pitch] = note
                    for kind in ties:
                        ET.SubElement(note, "tie", type=kind)
                    ET.SubElement(note, "voice").text = str(voice if (staff, voice) in written_voices else staff * 1000 + voice)
                    d = Duration(duration if not grace else Fraction(1, 2))
                    if d.type == "complex":
                        raise CorrectionError(f"Bar {owners[number].name}: duration {duration} needs tied notes")
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
                    marked = not chord and (group.slurs_opened or group.slurs_closed or group.staccato or group.accent)
                    if ties or marked:
                        notations = ET.SubElement(note, "notations")
                        for kind in ties:
                            ET.SubElement(notations, "tied", type=kind)
                        if marked:
                            _write_marks(notations, group, open_slurs.setdefault((staff, voice), []), slur_numbers_taken,
                                         f"Bar {owners[number].number}, voice {staff}.{voice}")
                    if group.word and not chord:
                        lyrics.append(((staff, voice), note, group.word))
                    content.append(note)
                    voice_notes.append(note)
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
    _join_ties(selected, set(replacements))
    for (staff, voice), numbers in open_slurs.items():
        if numbers:
            raise CorrectionError(f"A slur starts in voice {staff}.{voice} and never ends; close it with ) after its last note")
    bars = selected.findall("measure")
    for number, key in keys.items():
        _write_accidentals(bars[number - 1], key)
    _write_lyrics(lyrics)
    result = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    _, _, after = _read(result, part)
    def timing(bar):
        return [(e.staff, e.layer, e.onset, e.duration, e.pitch, e.grace) for e in bar.events]
    def ties(bar):
        return [e.tied for e in bar.events]
    for original, following in zip(index.measures, index.measures[1:] + [None]):
        if original.number in changed_numbers:
            continue
        if timing(original) != timing(after.measure(original.number)):
            raise CorrectionError("Divisions normalization would change untouched bars' imported timing")
        if (following is None or following.number not in changed_numbers) and ties(original) != ties(after.measure(original.number)):
            raise CorrectionError(f"Bar {original.name}: the correction would change ties in this untouched bar")
    return result


def _held_after(groups: list[Group], held: bool) -> bool:
    for group in groups:
        if not group.grace:
            held = group.names != "r" and "~" in group.names
    return held


def sung_notes(body: str, div: int, tied_into: bool) -> int:
    return len(_sung_positions(_read_voice(body, div, "", "")[1], tied_into))


def ends_tied(body: str, div: int, tied_into: bool) -> bool:
    return _held_after(_read_voice(body, div, "", "")[1], tied_into)


def _sung_positions(groups: list[Group], held: bool) -> list[int]:
    sung = []
    for position, group in enumerate(groups):
        if group.grace or group.names == "r":
            held = held and bool(group.grace)
            continue
        if not held:
            sung.append(position)
        held = "~" in group.names
    return sung


def _with_words(groups: list[Group], words: list[str], held: bool, where: str) -> list[Group]:
    sung = _sung_positions(groups, held)
    if len(words) != len(sung):
        raise CorrectionError(f"{where}: {len(words)} entries for {len(sung)} sung notes; write one entry for each note "
                              "that is not a rest, a grace note or the continuation of a tie, and _ where no syllable is printed")
    result = list(groups)
    for position, word in zip(sung, words):
        if word != "_":
            result[position] = replace(groups[position], word=word)
    return result


def _clef_change(staff: int, sign: str, line: int, octave: int) -> ET.Element:
    attributes = ET.Element("attributes")
    clef = ET.SubElement(attributes, "clef", number=str(staff))
    ET.SubElement(clef, "sign").text = sign
    ET.SubElement(clef, "line").text = str(line)
    if octave:
        ET.SubElement(clef, "clef-octave-change").text = str(octave)
    return attributes


def _write_marks(notations: ET.Element, group: Group, open_numbers: list[int], taken: set[int], where: str) -> None:
    for _ in range(group.slurs_opened):
        number = next((n for n in SLUR_NUMBERS if n not in taken), None)
        if number is None:
            raise CorrectionError(f"{where}: more than {len(SLUR_NUMBERS)} slurs are open at once")
        taken.add(number)
        open_numbers.append(number)
        ET.SubElement(notations, "slur", type="start", number=str(number))
    if group.staccato or group.accent:
        articulations = ET.SubElement(notations, "articulations")
        for wanted, tag in ((group.accent, "accent"), (group.staccato, "staccato")):
            if wanted:
                ET.SubElement(articulations, tag)
    for _ in range(group.slurs_closed):
        if not open_numbers:
            raise CorrectionError(f"{where}: a slur ends here that was never started; write ( before its first note")
        number = open_numbers.pop()
        taken.discard(number)
        ET.SubElement(notations, "slur", type="stop", number=str(number))


def _write_accidentals(bar: ET.Element, fifths: int) -> None:
    in_key = {step: 1 for step in "FCGDAEB"[:max(fifths, 0)]} | {step: -1 for step in "BEADGCF"[:max(-fifths, 0)]}
    cursor = onset = Fraction(0)
    sounding = []
    for element in bar:
        if element.tag in {"backup", "forward"}:
            cursor += Fraction(element.findtext("duration", "0")) * (-1 if element.tag == "backup" else 1)
        elif element.tag == "note":
            if element.find("chord") is None:
                onset = cursor
                if element.find("grace") is None:
                    cursor += Fraction(element.findtext("duration", "0"))
            if element.find("pitch") is not None:
                sounding.append((onset, len(sounding), element))
    altered = {}
    for _, _, note in sorted(sounding, key=lambda entry: entry[:2]):
        if any(tie.get("type") == "stop" for tie in note.findall("tie")):
            continue
        place = (note.findtext("staff", "1"), note.findtext("pitch/step"), note.findtext("pitch/octave"))
        alter = int(float(note.findtext("pitch/alter", "0")))
        if alter != altered.get(place, in_key.get(place[1], 0)) and alter in ACCIDENTALS:
            sign = ET.Element("accidental")
            sign.text = ACCIDENTALS[alter]
            note.insert(next((i for i, child in enumerate(note) if child.tag in AFTER_ACCIDENTAL), len(note)), sign)
        altered[place] = alter


def _write_lyrics(lyrics: list[tuple[tuple[int, int], ET.Element, str]]) -> None:
    inside_word = {}
    for voice, note, word in lyrics:
        goes_on = word.endswith("-") and len(word) > 1
        lyric = ET.SubElement(note, "lyric", number="1")
        ET.SubElement(lyric, "syllabic").text = {(False, False): "single", (False, True): "begin", (True, True): "middle", (True, False): "end"}[inside_word.get(voice, False), goes_on]
        ET.SubElement(lyric, "text").text = word[:-1] if goes_on else word
        inside_word[voice] = goes_on


def _beam_voice(voice_notes, measure, segment, divisions):
    length = measure.length
    signature = meter.TimeSignature(measure.meter or f"{length.numerator}/{4 * length.denominator}")
    offset = next(s.start for s in measure.segments if s.index == segment)
    offset += measure.pickup_padding
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
    changed_bars: list[int | str]
    ranges: list[tuple[int, int]]
    engravings: list[Engraving]
    notes: dict[int | str, str]


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
    changed, printed, descriptions, marked = [], [], {}, set()
    for original, corrected in zip(old.measures, new.measures):
        if events(original) == events(corrected) and original.length == corrected.length:
            continue
        changed.append(corrected.number)
        printed.append(corrected.printed)
        descriptions[corrected.printed] = _change_note(original, corrected)
        marked |= {(corrected.number, e.staff + above, e.onset, e.duration, e.pitch, e.tied, e.grace)
                   for e in _changed_events(original, corrected)}
    ranges = []
    for number in changed:
        if ranges and number == ranges[-1][1] + 1:
            ranges[-1] = (ranges[-1][0], number)
        else:
            ranges.append((number, number))
    return CorrectionReview(printed, ranges, [_engrave_marked(after, bounds, marked) for bounds in ranges], descriptions)


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
    return f"Bar {after.name}: {text}."


def _segment_replacements(index, replacements):
    result = {}
    for number, voices in replacements.items():
        measure = index.measure(number)
        segments = measure.segments
        for i, segment in enumerate(segments):
            result[segment.index] = {}
            for label, (total, groups) in voices.items():
                end = segments[i + 1].start if i + 1 < len(segments) else max(measure.length, total)
                cursor = Fraction(0)
                pieces = []
                for group in groups:
                    names, duration = group.names, group.duration
                    if group.grace:
                        if segment.start <= cursor < end or cursor == end == measure.length:
                            pieces.append(group)
                    else:
                        left, right = max(cursor, segment.start), min(cursor + duration, end)
                        if left < right:
                            if right < cursor + duration and names != "r":
                                split_names = "+".join(n.rstrip("~") + "~" for n in names.split("+"))
                            else:
                                split_names = names
                            pieces.append(group.piece(split_names, right - left, left == cursor, right == cursor + duration))
                        cursor += duration
                result[segment.index][label] = (end - segment.start, pieces)
    return result


def _drop_crossings(part: ET.Element, replaced: set[int]) -> None:
    starts = {}
    for number, bar in enumerate(part.findall("measure"), 1):
        for note in bar.findall("note"):
            notations = note.find("notations")
            for mark in list(notations) if notations is not None else []:
                if mark.tag != "slur":
                    continue
                key = mark.get("number", "1")
                if mark.get("type") == "start":
                    starts[key] = (number, notations, mark)
                elif mark.get("type") == "stop" and key in starts:
                    first, owner, start = starts.pop(key)
                    if first != number and any(first <= bar <= number for bar in replaced):
                        owner.remove(start)
                        notations.remove(mark)


def _join_ties(part: ET.Element, replaced: set[int]) -> None:
    bars = part.findall("measure")
    for number in sorted({n for r in replaced for n in (r - 1, r)} - {0}):
        starts, _ = _loose_ties(bars[number - 1])
        _, stops = _loose_ties(bars[number]) if number < len(bars) else ({}, {})
        rewritten = number + 1 in replaced
        opening = _opening_notes(bars[number]) if rewritten else {}
        for key, loose in starts.items():
            landing = stops.pop(key, [])
            for note in landing[len(loose):]:
                _remove_tie(note, "stop")
            waiting = loose[len(landing):]
            if waiting and key in opening:
                target = opening[key]
                target.insert(list(target).index(target.find("duration")) + 1, ET.Element("tie", type="stop"))
                notations = target.find("notations")
                if notations is None:
                    notations = ET.SubElement(target, "notations")
                ET.SubElement(notations, "tied", type="stop")
                waiting = waiting[1:]
            for note in waiting:
                _remove_tie(note, "start")
        for stopping in stops.values():
            for note in stopping:
                _remove_tie(note, "stop")


def _tie_key(note: ET.Element):
    return (note.findtext("staff", "1"), note.findtext("pitch/step"),
            float(note.findtext("pitch/alter", "0")), note.findtext("pitch/octave"))


def _loose_ties(bar: ET.Element):
    starts, stops = {}, {}
    for note in bar.findall("note"):
        kinds = {mark.get("type") for mark in note.findall("tie") + note.findall("notations/tied")}
        key = _tie_key(note)
        if "stop" in kinds:
            if starts.get(key):
                starts[key].pop()
            else:
                stops.setdefault(key, []).append(note)
        if "start" in kinds:
            starts.setdefault(key, []).append(note)
    return starts, stops


def _opening_notes(bar: ET.Element):
    cursor = onset = Fraction(0)
    found = {}
    for element in bar:
        if element.tag in {"backup", "forward"}:
            cursor += Fraction(element.findtext("duration", "0")) * (-1 if element.tag == "backup" else 1)
        elif element.tag == "note" and element.find("grace") is None:
            if element.find("chord") is None:
                onset = cursor
                cursor += Fraction(element.findtext("duration", "0"))
            if onset == 0 and element.find("pitch") is not None:
                found.setdefault(_tie_key(element), element)
    return found


def _remove_tie(note: ET.Element, kind: str) -> None:
    for parent in [note, note.find("notations")]:
        if parent is not None:
            for mark in list(parent):
                if mark.tag in {"tie", "tied"} and mark.get("type") == kind:
                    parent.remove(mark)
