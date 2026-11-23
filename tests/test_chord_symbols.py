import re
from pathlib import Path

import anyio
import pytest
from mcp.client.client import Client

from engine import read_pdf as pdf_reader
from engine import reduce
from engine.annotate import render
from engine.annotations import AnnotationList
from server import app

DATA = Path(__file__).parent / "data"
LEAD_SHEET = (DATA / "chord_symbols/amazing-grace-lead-sheet.musicxml").read_bytes()
NOCTURNE = (DATA / "chopin_nocturne_op9_no2.mxl").read_bytes()
PRINTED = ["G", "G7", "C", "G", "G", "Em", "D", "D7", "G", "G7", "C", "G", "G", "Em", "D7", "G"]


def printed_symbols(svg: str) -> list[str]:
    return [re.sub(r"<[^>]+>|\s", "", symbol) for symbol in re.findall(r'<g id="[^"]+" class="harm">(.*?)</text>', svg, re.S)]


def draft(score: bytes, code: str) -> str:
    app.store.put(f"scores/{code}", score)

    async def go():
        async with Client(app.mcp) as client:
            return await client.call_tool("draft_analysis", {"score_id": code})

    return " ".join(part.text for part in anyio.run(go).content if part.type == "text")


@pytest.fixture
def store(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "store", app.LocalStore(tmp_path))


def test_the_drawn_page_keeps_the_printed_chord_symbols_and_none_of_our_spacers():
    annotations = AnnotationList.model_validate({"annotations": [
        {"type": "harmony", "at": {"measure": bar, "beat": 1}, "label": label, **({"key": "G"} if bar == 1 else {})}
        for bar, label in ((1, "I"), (2, "I7"), (3, "IV"), (4, "I"), (6, "vi"), (7, "V"), (8, "V7"))]})
    page = render(LEAD_SHEET, annotations)
    shown = [symbol for svg in page.svgs for symbol in printed_symbols(svg)]
    assert shown == PRINTED
    assert not any("analysis-room" in svg for svg in page.svgs)


def test_the_reading_card_of_a_pdf_keeps_the_printed_chord_symbols():
    shown = [symbol for svg in pdf_reader.preview(LEAD_SHEET).svgs for symbol in printed_symbols(svg)]
    assert shown == PRINTED


def test_the_draft_lists_the_printed_chord_symbols_with_their_beats(store):
    text = draft(LEAD_SHEET, "LEADSHEET1")
    assert reduce.CHORD_SYMBOLS in text
    notes = text.split("\nNOTES (", 1)[1]
    assert "m2\n  b1 | bass B4 | B | staff 1: B4@1 | chord symbol G7@1\n" in notes
    assert "m13\n  b1 | bass G4 | G | staff 1: G4@1 | chord symbol G@1\n" in notes
    assert "  b3 | bass G4 | G B | staff 1: B4@3 G4@3.5 | chord symbol Em@3\nm14" in notes
    assert re.findall(r"chord symbol (\S+)@\d", notes) == PRINTED


def test_a_score_without_chord_symbols_gets_no_word_about_them(store):
    text = draft(NOCTURNE, "NOCTURNE1")
    assert reduce.CHORD_SYMBOLS not in text and "| chord symbol" not in text


def test_a_symbol_of_kind_none_prints_its_text_and_never_the_placeholder_root(store):
    harmonies = re.findall(r"<harmony>.*?</harmony>", LEAD_SHEET.decode())
    no_chord = LEAD_SHEET.decode().replace(harmonies[1], '<harmony><root><root-step>C</root-step></root><kind text="N.C.">none</kind></harmony>', 1)
    no_chord = no_chord.replace(harmonies[2], '<harmony><root><root-step>C</root-step></root><kind text="">none</kind></harmony>', 1).encode()
    expected = ["G", "N.C.", *PRINTED[3:]]
    assert [symbol for svg in render(no_chord, AnnotationList(annotations=[])).svgs for symbol in printed_symbols(svg)] == expected
    assert [symbol for svg in pdf_reader.preview(no_chord).svgs for symbol in printed_symbols(svg)] == expected
    assert re.findall(r"chord symbol (\S+)@\d", draft(no_chord, "NOCHORD1").split("\nNOTES (", 1)[1]) == expected


@pytest.mark.parametrize("name, shown", [
    ("musescore-roman", ["N6", "Ger65", "Fr43"]),
    ("musescore-mixed", ["N.C.", "Cmaj7", "Am", "H7", "C(add9)", "C7sus4", "Verse", "N.C.", "Cmaj7", "Am", "C"]),
])
def test_typed_numerals_stay_off_the_page_and_unparsed_labels_print_as_typed(name, shown):
    score = (DATA / f"check_analysis/{name}.musicxml").read_bytes()
    assert [symbol for svg in pdf_reader.preview(score).svgs for symbol in printed_symbols(svg)] == shown
