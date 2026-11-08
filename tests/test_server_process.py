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


def test_claude_is_offered_score_links_and_cards_on_its_own_domain(server):
    listed = {tool["name"]: tool for tool in json.loads(as_client(server, "Claude-User", "tools/list", {}))["result"]["tools"]}
    card = json.loads(as_client(server, "Claude-User", "resources/read", {"uri": "ui://sheet-music-analysis/card-v2.html"}))
    assert set(listed) == {"fetch_score", "read_fetched_pdf", "draft_analysis", "correct_bars", "render_analysis",
                           "play", "draft_from_notes"}
    assert "score_file" not in listed["draft_analysis"]["inputSchema"]["properties"]
    assert "fetch_score" in listed["draft_analysis"]["description"] and "read_fetched_pdf" in listed["correct_bars"]["description"]
    assert card["result"]["contents"][0]["_meta"]["ui"]["domain"].endswith(".claudemcpcontent.com")


def test_chatgpt_keeps_its_tools_and_attachment_arguments(server):
    listed = {tool["name"]: tool for tool in json.loads(as_client(server, "openai-mcp/1.0.0", "tools/list", {}))["result"]["tools"]}
    assert set(listed) == {"draft_analysis", "render_analysis", "correct_bars", "read_pdf", "rate_analysis"}
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


def test_health_still_answers(server):
    assert urllib.request.urlopen(f"{server}/health", timeout=5).read() == b"ok"
