from fractions import Fraction

import pytest

from engine.render import load_toolkit
from engine.score import PositionError, ScoreIndex
from tools.robustness import CORPUS


@pytest.fixture(scope="module")
def index(chopin) -> ScoreIndex:
    return ScoreIndex(load_toolkit(chopin).getMEI())


def test_the_key_signature_is_the_concert_one_when_the_top_staff_transposes():
    weber = ScoreIndex(load_toolkit((CORPUS / "weber/concertino_clarinet.mxl").read_bytes()).getMEI())
    assert weber.key_signature == "3f"
    assert {measure.key_signature for measure in weber.measures[:20]} == {"3f"}


def test_pickup_is_measure_zero(index):
    assert index.measures[0].number == 0
    assert index.measure(1).index == 2
    assert index.measure(1).beat_length == Fraction(3, 2)


def test_measure_range_includes_the_pickup(index):
    assert index.measure_range(1, 8) == "1-9"
    assert index.measure_range(3, 4) == "4-5"


def test_find_note_by_staff_and_pitch(index):
    note = index.find_note(1, 4, staff=2, pitch="D2")
    assert note.pitch == "D2" and note.onset == Fraction(9, 2)
    assert index.find_note(2, 3, staff=1, pitch="B-5").pitch == "Bb5"


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


def test_unmarked_pickup_numbered_one_becomes_measure_zero(chopin):
    import re, zipfile, io
    archive = zipfile.ZipFile(io.BytesIO(chopin))
    name = next(n for n in archive.namelist() if not n.startswith("META"))
    text = archive.read(name).decode()
    text = re.sub(r'<measure number="(\d+)"( implicit="yes")?', lambda m: f'<measure number="{int(m.group(1)) + 1}"', text)
    toolkit = load_toolkit(text.encode())
    index = ScoreIndex(toolkit.getMEI())
    assert [measure.number for measure in index.measures[:3]] == [0, 1, 2]
    assert index.measure_range(1, 8) == "1-9"
    original = ScoreIndex(load_toolkit(chopin).getMEI())
    assert [measure.number for measure in index.measures] == [measure.number for measure in original.measures]
    assert re.findall(r'<measure\b[^>]*\bn="(\d+)"', toolkit.getMEI()) == re.findall(r'<measure\b[^>]*\bn="(\d+)"', load_toolkit(chopin).getMEI())
