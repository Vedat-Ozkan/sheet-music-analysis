from __future__ import annotations

import copy
import math
import os
import tempfile
from bisect import bisect_left, bisect_right
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from fractions import Fraction

from music21 import chord, clef, tie, converter, duration, dynamics, instrument, key, layout, meter, note, pitch, stream
from music21.common.numberTools import opFrac
from music21.stream import makeNotation
from music21.musicxml.m21ToXml import GeneralObjectExporter

from engine.errors import UserError
from engine.render import load_toolkit
from engine.score import ScoreIndex, beat_length

PARTS_DO_NOT_LINE_UP = ("A piano version can't be made for this score: its parts don't line up bar for bar, "
                        "which happens when a PDF was read badly. The full score can still be drawn.")
UNWRITABLE_BAR = ("A piano version can't be made for bars {first}-{last}: bar {name} was read with note lengths "
                  "that can't be written. Try other bars, or correct that bar first.")
FAMILIES = {
    "Piccolo", "Flute", "Oboe", "EnglishHorn", "Clarinet", "BassClarinet", "Bassoon", "Contrabassoon", "Horn", "Trumpet",
    "Trombone", "BassTrombone", "Tuba", "Timpani", "Harp", "Violin", "Viola", "Violoncello", "Contrabass",
    "SopranoSaxophone", "AltoSaxophone", "TenorSaxophone", "BaritoneSaxophone", "Euphonium", "Piano", "Organ",
}
STRINGS = {"Violin", "Viola", "Violoncello", "Contrabass"}
BASS = {"Violoncello", "Contrabass", "Bassoon", "Contrabassoon", "Tuba", "Trombone", "BassTrombone", "BassClarinet", "BaritoneSaxophone"}
LOWEST_RIGHT_HAND = 55
SPAN = 14
HIGHEST_LEFT_HAND = 64
PLAIN = (1.0, 0.5, 0.25, 0.125, 0.0625, 0.03125)
TUPLETS = (Fraction(2, 3), Fraction(4, 5), Fraction(4, 7))

class PianoError(UserError):
    pass


def reduce(score: bytes, measures: tuple[int, int] | None, keep: Iterable[tuple[int, Fraction, str, Fraction]] = (),
           index: ScoreIndex | None = None) -> bytes:
    index = index or ScoreIndex(load_toolkit(score).getMEI())
    owners = {segment.index: (measure, segment.start, following.start if following else None)
              for measure in index.measures
              for segment, following in zip(measure.segments, measure.segments[1:] + [None])}
    first = index.select(*measures)[0].index if measures else 1
    last = index.measure(measures[1]).last_index if measures else max(owners)
    parts = _parts(score, (first, last))
    kept: dict[int, list[tuple[Fraction, pitch.Pitch, float]]] = {}
    for number, offset, name, length in keep:
        kept.setdefault(number, []).append((offset, _m21_pitch(name), float(length)))
    reference = next((p for p in parts.values() if p.family in STRINGS), next(iter(parts.values())))
    signature = reference.keys[0]
    flat_key = signature is not None and signature.sharps < 0
    right_hand, left_hand = stream.Part(), stream.Part()
    previous_lead = None
    carried: dict = {}
    for number, ref in enumerate(reference.measures):
        bar = {name: part.measures[number] for name, part in parts.items()}
        length = max(part.ends[number] for part in parts.values()) or reference.bar_lengths[number]
        owner, start, end = owners[first + number]
        here = [(float(offset - start), found, length) for offset, found, length in kept.get(owner.number, [])
                if start <= offset and (end is None or offset < end)]
        right, left, previous_lead, carried = _reduce_bar(
            bar, parts, ref, (reference.keys[number], reference.times[number], length),
            owner.number, here, flat_key, previous_lead, number == 0, carried
        )
        right_hand.append(right)
        left_hand.append(left)
    for hand in (right_hand, left_hand):
        _pair_ties(hand)
    out = stream.Score([right_hand, left_hand])
    out.insert(0, layout.StaffGroup([right_hand, left_hand], symbol="brace", name="Piano"))
    for hand in (right_hand, left_hand):
        _notate(hand)
        bar = _unwritable_bar(hand)
        if bar is not None:
            span = (index.name_of(owners[first][0].number), index.name_of(owners[last][0].number))
            raise PianoError(UNWRITABLE_BAR.format(first=span[0], last=span[1], name=index.name_of(bar)))
    exporter = GeneralObjectExporter(out)
    exporter.makeNotation = False
    return exporter.parse()


def _unwritable_bar(hand: stream.Part) -> int | None:
    return next((measure.number for measure in hand.getElementsByClass(stream.Measure) for element in measure.recurse().notesAndRests
                 if element.duration.type == "inexpressible" or (element.duration.type == "complex" and not element.isRest)), None)


def _notate(hand: stream.Part) -> None:
    if not hand.streamStatus.accidentals:
        makeNotation.makeAccidentalsInMeasureStream(hand)
    for measure in hand.getElementsByClass(stream.Measure):
        measure.flattenUnnecessaryVoices(inPlace=True)
    if not hand.streamStatus.beams:
        makeNotation.makeBeams(hand, inPlace=True)
    for measure in hand.getElementsByClass(stream.Measure):
        for written in (measure, *measure.voices):
            if not written.streamStatus.tuplets:
                makeNotation.makeTupletBrackets(written, inPlace=True)
    hand.splitAtDurations(recurse=True)


def _pair_ties(part: stream.Part) -> None:
    heads = []
    for n in part.recurse().notes:
        start = opFrac(n.getOffsetInHierarchy(part))
        heads += [(start, opFrac(start + n.quarterLength), written) for written in (n.notes if n.isChord else [n])]
    kind = lambda w: w.tie.type if w.tie else None
    starts = {(s, w.pitch.ps) for s, _, w in heads if kind(w) in ("stop", "continue")}
    ends = {(e, w.pitch.ps) for _, e, w in heads if kind(w) in ("start", "continue")}
    last = opFrac(part.highestTime)
    for s, e, w in heads:
        goes = kind(w) in ("start", "continue") and ((e, w.pitch.ps) in starts or e == last)
        comes = kind(w) in ("stop", "continue") and ((s, w.pitch.ps) in ends or s == 0)
        w.tie = _edge_tie(comes, goes)


def _edge_tie(comes_in: bool, goes_out: bool):
    if comes_in and goes_out:
        return tie.Tie("continue")
    return tie.Tie("stop") if comes_in else tie.Tie("start") if goes_out else None


class _Part:
    def __init__(self, part: stream.Part, name: str, family: str):
        self.measures = list(part.getElementsByClass(stream.Measure))
        self.keys = [m.keySignature or m.getContextByClass(key.KeySignature) for m in self.measures]
        self.times = [m.timeSignature or m.getContextByClass(meter.TimeSignature) for m in self.measures]
        self.bar_lengths = [m.barDuration.quarterLength for m in self.measures]
        self.ends = [max((m.barDuration.quarterLength if e.isRest and e.fullMeasure in (True, "always")
                          else opFrac(e.getOffsetInHierarchy(m) + e.quarterLength)
                          for e in m.recurse().notesAndRests if not e.duration.isGrace), default=0)
                     for m in self.measures]
        self.name, self.family = name, family


def _family(part: stream.Part, inst: instrument.Instrument) -> str:
    family = type(inst).__name__
    if family in FAMILIES:
        return family
    for name in (inst.instrumentName, part.partName):
        try:
            return type(instrument.fromString(name)).__name__ if name else family
        except instrument.InstrumentException:
            continue
    return family


def _parts(score: bytes, positions: tuple[int, int]) -> dict[str, _Part]:
    suffix = ".mxl" if score[:2] == b"PK" else ".musicxml"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as file:
        file.write(score)
    try:
        parsed = converter.parse(file.name, format="musicxml")
    finally:
        os.unlink(file.name)
    if len({tuple(m.number for m in part.getElementsByClass(stream.Measure)) for part in parsed.parts}) > 1:
        raise PianoError(PARTS_DO_NOT_LINE_UP)
    excerpt = parsed.measures(positions[0] - 1, positions[1], indicesNotNumbers=True)
    excerpt = excerpt.toSoundingPitch()
    every_part = [(part, part.getInstrument()) for part in excerpt.parts]
    found = [(part, inst) for part, inst in every_part if part.flatten().pitches] or every_part
    families = [_family(part, inst) for part, inst in found]
    parts = {}
    for (part, inst), family in zip(found, families):
        if isinstance(inst, instrument.UnpitchedPercussion):
            continue
        name = str(len(parts))
        parts[name] = _Part(part, name, family)
    return parts


def _m21_pitch(name: str) -> pitch.Pitch:
    step, rest = name[0], name[1:]
    octave = rest.lstrip("#b-")
    accidental = rest[: len(rest) - len(octave)].replace("b", "-")
    return pitch.Pitch(f"{step}{accidental}{octave}")


def _attacks(measure: stream.Measure) -> list:
    return [n for n in measure.recurse().notes if not (n.tie and n.tie.type in ("stop", "continue"))]


def _rhythm(measure: stream.Measure) -> list[float]:
    return [round(float(n.getOffsetInHierarchy(measure)), 3) for n in _attacks(measure)]


def _similar(a: list[float], b: list[float]) -> bool:
    return len(set(a) & set(b)) >= 0.8 * max(len(a), len(b))


def _respell(p: pitch.Pitch, flat_key: bool) -> pitch.Pitch:
    if p.accidental is None or abs(p.alter) <= 2:
        return p
    q = p.simplifyEnharmonic(mostCommon=True)
    if flat_key and q.accidental is not None and q.accidental.name == "sharp":
        q = q.getHigherEnharmonic()
    return q


def _beat(signature: meter.TimeSignature | None) -> float:
    if signature is None:
        return 1.0
    if signature.denominator == 8 and signature.numerator % 3 == 0:
        return 1.5
    try:
        return float(signature.beatDuration.quarterLength)
    except meter.TimeSignatureException:
        return float(beat_length(signature.numerator, signature.denominator))


def _beam(voice: stream.Stream, beat: float) -> None:
    beat_of = lambda element: int(float(element.offset) / beat + 1e-6)
    with_tuplets = {beat_of(element) for element in voice.notesAndRests if element.duration.tuplets}
    groups: dict[tuple[int, ...], list] = {}
    for element in voice.notesAndRests:
        key = (beat_of(element), int(Fraction(element.offset) // _beam_span(element, beat))) if beat_of(element) in with_tuplets else (beat_of(element),)
        groups.setdefault(key, []).append(element)
    for group in groups.values():
        run = []
        for element in group + [None]:
            if element is not None and not element.isRest and element.duration.type in ("eighth", "16th", "32nd") and not element.beams.beamsList:
                run.append(element)
                continue
            if len(run) > 1:
                same = len({x.duration.type for x in run}) == 1
                for i, x in enumerate(run):
                    kind = "start" if i == 0 else "stop" if i == len(run) - 1 else "continue"
                    if same:
                        x.beams.fill(x.duration.type, type=kind)
                    else:
                        x.beams.append(kind)
            run = []


def _beam_span(element, beat: float) -> Fraction:
    written = element.duration
    group = Fraction(duration.convertTypeToQuarterLength(written.type)) * written.tuplets[0].numberNotesNormal if written.tuplets else 0
    pulse = Fraction(beat) if beat <= 1.5 else 1
    return max(group, pulse)


@dataclass(eq=False)
class _Note:

    start: float
    end: float
    pitch: pitch.Pitch
    line: str
    comes_in: bool
    goes_out: bool
    keep: bool = False
    hand: str = ""
    cut: float = 0.0
    pinned: bool = False
    names: list = field(default_factory=list)
    @property
    def ps(self) -> float:
        return self.pitch.ps


def _sounding(measure: stream.Measure, line: str) -> list[_Note]:
    found: list[_Note] = []
    for n in measure.recurse().notes:
        if n.duration.isGrace:
            continue
        start = opFrac(n.getOffsetInHierarchy(measure))
        end = opFrac(start + n.quarterLength)
        for p in n.pitches:
            kind = (n.getTie(p) if n.isChord else n.tie)
            kind = kind.type if kind else None
            before = next((f for f in found if f.ps == p.ps and f.end == start and f.goes_out), None)
            if before is not None and kind in ("stop", "continue"):
                before.end, before.goes_out = end, kind == "continue"
            else:
                found.append(_Note(start, end, copy.deepcopy(p), line, kind in ("stop", "continue"), kind in ("start", "continue"), names=[(line, p.ps)]))
    return found


def _merge_unisons(notes: list[_Note]) -> list[_Note]:
    result: list[_Note] = []
    for n in sorted(notes, key=lambda n: (n.start, -n.end)):
        held = next((m for m in result if m.ps == n.ps and m.start <= n.start < m.end), None)
        if held is None:
            result.append(n)
        elif held.start == n.start:
            held.goes_out = held.goes_out or (n.goes_out and n.end == held.end)
            held.keep, held.names = held.keep or n.keep, held.names + n.names
        else:
            if held.end >= n.end:
                n.goes_out = held.goes_out or (n.goes_out and held.end == n.end)
                n.end, n.names = held.end, n.names + held.names
            held.end, held.goes_out = n.start, False
            result.append(n)
    return result


def _thin(notes: list[_Note]) -> list[_Note]:
    lowest = {n.start: n for n in sorted(notes, key=lambda n: -n.ps)}
    kept = []
    for n in sorted(notes, key=lambda n: -n.ps):
        if n.pinned or n.keep or lowest[n.start] is n or not any(
            m.pitch.pitchClass == n.pitch.pitchClass and m.start == n.start and m.end == n.end for m in kept
        ):
            kept.append(n)
    return [n for n in notes if n in kept]


def _ties(notes: list[_Note]) -> int:
    edges = sorted({n.start for n in notes} | {n.end for n in notes})
    return sum(bisect_left(edges, n.end) - bisect_right(edges, n.start) for n in notes)


def _sounding_at(notes, t) -> list[float]:
    return [n.ps for n in notes if n.start <= t < n.end]


def _voices(notes: list[_Note], one: bool) -> tuple[float, list[list[_Note]]]:
    best = (float(_ties(notes)), [notes] if notes else [])
    if one:
        return best
    lines: dict[str, list[_Note]] = {}
    for n in notes:
        lines.setdefault(n.line, []).append(n)
    order = sorted(lines.values(), key=lambda line: sum(n.ps for n in line) / len(line))
    splits = [([n for line in order[:k] for n in line], [n for line in order[k:] for n in line]) for k in range(1, len(order))]
    edges = sorted({n.start for n in notes} | {n.end for n in notes})
    held = [n for n in notes if bisect_left(edges, n.end) > bisect_right(edges, n.start)]
    splits.append((held, [n for n in notes if n not in held]))
    for a, b in splits:
        if not a or not b:
            continue
        lower, upper = sorted((a, b), key=lambda v: sum(n.ps for n in v) / len(v))
        crossed = sum(
            1 for t in {n.start for n in notes}
            if (u := _sounding_at(upper, t)) and (d := _sounding_at(lower, t)) and min(u) < max(d)
        )
        cost = _ties(lower) + _ties(upper) + 0.5 + 2 * crossed
        if cost < best[0]:
            best = (cost, [upper, lower])
    return best


def _hands(notes: list[_Note], tune_at: Callable[[float], float | None], one_right: bool) -> None:
    base = [n.hand for n in notes]
    times = sorted({n.start for n in notes})
    chords: dict[str, dict[float, list[int]]] = {}
    for i, n in sorted(enumerate(notes), key=lambda item: item[1].start):
        chords.setdefault(n.line, {}).setdefault(n.start, []).append(i)

    def cost(hands: list[str]) -> float:
        right = [n for n, h in zip(notes, hands) if h == "R"]
        left = [n for n, h in zip(notes, hands) if h == "L"]
        total = _voices(right, one_right)[0] + _voices(left, False)[0]
        total += sum(0.25 + abs(n.ps - n.cut) / 12 for n, h, b in zip(notes, hands, base) if h != b)
        for attacks in chords.values():
            steps = list(attacks.values())
            for a, b in zip(steps, steps[1:]):
                if {hands[i] for i in a} != {hands[i] for i in b}:
                    total += 2 if max(notes[i].end for i in a) >= notes[b[0]].start else 1
        for t in times:
            r, l = _sounding_at(right, t), _sounding_at(left, t)
            top = tune_at(t)
            struck = [n.ps for n in left if n.start == t and not n.comes_in]
            if r and max(r + ([top] if top is not None else [])) - min(r) > SPAN:
                total += 10
            if r and l and max(l) > min(r):
                total += 10
            if struck and max(struck) - min(struck) > SPAN:
                total += 10
            total += max(len(r) + (top is not None) - 4, 0) + max(len(struck) - 4, 0)
        return total + 10 * sum(n.ps < LOWEST_RIGHT_HAND for n in right) + 2 * sum(n.ps > HIGHEST_LEFT_HAND for n in left)

    hands, current = base[:], cost(base)
    free = [i for i, n in enumerate(notes) if not n.pinned]
    for _ in range(len(notes)):
        options = [[("L" if h == "R" else "R") if j == i else h for j, h in enumerate(hands)] for i in free]
        for attacks in chords.values():
            steps = list(attacks.values())
            for k in range(len(steps)):
                for part in (steps[:k + 1], steps[k:]):
                    moved = {i for step in part for i in step if not notes[i].pinned}
                    for side in "RL":
                        options.append([side if j in moved else h for j, h in enumerate(hands)])
        scored = min(((cost(o), o) for o in options), key=lambda x: x[0], default=None)
        if scored is None or scored[0] >= current - 1e-9:
            break
        current, hands = scored
    for n, h in zip(notes, hands):
        n.hand = h


def _lengths(start: float, end: float, beat: float, length: float, note: bool = False) -> list[float]:
    pieces, t = [], start
    while t < end:
        if t == 0 and end == length and not note:
            size = length
        elif _on(t, beat) and t + beat <= end:
            whole = [beat * 2**k * dots for k in range(4) for dots in ((1, 1.5) if note else (1,))]
            size = max(s for s in whole if _on(t, s) and t + s <= end)
        else:
            limit = min(end, (t // beat + 1) * beat)
            sizes = _sizes(t, limit, beat, note)
            size = sizes[0] if sizes else limit - t
        pieces.append(opFrac(size))
        t = opFrac(t + size)
    return pieces


def _sizes(t: float, limit: float, beat: float, note: bool) -> list[float]:
    t = Fraction(t)
    within = t % Fraction(beat)
    for factor in (1, *TUPLETS):
        bound = limit if factor == 1 else min(limit, t // 1 + 1)
        smallest = Fraction(PLAIN[-1]) * factor
        if not (_on(t, smallest) and _on(bound, smallest)):
            continue
        units = [Fraction(s) * factor for s in PLAIN if Fraction(s) * factor < beat]
        dotted = (1.5, 1) if note and factor == 1 else (1,)
        sizes = [opFrac(unit * dots) for unit in units for dots in dotted]
        return [size for size in sizes if _on(within, size) and t + size <= bound]
    return []


def _on(time: float, grid: float) -> bool:
    return Fraction(time) % Fraction(grid) == 0


def _writable(start: float, end: float) -> bool:
    written = duration.Duration(opFrac(end - start))
    if written.type in ("inexpressible", "complex", "zero") or written.dots > 2:
        return False
    if not written.tuplets:
        return True
    group = Fraction(duration.convertTypeToQuarterLength(written.type)) * written.tuplets[0].numberNotesNormal
    one_group = Fraction(start) // group == math.ceil(Fraction(end) / group) - 1
    return one_group and all(Fraction(t.numberNotesNormal, t.numberNotesActual) in TUPLETS for t in written.tuplets)


def _note_spans(start: float, end: float, beat: float, length: float) -> list[tuple[float, float]]:
    cuts = [start]
    first = opFrac((start // beat + 1) * beat)
    if start % beat and first < end:
        cuts.append(first)
    last = opFrac(end // beat * beat)
    if beat == 1.5 and end % beat and cuts[-1] < last:
        cuts.append(last)
    spans = []
    for c, d in zip(cuts, cuts[1:] + [end]):
        sizes = [opFrac(d - c)] if _writable(c, d) else _lengths(c, d, beat, length, note=True)
        for size in sizes:
            spans.append((c, opFrac(c + size)))
            c = opFrac(c + size)
    return spans


def _voice(notes: list[_Note], length: float, beat: float, flat_key: bool) -> stream.Voice:
    voice = stream.Voice()
    times = sorted({0.0, length} | {n.start for n in notes} | {n.end for n in notes})
    for a, b in zip(times, times[1:]):
        here = [n for n in notes if n.start <= a and n.end >= b]
        if not here:
            _rests(voice, a, b, beat, length)
            continue
        here.sort(key=lambda n: n.ps)
        pitches = [_respell(n.pitch, flat_key) for n in here]
        for c, d in _note_spans(a, b, beat, length):
            element = chord.Chord(pitches, quarterLength=d - c) if len(pitches) > 1 else note.Note(pitches[0], quarterLength=d - c)
            for n, written in zip(here, element.notes if element.isChord else [element]):
                written.tie = _edge_tie(n.start < c or n.comes_in, n.end > d or n.goes_out)
            voice.insert(c, element)
    _beam(voice, beat)
    return voice


def _rests(voice: stream.Voice, start: float, end: float, beat: float, length: float) -> None:
    for size in _lengths(start, end, beat, length):
        voice.insert(start, note.Rest(quarterLength=size))
        start = opFrac(start + size)


def _staff(target: stream.Measure, voices: list[stream.Voice], length: float) -> None:
    if not voices:
        target.insert(0, note.Rest(quarterLength=length))
        return
    if len(voices) == 1:
        target.insert(0, voices[0])
        return
    upper, lower = voices
    last = max(e.offset for e in lower.notes)
    for voice, stem in ((upper, "up"), (lower, "down")):
        for element in voice.notesAndRests:
            if not element.isRest:
                element.stemDirection = stem
            elif voice is lower and (element.offset > last or not any(
                not e.isRest and e.offset < element.offset + element.quarterLength and element.offset < e.offset + e.quarterLength
                for e in upper.notesAndRests
            )):
                element.style.hideObjectOnPrint = True
        target.insert(0, voice)


def _reduce_bar(bar, parts, ref, context, number, kept, flat_key, previous_lead, first, carried):
    counts = {n: len(_attacks(m)) for n, m in bar.items()}
    playing = [n for n in bar if counts[n]]
    best = max(counts, key=lambda n: (counts[n], sum(p.ps for p in bar[n].pitches) / max(len(bar[n].pitches), 1)))
    if previous_lead in bar and counts[previous_lead] >= 0.6 * counts[best]:
        best = previous_lead
    group = [n for n in bar if counts[n] and _similar(_rhythm(bar[n]), _rhythm(bar[best]))]
    highest = max(playing, key=lambda n: max(p.ps for p in bar[n].pitches)) if playing else None
    others = [n for n in playing if n not in group]
    busiest = max([counts[n] for n in others] + [0])
    tune = (
        bool(others)
        and not BASS & {parts[n].family for n in group}
        and (counts[best] > busiest or (best == previous_lead and counts[best] >= 0.6 * busiest))
        and (highest in group or {parts[n].family for n in group}.isdisjoint(parts[n].family for n in others))
    )
    lead = best if tune else None
    melody = []
    for source_element in (bar[best].voices[0] if bar[best].voices else bar[best]).notesAndRests if tune else []:
        element = copy.deepcopy(source_element)
        element.offset = source_element.offset
        if element.isChord:
            top = max(element.pitches, key=lambda p: p.ps)
            single = note.Note(top, quarterLength=element.quarterLength)
            single.tie, single.beams = element.getTie(top), element.beams
            single.offset = element.offset
            element = single
        melody.append(element)
    sounding = [m for m in melody if not m.isRest and not m.duration.isGrace]

    def tune_at(time: float) -> float | None:
        return next((e.pitch.ps for e in sounding if e.offset <= time < e.offset + e.quarterLength), None)

    signature_key, signature_time, length = context
    in_tune = {(opFrac(e.offset), e.pitch.ps) for e in sounding}
    notes = [n for name in bar for n in _sounding(bar[name], name) if not (name == best and (n.start, n.ps) in in_tune)]
    doubled = {(opFrac(e.offset), e.pitch.pitchClass) for e in sounding}
    notes = [n for n in notes if not (tune and n.line in group and not n.comes_in and (n.start, n.pitch.pitchClass) in doubled)]
    marked = {(opFrac(offset), p.ps) for offset, p, _ in kept}
    for n in notes:
        n.keep = (n.start, n.ps) in marked
    for offset, p, span in kept:
        if (opFrac(offset), p.ps) not in in_tune and not any(n.keep and n.start == opFrac(offset) and n.ps == p.ps for n in notes):
            notes.append(_Note(opFrac(offset), opFrac(min(offset + span, length)), copy.deepcopy(p), "marked", False, False, keep=True))

    lost = []
    for n in notes:
        before = next((carried[name] for name in n.names if name in carried), None) if n.comes_in else None
        if before is not None and not before[2]:
            lost.append(n)
        elif before is not None:
            n.pitch.octave += round((before[0] - n.ps) / 12)
            n.hand, n.pinned = before[1], True
        if not n.pinned and not n.keep:
            ceiling = min((e.pitch.ps for e in sounding if e.offset < n.end and n.start < e.offset + e.quarterLength), default=None)
            while ceiling is not None and n.ps >= ceiling:
                n.pitch.octave -= 1
    notes = _merge_unisons([n for n in notes if n not in lost])
    for n in notes:
        if not n.pinned:
            ceiling = tune_at(n.start)
            height = max(_sounding_at(notes, n.start))
            n.cut = max((ceiling if ceiling is not None else height) - 12, LOWEST_RIGHT_HAND)
            n.hand = "R" if n.ps >= n.cut else "L"
    written = _thin([n for n in notes if n.hand == "R"]) + _thin([n for n in notes if n.hand == "L"])
    _hands(written, tune_at, tune)
    written = _thin([n for n in written if n.hand == "R"]) + _thin([n for n in written if n.hand == "L"])

    beat = _beat(signature_time)
    right, left = stream.Measure(number=number), stream.Measure(number=number)
    for hand in (right, left):
        hand.paddingLeft, hand.paddingRight = ref.paddingLeft, ref.paddingRight
    upper = stream.Voice()
    staves = {}
    for hand in "RL":
        _, groups = _voices([n for n in written if n.hand == hand], hand == "R" and tune)
        staves[hand] = [_voice(g, length, beat, flat_key) for g in groups]
    if tune:
        for element in melody:
            upper.insert(element.offset, element)
        _rests(upper, opFrac(upper.highestTime), length, beat, length)
        staves["R"] = [upper] + staves["R"]
    _staff(right, staves["R"], length)
    _staff(left, staves["L"], length)
    carry = {}
    for n in notes + lost:
        if n.goes_out:
            for name in n.names:
                carry[name] = (n.ps, n.hand, n in written)
    if sounding and sounding[-1].tie and sounding[-1].tie.type in ("start", "continue"):
        carry[(best, sounding[-1].pitch.ps)] = (sounding[-1].pitch.ps, "R", True)

    source = bar[best] if playing else ref
    carrier = upper if tune else right
    for mark in source.recurse().getElementsByClass(dynamics.Dynamic):
        carrier.insert(mark.getOffsetInHierarchy(source), copy.deepcopy(mark))
    signatures = [ref.keySignature, ref.timeSignature]
    if first:
        right.insert(0, clef.TrebleClef())
        left.insert(0, clef.BassClef())
        signatures = [signature_key, signature_time]
    for m in (right, left):
        for found in signatures:
            if found is not None:
                m.insert(0, copy.deepcopy(found))
    return right, left, lead, carry
