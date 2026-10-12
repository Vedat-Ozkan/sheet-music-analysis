"""Reduce an ensemble score to two piano staves, the way published reductions do (Goetschius,
"Analytic Symphony Series", Ditson 1928): the tune as the top voice, the harmony under it, held chords
as one long note, and an abbreviated instrument cue where the tune changes hands.

The analysis is made on the original score; the reduction is only a clearer view of it. Notes the
analysis points at are always kept, at the same bar, beat and pitch, so its marks find them again.
"""

from __future__ import annotations

import copy
import os
import tempfile
from collections.abc import Iterable
from fractions import Fraction

from music21 import chord, clef, tie, converter, dynamics, expressions, instrument, key, layout, meter, note, pitch, stream
from music21.musicxml.m21ToXml import GeneralObjectExporter

# Standard score abbreviations, by music21 instrument class.
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
LOWEST_RIGHT_HAND = 55  # G3: harmony below this goes to the left hand


def reduce(score: bytes, measures: tuple[int, int] | None, keep: Iterable[tuple[int, Fraction, str, Fraction]] = ()) -> bytes:
    """MusicXML for a two-staff piano version of `measures` (printed numbers, inclusive).

    `keep` lists notes that must survive as (measure, quarter notes from the bar start, sounding pitch
    like "Eb4", length in quarter notes); everything else may be thinned, merged or moved an octave."""
    parts = _parts(score, measures)
    kept: dict[int, list[tuple[float, pitch.Pitch, float]]] = {}
    for number, offset, name, length in keep:
        kept.setdefault(number, []).append((float(offset), _m21_pitch(name), float(length)))
    reference = next((p for p in parts.values() if p.family in STRINGS), next(iter(parts.values())))
    signature = reference.measures[0].keySignature or reference.measures[0].getContextByClass(key.KeySignature)
    flat_key = signature is not None and signature.sharps < 0
    right_hand, left_hand = stream.Part(), stream.Part()
    previous_cue = previous_lead = None
    for number, ref in enumerate(reference.measures):
        bar = {name: part.measures[number] for name, part in parts.items()}
        right, left, previous_cue, previous_lead = _reduce_bar(
            bar, parts, ref, kept.get(ref.number, []), flat_key, previous_cue, previous_lead, first=number == 0
        )
        right_hand.append(right)
        left_hand.append(left)
    out = stream.Score([right_hand, left_hand])
    out.insert(0, layout.StaffGroup([right_hand, left_hand], symbol="brace", name="Piano"))
    return GeneralObjectExporter(out).parse()


class _Part:
    def __init__(self, part: stream.Part, name: str, family: str, abbreviation: str, number: str):
        self.measures = list(part.getElementsByClass(stream.Measure))
        self.name, self.family, self.abbreviation, self.number = name, family, abbreviation, number


def _family(part: stream.Part, inst: instrument.Instrument) -> str:
    """The music21 instrument class name; files often give strings only a generic class and a name like "Violins"."""
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
    """The pitched parts that play in `measures`, at sounding pitch, with their instrument family and cue name."""
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
        # Two parts of one instrument are told apart in the cue: Vl. I and Vl. II.
        number = ""
        if families.count(family) > 1:
            seen[family] = seen.get(family, 0) + 1
            number = " " + ["I", "II", "III", "IV"][min(seen[family], 4) - 1]
        parts[name] = _Part(part, name, family, abbreviation, number)
    return parts


def _m21_pitch(name: str) -> pitch.Pitch:
    """A pitch written the annotation way ("Eb4", "F#5") or music21's ("E-4")."""
    step, rest = name[0], name[1:]
    octave = rest.lstrip("#b-")
    accidental = rest[: len(rest) - len(octave)].replace("b", "-")
    return pitch.Pitch(f"{step}{accidental}{octave}")


def _attacks(measure: stream.Measure) -> list:
    return [n for n in measure.recurse().notes if not (n.tie and n.tie.type in ("stop", "continue"))]


def _rhythm(measure: stream.Measure) -> list[float]:
    return [round(float(n.getOffsetInHierarchy(measure)), 3) for n in _attacks(measure)]


def _similar(a: list[float], b: list[float]) -> bool:
    """Two rhythms that share most of their attacks: lines doubling each other, give or take an ornament."""
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
        # All the parts of an instrument playing together are named once: "Ob.", not "Ob. I, Ob. II".
        if len(members) == len(everyone):
            cues.append(parts[members[0]].abbreviation)
        else:
            cues += [parts[n].abbreviation + parts[n].number for n in members]
    return ", ".join(cues)


def _thin(pitches: list, keep: set[float], most: int = 4) -> list:
    """At most `most` notes, the outer two first, then one of each pitch class; kept notes always stay."""
    pitches = sorted({p.ps: p for p in pitches}.values(), key=lambda p: p.ps)
    if len(pitches) <= 2:
        return pitches
    chosen = [pitches[0], pitches[-1]] + [p for p in pitches[1:-1] if p.ps in keep]
    for p in reversed(pitches[1:-1]):
        if len(chosen) < most and p not in chosen and p.pitchClass not in {k.pitchClass for k in chosen}:
            chosen.append(p)
    return sorted(chosen, key=lambda p: p.ps)


def _respell(p: pitch.Pitch, flat_key: bool) -> pitch.Pitch:
    """Sounding pitch from some horn transpositions comes out as B triple-flat and the like."""
    if p.accidental is None or abs(p.alter) <= 2:
        return p
    q = p.simplifyEnharmonic(mostCommon=True)
    if flat_key and q.accidental is not None and q.accidental.name == "sharp":
        q = q.getHigherEnharmonic()
    return q


def _blocks(events: list) -> list:
    """Held chords as one long note instead of a chain of ties: an event joins the one before when it has
    the same notes, all tied over. Any change of notes strikes a new chord, so every harmony is on the page."""
    result = []
    for offset, length, pitches, tied, beams in events:
        if result:
            last = result[-1]
            same = [p.ps for p in pitches] == [p.ps for p in last[2]]
            held = all(last[3].get(p.ps) is not None and last[3][p.ps].type in ("start", "continue") for p in last[2])
            if same and (not pitches or held):
                last[1] += length
                last[4] = None  # a merged note no longer belongs to the beam it started in
                # The joined note comes in the way its first part did and goes out the way its last part does.
                last[3] = {
                    ps: _edge_tie(_kind(last[3], ps) in ("stop", "continue"), _kind(tied, ps) in ("start", "continue"))
                    for ps in tied
                }
                continue
        result.append([offset, length, pitches, dict(tied), beams])
    return result


def _beat(ref: stream.Measure) -> float:
    """Length in quarter notes of one beam group: a dotted quarter in compound meters, else the beat."""
    signature = ref.timeSignature or ref.getContextByClass(meter.TimeSignature)
    if signature is None:
        return 1.0
    if signature.denominator == 8 and signature.numerator % 3 == 0:
        return 1.5
    return float(signature.beatDuration.quarterLength)


def _split_runs(events: list) -> tuple[list, list]:
    """The lowest notes that keep sounding while the notes above them change are written once, as a voice of their
    own, the way published reductions do, instead of being tied through every chord. Returns the events without
    those notes and the held notes as events."""
    runs, i = [], 0
    while i < len(events):
        found = None
        for count in range(len(events[i][2]), 0, -1):
            bass = [p.ps for p in events[i][2][:count]]
            j = i
            while (
                j + 1 < len(events)
                and all(_kind(events[j][3], ps) in ("start", "continue") for ps in bass)
                and [p.ps for p in events[j + 1][2][:count]] == bass
            ):
                j += 1
            above = {tuple(p.ps for p in e[2][count:]) for e in events[i : j + 1]}
            # Notes above that are the same and tied all the way through are already one block (see _blocks).
            struck_again = any(_kind(e[3], p.ps) not in ("stop", "continue") for e in events[i + 1 : j + 1] for p in e[2][count:])
            # Under two quarter notes a separate voice costs more clarity than the tie does.
            long_enough = sum(e[1] for e in events[i : j + 1]) >= 2
            if j > i and long_enough and (len(above) > 1 or struck_again):
                found = (i, j, count)
                break
        if found:
            runs.append(found)
        i = found[1] + 1 if found else i + 1
    held = []
    for i, j, count in runs:
        first, last = events[i], events[j]
        bass = first[2][:count]
        # The ends of the tie belong to the neighbouring bars, so the held notes keep them.
        ties = {
            p.ps: _edge_tie(_kind(first[3], p.ps) in ("stop", "continue"), _kind(last[3], p.ps) in ("start", "continue"))
            for p in bass
        }
        held.append((first[0], sum(e[1] for e in events[i : j + 1]), bass, ties, None))
        for k in range(i, j + 1):
            e = events[k]
            events[k] = (e[0], e[1], e[2][count:], {ps: t for ps, t in e[3].items() if ps not in ties}, e[4])
    return events, held


def _split_held(events: list) -> tuple[list, list, str]:
    """_split_runs on the bottom notes of each chord, else on the top notes (a held top note under a moving bass).
    The third value is the stem direction of the held voice."""
    for top in (False, True):
        flipped = [(o, n, p[::-1] if top else p, t, b) for o, n, p, t, b in events]
        rest, held = _split_runs(flipped)
        if held:
            order = (lambda p: p[::-1]) if top else (lambda p: p)
            return [(o, n, order(p), t, b) for o, n, p, t, b in rest], [(o, n, order(p), t, b) for o, n, p, t, b in held], "up" if top else "down"
    return events, [], "down"


def _fill(events: list, held: list, direction: str, target: stream.Stream, flat_key: bool, beat: float, length: float) -> None:
    """Write a hand's events into `target`; held notes get a voice of their own, stems down, the rest stems up."""
    voices = [(events, stream.Voice() if held else target)] + ([(held, stream.Voice())] if held else [])
    for group, voice in voices:
        for offset, span, pitches, tied, beams in _blocks(group) if group is events else group:
            voice.insert(offset, _make(pitches, span, tied, beams, flat_key))
        _beam(voice, beat)
    if held:
        stems = ("down", "up") if direction == "up" else ("up", "down")
        for (group, voice), stem in zip(voices, stems):
            voice.makeRests(fillGaps=True, inPlace=True, timeRangeFromBarDuration=False)
            for element in voice.notesAndRests:
                if element.isRest and group is held:
                    element.style.hideObjectOnPrint = True
                elif not element.isRest:
                    element.stemDirection = stem
            target.insert(0, voice)
    if not target.recurse().notesAndRests:
        target.insert(0, note.Rest(quarterLength=length))


def _kind(ties: dict, ps: float):
    return ties[ps].type if ties.get(ps) is not None else None


def _edge_tie(comes_in: bool, goes_out: bool):
    if comes_in and goes_out:
        return tie.Tie("continue")
    return tie.Tie("stop") if comes_in else tie.Tie("start") if goes_out else None


def _beam(voice: stream.Stream, beat: float) -> None:
    """Beam the short notes in each beat group of the meter (a dotted quarter in 6/8, 9/8, 12/8); chords built here
    have no beams of their own."""
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


def _real_ties(chords: stream.Measure, sources: list) -> list[dict]:
    """The tie type of each pitch of each chord. chordify ties a pitch into the next chord whenever it recurs,
    even where the instrument struck it again; a tie is kept only where one written note sounds across the change."""
    spans = sorted(
        (float(n.getOffsetInHierarchy(m)), float(n.getOffsetInHierarchy(m) + n.quarterLength), p.ps,
         (n.getTie(p) if n.isChord else n.tie) is not None and (n.getTie(p) if n.isChord else n.tie).type in ("stop", "continue"))
        for m in sources for n in m.recurse().notes for p in n.pitches
    )
    # A note tied to the next one in the same part is one sounding.
    merged: list[list] = []
    for start, end, ps, continues in spans:
        for span in merged:
            if continues and span[2] == ps and abs(span[1] - start) < 1e-6:
                span[1] = end
                break
        else:
            merged.append([start, end, ps])
    result = []
    for c in chords.notesAndRests:
        result.append({} if c.isRest else {p.ps: (c.getTie(p).type if c.getTie(p) else None) for p in c.pitches})
    events = list(chords.notesAndRests)
    for i in range(len(events) - 1):
        boundary = float(events[i + 1].offset)
        for ps, kind in result[i].items():
            if kind in ("start", "continue") and not any(
                s < boundary - 1e-6 and e > boundary + 1e-6 and q == ps for s, e, q in merged
            ):
                result[i][ps] = None if kind == "start" else "stop"
                after = result[i + 1].get(ps)
                if after is not None:
                    result[i + 1][ps] = None if after == "stop" else "start"
    return result


def _make(pitches: list, length: float, tied: dict, beams, flat_key: bool):
    pitches = [_respell(p, flat_key) for p in pitches]
    if not pitches:
        return note.Rest(quarterLength=length)
    element = chord.Chord(pitches, quarterLength=length) if len(pitches) > 1 else note.Note(pitches[0], quarterLength=length)
    for n in element.notes if element.isChord else [element]:
        n.tie = tied.get(n.pitch.ps)
    if beams is not None:
        element.beams = copy.deepcopy(beams)
    return element


def _reduce_bar(bar, parts, ref, kept, flat_key, previous_cue, previous_lead, first):
    counts = {n: len(_attacks(m)) for n, m in bar.items()}
    playing = [n for n in bar if counts[n]]
    best = max(counts, key=lambda n: (counts[n], sum(p.ps for p in bar[n].pitches) / max(len(bar[n].pitches), 1)))
    # The tune stays with the instrument that had it while that instrument is still busy.
    if previous_lead in bar and counts[previous_lead] >= 0.6 * counts[best]:
        best = previous_lead
    group = [n for n in bar if counts[n] and _similar(_rhythm(bar[n]), _rhythm(bar[best]))]
    highest = max(playing, key=lambda n: max(p.ps for p in bar[n].pitches)) if playing else None
    # A tune moves more than everything else and stands out: it is the top line, or another family than
    # the accompaniment. Otherwise (a tutti unison, a string chorale) the bar is set as chords.
    others = [n for n in playing if n not in group]
    busiest = max([counts[n] for n in others] + [0])
    tune = (
        bool(others)
        and not BASS & {parts[n].family for n in group}  # a unison reaching the bass is the whole orchestra, not a tune
        and (counts[best] > busiest or (best == previous_lead and counts[best] >= 0.6 * busiest))
        and (highest in group or {parts[n].family for n in group}.isdisjoint(parts[n].family for n in others))
    )
    lead = best if tune else None
    label = _cue(group if tune else playing, parts) if playing else None
    accompaniment = [n for n in bar if n not in group] if tune else list(bar)
    melody = []
    for source_element in bar[best].notesAndRests if tune else []:
        element = copy.deepcopy(source_element)
        # deepcopy detaches the note from its bar and resets its offset to 0; the tune needs its place in the bar.
        element.offset = source_element.offset
        if element.isChord:
            top = max(element.pitches, key=lambda p: p.ps)
            single = note.Note(top, quarterLength=element.quarterLength)
            single.tie = element.getTie(top)
            single.offset = element.offset
            element = single
        melody.append(element)
    # Notes the analysis marks go into the harmony unless the tune has them, so a chord is struck at
    # each one even when the accompaniment does not move there (a doubling, an inner voice, an ornament).
    in_tune = {(round(float(e.offset), 4), e.pitch.ps) for e in melody if not e.isRest}
    marked = stream.Measure()
    for offset, p, length in kept:
        if (round(offset, 4), p.ps) not in in_tune:
            marked.insert(offset, note.Note(copy.deepcopy(p), quarterLength=min(length, ref.duration.quarterLength - offset)))
    sources = [copy.deepcopy(bar[n]) for n in accompaniment] + ([marked] if marked.notes else [])
    chords = stream.Score([stream.Part([m]) for m in sources]).chordify()
    chords = chords.getElementsByClass(stream.Measure)[0] if sources else stream.Measure()

    def tune_at(time: float) -> float | None:
        for element in melody:
            if element.offset <= time < element.offset + element.quarterLength and not element.isRest:
                return element.pitch.ps
        return None

    ties = _real_ties(chords, sources)
    right, left = stream.Measure(number=ref.number), stream.Measure(number=ref.number)
    upper, lower = stream.Voice(), stream.Voice()
    right_events, left_events = [], []
    for index, c in enumerate(chords.notesAndRests):
        pitches = [] if c.isRest else list(c.pitches)
        tied = {} if c.isRest else {ps: tie.Tie(kind) if kind else None for ps, kind in ties[index].items()}
        start = float(c.offset)
        ceiling = tune_at(start)
        keep = {p.ps for offset, p, _ in kept if abs(offset - start) < 1e-6}
        if ceiling is not None:
            # Harmony that sounds above the tune is set an octave or two lower, as a pianist would play it.
            moved = []
            for p in pitches:
                q = copy.deepcopy(p)
                while q.ps >= ceiling and q.ps not in keep:
                    q.octave -= 1
                tied[q.ps] = tied.get(p.ps)
                moved.append(q)
            pitches = moved
        height = max([p.ps for p in pitches] + [0])
        cut = max((ceiling - 12) if ceiling is not None else (height - 12), LOWEST_RIGHT_HAND)
        hand_right = _thin([p for p in pitches if p.ps >= cut], keep, 3 if ceiling else 4)
        hand_left = _thin([p for p in pitches if p.ps not in {q.ps for q in hand_right} and p.ps < cut], keep)
        beams = None if c.isRest else c.beams
        right_events.append((c.offset, c.quarterLength, hand_right, tied, beams))
        left_events.append((c.offset, c.quarterLength, hand_left, tied, beams))
    beat = _beat(ref)
    held_right, side_right = [], "down"
    if not tune:
        right_events, held_right, side_right = _split_held(right_events)
    left_events, held_left, side_left = _split_held(left_events)
    length = ref.duration.quarterLength
    _fill(right_events, held_right, side_right, lower if tune else right, flat_key, beat, length)
    _fill(left_events, held_left, side_left, left, flat_key, beat, length)
    if tune:
        for element in melody:
            upper.insert(element.offset, element)
        for element in upper.notes:
            element.stemDirection = "up"
        for element in lower.notes:
            element.stemDirection = "down"
        right.insert(0, upper)
        right.insert(0, lower)
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
    if first:
        right.insert(0, clef.TrebleClef())
        left.insert(0, clef.BassClef())
        # A bar cut out of the score answers for its own signatures; the context search does not find them.
        signatures = [ref.keySignature or ref.getContextByClass(key.KeySignature), ref.timeSignature or ref.getContextByClass(meter.TimeSignature)]
        for m in (right, left):
            for found in signatures:
                if found is not None:
                    m.insert(0, copy.deepcopy(found))
    return right, left, previous_cue, lead
