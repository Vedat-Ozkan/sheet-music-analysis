"""Deterministic classroom part-writing checks on the sounding note table.

Voices are staff/layer pairs in score order, never sorted by current pitch (which
would hide crossings). Four voices are SATB; fewer voices retain soprano/bass
outer roles, but get no guessed inner vocal ranges. Ranges are C4–G5, G3–D5,
C3–G4 and F2–D4, from Open Music Theory, 'Roman Numerals and SATB Chord Construction':
https://viva.pressbooks.pub/openmusictheorycopy/chapter/roman-numerals/.

Pass draft.Chord spans to reuse the engine's local keys and Roman labels without
running its model. Without spans, music21 estimates a duration-weighted key in
four-bar windows (a phrase proxy; fermatas are absent from the note table), and
recognises only complete triads/sevenths at note onsets. Ambiguous sonorities do
not get tendency-tone checks. This limits, but cannot eliminate, passing-note misreadings.
The fallback cannot reliably recognise tonicizations or incomplete chords.

music21's VoiceLeadingQuartet fits the spelled parallel-interval checks. Direct
intervals additionally require an outer soprano leap, the usual classroom rule.
These are reports of strict exercise rules, not a verdict on a composition.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations

from engine import harmony
from engine.reduce import midi
from engine.score import ScoreIndex

Voice = tuple[int, int]
RANGES = (("C4", "G5"), ("G3", "D5"), ("C3", "G4"), ("F2", "D4"))
# Arrow labels in the draft: short enough not to crowd the staff, spelled as the commentary names them
LABELS = {"parallel_fifths": "P5", "parallel_octaves": "P8", "direct_fifths": "direct 5", "direct_octaves": "direct 8",
          "voice_crossing": "crossing", "voice_overlap": "overlap", "spacing": "spacing", "range": "range",
          "doubled_leading_tone": "LT doubled", "unresolved_seventh": "7th", "unresolved_leading_tone": "LT"}


@dataclass
class Finding:
    bars: tuple[int, ...]
    beats: tuple[float, ...]
    voices: tuple[Voice, ...]
    rule: str
    why: str


def _table(index):
    voices = sorted({(e.staff, e.layer) for m in index.measures for e in m.events if e.pitch and not e.grace})
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
    rows = []
    for t in sorted(positions):
        sounding = {v: [e for start, end, e in notes[v] if start <= t < end] for v in voices}
        rows.append((positions[t], sounding))
    return voices, notes, rows


def applies(index: ScoreIndex) -> bool:
    """At least 60% of voice onsets must coincide with every voice, with 2–4 monophonic
    voices and at most four staves. A majority with room for passing eighths
    admits chorales while rejecting predominantly staggered counterpoint.
    Tied continuations count as aligned notated onsets, not fresh attacks.
    """
    voices, notes, rows = _table(index)
    if not 2 <= len(voices) <= 4 or len({e.staff for m in index.measures for e in m.events}) > 4:
        return False
    if any(len(es) > 1 for _, row in rows for es in row.values()):
        return False
    starts = [set(start for start, _, _ in notes[v]) for v in voices]
    total = sum(map(len, starts))
    return bool(total) and len(voices) * len(set.intersection(*starts)) / total >= 0.6


def check(index: ScoreIndex, chords=None) -> list[Finding]:
    """Report strict rules, or return no findings when the texture does not apply.

    Optional chords are engine.draft.Chord spans, in score order. Findings use
    the start and arrival positions for motion, and one position for a sonority.
    music21 is imported only when an applicable report is requested.
    """
    if not applies(index):
        return []
    from music21 import chord, interval, key, note, roman, stream, voiceLeading

    voices, _, rows = _table(index)
    result = []

    def add(rule, positions, vs, why):
        result.append(Finding(tuple(p[0] for p in positions), tuple(p[1] for p in positions), tuple(vs), rule, why))

    def pitch(e):
        return e.pitch.replace("b", "-")

    sonorities = [(p, {v: es[0] for v, es in row.items() if len(es) == 1}) for p, row in rows]
    spans = sorted(chords or [], key=lambda c: (index.measure(c.measure).index, c.beat))
    keys = {}
    if not spans:
        for start in range(0, len(index.measures), 4):
            phrase = stream.Stream()
            for m in index.measures[start:start + 4]:
                for e in m.events:
                    if e.pitch and not e.grace and e.duration > 0:
                        phrase.append(note.Note(pitch(e), quarterLength=float(e.duration)))
            if phrase.notes:
                estimated = phrase.analyze("key")
                for m in index.measures[start:start + 4]:
                    keys[m.number] = estimated

    def named(pos, row):
        if spans:
            here = (index.measure(pos[0]).index, pos[1])
            span = next((c for c in reversed(spans) if (index.measure(c.measure).index, c.beat) <= here), None)
            if span is None:
                return None, None
            k = key.Key(span.key.replace("b", "-"))
            c = harmony.chord(span.key, span.label)
            # Applied dominants have the target's leading tone, not the global key's.
            figure = span.label.replace('/o', 'ø')
            if c and '/' in figure:
                named_chord = roman.RomanNumeral(figure.replace('ø', '/o'), k,
                                                sixthMinor=roman.Minor67Default.CAUTIONARY,
                                                seventhMinor=roman.Minor67Default.CAUTIONARY)
                if named_chord.secondaryRomanNumeralKey:
                    k = named_chord.secondaryRomanNumeralKey
            return k, c
        k = keys.get(pos[0])
        c = chord.Chord([pitch(e) for e in row.values()])
        if k is None or not (c.isTriad() or c.isSeventh()):
            return k, None
        return k, harmony.Chord(c.root().pitchClass, frozenset(p.pitchClass for p in c.pitches),
                                c.bass().pitchClass, c.seventh.pitchClass if c.seventh else None,
                                c.third.pitchClass if c.third else None)

    for pos, row in sonorities:
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
                add("range", [pos], [v], f"{row[v].pitch} lies outside the exercise range {low}–{high} (Open Music Theory).")
        for upper, lower in zip(voices, voices[1:]):
            if upper not in row or lower not in row:
                continue
            gap = midi(row[upper].pitch) - midi(row[lower].pitch)
            if gap < 0:
                add("voice_crossing", [pos], [upper, lower], f"The lower voice's {row[lower].pitch} is above the upper voice's {row[upper].pitch}.")
            if lower != voices[-1] and gap > 12:
                add("spacing", [pos], [upper, lower], "Adjacent upper voices are more than an octave apart.")
        if not spans and len(row) != len(voices):
            continue
        k, c = named(pos, row)
        if k and c:
            leading = k.getLeadingTone()
            dominant = c.root == (k.tonic.pitchClass + 7) % 12 and c.third == leading.pitchClass
            diminished = c.root == leading.pitchClass and {(c.root + 3) % 12, (c.root + 6) % 12} <= c.tones
            if not (dominant or diminished):
                continue
            doubled = [v for v in row if pitch(row[v])[:-1] == leading.name and midi(row[v].pitch) % 12 in c.tones]
            if len(doubled) > 1:
                add("doubled_leading_tone", [pos], doubled, f"The leading tone {leading.name.replace('-', 'b')} is doubled.")

    for row_number, ((before, arow), (after, brow)) in enumerate(zip(rows, rows[1:])):
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
                    add(rule, [before, after], [upper, lower], f"Both voices move in the same direction through perfect {'fifths' if rule == 'parallel_fifths' else 'octaves or unisons'}.")
                elif (upper, lower) == (voices[0], voices[-1]) and abs(bu - au) > 2:
                    arrival = interval.Interval(note.Note(pitch(b[lower])), note.Note(pitch(b[upper]))).semiSimpleName
                    if arrival in ("P5", "P8", "P1"):
                        add("direct_fifths" if arrival == "P5" else "direct_octaves", [before, after], [upper, lower], "The outer voices approach a perfect interval in similar motion while the soprano leaps.")
            # Unisons are noncrossing; overlap still requires moving strictly past.
            if voices.index(lower) == voices.index(upper) + 1 and bu >= bl and au >= al and (bu < al or bl > au):
                add("voice_overlap", [before, after], [upper, lower], "One voice moves beyond the adjacent voice's previous pitch.")
        if not spans and (len(a) != len(voices) or len(b) != len(voices)):
            continue
        ka, ca = named(before, a)
        kb, cb = named(after, b)
        if ca is None or cb is None:
            continue
        for v in voices:
            if v not in a or v not in b:
                continue
            destination, target = after, b[v]
            if a[v].pitch == target.pitch:
                for later, sounding in rows[row_number + 2:]:
                    later_row = {w: es[0] for w, es in sounding.items() if len(es) == 1}
                    later_key, later_chord = named(later, later_row) if spans or len(later_row) == len(voices) else (None, None)
                    # A suspension must resolve while the arrival harmony is active.
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
            if ca.seventh is not None and midi(a[v].pitch) % 12 == ca.seventh and ca.tones != cb.tones:
                # A retained common tone may be a consonance in a revoicing, not a failed resolution.
                retained = a[v].pitch == b[v].pitch and ca.seventh in cb.tones and cb.seventh != ca.seventh
                if not retained and motion.directedName not in ("m-2", "M-2"):
                    add("unresolved_seventh", [before, destination], [v], f"The chordal seventh {a[v].pitch} does not resolve down by step.")
            if ka and kb and v in (voices[0], voices[-1]):
                tonic = ka.tonic.pitchClass
                if ca.root == (tonic + 7) % 12 and cb.root == tonic and midi(a[v].pitch) % 12 == ka.getLeadingTone().pitchClass:
                    if motion.directedName != "m2":
                        add("unresolved_leading_tone", [before, destination], [v], f"The outer voice's leading tone {a[v].pitch} does not rise to the tonic at V–I.")
    return result


def as_text(index: ScoreIndex, chords=None) -> str:
    """The findings as a compact section of the draft the chat model reads; empty when the texture does not apply.

    Each finding carries NoteRefs in the form the annotation list accepts, so the model can draw an arrow
    per voice (or between the two voices of a single sonority) and a callout without looking notes up.
    """
    if not applies(index):
        return ""
    voices, _, rows = _table(index)
    found = check(index, chords)
    names = dict(zip(voices, ("S", "A", "T", "B"))) if len(voices) == 4 else {v: f"voice {i + 1}" for i, v in enumerate(voices)}
    at = {pos: row for pos, row in rows}

    def ref(pos, voice):
        es = at[pos].get(voice)
        if not es:
            return None
        e = es[0]
        return json.dumps({"measure": e.measure, "beat": index.measure(e.measure).beat_of(e.onset), "staff": e.staff, "pitch": e.pitch}, separators=(",", ":"))

    lines = [
        "PART-WRITING CHECK (strict classroom rules, not verdicts on the composer; this is a chorale-style score, so "
        "offer the check in one line and draw it only if the user wants it). One callout per numbered spot, at the "
        "first note given, explaining every finding listed there; one voice_leading arrow per line under it, with "
        "that line's label.",
    ]
    if not found:
        return lines[0] + "\nNo violations found."
    spots = {}  # first position -> (findings, {arrow: labels}, callout note)
    for f in found:
        pos = list(zip(f.bars, f.beats))
        if len(pos) == 2:
            arrows = [(ref(pos[0], v), ref(pos[1], v)) for v in f.voices]
        elif len(f.voices) == 2:
            arrows = [(ref(pos[0], f.voices[0]), ref(pos[0], f.voices[1]))]
        else:
            arrows = []
        findings, drawn, _ = spots.setdefault(pos[0], ([], {}, ref(pos[0], f.voices[0])))
        findings.append(f)
        for arrow in arrows:
            if None not in arrow:
                labels = drawn.setdefault(arrow, [])
                if LABELS[f.rule] not in labels:
                    labels.append(LABELS[f.rule])
    for n, (pos, (findings, drawn, at_note)) in enumerate(sorted(spots.items()), 1):
        lines.append(f"{n}. m{pos[0]} b{pos[1]:g}, callout at {at_note}")
        for f in findings:
            where = " to ".join(f"m{b} b{beat:g}" for b, beat in zip(f.bars, f.beats))
            lines.append(f"   {f.rule.replace('_', ' ')} {'+'.join(names[v] for v in f.voices)} {where}: {f.why}")
        lines += [f"   arrow {a} -> {b} label \"{', '.join(sorted(labels))}\"" for (a, b), labels in drawn.items()]
    return "\n".join(lines)
