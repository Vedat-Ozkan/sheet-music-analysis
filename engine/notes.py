from __future__ import annotations

import re
from dataclasses import dataclass, field
from fractions import Fraction

from engine.score import Event, Measure, ScoreIndex, beat_length

VERSION = "N1"
MAX_CHARS = 200_000


class NotesError(ValueError):
    pass


@dataclass
class Voice:
    staff: int
    number: int
    events: list[Event] = field(default_factory=list)


def encode(index: ScoreIndex, first: int | None = None, last: int | None = None) -> str:
    measures = index.measures
    if first is not None or last is not None:
        start = measures.index(index.measure(first if first is not None else measures[0].number))
        end = measures.index(index.measure(last if last is not None else measures[-1].number))
        if start == 1 and measures[0].number == 0:
            start = 0
        measures = measures[start : end + 1]
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
    onsets: dict[tuple[Fraction, bool, str], list[Event]] = {}
    for event in events:
        onsets.setdefault((event.onset, event.grace, event.attack if event.grace else ""), []).append(event)
    for onset, grace, attack in sorted(onsets, key=lambda key: (key[0], not key[1])):
        group = onsets[(onset, grace, attack)]
        names = "+".join(event.pitch + ("~" if event.tied else "") for event in group)
        if onset > cursor:
            gap = _units(onset - cursor, div)
            tokens += [str(gap), "r"]
            current, cursor = gap, onset
        if grace:
            tokens.append("g" + names)
            continue
        duration = _units(group[0].duration, div)
        if duration != current:
            tokens.append(str(duration))
            current = duration
        tokens.append(names)
        cursor = onset + group[0].duration
    return " ".join(tokens)


def decode(text: str) -> ScoreIndex:
    if len(text) > MAX_CHARS:
        raise NotesError("The note list is too long")
    numbered = [(number, line.strip()) for number, line in enumerate(text.splitlines(), 1) if line.strip()]
    lines = [line for _, line in numbered]
    if not lines or not lines[0].startswith(VERSION + " "):
        raise NotesError(f'The note list must start with a "{VERSION} div=… ts=… ks=…" line')
    try:
        settings = dict(part.split("=", 1) for part in lines[0].split()[1:])
        div, meter, key = int(settings["div"]), settings["ts"], settings.get("ks", "0")
        measures: list[Measure] = []
        current_meter = meter
        for number, line in numbered[1:]:
            if line.startswith("m"):
                parts = line.split()
                if not all("=" in part for part in parts[1:]) or not parts[0][1:].isdigit():
                    raise NotesError(f"Line {number}: a bar line looks like 'm3 len=96', not {line!r}")
                fields = dict(part.split("=", 1) for part in parts[1:])
                if "len" not in fields:
                    raise NotesError(f"Line {number}: bar line '{parts[0]}' needs len=…, e.g. '{parts[0]} len=96'")
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
                if not measures:
                    raise NotesError(f"Line {number}: a voice line needs a bar line like 'm3 len=96' before it")
                voice, _, body = line.partition(":")
                if not re.fullmatch(r"\d+\.\d+", voice):
                    raise NotesError(f"Line {number}: expected 'staff.voice: tokens', e.g. '1.1: 24 C4'")
                staff, layer = (int(part) for part in voice.split("."))
                _read_voice(body.split(), measures[-1], staff, layer, div)
        for measure in measures:
            measure.events.sort(key=lambda event: (event.onset, event.staff))
    except NotesError:
        raise
    except (KeyError, ValueError, IndexError) as error:
        raise NotesError(f"The note list could not be read: {error}") from error
    if not measures:
        raise NotesError("The note list has no measures")
    return ScoreIndex.from_measures(measures, meter, key)


def _read_voice(tokens: list[str], measure: Measure, staff: int, layer: int, div: int) -> None:
    cursor, duration = Fraction(0), Fraction(0)
    for attack, token in enumerate(tokens):
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
                Event(identity, measure.number, staff, cursor, Fraction(0) if grace else duration, pitch, grace, layer, tied, attack=str(attack) if grace else "")
            )
        if not grace:
            cursor += duration
