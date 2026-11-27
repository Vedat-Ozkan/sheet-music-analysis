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
from starlette.responses import JSONResponse, Response
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


def answering(response):
    async def answer(request):
        return response

    return [Route("/read-work", answer, methods=["POST"])]


READ_WORK = [Route("/read-work", app.read_work, methods=["POST"])]


def two_machines(sent_to_the_other_first):
    asked = []

    async def balanced(request):
        asked.append(request.headers.get("x-read-machine"))
        if len(asked) > sent_to_the_other_first:
            return await app.read_work(request)
        here, app.MACHINE = app.MACHINE, "the other machine"
        try:
            return await app.read_work(request)
        finally:
            app.MACHINE = here

    return [Route("/read-work", balanced, methods=["POST"])], asked


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


def read_the_pdf(person=None):
    async def call():
        async with Client(app.mcp) as client:
            return await client.call_tool("read_pdf", ATTACHED, meta={"openai/subject": person} if person else None)

    return anyio.run(call)


def text_of(result):
    return " ".join(part.text for part in result.content if part.type == "text")


def without_reference(result):
    return re.sub(r"\b[0-9a-f]{8}\b", "REFERENCE", result.model_dump_json())


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


def test_a_read_sent_to_the_other_machine_first_is_asked_again_until_its_own_machine_takes_it(monkeypatch, tmp_path):
    routes, asked = two_machines(sent_to_the_other_first=2)
    with serving(routes) as (address, open_requests):
        reads = reader(monkeypatch, tmp_path, open_requests, READING)
        monkeypatch.setattr(app, "OWN_ADDRESS", address)
        result = read_the_pdf()
    assert asked == [app.MACHINE] * 3
    assert reads == [["/read-work"]]
    assert "score_id:" in text_of(result)


def test_a_read_its_own_machine_never_gets_is_read_by_the_other_machine(monkeypatch, tmp_path):
    routes, asked = two_machines(sent_to_the_other_first=app.OWN_MACHINE_TRIES + 1)
    with serving(routes) as (address, open_requests):
        reads = reader(monkeypatch, tmp_path, open_requests, READING)
        monkeypatch.setattr(app, "OWN_ADDRESS", address)
        result = read_the_pdf()
    assert asked == [app.MACHINE] * app.OWN_MACHINE_TRIES + [None]
    assert reads == [["/read-work"]]
    assert "score_id:" in text_of(result)
    assert app.store.get(app.marker_of(CARD_KEY)) is None and app.reads_held == {}


def test_a_read_in_a_request_of_its_own_is_counted_once_for_the_person_who_sent_it(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "pseudonym_key", None)
    monkeypatch.setattr(app, "months_recorded", set())
    with serving(READ_WORK) as (address, open_requests):
        reader(monkeypatch, tmp_path, open_requests, READING)
        monkeypatch.setattr(app, "OWN_ADDRESS", address)
        assert "score_id:" in text_of(read_the_pdf("anna"))
    counts = json.loads(app.store.get(f"limits/{app.today()}.json"))
    assert counts == {app.pseudonym("anna"): 1}
    assert json.loads(app.store.get(app.person_reading(app.pseudonym("anna"))))["card"] == CARD_KEY


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
    assert own.meta["report"]["text"] and without_reference(own) == without_reference(here)


@pytest.mark.parametrize("status", [401, 403, 404, 429])
def test_a_read_refused_at_the_door_is_read_on_the_machine_that_got_the_call(monkeypatch, tmp_path, capsys, status):
    with serving(answering(Response(status_code=status))) as (address, _):
        reads = reader(monkeypatch, tmp_path, reading=READING)
        monkeypatch.setattr(app, "OWN_ADDRESS", address)
        result = read_the_pdf()
    assert reads == [[]]
    assert "score_id:" in text_of(result)
    assert app.store.get(app.marker_of(CARD_KEY)) is None and app.reads_held == {}
    assert any(line.get("reason") == f"status {status}" for line in lines_of(capsys))


@pytest.mark.parametrize("address", ["closed port", "not an address"])
def test_a_read_whose_own_address_cannot_be_reached_is_read_on_the_machine_that_got_the_call(monkeypatch, tmp_path, address):
    with socket.socket() as unused:
        unused.bind(("127.0.0.1", 0))
        address = address.replace("closed port", f"http://127.0.0.1:{unused.getsockname()[1]}")
    reads = reader(monkeypatch, tmp_path, reading=READING)
    monkeypatch.setattr(app, "OWN_ADDRESS", address)
    assert "score_id:" in text_of(read_the_pdf())
    assert reads == [[]]


@pytest.mark.parametrize("response", [Response(status_code=503), JSONResponse({"not": "the answer"})], ids=["503", "wrong body"])
def test_a_read_lost_after_it_was_taken_is_our_error_until_its_marker_runs_out(monkeypatch, tmp_path, capsys, response):
    with serving(answering(response)) as (address, _):
        reads = reader(monkeypatch, tmp_path, reading=READING)
        monkeypatch.setattr(app, "OWN_ADDRESS", address)
        lost = read_the_pdf()
        lines = lines_of(capsys)
        sent_again = read_the_pdf()
        app.store.put(app.marker_of(CARD_KEY), json.dumps({"token": "gone", "started": 0}).encode())
        monkeypatch.setattr(app, "OWN_ADDRESS", "")
        after_the_marker = read_the_pdf()
    work = next(line for line in lines if line.get("event") == "read_pdf_work")
    call = next(line for line in lines if line.get("tool") == "read_pdf")
    assert lost.meta["report"]["reference"] == work["reference"] and work["reference"] in text_of(lost)
    assert work["outcome"] == call["outcome"] == "server_error" and call["stack_trace"]
    assert app.store.get(f"failed/{work['digest']}.pdf") == PDF
    assert without_reference(sent_again) == without_reference(lost)
    assert reads == [[]] and "score_id:" in text_of(after_the_marker)


def test_the_reading_request_serves_only_the_holder_of_the_read_marker(monkeypatch, tmp_path):
    with serving(READ_WORK) as (address, _):
        reads = reader(monkeypatch, tmp_path, reading=READING)
        asked = {"x-read-source": "other", "x-read-arrived": "1", "x-read-token": "not the holder"}
        unmarked = httpx.post(f"{address}/read-work", headers=asked, content=PDF)
        app.store.put(app.marker_of(CARD_KEY), json.dumps({"token": "the holder", "started": time.time()}).encode())
        marked = httpx.post(f"{address}/read-work", headers=asked, content=PDF)
        tokenless = httpx.post(f"{address}/read-work", headers={"x-read-source": "other", "x-read-arrived": "1"}, content=PDF)
    assert [unmarked.status_code, marked.status_code, tokenless.status_code] == [403, 403, 403]
    assert reads == []
