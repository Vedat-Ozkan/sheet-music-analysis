import json
from datetime import datetime, timezone
from pathlib import Path

import anyio
import pytest
from mcp.client.client import Client

from engine import draft
from engine import read_pdf as pdf_reader
from server import app

DATA = Path(__file__).parent / "data"
PDF = (DATA / "chopin-28-4-mutopia.pdf").read_bytes()
READING = (DATA / "chopin_prelude_op28_no4_reading.musicxml").read_bytes()
NOCTURNE = (DATA / "chopin_nocturne_op9_no2.mxl").read_bytes()
ATTACHED = {"pdf_file": {"download_url": "https://example.com/score.pdf", "file_id": "file-1"}}


@pytest.fixture
def server(monkeypatch, tmp_path):
    async def download(url):
        return PDF

    def read(data):
        return pdf_reader.PdfReading(READING, 1, False, [], [{"setting": 0, "outcome": "done"}])

    monkeypatch.setattr(app, "store", app.LocalStore(tmp_path))
    monkeypatch.setattr(app, "download", download)
    monkeypatch.setattr(app.pdf_reader, "read_pdf", read)
    return app.store


def call(name, arguments):
    async def go():
        async with Client(app.mcp) as client:
            return await client.call_tool(name, arguments)

    return anyio.run(go)


def text_of(result):
    return " ".join(part.text for part in result.content if part.type == "text")


def charged(store, kind):
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    raw = store.get(f"usage/{day}.json")
    return json.loads(raw).get(kind, 0) if raw else 0


def score_id_of(result):
    return text_of(result).split("score_id: ", 1)[1].split()[0]


def test_a_pdf_reading_states_its_bars_so_the_model_can_ask_for_real_ranges(server):
    result = call("read_pdf", ATTACHED)
    assert "The score has measures 0 to 24" in text_of(result)


def test_drawing_with_no_marks_tells_the_model_to_analyse_first(server):
    score_id = score_id_of(call("read_pdf", ATTACHED))
    result = call("render_analysis", {"score_id": score_id, "annotations": {"annotations": []}, "measure_range": "1-4"})
    assert not result.is_error
    assert "call draft_analysis with score_id" in text_of(result)


def test_marks_that_fit_are_drawn_and_the_rest_are_listed(server):
    score_id = score_id_of(call("read_pdf", ATTACHED))
    marks = [{"type": "harmony", "at": {"measure": 1, "beat": 1}, "label": "i", "key": "e"},
             {"type": "harmony", "at": {"measure": 99, "beat": 1}, "label": "V"}]
    result = call("render_analysis", {"score_id": score_id, "annotations": {"annotations": marks}, "measure_range": "1-4"})
    assert not result.is_error
    assert "annotations[1] (harmony): Measure 99 does not exist" in text_of(result)


def test_a_range_longer_than_a_page_draws_the_first_32_bars(server):
    server.put("scores/NOCTURNE", NOCTURNE)
    result = call("render_analysis", {"score_id": "NOCTURNE", "annotations": {"annotations": []}})
    assert not result.is_error
    assert "This page shows measures 0-32" in text_of(result)
    assert "measures 0-32" in result.structured_content["caption"]


def test_a_request_turned_away_before_any_work_is_not_charged(server):
    result = call("render_analysis", {"score_id": "NOSUCHSCORE", "annotations": {"annotations": []}})
    assert result.is_error and "No score has the id" in text_of(result)
    assert charged(server, "render") == 0


def test_when_the_draft_model_fails_the_notes_table_still_comes_back(server, monkeypatch):
    def broken(*args):
        raise draft.DraftError("AnalysisGNN failed: injected")

    monkeypatch.setitem(app.draft.MODELS, "analysisgnn", broken)
    score_id = score_id_of(call("read_pdf", ATTACHED))
    result = call("draft_analysis", {"score_id": score_id, "measure_range": "1-4"})
    assert not result.is_error
    assert "DRAFT UNAVAILABLE" in text_of(result) and "NOTES (one row per beat" in text_of(result)


def test_a_failed_correction_shows_the_bars_as_they_are_now(server):
    score_id = score_id_of(call("read_pdf", ATTACHED))
    result = call("correct_bars", {"score_id": score_id, "replacement_bars": "N1 div=24 ts=2/2 ks=1\nm3 len=96\n1.1: 24 C4\n"})
    assert result.is_error
    assert "The score's current notes for measures 3-3" in text_of(result)
    assert "\nm3 len=" in text_of(result)


def test_a_pdf_that_cannot_be_read_says_what_to_try_next(server, monkeypatch):
    def unreadable(data):
        raise pdf_reader.ReadError("No music could be read from this PDF", [{"setting": 0, "outcome": "no music"}])

    monkeypatch.setattr(app.pdf_reader, "read_pdf", unreadable)
    result = call("read_pdf", ATTACHED)
    assert result.is_error and "a MusicXML file" in text_of(result)


def test_a_mark_beyond_the_bars_that_fit_is_left_off_the_page(server):
    server.put("scores/NOCTURNE", NOCTURNE)
    marks = [{"type": "harmony", "at": {"measure": 1, "beat": 1}, "label": "I", "key": "Eb"},
             {"type": "harmony", "at": {"measure": 35, "beat": 1}, "label": "V"}]
    result = call("render_analysis", {"score_id": "NOCTURNE", "annotations": {"annotations": marks}})
    assert not result.is_error
    assert "This page shows measures 0-32" in text_of(result)


def test_numbers_of_marks_left_out_refer_to_the_list_the_model_sent(server):
    score_id = score_id_of(call("read_pdf", ATTACHED))
    marks = [{"type": "harmony", "at": {"measure": 99, "beat": 1}, "label": "V"},
             {"type": "harmony", "at": {"measure": 1, "beat": 1}, "label": "i", "key": "e"},
             {"type": "harmony", "at": {"measure": 98, "beat": 1}, "label": "V"}]
    result = call("render_analysis", {"score_id": score_id, "annotations": {"annotations": marks}, "measure_range": "1-4"})
    assert "annotations[0] (harmony): Measure 99" in text_of(result)
    assert "annotations[2] (harmony): Measure 98" in text_of(result)
