"""A compact text form of a score's notes, small enough for a chat model to pass to a tool.

A host that keeps the user's file in its own sandbox (Claude) cannot send the
file to the server, but it can send this. It carries what the harmony model
reads and nothing else: no layout, slurs, dynamics or text.

    N1 div=48 ts=12/8 ks=3f
    m0 len=24
    1.1: 24 Bb4
    m1 len=288
    1.1: 72 G5 24 G5 F5 G5 72 F5 48 Eb5 24 Bb4
    2.1: 24 Eb2 G3+Eb4 Bb3+Eb4+G4 ...

Each `staff.voice:` line is one voice. A bare number sets the duration (in
`div` units per quarter note) for the notes after it. `+` joins a chord, `r` is
a rest, a leading `g` marks a grace note and a trailing `~` a tie to the next
note. A measure line repeats `ts=` when the meter changes.

This module uses only the standard library, because the model's own
environment imports it too.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction

from engine.score import Event, Measure, ScoreIndex, beat_length

VERSION = "N1"
MAX_CHARS = 200_000


class NotesError(ValueError):
    """The note list is not in the expected form."""


@dataclass
class Voice:
    staff: int
    number: int
    events: list[Event] = field(default_factory=list)


def encode(index: ScoreIndex, first: int | None = None, last: int | None = None) -> str:
    """The note list for printed measures first..last (the whole score by default).

    A range that starts at measure 1 takes the pickup along.
    """
    measures = index.measures
    if first is not None or last is not None:
        start = index.measure(first if first is not None else measures[0].number).index
        end = index.measure(last if last is not None else measures[-1].number).index
        if start == 2 and measures[0].number == 0:
            start = 1
        measures = measures[start - 1 : end]
    div = index.ppq
    lines = [f"{VERSION} div={div} ts={index.meter} ks={index.key_signature or '0'}"]
    meter = index.meter
    for measure in measures:
        header = f"m{measure.number} len={_units(measure.length, div)}"
        if measure.meter and measure.meter != meter:
            meter = measure.meter
            header += f" ts={meter}"
        lines.append(header)
        voices: dict[tuple[int, int], list[Event]] = {}
        for event in measure.events:
            if event.pitch:
                voices.setdefault((event.staff, event.layer), []).append(event)
        for (staff, layer), events in sorted(voices.items()):
            lines.append(f"{staff}.{layer}: " + _voice(events, div))
    return "\n".join(lines)


def _units(value: Fraction, div: int) -> int:
    units = value * div
    if units.denominator != 1:
        raise NotesError(f"A duration of {value} quarter notes is not a whole number of {div}ths")
    return int(units)


def _voice(events: list[Event], div: int) -> str:
    tokens: list[str] = []
    cursor, current = Fraction(0), None
    onsets: dict[tuple[Fraction, bool], list[Event]] = {}
    for event in events:
        onsets.setdefault((event.onset, event.grace), []).append(event)
    for onset, grace in sorted(onsets, key=lambda key: (key[0], not key[1])):  # grace notes come before the beat
        group = onsets[(onset, grace)]
        names = "+".join(event.pitch + ("~" if event.tied else "") for event in group)
        if grace:
            tokens.append("g" + names)
            continue
        if onset > cursor:
            gap = _units(onset - cursor, div)
            tokens += [str(gap), "r"]
            current = gap
        duration = _units(group[0].duration, div)
        if duration != current:
            tokens.append(str(duration))
            current = duration
        tokens.append(names)
        cursor = onset + group[0].duration
    return " ".join(tokens)


def decode(text: str) -> ScoreIndex:
    """Rebuild a score index (measures and notes, no engraving) from a note list."""
    if len(text) > MAX_CHARS:
        raise NotesError("The note list is too long")
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if not lines or not lines[0].startswith(VERSION + " "):
        raise NotesError(f'The note list must start with a "{VERSION} div=… ts=… ks=…" line')
    try:
        settings = dict(part.split("=", 1) for part in lines[0].split()[1:])
        div, meter, key = int(settings["div"]), settings["ts"], settings.get("ks", "0")
        measures: list[Measure] = []
        current_meter = meter
        for line in lines[1:]:
            if line.startswith("m"):
                parts = line.split()
                fields = dict(part.split("=", 1) for part in parts[1:])
                current_meter = fields.get("ts", current_meter)
                count, unit = current_meter.split("/")
                measure = Measure(
                    id=f"m{len(measures) + 1}",
                    number=int(parts[0][1:]),
                    index=len(measures) + 1,
                    beat_length=beat_length(int(count), int(unit)),
                    meter=current_meter,
                )
                measure.declared_length = Fraction(int(fields["len"]), div)
                measures.append(measure)
            else:
                voice, _, body = line.partition(":")
                staff, layer = (int(part) for part in voice.split("."))
                _read_voice(body.split(), measures[-1], staff, layer, div)
        for measure in measures:
            measure.events.sort(key=lambda event: (event.onset, event.staff))
    except (KeyError, ValueError, IndexError) as error:
        raise NotesError(f"The note list could not be read: {error}") from error
    if not measures:
        raise NotesError("The note list has no measures")
    return ScoreIndex.from_measures(measures, meter, key, div)


def _read_voice(tokens: list[str], measure: Measure, staff: int, layer: int, div: int) -> None:
    cursor, duration = Fraction(0), Fraction(0)
    for token in tokens:
        if token.isdigit():
            duration = Fraction(int(token), div)
            continue
        if token == "r":
            cursor += duration
            continue
        grace = token.startswith("g")
        for name in token[1 if grace else 0 :].split("+"):
            tied = name.endswith("~")
            pitch = name.rstrip("~")
            if pitch[0] not in "ABCDEFG" or not pitch[-1].isdigit():
                raise ValueError(f"unknown token {token!r}")
            identity = f"{measure.id}-{staff}.{layer}-{len(measure.events)}"
            measure.events.append(
                Event(identity, measure.number, staff, cursor, Fraction(0) if grace else duration, pitch, grace, layer, tied)
            )
        if not grace:
            cursor += duration
