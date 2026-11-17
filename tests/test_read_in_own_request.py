import json
import re
import socket
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import anyio
import httpx
import pytest
import uvicorn
from mcp.client.client import Client
from starlette.applications import Starlette
from starlette.responses import Response
from starlette.routing import Route

from engine import read_pdf as pdf_reader
from server import app

DATA = Path(__file__).parent / "data"
PDF = (DATA / "chopin-28-4-mutopia.pdf").read_bytes()
READING = (DATA / "chopin_prelude_op28_no4_reading.musicxml").read_bytes()
ATTACHED = {"pdf_file": {"download_url": "https://example.com/score.pdf", "file_id": "file-1"}}
CARD_KEY = app.card_of(app.hashlib.sha256(PDF).hexdigest())


@contextmanager
def serving(routes):
    open_requests = []

    async def counted(scope, receive, send):
        if scope["type"] != "http":
            return await served(scope, receive, send)
        open_requests.append(scope["path"])
        try:
            await served(scope, receive, send)
        finally:
            open_requests.remove(scope["path"])

    served = Starlette(routes=routes)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(counted, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    try:
        yield f"http://127.0.0.1:{port}", open_requests
    finally:
        server.should_exit = True
        thread.join(10)


def answering(status):
    async def answer(request):
        return Response(status_code=status)

    return [Route("/read-work", answer, methods=["POST"])]


READ_WORK = [Route("/read-work", app.read_work, methods=["POST"])]


def reader(monkeypatch, tmp_path, open_requests=(), reading=None):
    reads = []

    def read(data):
        reads.append(list(open_requests))
        if reading is None:
            raise pdf_reader.ReadError("No music could be read from this PDF", [{"setting": 0, "outcome": "no music"}])
        return pdf_reader.PdfReading(reading, 1, False, [], [{"setting": 0, "outcome": "done"}])

    async def download(url):
        return PDF

    monkeypatch.setattr(app, "store", app.LocalStore(tmp_path))
    monkeypatch.setattr(app, "download", download)
    monkeypatch.setattr(app.pdf_reader, "read_pdf", read)
    return reads


def read_the_pdf():
    async def call():
        async with Client(app.mcp) as client:
            return await client.call_tool("read_pdf", ATTACHED)

    return anyio.run(call)


def text_of(result):
    return " ".join(part.text for part in result.content if part.type == "text")


def lines_of(capsys):
    return [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")]


def test_a_read_started_by_a_call_runs_inside_a_request_of_its_own(monkeypatch, tmp_path, capsys):
    with serving(READ_WORK) as (address, open_requests):
        reads = reader(monkeypatch, tmp_path, open_requests, READING)
        monkeypatch.setattr(app, "OWN_ADDRESS", address)
        result = read_the_pdf()
    assert reads == [["/read-work"]]
    assert not result.is_error and "score_id:" in text_of(result)
    assert app.store.get(app.marker_of(CARD_KEY)) is None and app.reads_held == {}
    call = next(line for line in lines_of(capsys) if line.get("tool") == "read_pdf")
    assert call["outcome"] == "ok" and "omr" in call["timings_ms"]


def test_without_an_address_of_its_own_the_read_runs_on_the_machine_that_got_the_call(monkeypatch, tmp_path):
    reads = reader(monkeypatch, tmp_path, reading=READING)
    result = read_the_pdf()
    assert reads == [[]]
    assert "score_id:" in text_of(result)


def test_a_pdf_that_cannot_be_read_gives_the_same_answer_from_a_request_of_its_own(monkeypatch, tmp_path):
    reader(monkeypatch, tmp_path / "here")
    here = read_the_pdf()
    with serving(READ_WORK) as (address, open_requests):
        reads = reader(monkeypatch, tmp_path / "own", open_requests)
        monkeypatch.setattr(app, "OWN_ADDRESS", address)
        own = read_the_pdf()
    assert reads == [["/read-work"]]

    def without_reference(result):
        return re.sub(r"\b[0-9a-f]{8}\b", "REFERENCE", result.model_dump_json())

    assert own.meta["report"]["text"] and without_reference(own) == without_reference(here)


@pytest.mark.parametrize("status", [401, 403, 404, 429])
def test_a_read_refused_at_the_door_is_read_on_the_machine_that_got_the_call(monkeypatch, tmp_path, capsys, status):
    with serving(answering(status)) as (address, _):
        reads = reader(monkeypatch, tmp_path, reading=READING)
        monkeypatch.setattr(app, "OWN_ADDRESS", address)
        result = read_the_pdf()
    assert reads == [[]]
    assert "score_id:" in text_of(result)
    assert app.store.get(app.marker_of(CARD_KEY)) is None and app.reads_held == {}
    assert any(line.get("reason") == f"status {status}" for line in lines_of(capsys))


def test_a_read_whose_own_address_does_not_answer_is_read_on_the_machine_that_got_the_call(monkeypatch, tmp_path):
    with socket.socket() as unused:
        unused.bind(("127.0.0.1", 0))
        address = f"http://127.0.0.1:{unused.getsockname()[1]}"
    reads = reader(monkeypatch, tmp_path, reading=READING)
    monkeypatch.setattr(app, "OWN_ADDRESS", address)
    assert "score_id:" in text_of(read_the_pdf())
    assert reads == [[]]


def test_a_read_lost_after_it_was_taken_is_our_error_and_the_pdf_can_be_sent_again(monkeypatch, tmp_path, capsys):
    with serving(answering(503)) as (address, _):
        reads = reader(monkeypatch, tmp_path, reading=READING)
        monkeypatch.setattr(app, "OWN_ADDRESS", address)
        lost = read_the_pdf()
        lines = lines_of(capsys)
        monkeypatch.setattr(app, "OWN_ADDRESS", "")
        again = read_the_pdf()
    work = next(line for line in lines if line.get("event") == "read_pdf_work")
    call = next(line for line in lines if line.get("tool") == "read_pdf")
    assert lost.meta["report"]["reference"] == work["reference"] and work["reference"] in text_of(lost)
    assert work["outcome"] == call["outcome"] == "server_error" and "503" in call["stack_trace"]
    assert app.store.get(f"failed/{work['digest']}.pdf") == PDF
    assert reads == [[]] and "score_id:" in text_of(again)


def test_the_reading_request_serves_only_the_holder_of_the_read_marker(monkeypatch, tmp_path):
    with serving(READ_WORK) as (address, _):
        reads = reader(monkeypatch, tmp_path, reading=READING)
        asked = {"source": "other", "arrived": 1, "token": "not the holder"}
        unmarked = httpx.post(f"{address}/read-work", params=asked, content=PDF)
        app.store.put(app.marker_of(CARD_KEY), json.dumps({"token": "the holder", "started": time.time()}).encode())
        marked = httpx.post(f"{address}/read-work", params=asked, content=PDF)
        tokenless = httpx.post(f"{address}/read-work", params={"source": "other", "arrived": 1}, content=PDF)
    assert [unmarked.status_code, marked.status_code, tokenless.status_code] == [403, 403, 403]
    assert reads == []
