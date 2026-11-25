import asyncio
import base64
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path

import pytest
from mcp.client.client import Client

from engine import read_pdf as pdf_reader
from server import app


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
    process = subprocess.Popen([sys.executable, "-m", "server.app"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
                           "play", "draft_from_notes", "send_suggestion", "asked_to_analyse"}
    assert "score_file" not in listed["draft_analysis"]["inputSchema"]["properties"]
    assert set(listed["play"]["inputSchema"]["properties"]) == {"score_id", "measure_range", "tempo", "play_id", "notes"}
    assert "fetch_score" in listed["draft_analysis"]["description"] and "read_fetched_pdf" in listed["correct_bars"]["description"]
    assert "(Blank worksheet, MIDI, Analysis as text)" in listed["render_analysis"]["description"]
    assert not [name for name, tool in listed.items() if re.search("RomanText|worksheet PDF", tool["description"])]
    assert card["result"]["contents"][0]["_meta"]["ui"]["domain"].endswith(".claudemcpcontent.com")


def test_a_chat_can_download_the_careful_reading_kit(server):
    opening = {"notetool.py": "import argparse", "tool.md": "# Reading notes with notetool.py", "reader.md": "# Read one page of scanned music"}
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


@pytest.mark.parametrize("setting, offered_to", [(None, set()), ("chatgpt", {CHATGPT}), ("claude", {CLAUDE}),
                                                 ("chatgpt,claude", {CHATGPT, CLAUDE})])
def test_the_careful_reading_is_offered_only_on_the_platforms_it_is_switched_on_for(tmp_path, setting, offered_to):
    pdf = (NOCTURNE.parent / "chopin-28-4-mutopia.pdf").read_bytes()
    scores = tmp_path / "scores"
    scores.mkdir()
    (scores / "SCAN1.pdf").write_bytes(pdf)
    (scores / "QUICK1N").write_bytes((NOCTURNE.parent / "chopin_prelude_op28_no4_reading.musicxml").read_bytes())
    (scores / "QUICK1N.scan").write_text(json.dumps({"pages": 3}))
    card = {"score_id": "QUICK1N", "pages": 3, "scan": True, "measures": "1 to 25", "bars": 25, "notice": "", "image_url": "",
            "pdf_url": "", "page_images": []}
    (scores / f"pdf-card-{pdf_reader.READER}-{hashlib.sha256(pdf).hexdigest()}.json").write_text(json.dumps(card))
    with running_server(tmp_path, **({"CAREFUL_READING": setting} if setting is not None else {})) as (url, _):
        careful_tools = {"careful_reading", "use_careful_reading"}
        assert careful_tools <= listed_tools(url, CHATGPT)
        assert careful_tools & listed_tools(url, CLAUDE) == (careful_tools if CLAUDE in offered_to else set())
        for agent in (CHATGPT, CLAUDE):
            offer = read_scan(url, agent, "SCAN1")["content"][-1]["text"]
            assert "draft_analysis with this score_id now" in offer, agent
            if agent in offered_to:
                assert "Shall I go ahead?" in offer and "careful_reading" in offer, agent
                assert ("usage allowance" in offer) == (agent == CLAUDE), agent
                assert offer.index("draft_analysis with this score_id now") < offer.index("Shall I go ahead?"), agent
            else:
                assert "careful" not in offer.lower() and "Shall I go ahead?" not in offer, agent
        steps = careful_call(url, CHATGPT, "careful_reading", score_id="QUICK1N")
        handed_in = careful_call(url, CHATGPT, "use_careful_reading", score_id="QUICK1N", pages=CAREFUL_PAGES)
        assert not steps.get("isError") and "kit/reader.md" in steps["content"][0]["text"]
        assert not handed_in.get("isError") and handed_in["content"][0]["text"].startswith("score_id: ")
        warning = app.careful_warning(3, "chatgpt")
        assert steps["content"][0]["text"].startswith("Before any of these steps, ask the user")
        assert f'"{warning}"' in steps["content"][0]["text"].split("\n", 1)[0]
        if CLAUDE in offered_to:
            asked_in_claude = careful_call(url, CLAUDE, "careful_reading", score_id="QUICK1N")["content"][0]["text"].split("\n", 1)[0]
            assert f'"{app.careful_warning(3, "claude")}"' in asked_in_claude and "usage allowance" in asked_in_claude


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
    assert content[-1]["text"].endswith("\nNow call draft_analysis with this score_id.")


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
    assert "choose the same file again in the card below" in listed["choose_score"]["description"]
    code = shown["structuredContent"]["upload_id"]
    assert not shown.get("isError") and "End your reply here" in shown["content"][0]["text"]
    assert f"read_fetched_pdf with pdf_id {code}" in shown["content"][0]["text"]
    assert "you are reading the PDF now" in shown["content"][0]["text"]
    assert f"draft_analysis with score_id {code}" in shown["content"][0]["text"]
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

