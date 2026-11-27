import hashlib
import io
import json
import re
from pathlib import Path

import anyio
import pikepdf
import pytest
from mcp.client.client import Client

from engine import read_pdf as pdf_reader
from server import app
from tests import test_chatgpt_flow
from tests.test_chatgpt_flow import ATTACHED, PDF, call, charged, counted_for, logged, score_id_of, text_of

PAGE = (Path(__file__).parent / "data/careful/dvorak-silhouette-1-page1.n1").read_text()
server = test_chatgpt_flow.server


@pytest.fixture(autouse=True)
def careful_reading_on(monkeypatch, server):
    monkeypatch.setattr(app, "CAREFUL_PLATFORMS", {"other", "claude"})


def as_person(person, name, **arguments):
    async def go():
        async with Client(app.mcp) as client:
            return await client.call_tool(name, arguments, meta={"openai/subject": person})

    return anyio.run(go)


def read(person="ann", **arguments):
    return as_person(person, "read_pdf" if not arguments else "read_fetched_pdf", **(arguments or ATTACHED))


def asked(result):
    return "Question for the user, before any reading" in text_of(result)


def reading_id(result):
    return re.search(r"careful_reading with the reading id (\w+)\.", text_of(result))[1]


def read_carefully(person, score_id):
    steps = text_of(as_person(person, "careful_reading", score_id=score_id))
    own = re.search(r"own score_id \((\w+)\)", steps)[1]
    return as_person(person, "use_careful_reading", score_id=own, pages=[PAGE])


def blank_pdf(pages, **saving):
    pdf = pikepdf.new()
    for _ in range(pages):
        pdf.add_blank_page()
    out = io.BytesIO()
    pdf.save(out, **saving)
    return out.getvalue()


def person_code(server):
    [name] = server.folder.glob("limits/*.json")
    [person] = json.loads(name.read_text())
    return person


def test_the_question_is_remembered_for_an_hour_for_one_person_and_one_chosen_file(server, monkeypatch):
    server.put("scores/AAA.pdf", PDF)
    server.put("scores/BBB.pdf", PDF)
    clock = [1_000_000.0]
    monkeypatch.setattr(app.time, "time", lambda: clock[0])
    assert asked(read("ann", pdf_id="AAA"))
    assert asked(read("bob", pdf_id="AAA")) and asked(read("ann", pdf_id="BBB")) and asked(read("ann"))
    assert asked(read("cleo", pdf_id="AAA"))
    clock[0] += app.ASKED_FOR_SECONDS - 1
    assert not asked(read("ann", pdf_id="AAA"))
    clock[0] += 2
    assert asked(read("cleo", pdf_id="AAA"))
    clock[0] += app.ASKED_FOR_SECONDS * 5
    later = read("ann", pdf_id="AAA")
    assert not asked(later) and score_id_of(later)


def test_a_careful_reading_takes_the_score_unit_once_and_its_reading_id_then_says_which_score_id_to_use(server):
    reading = reading_id(read())
    assert charged(server, "score") == 0
    first = read_carefully("ann", reading)
    assert not first.is_error, text_of(first)
    person, stored = person_code(server), text_of(first).split()[1]
    assert (charged(server, "score"), counted_for(server, person), charged(server, "pdf_page"), charged(server, "draft")) == (1, 1, 0, 1)
    second = text_of(read_carefully("ann", reading)).split()[1]
    assert (charged(server, "score"), counted_for(server, person), charged(server, "draft")) == (1, 1, 2)
    assert f"this PDF has been read carefully already: score_id {second} is that reading".lower() in text_of(read()).lower()
    refused = text_of(call("draft_analysis", {"score_id": reading}))
    assert f"its careful reading is score_id {second}" in refused and "not read yet" not in refused and stored != second
    steps = text_of(as_person("ann", "careful_reading", score_id=reading))
    assert f"If they say no, the earlier careful reading stays: score_id {second} is ready for draft_analysis." in steps
    anyio.run(app.read_pdf_card, PDF, hashlib.sha256(PDF).hexdigest(), "other", True, person)
    assert (charged(server, "score"), counted_for(server, person)) == (1, 1) and charged(server, "pdf_page") > 0


def test_a_user_who_chose_the_quick_reading_keeps_it_and_can_still_ask_for_the_careful_one(server, monkeypatch):
    clock = [1_000_000.0]
    monkeypatch.setattr(app.time, "time", lambda: clock[0])
    reading = reading_id(read())
    question = json.loads(server.get(app.reading_key(reading)))
    score_id = score_id_of(read())
    clock[0] += app.ASKED_FOR_SECONDS * 3
    assert score_id_of(read()) == score_id
    assert f"its quick reading is score_id {score_id}" in text_of(call("draft_analysis", {"score_id": reading}))
    steps = text_of(as_person("ann", "careful_reading", score_id=score_id))
    assert f"If they say no, the quick reading stays: score_id {score_id} is ready for draft_analysis." in steps
    assert not read_carefully("ann", score_id).is_error
    assert charged(server, "score") == 1 and score_id_of(read()) == score_id
    as_person("ann", "careful_reading", score_id=reading)
    assert not read_carefully("ann", reading).is_error
    assert json.loads(server.get(app.reading_key(reading))) == question
    assert all(server.get(app.fact_key(reading, fact)) is not None for fact in app.PDF_FACTS)


def unreadable_for(lasting):
    def unreadable(data):
        raise pdf_reader.ReadError("No music could be read from this PDF", [{"setting": 0, "outcome": "no music"}], lasting=lasting)

    return unreadable


def test_a_reading_id_whose_quick_reading_failed_says_so_and_names_no_score_id(server, monkeypatch):
    monkeypatch.setattr(app.pdf_reader, "read_pdf", unreadable_for(lasting=False))
    reading = reading_id(read())
    assert "a MusicXML file" in text_of(read())
    refused = text_of(call("draft_analysis", {"score_id": reading}))
    assert "its quick reading has returned no score_id yet: read_pdf again with the same file says where it stands" in refused


def test_after_a_quick_reading_failed_for_good_no_text_says_that_calling_again_gives_one(server, monkeypatch):
    monkeypatch.setattr(app.pdf_reader, "read_pdf", unreadable_for(lasting=True))
    own, others = reading_id(read("ann")), reading_id(read("bob"))
    read("ann")
    for reading in (own, others):
        refused = text_of(call("draft_analysis", {"score_id": reading}))
        assert "there is no quick reading of it: it could not read this PDF." in refused and "read_pdf again" not in refused
        steps = text_of(as_person("ann", "careful_reading", score_id=reading))
        assert "If they say no, there is no quick reading: it could not read this PDF." in steps
        assert "reads the PDF" not in steps


@pytest.mark.parametrize("pages, named", [(pdf_reader.READ_PAGES, False), (pdf_reader.READ_PAGES + 1, True)])
def test_the_question_for_a_pdf_longer_than_the_quick_reading_names_its_page_limit(server, monkeypatch, pages, named):
    long = blank_pdf(pages)

    async def download(url):
        return long

    monkeypatch.setattr(app, "download", download)
    result = read()
    assert asked(result)
    assert (f"The quick reading takes only the first {pdf_reader.READ_PAGES} pages." in text_of(result)) == named


@pytest.mark.parametrize("full, message", [("person", "PERSON_LIMIT_MESSAGE"), ("score", "LIMIT_MESSAGE"), ("draft", "LIMIT_MESSAGE")])
def test_a_careful_reading_gives_no_steps_when_a_limit_it_needs_is_used_up(server, monkeypatch, full, message):
    reading = reading_id(read())
    if full == "person":
        monkeypatch.setattr(app, "PERSON_SCORE_LIMIT", 0)
    else:
        monkeypatch.setitem(app.DAILY_LIMITS, full, 0)
    refused = as_person("ann", "careful_reading", score_id=reading)
    assert refused.is_error and text_of(refused) == getattr(app, message)
    assert not list(server.folder.glob("scores/careful-*")) and not list(server.folder.glob("usage/*.json"))


def test_a_locked_pdf_is_the_users_error_and_its_copy_is_kept(server, monkeypatch):
    locked = blank_pdf(1, encryption=pikepdf.Encryption(owner="owner", user="user"))

    async def download(url):
        return locked

    monkeypatch.setattr(app, "download", download)
    result = read()
    assert "This file could not be opened as a PDF" in text_of(result) and not asked(result)
    assert server.get(f"failed/{hashlib.sha256(locked).hexdigest()}.pdf") == locked


def test_a_pdf_whose_first_look_fails_is_read_without_the_question_and_the_log_names_the_failure(server, monkeypatch, capsys):
    looks, is_scan = [], pdf_reader.is_scan

    def broken_once(pdf):
        looks.append(pdf)
        if len(looks) == 1:
            raise RuntimeError("first look")
        return is_scan(pdf)

    monkeypatch.setattr(app.pdf_reader, "is_scan", broken_once)
    result = read()
    assert not asked(result) and score_id_of(result)
    assert [line.get("first_look") for line in logged(capsys, "read_pdf") if line.get("event") == "read_pdf"] == ["RuntimeError"]
