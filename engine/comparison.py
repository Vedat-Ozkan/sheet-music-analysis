from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache

from music21 import harmony
from music21 import key as m21key
from music21 import meter
from music21 import roman

from engine.draft import FUNCTIONS
from engine.reduce import midi
from engine.score import ScoreIndex, beat_length

MEASURE_LINE = re.compile(r"^m(\d+)(var\d+)?([a-z])?(?:-(\d+))?\s*(?:=\s*m(\d+)(?:-(\d+))?)?\s*(.*)$")
TIME_SIGNATURE = re.compile(r"^Time Signature:\s*(.+?)\s*$")
BEAT = re.compile(r"^b(\d+(?:\.\d+)?)$")
KEY = re.compile(r"^([A-Ga-g][#b-]*):$")
CHORD_SYMBOL = re.compile(r"^(?!Ger|Fr|It|Cad)[A-G]")
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
    family: str | None = None


@lru_cache(maxsize=None)
def sounding(key: str, figure: str) -> Sounding | None:
    try:
        local = m21key.Key(m21key.convertKeyStringToMusic21KeyString(key))
        if CHORD_SYMBOL.match(figure):
            chord = harmony.ChordSymbol(re.sub(r"(^|/)([A-G])b", r"\1\2-", figure))
            return Sounding(local.tonic.pitchClass, local.mode == "minor", chord.root().pitchClass, frozenset(p.pitchClass for p in chord.pitches), chord.bass().pitchClass)
        chord = roman.RomanNumeral(figure.replace("ø", "/o"), local, sixthMinor=roman.Minor67Default.CAUTIONARY, seventhMinor=roman.Minor67Default.CAUTIONARY)
        return Sounding(local.tonic.pitchClass, local.mode == "minor", chord.root().pitchClass, frozenset(p.pitchClass for p in chord.pitches), chord.bass().pitchClass,
                        None if chord.secondaryRomanNumeral or chord.scaleDegree == 3 or chord.scaleDegree == 7 and (chord.root().pitchClass - local.tonic.pitchClass) % 12 != 11 else FUNCTIONS.get(str(chord.scaleDegree)))
    except Exception:
        return None


def beat_ratio(signature: meter.TimeSignature) -> Fraction:
    return Fraction(signature.beatDuration.quarterLength).limit_denominator(16) / beat_length(signature.numerator, signature.denominator)


def from_romantext(text: str) -> list[Label]:
    by_measure: dict[int, list[tuple]] = {}
    key_after: dict[int, str] = {}
    key, score_beats = "C", False
    matches, meters, current = [], {}, None
    for line in text.splitlines():
        if signature := TIME_SIGNATURE.match(line.strip()):
            try:
                current = meter.TimeSignature(signature.group(1))
            except Exception:
                pass
        elif (match := MEASURE_LINE.match(line.strip())) and not match.group(2):
            matches.append(match)
            meters[id(match)] = current
    lettered = {(int(match.group(1)), match.group(3)) for match in matches if match.group(3)}
    firsts = {number for number, letter in lettered if letter == "a"}
    blocks = [(start, next(length for length in range(1, len(firsts) + 2) if start + length not in firsts))
              for start, letter in lettered if letter != "a" and start in firsts and (start - 1, letter) not in lettered]

    def bar(printed: int, letter: str | None = None) -> int:
        before = lambda start, length: start <= printed if letter and letter != "a" else start + length <= printed if letter else start < printed
        return printed + sum(length for start, length in blocks if before(start, length))

    for match in matches:
        first = bar(int(match.group(1)), match.group(3))
        last = bar(int(match.group(4))) if match.group(4) else first
        if match.group(5):
            source = bar(int(match.group(5)))
            for offset in range(last - first + 1):
                by_measure[first + offset] = list(by_measure.get(source + offset, []))
                key = key_after.get(source + offset, key)
                key_after[first + offset] = key
            continue
        beat = 1.0
        chords = by_measure.setdefault(first, [])
        signature = meters[id(match)]
        for token in match.group(7).split():
            if BEAT.match(token):
                beat = float(token[1:])
                score_beats = score_beats or bool(signature) and beat >= 1 + signature.barDuration.quarterLength / signature.beatDuration.quarterLength
            elif KEY.match(token):
                key = token[:-1].replace("-", "b")
            elif not NOT_A_CHORD.match(token):
                chords.append((beat, key, token, signature))
        key_after[first] = key

    def scaled(beat: float, signature) -> float:
        if score_beats or signature is None:
            return beat
        ratio = beat_ratio(signature)
        return beat if ratio == 1 else float(1 + (Fraction(beat).limit_denominator(12) - 1) * ratio)

    return [Label(number, scaled(beat, signature), key, figure) for number in sorted(by_measure) for beat, key, figure, signature in by_measure[number]]


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
    same_root = reference.root == reading.root
    same_chord = same_root and reference.tones == reading.tones
    same_bass = same_chord and reference.bass == reading.bass
    same_key = reference.tonic == reading.tonic and (reference.minor == reading.minor or same_bass)
    return dict(key=same_key, root=same_root, chord=same_chord, chord_and_bass=same_bass, full=same_bass and same_key)


def same_function(a: Sounding, b: Sounding) -> bool:
    if a.bass != b.bass:
        return False
    if a.root == b.root and len(a.tones ^ b.tones) == 1 and (a.tones <= b.tones or b.tones <= a.tones):
        return True
    cadential = lambda s: s.root == s.tonic and s.bass == (s.tonic + 7) % 12 and len(s.tones) == 3
    dominant = lambda s, of: s.tonic == of.tonic and s.root == s.bass == (of.tonic + 7) % 12 and (s.root + 4) % 12 in s.tones
    return cadential(a) and dominant(b, a) or cadential(b) and dominant(a, b)


def same_idea(a: Sounding, b: Sounding) -> bool:
    if same_function(a, b):
        return True
    six_four = lambda s: s.bass == (s.root + 7) % 12 and len(s.tones) == 3
    if six_four(a) or six_four(b):
        return False
    if a.root == b.root and (a.tones <= b.tones or b.tones <= a.tones) and len(a.tones ^ b.tones) <= 1:
        return True
    if a.tones == b.tones and len(a.tones) == 4 and all((tone + 3) % 12 in a.tones for tone in a.tones):
        return True
    return a.tonic == b.tonic and a.family is not None and a.family == b.family


def agreement(reference: Sounding, reading: Sounding) -> dict[str, bool]:
    found = matches(reference, reading)
    return {**found, "function": same_function(reference, reading) or found["chord_and_bass"], "idea": same_idea(reference, reading) or found["chord_and_bass"]}


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
            inside = max(Fraction(0), (Fraction(label.beat).limit_denominator(96) - 1) * measure.beat_length)
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


def compare(reference: list[Label], reading: list[Label], index: ScoreIndex, bars: list[tuple[int, int]] | None = None) -> dict:
    timeline = Timeline(index)
    ref, ref_missing = timeline.spans(reference)
    hyp, _ = timeline.spans(reading)
    windows = [(timeline.starts[first], timeline.starts[last] + timeline.measures[last].length) for first, last in bars or []]
    cuts = sorted({point for start, end, _ in ref + hyp for point in (start, end)} | {point for window in windows for point in window})

    def at(spans: list[Span], time: Fraction) -> Sounding | None:
        return next((chord for start, end, chord in spans if start <= time < end), None)

    weights = dict.fromkeys(("labelled", "key", "root", "chord", "chord_and_bass", "function", "idea", "full"), Fraction(0))
    for start, end in zip(cuts, cuts[1:]):
        r, h = at(ref, start), at(hyp, start)
        if r is None or windows and not any(low <= start < high for low, high in windows):
            continue
        length = end - start
        weights["labelled"] += length
        if h is None:
            continue
        for name, agrees in agreement(r, h).items():
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
