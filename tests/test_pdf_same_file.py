import io
import json
import threading
import time
import zipfile
from pathlib import Path

import anyio
import pikepdf
from mcp.client.client import Client
from PIL import Image

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


def test_the_call_that_starts_a_read_stays_for_it_and_a_repeat_is_told_it_is_still_being_read(monkeypatch, tmp_path):
    reads = slow_reader(monkeypatch, tmp_path, 3)
    monkeypatch.setattr(app, "SAME_FILE_WAIT", 1)
    results = call_twice(0.5)
    assert len(reads) == 1
    assert "score_id:" in text_of(results["first"])
    assert not results["second"].is_error and "still being read" in text_of(results["second"])


def test_a_read_carries_on_when_the_call_that_started_it_is_cancelled(monkeypatch, tmp_path):
    reads = slow_reader(monkeypatch, tmp_path, 2)

    async def cancel_then_resend():
        async with Client(app.mcp) as client:
            with anyio.move_on_after(0.5):
                await client.call_tool("read_pdf", ATTACHED)
            return await client.call_tool("read_pdf", ATTACHED)

    result = anyio.run(cancel_then_resend)
    assert len(reads) == 1
    assert not result.is_error and "score_id:" in text_of(result)


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


def test_a_call_on_the_other_machine_waits_for_that_machines_reading(monkeypatch, tmp_path):
    reads = slow_reader(monkeypatch, tmp_path, 0)

    async def call():
        async with Client(app.mcp) as client:
            return await client.call_tool("read_pdf", ATTACHED)

    first = anyio.run(call)
    card_key = next(key for key in (p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*"))
                    if "pdf-card-" in key)
    card = app.store.get(card_key)
    app.store.delete(card_key)
    app.store.put(app.marker_of(card_key), json.dumps({"token": "other", "started": time.time()}).encode())
    monkeypatch.setattr(app, "POLL_SECONDS", 0.2)

    async def other_machine_finishes_then_call():
        async def finish():
            await anyio.sleep(1)
            app.store.put(card_key, card)

        async with anyio.create_task_group() as group:
            group.start_soon(finish)
            result = await call()
        return result

    second = anyio.run(other_machine_finishes_then_call)
    assert len(reads) == 1
    assert text_of(first) == text_of(second)


def test_a_marker_left_by_a_machine_that_stopped_is_taken_over(monkeypatch, tmp_path):
    reads = slow_reader(monkeypatch, tmp_path, 0)
    digest = __import__("hashlib").sha256(PDF).hexdigest()
    card_key = f"scores/pdf-card-{pdf_reader.READER}-{digest}-no-slurs.json"
    app.store.put(app.marker_of(card_key), json.dumps({"token": "gone", "started": time.time() - 3600}).encode())

    async def call():
        async with Client(app.mcp) as client:
            return await client.call_tool("read_pdf", ATTACHED)

    result = anyio.run(call)
    assert len(reads) == 1 and "score_id:" in text_of(result)
    assert app.store.get(app.marker_of(card_key)) is None


def reading_card(monkeypatch, tmp_path, musicxml):
    async def download(url):
        return PDF

    monkeypatch.setattr(app, "store", app.LocalStore(tmp_path))
    monkeypatch.setattr(app, "download", download)
    monkeypatch.setattr(app.pdf_reader, "read_pdf", lambda data: pdf_reader.PdfReading(musicxml, 6, False, [], []))

    async def call():
        async with Client(app.mcp) as client:
            return await client.call_tool("read_pdf", ATTACHED)

    return anyio.run(call)


def stored(url):
    return app.store.get("files/" + url.rsplit("/", 1)[1])


def test_the_reading_card_of_a_long_score_shows_two_pages_and_the_pdf_has_them_all(monkeypatch, tmp_path):
    from music21 import corpus
    archive = zipfile.ZipFile(corpus.getWork("beethoven/opus59no1/movement1"))
    musicxml = next(archive.read(name) for name in archive.namelist() if not name.startswith("META-INF"))
    result = reading_card(monkeypatch, tmp_path, musicxml)
    data = result.structured_content
    assert len([part for part in result.content if part.type == "image"]) == app.CARD_PAGES
    image = Image.open(io.BytesIO(stored(data["image_url"])))
    assert image.height < 2.5 * image.width
    assert len(pikepdf.open(io.BytesIO(stored(data["pdf_url"]))).pages) > app.CARD_PAGES
    assert "first 2 pages" in data["caption"]
    assert "download the PDF to check the rest" in text_of(result)


def test_the_reading_card_of_a_short_score_shows_every_bar(monkeypatch, tmp_path):
    result = reading_card(monkeypatch, tmp_path, READING)
    assert result.structured_content["caption"] == "What I read from your PDF, every bar"
    assert "download the PDF" not in text_of(result)


def waiter_outcome(monkeypatch, tmp_path, capsys, failure_error, text):
    slow_reader(monkeypatch, tmp_path, 0)
    digest = __import__("hashlib").sha256(PDF).hexdigest()
    card_key = f"scores/pdf-card-{pdf_reader.READER}-{digest}-no-slurs.json"
    started = time.time() - 5
    app.store.put(app.marker_of(card_key), json.dumps({"token": "other", "started": started}).encode())
    app.store.put(app.failure_of(card_key), json.dumps({"at": time.time(), "error": failure_error, "text": text}).encode())

    async def call():
        async with Client(app.mcp) as client:
            return await client.call_tool("read_pdf", ATTACHED)

    result = anyio.run(call)
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")]
    return result, next(line for line in lines if line.get("tool") == "read_pdf" and "outcome" in line)


def test_a_busy_reading_on_the_other_machine_is_logged_as_busy(monkeypatch, tmp_path, capsys):
    result, line = waiter_outcome(monkeypatch, tmp_path, capsys, "busy", app.BUSY_MESSAGE)
    assert text_of(result) == app.BUSY_MESSAGE
    assert line["outcome"] == "busy"


def test_a_limit_on_the_other_machine_is_logged_as_a_limit(monkeypatch, tmp_path, capsys):
    result, line = waiter_outcome(monkeypatch, tmp_path, capsys, "limit", app.LIMIT_MESSAGE)
    assert text_of(result) == app.LIMIT_MESSAGE
    assert line["outcome"] == "limit"


def test_a_failed_reading_on_the_other_machine_stays_a_user_error(monkeypatch, tmp_path, capsys):
    result, line = waiter_outcome(monkeypatch, tmp_path, capsys, "ReadError", "No music could be read from this PDF")
    assert line["outcome"] == "user_error"
