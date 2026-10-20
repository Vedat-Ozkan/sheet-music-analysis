import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest

from engine import notes as note_list
from engine.render import load_toolkit
from engine.score import ScoreIndex
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
    return text.split("STUDENT CHECK", 1)[1].split("HOW TO USE", 1)[0]


def assert_planted_differences(section):
    rows = {line.split(" | ")[0]: line for line in section.splitlines() if line.startswith("m")}
    assert rows["m1 b1"].endswith("same chord different spelling")
    assert rows["m1 b3"].endswith("different inversion")
    assert rows["m3 b2"].endswith("different chord") and "V65/vi" in rows["m3 b2"]
    assert rows["m2 b1"].endswith("agrees") and rows["m7 b2"].endswith("agrees")
    assert "second reader" in section and "both readings are defensible" in section


def test_draft_analysis_checks_typed_answer(local_store):
    result = call(app.draft_analysis, score_id="CHOPIN", measure_range="1-8", student_analysis=STUDENT)
    assert not result.is_error
    text = result.content[0].text
    assert_planted_differences(section_of(text))
    assert "If the draft has a STUDENT CHECK section" in text.split("HOW TO USE", 1)[1]


def test_draft_analysis_without_answer_has_no_section(local_store):
    assert "STUDENT CHECK (" not in call(app.draft_analysis, score_id="CHOPIN", measure_range="1-8").content[0].text


def test_numerals_written_in_the_score_are_read_only_when_asked(local_store):
    asked = call(app.draft_analysis, score_id="LABELLED", student_analysis="score").content[0].text
    assert "m2 b1 | G: V6 |" in section_of(asked)
    assert "STUDENT CHECK (" not in call(app.draft_analysis, score_id="LABELLED").content[0].text


def test_ambiguous_answer_comes_back_as_the_question(local_store):
    result = call(app.draft_analysis, score_id="CHOPIN", student_analysis="I IV V I")
    assert result.is_error and result.content[0].text == QUESTION


def test_draft_from_notes_checks_typed_answer(local_store):
    index = ScoreIndex(load_toolkit(CHOPIN.read_bytes()).getMEI())
    result = call(app.draft_from_notes, notes=note_list.encode(index, 1, 8), student_analysis=STUDENT)
    assert not result.is_error
    assert_planted_differences(section_of(result.content[0].text))


def test_draft_from_notes_ambiguous_answer(local_store):
    index = ScoreIndex(load_toolkit(CHOPIN.read_bytes()).getMEI())
    result = call(app.draft_from_notes, notes=note_list.encode(index, 1, 8), student_analysis="I IV V I")
    assert result.is_error and result.content[0].text == QUESTION


def run_script(*arguments):
    return subprocess.run(
        [sys.executable, str(ROOT / "skill/scripts/model_notes.py"), *arguments],
        capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(ROOT)},
    )


def test_skill_script_hands_the_answer_to_the_tool(local_store):
    ran = run_script(str(CHOPIN), "--measures", "1-8", "--student-analysis", STUDENT)
    assert ran.returncode == 0, ran.stderr
    typed = ran.stderr.split("student_analysis: ", 1)[1].strip()
    result = call(app.draft_from_notes, notes=ran.stdout, student_analysis=typed)
    assert_planted_differences(section_of(result.content[0].text))


def test_skill_script_reads_numerals_written_in_the_file():
    ran = run_script(str(LABELLED), "--student-analysis", "score")
    assert ran.returncode == 0, ran.stderr
    assert "m2 b1 G: V6" in ran.stderr


def test_skill_script_asks_the_question():
    ran = run_script(str(CHOPIN), "--student-analysis", "I IV V I")
    assert ran.returncode == 1 and f"Ask the user: {QUESTION}" in ran.stderr
    assert ran.stdout == ""
