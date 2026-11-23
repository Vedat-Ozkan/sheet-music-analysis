import re
from pathlib import Path


from engine import read_pdf as pdf_reader
from engine.annotate import render
from engine.annotations import AnnotationList

DATA = Path(__file__).parent / "data"
LEAD_SHEET = (DATA / "chord_symbols/amazing-grace-lead-sheet.musicxml").read_bytes()
PRINTED = ["G", "G7", "C", "G", "G", "Em", "D", "D7", "G", "G7", "C", "G", "G", "Em", "D7", "G"]


def printed_symbols(svg: str) -> list[str]:
    return [re.sub(r"<[^>]+>|\s", "", symbol) for symbol in re.findall(r'<g id="[^"]+" class="harm">(.*?)</text>', svg, re.S)]


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
