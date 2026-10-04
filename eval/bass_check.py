"""Correct inversions that contradict the bass actually sounding, in a reviewed annotation list. Prototype.

    .venv/bin/python -m eval.bass_check [--reviewed opus-medium] [--out opus-medium-bassfix]

The error breakdown of 2026-10-03 found that where our chord matched the expert's but the bass did not,
the expert's bass was the lowest note sounding in 38% of cases and ours was not (for example `I` written
over an A in the bass, which is `I6` in F). This pass changes only the inversion figure, and only when the
lowest note that *starts with* the chord belongs to it: a note held over from before (a pedal, a tie) is
left alone. Writes corrected lists to out/eval/reviewed/<out>/ for eval.run to score.
"""

from __future__ import annotations

import argparse
import json
import re
from fractions import Fraction

from music21 import key as m21key
from music21 import roman

from engine.reduce import midi
from engine.render import load_toolkit
from engine.score import ScoreIndex
from eval import pieces
from eval.review import REVIEWED

FIGURE = re.compile(r"^(?P<head>[#b-]*[ivIV]+(?:o|\+|ø|/o)?)(?P<inversion>\d*)(?P<secondary>/.+)?$")
TRIAD, SEVENTH = ["", "6", "64"], ["7", "65", "43", "42"]


def lowest_starting(index: ScoreIndex, measure: int, beat: float) -> int | None:
    """Pitch class of the lowest note that begins exactly at this measure and beat, if any."""
    found = index.measure(measure) if hasattr(index, "measure") else next((m for m in index.measures if m.number == measure), None)
    if found is None:
        return None
    onset = found.offset_of(Fraction(beat).limit_denominator(48))
    starting = [e for e in found.events if e.pitch and not e.grace and e.onset == onset]
    return midi(min(starting, key=lambda e: midi(e.pitch)).pitch) % 12 if starting else None


def corrected(label: str, key: str, bass: int) -> str | None:
    """`label` with its inversion changed so that `bass` is in the bass, or None if it cannot or need not change."""
    match = FIGURE.match(label)
    if not match:
        return None  # augmented sixths, Neapolitans, Cad64 and chord symbols are left alone
    try:
        local = m21key.Key(m21key.convertKeyStringToMusic21KeyString(key))
        chord = roman.RomanNumeral(label.replace("ø", "/o"), local)
    except Exception:
        return None
    if chord.bass().pitchClass == bass:
        return None
    members = [chord.root().pitchClass, chord.third.pitchClass if chord.third else None, chord.fifth.pitchClass if chord.fifth else None, chord.seventh.pitchClass if chord.seventh else None]
    if bass not in members:
        return None  # the lowest note is not in the chord: a passing or neighbour note, not an inversion
    position = members.index(bass)
    figures = SEVENTH if chord.seventh is not None else TRIAD
    if position >= len(figures):
        return None
    return match["head"] + figures[position] + (match["secondary"] or "")


def lowest_over(index: ScoreIndex, start: tuple[int, float], end: tuple[int, float] | None) -> int | None:
    """Pitch class of the lowest note sounding anywhere from `start` up to `end` (the next chord label):
    the bottom of a broken-chord pattern, as a textbook defines the bass, rather than whatever starts first."""
    numbers = [m.number for m in index.measures]
    first = numbers.index(start[0]) if start[0] in numbers else None
    if first is None:
        return None
    lowest = None
    for m in index.measures[first:]:
        begin = m.offset_of(Fraction(start[1]).limit_denominator(48)) if m.number == start[0] else Fraction(0)
        stop = m.offset_of(Fraction(end[1]).limit_denominator(48)) if end and m.number == end[0] else m.length
        for e in m.events:
            if e.pitch and not e.grace and e.onset < stop and e.onset + e.duration > begin:
                if lowest is None or midi(e.pitch) < midi(lowest):
                    lowest = e.pitch
        if end is None or m.number >= end[0]:
            break
    return midi(lowest) % 12 if lowest else None


def fix(annotations: dict, index: ScoreIndex, mode: str = "span") -> tuple[dict, int]:
    changed, key = 0, "C"
    items = sorted((a for a in annotations["annotations"] if a["type"] == "harmony"), key=lambda a: (a["at"]["measure"], a["at"].get("beat", 1)))
    for number, item in enumerate(items):
        key = item.get("key", key)
        here = (item["at"]["measure"], float(item["at"].get("beat", 1)))
        after = items[number + 1] if number + 1 < len(items) else None
        following = (after["at"]["measure"], float(after["at"].get("beat", 1))) if after else None
        bass = lowest_over(index, here, following) if mode == "span" else lowest_starting(index, *here)
        if bass is None:
            continue
        new = corrected(item["label"].split(" ")[0], key, bass)
        if new:
            item["label"], changed = new, changed + 1
    return annotations, changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviewed", default="opus-medium")
    parser.add_argument("--out", default="opus-medium-bassfix")
    parser.add_argument("--mode", choices=("span", "onset"), default="span", help="span: lowest note over the chord's whole duration; onset: lowest note starting with it")
    args = parser.parse_args()
    target = REVIEWED / args.out
    target.mkdir(parents=True, exist_ok=True)
    for piece in pieces.PIECES:
        source = REVIEWED / args.reviewed / f"{piece.id}.json"
        if not source.exists() or not pieces.labels(piece):
            continue
        index = ScoreIndex(load_toolkit(pieces.score(piece)).getMEI())
        annotations, changed = fix(json.loads(source.read_text()), index, args.mode)
        (target / f"{piece.id}.json").write_text(json.dumps(annotations, indent=1))
        total = sum(1 for a in annotations["annotations"] if a["type"] == "harmony")
        print(f"{piece.id:26s} {changed:3d} of {total} chord labels changed")


if __name__ == "__main__":
    main()
