import dataclasses
from pathlib import Path

import anyio
from mcp.client.client import Client

from engine import read_pdf as pdf_reader
from server import app

TABS = Path(__file__).parent / "data" / "tabs"
ATTACHED = {"pdf_file": {"download_url": "https://example.com/score.pdf", "file_id": "file-1"}}


def read_through_the_server(monkeypatch, tmp_path, data: bytes, reader=None):
    async def download(url):
        return data

    monkeypatch.setattr(app, "store", app.LocalStore(tmp_path))
    monkeypatch.setattr(app, "download", download)
    if reader:
        monkeypatch.setattr(app.pdf_reader, "read_pdf", reader)

    async def call():
        async with Client(app.mcp) as client:
            return await client.call_tool("read_pdf", ATTACHED)

    result = anyio.run(call)
    return " ".join(part.text for part in result.content if part.type == "text"), result.structured_content


def test_a_tablature_pdf_is_read_from_its_fret_numbers_with_its_printed_tuning(monkeypatch, tmp_path):
    text, card = read_through_the_server(monkeypatch, tmp_path, (TABS / "bwv245-40-drop-d.pdf").read_bytes())
    assert "score_id" in text and "measures 0 to 28" in text and card["shaded_bars"] == []
    assert "with the tuning printed on it (D A D G B E)" in text


def test_a_tablature_bar_whose_lengths_were_guessed_is_shaded_like_a_misread_bar(monkeypatch, tmp_path):
    data = (TABS / "greensleeves.pdf").read_bytes()
    read = pdf_reader.read_pdf(data)
    doubtful = dataclasses.replace(read, tablature={**read.tablature, "doubtful": [3]})
    text, card = read_through_the_server(monkeypatch, tmp_path, data, lambda _: doubtful)
    assert card["shaded_bars"] == [3]
    assert "Bar 3 (shaded)" in text and "in standard guitar tuning (E A D G B E)" in text


def test_signs_left_out_and_a_tuning_not_followed_are_told_to_the_user(monkeypatch, tmp_path):
    text, card = read_through_the_server(monkeypatch, tmp_path, (TABS / "review/f1-grace-notes.pdf").read_bytes())
    assert "Bar 1 holds signs on the strings that change a note and were not read" in text and 1 in card["shaded_bars"]
    assert "look misread" not in text
    text, _ = read_through_the_server(monkeypatch, tmp_path / "words", (TABS / "review/f6-eb-standard-words.pdf").read_bytes())
    assert ("assuming standard guitar tuning (E A D G B E), because the page gives no tuning this reading can follow. If the "
            "piece uses another tuning, the notes on the retuned strings are wrong here.") in text
    assert "No capo is counted. Slides, bends, hammer-ons and pull-offs" in text


def test_tablature_outside_the_scope_is_answered_at_once_without_the_slow_reader(monkeypatch, tmp_path):
    def slow_reader(*_):
        raise AssertionError("the slow reader was started")

    monkeypatch.setattr(app.pdf_reader, "_read_with_every_setting", slow_reader)
    text, _ = read_through_the_server(monkeypatch, tmp_path, (TABS / "review/d4-duet.pdf").read_bytes())
    assert "This tablature can't be read: each line of music has more than one staff, for example two instruments" in text
