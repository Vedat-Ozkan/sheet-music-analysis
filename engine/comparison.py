from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache

from music21 import key as m21key
from music21 import roman

from engine.reduce import midi
from engine.score import ScoreIndex

MEASURE_LINE = re.compile(r"^m(\d+)(var\d+)?[a-z]?(?:-(\d+))?\s*(?:=\s*m(\d+)(?:-(\d+))?)?\s*(.*)$")
BEAT = re.compile(r"^b(\d+(?:\.\d+)?)$")
KEY = re.compile(r"^([A-Ga-g][#b-]*):$")
NOT_A_CHORD = re.compile(r"^(\|.*|:?\|\|:?|\\\\.*|NC|N\.C\.|\(.*|.*\))$")


@dataclass(frozen=True)
class Label:
    measure: int
    beat: float
    key: str
    figure: str


@dataclass(frozen=True)
class Sounding:
    tonic: int
    minor: bool
    root: int
    tones: frozenset[int]
    bass: int


@lru_cache(maxsize=None)
def sounding(key: str, figure: str) -> Sounding | None:
    try:
        local = m21key.Key(m21key.convertKeyStringToMusic21KeyString(key))
        chord = roman.RomanNumeral(figure.replace("ø", "/o"), local, sixthMinor=roman.Minor67Default.CAUTIONARY, seventhMinor=roman.Minor67Default.CAUTIONARY)
        return Sounding(local.tonic.pitchClass, local.mode == "minor", chord.root().pitchClass, frozenset(p.pitchClass for p in chord.pitches), chord.bass().pitchClass)
    except Exception:
        return None


def from_romantext(text: str) -> list[Label]:
    by_measure: dict[int, list[tuple[float, str, str]]] = {}
    key_after: dict[int, str] = {}
    key = "C"
    for line in text.splitlines():
        match = MEASURE_LINE.match(line.strip())
        if not match or match.group(2):
            continue
        first, last = int(match.group(1)), int(match.group(3) or match.group(1))
        if match.group(4):
            source = int(match.group(4))
            for offset in range(last - first + 1):
                by_measure[first + offset] = list(by_measure.get(source + offset, []))
                key = key_after.get(source + offset, key)
                key_after[first + offset] = key
            continue
        beat = 1.0
        chords = by_measure.setdefault(first, [])
        for token in match.group(6).split():
            if BEAT.match(token):
                beat = float(token[1:])
            elif KEY.match(token):
                key = token[:-1].replace("-", "b")
            elif not NOT_A_CHORD.match(token):
                chords.append((beat, key, token))
        key_after[first] = key
    return [Label(number, beat, key, figure) for number in sorted(by_measure) for beat, key, figure in by_measure[number]]


def from_draft(draft) -> list[Label]:
    return [Label(chord.measure, chord.beat, chord.key, chord.label) for chord in draft.chords]


def from_annotations(annotations: dict) -> list[Label]:
    found, key = [], "C"
    harmonies = [item for item in annotations["annotations"] if item["type"] == "harmony"]
    for item in sorted(harmonies, key=lambda item: (item["at"]["measure"], item["at"].get("beat", 1))):
        key = item.get("key", key)
        found.append(Label(item["at"]["measure"], float(item["at"].get("beat", 1)), key, item["label"].split(" ")[0]))
    return found


def matches(reference: Sounding, reading: Sounding) -> dict[str, bool]:
    same_key = (reference.tonic, reference.minor) == (reading.tonic, reading.minor)
    same_root = reference.root == reading.root
    same_chord = same_root and reference.tones == reading.tones
    same_bass = same_chord and reference.bass == reading.bass
    return dict(key=same_key, root=same_root, chord=same_chord, chord_and_bass=same_bass, full=same_bass and same_key)

Span = tuple[Fraction, Fraction, Sounding | None]


class Timeline:
    def __init__(self, index: ScoreIndex):
        self.index = index
        self.starts: dict[int, Fraction] = {}
        self.measures = {}
        total = Fraction(0)
        for measure in index.measures:
            self.starts.setdefault(measure.number, total)
            self.measures.setdefault(measure.number, measure)
            total += measure.length
        self.total = total

    def spans(self, labels: list[Label]) -> tuple[list[Span], int]:
        placed, missing = [], 0
        for label in labels:
            measure = self.measures.get(label.measure)
            if measure is None:
                missing += 1
                continue
            inside = measure.offset_of(label.beat) if measure.declared_length is not None else Fraction(0)
            placed.append((self.starts[label.measure] + min(inside, measure.length), sounding(label.key, label.figure)))
        placed.sort(key=lambda item: item[0])
        ends = [start for start, _ in placed[1:]] + [self.total]
        return [(start, end, chord) for (start, chord), end in zip(placed, ends) if end > start], missing

    def fit(self, spans: list[Span]) -> float:
        inside = outside = Fraction(0)
        notes = sorted(
            (self.starts[m.number] + e.onset, e.duration, midi(e.pitch) % 12)
            for m in self.index.measures
            if self.measures[m.number] is m
            for e in m.events
            if e.pitch and not e.grace
        )
        position = 0
        for onset, duration, pitch_class in notes:
            while position < len(spans) - 1 and spans[position][1] <= onset:
                position += 1
            if not spans or not spans[position][0] <= onset < spans[position][1] or spans[position][2] is None:
                continue
            if pitch_class in spans[position][2].tones:
                inside += duration
            else:
                outside += duration
        return float(inside / (inside + outside)) if inside + outside else 0.0


def compare(reference: list[Label], reading: list[Label], index: ScoreIndex) -> dict:
    timeline = Timeline(index)
    ref, ref_missing = timeline.spans(reference)
    hyp, _ = timeline.spans(reading)
    cuts = sorted({point for start, end, _ in ref + hyp for point in (start, end)})

    def at(spans: list[Span], time: Fraction) -> Sounding | None:
        return next((chord for start, end, chord in spans if start <= time < end), None)

    weights = dict.fromkeys(("labelled", "key", "root", "chord", "chord_and_bass", "full"), Fraction(0))
    for start, end in zip(cuts, cuts[1:]):
        r, h = at(ref, start), at(hyp, start)
        if r is None:
            continue
        length = end - start
        weights["labelled"] += length
        if h is None:
            continue
        for name, agrees in matches(r, h).items():
            weights[name] += length * agrees
    labelled = weights.pop("labelled")
    result = {name: round(float(value / labelled), 3) if labelled else None for name, value in weights.items()}
    result.update(
        reference_chords=len(reference),
        reading_chords=len(reading),
        reference_unreadable=sum(1 for label in reference if sounding(label.key, label.figure) is None),
        reading_unreadable=sum(1 for label in reading if sounding(label.key, label.figure) is None),
        reference_outside_score=ref_missing,
        reference_fit=round(timeline.fit(ref), 3),
        reading_fit=round(timeline.fit(hyp), 3),
    )
    return result
