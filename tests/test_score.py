from fractions import Fraction

import io
import zipfile

import pytest

from engine import notes
from engine.render import ScoreError, load_toolkit
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


def test_a_voice_written_twice_in_one_bar_becomes_two_voices():
    voice_one = '<note><pitch><step>{}</step><octave>{}</octave></pitch><duration>4</duration><voice>1</voice><type>whole</type></note>'
    score = f'''<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0"><part-list><score-part id="P1"><part-name>P</part-name></score-part></part-list>
<part id="P1"><measure number="1"><attributes><divisions>1</divisions><time><beats>4</beats><beat-type>4</beat-type></time>
<clef><sign>G</sign><line>2</line></clef></attributes>{voice_one.format("C", 5)}<backup><duration>4</duration></backup>{voice_one.format("E", 4)}
</measure></part></score-partwise>'''.encode()
    events = ScoreIndex(load_toolkit(score).getMEI()).measures[0].events
    assert sorted((event.pitch, event.onset) for event in events) == [("C5", 0), ("E4", 0)]


def mxl(container: str | None, score: bytes) -> bytes:
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        if container is not None:
            archive.writestr("META-INF/container.xml", container)
        archive.writestr("score.xml", score)
    return data.getvalue()


def test_an_mxl_container_is_read_as_xml():
    container = "<container><rootfiles><rootfile full-path = 'score.xml'/></rootfiles></container>"
    assert ScoreIndex(load_toolkit(mxl(container, one_bar("", "C4"))).getMEI()).measures[0].events[0].pitch == "C4"


@pytest.mark.parametrize("data", [mxl(None, one_bar("", "C4")), b"PK\x03\x04 not a zip"])
def test_a_broken_mxl_is_refused_as_not_musicxml(data):
    with pytest.raises(ScoreError, match="not MusicXML"):
        load_toolkit(data)


def test_a_huge_mxl_container_is_refused_before_it_is_unpacked():
    container = "<container>" + " " * (50 * 1024 * 1024) + "</container>"
    with pytest.raises(ScoreError, match="larger than 50 MB"):
        load_toolkit(mxl(container, one_bar("", "C4")))


def test_an_empty_duration_does_not_stop_the_score_loading():
    score = one_bar("", "C4").replace(b"<duration>4</duration>", b"<duration/>")
    assert load_toolkit(score).getMEI()
