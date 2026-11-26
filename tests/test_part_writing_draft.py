import asyncio
import copy
import re
import cProfile
import pstats
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


def calls(make, name, module):
    profile = cProfile.Profile()
    profile.enable()
    make()
    profile.disable()
    return sum(stats[1] for where, stats in pstats.Stats(profile).stats.items()
               if where[2] == name and where[0].endswith(module))


def test_a_symphony_is_turned_away_before_the_part_writing_table_is_built(local_store):
    symphony = (DATA / "piano" / "mozart-41.mxl").read_bytes()
    assert calls(lambda: app.make_draft(symphony, "SYM", ("1", "8")), "_table", "part_writing.py") == 0


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
    return ET.tostring(root)


def test_a_long_chorale_does_the_key_work_of_the_asked_bars_only(local_store):
    chorale = DATA / "part_writing_bwv245.40.musicxml"
    short, long = tiled(chorale, 1), tiled(chorale, 16)

    def key_estimates(score):
        return calls(lambda: app.make_draft(score, "LONG", ("1", "8")), "analyze", "stream/base.py")

    assert key_estimates(long) == key_estimates(short)
    assert section_of(app.make_draft(long, "LONG", ("1", "8"))) == section_of(app.make_draft(short, "SHORT", ("1", "8")))


def finding_lines(index, findings):
    voices = sorted({(e.staff, e.layer) for m in index.measures for e in m.events if e.pitch and not e.grace})
    names = dict(zip(voices, ("soprano", "alto", "tenor", "bass")))
    return {f"{f.rule.replace('_', ' ')} {'+'.join(names[v] for v in f.voices)} "
            + " to ".join(f"m{index.name_of(bar)} b{beat:g}" for bar, beat in zip(f.bars, f.beats)) + f": {f.why}"
            for f in findings}


@pytest.mark.parametrize("name,first,last", [("bwv418", 0, 2), ("bwv418", 3, 7), ("bwv418", 8, 12), ("bwv418", 14, 16),
                                             ("bwv245.40", 1, 5), ("bwv245.40", 10, 13), ("bwv245.40", 22, 24),
                                             ("bwv245.40", 26, 28)])
def test_the_check_of_some_bars_finds_what_the_whole_piece_check_finds_there(name, first, last):
    index = ScoreIndex(load_toolkit((DATA / f"part_writing_{name}.musicxml").read_bytes()).getMEI())
    chosen = {m.number for m in index.select(first, last, include_pickup=False)}
    whole = [f for f in part_writing.check(index) if all(bar in chosen for bar in f.bars)]
    shown = finding_lines(index, whole) & listed(part_writing.as_text(index))
    assert shown and listed(part_writing.as_text(index, None, first, last)) == shown


def listed(section):
    return {line.strip() for line in section.splitlines() if line.startswith("   ") and not line.startswith("   draw")}
