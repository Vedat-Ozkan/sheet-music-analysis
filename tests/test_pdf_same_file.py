import threading
import time
from pathlib import Path

import anyio
from mcp.client.client import Client

from engine import read_pdf as pdf_reader
from server import app

DATA = Path(__file__).parent / "data"
PDF = (DATA / "chopin-28-4-mutopia.pdf").read_bytes()
READING = (DATA / "chopin_prelude_op28_no4_reading.musicxml").read_bytes()
ATTACHED = {"pdf_file": {"download_url": "https://example.com/score.pdf", "file_id": "file-1"}}


def slow_reader(monkeypatch, tmp_path, seconds):
    reads = []

    def read(data):
        reads.append(threading.get_ident())
        time.sleep(seconds)
        return pdf_reader.PdfReading(READING, 1, False, [], [{"setting": 0, "outcome": "done"}])

    async def download(url):
        return PDF

    monkeypatch.setattr(app, "store", app.LocalStore(tmp_path))
    monkeypatch.setattr(app, "download", download)
    monkeypatch.setattr(app.pdf_reader, "read_pdf", read)
    return reads


def call_twice(second_after):
    results = {}

    async def both():
        async with Client(app.mcp) as first, Client(app.mcp) as second:
            async def call(name, client, delay):
                await anyio.sleep(delay)
                results[name] = await client.call_tool("read_pdf", ATTACHED)

            async with anyio.create_task_group() as group:
                group.start_soon(call, "first", first, 0)
                group.start_soon(call, "second", second, second_after)

    anyio.run(both)
    return results


def text_of(result):
    return " ".join(part.text for part in result.content if part.type == "text")


def test_a_repeat_of_the_same_pdf_waits_for_the_reading_already_running(monkeypatch, tmp_path):
    reads = slow_reader(monkeypatch, tmp_path, 2)
    results = call_twice(0.5)
    assert len(reads) == 1
    for result in results.values():
        assert not result.is_error and "score_id:" in text_of(result)


def test_a_repeat_that_outwaits_its_limit_is_told_the_pdf_is_still_being_read(monkeypatch, tmp_path):
    reads = slow_reader(monkeypatch, tmp_path, 3)
    monkeypatch.setattr(app, "SAME_FILE_WAIT", 1)
    results = call_twice(0.5)
    assert len(reads) == 1
    assert "score_id:" in text_of(results["first"])
    assert not results["second"].is_error and "still being read" in text_of(results["second"])


def test_a_pdf_read_once_comes_back_from_the_saved_card(monkeypatch, tmp_path):
    reads = slow_reader(monkeypatch, tmp_path, 0)

    async def call():
        async with Client(app.mcp) as client:
            return await client.call_tool("read_pdf", ATTACHED)

    first = anyio.run(call)
    monkeypatch.setattr(app, "read_pdf_card", None)
    second = anyio.run(call)
    assert len(reads) == 1
    assert text_of(first) == text_of(second)
