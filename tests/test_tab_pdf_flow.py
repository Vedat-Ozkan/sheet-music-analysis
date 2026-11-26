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
