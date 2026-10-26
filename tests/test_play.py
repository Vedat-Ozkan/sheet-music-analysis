import asyncio
from pathlib import Path

import pytest

from engine import notes as note_list
from engine.performance import marked_index, performance_text
from server import app

CHOPIN = Path(__file__).parent / "data/chopin_nocturne_op9_no2.mxl"


def call(tool, **arguments):
    return asyncio.run(tool(None, **arguments))


def listed_for(agent):
    class Request:
        headers = {"user-agent": agent}

    class Context:
        request = Request()

    return {tool.name for tool in asyncio.run(app.mcp._handle_list_tools(Context(), None)).tools}


@pytest.fixture
def local_store(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "store", app.LocalStore(tmp_path))


def test_a_draft_hands_back_a_play_id_for_the_same_passage(local_store):
    sent = note_list.encode(marked_index(CHOPIN.read_bytes()), 1, 8)
    drafted = call(app.draft_from_notes, notes=sent).content[0].text
    play_id = drafted.split("play_id ")[1].split()[0]
    result = call(app.play, play_id=play_id)
    assert not result.is_error
    assert result.structured_content == {"performance": performance_text(note_list.decode(sent))}


def test_a_note_list_plays_without_a_draft(local_store):
    sent = note_list.encode(marked_index(CHOPIN.read_bytes()), 1, 8)
    result = call(app.play, notes=sent)
    assert result.structured_content["performance"].startswith("P1 v55 ")


def test_an_unknown_play_id_explains_what_to_pass(local_store):
    result = call(app.play, play_id="NOPE00")
    assert result.is_error and "play_id that draft_from_notes returned" in result.content[0].text


def test_only_claude_is_offered_the_player():
    assert listed_for("Claude-User") == {"draft_from_notes", "play"}
    assert "play" not in listed_for("openai-mcp/1.0.0")
