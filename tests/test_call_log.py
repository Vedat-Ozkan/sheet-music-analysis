import ast
import asyncio
import anyio
import json
from datetime import datetime, timezone
from pathlib import Path

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
            await client.call_tool("play", {"score_id": "NOPE00"}, meta=meta)

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
            return await client.call_tool("play", {"score_id": "ABC123"})

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


class StoreRaisingValueError:
    def get(self, key):
        raise ValueError("internal detail")


@pytest.mark.parametrize("tool, arguments", [
    ("render_analysis", {"score_id": "ABC123", "annotations": {"annotations": []}}),
    ("draft_analysis", {"score_id": "ABC123"}),
    ("play", {"score_id": "ABC123"}),
    ("correct_bars", {"score_id": "ABC123", "replacement_bars": "N1 div=24 ts=4/4 ks=0"}),
])
def test_a_stray_value_error_inside_a_tool_is_a_server_error_with_the_generic_message(tool, arguments, monkeypatch, capsys):
    monkeypatch.setattr(app, "store", StoreRaisingValueError())

    async def call():
        async with Client(app.mcp) as client:
            return await client.call_tool(tool, arguments)

    result = asyncio.run(call())
    line = json.loads([line for line in capsys.readouterr().out.splitlines() if f'"tool": "{tool}"' in line][-1])
    assert line["outcome"] == "server_error" and "internal detail" in line["stack_trace"]
    text = result.content[0].text
    assert line["reference"] in text and "support@sheetmusicanalysis.com" in text and "internal detail" not in text


def test_a_message_written_for_the_user_still_reaches_them_as_a_user_error(local_store, capsys):
    score = (Path(__file__).parent / "data" / "part_writing_bwv64.4.musicxml").read_bytes()
    app.store.put("scores/CHORALE", score)

    async def call(tool, arguments):
        async with Client(app.mcp) as client:
            return await client.call_tool(tool, arguments)

    drawn = asyncio.run(call("render_analysis", {"score_id": "CHORALE", "annotations": {"annotations": []}, "view": "nonsense"}))
    drafted = asyncio.run(call("draft_analysis", {"score_id": "CHORALE", "student_analysis": "m1 b0 I"}))
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")]
    assert drawn.is_error and drawn.content[0].text.startswith("view must be one of")
    assert drafted.is_error and drafted.content[0].text == "Beat must be at least 1 in bar 1"
    assert [line["outcome"] for line in lines if line.get("tool") in ("render_analysis", "draft_analysis")] == ["user_error"] * 2


ALLOWED_VALUE_ERROR_CATCHES = {"is_public_https", "link_host", "fetch_score"}


def test_only_link_parsing_catches_a_bare_value_error_in_the_server():
    tree = ast.parse((Path(app.__file__)).read_text())
    catching = set()
    for function in ast.walk(tree):
        if isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for handler in ast.walk(function):
                if isinstance(handler, ast.ExceptHandler) and handler.type is not None and any(
                        isinstance(name, ast.Name) and name.id == "ValueError" for name in ast.walk(handler.type)):
                    catching.add(function.name)
    assert catching == ALLOWED_VALUE_ERROR_CATCHES
