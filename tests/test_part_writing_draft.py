import asyncio
import copy
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from engine import part_writing
from engine.render import load_toolkit
from engine.score import ScoreIndex
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
    assert "A PART-WRITING CHECK section (chorale-style scores only) is an offer for the user" in text.split("HOW THE NOTES ARE USED", 1)[1]


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


def test_a_symphony_is_turned_away_from_the_check_at_once():
    index = ScoreIndex(load_toolkit((DATA / "piano" / "mozart-41.mxl").read_bytes()).getMEI())
    started = time.perf_counter()
    assert part_writing.as_text(index, None, 1, 8) == ""
    assert time.perf_counter() - started < 0.5


def tiled(path, times):
    root = ET.fromstring(path.read_bytes())
    for part in root.iter("part"):
        bars = part.findall("measure")
        for bar in bars:
            part.remove(bar)
        for copy_number in range(times):
            for bar in bars:
                bar = copy.deepcopy(bar)
                if copy_number:
                    for heading in bar.findall("attributes") + bar.findall("print"):
                        bar.remove(heading)
                part.append(bar)
        for number, bar in enumerate(part.findall("measure"), 1):
            bar.set("number", str(number))
    return ScoreIndex(load_toolkit(ET.tostring(root)).getMEI())


def test_a_long_chorale_costs_what_the_asked_bars_cost():
    chorale = DATA / "part_writing_bwv245.40.musicxml"
    short, long = tiled(chorale, 1), tiled(chorale, 16)
    started = time.perf_counter()
    section = part_writing.as_text(long, None, 1, 8)
    assert time.perf_counter() - started < 1.5
    assert section == part_writing.as_text(short, None, 1, 8)
