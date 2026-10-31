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


def _beat_rows(measure: Measure) -> list[str]:
    notes = [event for event in measure.events if event.pitch and not event.grace]
    rows = []
    beats = int(measure.length / measure.beat_length + Fraction(95, 96)) if measure.length else 0
    for number in range(beats):
        start, end = number * measure.beat_length, (number + 1) * measure.beat_length
        starting = [event for event in notes if start <= event.onset < end]
        held = [event for event in notes if event.onset < start < event.onset + event.duration]
        if not starting and not held:
            rows.append(f"  b{number + 1} | rest")
            continue
        sounding = sorted(starting + held, key=lambda event: midi(event.pitch))
        classes: list[str] = []
        for event in sounding:
            if event.pitch.rstrip("0123456789") not in classes:
                classes.append(event.pitch.rstrip("0123456789"))
        row = f"  b{number + 1} | bass {sounding[0].pitch} | {' '.join(classes)}"
        staves = sorted({event.staff for event in starting})
        for staff in staves:
            row += f" | staff {staff}: " + _onsets(measure, [event for event in starting if event.staff == staff])
        if held:
            row += " | held: " + " ".join(event.pitch for event in sorted(held, key=lambda event: midi(event.pitch)))
        rows.append(row)
    return rows


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
        "Each row: beat | lowest note | pitch classes sounding, low to high | notes per staff as pitch@beat-where-it-starts.",
        "",
    ]
    meter, key = shown.meter, shown.key_signature
    for measure in measures:
        changes = []
        if measure.meter != meter:
            changes.append(f"{measure.meter}; one beat = {_beat(measure)}")
        if measure.key_signature != key:
            changes.append(f"key signature: {describe_key_signature(measure.key_signature)}")
        meter, key = measure.meter, measure.key_signature
        lines.append(f"m{measure.number}" + (f" ({'; '.join(changes)})" if changes else ""))
        lines += _beat_rows(measure)
    return "\n".join(lines)


def _beat(measure: Measure) -> str:
    unit = float(measure.beat_length)
    return f"{unit:g} quarter note{'' if unit == 1 else 's'}"
