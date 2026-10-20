import json
from fractions import Fraction
from pathlib import Path

import pytest

from engine import draft, notes
from engine.render import load_toolkit
from engine.score import Measure, ScoreIndex

RAW = Path(__file__).parent / "data" / "chopin_analysisgnn_raw.json"


@pytest.fixture(scope="module")
def index(chopin) -> ScoreIndex:
    return ScoreIndex(load_toolkit(chopin).getMEI())


def summary(index: ScoreIndex) -> list:
    return [
        (m.number, m.length, m.meter, [(e.staff, e.layer, e.onset, e.duration, e.pitch, e.grace, e.tied) for e in m.events if e.pitch])
        for m in index.measures
    ]


def test_round_trip_keeps_every_note(index):
    assert summary(notes.decode(notes.encode(index))) == summary(index)


def test_note_list_is_small(index, chopin):
    assert len(notes.encode(index)) < 6_000
    assert len(notes.encode(index, 1, 8)) < 1_500


def test_range_from_measure_one_takes_the_pickup(index):
    lines = notes.encode(index, 1, 2).splitlines()
    assert lines[0] == "N1 div=48 ts=12/8 ks=3f"
    assert [line for line in lines if line.startswith("m")] == ["m0 len=24", "m1 len=288", "m2 len=288"]
    assert lines[2] == "1.1: 24 Bb4"


def test_ties_grace_notes_and_rests_are_written(index):
    text = notes.encode(index)
    assert "72 G5~ 24 G5" in text
    assert " gE5 " in text or " gE5+" in text or "gE5 gF5" in text
    assert "48 r" in text


def test_bad_note_lists_are_refused():
    with pytest.raises(notes.NotesError, match="must start with"):
        notes.decode("hello")
    with pytest.raises(notes.NotesError, match="could not be read"):
        notes.decode("N1 div=48 ts=4/4 ks=0\nm1 len=192\n1.1: 48 H9")
    with pytest.raises(notes.NotesError, match="too long"):
        notes.decode("N1 " + "x" * 300_000)


def test_draft_builds_against_a_decoded_note_list(index):
    decoded = notes.decode(notes.encode(index))
    result = draft.build(json.loads(RAW.read_text()), decoded)
    opening = {(chord.measure, chord.beat): chord.label for chord in result.chords if 1 <= chord.measure <= 4}
    assert opening[(3, 2.0)] == "V65/vi" and opening[(4, 3.0)] == "I"
    assert [(mark.measure, mark.beat, mark.label) for mark in result.cadences[:2]] == [(4, 3.0, "PAC"), (8, 3.0, "PAC")]


def test_grace_notes_after_a_rest_keep_their_place():
    text = "N1 div=4 ts=4/4 ks=0\nm1 len=16\n1.1: 8 r gA5+B5 4 C6 r"
    index = notes.decode(text)
    grace = [event for event in index.measures[0].events if event.grace]
    assert {event.onset for event in grace} == {2}
    assert notes.encode(index).splitlines()[2] == "1.1: 2 r gA5+B5 1 C6"


N1X = """N1x div=2 ts=4/4 ks=1s
P1 "Violin" staves=1
P2 "Piano" staves=2-3
m1 len=8
1.1: !mf "G7" 2 G4 1 B4 C5 4 D5~ "C maj7"@6
2.1: !p 8 G2
m2 len=8 ks=2f
1.1: 2 D5 2 r 4 Bb4
3.1: "Bb"@0"""


def test_extended_note_list_round_trips():
    index = notes.decode(N1X)
    assert index.parts == [("Violin", [1]), ("Piano", [2, 3])]
    assert [m.key_signature for m in index.measures] == ["", "2f"]
    assert [(m.staff, m.onset, m.kind, m.text) for m in index.measures[0].marks] == [
        (1, 0, "dyn", "mf"), (1, 0, "harm", "G7"), (1, 3, "harm", "C maj7"), (2, 0, "dyn", "p")
    ]
    assert notes.encode(index, extended=True) == N1X


def test_extended_note_list_filters_parts_and_carries_the_key():
    index = notes.decode(N1X)
    lines = notes.encode(index, 2, 2, extended=True, parts=[2]).splitlines()
    assert lines == ["N1x div=2 ts=4/4 ks=1s", 'P2 "Piano" staves=2-3', "m2 len=8 ks=2f", '3.1: "Bb"@0']
    index.measures.append(Measure("m3", 3, 3, Fraction(1), "4/4", Fraction(4)))
    assert notes.encode(ScoreIndex.from_measures(index.measures, "4/4", "1s"), 3, 3, extended=True).startswith(
        "N1x div=2 ts=4/4 ks=2f\nm3 len=8"
    )


def test_plain_note_list_leaves_the_extensions_out():
    assert notes.encode(notes.decode(N1X)).splitlines() == [
        "N1 div=2 ts=4/4 ks=1s", "m1 len=8", "1.1: 2 G4 1 B4 C5 4 D5~", "2.1: 8 G2", "m2 len=8", "1.1: 2 D5 2 r 4 Bb4"
    ]
