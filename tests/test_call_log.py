import asyncio
import json
from datetime import datetime, timezone

import pytest
from mcp.client.client import Client

from server import app


@pytest.fixture
def local_store(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "store", app.LocalStore(tmp_path))
    monkeypatch.setattr(app, "day_keys", {})


def logged_call(capsys, meta: dict | None) -> dict:
    async def call():
        async with Client(app.mcp) as client:
            await client.call_tool("play", {"play_id": "NOPE00"}, meta=meta)

    asyncio.run(call())
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")]
    return next(line for line in reversed(lines) if line.get("tool") == "play")


def chatgpt(subject: str) -> dict:
    return {"openai/subject": subject, "openai/locale": "pl-PL"}


def on_day(monkeypatch, day: int) -> None:
    class Day(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, day, 12, tzinfo=timezone.utc)

    monkeypatch.setattr(app, "datetime", Day)


def test_a_call_logs_field_names_and_a_hashed_user_but_no_values(local_store, capsys):
    line = logged_call(capsys, chatgpt("user-123"))
    assert {"openai/locale", "openai/subject"} <= set(line["meta_keys"])
    assert len(line["user"]) == 16
    assert "user-123" not in json.dumps(line) and "pl-PL" not in json.dumps(line)


def test_the_same_user_matches_within_a_day_but_not_across_days(local_store, capsys, monkeypatch):
    on_day(monkeypatch, 1)
    first, again, other = (logged_call(capsys, chatgpt(subject))["user"] for subject in ("user-123", "user-123", "user-456"))
    on_day(monkeypatch, 2)
    next_day = logged_call(capsys, chatgpt("user-123"))["user"]
    assert first == again and first != other and first != next_day


def test_a_call_without_a_subject_logs_no_user(local_store, capsys):
    assert "user" not in logged_call(capsys, None)
