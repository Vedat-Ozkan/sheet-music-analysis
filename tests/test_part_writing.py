from pathlib import Path

import pytest
from music21 import corpus

from engine.draft import Chord
from engine.part_writing import applies, check
from engine.render import load_toolkit
from engine.score import ScoreIndex

DATA = Path(__file__).parent / "data"
S, A, T, B = ((n, 1) for n in range(1, 5))


def read(path):
    return ScoreIndex(load_toolkit(path.read_bytes()).getMEI())


def identities(hits):
    return {(h.rule, h.bars, h.voices) for h in hits}


def span(bar, label, key="C", beat=1):
    return Chord(bar, beat, key, label, 1, 4, None)


def test_planted_motion_errors():
    # m1–2: S/T and S/B fifths, T/B octaves; m4–5: S/B octaves, T/B fifths.
    # m7–8: direct outer fifth; m10–11: direct outer octave; m13: S/A crossing.
    # m15: soprano A5 out of range; m17–18: S/A overlap.
    # m20–21: S/A and S/T fifths, A/T parallel unisons; m23: S/A spacing.
    expected = {
        ("parallel_fifths", (1, 2), (S, T)),
        ("parallel_fifths", (1, 2), (S, B)),
        ("parallel_octaves", (1, 2), (T, B)),
        ("parallel_octaves", (4, 5), (S, B)),
        ("parallel_fifths", (4, 5), (T, B)),
        ("direct_fifths", (7, 8), (S, B)),
        ("direct_octaves", (10, 11), (S, B)),
        ("voice_crossing", (13,), (S, A)),
        ("range", (15,), (S,)),
        ("voice_overlap", (17, 18), (S, A)),
        ("parallel_fifths", (20, 21), (S, A)),
        ("parallel_fifths", (20, 21), (S, T)),
        ("parallel_octaves", (20, 21), (A, T)),
        ("voice_overlap", (20, 21), (A, T)),
        ("spacing", (23,), (S, A)),
    }
    index = read(DATA / "part_writing_motion.musicxml")
    assert applies(index)
    hits = check(index)
    assert identities(hits) == expected
    assert len(hits) == len(expected)
    assert all(h.beats == (1.0,) * len(h.bars) and h.why.endswith(".") for h in hits)


def test_planted_tendency_errors():
    # m1–2: outer B4 falls to G4 at V7–I; alto F4 rises to G4 (unresolved seventh).
    # m4: S/T doubled B in V; m4–5 otherwise resolves correctly.
    index = read(DATA / "part_writing_tendency.musicxml")
    chords = [span(1, "V7"), span(2, "I"), span(4, "V"), span(5, "I")]
    hits = check(index, chords)
    expected = {
        ("unresolved_leading_tone", (1, 2), (S,)),
        ("unresolved_seventh", (1, 2), (A,)),
        ("doubled_leading_tone", (4,), (S, T)),
    }
    assert identities(hits) == expected
    assert len(hits) == len(expected)
    # The short fallback window estimates G major and skips the incomplete G/B dominant.
    assert identities(check(index)) == {("unresolved_seventh", (1, 2), (A,))}


@pytest.mark.parametrize("name, expected", [
    ("bwv66.6", {
        ("range", (7,), (A,)),
        ("voice_crossing", (7,), (A, T)),
        ("voice_overlap", (5, 5), (A, T)),
        ("voice_overlap", (4, 4), (T, B)),  # B3 unison: tenor falls to A3.
        ("unresolved_leading_tone", (5, 6), (S,)),  # E–A–D: outer C#5 falls to A4.
    }),
    ("bwv269", {("voice_overlap", (2, 3), (A, T)),
                ("voice_overlap", (2, 2), (T, B))}),  # G3 unison: tenor falls to F#3.
    ("bwv244.15", {
        ("range", (12,), (B,)),
        ("voice_overlap", (4, 4), (A, T)),
        ("direct_octaves", (11, 11), (S, B)),
        ("voice_overlap", (9, 10), (T, B)),  # A3 unison: tenor falls to F#3.
    }),
])
def test_bach_chorales_reviewed_hits(name, expected):
    # These are strict exercise-rule exceptions, reviewed note by note in REPORT.md.
    index = read(Path(corpus.__file__).parent / "bach" / f"{name}.mxl")
    assert applies(index)
    hits = check(index)
    assert identities(hits) == expected
    assert len(hits) == len(expected)


def altered_tendency(changes, split=False):
    import copy
    import xml.etree.ElementTree as ET

    root = ET.fromstring((DATA / "part_writing_tendency.musicxml").read_bytes())
    for staff, bar, name in changes:
        measure = root.findall("part")[staff - 1].find(f"measure[@number='{bar}']")
        n = measure.find("note")
        n.find("pitch/step").text, n.find("pitch/octave").text = name[0], name[-1]
        if split:
            n.find("duration").text = "2"
            n.find("type").text = "half"
            held = copy.deepcopy(n)
            held.find("pitch/step").text = "B" if staff == 1 else "F"
            held.find("pitch/octave").text = "4"
            measure.insert(list(measure).index(n), held)
    return ScoreIndex(load_toolkit(ET.tostring(root)).getMEI())


def test_correct_and_delayed_resolutions():
    chords = [span(1, "V7"), span(2, "I"), span(4, "V"), span(5, "I")]
    changes = [(1, 2, "C5"), (2, 2, "E4"), (3, 4, "D4")]
    assert check(altered_tendency(changes), chords) == []
    delayed = altered_tendency(changes[:2], split=True)
    # A tied or repeated suspension resolves later in the tonic harmony.
    assert identities(check(delayed, chords)) == {("doubled_leading_tone", (4,), (S, T))}


def test_held_tendency_tones_do_not_escape_the_check():
    chords = [span(1, "V7"), span(2, "I"), span(4, "V"), span(5, "I")]
    index = altered_tendency([(1, 2, "B4"), (2, 2, "F4"), (3, 4, "D4")])
    assert identities(check(index, chords)) == {
        ("unresolved_leading_tone", (1, 2), (S,)),
        ("unresolved_seventh", (1, 2), (A,)),
    }


def test_applicability_rejects_staggered_and_chordal_textures():
    from music21 import converter
    from music21.musicxml.m21ToXml import GeneralObjectExporter

    score = converter.parse(DATA / "part_writing_tendency.musicxml")
    for number, part in enumerate(score.parts):
        for n in part.recurse().notes:
            n.offset += number / 4
    staggered = ScoreIndex(load_toolkit(GeneralObjectExporter(score).parse()).getMEI())
    assert not applies(staggered)
    assert check(staggered) == []
    assert not applies(read(DATA / "cadential_64.musicxml"))
    assert not applies(read(DATA / "chopin_nocturne_op9_no2.mxl"))


def test_satb_on_two_staves_retains_voice_identity():
    from music21 import converter, stream
    from music21.musicxml.m21ToXml import GeneralObjectExporter

    source = converter.parse(DATA / "part_writing_tendency.musicxml")
    score = stream.Score()
    for pair in (source.parts[:2], source.parts[2:]):
        staff = stream.Part()
        for number in range(1, 7):
            bar = stream.Measure(number=number)
            for part in pair:
                voice = stream.Voice()
                for element in part.measure(number):
                    voice.insert(element.offset, element)
                bar.insert(0, voice)
            staff.append(bar)
        score.append(staff)
    index = ScoreIndex(load_toolkit(GeneralObjectExporter(score).parse()).getMEI())
    assert applies(index)
    hits = check(index, [span(1, "V7"), span(2, "I"), span(4, "V"), span(5, "I")])
    assert identities(hits) == {
        ("unresolved_leading_tone", (1, 2), ((1, 1),)),
        ("unresolved_seventh", (1, 2), ((1, 2),)),
        ("doubled_leading_tone", (4,), ((1, 1), (2, 1))),
    }


def test_minor_key_uses_raised_leading_tone():
    import xml.etree.ElementTree as ET

    root = ET.fromstring((DATA / "part_writing_tendency.musicxml").read_bytes())
    for p in root.iter("pitch"):
        if p.findtext("step") == "E":
            ET.SubElement(p, "alter").text = "-1"
    index = ScoreIndex(load_toolkit(ET.tostring(root)).getMEI())
    chords = [span(1, "V7", "c"), span(2, "i", "c"), span(4, "V", "c"), span(5, "i", "c")]
    assert identities(check(index, chords)) == {
        ("unresolved_leading_tone", (1, 2), (S,)),
        ("unresolved_seventh", (1, 2), (A,)),
        ("doubled_leading_tone", (4,), (S, T)),
    }


def test_spelling_distinguishes_augmented_fourths_from_perfect_fifths():
    import xml.etree.ElementTree as ET

    root = ET.fromstring((DATA / "part_writing_motion.musicxml").read_bytes())
    for number, step in [(1, "F"), (2, "G")]:
        p = root.find(f"part[@id='P1']/measure[@number='{number}']/note/pitch")
        p.find("step").text = step
        ET.SubElement(p, "alter").text = "1"
    index = ScoreIndex(load_toolkit(ET.tostring(root)).getMEI())
    first_pair = [h for h in check(index) if h.bars == (1, 2)]
    assert identities(first_pair) == {("parallel_octaves", (1, 2), (T, B))}


def satb(bars):
    from music21 import meter, note, stream
    from music21.musicxml.m21ToXml import GeneralObjectExporter

    score = stream.Score()
    for voice in range(4):
        part = stream.Part()
        for number, pitches in enumerate(bars, 1):
            measure = stream.Measure(number=number)
            if number == 1:
                measure.insert(0, meter.TimeSignature('4/4'))
            event = note.Note(pitches[voice]) if pitches[voice] else note.Rest()
            event.quarterLength = 4
            measure.append(event)
            part.append(measure)
        score.append(part)
    return ScoreIndex(load_toolkit(GeneralObjectExporter(score).parse()).getMEI())


def test_secondary_dominant_leading_tone():
    index = satb([('F#4', 'A3', 'F#3', 'D3'), ('D4', 'B3', 'G3', 'G2')])
    hits = identities(check(index, [span(1, 'V/V'), span(2, 'V')]))
    assert ('doubled_leading_tone', (1,), (S, T)) in hits
    assert ('unresolved_leading_tone', (1, 2), (S,)) in hits


def test_tendency_checks_survive_another_voices_rest():
    index = satb([('B4', 'F4', 'D4', 'G2'), ('G4', None, 'E4', 'C3'), ('G4', 'E4', 'E4', 'C3')])
    assert applies(index)
    assert ('unresolved_leading_tone', (1, 2), (S,)) in identities(
        check(index, [span(1, 'V7'), span(2, 'I'), span(3, 'I')]))


@pytest.mark.parametrize('bars', [
    [('C5', 'C5', 'E4', 'C3'), ('B4', 'A4', 'F4', 'F3')],
    [('C5', 'B4', 'E4', 'C3'), ('A4', 'A4', 'F4', 'F3')],
])
def test_overlap_with_unison_at_either_end(bars):
    assert ('voice_overlap', (1, 2), (S, A)) in identities(
        check(satb(bars), [span(1, 'I'), span(2, 'IV')]))


def test_delayed_resolution_cannot_cross_harmony_boundary():
    index = satb([('B4', 'G4', 'D4', 'G2'), ('B4', 'G4', 'E4', 'C3'), ('C5', 'A4', 'F4', 'F3')])
    assert ('unresolved_leading_tone', (1, 2), (S,)) in identities(
        check(index, [span(1, 'V'), span(2, 'I'), span(3, 'IV')]))


@pytest.mark.parametrize('name, rule, bars, beats, voices', [
    # E4 passes D4–E4–F#4; the weak-beat stack is not a new F# minor seventh.
    ('bwv108.6', 'unresolved_seventh', (7, 7), (2.5, 3.0), (T,)),
    # A3–G#3–A3 is a neighbour; A2–B2–C#3 is a passing bass, not C# minor seventh.
    ('bwv386', 'unresolved_seventh', (5, 5), (3.75, 4.0), (B,)),
    # The passing bass C#3 does not make the held B-minor tones a D augmented seventh.
    ('bwv99.6', 'unresolved_seventh', (10, 10), (1.5, 2.0), (B,)),
    # The alto ornaments G4 with A4–G4 before resolving the A7 seventh to F#4.
    ('bwv282', 'unresolved_seventh', (15, 15), (3.0, 3.5), (A,)),
    # B7–E establishes E locally: doubled G# is the tonic third, not A's leading tone.
    ('bwv197.5', 'doubled_leading_tone', (12,), (1.5,), (S, B)),
    # A held C# over D is a seventh sonority, not a completed V–I arrival.
    ('bwv303', 'unresolved_leading_tone', (3, 3), (1.0, 1.5), (S,)),
])
def test_bach_embellishments_and_local_tonics(name, rule, bars, beats, voices):
    index = read(DATA / f'part_writing_{name}.musicxml')
    assert applies(index)
    assert not any((h.rule, h.bars, h.beats, h.voices) == (rule, bars, beats, voices)
                   for h in check(index))


def test_explicit_dominant_still_reports_doubled_leading_tone():
    index = read(DATA / 'part_writing_bwv197.5.musicxml')
    # The same G# doubling is an error when the supplied analysis establishes A, not E, as tonic.
    assert any(h.rule == 'doubled_leading_tone' and h.bars == (12,) and h.beats == (1.5,)
               and h.voices == (S, B) for h in check(index, [span(12, 'V6', 'A', 1.5)]))


@pytest.mark.parametrize('name, bar', [('bwv244.3', 9), ('bwv168.6', 4)])
def test_leaping_leading_note_decoration_is_not_a_chordal_seventh(name, bar):
    # The alto falls a third then rises a semitone into the sustained minor tonic.
    index = read(DATA / f'part_writing_{name}.musicxml')
    assert applies(index)
    assert not any(h.rule == 'unresolved_seventh' and h.bars == (bar, bar)
                   and h.beats == (1.5, 2.0) and h.voices == (A,) for h in check(index))


def test_established_seventh_obligation_survives_decorated_arrival():
    # Complete Fm7 has Eb4 rising to F4; the soprano's passing D5 cannot erase it.
    index = read(DATA / 'part_writing_bwv102.7.musicxml')
    assert applies(index)
    assert any(h.rule == 'unresolved_seventh' and h.bars == (5, 5)
               and h.beats == (2.0, 2.5) and h.voices == (A,) for h in check(index))


@pytest.mark.parametrize('name, bar, voice', [('bwv85.6', 12, T), ('bwv404', 7, S)])
def test_anticipations_do_not_create_seventh_obligations(name, bar, voice):
    # Repeated arrival tones anticipate the new harmony while the dominant resolves.
    index = read(DATA / f'part_writing_{name}.musicxml')
    assert applies(index)
    assert not any(h.rule == 'unresolved_seventh' and h.bars == (bar, bar)
                   and h.beats == (2.5, 3.0) and h.voices == (voice,) for h in check(index))


def test_successive_tonicizations_preserve_outer_leading_tone_obligation():
    # E7–A tonicizes A, but A–D/F# still requires the soprano C#5 to rise to D5.
    index = read(DATA / 'part_writing_bwv64.4.musicxml')
    assert applies(index)
    chords = [span(11, 'V7/V', 'D', 4), span(12, 'V', 'D'), span(12, 'I6', 'D', 4)]
    for hits in (check(index, chords), check(index)):
        assert any(h.rule == 'unresolved_leading_tone' and h.bars == (12, 12)
                   and h.beats == (1.0, 4.0) and h.voices == (S,) for h in hits)


def test_successive_dominants_are_not_a_tonic_arrival():
    # B7–E–A7 continues the dominant sequence; bass G#3 becomes A7's G3 seventh.
    index = read(DATA / 'part_writing_bwv245.14.musicxml')
    assert applies(index)
    assert not any(h.rule == 'unresolved_leading_tone' and h.bars == (11, 11)
                   and h.beats == (2.0, 3.0) and h.voices == (B,) for h in check(index))
