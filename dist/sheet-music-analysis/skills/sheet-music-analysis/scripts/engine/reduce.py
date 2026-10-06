"""A beat-by-beat table of the notes, for an analyst to read instead of the raw score.

Each row is one beat: the bass, the pitch classes sounding, and every note with
the exact beat where it starts, written the way the annotation list addresses it.
"""

from __future__ import annotations

from fractions import Fraction

from engine.score import Event, Measure, ScoreIndex

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
    """ "G5@1 F5@1.33": each note with the beat it starts on; simultaneous notes are joined with +."""
    groups: dict[Fraction, list[Event]] = {}
    for event in events:
        groups.setdefault(event.onset, []).append(event)
    parts = []
    for onset in sorted(groups):
        names = "+".join(event.pitch for event in sorted(groups[onset], key=lambda event: midi(event.pitch)))
        parts.append(f"{names}@{round(measure.beat_of(onset), 2):g}")
    return " ".join(parts)


def as_text(index: ScoreIndex, first: int | None = None, last: int | None = None) -> str:
    measures = [m for m in index.measures if (first is None or m.number >= first) and (last is None or m.number <= last)]
    unit = float(index.measures[-1].beat_length)
    lines = [
        f"Key signature: {describe_key_signature(index.key_signature)}. Meter: {index.meter or 'unknown'}; "
        f"one beat = {unit:g} quarter note{'' if unit == 1 else 's'}.",
        f"The score has measures {index.measures[0].number} to {index.measures[-1].number}"
        + (" (0 is a pickup; its beat 1 is its first note)." if index.measures[0].number == 0 else ".")
        + (" The file's own bar numbers repeat, so bars are counted here in order." if index.renumbered else ""),
        "Each row: beat | lowest note | pitch classes sounding, low to high | notes per staff as pitch@beat-where-it-starts.",
        "",
    ]
    for measure in measures:
        lines.append(f"m{measure.number}")
        lines += _beat_rows(measure)
    return "\n".join(lines)
