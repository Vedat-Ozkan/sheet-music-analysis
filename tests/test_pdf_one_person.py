import hashlib
import json
import threading
import time
from pathlib import Path

import anyio
from mcp.client.client import Client

from engine import read_pdf as pdf_reader
from server import app

DATA = Path(__file__).parent / "data"
FIRST = (DATA / "chopin-28-4-mutopia.pdf").read_bytes()
SECOND = FIRST + b"\n%second copy\n"
READING = (DATA / "chopin_prelude_op28_no4_reading.musicxml").read_bytes()
FILES = {"https://example.com/first.pdf": FIRST, "https://example.com/second.pdf": SECOND}


def attached(url):
    return {"pdf_file": {"download_url": url, "file_id": url}}


def as_person(name):
    return {"openai/subject": name}


def readers(monkeypatch, tmp_path, seconds):
    spans = []

    def read(data):
        started = time.monotonic()
        time.sleep(seconds)
        spans.append((started, time.monotonic()))
        return pdf_reader.PdfReading(READING, 1, False, [], [{"setting": 0, "outcome": "done"}])

    async def download(url):
        return FILES[url]

    monkeypatch.setattr(app, "store", app.LocalStore(tmp_path))
    monkeypatch.setattr(app, "pseudonym_key", None)
    monkeypatch.setattr(app, "months_recorded", set())
    monkeypatch.setattr(app, "download", download)
    monkeypatch.setattr(app.pdf_reader, "read_pdf", read)
    monkeypatch.setattr(app, "POLL_SECONDS", 0.2)
    return spans


def card_key_of(data):
    return f"scores/pdf-card-{pdf_reader.READER}-{hashlib.sha256(data).hexdigest()}.json"


def reading_elsewhere(person, data, started):
    card_key = card_key_of(data)
    app.store.put(app.marker_of(card_key), json.dumps({"token": "other", "started": started}).encode())
    app.store.put(app.person_reading(app.pseudonym(person)), json.dumps({"card": card_key, "token": "other"}).encode())
    return card_key


def call(url, person):
    async def one():
        async with Client(app.mcp) as client:
            return await client.call_tool("read_pdf", attached(url), meta=as_person(person))

    return anyio.run(one)


def text_of(result):
    return " ".join(part.text for part in result.content if part.type == "text")


def test_one_persons_pdfs_are_read_one_after_another_not_refused_as_busy(monkeypatch, tmp_path):
    spans = readers(monkeypatch, tmp_path, 1.5)
    results = {}

    async def both():
        async with Client(app.mcp) as first, Client(app.mcp) as second:
            async def send(name, client, url, delay):
                await anyio.sleep(delay)
                results[name] = await client.call_tool("read_pdf", attached(url), meta=as_person("person-1"))

            async with anyio.create_task_group() as group:
                group.start_soon(send, "first", first, "https://example.com/first.pdf", 0)
                group.start_soon(send, "second", second, "https://example.com/second.pdf", 0.3)

    anyio.run(both)
    assert all("score_id:" in text_of(result) for result in results.values()), [text_of(r) for r in results.values()]
    (first_start, first_end), (second_start, _) = sorted(spans)
    assert second_start >= first_end


def test_a_pdf_waits_while_the_same_person_has_another_pdf_reading_on_the_other_machine(monkeypatch, tmp_path):
    spans = readers(monkeypatch, tmp_path, 0)
    other = reading_elsewhere("person-1", SECOND, time.time())
    finished = []

    def other_machine_finishes():
        time.sleep(1)
        finished.append(time.monotonic())
        app.store.delete(app.marker_of(other))

    threading.Thread(target=other_machine_finishes).start()
    result = call("https://example.com/first.pdf", "person-1")
    assert "score_id:" in text_of(result)
    assert spans[0][0] >= finished[0]


def test_another_persons_reading_does_not_hold_up_this_person(monkeypatch, tmp_path):
    spans = readers(monkeypatch, tmp_path, 0)
    reading_elsewhere("person-2", SECOND, time.time())
    started = time.monotonic()
    result = call("https://example.com/first.pdf", "person-1")
    assert "score_id:" in text_of(result) and spans[0][0] - started < 1


def test_a_person_whose_other_read_marker_has_expired_is_not_held_up(monkeypatch, tmp_path):
    spans = readers(monkeypatch, tmp_path, 0)
    reading_elsewhere("person-1", SECOND, time.time() - 3600)
    started = time.monotonic()
    result = call("https://example.com/first.pdf", "person-1")
    assert "score_id:" in text_of(result) and spans[0][0] - started < 1


def test_a_pdf_still_waiting_its_turn_is_answered_with_call_again_and_not_read(monkeypatch, tmp_path):
    spans = readers(monkeypatch, tmp_path, 0)
    monkeypatch.setattr(app, "STARTER_WAIT", 1)
    reading_elsewhere("person-1", SECOND, time.time())
    result = call("https://example.com/first.pdf", "person-1")
    assert not result.is_error and "after" in text_of(result) and "read_pdf again" in text_of(result)
    assert spans == [] and not list(tmp_path.glob("limits/**/*"))


def test_a_resent_attachment_is_read_from_the_kept_copy_when_its_link_no_longer_works(monkeypatch, tmp_path):
    readers(monkeypatch, tmp_path, 0)
    first = call("https://example.com/first.pdf", "person-1")

    async def link_expired(url):
        raise app.ScoreError(app.ATTACHMENT_ANSWERED.format(status=403))

    monkeypatch.setattr(app, "download_attachment", link_expired)
    again = call("https://example.com/first.pdf", "person-1")
    assert "score_id:" in text_of(first) and text_of(again) == text_of(first)


def test_the_same_file_id_from_two_people_gives_each_their_own_pdf(monkeypatch, tmp_path):
    readers(monkeypatch, tmp_path, 0)

    async def same_id(url, person):
        async with Client(app.mcp) as client:
            return await client.call_tool("read_pdf", {"pdf_file": {"download_url": url, "file_id": "file-1"}},
                                          meta=as_person(person))

    first = anyio.run(same_id, "https://example.com/first.pdf", "person-1")
    second = anyio.run(same_id, "https://example.com/second.pdf", "person-2")
    assert "score_id:" in text_of(first) and "score_id:" in text_of(second)
    assert text_of(first) != text_of(second)


def test_a_pdf_from_a_caller_without_a_user_code_is_not_kept(monkeypatch, tmp_path):
    readers(monkeypatch, tmp_path, 0)

    async def anonymous():
        async with Client(app.mcp) as client:
            return await client.call_tool("read_pdf", attached("https://example.com/first.pdf"))

    assert "score_id:" in text_of(anyio.run(anonymous))
    assert not list(tmp_path.glob("scores/attached-*"))


def test_a_call_that_loses_the_turn_after_claiming_gives_its_file_back_and_waits(monkeypatch, tmp_path):
    spans = readers(monkeypatch, tmp_path, 0)
    person = app.pseudonym("person-1")
    other = card_key_of(SECOND)
    mine = card_key_of(FIRST)
    plain = app.store.get_versioned
    seen = []

    def turn_taken_meanwhile(key):
        found = plain(key)
        if key == app.person_reading(person) and app.store.get(app.marker_of(mine)) and not seen:
            seen.append(True)
            app.store.put(app.marker_of(other), json.dumps({"token": "other", "started": time.time()}).encode())
            app.store.put(key, json.dumps({"card": other, "token": "other"}).encode())
            time.sleep(0.01)
        return found

    monkeypatch.setattr(app.store, "get_versioned", turn_taken_meanwhile)
    released = []

    def other_read_finishes():
        while not seen:
            time.sleep(0.05)
        time.sleep(1)
        released.append(app.store.get(app.marker_of(mine)))
        app.store.delete(app.marker_of(other))

    threading.Thread(target=other_read_finishes).start()
    result = call("https://example.com/first.pdf", "person-1")
    assert seen and released == [None]
    assert "score_id:" in text_of(result) and len(spans) == 1


def test_an_attachment_without_a_file_id_is_not_kept(monkeypatch, tmp_path):
    readers(monkeypatch, tmp_path, 0)

    async def no_id():
        async with Client(app.mcp) as client:
            return await client.call_tool("read_pdf", {"pdf_file": {"download_url": "https://example.com/first.pdf",
                                                                    "file_id": ""}}, meta=as_person("person-1"))

    assert "score_id:" in text_of(anyio.run(no_id))
    assert not list(tmp_path.glob("scores/attached-*"))


def test_a_machine_told_to_stop_frees_the_reads_it_holds(monkeypatch, tmp_path):
    readers(monkeypatch, tmp_path, 2)
    marker = app.marker_of(card_key_of(FIRST))
    seen = []

    async def stop_while_reading():
        async with Client(app.mcp) as client:
            async with anyio.create_task_group() as group:
                async def read():
                    await client.call_tool("read_pdf", attached("https://example.com/first.pdf"), meta=as_person("person-1"))

                group.start_soon(read)
                while not app.store.get(marker):
                    await anyio.sleep(0.05)
                server = app.HttpServer(app.uvicorn.Config(None))
                server.handle_exit(15, None)
                seen.append((server.should_exit, app.store.get(marker)))

    anyio.run(stop_while_reading)
    assert seen == [(True, None)]
