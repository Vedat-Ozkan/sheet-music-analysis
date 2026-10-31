import asyncio
import json
from pathlib import Path

import pytest
from mcp.client.client import Client

from server import app

CHOPIN = Path(__file__).parent / "data/chopin_nocturne_op9_no2.mxl"


@pytest.fixture
def chopin(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "store", app.LocalStore(tmp_path))
    monkeypatch.setattr(app, "day_keys", {})
    monkeypatch.setattr(app, "publish", lambda data, *kind: "https://example.com/file")
    app.store.put("scores/ABC", CHOPIN.read_bytes())


def renders(chats: list[str]) -> list[bool]:
    async def call():
        async with Client(app.mcp) as client:
            results = [await client.call_tool("render_analysis", {"score_id": "ABC", "measure_range": "1-1", "annotations": {"annotations": []}},
                                              meta={"openai/session": chat}) for chat in chats]
        return [bool(result.meta and result.meta.get("ask_for_rating")) for result in results]

    return asyncio.run(call())


def test_a_chat_is_asked_for_a_rating_once_at_its_third_analysis(chopin):
    assert renders(["chat-1", "chat-1", "chat-2", "chat-1", "chat-1"]) == [False, False, False, True, False]


def test_a_rating_is_logged_and_the_tool_is_only_for_the_card(capsys):
    async def call():
        async with Client(app.mcp) as client:
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}
            await client.call_tool("rate_analysis", {"helpful": False})
        return tools["rate_analysis"]

    tool = asyncio.run(call())
    assert tool.meta["ui"]["visibility"] == ["app"]
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")]
    assert any(line.get("event") == "rate_analysis" and line.get("helpful") is False for line in lines)
