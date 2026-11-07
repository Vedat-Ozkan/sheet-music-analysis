from __future__ import annotations

from fractions import Fraction

from engine.score import Event, Measure, ScoreIndex, in_range

STEPS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
SIGNATURES = {"f": "flat", "s": "sharp"}


def midi(pitch: str) -> int:
    accidental = pitch[1:].rstrip("0123456789-")
    octave = int(pitch[1 + len(accidental) :])
    return STEPS[pitch[0]] + accidental.count("#") - accidental.count("b") + 12 * (octave + 1)


def describe_key_signature(signature: str) -> str:
    if not signature or signature == "0":
        return "no sharps or flats"
    count, kind = signature[:-1], SIGNATURES.get(signature[-1], "")
    return f"{count} {kind}{'' if count == '1' else 's'}"


def _pitch_class(event: Event) -> str:
    return event.pitch.rstrip("0123456789")


def _lowest(notes: list[Event], time: Fraction) -> Event | None:
    sounding = [event for event in notes if event.onset <= time < event.onset + event.duration]
    return min(sounding, key=lambda event: midi(event.pitch)) if sounding else None


def _bass_spans(notes: list[Event], start: Fraction, end: Fraction) -> list[tuple[Fraction, Fraction]]:
    starts = [start]
    bass = _lowest(notes, start)
    for onset in sorted({event.onset for event in notes if start < event.onset < end}):
        lowest = _lowest(notes, onset)
        if bass and _pitch_class(lowest) != _pitch_class(bass):
            starts.append(onset)
        bass = lowest
    return list(zip(starts, starts[1:] + [end]))


def _beat_rows(measure: Measure) -> list[tuple[str, str | None]]:
    notes = [event for event in measure.events if event.pitch and not event.grace]
    rows = []
    beats = int(measure.length / measure.beat_length + Fraction(95, 96)) if measure.length else 0
    for number in range(beats):
        for start, end in _bass_spans(notes, number * measure.beat_length, (number + 1) * measure.beat_length):
            rows.append(_row(measure, notes, start, end))
    return rows


def _row(measure: Measure, notes: list[Event], start: Fraction, end: Fraction) -> tuple[str, str | None]:
    label = f"b{round(measure.beat_of(start), 2):g}"
    starting = [event for event in notes if start <= event.onset < end]
    held = [event for event in notes if event.onset < start < event.onset + event.duration]
    if not starting and not held:
        return f"  {label} | rest", None
    sounding = sorted(starting + held, key=lambda event: midi(event.pitch))
    classes: list[str] = []
    for event in sounding:
        if _pitch_class(event) not in classes:
            classes.append(_pitch_class(event))
    row = f"  {label} | bass {sounding[0].pitch} | {' '.join(classes)}"
    staves = sorted({event.staff for event in starting})
    for staff in staves:
        row += f" | staff {staff}: " + _onsets(measure, [event for event in starting if event.staff == staff])
    if held:
        row += " | held: " + " ".join(event.pitch for event in sorted(held, key=lambda event: midi(event.pitch)))
    return row, _pitch_class(sounding[0])


def _onsets(measure: Measure, events: list[Event]) -> str:
    groups: dict[Fraction, list[Event]] = {}
    for event in events:
        groups.setdefault(event.onset, []).append(event)
    parts = []
    for onset in sorted(groups):
        names = "+".join(event.pitch for event in sorted(groups[onset], key=lambda event: midi(event.pitch)))
        parts.append(f"{names}@{round(measure.beat_of(onset), 2):g}")
    return " ".join(parts)


def as_text(index: ScoreIndex, first: int | None = None, last: int | None = None) -> str:
    measures = [m for m in index.measures if in_range(m.number, first, last)]
    shown = measures[0] if measures else index.measures[0]
    lines = [
        f"Key signature: {describe_key_signature(shown.key_signature or index.key_signature)}. Meter: {shown.meter or index.meter or 'unknown'}; "
        f"one beat = {_beat(shown)}.",
        f"The score has measures {index.measures[0].number} to {index.measures[-1].number}"
        + (" (0 is a pickup; its beat 1 is its first note)." if index.measures[0].number == 0 else ".")
        + (" The file's own bar numbers repeat, so bars are counted here in order." if index.renumbered else ""),
        "Each row: beat | lowest note | pitch classes sounding, low to high | notes per staff as pitch@beat-where-it-starts. "
        "A beat has more rows when its lowest note changes inside it, each labelled with the beat where it starts (b2.5 is halfway through beat 2).",
    ]
    body: list[str] = []
    basses: list[str] = []
    meter, key = shown.meter, shown.key_signature
    for measure in measures:
        changes = []
        if measure.meter != meter:
            changes.append(f"{measure.meter}; one beat = {_beat(measure)}")
        if measure.key_signature != key:
            changes.append(f"key signature: {describe_key_signature(measure.key_signature)}")
        meter, key = measure.meter, measure.key_signature
        body.append(f"m{measure.number}" + (f" ({'; '.join(changes)})" if changes else ""))
        for row, bass in _beat_rows(measure):
            body.append(row)
            basses += [bass] if bass else []
    rate = round(2 * sum(a != b for a, b in zip(basses, basses[1:])) / max(len(measures), 1)) / 2
    lines += [
        f"The lowest note changes about {rate:g} time{'' if rate == 1 else 's'} a bar in these bars "
        "(counting a new pitch class only: a repeated, tied or octave-shifted lowest note, or a rest, is not a change).",
        "",
    ]
    return "\n".join(lines + body)


def _beat(measure: Measure) -> str:
    unit = float(measure.beat_length)
    return f"{unit:g} quarter note{'' if unit == 1 else 's'}"
