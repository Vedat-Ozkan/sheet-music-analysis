import re
import xml.etree.ElementTree as ET

import anyio
import pytest
from mcp.client.client import Client

from engine import correct
from engine.render import load_toolkit
from engine.score import MEI, XML_ID, PositionError, ScoreIndex
from server import app

ATTRIBUTES = ("<attributes><divisions>1</divisions><time><beats>4</beats><beat-type>4</beat-type></time>"
              "<clef><sign>G</sign><line>2</line></clef></attributes>")
REST = '<note><rest measure="yes"/><duration>4</duration></note>'


def note(step: str, duration: int = 4, kind: str = "whole") -> str:
    return f"<note><pitch><step>{step}</step><octave>5</octave></pitch><duration>{duration}</duration><type>{kind}</type></note>"


def score(bars: list[tuple[str, str]]) -> bytes:
    return ('<?xml version="1.0" encoding="UTF-8"?><score-partwise version="4.0"><part-list><score-part id="P1">'
            '<part-name>P</part-name></score-part></part-list><part id="P1">'
            + "".join(f'<measure number="{number}">{content}</measure>' for number, content in bars)
            + "</part></score-partwise>").encode()


SECOND_ENDING = score([
    ("1", ATTRIBUTES + note("C")), ("2", note("D")),
    ("3", '<barline location="left"><ending number="1" type="start"/></barline>' + note("E")
     + '<barline location="right"><ending number="1" type="stop"/><repeat direction="backward"/></barline>'),
    ("X1", '<barline location="left"><ending number="2" type="start"/></barline>' + note("F")
     + '<barline location="right"><ending number="2" type="discontinue"/></barline>'),
    ("4", note("G")), ("5", note("A")),
])


def names(data: bytes, labelled_bars=()) -> list[str]:
    return re.findall(r'<measure\b[^>]*\bn="([^"]+)"', load_toolkit(data, labelled_bars=labelled_bars).getMEI())


@pytest.fixture
def ending(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "store", app.LocalStore(tmp_path))
    app.store.put("scores/ENDING", SECOND_ENDING)
    return "ENDING"


def call(name, arguments):
    async def go():
        async with Client(app.mcp) as client:
            return await client.call_tool(name, arguments)

    return anyio.run(go)


def text_of(result):
    return " ".join(part.text for part in result.content if part.type == "text")


def labelled(musicxml: bytes) -> dict[str, list[str]]:
    mei = load_toolkit(musicxml).getMEI()
    nodes = {node.get(XML_ID): node for node in ET.fromstring(mei).iter()}
    found = {}
    for bar in ScoreIndex(mei).measures:
        for event in bar.events:
            for verse in nodes[event.id].findall(f'{MEI}verse[@label="roman-analysis"]'):
                found.setdefault(bar.name, []).append("".join(verse.itertext()).strip())
    return found


def test_an_uncounted_second_ending_is_named_after_the_bar_before():
    assert [m.name for m in ScoreIndex(load_toolkit(SECOND_ENDING).getMEI()).measures] == ["1", "2", "3", "3a", "4", "5"]
    assert names(SECOND_ENDING) == ["1", "2", "3", "3a", "4", "5"]


def test_both_halves_of_a_bar_split_by_a_repeat_share_its_name():
    split = score([
        ("1", ATTRIBUTES + note("C")),
        ("2", note("D", 2, "half") + '<barline location="right"><bar-style>light-heavy</bar-style><repeat direction="backward"/></barline>'),
        ("X1", '<barline location="left"><bar-style>heavy-light</bar-style><repeat direction="forward"/></barline>' + note("E", 2, "half")),
        ("3", note("F")),
    ])
    index = ScoreIndex(load_toolkit(split).getMEI())
    assert [(m.name, len(m.segments)) for m in index.measures] == [("1", 1), ("2", 2), ("3", 1)]
    assert names(split) == ["1", "2", "2", "3"]


def test_the_notes_table_names_the_second_ending_as_printed(ending):
    text = text_of(call("draft_analysis", {"score_id": ending, "measure_range": "3-4"}))
    assert "The score has measures 1 to 5" in text
    assert re.findall(r"^m(\S+)", text.split("\nNOTES", 1)[1], re.M) == ["3", "3a", "4"]


def test_a_chord_placed_in_3a_is_drawn_in_that_bar(ending):
    annotations = {"annotations": [{"type": "harmony", "at": {"measure": "3a", "beat": 1}, "label": "I", "key": "C"},
                                   {"type": "harmony", "at": {"measure": 4, "beat": 1}, "label": "V"}]}
    result = call("render_analysis", {"score_id": ending, "annotations": annotations, "measure_range": "3a-4"})
    assert not result.is_error, text_of(result)
    assert result.structured_content["caption"].startswith("Analysis of bars 3a–4")
    name = result.structured_content["musicxml_url"].rsplit("/", 1)[1]
    assert labelled(app.store.get(f"files/{name}")) == {"3a": ["C: I"], "4": ["V"]}


def test_a_bar_name_the_score_lacks_is_left_out_with_the_names_it_has(ending):
    annotations = {"annotations": [{"type": "harmony", "at": {"measure": "3b", "beat": 1}, "label": "I", "key": "C"},
                                   {"type": "harmony", "at": {"measure": 3, "beat": 1}, "label": "V"}]}
    text = text_of(call("render_analysis", {"score_id": ending, "annotations": annotations}))
    assert "annotations[0] (harmony): Measure 3b does not exist; the score has measures 1 to 5" in text


def test_play_takes_and_gives_back_bar_names(ending):
    result = call("play", {"score_id": ending, "measure_range": "3a-4"})
    assert result.structured_content["measures"] == ["3a", 4]
    assert "run backwards" in text_of(call("play", {"score_id": ending, "measure_range": "4-3a"}))


def test_a_misread_3a_is_corrected_by_its_name(ending):
    shown = text_of(call("correct_bars", {"score_id": ending, "replacement_bars": "N1 div=1 ts=4/4 ks=0\nm3a len=1\n1.1: 1 C4"}))
    assert "current notes for measures 3a-3a" in shown
    current = correct.bars_from_musicxml(SECOND_ENDING, ScoreIndex(load_toolkit(SECOND_ENDING).getMEI()).bar("3a").number)
    assert current.splitlines()[1:] == ["m3a len=4", "1.1: 4 F5"]
    result = call("correct_bars", {"score_id": ending, "replacement_bars": current.replace("F5", "G5")})
    assert not result.is_error, text_of(result)
    assert result.structured_content["changed_bars"] == ["3a"]
    assert "Bar 3a:" in text_of(result)


def test_a_rest_split_for_a_labelled_bar_names_every_copy():
    rests = score([
        ("1", ATTRIBUTES + note("C")), ("2", '<barline location="left"><ending number="1" type="start"/></barline>' + note("C")),
        ("X1", '<barline location="left"><ending number="2" type="start"/></barline>' + note("C")),
        ("3", "<attributes><measure-style><multiple-rest>4</multiple-rest></measure-style></attributes>" + REST),
        ("4", REST), ("5", REST), ("6", REST), ("7", note("C")),
    ])
    index = ScoreIndex(load_toolkit(rests).getMEI())
    assert [measure.name for measure in index.measures] == ["1", "2", "2a", "3", "4", "5", "6", "7"]
    assert names(rests, [index.bar("6").number]) == ["1", "2", "2a", "3", "4", "5", "6", "7"]


def test_a_rest_after_a_pickup_the_file_numbers_1_is_split_only_for_a_bar_inside_it():
    rests = score([
        ("1", ATTRIBUTES + note("G", 1, "quarter")), ("2", note("C")),
        ("3", "<attributes><measure-style><multiple-rest>3</multiple-rest></measure-style></attributes>" + REST),
        ("4", REST), ("5", REST), ("6", note("C", 3, "half").replace("</type>", "</type><dot/>")),
    ])
    index = ScoreIndex(load_toolkit(rests).getMEI())
    assert [measure.name for measure in index.measures] == ["0", "1", "2", "3", "4", "5"]
    assert names(rests, [index.bar("4").number]) == ["0", "1", "2", "3", "4", "5"]
    assert names(rests, [index.bar("5").number]) == ["0", "1", "2", "5"]


def test_a_pickup_the_file_numbers_1_is_named_0_when_a_later_bar_is_uncounted():
    pickup = score([
        ("1", ATTRIBUTES + note("G", 1, "quarter")), ("2", note("C")),
        ("3", '<barline location="left"><ending number="1" type="start"/></barline>' + note("E")
         + '<barline location="right"><ending number="1" type="stop"/><repeat direction="backward"/></barline>'),
        ("X1", '<barline location="left"><ending number="2" type="start"/></barline>' + note("F")
         + '<barline location="right"><ending number="2" type="discontinue"/></barline>'),
        ("4", note("C", 3, "half").replace("</type>", "</type><dot/>")),
    ])
    assert [m.name for m in ScoreIndex(load_toolkit(pickup).getMEI()).measures] == ["0", "1", "2", "2a", "3"]


def test_an_unnumbered_opening_bar_that_would_repeat_a_later_name_is_named_by_count():
    opening = score([("X1", ATTRIBUTES + note("C")), ("1", note("D")), ("2", note("E"))])
    index = ScoreIndex(load_toolkit(opening).getMEI())
    assert index.named_by_count
    assert [m.name for m in index.measures] == ["1", "2", "3"]


def test_a_range_running_past_the_last_bar_stops_at_it(ending):
    text = text_of(call("draft_analysis", {"score_id": ending, "measure_range": "4-9"}))
    assert re.findall(r"^m(\S+)", text.split("\nNOTES", 1)[1], re.M) == ["4", "5"]
    assert call("play", {"score_id": ending, "measure_range": "4-9"}).structured_content["measures"] == [4, 5]
    annotations = {"annotations": [{"type": "harmony", "at": {"measure": 4, "beat": 1}, "label": "I", "key": "C"}]}
    drawn = call("render_analysis", {"score_id": ending, "annotations": annotations, "measure_range": "4-9"})
    assert drawn.structured_content["caption"].startswith("Analysis of bars 4–5"), drawn.structured_content["caption"]
    assert "Measure 9 does not exist" in text_of(call("play", {"score_id": ending, "measure_range": "9"}))
    assert "Measure 5a does not exist" in text_of(call("play", {"score_id": ending, "measure_range": "4-5a"}))


def test_a_range_inside_a_gap_in_the_printed_numbers_does_not_exist():
    gap = ScoreIndex(load_toolkit(score([("1", ATTRIBUTES + note("C")), ("2", note("D")), ("5", note("E")), ("6", note("F"))])).getMEI())
    for asked in (("3", "3"), ("3", "4")):
        with pytest.raises(PositionError, match="Measure 3 does not exist; the score has measures 1 to 6"):
            gap.numbers(asked)
    assert [gap.name_of(number) for number in gap.numbers(("2", "4"))] == ["2", "2"]
    assert [gap.name_of(number) for number in gap.numbers(("3", "6"))] == ["5", "6"]
    with pytest.raises(PositionError, match="Measures 6-3 run backwards"):
        gap.numbers(("6", "3"))


def two_parts(bars: list[tuple[str, str, str]]) -> bytes:
    parts = "".join(
        f'<part id="P{part}">' + "".join(f'<measure number="{number}"{extra}>{content}</measure>'
                                       for number, extra, content in bars) + "</part>"
        for part in (1, 2))
    return ('<?xml version="1.0" encoding="UTF-8"?><score-partwise version="4.0"><part-list>'
            '<score-part id="P1"><part-name>Violin</part-name></score-part>'
            '<score-part id="P2"><part-name>Violoncello</part-name></score-part></part-list>'
            + parts + "</score-partwise>").encode()


ENSEMBLE = two_parts([
    ("1", "", ATTRIBUTES + note("C")), ("2", "", note("D", 3, "half").replace("</type>", "</type><dot/>")
                                         + '<barline location="right"><repeat direction="backward"/></barline>'),
    ("X1", ' implicit="yes"', '<barline location="left"><repeat direction="forward"/></barline>' + note("E", 1, "quarter")),
    ("3", "", '<barline location="left"><ending number="1" type="start"/></barline>' + note("F")
     + '<barline location="right"><ending number="1" type="stop"/><repeat direction="backward"/></barline>'),
    ("X2", "", '<barline location="left"><ending number="2" type="start"/></barline>' + note("G")
     + '<barline location="right"><ending number="2" type="discontinue"/></barline>'),
    ("4", "", note("A")), ("5", "", note("B")),
])


@pytest.mark.parametrize("passage", [None, ("3a", "5")])
def test_a_piano_reduction_keeps_the_bars_and_draws_their_printed_names(passage):
    from engine.annotate import _piano_version
    from engine.annotations import AnnotationList

    original = ScoreIndex(load_toolkit(ENSEMBLE).getMEI())
    assert [(m.name, len(m.segments)) for m in original.measures] == [("1", 1), ("2", 2), ("3", 1), ("3a", 1), ("4", 1), ("5", 1)]
    measures = original.numbers(passage)
    reduced, _, bar_names = _piano_version(ENSEMBLE, AnnotationList(annotations=[]), measures)
    page = ScoreIndex(load_toolkit(reduced, bar_names=bar_names).getMEI())
    shown = original.measures[original.measures.index(original.measure(measures[0])):] if measures else original.measures
    assert [(m.number, m.name, m.length) for m in page.measures] == [(m.number, m.name, m.length) for m in shown]
