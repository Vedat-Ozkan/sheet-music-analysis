import asyncio
from pathlib import Path

import pytest

from server import app

ROOT = Path(__file__).parent.parent
CHOPIN = ROOT / "tests/data/chopin_nocturne_op9_no2.mxl"
LABELLED = ROOT / "tests/data/check_analysis/musescore-roman.musicxml"
QUESTION = "Which bar and beat does each numeral belong to?"
STUDENT = (
    "key: Eb major; m1 I53 beat 3 I6; m2 V7/ii beat 3 ii; m3 V7 V65 vi viio7/V; m4 V7 beat 3 I; "
    "m5 I beat 3 I; m6 V7/ii beat 3 ii; m7 V7 V65/vi vi viio7/V; m8 V7 beat 3 I"
)


@pytest.fixture
def local_store(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "store", app.LocalStore(tmp_path))
    app.store.put("scores/CHOPIN", CHOPIN.read_bytes())
    app.store.put("scores/LABELLED", LABELLED.read_bytes())


def call(tool, **arguments):
    return asyncio.run(tool(None, **arguments))


def section_of(text):
    return text.split("STUDENT CHECK (", 1)[1].split("## Method", 1)[0]


def rows_of(section):
    return {line.split(" | ")[0]: line.split(" | ") for line in section.splitlines() if line.startswith("m")}


def test_each_typed_label_is_tested_against_the_notes_of_its_beat(local_store):
    result = call(app.draft_analysis, score_id="CHOPIN", measure_range="1-8", student_analysis=STUDENT)
    assert not result.is_error
    rows = rows_of(section_of(result.content[0].text))
    assert rows["m1 b1"] == ["m1 b1", "Eb: I53", "Eb2", "Eb G Bb", "Eb G Bb", "-", "-", "fits"]
    assert rows["m1 b3"][1:4] == ["Eb: I6", "Eb2", "Eb G Bb F"]
    assert rows["m1 b3"][4] == "G Bb Eb" and rows["m1 b3"][-1] == "right chord, different inversion"
    assert rows["m3 b2"][1:4] == ["Eb: V65", "B2", "B G D F"] and rows["m3 b2"][-1] == "doesn't fit the notes"
    assert rows["m7 b2"][1] == "Eb: V65/vi" and rows["m7 b2"][-1] == "fits"
    assert rows["m3 b2"][5:7] == ["Ab Bb", "B G"]


def test_the_check_tells_the_chat_model_how_to_answer(local_store):
    text = call(app.draft_analysis, score_id="CHOPIN", measure_range="1-8", student_analysis=STUDENT).content[0].text
    section = section_of(text)
    assert "second reader" in section and "Start with what the student got right" in section
    assert "both readings are defensible" in section and "the bass" in section
    assert "draft" not in section.lower() and "model" not in section.lower()
    assert "If there is a STUDENT CHECK section" in text.split("HOW TO ANALYSE", 1)[1]


def test_draft_analysis_without_answer_has_no_section(local_store):
    assert "STUDENT CHECK (" not in call(app.draft_analysis, score_id="CHOPIN", measure_range="1-8").content[0].text


def test_numerals_written_in_the_score_are_read_only_when_asked(local_store):
    asked = call(app.draft_analysis, score_id="LABELLED", student_analysis="score").content[0].text
    assert rows_of(section_of(asked))["m2 b1"][1:3] == ["G: V6", "G4"]
    assert "STUDENT CHECK (" not in call(app.draft_analysis, score_id="LABELLED").content[0].text


def test_ambiguous_answer_comes_back_as_the_question(local_store):
    result = call(app.draft_analysis, score_id="CHOPIN", student_analysis="I IV V I")
    assert result.is_error and result.content[0].text == app.QUESTION_FOR_USER + QUESTION
