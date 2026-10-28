import re

import pytest

from engine import draft, part_writing
from engine import notes as note_list
from engine.render import load_toolkit
from engine.score import ScoreIndex
from server import app

from pathlib import Path

DATA = Path(__file__).parent / "data"


@pytest.fixture
def local_store(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "store", app.LocalStore(tmp_path))


def test_draft_analysis_lists_planted_motion_errors(local_store):
    text = app.make_draft((DATA / "part_writing_motion.musicxml").read_bytes(), "pw1", None)
    section = text.split("PART-WRITING CHECK", 1)[1].split("HOW TO USE", 1)[0]
    assert "parallel fifths soprano+tenor m1 b1 to m2 b1" in section
    assert "voice crossing soprano+alto m13 b1" in section
    assert '(Open Music Theory)' in section
    assert '{"measure":13,"beat":1.0,"staff":2,"pitch":"G4"}' in section
    labels = re.findall(r'label "([^"]*)"', section)
    assert "P5" in labels and not any("," in word for word in labels)
    assert "one sentence offering to check the voice leading" in text.split("HOW TO USE", 1)[1]


def test_draft_analysis_lists_planted_tendency_errors(local_store):
    text = app.make_draft((DATA / "part_writing_tendency.musicxml").read_bytes(), "pw2", None)
    assert "unresolved seventh" in text.split("PART-WRITING CHECK", 1)[1]


def test_note_list_path_gets_the_same_section():
    index = ScoreIndex(load_toolkit((DATA / "part_writing_motion.musicxml").read_bytes()).getMEI())
    text = note_list.encode(index)
    result = draft.draft_from_notes(text)
    section = part_writing.as_text(note_list.decode(text), result.chords)
    assert "parallel fifths soprano+tenor m1 b1 to m2 b1" in section


def test_piano_piece_gets_no_section(local_store, chopin):
    assert "PART-WRITING CHECK (" not in app.make_draft(chopin, "pw3", (1, 8))


def test_section_keeps_only_findings_inside_the_requested_bars(local_store):
    text = app.make_draft((DATA / "part_writing_motion.musicxml").read_bytes(), "pw4", (10, 14))
    section = text.split("PART-WRITING CHECK", 1)[1].split("HOW TO USE", 1)[0]
    assert "voice crossing soprano+alto m13 b1" in section
    assert "m1 b1 to m2 b1" not in section
