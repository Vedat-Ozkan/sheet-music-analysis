from __future__ import annotations

import itertools
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

from music21 import converter, pitch

from engine import correct

HERE = Path(__file__).parent
DATA = HERE.parent
MUSESCORE = "/mnt/c/Program Files/MuseScore 4/bin/MuseScore4.exe"
DIVISIONS = 48
GUITAR = ["E4", "B3", "G3", "D3", "A2", "E2"]
DROP_D = ["E4", "B3", "G3", "D3", "A2", "D2"]
BASS = ["G2", "D2", "A1", "E1"]
TYPES = {"w": ("whole", Fraction(4)), "h": ("half", Fraction(2)), "q": ("quarter", Fraction(1)),
         "e": ("eighth", Fraction(1, 2)), "s": ("16th", Fraction(1, 4)), "t": ("32nd", Fraction(1, 8))}
LONGEST_FRET = 19


@dataclass
class Event:
    kind: str
    dots: int = 0
    triplet: bool = False
    notes: list[tuple[int, int, bool]] = field(default_factory=list)
    names: list[str] = field(default_factory=list)

    @property
    def length(self) -> Fraction:
        base = TYPES[self.kind][1] * (2 - Fraction(1, 2 ** self.dots))
        return base * Fraction(2, 3) if self.triplet else base


@dataclass
class Bar:
    voices: list[list[Event]]
    repeat_start: bool = False
    repeat_end: bool = False


@dataclass
class Piece:
    name: str
    tuning: list[str]
    meter: str
    bars: list[Bar]
    pickup: bool = False
    words: str = ""
    capo: int = 0
    staff_too: bool = False
    keys: dict[int, int] = field(default_factory=dict)


def parse_event(token: str) -> Event:
    head, _, body = token.partition(":")
    event = Event(head[0], head.count("."), "3" in head)
    if body != "r":
        event.notes = [(int(s), int(f.rstrip("~")), f.endswith("~")) for s, f in (n.split("-") for n in body.split("+"))]
    return event


def bars(text: str) -> list[Bar]:
    result = []
    for line in filter(None, (line.strip() for line in text.strip().splitlines())):
        start, end = line.startswith("|:"), line.endswith(":|")
        line = line.removeprefix("|:").removesuffix(":|")
        result.append(Bar([[parse_event(token) for token in voice.split()] for voice in line.split("//")], start, end))
    return result


GREENSLEEVES = """
q:3-2
|: h:2-1 q:2-3
q.:1-0 e:1-1 q:1-0
h:2-3 q:2-0
q.:3-0 e:3-2 q:2-0
h:2-1 q:3-2
q.:3-2 e:3-1 q:3-2
h:2-0 q:3-1
h:4-2 q:r
h:2-1 q:2-3
q.:1-0 e:1-1 q:1-0
h:2-3 q:2-0
q.:3-0 e:3-2 q:2-0
q.:2-1 e:2-0 q:3-2
q.:3-1 e:4-4 q:3-1
h.:3-2
h:r :|
"""

ROMANZA_ARPEGGIO = {"Em": "2-0 3-0", "Am": "2-1 3-2", "B7": "2-0 3-2", "E": "2-0 3-1", "A": "2-2 3-2", "B": "2-4 3-4"}
ROMANZA = [("Em", "6-0~", "7 7 7"), ("Em", "6-0", "7 5 3"), ("Em", "6-0~", "3 2 0"), ("Em", "6-0", "0 3 7"),
           ("Am", "5-0", "12 12 12"), ("Am", "5-0", "12 10 8"), ("B7", "5-2", "8 7 5"), ("Em", "6-0", "7 8 7"),
           ("E", "6-0~", "4 4 4"), ("E", "6-0", "4 2 0"), ("B", "5-2", "2 4 7"), ("E", "6-0", "4 4 4"),
           ("A", "5-0", "5 4 2"), ("B", "5-2", "2 4 11"), ("E", "6-0~", "12 11 9"), ("E", "6-0", "0 0 0")]


def romanza() -> list[Bar]:
    result = []
    for chord, bass, melody in ROMANZA:
        upper = []
        for fret in melody.split():
            upper += [parse_event(f"e3:1-{fret}")] + [parse_event(f"e3:{note}") for note in ROMANZA_ARPEGGIO[chord].split()]
        result.append(Bar([upper, [parse_event(f"h.:{bass}")]]))
    return result


def chorale_bars(source: str, parts: list[int], tuning: list[str], *, chords: bool = False, octave: int = 0,
                 rests_after_fermatas: bool = False) -> tuple[list[Bar], bool]:
    score = converter.parse(DATA / source)
    if chords:
        score = score.chordify()
        streams = [score]
    else:
        streams = [score.parts[index] for index in parts]
    measures = [list(stream.getElementsByClass("Measure")) for stream in streams]
    open_strings = [pitch.Pitch(name).midi for name in tuning]
    result, held = [], {}
    for bar_index, columns in enumerate(zip(*measures)):
        timeline = sorted({float(element.offset) for measure in columns for element in measure.notesAndRests})
        voices = [[] for _ in columns]
        for at in timeline:
            sounding = []
            for voice, measure in enumerate(columns):
                for element in measure.notesAndRests:
                    if float(element.offset) == at:
                        sounding.append((voice, element))
            wanted = [(voice, note, note.pitch.midi + 12 * octave, note.pitch) for voice, element in sounding
                      if not element.isRest for note in (element.notes if element.isChord else [element])]
            kept = [held.get((voice, p.nameWithOctave)) for voice, _, _, p in wanted]
            taken = set(held.values()) - set(kept)
            choice = _strings([midi for *_, midi, _ in wanted], open_strings, taken, kept)
            notes_of, names_of = {}, {}
            for (voice, note, midi, p), string in zip(wanted, choice):
                tie = note.tie is not None and note.tie.type in ("start", "continue")
                notes_of.setdefault(voice, []).append((string + 1, midi - open_strings[string], tie))
                names_of.setdefault(voice, []).append(p.transpose(12 * octave).nameWithOctave)
                held.pop((voice, p.nameWithOctave), None)
                if tie:
                    held[(voice, p.nameWithOctave)] = string
            for voice, element in sounding:
                for event in _events(element, notes_of.get(voice, []), rests_after_fermatas):
                    if event.notes:
                        event.names = names_of[voice]
                    voices[voice].append(event)
        result.append(Bar(voices))
    first = measures[0][0]
    pickup = first.duration.quarterLength < first.barDuration.quarterLength
    return result, pickup


def _strings(midis: list[int], open_strings: list[int], taken: set[int], kept: list[int | None]) -> tuple[int, ...]:
    best = None
    for choice in itertools.permutations([string for string in range(len(open_strings)) if string not in taken], len(midis)):
        if any(k is not None and k != c for k, c in zip(kept, choice)):
            continue
        frets = [midi - open_strings[string] for midi, string in zip(midis, choice)]
        if any(not 0 <= fret <= LONGEST_FRET for fret in frets):
            continue
        order = sorted(range(len(midis)), key=lambda i: -midis[i])
        if [choice[i] for i in order] != sorted(choice):
            continue
        cost = sum(frets) + 3 * (max(frets) - min(frets) if frets else 0)
        if best is None or cost < best[0]:
            best = (cost, choice)
    if best is None:
        raise ValueError(f"no strings for {midis}")
    return best[1]


def _events(element, notes: list[tuple[int, int, bool]], rests_after_fermatas: bool) -> list[Event]:
    length = Fraction(element.duration.quarterLength).limit_denominator(48)
    fermata = any(type(e).__name__ == "Fermata" for e in element.expressions)
    if rests_after_fermatas and fermata and notes and length > 1:
        return [_event(Fraction(1), notes), *_rest_events(length - 1)]
    return [_event(length, notes)] if notes else _rest_events(length)


def _event(length: Fraction, notes) -> Event:
    for kind, (_, base) in TYPES.items():
        for dots in (0, 1):
            if base * (2 - Fraction(1, 2 ** dots)) == length:
                return Event(kind, dots, notes=notes)
    raise ValueError(f"no note type for {length}")


def _rest_events(length: Fraction) -> list[Event]:
    events = []
    for kind, (_, base) in TYPES.items():
        while length >= base:
            events.append(Event(kind))
            length -= base
    return events


def pieces() -> list[Piece]:
    bwv336, pickup336 = chorale_bars("part_writing_bwv336.musicxml", [0, 3], GUITAR)
    bwv386, pickup386 = chorale_bars("part_writing_bwv386.musicxml", [], GUITAR, chords=True)
    bwv245, pickup245 = chorale_bars("part_writing_bwv245.40.musicxml", [0, 3], DROP_D)
    bwv418, pickup418 = chorale_bars("part_writing_bwv418.musicxml", [3], BASS, octave=-1, rests_after_fermatas=True)
    return [
        Piece("greensleeves", GUITAR, "3/4", bars(GREENSLEEVES), pickup=True, keys={0: 0}),
        Piece("greensleeves-staff-and-tab", GUITAR, "3/4", bars(GREENSLEEVES), pickup=True, staff_too=True, keys={0: 0}),
        Piece("romanza", GUITAR, "3/4", romanza(), keys={0: 1, 8: 4}),
        Piece("bwv336-capo", GUITAR, "4/4", bwv336, pickup=pickup336, words="Capo 2", capo=2, keys={0: 3}),
        Piece("bwv386-chords", GUITAR, "4/4", bwv386, pickup=pickup386, keys={0: 4}),
        Piece("bwv245-40-drop-d", DROP_D, "4/4", bwv245, pickup=pickup245, words="Tuning: D A D G B E", keys={0: -3}),
        Piece("bwv418-bass", BASS, "4/4", bwv418, pickup=pickup418, keys={0: 0}),
    ]


def musicxml(piece: Piece) -> bytes:
    root = ET.Element("score-partwise", version="4.0")
    ET.SubElement(ET.SubElement(root, "work"), "work-title").text = piece.name
    score_part = ET.SubElement(ET.SubElement(root, "part-list"), "score-part", id="P1")
    ET.SubElement(score_part, "part-name").text = "Bass" if len(piece.tuning) == 4 else "Guitar"
    part = ET.SubElement(root, "part", id="P1")
    tab_staff = 2 if piece.staff_too else 1
    tied = set()
    fifths = 0
    open_strings = [pitch.Pitch(name) for name in piece.tuning]
    for index, bar in enumerate(piece.bars):
        measure = ET.SubElement(part, "measure", number=str(index if piece.pickup else index + 1))
        if piece.pickup and index == 0:
            measure.set("implicit", "yes")
        if bar.repeat_start:
            ET.SubElement(ET.SubElement(measure, "barline", location="left"), "repeat", direction="forward")
        if index == 0 or index in piece.keys:
            attributes = ET.SubElement(measure, "attributes")
            if index == 0:
                ET.SubElement(attributes, "divisions").text = str(DIVISIONS)
            if index in piece.keys:
                fifths = piece.keys[index]
                ET.SubElement(ET.SubElement(attributes, "key"), "fifths").text = str(fifths)
            if index == 0:
                time = ET.SubElement(attributes, "time")
                ET.SubElement(time, "beats").text, ET.SubElement(time, "beat-type").text = piece.meter.split("/")
                if piece.staff_too:
                    ET.SubElement(attributes, "staves").text = "2"
                    clef = ET.SubElement(attributes, "clef", number="1")
                    ET.SubElement(clef, "sign").text, ET.SubElement(clef, "line").text = "G", "2"
                    ET.SubElement(clef, "clef-octave-change").text = "-1"
                clef = ET.SubElement(attributes, "clef", number=str(tab_staff))
                ET.SubElement(clef, "sign").text, ET.SubElement(clef, "line").text = "TAB", "5"
                details = ET.SubElement(attributes, "staff-details", number=str(tab_staff))
                ET.SubElement(details, "staff-lines").text = str(len(piece.tuning))
                for line, name in enumerate(reversed(open_strings), 1):
                    tuning = ET.SubElement(details, "staff-tuning", line=str(line))
                    ET.SubElement(tuning, "tuning-step").text = name.step
                    if name.accidental:
                        ET.SubElement(tuning, "tuning-alter").text = str(int(name.accidental.alter))
                    ET.SubElement(tuning, "tuning-octave").text = str(name.octave)
                if piece.capo:
                    ET.SubElement(details, "capo").text = str(piece.capo)
        if index == 0 and piece.words:
            direction = ET.SubElement(measure, "direction", placement="above")
            ET.SubElement(ET.SubElement(direction, "direction-type"), "words").text = piece.words
        staves = [1, 2] if piece.staff_too else [1]
        for staff_position, staff in enumerate(staves):
            for voice_index, voice in enumerate(bar.voices):
                if staff_position or voice_index:
                    before = bar.voices[voice_index - 1] if voice_index else bar.voices[-1]
                    ET.SubElement(ET.SubElement(measure, "backup"), "duration").text = str(_units(_voice_length(before)))
                for event in voice:
                    _write_event(measure, event, voice_index + 1 + 4 * staff_position, staff if piece.staff_too else None,
                                 open_strings, staff == tab_staff, voice_index == 0 if len(bar.voices) > 1 else None,
                                 tied, fifths)
        if bar.repeat_end:
            ET.SubElement(ET.SubElement(measure, "barline", location="right"), "repeat", direction="backward")
        correct._write_accidentals(measure, fifths)
    ET.indent(root)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _spelled(midi: int, fifths: int) -> pitch.Pitch:
    order = "FCGDAEB"
    altered = {letter: 1 for letter in order[:fifths]} if fifths > 0 else {letter: -1 for letter in order[::-1][:-fifths]}
    plain = pitch.Pitch(midi=midi)
    candidates = [plain, plain.getEnharmonic(), plain.getLowerEnharmonic(), plain.getHigherEnharmonic()]
    for candidate in candidates:
        if (candidate.accidental.alter if candidate.accidental else 0) == altered.get(candidate.step, 0):
            return candidate
    wanted = 1 if fifths >= 0 else -1
    return next((candidate for candidate in candidates if candidate.accidental and candidate.accidental.alter == wanted), plain)


def _voice_length(voice: list[Event]) -> Fraction:
    return sum((event.length for event in voice), Fraction(0))


def _units(length: Fraction) -> int:
    value = length * DIVISIONS
    assert value.denominator == 1
    return int(value)


def _write_event(measure, event: Event, voice: int, staff: int | None, open_strings, tablature: bool, up: bool | None,
                 tied: set, fifths: int):
    for position, note_spec in enumerate(event.notes or [None]):
        note = ET.SubElement(measure, "note")
        if position:
            ET.SubElement(note, "chord")
        if note_spec is None:
            ET.SubElement(note, "rest")
        else:
            string, fret, _ = note_spec
            midi = open_strings[string - 1].midi + fret
            sounding = pitch.Pitch(event.names[position]) if event.names else _spelled(midi, fifths)
            assert sounding.midi == midi
            element = ET.SubElement(note, "pitch")
            ET.SubElement(element, "step").text = sounding.step
            if sounding.accidental and sounding.accidental.alter:
                ET.SubElement(element, "alter").text = str(int(sounding.accidental.alter))
            ET.SubElement(element, "octave").text = str(sounding.octave)
        ET.SubElement(note, "duration").text = str(_units(event.length))
        held = note_spec is not None and (voice, note_spec[0]) in tied
        if held:
            ET.SubElement(note, "tie", type="stop")
        if note_spec is not None and note_spec[2]:
            ET.SubElement(note, "tie", type="start")
        ET.SubElement(note, "voice").text = str(voice)
        ET.SubElement(note, "type").text = TYPES[event.kind][0]
        for _ in range(event.dots):
            ET.SubElement(note, "dot")
        if event.triplet:
            modification = ET.SubElement(note, "time-modification")
            ET.SubElement(modification, "actual-notes").text, ET.SubElement(modification, "normal-notes").text = "3", "2"
        if up is not None and note_spec is not None:
            ET.SubElement(note, "stem").text = "up" if up else "down"
        if staff:
            ET.SubElement(note, "staff").text = str(staff)
        if note_spec is not None:
            notations = ET.SubElement(note, "notations")
            if held:
                ET.SubElement(notations, "tied", type="stop")
            if note_spec[2]:
                ET.SubElement(notations, "tied", type="start")
            tied.discard((voice, note_spec[0]))
            if note_spec[2]:
                tied.add((voice, note_spec[0]))
        if note_spec is not None and tablature:
            technical = ET.SubElement(notations, "technical")
            ET.SubElement(technical, "string").text = str(note_spec[0])
            ET.SubElement(technical, "fret").text = str(note_spec[1])


def main(names: list[str]) -> None:
    for piece in pieces():
        if names and piece.name not in names:
            continue
        source = HERE / f"{piece.name}.musicxml"
        source.write_bytes(musicxml(piece))
        target = HERE / f"{piece.name}.pdf"
        subprocess.run([MUSESCORE, "-o", _windows(target), _windows(source)], check=True, timeout=120,
                       capture_output=True)
        print(piece.name, target.stat().st_size)


def _windows(path: Path) -> str:
    return subprocess.run(["wslpath", "-w", str(path)], check=True, capture_output=True, text=True).stdout.strip()


if __name__ == "__main__":
    main(sys.argv[1:])
