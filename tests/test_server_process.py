import asyncio
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from mcp.client.client import Client


NOCTURNE = Path(__file__).parent / "data" / "chopin_nocturne_op9_no2.mxl"


@pytest.fixture(scope="module")
def store(tmp_path_factory):
    return tmp_path_factory.mktemp("store")


@pytest.fixture(scope="module")
def server(store):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    env = {**os.environ, "PORT": str(port), "DATA_DIR": str(store)}
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
    yield url
    process.terminate()
    process.wait(10)


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


def as_client(server, agent, method, params):
    request = urllib.request.Request(
        f"{server}/mcp", method="POST",
        data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
        headers={"User-Agent": agent, "Content-Type": "application/json", "Accept": "application/json, text/event-stream"})
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
    assert card["result"]["contents"][0]["_meta"]["ui"]["domain"].endswith(".claudemcpcontent.com")


def test_chatgpt_keeps_its_tools_and_attachment_arguments(server):
    listed = {tool["name"]: tool for tool in json.loads(as_client(server, "openai-mcp/1.0.0", "tools/list", {}))["result"]["tools"]}
    assert set(listed) == {"draft_analysis", "render_analysis", "correct_bars", "read_pdf", "rate_analysis", "report_problem", "send_suggestion"}
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
    assert [part["type"] for part in content] == ["text", "text"] and "left out" in content[1]["text"]
    assert json.loads(claude)["result"]["structuredContent"]["image_url"]


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
    assert f"draft_analysis with score_id {code}" in shown["content"][0]["text"]
    assert card["_meta"]["ui"]["domain"].endswith(".claudemcpcontent.com")
    assert card["_meta"]["ui"]["csp"]["connectDomains"] == [f"http://localhost:{port}"]
    assert f'"http://localhost:{port}/upload"' in card["text"]


def test_a_score_chosen_in_the_card_is_kept_drafted_and_drawn_for_claude(server, store):
    score_id = card_id(server)
    too_soon = as_claude(server, "tools/call", {"name": "draft_analysis", "arguments": {"score_id": score_id}})
    status, headers, body = upload(server, NOCTURNE.read_bytes(), score_id)
    again = upload(server, NOCTURNE.read_bytes(), score_id)
    assert too_soon["isError"] and "has not chosen their file in the card yet" in too_soon["content"][0]["text"]
    assert status == 200 and headers["Access-Control-Allow-Origin"] == "*" and body == {"kind": "musicxml"}
    assert again[0] == 409 and "already chosen in this card" in again[2]["error"]
    assert (store / "scores" / score_id).is_file()
    drafted = as_claude(server, "tools/call", {"name": "draft_analysis", "arguments": {"score_id": score_id, "measure_range": "1-2"}})
    marks = [{"type": "harmony", "at": {"measure": 1, "beat": 1}, "label": "I", "key": "Eb"}]
    drawn = as_claude(server, "tools/call", {"name": "render_analysis", "arguments": {
        "score_id": score_id, "measure_range": "1-2", "annotations": {"annotations": marks}}})
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
    preflight = urllib.request.Request(f"{server}/upload", method="OPTIONS")
    with urllib.request.urlopen(preflight, timeout=10) as response:
        assert response.status == 204 and "POST" in response.headers["Access-Control-Allow-Methods"]
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
