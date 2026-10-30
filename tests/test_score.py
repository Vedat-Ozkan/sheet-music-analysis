from fractions import Fraction

import pytest

from engine import notes
from engine.render import load_toolkit
from engine.score import PositionError, ScoreIndex


@pytest.fixture(scope="module")
def index(chopin) -> ScoreIndex:
    return ScoreIndex(load_toolkit(chopin).getMEI())


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


def one_bar(attributes: str, pitch: str) -> bytes:
    step, octave = pitch[0], pitch[-1]
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0"><part-list><score-part id="P1"><part-name>P</part-name></score-part></part-list>
<part id="P1"><measure number="1"><attributes><divisions>1</divisions>{attributes}<clef><sign>G</sign><line>2</line></clef></attributes>
<note><pitch><step>{step}</step><octave>{octave}</octave></pitch><duration>4</duration><type>whole</type></note>
</measure></part></score-partwise>'''.encode()


def test_baritone_saxophone_sounds_an_octave_and_a_sixth_down():
    transpose = "<transpose><diatonic>-5</diatonic><chromatic>-9</chromatic><octave-change>-1</octave-change></transpose>"
    index = ScoreIndex(load_toolkit(one_bar(transpose, "C5")).getMEI())
    assert index.measures[0].events[0].pitch == "Eb3"


def test_score_without_a_time_signature_survives_the_note_list():
    index = ScoreIndex(load_toolkit(one_bar("", "C4")).getMEI())
    assert index.meter == ""
    decoded = notes.decode(notes.encode(index))
    assert decoded.measures[0].events[0].pitch == "C4"
