import asyncio
import base64
import hashlib
import io
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from contextlib import contextmanager
from pathlib import Path

import pytest
from mcp.client.client import Client

from engine import correct
from engine import read_pdf as pdf_reader
from server import app
from tests.test_chord_symbols import PRINTED


NOCTURNE = Path(__file__).parent / "data" / "chopin_nocturne_op9_no2.mxl"


@pytest.fixture(scope="module")
def store(tmp_path_factory):
    return tmp_path_factory.mktemp("store")


def listening_ports(pid):
    sockets = set()
    for fd in Path(f"/proc/{pid}/fd").iterdir():
        try:
            sockets.add(os.readlink(fd))
        except OSError:
            pass
    rows = [line.split() for line in Path("/proc/net/tcp").read_text().splitlines()[1:]]
    return {int(row[1].split(":")[1], 16) for row in rows if row[3] == "0A" and f"socket:[{row[9]}]" in sockets}


def started_server(store, settings):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    env = {**os.environ, "PORT": str(port), "DATA_DIR": str(store), **settings}
    env.pop("BUCKET", None)
    env.pop("K_SERVICE", None)
    with (Path(store) / "server-log.jsonl").open("a") as log_file:
        process = subprocess.Popen([sys.executable, "-m", "server.app"], env=env, stdout=log_file, stderr=subprocess.DEVNULL)
    for _ in range(480):
        if process.poll() is not None:
            return None
        if port in listening_ports(process.pid):
            return port, process
        time.sleep(0.25)
    process.kill()
    raise TimeoutError("the server did not start listening within 120 s")


@contextmanager
def running_server(store, **settings):
    for _ in range(3):
        if started := started_server(store, settings):
            break
    else:
        raise RuntimeError("the server could not take a free port three times")
    port, process = started
    try:
        yield f"http://127.0.0.1:{port}", process
    finally:
        process.terminate()
        process.wait(10)


@pytest.fixture(scope="module")
def server(store):
    with running_server(store) as (url, _):
        yield url


def test_a_get_on_the_mcp_path_is_refused_at_once(server):
    started = time.monotonic()
    request = urllib.request.Request(f"{server}/mcp", headers={"Accept": "text/event-stream"})
    with pytest.raises(urllib.error.HTTPError) as refused:
        urllib.request.urlopen(request, timeout=10)
    assert refused.value.code == 405 and refused.value.headers["Allow"] == "POST"
    assert time.monotonic() - started < 2


def test_tools_still_answer_over_post(server):
    async def tools():
        async with Client(f"{server}/mcp") as client:
            return {tool.name for tool in (await client.list_tools()).tools}

    assert "draft_analysis" in asyncio.run(tools())


def test_tool_inputs_spell_out_every_field(server):
    async def schemas():
        async with Client(f"{server}/mcp") as client:
            return {tool.name: tool.input_schema for tool in (await client.list_tools()).tools}

    listed = asyncio.run(schemas())
    assert "render_analysis" in listed
    for name, schema in listed.items():
        assert "$ref" not in json.dumps(schema), name


def as_client(server, agent, method, params, **headers):
    request = urllib.request.Request(
        f"{server}/mcp", method="POST",
        data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
        headers={"User-Agent": agent, "Content-Type": "application/json", "Accept": "application/json, text/event-stream", **headers})
    body = urllib.request.urlopen(request, timeout=120).read().decode()
    return next(line[5:] for line in body.splitlines() if line.startswith("data:"))


def test_claude_is_offered_the_upload_card_score_links_and_cards_on_its_own_domain(server):
    listed = {tool["name"]: tool for tool in json.loads(as_client(server, "Claude-User", "tools/list", {}))["result"]["tools"]}
    card = json.loads(as_client(server, "Claude-User", "resources/read", {"uri": "ui://sheet-music-analysis/card-v2.html"}))
    assert set(listed) == {"choose_score", "fetch_score", "read_fetched_pdf", "draft_analysis", "correct_bars", "render_analysis",
                           "play", "draft_from_notes", "send_suggestion"}
    assert "score_file" not in listed["draft_analysis"]["inputSchema"]["properties"]
    assert set(listed["play"]["inputSchema"]["properties"]) == {"score_id", "measure_range", "tempo", "play_id", "notes"}
    assert "fetch_score" in listed["draft_analysis"]["description"] and "read_fetched_pdf" in listed["correct_bars"]["description"]
    assert "(Blank worksheet, MIDI, Analysis as text)" in listed["render_analysis"]["description"]
    assert not [name for name, tool in listed.items() if re.search("RomanText|worksheet PDF", tool["description"])]
    assert card["result"]["contents"][0]["_meta"]["ui"]["domain"].endswith(".claudemcpcontent.com")


def test_a_chat_can_download_the_careful_reading_kit(server):
    opening = {"notetool.py": "import argparse", "note_rules.py": "import re", "tool.md": "# Reading notes with notetool.py", "reader.md": "# Read one page of scanned music"}
    for name, first_words in opening.items():
        assert urllib.request.urlopen(f"{server}/kit/{name}", timeout=30).read().decode().startswith(first_words)
    with pytest.raises(urllib.error.HTTPError) as refused:
        urllib.request.urlopen(f"{server}/kit/app.py", timeout=30)
    assert refused.value.code == 404


CAREFUL_PAGES = [(NOCTURNE.parent / f"careful/dvorak-silhouette-1-page{number}.n1").read_text() for number in (1, 2, 3)]
CHATGPT, CLAUDE = "openai-mcp/1.0.0", "Claude-User"


def read_scan(server, agent, pdf_id):
    return json.loads(as_client(server, agent, "tools/call", {"name": "read_fetched_pdf", "arguments": {"pdf_id": pdf_id}}))["result"]


def careful_call(server, agent, name, **arguments):
    return json.loads(as_client(server, agent, "tools/call", {"name": name, "arguments": arguments}))["result"]


def listed_tools(server, agent):
    return {tool["name"] for tool in json.loads(as_client(server, agent, "tools/list", {}))["result"]["tools"]}


def store_a_read_scan(tmp_path):
    pdf = (NOCTURNE.parent / "chopin-28-4-mutopia.pdf").read_bytes()
    scores = tmp_path / "scores"
    scores.mkdir()
    (scores / "SCAN1.pdf").write_bytes(pdf)
    (scores / "QUICK1N").write_bytes((NOCTURNE.parent / "chopin_prelude_op28_no4_reading.musicxml").read_bytes())
    (scores / "QUICK1N.reading").write_text(json.dumps({"pages": 3}))
    card = {"score_id": "QUICK1N", "pages": 3, "of_pages": 3, "scan": True, "measures": "1 to 25", "bars": 25, "notice": "", "image_url": "",
            "pdf_url": "", "page_images": []}
    (scores / f"pdf-card-{pdf_reader.READER}-{hashlib.sha256(pdf).hexdigest()}.json").write_text(json.dumps(card))
    typeset = pdf + b"\n"
    (scores / "TYPESET1.pdf").write_bytes(typeset)
    (scores / "TYPESET1N").write_bytes((scores / "QUICK1N").read_bytes())
    (scores / f"pdf-card-{pdf_reader.READER}-{hashlib.sha256(typeset).hexdigest()}.json").write_text(
        json.dumps({**card, "score_id": "TYPESET1N", "scan": False}))


CHOPIN_BAR_1 = correct.bars_from_musicxml((NOCTURNE.parent / "chopin_prelude_op28_no4_reading.musicxml").read_bytes(), 1)
CHOPIN_MARK = {"annotations": [{"type": "harmony", "at": {"measure": 1, "beat": 1}, "label": "i", "key": "e"}]}


def drawn_text(server, agent, score_id, **arguments):
    drawn = careful_call(server, agent, "render_analysis", score_id=score_id, annotations=CHOPIN_MARK, **arguments)
    assert not drawn.get("isError"), drawn
    return drawn["content"][-1]["text"]


def test_the_careful_reading_is_offered_on_the_first_drawn_page_of_each_reading_of_a_scan(tmp_path):
    store_a_read_scan(tmp_path)
    with running_server(tmp_path, CAREFUL_READING="chatgpt") as (url, _):
        read_scan(url, CHATGPT, "SCAN1")
        corrected = careful_call(url, CHATGPT, "correct_bars", score_id="QUICK1N",
                                 replacement_bars=CHOPIN_BAR_1.replace("24 C5", "24 D5"))["structuredContent"]["score_id"]
        offered = {"corrected before any drawing": drawn_text(url, CHATGPT, corrected),
                   "the original after that": drawn_text(url, CHATGPT, "QUICK1N"),
                   "a few bars again": drawn_text(url, CHATGPT, "QUICK1N", measure_range="1-4"),
                   "the piano version": drawn_text(url, CHATGPT, "QUICK1N", piano=True)}
        read_scan(url, CHATGPT, "SCAN1")
        offered["after the scan is read again"] = drawn_text(url, CHATGPT, "QUICK1N")
        careful = careful_call(url, CHATGPT, "use_careful_reading", score_id="QUICK1N", pages=CAREFUL_PAGES)
        offered["the careful reading"] = drawn_text(url, CHATGPT, careful["content"][0]["text"].split()[1])
    assert all(("Offer for the user" in text) == ("had a quick reading" in text) for text in offered.values())
    offered = {path: "Offer for the user" in text for path, text in offered.items()}
    assert offered == {"corrected before any drawing": True, "the original after that": False, "a few bars again": False,
                       "the piano version": False, "after the scan is read again": True, "the careful reading": False}
    lines = logged_lines(tmp_path, "render_analysis")
    assert [line.get("careful_offer") for line in lines] == [True, None, None, None, True, None]


def test_only_chatgpt_is_offered_the_analyse_button_on_a_reading(tmp_path):
    store_a_read_scan(tmp_path)
    with running_server(tmp_path) as (url, _):
        offered = {agent: read_scan(url, agent, "SCAN1").get("_meta", {}).get("offer_analysis") for agent in (CHATGPT, CLAUDE, "curl/8.5")}
    assert offered == {CHATGPT: True, CLAUDE: None, "curl/8.5": None}


@pytest.mark.parametrize("setting, offered_to", [(None, set()), ("chatgpt", {CHATGPT}), ("claude", {CLAUDE}),
                                                 ("chatgpt,claude", {CHATGPT, CLAUDE})])
def test_the_careful_reading_is_offered_only_on_the_platforms_it_is_switched_on_for(tmp_path, setting, offered_to):
    store_a_read_scan(tmp_path)
    with running_server(tmp_path, **({"CAREFUL_READING": setting} if setting is not None else {})) as (url, _):
        careful_tools = {"careful_reading", "use_careful_reading"}
        assert careful_tools <= listed_tools(url, CHATGPT)
        assert careful_tools & listed_tools(url, CLAUDE) == (careful_tools if CLAUDE in offered_to else set())
        for agent in (CHATGPT, CLAUDE):
            reading = read_scan(url, agent, "SCAN1")["content"][-1]["text"]
            assert "Shall I go ahead?" not in reading and "Offer for the user" not in reading, agent
            assert ("Question for the user, before any analysis" in reading) == (agent in offered_to), agent
            assert reading.endswith("\nscore_id QUICK1N is ready for careful_reading after a yes, and for draft_analysis otherwise."
                                    if agent in offered_to else "\nscore_id QUICK1N is ready for draft_analysis."), agent
            assert reading == read_scan(url, agent, "TYPESET1")["content"][-1]["text"].replace("TYPESET1N", "QUICK1N"), agent
            first, again = (drawn_text(url, agent, "QUICK1N") for _ in range(2))
            assert "Shall I go ahead?" not in again, agent
            if agent in offered_to:
                assert "Shall I go ahead?" in first and "careful_reading" in first, agent
                assert first.index("shown in a card") < first.index("had a quick reading") < first.index("Offer for the user"), agent
                assert ("usage allowance" in first) == (agent == CLAUDE), agent
                assert first.index("Offer for the user, at the end of the reply with this analysis:") < first.index("Shall I go ahead?"), agent
            else:
                assert "careful" not in first.lower() and "Shall I go ahead?" not in first, agent
        steps = careful_call(url, CHATGPT, "careful_reading", score_id="QUICK1N")
        handed_in = careful_call(url, CHATGPT, "use_careful_reading", score_id="QUICK1N", pages=CAREFUL_PAGES)
        assert not steps.get("isError") and "kit/reader.md" in steps["content"][0]["text"]
        assert not handed_in.get("isError") and handed_in["content"][0]["text"].startswith("score_id: ")
        warning = app.careful_warning(3, "chatgpt")
        assert steps["content"][0]["text"].startswith("These steps are for after the user's yes to this question")
        assert f'"{warning} Shall I go ahead?"' in steps["content"][0]["text"].split("\n", 1)[0]
        if CLAUDE in offered_to:
            asked_in_claude = careful_call(url, CLAUDE, "careful_reading", score_id="QUICK1N")["content"][0]["text"].split("\n", 1)[0]
            assert f'"{app.careful_warning(3, "claude")} Shall I go ahead?"' in asked_in_claude and "usage allowance" in asked_in_claude


def test_the_chord_symbols_of_pages_handed_in_reach_the_table_of_notes(tmp_path):
    store_a_read_scan(tmp_path)
    page = (NOCTURNE.parent / "chord_symbols/amazing-grace-lead-sheet-page.n1").read_text()
    with running_server(tmp_path, CAREFUL_READING="chatgpt") as (url, _):
        handed_in = careful_call(url, CHATGPT, "use_careful_reading", score_id="QUICK1N", pages=[page])
        code = handed_in["content"][0]["text"].split()[1]
        drafted = careful_call(url, CHATGPT, "draft_analysis", score_id=code)
    table = "".join(part.get("text", "") for part in drafted["content"]).split("\nNOTES (", 1)[1]
    assert re.findall(r"chord symbol (\S+)@1(?!\d)", table)[:3] == ["G", "G7", "C"]
    assert "chord symbol Em@3\nm14" in table
    assert re.findall(r"chord symbol (\S+)@\d", table) == PRINTED


def test_chatgpt_keeps_its_tools_and_attachment_arguments(server):
    listed = {tool["name"]: tool for tool in json.loads(as_client(server, "openai-mcp/1.0.0", "tools/list", {}))["result"]["tools"]}
    assert set(listed) == {"draft_analysis", "render_analysis", "correct_bars", "read_pdf", "rate_analysis", "report_problem", "send_suggestion",
                           "asked_to_analyse", "careful_reading", "use_careful_reading"}
    assert "pdf_file" in listed["read_pdf"]["inputSchema"]["properties"]
    assert "score_file" in listed["draft_analysis"]["inputSchema"]["properties"]


@pytest.mark.parametrize("url", ["http://example.com/score.pdf", "https://127.0.0.1/score.pdf", "https://localhost/score.pdf",
                                 "https://169.254.169.254/computeMetadata/v1/", "https://metadata.google.internal/",
                                 "https://10.0.0.1/score.pdf", "https://[::1]/score.pdf"])
def test_links_to_private_addresses_are_refused(server, url):
    result = json.loads(as_client(server, "Claude-User", "tools/call", {"name": "fetch_score", "arguments": {"url": url}}))["result"]
    assert result["isError"] and "not a public https URL" in result["content"][0]["text"]


def test_a_whole_piece_drawn_for_claude_fits_its_result_limit(server, store):
    (store / "scores").mkdir(exist_ok=True)
    (store / "scores" / "NOCTURNE").write_bytes(NOCTURNE.read_bytes())
    marks = [{"type": "harmony", "at": {"measure": bar, "beat": beat}, "label": "V65/IV", "key": "Eb"}
             for bar in range(1, 34) for beat in (1, 3)]
    arguments = {"name": "render_analysis", "arguments": {"score_id": "NOCTURNE", "annotations": {"annotations": marks}}}
    claude, chatgpt = (as_client(server, agent, "tools/call", arguments) for agent in ("Claude-User", "openai-mcp/1.0.0"))
    assert len(claude) < 150_000
    assert "image" in [part["type"] for part in json.loads(chatgpt)["result"]["content"]]
    content = json.loads(claude)["result"]["content"]
    assert [part["type"] for part in content] == ["text", "text"] and "left out" in content[0]["text"]
    assert json.loads(claude)["result"]["structuredContent"]["image_url"]


def test_a_reading_too_large_for_claude_still_ends_with_the_next_step(server, store):
    pdf = (NOCTURNE.parent / "chopin-28-4-mutopia.pdf").read_bytes()
    pdf_id = card_id(server)
    upload(server, pdf, pdf_id)
    page = base64.b64encode(os.urandom(60_000)).decode()
    card = {"score_id": "READ1N", "pages": 1, "scan": False, "measures": "1 to 25", "bars": 25, "notice": "",
            "image_url": "", "pdf_url": "", "page_images": [page, page]}
    (store / app.card_of(hashlib.sha256(pdf).hexdigest())).write_text(json.dumps(card))
    content = as_claude(server, "tools/call", {"name": "read_fetched_pdf", "arguments": {"pdf_id": pdf_id}})["content"]
    assert "image" in [part["type"] for part in content] and "left out" in content[-2]["text"]
    assert content[-1]["text"].endswith("\nscore_id READ1N is ready for draft_analysis.")


def as_claude(server, method, params):
    return json.loads(as_client(server, "Claude-User", method, params))["result"]


def card_id(server):
    return as_claude(server, "tools/call", {"name": "choose_score", "arguments": {}})["structuredContent"]["upload_id"]


def upload(server, data, code, origin="https://abc.claudemcpcontent.com"):
    request = urllib.request.Request(f"{server}/upload?id={code}", data=data, method="POST", headers={"Origin": origin})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.headers, json.loads(response.read())
    except urllib.error.HTTPError as refused:
        return refused.code, refused.headers, json.loads(refused.read())


def test_the_upload_card_tool_shows_the_card_that_sends_to_this_server(server):
    listed = {tool["name"]: tool for tool in as_claude(server, "tools/list", {})["tools"]}
    uri = listed["choose_score"]["_meta"]["ui"]["resourceUri"]
    shown = as_claude(server, "tools/call", {"name": "choose_score", "arguments": {}})
    card = as_claude(server, "resources/read", {"uri": uri})["contents"][0]
    port = server.rsplit(":", 1)[1]
    code = shown["structuredContent"]["upload_id"]
    assert not shown.get("isError") and "the next step comes with their message" in shown["content"][0]["text"]
    assert f"{code} is the pdf_id for read_fetched_pdf" in shown["content"][0]["text"]
    assert f"{code} is the score_id for draft_analysis" in shown["content"][0]["text"]
    assert "choose the same file again in the card below" in shown["content"][0]["text"]
    assert card["_meta"]["ui"]["domain"].endswith(".claudemcpcontent.com")
    assert card["_meta"]["ui"]["csp"]["connectDomains"] == [f"http://localhost:{port}"]
    assert f'"http://localhost:{port}/upload"' in card["text"]


def test_a_score_chosen_in_the_card_is_kept_drafted_and_drawn_for_claude(server, store):
    score_id = card_id(server)
    too_soon = as_claude(server, "tools/call", {"name": "draft_analysis", "arguments": {"score_id": score_id}})
    status, headers, body = upload(server, NOCTURNE.read_bytes(), score_id)
    again = upload(server, NOCTURNE.read_bytes(), score_id)
    assert not too_soon.get("isError") and "has not chosen their file in the card yet" in too_soon["content"][0]["text"]
    assert status == 200 and headers["Access-Control-Allow-Origin"] == "*" and body == {"kind": "musicxml"}
    assert again[0] == 409 and "already chosen in this card" in again[2]["error"]
    assert (store / "scores" / score_id).is_file()
    drafted = as_claude(server, "tools/call", {"name": "draft_analysis", "arguments": {"score_id": score_id, "measure_range": "1-2"}})
    marks = [{"type": "harmony", "at": {"measure": 1, "beat": 1}, "label": "I", "key": "Eb"}]
    drawn = as_claude(server, "tools/call", {"name": "render_analysis", "arguments": {
        "score_id": score_id, "measure_range": "1-2", "annotations": {"annotations": marks}}})
    assert not drafted.get("isError") and drafted["content"][0]["text"].startswith(f"score_id: {score_id}")
    assert not drawn.get("isError") and drawn["structuredContent"]["image_url"]


def test_a_score_saved_as_utf_16_is_kept_drafted_and_drawn(server, store):
    intermezzo = (NOCTURNE.parent / "export-brahms-118-2.musicxml").read_text(encoding="utf-8")
    score = intermezzo.replace("encoding='utf-8'", "encoding='UTF-16'", 1).encode("utf-16")
    score_id = card_id(server)
    status, _, body = upload(server, score, score_id)
    drafted = as_claude(server, "tools/call", {"name": "draft_analysis", "arguments": {"score_id": score_id, "measure_range": "1-2"}})
    marks = [{"type": "harmony", "at": {"measure": 1, "beat": 1}, "label": "I", "key": "A"}]
    drawn = as_claude(server, "tools/call", {"name": "render_analysis", "arguments": {
        "score_id": score_id, "measure_range": "1-2", "annotations": {"annotations": marks}}})
    assert "encoding='UTF-16'" in score.decode("utf-16")
    assert status == 200 and body == {"kind": "musicxml"}
    assert not drafted.get("isError") and drafted["content"][0]["text"].startswith(f"score_id: {score_id}")
    assert not drawn.get("isError") and drawn["structuredContent"]["image_url"]


def test_a_pdf_chosen_in_the_card_is_kept_for_the_pdf_reader(server, store):
    pdf = (NOCTURNE.parent / "chopin-28-4-mutopia.pdf").read_bytes()
    pdf_id = card_id(server)
    status, _, body = upload(server, pdf, pdf_id)
    assert status == 200 and body == {"kind": "pdf"}
    assert (store / "scores" / f"{pdf_id}.pdf").is_file()


def test_an_upload_without_a_card_id_from_this_server_is_refused(server, store):
    unknown = upload(server, NOCTURNE.read_bytes(), "0123456789ABCDEF")
    missing = upload(server, NOCTURNE.read_bytes(), "")
    assert unknown[0] == missing[0] == 404 and "This card has expired" in unknown[2]["error"]
    assert not (store / "scores" / "0123456789ABCDEF").exists()


def test_the_upload_refuses_what_is_not_a_score_and_answers_the_browser_s_preflight(server):
    preflight = urllib.request.Request(f"{server}/upload", method="OPTIONS",
                                       headers={"Access-Control-Request-Headers": "content-type,x-device"})
    with urllib.request.urlopen(preflight, timeout=10) as response:
        assert response.status == 204 and "POST" in response.headers["Access-Control-Allow-Methods"]
        assert response.headers["Access-Control-Allow-Headers"] == "content-type, x-device"
    page = upload(server, b"<!DOCTYPE html><html><body>Sign in</body></html>", card_id(server))
    empty = upload(server, b"", card_id(server))
    assert page[0] == 415 and page[1]["Access-Control-Allow-Origin"] == "*" and "not a MusicXML file or a PDF" in page[2]["error"]
    assert empty[0] == 415


def test_an_upload_announced_over_10_mb_is_refused_before_its_body_is_read(server):
    host, port = server.removeprefix("http://").split(":")
    code = card_id(server)
    with socket.create_connection((host, int(port)), timeout=10) as connection:
        connection.sendall(f"POST /upload?id={code} HTTP/1.1\r\nHost: x\r\nContent-Length: 20000000\r\n\r\n".encode())
        answer = b""
        while b"larger than" not in answer and (part := connection.recv(4096)):
            answer += part
    answer = answer.decode()
    assert answer.startswith("HTTP/1.1 413") and "larger than 10 MB" in answer


def test_health_still_answers(server):
    assert urllib.request.urlopen(f"{server}/health", timeout=5).read() == b"ok"


def test_with_a_proxy_key_set_only_requests_that_carry_it_are_served(tmp_path):
    with running_server(tmp_path, PROXY_KEY="the key of this test") as (locked, _):
        with pytest.raises(urllib.error.HTTPError) as no_key:
            as_client(locked, "Claude-User", "tools/list", {})
        with pytest.raises(urllib.error.HTTPError) as wrong_key:
            as_client(locked, "Claude-User", "tools/list", {}, **{"X-Proxy-Key": "another key"})
        with pytest.raises(urllib.error.HTTPError) as upload_without:
            urllib.request.urlopen(urllib.request.Request(f"{locked}/upload?id=0123456789ABCDEF", data=b"x", method="POST"), timeout=10)
        listed = json.loads(as_client(locked, "Claude-User", "tools/list", {}, **{"X-Proxy-Key": "the key of this test"}))
        health = urllib.request.urlopen(f"{locked}/health", timeout=10)
    assert no_key.value.code == wrong_key.value.code == upload_without.value.code == 403
    assert "mcp.sheetmusicanalysis.com" in no_key.value.read().decode()
    assert "draft_analysis" in {tool["name"] for tool in listed["result"]["tools"]}
    assert health.status == 200


def test_every_answer_from_our_server_carries_the_mark_the_proxy_retries_without(tmp_path):
    def answer(path, key="the key of this test", **sent):
        request = urllib.request.Request(f"{locked}{path}", headers={"X-Proxy-Key": key, "Accept": "application/json, text/event-stream",
                                                                     "Content-Type": "application/json"}, **sent)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status, response.headers.get("x-answered-by")
        except urllib.error.HTTPError as refused:
            return refused.code, refused.headers.get("x-answered-by")

    listing = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}).encode()
    with running_server(tmp_path, PROXY_KEY="the key of this test") as (locked, _):
        answers = [answer("/mcp", data=listing, method="POST"), answer("/mcp", key="another key", data=listing, method="POST"),
                   answer("/mcp"), answer("/files/nothing-here.png"), answer("/health")]
    assert [status for status, _ in answers] == [200, 403, 405, 404, 200]
    assert {mark for _, mark in answers} == {"sheet-music-analysis"}


def test_a_request_without_the_key_gets_the_whole_refusal_while_its_body_is_still_arriving(tmp_path):
    size = 2_000_000

    def refused(port):
        with socket.create_connection(("127.0.0.1", port), timeout=10) as connection:
            connection.sendall(f"POST /mcp HTTP/1.1\r\nHost: x\r\nConnection: close\r\nContent-Length: {size}\r\n\r\n".encode())
            connection.sendall(b"x" * size)
            answer = b""
            while part := connection.recv(4096):
                answer += part
            return answer.decode()

    with running_server(tmp_path, PROXY_KEY="the key of this test") as (locked, _):
        answers = [refused(int(locked.rsplit(":", 1)[1])) for _ in range(10)]
    assert all(answer.startswith("HTTP/1.1 403") and "mcp.sheetmusicanalysis.com" in answer for answer in answers)


def test_a_request_without_the_key_whose_body_never_ends_is_refused_after_a_short_wait_and_holds_no_one_up(tmp_path):
    with running_server(tmp_path, PROXY_KEY="the key of this test") as (locked, _):
        with socket.create_connection(("127.0.0.1", int(locked.rsplit(":", 1)[1])), timeout=30) as stalled:
            stalled.sendall(b"POST /mcp HTTP/1.1\r\nHost: x\r\nConnection: close\r\nContent-Length: 10000000\r\n\r\nxx")
            started = time.monotonic()
            listed = json.loads(as_client(locked, "Claude-User", "tools/list", {}, **{"X-Proxy-Key": "the key of this test"}))
            served = time.monotonic() - started
            answer = b""
            while part := stalled.recv(4096):
                answer += part
            refused = time.monotonic() - started
    assert "draft_analysis" in {tool["name"] for tool in listed["result"]["tools"]}
    assert served < refused
    assert answer.startswith(b"HTTP/1.1 403") and refused < app.REFUSED_BODY_SECONDS + 5


def test_while_the_key_changes_the_previous_key_is_served_too(tmp_path):
    with running_server(tmp_path, PROXY_KEY="the new key", PROXY_KEY_PREVIOUS="the old key") as (changing, _):
        old = json.loads(as_client(changing, "Claude-User", "tools/list", {}, **{"X-Proxy-Key": "the old key"}))
        new = json.loads(as_client(changing, "Claude-User", "tools/list", {}, **{"X-Proxy-Key": "the new key"}))
        with pytest.raises(urllib.error.HTTPError) as other:
            as_client(changing, "Claude-User", "tools/list", {}, **{"X-Proxy-Key": "another key"})
    assert "draft_analysis" in {tool["name"] for tool in old["result"]["tools"]} & {tool["name"] for tool in new["result"]["tools"]}
    assert other.value.code == 403



NO_NOTES = ("This file has no notes in it, only empty bars. Export it again from your music program, or send a PDF "
            "of the score.")
WHOLE_BAR_REST = '<note><rest measure="yes"/><duration>4</duration></note>'
PITCHED = '<note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>whole</type></note>'
UNPITCHED = ('<note><unpitched><display-step>E</display-step><display-octave>4</display-octave></unpitched>'
             '<duration>4</duration><type>whole</type></note>')


def one_bar_score(*parts):
    listed = "".join(f'<score-part id="P{n}"><part-name>Part {n}</part-name></score-part>' for n in range(1, len(parts) + 1))
    attributes = ("<attributes><divisions>1</divisions><time><beats>4</beats><beat-type>4</beat-type></time>"
                  "<clef><sign>G</sign><line>2</line></clef></attributes>")
    written = "".join(f'<part id="P{n}">' + (f'<measure number="1">{attributes}{content}</measure>' if content else "") + "</part>"
                      for n, content in enumerate(parts, start=1))
    return (f'<?xml version="1.0" encoding="UTF-8"?><score-partwise version="4.0"><part-list>{listed}</part-list>'
            f"{written}</score-partwise>").encode()


def packed(score):
    sink = io.BytesIO()
    with zipfile.ZipFile(sink, "w") as archive:
        archive.writestr("META-INF/container.xml", '<container><rootfiles><rootfile full-path="score.xml"/></rootfiles></container>')
        archive.writestr("score.xml", score)
    return sink.getvalue()


WITHOUT_NOTES = {"a-whole-bar-rest": one_bar_score(WHOLE_BAR_REST), "two-silent-parts": one_bar_score(WHOLE_BAR_REST, ""),
                 "no-bars": one_bar_score(""), "packed": packed(one_bar_score(WHOLE_BAR_REST)),
                 "utf-16": one_bar_score(WHOLE_BAR_REST).decode().replace("UTF-8", "UTF-16").encode("utf-16")}


def tool_answer(server, agent, name, **arguments):
    return json.loads(as_client(server, agent, "tools/call", {"name": name, "arguments": arguments}))["result"]


def refused_plainly(answer):
    return answer.get("isError") and [part["text"] for part in answer["content"]] == [NO_NOTES]


@pytest.mark.parametrize("kind", list(WITHOUT_NOTES))
def test_a_score_with_no_notes_chosen_in_the_card_is_answered_plainly_by_every_tool_claude_gives_it_to(server, kind):
    score_id = card_id(server)
    assert upload(server, WITHOUT_NOTES[kind], score_id)[0] == 200
    answers = {name: tool_answer(server, CLAUDE, name, score_id=score_id, **arguments) for name, arguments in {
        "draft_analysis": {}, "render_analysis": {"annotations": {"annotations": [{"type": "harmony", "at": {"measure": 1, "beat": 1}, "label": "I", "key": "C"}]}}, "play": {}}.items()}
    assert {name for name, answer in answers.items() if refused_plainly(answer)} == set(answers), answers


def test_a_reading_with_no_notes_can_still_be_read_carefully_and_corrected(tmp_path):
    store_a_read_scan(tmp_path)
    (tmp_path / "scores" / "QUICK1N").write_bytes(one_bar_score(WHOLE_BAR_REST))
    with running_server(tmp_path, CAREFUL_READING="chatgpt") as (url, _):
        steps = careful_call(url, CHATGPT, "careful_reading", score_id="QUICK1N")
        corrected = careful_call(url, CHATGPT, "correct_bars", score_id="QUICK1N", replacement_bars="")
    assert not steps.get("isError") and "kit/reader.md" in steps["content"][0]["text"]
    assert not refused_plainly(corrected)


@pytest.mark.parametrize("kind", list(WITHOUT_NOTES))
def test_a_stored_score_with_no_notes_is_answered_plainly_to_chatgpt(server, store, kind):
    (store / "scores").mkdir(exist_ok=True)
    (store / "scores" / "NONOTES").write_bytes(WITHOUT_NOTES[kind])
    drafted = tool_answer(server, CHATGPT, "draft_analysis", score_id="NONOTES")
    drawn = tool_answer(server, CHATGPT, "render_analysis", score_id="NONOTES", annotations={"annotations": [{"type": "harmony", "at": {"measure": 1, "beat": 1}, "label": "I", "key": "C"}]})
    assert refused_plainly(drafted) and refused_plainly(drawn), (drafted, drawn)


@pytest.mark.parametrize("score", [one_bar_score(PITCHED), one_bar_score(UNPITCHED), one_bar_score(WHOLE_BAR_REST, PITCHED)],
                         ids=["pitched", "percussion", "one-silent-part-among-sounding-ones"])
def test_a_score_with_any_note_is_drafted(server, score):
    score_id = card_id(server)
    upload(server, score, score_id)
    drafted = tool_answer(server, CLAUDE, "draft_analysis", score_id=score_id)
    assert not drafted.get("isError") and drafted["content"][0]["text"].startswith(f"score_id: {score_id}")


@pytest.mark.parametrize("name, arguments", [
    ("draft_analysis", {"score_file": {"download_url": "https://example.com/score.musicxml", "file_id": "file-1"}}),
    ("fetch_score", {"url": "https://example.com/score.musicxml"})])
def test_a_file_with_no_notes_that_is_attached_or_linked_is_a_user_error_with_the_sentence_as_its_reason(
        monkeypatch, tmp_path, capsys, name, arguments):
    async def download(url):
        return WITHOUT_NOTES["a-whole-bar-rest"]

    monkeypatch.setattr(app, "store", app.LocalStore(tmp_path))
    monkeypatch.setattr(app, "download", download)

    async def go():
        async with Client(app.mcp) as client:
            answered = await client.call_tool(name, arguments)
            if name == "fetch_score":
                score_id = answered.content[0].text.split("score_id: ", 1)[1].split()[0]
                answered = await client.call_tool("draft_analysis", {"score_id": score_id})
            return answered

    answered = asyncio.run(go())
    line = [json.loads(line) for line in capsys.readouterr().out.splitlines() if '"tool": "draft_analysis"' in line][-1]
    assert answered.is_error and [part.text for part in answered.content] == [NO_NOTES]
    assert (line["outcome"], line["error"], line["reason"]) == ("user_error", "ScoreError", NO_NOTES)
    if name == "draft_analysis":
        assert not list(tmp_path.glob("scores/*")) and not list(tmp_path.glob("limits/*")) and not list(tmp_path.glob("usage/*"))


AGENT_TURN = ("openai-mcp/1.0.0 (Codex)",
              {"callId": "exec-1", "itemId": "item-1", "sessionId": "session-1", "windowId": "window-1",
               "io.modelcontextprotocol/clientInfo": {"name": "openai-mcp (Codex)", "version": "1.0.0"},
               "openai/subject": "user-1"})
ORDINARY_TURN = ("openai-mcp/1.0.0",
                 {"io.modelcontextprotocol/clientInfo": {"name": "openai-mcp", "version": "1.0.0"},
                  "openai/locale": "en-US", "openai/userAgent": "Mozilla/5.0", "timezone": "America/New_York",
                  "timezone_offset_minutes": -300, "openai/subject": "user-1"})
UNKNOWN_CHATGPT = (CHATGPT, {})
CLAUDE_CALL = (CLAUDE, {})


def logged_lines(store, tool):
    lines = [json.loads(line) for line in (store / "server-log.jsonl").read_text().splitlines() if line.startswith("{")]
    return [line for line in lines if line.get("tool") == tool]


def test_an_ordinary_chatgpt_turn_is_told_how_to_start_the_careful_reading_and_the_others_get_the_steps(tmp_path):
    store_a_read_scan(tmp_path)
    with running_server(tmp_path, CAREFUL_READING="chatgpt,claude") as (url, _):
        answers = {}
        for name, (agent, meta) in {"agent": AGENT_TURN, "ordinary": ORDINARY_TURN, "unknown": UNKNOWN_CHATGPT,
                                    "claude": CLAUDE_CALL}.items():
            call = {"name": "careful_reading", "arguments": {"score_id": "QUICK1N"}, "_meta": meta}
            answers[name] = json.loads(as_client(url, agent, "tools/call", call))["result"]["content"][0]["text"]
    for name in ("agent", "unknown", "claude"):
        assert "kit/reader.md" in answers[name] and "@Sheet Music Analysis" not in answers[name], name
    ordinary = answers["ordinary"]
    assert "kit/" not in ordinary and "curl" not in ordinary
    assert ('Note for the user: "I can\'t start the careful reading from this message. To start it, type '
            '@Sheet Music Analysis, choose the app from the list, and say yes again."') in ordinary
    assert "thinking" not in ordinary
    assert "QUICK1N" not in ordinary
    lines = logged_lines(tmp_path, "careful_reading")
    assert [(line.get("route"), line["answer"]) for line in lines] == [
        ("agent", "steps"), ("ordinary", "needs_the_agent"), ("unknown", "steps"), (None, "steps")]
    assert lines[0]["user"] == lines[1]["user"] and len(lines[0]["user"]) == 16
    with running_server(tmp_path, CAREFUL_READING="chatgpt", CHATGPT_APP_NAME="sheet-music-staging") as (url, _):
        call = {"name": "careful_reading", "arguments": {"score_id": "QUICK1N"}, "_meta": ORDINARY_TURN[1]}
        on_staging = json.loads(as_client(url, ORDINARY_TURN[0], "tools/call", call))["result"]["content"][0]["text"]
    assert "To start it, type @sheet-music-staging, choose the app from the list" in on_staging


def called(server, caller, name, **arguments):
    agent, meta = caller
    return json.loads(as_client(server, agent, "tools/call", {"name": name, "arguments": arguments, "_meta": meta}))["result"]


@pytest.mark.parametrize("pdf, score_id", [("SCAN1", "QUICK1N"), ("TYPESET1", "TYPESET1N")])
def test_every_pdf_reading_recommends_the_careful_reading_first_and_a_yes_or_a_no_goes_on_from_there(tmp_path, pdf, score_id):
    store_a_read_scan(tmp_path)
    callers = {"agent": AGENT_TURN, "ordinary": ORDINARY_TURN, "unknown": UNKNOWN_CHATGPT, "claude": CLAUDE_CALL}
    with running_server(tmp_path, CAREFUL_READING="chatgpt,claude") as (url, _):
        for name, caller in callers.items():
            reading = called(url, caller, "read_fetched_pdf", pdf_id=pdf)["content"][-1]["text"]
            asked = name != "ordinary"
            assert ("Question for the user, before any analysis" in reading) == asked, name
            assert ("To start it, type @Sheet Music Analysis, choose the app from the list, and ask for the careful reading."
                    in reading) == (not asked), name
            assert ("usage allowance" in reading) == (name == "claude"), name
            assert "this piece's 3 pages takes about 15 minutes" in reading, name
            assert reading.index("Note for the user about the reading") < reading.index("I recommend a careful reading"), name

            steps = called(url, caller, "careful_reading", score_id=score_id)["content"][0]["text"]
            if not asked:
                assert "I can't start the careful reading from this message" in steps and "kit/" not in steps
            else:
                assert steps.startswith("These steps are for after the user's yes to this question (unless they have "
                                        "already said yes to a careful reading in this chat)"), name
                reading_id = re.search(r"use_careful_reading takes this careful reading's own score_id \((\w+)\)", steps)[1]
                handed_in = called(url, caller, "use_careful_reading", score_id=reading_id, pages=CAREFUL_PAGES)
                text = handed_in["content"][0]["text"]
                assert not handed_in.get("isError") and "my careful reading of your PDF" in text, name
                assert not called(url, caller, "draft_analysis", score_id=text.split()[1]).get("isError"), name

            assert not called(url, caller, "draft_analysis", score_id=score_id).get("isError"), name
            drawn = [called(url, caller, "render_analysis", score_id=score_id, annotations=CHOPIN_MARK)["content"][-1]["text"]
                     for _ in range(2)]
            assert ("Offer for the user" in drawn[0]) == asked and "Offer for the user" not in drawn[1], name
    reads = logged_lines(tmp_path, "read_fetched_pdf")
    assert [line.get("route") for line in reads] == ["agent", "ordinary", "unknown", None]
    assert [line["answer"] for line in logged_lines(tmp_path, "careful_reading")] == ["steps", "needs_the_agent", "steps", "steps"]
