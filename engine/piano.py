from __future__ import annotations

import copy
import os
import tempfile
from bisect import bisect_left, bisect_right
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from fractions import Fraction

from music21 import chord, clef, tie, converter, dynamics, expressions, instrument, key, layout, meter, note, pitch, stream
from music21.common.numberTools import opFrac
from music21.musicxml.m21ToXml import GeneralObjectExporter

ABBREVIATIONS = {
    "Piccolo": "Picc.", "Flute": "Fl.", "Oboe": "Ob.", "EnglishHorn": "Cor. ingl.", "Clarinet": "Cl.",
    "BassClarinet": "Cl. b.", "Bassoon": "Fg.", "Contrabassoon": "Cfg.", "Horn": "Cor.", "Trumpet": "Tr.",
    "Trombone": "Trb.", "BassTrombone": "Trb.", "Tuba": "Tuba", "Timpani": "Timp.", "Harp": "Arpa",
    "Violin": "Vl.", "Viola": "Vla.", "Violoncello": "Vc.", "Contrabass": "Cb.",
    "SopranoSaxophone": "S. Sax.", "AltoSaxophone": "A. Sax.", "TenorSaxophone": "T. Sax.", "BaritoneSaxophone": "Bar. Sax.",
    "Euphonium": "Euph.", "Piano": "Pno.", "Organ": "Org.",
}
STRINGS = {"Violin", "Viola", "Violoncello", "Contrabass"}
BASS = {"Violoncello", "Contrabass", "Bassoon", "Contrabassoon", "Tuba", "Trombone", "BassTrombone", "BassClarinet", "BaritoneSaxophone"}
LOWEST_RIGHT_HAND = 55
SPAN = 14
HIGHEST_LEFT_HAND = 64

def reduce(score: bytes, measures: tuple[int, int] | None, keep: Iterable[tuple[int, Fraction, str, Fraction]] = ()) -> bytes:
    parts = _parts(score, measures)
    kept: dict[int, list[tuple[float, pitch.Pitch, float]]] = {}
    for number, offset, name, length in keep:
        kept.setdefault(number, []).append((float(offset), _m21_pitch(name), float(length)))
    reference = next((p for p in parts.values() if p.family in STRINGS), next(iter(parts.values())))
    signature = reference.measures[0].keySignature or reference.measures[0].getContextByClass(key.KeySignature)
    flat_key = signature is not None and signature.sharps < 0
    right_hand, left_hand = stream.Part(), stream.Part()
    previous_cue = previous_lead = None
    carried: dict = {}
    for number, ref in enumerate(reference.measures):
        bar = {name: part.measures[number] for name, part in parts.items()}
        right, left, previous_cue, previous_lead, carried = _reduce_bar(
            bar, parts, ref, kept.get(ref.number, []), flat_key, previous_cue, previous_lead, number == 0, carried
        )
        right_hand.append(right)
        left_hand.append(left)
    for hand in (right_hand, left_hand):
        _pair_ties(hand)
    out = stream.Score([right_hand, left_hand])
    out.insert(0, layout.StaffGroup([right_hand, left_hand], symbol="brace", name="Piano"))
    return GeneralObjectExporter(out).parse()


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
    def __init__(self, part: stream.Part, name: str, family: str, abbreviation: str, number: str):
        self.measures = list(part.getElementsByClass(stream.Measure))
        self.name, self.family, self.abbreviation, self.number = name, family, abbreviation, number


def _family(part: stream.Part, inst: instrument.Instrument) -> str:
    family = type(inst).__name__
    if family in ABBREVIATIONS:
        return family
    for name in (inst.instrumentName, part.partName):
        try:
            return type(instrument.fromString(name)).__name__ if name else family
        except instrument.InstrumentException:
            continue
    return family


def _parts(score: bytes, measures: tuple[int, int] | None) -> dict[str, _Part]:
    suffix = ".mxl" if score[:2] == b"PK" else ".musicxml"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as file:
        file.write(score)
    try:
        parsed = converter.parse(file.name, format="musicxml")
    finally:
        os.unlink(file.name)
    excerpt = parsed.measures(*measures) if measures else parsed
    excerpt = excerpt.toSoundingPitch()
    found = [(part, part.getInstrument()) for part in excerpt.parts if part.flatten().pitches]
    families = [_family(part, inst) for part, inst in found]
    parts, seen = {}, {}
    for (part, inst), family in zip(found, families):
        if isinstance(inst, instrument.UnpitchedPercussion):
            continue
        name = part.id or str(len(parts))
        abbreviation = ABBREVIATIONS.get(family) or inst.instrumentAbbreviation or part.partName or "Instr."
        number = ""
        if families.count(family) > 1:
            seen[family] = seen.get(family, 0) + 1
            number = " " + ["I", "II", "III", "IV"][min(seen[family], 4) - 1]
        parts[name] = _Part(part, name, family, abbreviation, number)
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


def _cue(names: list[str], parts: dict[str, _Part]) -> str:
    families = {parts[n].family for n in names} - {"Timpani"}
    if families & STRINGS and families - STRINGS:
        return "Tutti"
    if families <= STRINGS and len(families) > 1:
        return "Str."
    cues = []
    for family in dict.fromkeys(parts[n].family for n in names if parts[n].family != "Timpani"):
        members = [n for n in names if parts[n].family == family]
        everyone = [n for n in parts if parts[n].family == family]
        if len(members) == len(everyone):
            cues.append(parts[members[0]].abbreviation)
        else:
            cues += [parts[n].abbreviation + parts[n].number for n in members]
    return ", ".join(cues)


def _respell(p: pitch.Pitch, flat_key: bool) -> pitch.Pitch:
    if p.accidental is None or abs(p.alter) <= 2:
        return p
    q = p.simplifyEnharmonic(mostCommon=True)
    if flat_key and q.accidental is not None and q.accidental.name == "sharp":
        q = q.getHigherEnharmonic()
    return q


def _beat(ref: stream.Measure) -> float:
    signature = ref.timeSignature or ref.getContextByClass(meter.TimeSignature)
    if signature is None:
        return 1.0
    if signature.denominator == 8 and signature.numerator % 3 == 0:
        return 1.5
    return float(signature.beatDuration.quarterLength)


def _beam(voice: stream.Stream, beat: float) -> None:
    groups: dict[int, list] = {}
    for element in voice.notesAndRests:
        groups.setdefault(int(float(element.offset) / beat + 1e-6), []).append(element)
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


def _rest_lengths(start: float, end: float, beat: float, length: float) -> list[float]:
    pieces, t = [], start
    while t < end:
        if t == 0 and end == length:
            size = length
        elif t % beat == 0 and t + beat <= end:
            size = max(s for s in (beat * 2**k for k in range(4)) if t % s == 0 and t + s <= end)
        else:
            limit = min(end, (t // beat + 1) * beat)
            within = t - (t // beat) * beat
            sizes = [s for s in (1.0, 0.5, 0.25, 0.125, 0.0625) if s < beat and within % s == 0 and t + s <= limit]
            size = sizes[0] if sizes else limit - t
        pieces.append(opFrac(size))
        t = opFrac(t + size)
    return pieces


def _note_spans(start: float, end: float, beat: float) -> list[tuple[float, float]]:
    cuts = [start]
    first = opFrac((start // beat + 1) * beat)
    if start % beat and first < end:
        cuts.append(first)
    last = opFrac(end // beat * beat)
    if beat == 1.5 and end % beat and cuts[-1] < last:
        cuts.append(last)
    return list(zip(cuts, cuts[1:] + [end]))


def _voice(notes: list[_Note], length: float, beat: float, flat_key: bool) -> stream.Voice:
    voice = stream.Voice()
    times = sorted({0.0, length} | {n.start for n in notes} | {n.end for n in notes})
    for a, b in zip(times, times[1:]):
        here = [n for n in notes if n.start <= a and n.end >= b]
        if not here:
            t = a
            for size in _rest_lengths(a, b, beat, length):
                voice.insert(t, note.Rest(quarterLength=size))
                t = opFrac(t + size)
            continue
        here.sort(key=lambda n: n.ps)
        pitches = [_respell(n.pitch, flat_key) for n in here]
        for c, d in _note_spans(a, b, beat):
            element = chord.Chord(pitches, quarterLength=d - c) if len(pitches) > 1 else note.Note(pitches[0], quarterLength=d - c)
            for n, written in zip(here, element.notes if element.isChord else [element]):
                written.tie = _edge_tie(n.start < c or n.comes_in, n.end > d or n.goes_out)
            voice.insert(c, element)
    _beam(voice, beat)
    return voice


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


def _reduce_bar(bar, parts, ref, kept, flat_key, previous_cue, previous_lead, first, carried):
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
    label = _cue(group if tune else playing, parts) if playing else None
    melody = []
    for source_element in (bar[best].voices[0] if bar[best].voices else bar[best]).notesAndRests if tune else []:
        element = copy.deepcopy(source_element)
        element.offset = source_element.offset
        if element.isChord:
            top = max(element.pitches, key=lambda p: p.ps)
            single = note.Note(top, quarterLength=element.quarterLength)
            single.tie = element.getTie(top)
            single.offset = element.offset
            element = single
        melody.append(element)
    sounding = [m for m in melody if not m.isRest and not m.duration.isGrace]

    def tune_at(time: float) -> float | None:
        return next((e.pitch.ps for e in sounding if e.offset <= time < e.offset + e.quarterLength), None)

    length = opFrac(ref.duration.quarterLength)
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

    beat = _beat(ref)
    right, left = stream.Measure(number=ref.number), stream.Measure(number=ref.number)
    upper = stream.Voice()
    staves = {}
    for hand in "RL":
        _, groups = _voices([n for n in written if n.hand == hand], hand == "R" and tune)
        staves[hand] = [_voice(g, length, beat, flat_key) for g in groups]
    if tune:
        for element in melody:
            upper.insert(element.offset, element)
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
    if label and label != previous_cue:
        text = expressions.TextExpression(label)
        text.style.fontStyle = "italic"
        text.placement = "above"
        entry = next((e.offset for e in melody if not e.isRest), 0) if tune else 0
        carrier.insert(entry, text)
        previous_cue = label
    signatures = [ref.keySignature, ref.timeSignature]
    if first:
        right.insert(0, clef.TrebleClef())
        left.insert(0, clef.BassClef())
        signatures = [ref.keySignature or ref.getContextByClass(key.KeySignature), ref.timeSignature or ref.getContextByClass(meter.TimeSignature)]
    for m in (right, left):
        for found in signatures:
            if found is not None:
                m.insert(0, copy.deepcopy(found))
    return right, left, previous_cue, lead, carry
