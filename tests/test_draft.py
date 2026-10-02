import json
from pathlib import Path

import pytest

from engine import draft
from engine.annotate import check
from engine.render import load_toolkit
from engine.score import ScoreIndex

RAW = Path(__file__).parent / "data" / "chopin_analysisgnn_raw.json"  # AnalysisGNN's saved output for the nocturne


@pytest.fixture(scope="module")
def index(chopin) -> ScoreIndex:
    return ScoreIndex(load_toolkit(chopin).getMEI())


@pytest.fixture(scope="module")
def result(index) -> draft.Draft:
    return draft.build(json.loads(RAW.read_text()), index)


@pytest.mark.parametrize(
    "args, expected",
    [
        (("1", "None", "major triad", 0, "Eb"), "I"),
        (("5", "6", "dominant seventh chord", 1, "Eb"), "V65/vi"),
        (("7", "5", "diminished seventh chord", 0, "Eb"), "viio7/V"),
        (("#7", "None", "diminished seventh chord", 2, "f"), "viio43"),
        (("2", "None", "half-diminished seventh chord", 1, "c"), "iiø65"),
        (("-2", "None", "major triad", 1, "c"), "bII6"),
        (("5", "5", "major triad", 0, "c"), "V/V"),
        (("-6", "None", "German augmented sixth chord", 0, "C"), "Ger65"),
    ],
)
def test_numeral_from_model_outputs(args, expected):
    assert draft.numeral(*args) == expected


def test_chords_of_the_opening(result):
    opening = {(chord.measure, chord.beat): chord.label for chord in result.chords if 1 <= chord.measure <= 4}
    assert opening[(1, 1.0)] == "I"
    assert opening[(2, 1.0)] == "V7/ii"  # the seventh arrives late in the arpeggio but still counts
    assert opening[(3, 1.0)] == "V7"
    assert opening[(3, 2.0)] == "V65/vi"
    assert opening[(3, 3.0)] == "vi"
    assert opening[(3, 4.0)] == "viio7/V"
    assert opening[(4, 3.0)] == "I"


def test_chord_rows_carry_the_notes_to_check_against(result):
    chord = next(chord for chord in result.chords if (chord.measure, chord.beat) == (3, 2.0))
    assert chord.bass == "B2" and set(chord.pitches) == {"B", "G", "D", "F"}
    assert chord.key == "Eb" and chord.beats == 1


def test_cadences_and_phrase_ends(result):
    assert [(mark.measure, mark.beat, mark.label) for mark in result.cadences[:2]] == [(4, 3.0, "PAC"), (8, 3.0, "PAC")]
    assert [(mark.measure, mark.beat) for mark in result.phrase_ends[:2]] == [(4, 3.0), (8, 3.0)]


def test_pickup_is_measure_zero_beat_one(result):
    assert (result.chords[0].measure, result.chords[0].beat) == (0, 1.0)


def test_whole_draft_resolves_against_the_score(result, index):
    check(draft.as_annotations(result), index)  # raises if any position or note is not in the score


def test_text_can_be_limited_to_a_range(result):
    text = draft.as_text(result, 3, 4)
    assert "m3 b2 | Eb | V65/vi" in text and "m4 b3 PAC" in text
    assert "m5 " not in text and "m2 " not in text


def test_misaligned_model_output_is_refused(index):
    raw = json.loads(RAW.read_text())
    raw["notes"]["pitch"] = ["C1"] * len(raw["notes"]["pitch"])
    with pytest.raises(draft.DraftError, match="line up"):
        draft.build(raw, index)
