from __future__ import annotations

import json
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations

from engine import harmony
from engine.reduce import midi
from engine.score import ScoreIndex

Voice = tuple[int, int]
RANGES = (("C4", "G5"), ("G3", "D5"), ("C3", "G4"), ("F2", "D4"))
LABELS = {"parallel_fifths": "P5", "parallel_octaves": "P8", "direct_fifths": "H5", "direct_octaves": "H8",
          "voice_crossing": "VC", "voice_overlap": "VO", "spacing": "S", "range": "r",
          "doubled_leading_tone": "D", "unresolved_seventh": "R", "unresolved_leading_tone": "R"}
LINES = {"parallel_fifths", "parallel_octaves", "direct_fifths", "direct_octaves"}
ARROWS = {"unresolved_seventh", "unresolved_leading_tone"}
BRACKETS = {"spacing"}

def _names(voices):
    if len(voices) == 4:
        return dict(zip(voices, ("soprano", "alto", "tenor", "bass")))
    names = {v: f"voice {i + 1}" for i, v in enumerate(voices)}
    names[voices[0]], names[voices[-1]] = "soprano", "bass"
    return names


@dataclass
class Finding:
    bars: tuple[int, ...]
    beats: tuple[float, ...]
    voices: tuple[Voice, ...]
    rule: str
    why: str


@dataclass
class _Table:
    voices: list[Voice]
    notes: dict[Voice, list]
    rows: list
    times: list[Fraction]

    def at(self, t):
        i = bisect_right(self.times, t) - 1
        return self.rows[i][1] if i >= 0 else {v: [] for v in self.voices}

    def just_before(self, t):
        i = bisect_left(self.times, t) - 1
        return self.rows[i][1] if i >= 0 else {v: [] for v in self.voices}


def _table(index, voices):
    notes, offset = {v: [] for v in voices}, Fraction(0)
    positions = {}
    for m in index.measures:
        positions[offset] = (m.number, 1.0)
        for e in m.events:
            if e.grace or e.duration <= 0:
                continue
            positions[offset + e.onset] = (m.number, m.beat_of(e.onset))
            end = e.onset + e.duration
            if end < m.length:
                positions[offset + end] = (m.number, m.beat_of(end))
            if e.pitch:
                t = offset + e.onset
                notes[e.staff, e.layer].append((t, t + e.duration, e))
        offset += m.length
    by_start = {v: sorted(range(len(notes[v])), key=lambda i: notes[v][i][0]) for v in voices}
    taken, sounding = dict.fromkeys(voices, 0), {v: [] for v in voices}
    times = sorted(positions)
    rows = []
    for t in times:
        for v in voices:
            line, order = notes[v], by_start[v]
            while taken[v] < len(order) and line[order[taken[v]]][0] <= t:
                sounding[v].append(order[taken[v]])
                taken[v] += 1
            sounding[v] = [i for i in sounding[v] if line[i][1] > t]
        rows.append((positions[t], {v: [notes[v][i][2] for i in sorted(sounding[v])] for v in voices}))
    return _Table(voices, notes, rows, times)


def _chorale(index: ScoreIndex) -> _Table | None:
    voices = sorted({(e.staff, e.layer) for m in index.measures for e in m.events if e.pitch and not e.grace})
    if not 2 <= len(voices) <= 4 or len({e.staff for m in index.measures for e in m.events}) > 4:
        return None
    table = _table(index, voices)
    if any(len(es) > 1 for _, row in table.rows for es in row.values()):
        return None
    starts = [set(start for start, _, _ in table.notes[v]) for v in voices]
    total = sum(map(len, starts))
    if not total or len(voices) * len(set.intersection(*starts)) / total < 0.6:
        return None
    return table


def applies(index: ScoreIndex) -> bool:
    return _chorale(index) is not None


def check(index: ScoreIndex, chords=None) -> list[Finding]:
    table = _chorale(index)
    return _findings(index, table, chords) if table else []


def _findings(index: ScoreIndex, table: _Table, chords, bars: set[int] | None = None) -> list[Finding]:
    from music21 import chord, interval, key, note, roman, stream, voiceLeading

    voices, notes, rows = table.voices, table.notes, table.rows
    inside = [i for i, (pos, _) in enumerate(rows) if bars is None or pos[0] in bars]
    if not inside:
        return []
    lo, hi = inside[0], inside[-1] + 1
    worked = {e.id for _, row in rows[lo:hi] for es in row.values() for e in es}
    name = _names(voices)
    result = []

    def add(rule, positions, vs, why):
        result.append(Finding(tuple(p[0] for p in positions), tuple(p[1] for p in positions), tuple(vs), rule, why))

    def pitch(e):
        return e.pitch.replace("b", "-")

    ornaments, neighbors = set(), set()
    for line in notes.values():
        for (start, end, previous), (onset, stop, event), (following, _, next_event) in zip(line, line[1:], line[2:]):
            if event.id not in worked:
                continue
            measure = index.measure(event.measure)
            if end != onset or stop != following or previous.tied or event.tied:
                continue
            if event.duration >= measure.beat_length or (event.onset / measure.beat_length).denominator == 1:
                continue
            approach = interval.Interval(note.Note(pitch(previous)), note.Note(pitch(event)))
            departure = interval.Interval(note.Note(pitch(event)), note.Note(pitch(next_event)))
            if approach.directedName in ('m-3', 'M-3') and departure.directedName == 'm2':
                others = [v for v in voices if v != (event.staff, event.layer)]
                held = [table.at(onset)[v] for v in others]
                arrival = [table.at(following)[v] for v in others]
                if all(len(es) == 1 for es in held + arrival):
                    tones = [midi(es[0].pitch) % 12 for es in held]
                    resolved = chord.Chord([pitch(es[0]) for es in held] + [pitch(next_event)])
                    if (tones == [midi(es[0].pitch) % 12 for es in arrival]
                            and resolved.isTriad() and resolved.root().pitchClass == midi(next_event.pitch) % 12):
                        ornaments.add(event.id)
            if not all(i.isStep and 0 < abs(i.semitones) <= 2 for i in (approach, departure)):
                continue
            neighbor = previous.pitch == next_event.pitch
            if neighbor or approach.semitones * departure.semitones > 0:
                ornaments.add(event.id)
                if neighbor:
                    neighbors.add(event.id)

    anticipations = {}
    for line in notes.values():
        for (_, end, previous), (onset, stop, event) in zip(line, line[1:]):
            if event.id not in worked:
                continue
            measure = index.measure(event.measure)
            beat = event.onset / measure.beat_length
            if (end != onset or previous.tied or event.duration > measure.beat_length
                    or beat.denominator == 1):
                continue
            following = onset + (int(beat) + 1 - beat) * measure.beat_length
            approach = interval.Interval(note.Note(pitch(previous)), note.Note(pitch(event)))
            if following > stop or not approach.isStep or not 0 < abs(approach.semitones) <= 2:
                continue
            source = [table.just_before(onset)[v] for v in voices]
            arrival = [table.at(following)[v] for v in voices]
            if all(len(es) == 1 for es in source + arrival):
                target = arrival[voices.index((event.staff, event.layer))][0]
                source_chord = chord.Chord([pitch(es[0]) for es in source])
                arrival_chord = chord.Chord([pitch(es[0]) for es in arrival])
                if (event.pitch == target.pitch and (source_chord.isTriad() or source_chord.isSeventh())
                        and (arrival_chord.isTriad() or arrival_chord.isSeventh())
                        and source_chord.root().pitchClass != arrival_chord.root().pitchClass
                        and midi(event.pitch) % 12 not in source_chord.pitchClasses
                        and midi(event.pitch) % 12 in arrival_chord.pitchClasses):
                    anticipations[event.id] = (event.measure, measure.beat_of(event.onset + following - onset))

    def decorated(pos, event):
        return event.id in ornaments or (event.id in anticipations
                                        and pos[0] == anticipations[event.id][0]
                                        and pos[1] < anticipations[event.id][1])

    sonorities = [(p, {v: es[0] for v, es in row.items() if len(es) == 1}) for p, row in rows]
    spans = sorted(chords or [], key=lambda c: (index.measure(c.measure).index, c.beat))
    keys, place = {}, {m.number: i for i, m in enumerate(index.measures)}

    def key_at(number):
        if spans:
            return None
        start = place[number] // 4 * 4
        if start not in keys:
            phrase = stream.Stream()
            for m in index.measures[start:start + 4]:
                for e in m.events:
                    if e.pitch and not e.grace and e.duration > 0:
                        phrase.append(note.Note(pitch(e), quarterLength=float(e.duration)))
            keys[start] = phrase.analyze("key") if phrase.notes else None
        return keys[start]

    lengths = {}
    for m in index.measures:
        for e in m.events:
            if e.pitch and not e.grace and e.duration > 0:
                lengths[midi(e.pitch) % 12] = lengths.get(midi(e.pitch) % 12, 0) + float(e.duration)
    context = stream.Stream([note.Note(pitch_class, quarterLength=length) for pitch_class, length in sorted(lengths.items())])
    context_key = context.analyze("key") if not spans and lengths else None
    context_tones = {p.pitchClass for p in context_key.pitches} if context_key else set()

    inferred = {}

    def inference():
        previous, local_key = None, None
        for pos, row in sonorities[lo:]:
            k = key_at(pos[0])
            c = chord.Chord([pitch(e) for e in row.values()])
            if len(row) != len(voices):
                previous, local_key = None, None
            if not (c.isTriad() or c.isSeventh()) or len(row) != len(voices):
                yield pos, (k, None)
                continue
            root = c.root().pitchClass
            if c.isDominantSeventh():
                local_key = None
            if previous is not None and previous.root != root:
                local_key = None
                dominant = previous.root == (root + 7) % 12 and previous.third == (root - 1) % 12
                diminished = previous.root == (root - 1) % 12 and {(root + 2) % 12, (root + 5) % 12} <= previous.tones
                if (dominant or diminished) and c.third and (c.third.pitchClass - root) % 12 in (3, 4):
                    local_key = key.Key(c.root().name, 'minor' if (c.third.pitchClass - root) % 12 == 3 else 'major')
            previous = harmony.Chord(root, frozenset(p.pitchClass for p in c.pitches),
                                     c.bass().pitchClass, c.seventh.pitchClass if c.seventh else None,
                                     c.third.pitchClass if c.third else None)
            reduced = chord.Chord([pitch(e) for e in row.values() if not decorated(pos, e)])
            sounding = None
            if reduced.isTriad() or reduced.isSeventh():
                sounding = harmony.Chord(reduced.root().pitchClass, frozenset(p.pitchClass for p in reduced.pitches),
                                         reduced.bass().pitchClass, reduced.seventh.pitchClass if reduced.seventh else None,
                                         reduced.third.pitchClass if reduced.third else None)
            yield pos, (local_key or k, sounding)

    inferring = inference()

    def inferred_at(pos):
        while pos not in inferred:
            found, value = next(inferring)
            inferred[found] = value
        return inferred[pos]

    def named(pos, row):
        if spans:
            here = (index.measure(pos[0]).index, pos[1])
            span = next((c for c in reversed(spans) if (index.measure(c.measure).index, c.beat) <= here), None)
            if span is None:
                return None, None
            k = key.Key(key.convertKeyStringToMusic21KeyString(span.key))
            c = harmony.chord(span.key, span.label)
            figure = span.label.replace('/o', 'ø')
            if c and '/' in figure:
                named_chord = roman.RomanNumeral(figure.replace('ø', '/o'), k,
                                                sixthMinor=roman.Minor67Default.CAUTIONARY,
                                                seventhMinor=roman.Minor67Default.CAUTIONARY)
                if named_chord.secondaryRomanNumeralKey:
                    k = named_chord.secondaryRomanNumeralKey
            return k, c
        return inferred_at(pos)

    for pos, row in sonorities[lo:hi]:
        for v in row:
            event = row[v]
            if pos != (event.measure, index.measure(event.measure).beat_of(event.onset)):
                continue
            if len(voices) == 4:
                low, high = RANGES[voices.index(v)]
            elif v == voices[0]:
                low, high = RANGES[0]
            elif v == voices[-1]:
                low, high = RANGES[-1]
            else:
                continue
            if not midi(low) <= midi(row[v].pitch) <= midi(high):
                add("range", [pos], [v], f"The {name[v]}'s {row[v].pitch} is outside its usual range, {low}–{high} (Open Music Theory).")
        for upper, lower in zip(voices, voices[1:]):
            if upper not in row or lower not in row:
                continue
            gap = midi(row[upper].pitch) - midi(row[lower].pitch)
            if gap < 0:
                add("voice_crossing", [pos], [upper, lower], f"Voice crossing: {name[upper]} and {name[lower]}. The {name[lower]}'s {row[lower].pitch} is higher than the {name[upper]}'s {row[upper].pitch}.")
            if lower != voices[-1] and gap > 12:
                add("spacing", [pos], [upper, lower], f"Spacing: {name[upper]} and {name[lower]} are more than an octave apart.")
        if not spans and len(row) != len(voices):
            continue
        k, c = named(pos, row)
        if k and c:
            leading = k.getLeadingTone()
            dominant = c.root == (k.tonic.pitchClass + 7) % 12 and c.third == leading.pitchClass
            diminished = c.root == leading.pitchClass and {(c.root + 3) % 12, (c.root + 6) % 12} <= c.tones
            if not (dominant or diminished):
                continue
            doubled = [v for v in row if (spans or not decorated(pos, row[v]))
                       and pitch(row[v])[:-1] == leading.name and midi(row[v].pitch) % 12 in c.tones]
            if len(doubled) > 1:
                add("doubled_leading_tone", [pos], doubled, f"The leading tone ({leading.name.replace('-', 'b')}) is doubled, in the {' and '.join(name[v] for v in doubled)}; it should appear once.")

    for row_number in range(lo, min(hi, len(rows) - 1)):
        (before, arow), (after, brow) = rows[row_number], rows[row_number + 1]
        a = {v: es[0] for v, es in arow.items() if len(es) == 1}
        b = {v: es[0] for v, es in brow.items() if len(es) == 1}
        for upper, lower in combinations(voices, 2):
            if not all(v in a and v in b for v in (upper, lower)):
                continue
            au, al, bu, bl = [midi(r[v].pitch) for r, v in ((a, upper), (a, lower), (b, upper), (b, lower))]
            same = (bu - au) * (bl - al) > 0
            quartet = voiceLeading.VoiceLeadingQuartet(pitch(a[upper]), pitch(b[upper]), pitch(a[lower]), pitch(b[lower]))
            if same:
                rule = "parallel_fifths" if quartet.parallelFifth() else "parallel_octaves" if quartet.parallelOctave() or quartet.parallelUnison() else None
                if rule:
                    add(rule, [before, after], [upper, lower], f"Parallel {'fifths' if rule == 'parallel_fifths' else 'octaves'}: {name[upper]} and {name[lower]} move in the same direction from one {'fifth' if rule == 'parallel_fifths' else 'octave'} to another.")
                elif (upper, lower) == (voices[0], voices[-1]) and abs(bu - au) > 2:
                    arrival = interval.Interval(note.Note(pitch(b[lower])), note.Note(pitch(b[upper]))).semiSimpleName
                    if arrival in ("P5", "P8", "P1"):
                        add("direct_fifths" if arrival == "P5" else "direct_octaves", [before, after], [upper, lower], f"Direct {'fifth' if arrival == 'P5' else 'octave'}: soprano and bass arrive at {'a fifth' if arrival == 'P5' else 'an octave'} in the same direction while the soprano leaps.")
            if voices.index(lower) == voices.index(upper) + 1 and bu >= bl and au >= al and (bu < al or bl > au):
                add("voice_overlap", [before, after], [upper, lower], f"Voice overlap: {name[upper]} and {name[lower]}. " + (f"The {name[upper]}'s {b[upper].pitch} falls below the {name[lower]}'s previous {a[lower].pitch}." if bu < al else f"The {name[lower]}'s {b[lower].pitch} rises above the {name[upper]}'s previous {a[upper].pitch}."))
        if not spans and (len(a) != len(voices) or len(b) != len(voices)):
            continue
        ka, ca = named(before, a)
        kb, cb = named(after, b)
        if ca is None:
            continue
        if cb is None:
            arrival = chord.Chord([pitch(e) for e in b.values()])
            if not (arrival.isTriad() or arrival.isSeventh()) or ca.tones == frozenset(p.pitchClass for p in arrival.pitches):
                continue
        for v in voices:
            if v not in a or v not in b:
                continue
            if cb is None and a[v].pitch == b[v].pitch:
                continue
            if b[v].id in neighbors and (cb is None or ca.root == cb.root):
                continue
            destination, target = after, b[v]
            if a[v].pitch == target.pitch:
                for later, sounding in rows[row_number + 2:]:
                    later_row = {w: es[0] for w, es in sounding.items() if len(es) == 1}
                    later_key, later_chord = named(later, later_row) if spans or len(later_row) == len(voices) else (None, None)
                    if later_key != kb or later_chord != cb:
                        break
                    if len(sounding[v]) != 1:
                        break
                    candidate = sounding[v][0]
                    if candidate.pitch != target.pitch:
                        if later_chord:
                            destination, target = later, candidate
                        break
            motion = interval.Interval(note.Note(pitch(a[v])), note.Note(pitch(target)))
            if ca.seventh is not None and midi(a[v].pitch) % 12 == ca.seventh and (cb is None or ca.tones != cb.tones):
                retained = cb is not None and a[v].pitch == b[v].pitch and ca.seventh in cb.tones and cb.seventh != ca.seventh
                if not retained and motion.directedName not in ("m-2", "M-2"):
                    add("unresolved_seventh", [before, destination], [v], f"The {name[v]}'s seventh ({a[v].pitch}) should fall by step; it {'moves to ' + target.pitch if target.pitch != a[v].pitch else 'is held'} instead.")
            if ka and kb and cb and v in (voices[0], voices[-1]):
                if (not spans and ka.tonic.pitchClass == ca.root and ka != key_at(before[0])
                        and cb.root == kb.tonic.pitchClass
                        and context_key and (cb.root == context_key.tonic.pitchClass
                                             or not ca.tones <= context_tones)
                        and cb.seventh != (cb.root + 10) % 12
                        and ca.root == (cb.root + 7) % 12 and ca.third == kb.getLeadingTone().pitchClass):
                    ka = kb
                tonic = ka.tonic.pitchClass
                retained = a[v].pitch == b[v].pitch and cb.seventh == ka.getLeadingTone().pitchClass
                if ca.root == (tonic + 7) % 12 and cb.root == tonic and not retained and midi(a[v].pitch) % 12 == ka.getLeadingTone().pitchClass:
                    if motion.directedName != "m2":
                        add("unresolved_leading_tone", [before, destination], [v], f"The {name[v]}'s leading tone ({a[v].pitch}) should rise to the tonic at V–I; it {'moves to ' + target.pitch if target.pitch != a[v].pitch else 'is held'} instead.")
    return result


def as_text(index: ScoreIndex, chords=None, first: int | None = None, last: int | None = None) -> str:
    table = _chorale(index)
    if table is None:
        return ""
    voices, rows = table.voices, table.rows
    chosen = index.select(first, last, include_pickup=False)
    numbers = {measure.number for measure in chosen}
    place = {m.number: i for i, m in enumerate(index.measures)}
    around = index.measures[max(place[chosen[0].number] - 1, 0):place[chosen[-1].number] + 2] if chosen else []
    found = [f for f in _findings(index, table, chords, {m.number for m in around})
             if all(bar in numbers for bar in f.bars)]
    names = _names(voices)
    at = {pos: row for pos, row in rows}

    def ref(pos, voice):
        es = at[pos].get(voice)
        if not es:
            return None
        e = es[0]
        return json.dumps({"measure": index.measure(e.measure).printed, "beat": index.measure(e.measure).beat_of(e.onset), "staff": e.staff, "pitch": e.pitch}, separators=(",", ":"))

    def pitch_of(pos, voice):
        return midi(at[pos][voice][0].pitch) if at[pos].get(voice) else None

    lines = [
        "PART-WRITING CHECK (strict classroom rules, not verdicts on the composer; this is a chorale-style score). Your "
        "first reply must include one sentence offering this check; "
        "draw it only if the user wants it. One callout per numbered spot, at the "
        "first note given, explaining every finding listed there. Under each spot, draw each 'draw' line as one "
        "voice_leading annotation: kind line, arrow, ring or bracket, with its from_note, to_note (not for a ring), direction (when given) and "
        "label exactly as given. Never add labels of your own or join labels with commas.",
    ]
    if not found:
        return lines[0] + "\nNo violations found."
    seen = set()
    rises = set()
    spots = {}
    for f in found:
        pos = list(zip(f.bars, f.beats))
        label, upper, lower = LABELS[f.rule], f.voices[0], f.voices[-1]
        marks = []
        if f.rule in LINES:
            marks = [("line", (ref(pos[0], v), ref(pos[1], v)), label if v == lower else None) for v in f.voices]
        elif f.rule in ARROWS:
            marks = [("arrow", (ref(pos[0], upper), ref(pos[1], upper)), label)]
            if f.rule == "unresolved_leading_tone":
                rises.add(marks[0][:2])
        elif f.rule in BRACKETS:
            if at[pos[0]][upper][0].staff == at[pos[0]][lower][0].staff:
                marks = [("bracket", (ref(pos[0], upper), ref(pos[0], lower)), label)]
            else:
                marks = [("ring", (ref(pos[0], v),), label if v == lower else None) for v in (upper, lower)]
        elif f.rule == "voice_overlap":
            new = upper if pitch_of(pos[1], upper) < pitch_of(pos[0], lower) else lower
            old = lower if new == upper else upper
            marks = [("ring", (ref(pos[1], new),), label), ("ring", (ref(pos[0], old),), None)]
        else:
            top = max(f.voices, key=lambda v: pitch_of(pos[0], v) or 0)
            marks = [("ring", (ref(pos[0], v),), label if v == top else None) for v in f.voices]
        same = (f.rule, f.voices, f.why, tuple((kind, refs) for kind, refs, _ in marks))
        if same in seen:
            continue
        seen.add(same)
        findings, drawn, _ = spots.setdefault(pos[-1], ([], {}, ref(pos[0], f.voices[0])))
        findings.append(f)
        for kind, refs, word in marks:
            if None not in refs:
                labels = drawn.setdefault((kind, refs), [])
                if word and word not in labels:
                    labels.append(word)
    for n, (pos, (findings, drawn, at_note)) in enumerate(sorted(spots.items()), 1):
        lines.append(f"{n}. m{index.name_of(pos[0])} b{pos[1]:g}, callout at {at_note}")
        for f in findings:
            where = " to ".join(f"m{index.name_of(b)} b{beat:g}" for b, beat in zip(f.bars, f.beats))
            lines.append(f"   {f.rule.replace('_', ' ')} {'+'.join(names[v] for v in f.voices)} {where}: {f.why}")
        for (kind, refs), labels in drawn.items():
            for word in labels or [None]:
                lines.append(f"   draw {kind} {' -> '.join(refs)}" + (f' label "{word}"' if word else "")
                             + (' direction "up"' if (kind, refs) in rises else ""))
    return "\n".join(lines)
