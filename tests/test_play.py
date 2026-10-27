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


def a_bar_marked(word: str, time: str) -> bytes:
    beats, unit = time.split("/")
    return f"""<?xml version="1.0"?>
<score-partwise version="4.0"><part-list><score-part id="P1"><part-name>Piano</part-name></score-part></part-list>
<part id="P1"><measure number="1"><attributes><divisions>1</divisions><key><fifths>0</fifths></key>
<time><beats>{beats}</beats><beat-type>{unit}</beat-type></time><clef><sign>G</sign><line>2</line></clef></attributes>
<direction placement="above"><direction-type><words>{word}</words></direction-type></direction>
<note><pitch><step>C</step><octave>5</octave></pitch><duration>4</duration><type>whole</type></note></measure></part>
</score-partwise>""".encode()


def test_a_tempo_word_over_a_half_note_beat_asks_for_a_speed_first(local_store):
    sent = note_list.encode(marked_index(a_bar_marked("Largo", "2/2")), 1, 1)
    asked = call(app.play, notes=sent)
    assert asked.structured_content is None and "'largo'" in asked.content[0].text
    played = call(app.play, notes=sent, tempo=60)
    assert played.structured_content["performance"].split()[-1].split(".")[1] == "400"


def test_a_tempo_word_over_a_quarter_note_beat_plays_at_once(local_store):
    sent = note_list.encode(marked_index(a_bar_marked("Largo", "4/4")), 1, 1)
    played = call(app.play, notes=sent)
    assert played.structured_content["performance"].split()[-1].split(".")[1] == "480"
