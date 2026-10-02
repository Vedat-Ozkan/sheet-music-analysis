import json
from pathlib import Path

import pytest

from engine import draft, notes
from engine.render import load_toolkit
from engine.score import ScoreIndex

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
    assert len(notes.encode(index)) < 6_000  # the compressed file as base64 is about 27,500 characters
    assert len(notes.encode(index, 1, 8)) < 1_500


def test_range_from_measure_one_takes_the_pickup(index):
    lines = notes.encode(index, 1, 2).splitlines()
    assert lines[0] == "N1 div=48 ts=12/8 ks=3f"
    assert [line for line in lines if line.startswith("m")] == ["m0 len=24", "m1 len=288", "m2 len=288"]
    assert lines[2] == "1.1: 24 Bb4"


def test_ties_grace_notes_and_rests_are_written(index):
    text = notes.encode(index)
    assert "72 G5~ 24 G5" in text  # tie in measure 1
    assert " gE5 " in text or " gE5+" in text or "gE5 gF5" in text  # grace notes before the beat in measure 7
    assert "48 r" in text  # the rest in measure 4


def test_bad_note_lists_are_refused():
    with pytest.raises(notes.NotesError, match="must start with"):
        notes.decode("hello")
    with pytest.raises(notes.NotesError, match="could not be read"):
        notes.decode("N1 div=48 ts=4/4 ks=0\nm1 len=192\n1.1: 48 H9")
    with pytest.raises(notes.NotesError, match="too long"):
        notes.decode("N1 " + "x" * 300_000)


def test_draft_builds_against_a_decoded_note_list(index):
    """The model saw the same notes either way, so its saved output must line up with the decoded index."""
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
    assert notes.encode(index).splitlines()[2] == "1.1: 2 r gA5+B5 1 C6"  # written in the smallest whole units
