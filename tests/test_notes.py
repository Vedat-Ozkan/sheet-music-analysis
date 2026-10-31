import json
import subprocess
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


def test_a_tie_into_another_voice_keeps_every_note_for_the_model():
    text = ("N1 div=1 ts=4/4 ks=0\nm1 len=4\n1.1: 4 C5\n1.2: 4 E4~\nm2 len=4\n1.1: 4 E4\n"
            "m3 len=4\n1.1: 4 D5\n1.2: 4 G4\nm4 len=4\n1.1: 4 C5\n1.2: 4 E4")
    raw = draft.MODELS["analysisgnn"](text.encode(), "notes")
    heard = sorted(zip(raw["notes"]["measure"], raw["notes"]["pitch"], raw["notes"]["duration"]))
    assert heard == [(1, "C5", 4.0), (1, "E4", 8.0), (3, "D5", 4.0), (3, "G4", 4.0), (4, "C5", 4.0), (4, "E4", 4.0)]


@pytest.fixture(scope="module")
def haydn() -> ScoreIndex:
    return ScoreIndex(load_toolkit((Path(__file__).parent / "data" / "piano" / "haydn-104.mxl").read_bytes()).getMEI())


def test_a_key_change_is_written_on_its_bar_and_read_back(haydn):
    text = notes.encode(haydn)
    assert text.splitlines()[0].startswith("N1 div=") and " ks=1f" in text.splitlines()[0]
    assert [line.split()[0] for line in text.splitlines() if " ks=" in line[1:] and line.startswith("m")] == ["m17"]
    assert [m.key_signature for m in notes.decode(text).measures] == [m.key_signature for m in haydn.measures]


def test_a_note_list_without_bar_keys_keeps_the_header_key():
    index = notes.decode("N1 div=1 ts=4/4 ks=2f\nm1 len=4\n1.1: 4 C4\nm2 len=3 ts=3/4\n1.1: 3 D4")
    assert [m.key_signature for m in index.measures] == ["2f", "2f"]


def test_the_model_reads_each_key_signature_at_its_bar(haydn):
    code = ("import sys; sys.path.insert(0, 'engine/models'); import analysisgnn_runner as runner; "
            "score = runner.score_from_notes(sys.stdin.read()); "
            "print([(k.start.t, k.fifths) for k in score[0].iter_all(runner.pt.score.KeySignature)])")
    text = notes.encode(haydn, 1, 20)
    decoded = notes.decode(text)
    bar_17 = sum(m.length for m in decoded.measures[: [m.number for m in decoded.measures].index(17)]) * decoded.ppq
    out = subprocess.run([draft.ANALYSISGNN_PYTHON, "-c", code], input=text, cwd=Path(__file__).parent.parent,
                         capture_output=True, text=True, check=True).stdout
    assert out.strip() == str([(0, -1), (int(bar_17), 2)])
