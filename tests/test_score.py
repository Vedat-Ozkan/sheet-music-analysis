from fractions import Fraction

import pytest

from engine.render import load_toolkit
from engine.score import PositionError, ScoreIndex


@pytest.fixture(scope="module")
def index(chopin) -> ScoreIndex:
    return ScoreIndex(load_toolkit(chopin).getMEI())


def test_pickup_is_measure_zero(index):
    assert index.measures[0].number == 0
    assert index.measure(1).index == 2
    assert index.measure(1).beat_length == Fraction(3, 2)  # 12/8 counts in dotted quarters


def test_measure_range_includes_the_pickup(index):
    assert index.measure_range(1, 8) == "1-9"
    assert index.measure_range(3, 4) == "4-5"


def test_find_note_by_staff_and_pitch(index):
    note = index.find_note(1, 4, staff=2, pitch="D2")
    assert note.pitch == "D2" and note.onset == Fraction(9, 2)
    assert index.find_note(2, 3, staff=1, pitch="B-5").pitch == "Bb5"  # music21 spelling is accepted


def test_wrong_pitch_lists_what_is_there(index):
    with pytest.raises(PositionError, match=r"notes there: .*G5"):
        index.find_note(1, 1, staff=1, pitch="C5")


def test_wrong_beat_lists_where_notes_start(index):
    with pytest.raises(PositionError, match="notes start at beats"):
        index.find_note(1, 1.5)


def test_beat_outside_the_measure(index):
    with pytest.raises(PositionError, match="has no beat 5"):
        index.measure(1).offset_of(5)
    with pytest.raises(PositionError, match="does not exist"):
        index.measure(99)
