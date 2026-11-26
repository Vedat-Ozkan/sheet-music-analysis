from pathlib import Path

import pytest

from engine import annotate, output_checks
from engine.annotations import AnnotationList
from tests.test_awkward import SCORES

DATA = Path(__file__).parent / "data"
TALL = DATA / "users" / "tall"
CORPUS = sorted({*SCORES.values(), *DATA.glob("*.mxl"), *DATA.glob("*.musicxml")})


def printed_with_checks(path: Path, monkeypatch) -> tuple[list[list[int]], list[tuple[str, list[int]]]]:
    found, reported = [], []
    check = output_checks.systems_off_the_page
    monkeypatch.setattr(output_checks, "systems_off_the_page", lambda layouts: found.append(check(layouts)) or found[-1])
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
