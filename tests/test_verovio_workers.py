import asyncio
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import anyio
import pytest
from mcp.client.client import Client

from engine import read_pdf as pdf_reader
from engine import render, verovio_workers
from server import app

DATA = Path(__file__).parent / "data"
CRASH = (DATA / "mozart-k545-1-homr-reading-verovio-crashed-staff.musicxml").read_bytes()
BALLADE = (DATA / "chopin_ballade_op23_pdmx.mxl").read_bytes()
CHORALE = (DATA / "part_writing_bwv64.4.musicxml").read_bytes()
PDF = (DATA / "chopin-28-4-mutopia.pdf").read_bytes()
AUDIVERIS = os.environ.get("AUDIVERIS", "/opt/audiveris/bin/Audiveris")
ATTACHED = {"pdf_file": {"download_url": "https://example.com/score.pdf", "file_id": "file-1"}}
NO_MARKS = {"annotations": []}
READ_PDF = pdf_reader.read_pdf


@pytest.fixture
def pool(monkeypatch):
    pool = verovio_workers.Pool()
    monkeypatch.setattr(render, "new_toolkit", pool.toolkit)
    yield pool
    pool.stop()


@pytest.fixture
def store(monkeypatch, tmp_path):
    async def download(url):
        return PDF

    monkeypatch.setattr(app, "store", app.LocalStore(tmp_path))
    monkeypatch.setattr(app, "download", download)
    app.store.put("scores/BALLADE", BALLADE)
    app.store.put("scores/CHORALE", CHORALE)
    app.store.put("scores/CRASH", CRASH)
    return app.store


def text_of(result):
    return " ".join(part.text for part in result.content if part.type == "text")


def call(name, arguments):
    async def go():
        async with Client(app.mcp) as client:
            return await client.call_tool(name, arguments)

    return anyio.run(go)


def logged(capsys):
    return [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")]


def pids(pool):
    return [worker.process.pid for worker in pool.workers]


def crashing_reader(data, audiveris, setting, leland, deadline, stop):
    return pdf_reader.RawReading(CRASH, [], {"outcome": "done"})


def test_a_reading_that_crashes_the_drawing_gets_the_normal_unread_pdf_answer(pool, store, monkeypatch, capsys):
    monkeypatch.setattr(app.pdf_reader, "read_pdf", lambda data: pdf_reader.PdfReading(CRASH, 1, True))
    before = pids(pool)
    result = call("read_pdf", ATTACHED)
    assert result.is_error
    assert text_of(result) == pdf_reader.NOTHING_READ + pdf_reader.NEXT_STEP
    digest = hashlib.sha256(PDF).hexdigest()
    assert store.get(f"failed/{digest}.pdf") == PDF
    assert not list(Path(store.folder, "scores").glob("pdf-reading-*"))
    work = [line for line in logged(capsys) if line.get("event") == "read_pdf_work"][-1]
    assert work["outcome"] == "user_error" and work["error"] == "VerovioFailed"
    assert work["verovio"].startswith("crashed")

    drawn = call("render_analysis", {"score_id": "CHORALE", "annotations": NO_MARKS})
    assert not drawn.is_error
    assert len(set(before) & set(pids(pool))) == 1
    assert [worker.bound for worker in pool.workers] == [0, 0]


def test_a_crash_in_one_reading_leaves_a_drawing_on_the_other_worker_running(pool, store, monkeypatch):
    monkeypatch.setattr(app.pdf_reader, "read_pdf", lambda data: READ_PDF(data, raw=crashing_reader))
    finished = {}

    async def both():
        async with Client(app.mcp) as drawing, Client(app.mcp) as reading:
            async def draw():
                finished["drawing"] = await drawing.call_tool("render_analysis", {"score_id": "BALLADE", "annotations": NO_MARKS}), time.monotonic()

            async def read():
                await anyio.sleep(0.5)
                finished["reading"] = await reading.call_tool("read_pdf", ATTACHED), time.monotonic()

            async with anyio.create_task_group() as group:
                group.start_soon(draw)
                group.start_soon(read)

    anyio.run(both)
    (drawn, drawn_at), (read, read_at) = finished["drawing"], finished["reading"]
    assert read.is_error and text_of(read).startswith(pdf_reader.NOTHING_READ)
    assert read_at < drawn_at
    assert not drawn.is_error and "shown in a card" in text_of(drawn)
    again = call("render_analysis", {"score_id": "CHORALE", "annotations": NO_MARKS})
    assert not again.is_error


@pytest.mark.skipif(not os.path.exists(AUDIVERIS), reason="Audiveris is not installed; set AUDIVERIS")
def test_a_pdf_is_read_with_audiveris_and_drawn_through_the_workers(pool, store, monkeypatch):
    monkeypatch.setattr(app.pdf_reader, "read_pdf", lambda data: READ_PDF(data, AUDIVERIS))
    result = call("read_pdf", ATTACHED)
    assert not result.is_error and "score_id:" in text_of(result)
    assert [worker.bound for worker in pool.workers] == [0, 0]


@pytest.fixture(scope="module")
def server_process(tmp_path_factory):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    folder = tmp_path_factory.mktemp("store")
    (folder / "scores").mkdir()
    (folder / "scores" / "CRASH").write_bytes(CRASH)
    (folder / "scores" / "CHORALE").write_bytes(CHORALE)
    env = {**os.environ, "PORT": str(port), "DATA_DIR": str(folder)}
    env.pop("BUCKET", None)
    env.pop("K_SERVICE", None)
    process = subprocess.Popen([sys.executable, "-m", "server.app"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    for _ in range(120):
        try:
            urllib.request.urlopen(f"{url}/health", timeout=1)
            break
        except OSError:
            time.sleep(0.25)
    yield url, process
    process.terminate()
    process.wait(10)


def workers_of(process):
    found = subprocess.run(["pgrep", "-P", str(process.pid)], capture_output=True, text=True).stdout.split()
    return sorted(int(pid) for pid in found)


def test_the_server_starts_two_workers_and_never_loads_the_drawing_library_itself(server_process):
    url, process = server_process
    assert len(workers_of(process)) == 2
    assert "_verovio" not in Path(f"/proc/{process.pid}/maps").read_text()


def test_the_server_survives_a_score_that_crashes_the_drawing_library(server_process):
    url, process = server_process

    async def draw(score_id):
        async with Client(f"{url}/mcp") as client:
            return await client.call_tool("render_analysis", {"score_id": score_id, "annotations": NO_MARKS})

    before = workers_of(process)
    crashed = asyncio.run(draw("CRASH"))
    assert crashed.is_error and text_of(crashed) == render.UNREADABLE
    drawn = asyncio.run(draw("CHORALE"))
    assert not drawn.is_error and "shown in a card" in text_of(drawn)
    assert process.poll() is None
    after = workers_of(process)
    assert len(after) == 2 and len(set(before) & set(after)) == 1
    assert "_verovio" not in Path(f"/proc/{process.pid}/maps").read_text()


def test_a_call_over_the_time_limit_is_stopped_and_the_next_request_gets_a_fresh_worker(pool, monkeypatch):
    monkeypatch.setattr(verovio_workers, "CALL_SECONDS", 0.05)
    token = verovio_workers.current.set(verovio_workers.Request())
    with pytest.raises(verovio_workers.VerovioFailed) as stopped:
        render.load_toolkit(BALLADE)
    verovio_workers.current.get().release()
    verovio_workers.current.reset(token)
    assert "took over" in stopped.value.reason
    monkeypatch.setattr(verovio_workers, "CALL_SECONDS", 120)
    token = verovio_workers.current.set(verovio_workers.Request())
    assert render.engrave(CHORALE).page_count
    verovio_workers.current.get().release()
    verovio_workers.current.reset(token)
