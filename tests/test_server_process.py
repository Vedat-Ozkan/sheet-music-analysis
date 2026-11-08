import asyncio
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest
from mcp.client.client import Client


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    env = {**os.environ, "PORT": str(port), "DATA_DIR": str(tmp_path_factory.mktemp("store"))}
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


def test_a_picked_score_reaches_the_tools_as_claude_sees_them(server):
    score = open("tests/data/chopin_nocturne_op9_no2.mxl", "rb").read()
    picked = urllib.request.Request(f"{server}/upload", data=score, method="POST",
                                    headers={"Origin": "https://example.claudemcpcontent.com"})
    with urllib.request.urlopen(picked, timeout=10) as response:
        assert response.headers["Access-Control-Allow-Origin"] == "*"
        score_id = json.loads(response.read())["score_id"]
    pdf = urllib.request.Request(f"{server}/upload", data=open("tests/data/chopin-28-4-mutopia.pdf", "rb").read(), method="POST")
    assert "pdf_id" in json.loads(urllib.request.urlopen(pdf, timeout=10).read())

    def as_claude(method, params):
        request = urllib.request.Request(
            f"{server}/mcp", method="POST",
            data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
            headers={"User-Agent": "Claude-User", "Content-Type": "application/json",
                     "Accept": "application/json, text/event-stream"})
        body = urllib.request.urlopen(request, timeout=10).read().decode()
        return json.loads(next(line[5:] for line in body.splitlines() if line.startswith("data:")))["result"]

    listed = {tool["name"]: tool for tool in as_claude("tools/list", {})["tools"]}
    card = as_claude("resources/read", {"uri": "ui://sheet-music-analysis/card-v2.html"})["contents"][0]
    drafted = as_claude("tools/call", {"name": "draft_analysis", "arguments": {"score_id": score_id, "measure_range": "1-2"}})
    assert "score_file" not in listed["draft_analysis"]["inputSchema"]["properties"]
    assert card["_meta"]["ui"]["domain"].endswith(".claudemcpcontent.com")
    assert not drafted.get("isError") and drafted["content"][0]["text"].startswith(f"score_id: {score_id}")


def test_health_still_answers(server):
    assert urllib.request.urlopen(f"{server}/health", timeout=5).read() == b"ok"
