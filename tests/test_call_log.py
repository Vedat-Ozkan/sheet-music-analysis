import asyncio
import anyio
import json
from datetime import datetime, timezone

import pytest
from mcp.client.client import Client

from server import app


@pytest.fixture
def local_store(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "store", app.LocalStore(tmp_path))
    monkeypatch.setattr(app, "pseudonym_key", None)
    monkeypatch.setattr(app, "months_recorded", set())


def logged_call(capsys, meta: dict | None) -> dict:
    async def call():
        async with Client(app.mcp) as client:
            await client.call_tool("play", {"play_id": "NOPE00"}, meta=meta)

    asyncio.run(call())
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")]
    return next(line for line in reversed(lines) if line.get("tool") == "play")


def chatgpt(subject: str) -> dict:
    return {"openai/subject": subject, "openai/locale": "pl-PL"}


def on_date(monkeypatch, month: int, day: int) -> None:
    class Date(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, month, day, 12, tzinfo=timezone.utc)

    monkeypatch.setattr(app, "datetime", Date)


def test_a_call_logs_field_names_and_a_hashed_user_but_no_values(local_store, capsys):
    line = logged_call(capsys, chatgpt("user-123"))
    assert {"openai/locale", "openai/subject"} <= set(line["meta_keys"])
    assert len(line["user"]) == 16
    assert "user-123" not in json.dumps(line) and "pl-PL" not in json.dumps(line)


def test_the_same_user_keeps_one_code_and_each_active_month_is_recorded(local_store, tmp_path, capsys, monkeypatch):
    on_date(monkeypatch, 11, 1)
    first, again, other = (logged_call(capsys, chatgpt(subject))["user"] for subject in ("user-123", "user-123", "user-456"))
    on_date(monkeypatch, 12, 3)
    next_month = logged_call(capsys, chatgpt("user-123"))["user"]
    assert first == again == next_month and first != other
    assert sorted(path.name for path in (tmp_path / "users" / first).iterdir()) == ["2026-11", "2026-12"]
    assert [path.name for path in (tmp_path / "users" / other).iterdir()] == ["2026-11"]


def test_a_call_without_a_subject_logs_no_user(local_store, capsys):
    assert "user" not in logged_call(capsys, None)


def test_a_failure_on_our_side_apologises_and_gives_the_support_email(monkeypatch, capsys):
    class BrokenStore:
        def get(self, key):
            raise OSError("bucket unreachable")

    monkeypatch.setattr(app, "store", BrokenStore())

    async def call():
        async with Client(app.mcp) as client:
            return await client.call_tool("play", {"play_id": "ABC123"})

    result = asyncio.run(call())
    line = json.loads([line for line in capsys.readouterr().out.splitlines() if '"tool": "play"' in line][-1])
    assert result.is_error and line["outcome"] == "server_error" and "bucket unreachable" in line["stack_trace"]
    text = result.content[0].text
    assert "support@sheetmusicanalysis.com" in text and line["reference"] in text and "bucket" not in text


def test_a_count_made_by_another_machine_between_read_and_write_is_kept(monkeypatch, tmp_path):
    store = app.LocalStore(tmp_path)
    monkeypatch.setattr(app, "store", store)
    read = store.get_versioned
    interfered = []

    def other_machine_counts_in_between(key):
        found = read(key)
        if not interfered:
            interfered.append(True)
            store.put(key, json.dumps({"render": 5, "render:chatgpt": 5}).encode())
        return found

    monkeypatch.setattr(store, "get_versioned", other_machine_counts_in_between)
    assert anyio.run(app.take, "render", "claude")
    day = app.datetime.now(app.timezone.utc).strftime("%Y-%m-%d")
    counts = json.loads(store.get(f"usage/{day}.json"))
    assert counts["render"] == 6 and counts["render:chatgpt"] == 5 and counts["render:claude"] == 1
