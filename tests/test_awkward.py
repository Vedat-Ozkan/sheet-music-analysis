import re
import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path

import pytest

from engine import correct, draft, notes
from engine.annotate import render
from engine.annotations import AnnotationList
from engine.check_analysis import ClarificationNeeded, from_text
from engine.export import _document, export_musicxml
from engine.part_writing import applies, as_text, check
from engine.read_pdf import problem_spots
from engine.render import load_toolkit
from engine.score import ScoreIndex

DATA = Path(__file__).parent / "data"
SCORES = {
    "pickup-repeat-split": DATA / "part_writing_bwv303.musicxml",
    "key-change-tuplets": DATA / "triplet_brahms_fruhlingstrost.musicxml",
    "compound-6-8-grace": DATA / "export-mozart-k458.musicxml",
    "compound-9-8": DATA / "export-debussy-clair.musicxml",
    "tuplets-6-8": DATA / "triplet_hensel.musicxml",
    "tuplets-4-4": DATA / "triplet_mayer.musicxml",
    "grace-mixed-meter": DATA / "chopin_nocturne_op9_no2.mxl",
    "cross-staff": DATA / "export-brahms-118-2.musicxml",
    "two-parts": DATA / "cadential_64.musicxml",
    "four-parts-pickup": DATA / "part_writing_motion.musicxml",
    "pdf-reading-prelude": DATA / "chopin_prelude_op28_no4_reading.musicxml",
    "pdf-reading-overrun": DATA / "awkward" / "kinkel-op8-5-trennung-reading.musicxml",
}
KNOWN: dict[tuple[str, str], str] = {
    ("model_notes", "key-change-tuplets"): "notes in its last bar run past the bar's length, so the model refuses the score",
}

score_ids = pytest.mark.parametrize("name", list(SCORES))


def known(request, test, name):
    if reason := KNOWN.get((test, name)):
        request.applymarker(pytest.mark.xfail(reason=reason, strict=False))


def load(name):
    data = SCORES[name].read_bytes()
    return data, ScoreIndex(load_toolkit(data).getMEI())


@score_ids
def test_index_loads(name):
    _, index = load(name)
    assert index.measures


@score_ids
def test_problem_spots(name):
    data, _ = load(name)
    bars, _ = problem_spots(_document(data))
    assert all(isinstance(bar, int) for bar in bars)


@score_ids
def test_export_trivial_analysis(request, name):
    known(request, "export", name)
    data, index = load(name)
    first = index.measures[0]
    analysis = {"annotations": [{"type": "harmony", "at": {"measure": first.number, "beat": 1}, "key": "C", "label": "I"}]}
    assert export_musicxml(data, analysis)


@score_ids
def test_part_writing(request, name):
    known(request, "part_writing", name)
    _, index = load(name)
    if applies(index):
        check(index)
        as_text(index)


@score_ids
def test_engrave_a_range(request, name):
    known(request, "engrave", name)
    data, index = load(name)
    numbers = [m.number for m in index.measures if m.number > 0]
    first, last = numbers[0], numbers[min(3, len(numbers) - 1)]
    notes = AnnotationList.model_validate(
        {"annotations": [{"type": "harmony", "at": {"measure": first, "beat": 1}, "key": "C", "label": "I"}]})
    assert render(data, notes, measures=(first, last)).png(1)


@score_ids
def test_correct_roundtrip(request, name):
    known(request, "correct_roundtrip", name)
    data, index = load(name)
    part = ET.fromstring(_document(data)).find("part").get("id")
    flagged = problem_spots(_document(data))[0]
    numbers = [m.number for m in index.measures]
    failures = []
    for bar in dict.fromkeys([numbers[0], numbers[-1], *flagged[:4]]):
        try:
            correct.replace_bars(data, correct.bars_from_musicxml(data, bar, part=part), part=part)
        except Exception as error:
            failures.append(f"bar {bar}: {type(error).__name__}: {error}")
    assert not failures, failures


@score_ids
def test_model_hears_every_note_once(request, name):
    known(request, "model_notes", name)
    _, index = load(name)
    text = notes.encode(index)
    expected, held, start = 0, {}, Fraction(0)
    for measure in notes.decode(text).measures:
        for event in measure.events:
            if not event.pitch or event.grace:
                continue
            begin = start + event.onset
            if held.pop((event.staff, event.pitch), None) != begin:
                expected += 1
            if event.tied:
                held[(event.staff, event.pitch)] = begin + event.duration
        start += measure.length
    raw = draft.MODELS["analysisgnn"](text.encode(), "notes")
    assert sum(1 for duration in raw["notes"]["duration"] if duration > 0) == expected



@score_ids
def test_note_list_keeps_every_bar_key(name):
    _, index = load(name)
    decoded = notes.decode(notes.encode(index))
    assert [m.key_signature or "0" for m in decoded.measures] == [m.key_signature or "0" for m in index.measures]


TYPED = [line for line in (DATA / "awkward" / "typed.txt").read_text().splitlines() if line.strip()]


def test_typed_answers_are_plentiful():
    assert len(TYPED) >= 40


@pytest.mark.parametrize("line", TYPED)
def test_typed_answer_parses_or_asks(line):
    try:
        labels = from_text(line)
    except ClarificationNeeded:
        return
    assert labels and all(re.fullmatch(r"\S+", label.figure) for label in labels)
