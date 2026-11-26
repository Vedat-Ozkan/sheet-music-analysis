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


def test_a_score_id_plays_the_bars_asked_for(local_store):
    app.store.put("scores/CHOPIN", CHOPIN.read_bytes())
    result = call(app.play, score_id="CHOPIN", measure_range="1-8")
    assert not result.is_error
    assert result.structured_content == {"performance": performance_text(marked_index(CHOPIN.read_bytes()), (1, 8)),
                                         "measures": [1, 8]}
    whole = call(app.play, score_id="CHOPIN", measure_range="all")
    index = marked_index(CHOPIN.read_bytes())
    assert whole.structured_content["measures"] == [index.measures[0].number, index.measures[-1].number]


def test_an_unknown_score_id_says_scores_are_kept_for_30_days(local_store):
    result = call(app.play, score_id="NOPE00")
    assert result.is_error and "scores are kept for 30 days" in result.content[0].text


def test_only_claude_is_offered_the_player_and_the_old_plugins_note_list_tool():
    assert {"play", "draft_from_notes"} <= listed_for("Claude-User")
    assert not {"play", "draft_from_notes"} & listed_for("openai-mcp/1.0.0")


def test_an_old_plugins_note_list_gets_no_draft_and_a_play_id_for_the_same_passage(local_store):
    sent = note_list.encode(marked_index(CHOPIN.read_bytes()), 1, 8)
    result = call(app.draft_from_notes, notes=sent, student_analysis="m1 I, m2 V7/ii")
    text = result.content[0].text
    assert not result.is_error and text.startswith(app.NOTES_FROM_LIST)
    assert "| Eb: I |" in text and "| Eb: V7/ii |" in text
    played = call(app.play, play_id=text.split("play_id ")[1].split()[0])
    decoded = note_list.decode(sent)
    assert played.structured_content == {"performance": performance_text(decoded),
                                         "measures": [decoded.measures[0].number, decoded.measures[-1].number]}


def test_a_chorale_note_list_gets_the_part_writing_and_student_checks(local_store):
    chorale = Path(__file__).parent / "data/part_writing_bwv303.musicxml"
    sent = note_list.encode(marked_index(chorale.read_bytes()))
    text = call(app.draft_from_notes, notes=sent, student_analysis="m1 I, m2 V").content[0].text
    assert "PART-WRITING CHECK (" in text and "STUDENT CHECK (" in text and "| D: I |" in text


def test_a_numeral_the_note_list_has_no_beat_for_is_a_question_and_not_charged(local_store):
    sent = note_list.encode(marked_index(CHOPIN.read_bytes()), 1, 8)
    result = call(app.draft_from_notes, notes=sent, student_analysis="m1 b9 I")
    assert result.is_error and result.content[0].text.startswith(app.QUESTION_FOR_USER + "Bar 1 has 4 beats")
    assert app.store.get(f"usage/{app.today()}.json") is None
    assert not call(app.draft_from_notes, notes=sent, student_analysis="m1 b4 I").is_error
    assert app.store.get(f"usage/{app.today()}.json") is not None


def test_a_note_list_plays_without_a_draft(local_store):
    sent = note_list.encode(marked_index(CHOPIN.read_bytes()), 1, 8)
    result = call(app.play, notes=sent)
    assert result.structured_content["performance"].startswith("P1 v55 ")


def test_an_unknown_play_id_explains_what_to_pass(local_store):
    result = call(app.play, play_id="NOPE00")
    assert result.is_error and "they are kept for 30 days. draft_from_notes gives a new one, or the note list can be passed as notes" in result.content[0].text


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
    app.store.put("scores/LARGO", a_bar_marked("Largo", "2/2"))
    asked = call(app.play, score_id="LARGO")
    assert asked.structured_content is None and "'largo'" in asked.content[0].text
    played = call(app.play, score_id="LARGO", tempo=60)
    assert played.structured_content["performance"].split()[-1].split(".")[1] == "400"


def test_a_tempo_word_over_a_quarter_note_beat_plays_at_once(local_store):
    app.store.put("scores/LARGO", a_bar_marked("Largo", "4/4"))
    played = call(app.play, score_id="LARGO")
    assert played.structured_content["performance"].split()[-1].split(".")[1] == "480"


def bars_marked(words: list[str]) -> bytes:
    bars = "".join(
        f'<measure number="{number}">'
        + ('<attributes><divisions>1</divisions><key><fifths>0</fifths></key><time><beats>2</beats><beat-type>2</beat-type>'
           '</time><clef><sign>G</sign><line>2</line></clef></attributes>' if number == 1 else "")
        + (f'<direction placement="above"><direction-type><words>{word}</words></direction-type></direction>' if word else "")
        + '<note><pitch><step>C</step><octave>5</octave></pitch><duration>4</duration><type>whole</type></note></measure>'
        for number, word in enumerate(words, 1))
    return f"""<?xml version="1.0"?>
<score-partwise version="4.0"><part-list><score-part id="P1"><part-name>Piano</part-name></score-part></part-list>
<part id="P1">{bars}</part></score-partwise>""".encode()


def test_only_the_tempo_word_in_force_over_the_bars_played_is_asked_about(local_store):
    app.store.put("scores/MARKED", bars_marked(["Largo", "", "Allegro"]))
    assert "Question for the user: bar 1 is marked 'largo'" in call(app.play, score_id="MARKED", measure_range="2-2").content[0].text
    assert "Question for the user: bar 3 is marked 'allegro'" in call(app.play, score_id="MARKED", measure_range="3-3").content[0].text


@pytest.mark.parametrize("written", ["Cx4", "Ck4", "C-4", "D#b4", "C###4", "C10"])
def test_a_pitch_the_note_list_cannot_hold_is_refused_by_name(local_store, written):
    sent = f"N1 div=1 ts=4/4 ks=0\nm1 len=4\n1.1: 2 C4 {written}"
    for tool in (app.draft_from_notes, app.play):
        result = call(tool, notes=sent)
        assert result.is_error and f"Bar 1: '{written}' is not a note this list can hold" in result.content[0].text
    app.store.put("scores/CHOPIN", CHOPIN.read_bytes())
    corrected = asyncio.run(app.mcp.call_tool("correct_bars", {"score_id": "CHOPIN", "replacement_bars": sent}))
    assert corrected.is_error and f"Bar 1: '{written}' is not a note this list can hold" in corrected.content[0].text
