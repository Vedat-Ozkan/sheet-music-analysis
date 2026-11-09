import asyncio
import re
from pathlib import Path

import pytest

from server import app

DATA = Path(__file__).parent / "data"


@pytest.fixture
def local_store(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "store", app.LocalStore(tmp_path))


def section_of(text):
    return text.split("PART-WRITING CHECK (", 1)[1].split("## Method", 1)[0]


def test_draft_analysis_lists_planted_motion_errors(local_store):
    text = app.make_draft((DATA / "part_writing_motion.musicxml").read_bytes(), "pw1", None)
    section = section_of(text)
    assert "parallel fifths soprano+tenor m1 b1 to m2 b1" in section
    assert "voice crossing soprano+alto m13 b1" in section
    assert '(Open Music Theory)' in section
    assert '{"measure":13,"beat":1.0,"staff":2,"pitch":"G4"}' in section
    labels = re.findall(r'label "([^"]*)"', section)
    assert "P5" in labels and not any("," in word for word in labels)
    assert "one sentence offering to check the voice leading" in text.split("HOW TO ANALYSE", 1)[1]


def test_draft_analysis_lists_planted_tendency_errors(local_store):
    text = app.make_draft((DATA / "part_writing_tendency.musicxml").read_bytes(), "pw2", None)
    assert "unresolved seventh" in section_of(text)


def test_piano_piece_gets_no_section(local_store, chopin):
    assert "PART-WRITING CHECK (" not in app.make_draft(chopin, "pw3", (1, 8))


def test_section_keeps_only_findings_inside_the_requested_bars(local_store):
    section = section_of(app.make_draft((DATA / "part_writing_motion.musicxml").read_bytes(), "pw4", (10, 14)))
    assert "voice crossing soprano+alto m13 b1" in section
    assert "m1 b1 to m2 b1" not in section


def test_a_chorale_sent_to_the_tool_gets_its_check(local_store):
    app.store.put("scores/PW", (DATA / "part_writing_motion.musicxml").read_bytes())
    text = asyncio.run(app.draft_analysis(None, score_id="PW")).content[0].text
    assert "parallel fifths soprano+tenor m1 b1 to m2 b1" in section_of(text)
