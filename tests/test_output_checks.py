import json
import re
from pathlib import Path

import pytest

from engine import annotate, output_checks
from engine.annotations import AnnotationList
from engine.render import load_toolkit
from engine.score import ScoreIndex
from tests.test_awkward import SCORES

DATA = Path(__file__).parent / "data"
TALL = DATA / "users" / "tall"
CORPUS = sorted({*SCORES.values(), *DATA.glob("*.mxl"), *DATA.glob("*.musicxml")})


def printed_with_checks(path: Path, monkeypatch) -> tuple[list[list[int]], list[tuple[str, list[int]]]]:
    found, reported = [], []
    tallest = output_checks.tallest_system
    monkeypatch.setattr(output_checks, "tallest_system", lambda layouts: found.append(output_checks.systems_off_the_page(layouts)) or tallest(layouts))
    monkeypatch.setattr(output_checks, "report", lambda rule, pages: reported.append((rule, pages)))
    annotate.render(path.read_bytes(), AnnotationList(annotations=[])).print_pages()
    return found, reported


@pytest.mark.parametrize("path", CORPUS, ids=lambda path: path.stem)
def test_every_printed_system_lies_inside_its_page(path, monkeypatch):
    _, reported = printed_with_checks(path, monkeypatch)
    assert reported == [(output_checks.SYSTEM_INSIDE_PAGE, [])]


@pytest.mark.parametrize("name", ["5e1094-orchestra", "4a3d12-orchestra", "9315e5-band"])
def test_a_system_taller_than_the_page_is_fitted_onto_it(name, monkeypatch):
    path = TALL / f"{name}.musicxml"
    if not path.exists():
        pytest.skip(f"{path} is a user's file kept out of the repository")
    found, reported = printed_with_checks(path, monkeypatch)
    assert found[0] != [] and reported == [(output_checks.SYSTEM_INSIDE_PAGE, [])]


ANALYSED = {
    "mozart-k545-1": (DATA / "mozart-k545-1-simulated-scan-reading.musicxml", DATA / "analyses" / "mozart-k545-1-sonnet.json"),
    "bach-bwv404": (DATA / "part_writing_bwv404.musicxml", DATA / "check_display" / "bach-reviewed.json"),
}


@pytest.mark.parametrize("name", list(ANALYSED))
def test_printing_a_real_analysis_never_takes_more_pages_than_its_layout_before_the_fit(name, monkeypatch):
    score_path, analysis_path = ANALYSED[name]
    score = score_path.read_bytes()
    index = ScoreIndex(load_toolkit(score).getMEI())
    annotations = AnnotationList.model_validate({"annotations": json.loads(analysis_path.read_text())["annotations"]})
    laid_out = []
    tallest = output_checks.tallest_system
    monkeypatch.setattr(output_checks, "tallest_system", lambda layouts: laid_out.append(len(layouts)) or tallest(layouts))
    engraving, _, _ = annotate.leave_out_rejected(lambda kept: annotate.render(score, kept, key=True), annotations,
                                                  lambda given: annotate.by_number(given, index))
    printed = engraving.print_pages()
    assert len(printed) <= laid_out[0]


@pytest.mark.parametrize("path", CORPUS, ids=lambda path: path.stem)
def test_no_system_break_is_drawn_inside_an_ending(path, monkeypatch):
    balanced, laid_out = annotate._balance_systems, []

    def balance(toolkit, *rest):
        balanced(toolkit, *rest)
        laid_out.append(toolkit.getMEI())

    monkeypatch.setattr(annotate, "_balance_systems", balance)
    annotate.render(path.read_bytes(), AnnotationList(annotations=[]))
    assert laid_out and not re.search(r"<ending\b[^>]*>\s*<sb\b", laid_out[0])
