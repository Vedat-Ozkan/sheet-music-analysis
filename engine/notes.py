from __future__ import annotations

import re
from dataclasses import dataclass, field
from fractions import Fraction

from engine.errors import UserError
from engine.score import PITCH, POSITION_DENOMINATOR, Event, Mark, Measure, ScoreIndex, beat_length, parse_meter

VERSION = "N1"
ORNAMENTS = ("tr", "mu", "ml", "tu", "tl")
MARK = re.compile(
    r"(?P<pedal>P[du])@(?P<at1>[\d.]+)"
    r"|q=(?P<tempo>[\d.]+|[a-z]+)@(?P<at2>[\d.]+)"
    r"|(?P<hairpin>[<>])@(?P<at3>[\d.]+)\+(?P<length>[\d.]+)"
    r"|(?P<ornament>" + "|".join(ORNAMENTS) + r")@(?P<at4>[\d.]+):(?P<pitch>" + PITCH.pattern + r")(?:\^(?P<upper>[a-z]+))?(?:_(?P<lower>[a-z]+))?"
    r"|(?P<dynamic>[a-z]+)@(?P<at5>[\d.]+)"
)
MAX_CHARS = 200_000
CLEFS = {"G": ("G", 2, 0), "F": ("F", 4, 0), "C": ("C", 3, 0), "T": ("C", 4, 0), "G8": ("G", 2, -1)}
CLEF = re.compile(r"clef=(" + "|".join(CLEFS) + ")")
WORDS_LABEL = re.compile(r"\d+\.\d+w")
CHORD_ENTRY = re.compile(r"(?P<symbol>[^@\s]+)@(?P<at>\d+)")
MARKED = re.compile(r"(?P<opened>\(*)(?P<sounding>.+?)(?P<signs>[.>]*)(?P<closed>\)*)")
METER = re.compile(r"(?:[1-9]\d*/[1-9]\d*)?")
KEY = re.compile(r"0|[1-7][sf]")
BAR_NAME = re.compile(r"\d+[a-zA-Z]*")
VOICE_LABEL = re.compile(r"\d+\.\d+")


class NotesError(UserError):
    pass


def not_a_pitch(bar: str, written: str) -> str:
    return (f"Bar {bar}: {written!r} is not a note this list can hold. A pitch is a letter A to G, then # or b "
            "(or ## or bb) if it has one, then the octave as one digit, such as F#4 or Bb3.")


def bar_line_name(line: str) -> str | None:
    name = line.split()[0][1:]
    return name if BAR_NAME.fullmatch(name) else None


def voice_label(label: str) -> tuple[int, int] | None:
    if not VOICE_LABEL.fullmatch(label):
        return None
    staff, layer = label.split(".")
    return int(staff), int(layer)


def _check_signatures(meter: str, key: str) -> None:
    if not METER.fullmatch(meter):
        raise NotesError(f"A time signature looks like ts=3/4, not ts={meter}")
    if not KEY.fullmatch(key):
        raise NotesError(f"A key signature looks like ks=0, ks=2s or ks=3f, not ks={key}")


@dataclass
class Voice:
    staff: int
    number: int
    events: list[Event] = field(default_factory=list)


@dataclass(frozen=True)
class Token:
    sounding: str
    slurs_opened: int = 0
    slurs_closed: int = 0
    staccato: bool = False
    accent: bool = False


def token(text: str) -> Token:
    parts = MARKED.fullmatch(text)
    return Token(parts["sounding"], len(parts["opened"]), len(parts["closed"]), "." in parts["signs"], ">" in parts["signs"])


def encode(index: ScoreIndex, first: int | None = None, last: int | None = None) -> str:
    measures = index.select(first, last)
    div = index.ppq
    meter, key = index.meter, index.key_signature or "0"
    lines = [f"{VERSION} div={div} ts={meter} ks={key}" + (" orn=upper" if index.ornaments_from_above else "")]
    for measure in measures:
        header = f"m{measure.name} len={_units(measure.length, div)}"
        if measure.meter and measure.meter != meter:
            meter = measure.meter
            header += f" ts={meter}"
        if measure.key_signature and measure.key_signature != key:
            key = measure.key_signature
            header += f" ks={key}"
        lines.append(header)
        if measure.marks:
            lines.append("x: " + " ".join(_mark(mark) for mark in measure.marks))
        voices: dict[tuple[int, int], list[Event]] = {}
        for event in measure.events:
            if event.pitch:
                voices.setdefault((event.staff, event.layer), []).append(event)
        for (staff, layer), events in sorted(voices.items()):
            lines.append(f"{staff}.{layer}: " + _voice(events, div))
    return "\n".join(lines)


def _quarters(value: Fraction) -> str:
    return f"{float(value):.3f}".rstrip("0").rstrip(".")


def _mark(mark: Mark) -> str:
    at = _quarters(mark.offset)
    if mark.kind == "pedal":
        return f"P{mark.value[0]}@{at}"
    if mark.kind == "tempo":
        return f"q={mark.value}@{at}"
    if mark.kind == "hairpin":
        return f"{mark.value}@{at}+{_quarters(mark.length)}"
    if mark.kind == "ornament":
        return f"{mark.value}@{at}:{mark.pitch}" + (f"^{mark.upper}" if mark.upper else "") + (f"_{mark.lower}" if mark.lower else "")
    return f"{mark.value}@{at}"


def _read_marks(tokens: list[str], measure: Measure) -> None:
    for token in tokens:
        match = MARK.fullmatch(token)
        if not match:
            raise ValueError(f"unknown mark {token!r}")
        found = match.groupdict()
        at = Fraction(next(found[f"at{n}"] for n in range(1, 6) if found[f"at{n}"])).limit_denominator(POSITION_DENOMINATOR)
        if found["pedal"]:
            measure.marks.append(Mark("pedal", at, "down" if found["pedal"] == "Pd" else "up"))
        elif found["tempo"]:
            measure.marks.append(Mark("tempo", at, found["tempo"]))
        elif found["hairpin"]:
            measure.marks.append(Mark("hairpin", at, found["hairpin"], Fraction(found["length"]).limit_denominator(POSITION_DENOMINATOR)))
        elif found["ornament"]:
            measure.marks.append(Mark("ornament", at, found["ornament"], pitch=found["pitch"], upper=found["upper"] or "", lower=found["lower"] or ""))
        else:
            measure.marks.append(Mark("dynamic", at, found["dynamic"]))


def _read_chord_symbols(entries: list[str], measure: Measure, div: int) -> None:
    for entry in entries:
        found = CHORD_ENTRY.fullmatch(entry)
        if not found or Fraction(int(found["at"]), div) >= measure.length:
            raise NotesError(f"Bar {measure.name}: a chord symbol is written as symbol@position, without spaces, with the "
                             f"position in units from the start of the bar and below its len, e.g. D7@0, not {entry!r}")
        measure.chord_symbols.append((Fraction(int(found["at"]), div), found["symbol"]))


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
            tokens.append(("u" if group[0].slashed else "g") + names)
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
        if div < 1:
            raise NotesError(f"div= is the number of units in a quarter note, so it must be at least 1, not {div}")
        _check_signatures(meter, key)
        measures: list[Measure] = []
        current_meter, current_key = meter, key
        for number, line in numbered[1:]:
            if line.startswith("m"):
                parts = line.split()
                if not all("=" in part for part in parts[1:]) or bar_line_name(line) is None:
                    raise NotesError(f"Line {number}: a bar line looks like 'm3 len=96', not {line!r}")
                fields = dict(part.split("=", 1) for part in parts[1:])
                if "len" not in fields:
                    raise NotesError(f"Line {number}: bar line '{parts[0]}' needs len=…, e.g. '{parts[0]} len=96'")
                current_meter = fields.get("ts", current_meter)
                current_key = fields.get("ks", current_key)
                _check_signatures(current_meter, current_key)
                measure = Measure(
                    id=f"m{len(measures) + 1}",
                    number=len(measures) + 1,
                    index=len(measures) + 1,
                    name=parts[0][1:].lower(),
                    beat_length=beat_length(*parse_meter(current_meter)) if current_meter else Fraction(1),
                    meter=current_meter,
                    key_signature=current_key,
                )
                measure.declared_length = Fraction(int(fields["len"]), div)
                measures.append(measure)
            elif line.startswith("x:"):
                if not measures:
                    raise NotesError(f"Line {number}: a marks line needs a bar line like 'm3 len=96' before it")
                _read_marks(line[2:].split(), measures[-1])
            elif line.startswith("c:"):
                if not measures:
                    raise NotesError(f"Line {number}: a chord symbol line needs a bar line like 'm3 len=96' before it")
                _read_chord_symbols(line[2:].split(), measures[-1], div)
            else:
                if not measures:
                    raise NotesError(f"Line {number}: a voice line needs a bar line like 'm3 len=96' before it")
                voice, _, body = line.partition(":")
                if WORDS_LABEL.fullmatch(voice):
                    continue
                if (labelled := voice_label(voice)) is None:
                    raise NotesError(f"Line {number}: expected 'staff.voice: tokens', e.g. '1.1: 24 C4'")
                staff, layer = labelled
                _read_voice(body.split(), measures[-1], staff, layer, div)
        for measure in measures:
            measure.events.sort(key=lambda event: (event.onset, event.staff))
    except NotesError:
        raise
    except (KeyError, ValueError, IndexError) as error:
        raise NotesError(f"The note list could not be read: {error}") from error
    if not measures:
        raise NotesError("The note list has no measures")
    _number_by_name(measures)
    index = ScoreIndex.from_measures(measures, meter, key)
    index.ornaments_from_above = settings.get("orn") == "upper"
    return index


def _number_by_name(measures: list[Measure]) -> None:
    named = [int(measure.name) if measure.name.isdigit() else None for measure in measures]
    if None in named or any(later <= earlier for earlier, later in zip(named, named[1:])):
        named = [position - (measures[0].name == "0") for position in range(1, len(measures) + 1)]
    for measure, number in zip(measures, named):
        measure.number = number
        for event in measure.events:
            event.measure = number


def _read_voice(tokens: list[str], measure: Measure, staff: int, layer: int, div: int) -> None:
    cursor, duration = Fraction(0), Fraction(0)
    for attack, written in enumerate(tokens):
        if written.isdigit():
            duration = Fraction(int(written), div)
            continue
        if CLEF.fullmatch(written):
            continue
        sounding = token(written).sounding
        if sounding == "r":
            cursor += duration
            continue
        grace = sounding.startswith(("g", "u"))
        for name in sounding[1 if grace else 0 :].split("+"):
            tied = name.endswith("~")
            pitch = name.rstrip("~")
            if not PITCH.fullmatch(pitch):
                raise NotesError(not_a_pitch(measure.name, written))
            identity = f"{measure.id}-{staff}.{layer}-{len(measure.events)}"
            measure.events.append(
                Event(identity, measure.number, staff, cursor, Fraction(0) if grace else duration, pitch, grace, layer, tied,
                      attack=str(attack) if grace else "", slashed=sounding.startswith("u"))
            )
        if not grace:
            cursor += duration
