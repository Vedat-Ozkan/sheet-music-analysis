import copy
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from engine import correct, notes
from engine.read_pdf import clean, problem_spots, without_slurs
from engine.render import engrave, load_toolkit
from engine.score import ScoreIndex

DATA = Path(__file__).parent / "data/chopin_prelude_op28_no4_audiveris.mxl"
TRUTH = Path(__file__).parents[1] / "spike/omr/truth/chopin-prelude-4.mxl"


def index(score):
    return ScoreIndex(load_toolkit(score).getMEI())


def summary(bar):
    return sorted((e.staff, e.layer, e.onset, e.duration, e.pitch, e.grace) for e in bar.events if e.pitch)


def correction_text():
    truth = TRUTH.read_bytes()
    first = correct.bars_from_musicxml(truth, 12)
    second = correct.bars_from_musicxml(truth, 16)
    return first + "\n" + "\n".join(second.splitlines()[1:])


def test_correct_real_reading():
    reading = without_slurs(clean(DATA.read_bytes()))
    result = correct.replace_bars(reading, correction_text())
    before, after, truth = index(reading), index(result), index(TRUTH.read_bytes())
    for bar in after.measures:
        expected = truth if bar.number in {12, 16} else before
        assert summary(bar) == summary(expected.measure(bar.number))
    assert 12 in problem_spots(reading)[0]
    assert 12 not in problem_spots(result)[0]
    assert engrave(result).page_count > 0
    assert engrave(result, (12, 16)).png().startswith(b"\x89PNG")
    # Apart from the necessary units rescaling, other bars retain every XML field.
    a, b = ET.fromstring(reading), ET.fromstring(result)
    for old, new in zip(a.findall("part/measure"), b.findall("part/measure")):
        if int(old.get("number")) in {12, 16}:
            continue
        old = copy.deepcopy(old)
        for element in old.iter():
            if element.tag in {"divisions", "duration"}:
                element.text = str(int(element.text) * 6)
        assert ET.tostring(old) == ET.tostring(new)


def test_bad_total_and_unknown_bar():
    reading = clean(DATA.read_bytes())
    with pytest.raises(correct.CorrectionError, match="adds up"):
        correct.replace_bars(reading, "N1 div=1 ts=2/2 ks=1s\nm12 len=4\n1.1: 1 C4\n2.1: 4 r")
    with pytest.raises(correct.CorrectionError, match="does not exist"):
        correct.replace_bars(reading, "N1 div=1 ts=2/2 ks=1s\nm99 len=4\n1.1: 4 C4\n2.1: 4 r")


def score():
    return b'''<score-partwise version="4.0"><part-list>
    <score-part id="P1"><part-name>Piano</part-name></score-part>
    <score-part id="P2"><part-name>Other</part-name></score-part></part-list>
    <part id="P1"><measure number="0" implicit="yes"><attributes><divisions>1</divisions><key><fifths>1</fifths></key><time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>G</sign><line>2</line></clef></attributes><note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration><tie type="start"/><type>quarter</type><notations><tied type="start"/><slur type="start" number="1"/></notations></note></measure>
    <measure number="1"><note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><tie type="stop"/><type>whole</type><notations><tied type="stop"/><slur type="stop" number="1"/></notations></note></measure></part>
    <part id="P2"><measure number="1"><attributes><divisions>1</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes><note><rest/><duration>4</duration><type>whole</type></note></measure></part></score-partwise>'''


def test_pickup_part_attributes_and_boundary_marks():
    original = score()
    with pytest.raises(correct.CorrectionError, match="Choose a part"):
        correct.bars_from_musicxml(original, 0)
    text = correct.bars_from_musicxml(original, 0, part="P1")
    assert "m0 len=1" in text
    result = correct.replace_bars(original, text.replace("C4~", "D4"), part="P1")
    a, b = ET.fromstring(original), ET.fromstring(result)
    assert ET.tostring(a.findall("part")[1]) == ET.tostring(b.findall("part")[1])
    assert ET.tostring(a.find("part/measure/attributes")) == ET.tostring(b.find("part/measure/attributes"))
    assert b.find(".//tie") is None
    assert b.find(".//slur") is None
    assert summary(index(result).measure(0))[0][4] == "D4"


def test_explicit_rest_only_voice_and_duplicate_voice():
    original = score()
    text = "N1 div=1 ts=4/4 ks=1s\nm1 len=4\n1.1: 4 r"
    result = correct.replace_bars(original, text, part="P1")
    assert ET.fromstring(result).findall("part")[0].findall("measure")[1].find("note/rest") is not None
    with pytest.raises(correct.CorrectionError, match="repeated voice"):
        correct.replace_bars(original, text + "\n1.1: 4 C4", part="P1")


def test_internal_ties_trailing_rests_and_terminal_ties():
    text = "N1 div=1 ts=4/4 ks=1s\nm1 len=4\n1.1: 1 C4~ C4 2 D4~"
    result = correct.replace_bars(score(), text, part="P1")
    events = [e for e in index(result).measure(1).events if e.pitch]
    assert [(e.pitch, e.tied) for e in events] == [("C4", True), ("C4", False), ("D4", False)]
    text = correct.bars_from_musicxml(TRUTH.read_bytes(), 12)
    assert "2.1: 24 B2+D#3+A3 72 r" in text
    assert all(v.duration > 0 for v in notes.decode(text).measure(12).events)


@pytest.mark.parametrize("text, message", [
    ("N1 div=0 ts=4/4 ks=0\nm1 len=4\n1.1: 4 C4", "positive"),
    ("N1 div=1 ts=4/4 ks=0\nm1 len=4\n1.1: C4", "no duration"),
    ("N1 div=1 ts=4/4 ks=0\nm1 len=4\n1.1: 0 C4", "positive"),
    ("N1 div=1 ts=4/4 ks=0\nm1 len=4\n2.1: 4 C4", "all 1 staves"),
])
def test_invalid_voice_data(text, message):
    with pytest.raises(correct.CorrectionError, match=message):
        correct.replace_bars(score(), text, part="P1")


def test_replace_bars_survives_notes_running_past_the_bar_end():
    # Bar 2 of 3/4 holds quarter, quarter and three eighths: a triplet typed without its tuplet.
    score = (Path(__file__).parent / "data/correct_missed_triplet.musicxml").read_bytes()
    text = correct.bars_from_musicxml(score, 2)
    result = correct.replace_bars(score, text.replace("F5", "E5"))
    assert correct.bars_from_musicxml(result, 2) == text.replace("F5", "E5")
