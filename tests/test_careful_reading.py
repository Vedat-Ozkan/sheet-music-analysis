import asyncio
import copy
import hashlib
import io
import itertools
import json
import os
import random
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from fractions import Fraction
from pathlib import Path

import pytest

from engine import correct, from_notes, notes
from engine import read_pdf as pdf_reader
from engine.render import load_toolkit
from engine.score import ScoreIndex
from kit import note_rules
from music21.common import opFrac
from music21.duration import quarterConversion
from server import app
from tests.test_chord_symbols import LEAD_SHEET, PRINTED, printed_symbols

DATA = Path(__file__).parent / "data"
RULES = DATA / "careful/rules"
PAGES = [(DATA / f"careful/dvorak-silhouette-1-page{number}.n1").read_text() for number in (1, 2, 3)]
QUICK_READING = DATA / "chopin_prelude_op28_no4_reading.musicxml"
LEAD_SHEET_PAGE = (DATA / "chord_symbols/amazing-grace-lead-sheet-page.n1").read_text()
SIGNS_DISAGREE_WITH_PITCHES = {
    "grieg-op38-7-scan-reading-verovio-crashed-chord.musicxml",
    "choral-songs-02-invalid-page-1.mxl",
    "choral-songs-02-invalid-page-3.mxl",
    "schubert_die_stadt_audiveris.musicxml",
    "ravel-oiseaux-tristes-scan-verovio-crashed-beam-setting0.mxl",
    "mozart-k545-1-homr-reading-clef-change.musicxml",
}


@pytest.fixture(autouse=True)
def careful_reading_on(monkeypatch):
    monkeypatch.setattr(app, "CAREFUL_PLATFORMS", {"other"})


def paged_file(path):
    if (text := path.read_text()).startswith("N1 page="):
        return text
    found = re.search(r"page(\d+)$", path.stem)
    return text.replace("N1 ", f"N1 page={found[1] if found else 1} ", 1)


def text_of(result):
    return next(item.text for item in result.content if item.type == "text")


def notes_of(bar):
    return [note for note in bar.findall("note") if note.find("pitch") is not None]


def test_a_scan_is_offered_a_careful_reading_and_the_pages_become_a_score(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "store", app.LocalStore(tmp_path))
    app.store.put("scores/QUICK1", QUICK_READING.read_bytes())
    card = {"score_id": "QUICK1", "pages": 3, "scan": True, "measures": "1 to 25", "bars": 25, "notice": "",
            "image_url": "", "pdf_url": "", "page_images": []}
    reading, typeset, ordinary, elsewhere = (text_of(app.pdf_card_result(given, "read_pdf", source, route)) for given, source, route in (
        (card, "other", None), ({**card, "scan": False}, "other", None), (card, "other", "ordinary"), (card, "claude", None)))
    assert reading == typeset == elsewhere
    assert "careful" not in reading and reading.endswith("\nscore_id QUICK1 is ready for draft_analysis.")
    assert ('Note for the user: "This was the quick reading of your PDF, which makes more mistakes, and not all of them are '
            'shaded. The careful reading is more accurate: the chat reads each page itself. A careful reading of this piece\'s 3 '
            'pages is slower than the quick one, uses your own plan\'s usage, and runs a small measuring script from Sheet Music '
            'Analysis in this chat. To start it, type @Sheet Music Analysis, choose the app from the list, and ask for the '
            'careful reading."') in ordinary and ordinary.endswith("\nscore_id QUICK1 is ready for draft_analysis.")
    assert "it needs no check by the user first" in reading
    assert ("takes about 10 minutes with one helper per page on Sonnet at medium effort, uses a lot of your plan's usage "
            "allowance (as a guide, a 10-page piece") in app.careful_warning(3, "claude")

    refused = asyncio.run(app.mcp.call_tool("careful_reading", {"score_id": "QUICK1"}))
    assert refused.is_error
    app.store.put(app.reading_key("QUICK1"), json.dumps({"pages": 3}).encode())
    steps = text_of(asyncio.run(app.mcp.call_tool("careful_reading", {"score_id": "QUICK1"})))
    assert f"{app.PUBLIC_BASE_URL}/kit/$f" in steps and "kit/reader.md" in steps and "page N of 3" in steps
    assert "automatic reader" not in steps and "If they say no, the quick reading stays: score_id QUICK1 is ready" in steps

    result = asyncio.run(app.mcp.call_tool("use_careful_reading", {"score_id": "QUICK1", "pages": PAGES}))
    assert not result.is_error and "It holds" not in text_of(result)
    first_page_only = text_of(asyncio.run(app.mcp.call_tool("use_careful_reading", {"score_id": "QUICK1", "pages": PAGES[:1]})))
    assert "It holds page 1 of the PDF's 3 pages; a page left out is taken to have no music." in first_page_only
    assert ('Note for the user, if a page with music cannot be read: "This careful reading covers only page 1 of your '
            "PDF's 3 pages") in first_page_only
    code = text_of(result).split("score_id: ")[1].split()[0]
    score = app.store.get(f"scores/{code}")
    index = ScoreIndex(load_toolkit(score).getMEI())
    assert [measure.number for measure in index.measures] == list(range(54))
    assert [measure.name for measure in index.measures[:2]] == ["0", "1"] and index.measures[0].is_pickup
    assert [(measure.number, measure.key_signature) for measure in index.measures if measure.number in (0, 6, 48)] == [(0, "4s"), (6, "5f"), (48, "4s")]
    bars = ET.fromstring(score).find("part").findall("measure")
    printed_sharps = [(note.findtext("pitch/step"), note.findtext("accidental")) for note in notes_of(bars[4]) if note.find("accidental") is not None]
    assert printed_sharps == [("B", "sharp"), ("B", "sharp")]
    assert len(ET.fromstring(score).findall(".//slur[@type='start']")) == len(ET.fromstring(score).findall(".//slur[@type='stop']")) == 14
    assert len(ET.fromstring(score).findall(".//staccato")) == 7

    draft = asyncio.run(app.mcp.call_tool("draft_analysis", {"score_id": code}))
    assert not draft.is_error


def test_a_page_that_cannot_be_built_comes_back_with_what_to_fix(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "store", app.LocalStore(tmp_path))
    app.store.put(app.reading_key("QUICK1"), json.dumps({"pages": 3}).encode())
    broken = PAGES[0].replace("1.1: 2 (G#3+G#4", "1.1: 4 (G#3+G#4", 1)
    assert broken != PAGES[0]
    result = asyncio.run(app.mcp.call_tool("use_careful_reading", {"score_id": "QUICK1", "pages": [broken, *PAGES[1:]]}))
    assert result.is_error
    assert "Page 1: Bar 0, voice 1.1 adds up to 1" in text_of(result) and "a corrected hand-in takes every page again" in text_of(result)
    second = PAGES[1].replace("m1 len=24", "m1 len=20", 1)
    wrong_second = asyncio.run(app.mcp.call_tool("use_careful_reading", {"score_id": "QUICK1", "pages": [PAGES[0], second, PAGES[2]]}))
    assert wrong_second.is_error and "Page 2: Bar 1, voice 1.1 adds up to" in text_of(wrong_second)
    pickup_as_bar_1 = re.sub(r"^m(\d+)", lambda bar: f"m{int(bar[1]) + 1}", PAGES[0], flags=re.M)
    taken = asyncio.run(app.mcp.call_tool("use_careful_reading", {"score_id": "QUICK1", "pages": [pickup_as_bar_1]}))
    assert "measures 0 to 16." in text_of(taken)
    for pages, reason in (([], "No pages"), ([PAGES[0]] * 4, "This PDF has 3 pages"),
                          ([PAGES[0].replace("\n2.1: ", "\n40.1: ")], "Staves are numbered 1 to 32"),
                          ([PAGES[0].replace(" len=", " len=99999", 1)], "longer than 64 quarter notes")):
        refused = asyncio.run(app.mcp.call_tool("use_careful_reading", {"score_id": "QUICK1", "pages": pages}))
        assert refused.is_error and reason in text_of(refused), text_of(refused)
    voice_line = next(line for line in PAGES[1].splitlines() if line.startswith("1.1:"))
    entries = voice_line.split()
    first_note = next(position for position, entry in enumerate(entries) if position and not entry.isdigit())
    entries[first_note] = "(" + entries[first_note]
    unclosed = asyncio.run(app.mcp.call_tool("use_careful_reading", {"score_id": "QUICK1", "pages": [PAGES[1].replace(voice_line, " ".join(entries), 1)]}))
    assert unclosed.is_error and "never ends" in text_of(unclosed)


def test_a_hand_in_counts_as_a_draft_and_is_refused_at_the_daily_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "store", app.LocalStore(tmp_path))
    app.store.put(app.reading_key("QUICK1"), json.dumps({"pages": 3}).encode())
    assert not asyncio.run(app.mcp.call_tool("use_careful_reading", {"score_id": "QUICK1", "pages": PAGES})).is_error
    usage = next((tmp_path / "usage").glob("*.json"))
    assert json.loads(usage.read_text())["draft"] == 1
    usage.write_text(json.dumps({"draft": app.DAILY_LIMITS["draft"]}))
    refused = asyncio.run(app.mcp.call_tool("use_careful_reading", {"score_id": "QUICK1", "pages": PAGES}))
    assert refused.is_error and text_of(refused) == app.LIMIT_MESSAGE


def test_pages_with_different_units_join_into_one_numbered_score():
    joined = from_notes.join_pages(PAGES)
    assert joined.splitlines()[0] == "N1 div=8 ts=6/8 ks=4s"
    bars = [line for line in joined.splitlines() if line.startswith("m")]
    assert [line.split()[0] for line in bars] == [f"m{number}" for number in range(54)]
    assert [line for line in bars if "ks=" in line or "ts=" in line] == ["m6 len=24 ks=5f", "m48 len=4 ks=4s"]
    assert bars[17] == "m17 len=24"


def test_words_are_written_under_the_notes_they_are_sung_on():
    score = ET.fromstring(from_notes.score_from_notes((DATA / "careful/schubert-kraehe-voice-opening.n1").read_text()))
    sung = [(note.findtext("lyric/syllabic"), note.findtext("lyric/text")) for note in score.iter("note") if note.find("lyric") is not None]
    assert sung[-6:] == [("single", "Um"), ("single", "mein"), ("single", "Haupt"), ("begin", "ge"), ("middle", "flo"), ("end", "gen.")]
    words = [word for line in (DATA / "careful/schubert-kraehe-voice-opening.n1").read_text().splitlines() if line.startswith("1.1w:") for word in line.split()[1:] if word != "_"]
    assert len(sung) == len(words)


def test_words_in_two_voices_keep_their_own_hyphens():
    page = "N1 page=1 div=1 ts=2/4 ks=0\nm1 len=2\n1.1: 2 C5\n1.1w: Hal-\n2.1: 2 C3\n2.1w: la\nm2 len=2\n1.1: 2 D5\n1.1w: lo\n2.1: 2 D3\n2.1w: la"
    score = ET.fromstring(from_notes.score_from_notes(page))
    sung = {(note.findtext("staff"), note.findtext("lyric/text")): note.findtext("lyric/syllabic") for note in score.iter("note") if note.find("lyric") is not None}
    assert sung == {("1", "Hal"): "begin", ("1", "lo"): "end", ("2", "la"): "single"}


def test_a_later_page_without_a_time_signature_keeps_the_one_before():
    later = PAGES[1].replace("ts=6/8", "ts=", 1)
    assert later != PAGES[1]
    assert from_notes.join_pages([PAGES[0], later]) == from_notes.join_pages(PAGES[:2])


def clefs_in_bars(score):
    bars = []
    for bar in ET.fromstring(score).find("part").findall("measure"):
        elements = list(bar)
        first_notes = {}
        for position, element in enumerate(elements):
            if element.tag == "note":
                first_notes.setdefault(element.findtext("staff"), position)
        bars.append([(clef.get("number"), clef.findtext("sign"), position < first_notes[clef.get("number")])
                     for position, element in enumerate(elements) for clef in element.findall("clef")])
    return bars


@pytest.mark.parametrize("pages", [
    ["N1 page=1 div=4 ts=4/4 ks=0\nm1 len=16\n1.1: 16 C5\n2.1: clef=G 16 C4 clef=F\nm2 len=16\n1.1: 16 D5\n2.1: 16 D3"],
    ["N1 page=1 div=4 ts=4/4 ks=0\nm1 len=16\n1.1: 16 C5\n2.1: clef=G 16 C4 clef=F",
     "N1 page=2 div=4 ts=4/4 ks=0\nm2 len=16\n1.1: 16 D5\n2.1: 16 D3"],
], ids=["next-bar", "next-page"])
def test_a_clef_printed_at_the_end_of_a_bar_starts_the_next_bar_in_that_clef(pages):
    assert all(note_rules.problems(page) == [] for page in pages)
    bars = clefs_in_bars(from_notes.score_from_pages(pages))
    assert bars[0] == [("1", "G", True), ("2", "G", True)] and bars[1] == [("2", "F", True)]


def test_a_clef_change_is_written_where_it_is_printed():
    page = PAGES[0].replace("2.1: 2 r", "2.1: clef=F 2 r", 1).replace("m6 len=12 ks=5f\n1.1:", "m6 len=12 ks=5f\n1.1: clef=G", 1)
    lower = next(line for line in page.splitlines()[page.splitlines().index("m6 len=12 ks=5f"):] if line.startswith("2.1:"))
    page = page.replace(lower, lower.replace("2.1: ", "2.1: clef=G ", 1), 1)
    bars = ET.fromstring(from_notes.score_from_notes(page)).find("part").findall("measure")
    changes = [(bar.get("number"), clef.get("number"), clef.findtext("sign")) for bar in bars[1:] for clef in bar.findall("attributes/clef")]
    assert changes == [("6", "2", "G")]


def test_a_corrected_bar_keeps_its_accidental_signs():
    before = QUICK_READING.read_bytes()
    lines = correct.bars_from_musicxml(before, 18).splitlines()
    replacement = "\n".join(lines[:2] + ["1.1: 12 D5 C5 8 E5 E4 A4 36 F#4 12 A4"] + [line for line in lines if line.startswith("2.")])
    after = correct.replace_bars(before, replacement)

    def lower_staff_signs(score):
        bar = ET.fromstring(score).find("part").findall("measure")[17]
        return [(note.findtext("pitch/step"), note.findtext("pitch/octave"), note.findtext("accidental")) for note in notes_of(bar) if note.findtext("staff") == "2"]

    assert any(sign for _, _, sign in lower_staff_signs(before))
    assert lower_staff_signs(after) == lower_staff_signs(before)


def scores_in_test_data():
    return [path for pattern in ("*.musicxml", "*.mxl") for path in sorted(DATA.rglob(pattern)) if path.name not in SIGNS_DISAGREE_WITH_PITCHES]


@pytest.mark.parametrize("path", scores_in_test_data(), ids=lambda path: path.name)
def test_the_accidental_rule_never_adds_or_changes_a_printed_sign(path):
    data = path.read_bytes()
    if data[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            data = archive.read(next(name for name in archive.namelist() if not name.startswith("META-INF") and name.endswith(("xml", "musicxml"))))
    root = ET.fromstring(data)
    for part in root.findall("part"):
        if part.find(".//transpose") is not None:
            continue
        fifths = 0
        for bar in part.findall("measure"):
            if bar.find("attributes/key/fifths") is not None:
                fifths = int(bar.findtext("attributes/key/fifths"))
            sounded = False
            key_changes_inside = False
            for element in bar:
                key_changes_inside = key_changes_inside or (sounded and element.tag == "attributes" and element.find("key") is not None)
                sounded = sounded or element.tag == "note"
            if key_changes_inside or bar.find("attributes/key[@number]") is not None:
                continue
            rewritten = copy.deepcopy(bar)
            for note in rewritten.findall("note"):
                for sign in note.findall("accidental"):
                    note.remove(sign)
            correct._write_accidentals(rewritten, fifths)
            for printed, ours in zip(notes_of(bar), notes_of(rewritten)):
                if ours.find("accidental") is not None:
                    assert printed.findtext("accidental") == ours.findtext("accidental"), (part.get("id"), bar.get("number"), printed.findtext("pitch/step"))


def bars_of(code):
    return [(measure.name, measure.length, [event.pitch for event in measure.events if event.pitch])
            for measure in ScoreIndex(load_toolkit(app.store.get(f"scores/{code}")).getMEI()).measures]


def hand_in(pages, score_id="QUICK1"):
    return asyncio.run(app.mcp.call_tool("use_careful_reading", {"score_id": score_id, "pages": pages}))


def careful_id(scan="QUICK1"):
    app.store.put(f"scores/{scan}", QUICK_READING.read_bytes())
    steps = text_of(asyncio.run(app.mcp.call_tool("careful_reading", {"score_id": scan})))
    return re.search(r"own score_id \((\w+)\)", steps)[1]


@pytest.mark.parametrize("pages, bars", [
    (["N1 page=1 div=4 ts=4/4 ks=0\nm1 len=16\n1.1: 16 C4\nm2 len=16\n1.1: 16 D4\nm3 len=8\n1.1: 8 E4",
      "N1 page=2 div=4 ts=4/4 ks=0\nm1 len=8\n1.1: 8 F4\n1.2: 8 A3\nm2 len=16\n1.1: 16 G4\nm3 len=16\n1.1: 16 A4"],
     [("1", 4, ["C4"]), ("2", 4, ["D4"]), ("3", 4, ["E4", "F4", "A3"]), ("4", 4, ["G4"]), ("5", 4, ["A4"])]),
    (["N1 page=1 div=2 ts=3/4 ks=1s\nm1 len=6\n1.1: 6 G4\nm2 len=4\n1.1: 4 B4",
      "N1 page=2 div=2 ts=3/4 ks=1s\nm1 len=2\n1.1: 2 D5\nm2 len=6\n1.1: 6 C5"],
     [("1", 3, ["G4"]), ("2", 3, ["B4", "D5"]), ("3", 3, ["C5"])]),
], ids=["bar-split-across-the-page-turn", "section-pickup-at-the-top-of-a-page"])
def test_a_later_page_may_begin_with_the_rest_of_a_bar_and_the_two_halves_are_one_bar(tmp_path, monkeypatch, pages, bars):
    monkeypatch.setattr(app, "store", app.LocalStore(tmp_path))
    app.store.put(app.reading_key("QUICK1"), json.dumps({"pages": 2}).encode())
    result = hand_in(pages)
    assert not result.is_error, text_of(result)
    code = text_of(result).split()[1]
    assert f"measures 1 to {bars[-1][0]}." in text_of(result)
    assert [(name, float(length), sorted(pitches)) for name, length, pitches in bars_of(code)] == [
        (name, float(length), sorted(pitches)) for name, length, pitches in bars]


def test_a_later_page_that_begins_with_a_short_bar_is_checked_by_its_own_bar_names(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "store", app.LocalStore(tmp_path))
    app.store.put(app.reading_key("QUICK1"), json.dumps({"pages": 2}).encode())
    first = "N1 page=1 div=4 ts=4/4 ks=0\nm1 len=16\n1.1: 16 C4\nm2 len=8\n1.1: 8 E4"
    for second, bar in (("N1 page=2 div=4 ts=4/4 ks=0\nm1 len=8\n1.1: 4 F4\nm2 len=16\n1.1: 16 G4", "1"),
                        ("N1 page=2 div=4 ts=4/4 ks=0\nm1 len=8\n1.1: 8 F4\nm2 len=16\n1.1: 8 G4", "2")):
        refused = hand_in([first, second])
        assert refused.is_error and f"Page 2: Bar {bar}, voice 1.1 adds up to" in text_of(refused), text_of(refused)
        assert "Bar 0" not in text_of(refused) and "-1" not in text_of(refused)
    short_first_page = hand_in(["N1 page=2 div=4 ts=4/4 ks=0\nm1 len=8\n1.1: 8 F4\nm2 len=16\n1.1: 16 G4"])
    assert [name for name, *_ in bars_of(text_of(short_first_page).split()[1])] == ["0", "1"]


SPLIT_AT_THE_TURN = ("N1 page=1 div=4 ts=4/4 ks=0\nm1 len=16\n1.1: 16 C4\nm2 len=8\n1.1: 8 E4{first}",
                     "N1 page=2 div=4 ts=4/4 ks=0\nm1 len=8\n1.1: 8 F4{second}\nm2 len=16\n1.1: 16 G4")


def test_a_slur_across_a_page_turn_is_refused_on_the_page_where_it_starts():
    first, second = SPLIT_AT_THE_TURN
    with pytest.raises(notes.NotesError, match="Page 1: A slur starts in voice 1.1 and never ends"):
        from_notes.score_from_pages([first.format(first="").replace("8 E4", "8 (E4"), second.format(second="").replace("8 F4", "8 F4)")])


def test_a_tie_into_a_voice_the_next_page_leaves_out_is_dropped():
    first, second = SPLIT_AT_THE_TURN
    score = ET.fromstring(from_notes.score_from_pages([first.format(first="\n1.2: 8 A3~"), second.format(second="")]))
    tied = [note for note in score.iter("note") if note.findtext("pitch/step") == "A"]
    assert len(tied) == 1 and tied[0].find("notations/tied") is None and tied[0].find("tie") is None


@pytest.mark.parametrize("before_the_turn, after_the_turn, sung", [
    ("\n1.1w: ki", "", [("E", "ki"), ("F", None), ("A", None), ("G", "lo")]),
    ("", "\n1.1w: la _", [("E", None), ("F", "la"), ("A", None), ("G", "lo")]),
], ids=["words-only-before-the-turn", "words-only-after-the-turn"])
def test_words_on_one_half_of_a_bar_split_by_the_page_turn_stay_on_their_notes(before_the_turn, after_the_turn, sung):
    pages = ["N1 page=1 div=4 ts=4/4 ks=0\nm1 len=16\n1.1: 16 C4\n1.1w: Ah\nm2 len=8\n1.1: 8 E4" + before_the_turn,
             "N1 page=2 div=4 ts=4/4 ks=0\nm1 len=8\n1.1: 4 F4 A4" + after_the_turn + "\nm2 len=16\n1.1: 16 G4\n1.1w: lo"]
    score = ET.fromstring(from_notes.score_from_pages(pages))
    words = [(note.findtext("pitch/step"), note.findtext("lyric/text")) for note in score.iter("note") if note.find("pitch") is not None]
    assert words == [("C", "Ah"), *sung]


@pytest.mark.parametrize("pages, sung", [
    (["N1 page=1 div=4 ts=4/4 ks=0\nm1 len=16\n1.1: 8 E4 C4~\n1.1w: Ah ki",
      "N1 page=2 div=4 ts=4/4 ks=0\nm1 len=16\n1.1: 8 C4 D4\n1.1w: _ la\nm2 len=16\n1.1: 16 G4\n1.1w: lo"],
     [("E4", "Ah"), ("C4", "ki"), ("C4", None), ("D4", "la"), ("G4", "lo")]),
    (["N1 page=1 div=4 ts=4/4 ks=0\nm1 len=16\n1.1: 16 C4\n1.1w: Ah\nm2 len=8\n1.1: 4 E4 D4~\n1.1w: ki ra",
      "N1 page=2 div=4 ts=4/4 ks=0\nm1 len=8\n1.1: 4 D4 A4\n1.1w: _ la\nm2 len=16\n1.1: 16 G4\n1.1w: lo"],
     [("C4", "Ah"), ("E4", "ki"), ("D4", "ra"), ("D4", None), ("A4", "la"), ("G4", "lo")]),
], ids=["between-two-whole-bars", "in-a-bar-split-by-the-turn"])
def test_a_sung_note_tied_over_the_page_turn_keeps_the_words_after_it_on_their_notes(pages, sung):
    score = ET.fromstring(from_notes.score_from_pages(pages))
    words = [(note.findtext("pitch/step") + note.findtext("pitch/octave"), note.findtext("lyric/text"))
             for note in score.iter("note") if note.find("pitch") is not None]
    assert words == sung
    tied = [note.find("tie").get("type") for note in score.iter("note") if note.find("tie") is not None]
    assert tied == ["start", "stop"]


def test_a_note_tied_in_from_the_page_before_still_needs_its_words_entry_on_its_own_page():
    pages = ["N1 page=1 div=4 ts=4/4 ks=0\nm1 len=16\n1.1: 8 E4 C4~\n1.1w: Ah ki",
             "N1 page=2 div=4 ts=4/4 ks=0\nm1 len=16\n1.1: 8 C4 D4\n1.1w: la"]
    with pytest.raises(notes.NotesError, match="Page 2: Bar 1, 1.1w: 1 entries for 2 sung notes"):
        from_notes.score_from_pages(pages)


def chord_symbols_of(score):
    return [(measure.name, at, symbol) for measure in ScoreIndex(load_toolkit(score).getMEI()).measures
            for at, symbol in measure.chord_symbols]


def drawn_symbols(score):
    signs = str.maketrans({"\uea64": "b", "\uea66": "#"})
    return [symbol.translate(signs) for svg in pdf_reader.preview(score).svgs for symbol in printed_symbols(svg)]


def test_a_lead_sheet_read_carefully_has_the_chord_symbols_of_the_score_it_was_printed_from():
    built = from_notes.score_from_pages([LEAD_SHEET_PAGE])
    assert chord_symbols_of(built) == chord_symbols_of(LEAD_SHEET)
    assert drawn_symbols(built) == PRINTED


def test_a_chord_symbol_line_gives_each_symbol_its_place_in_the_bar():
    index = notes.decode("N1 page=1 div=4 ts=4/4 ks=0\nm1 len=16\nc: Am7@0 D7/F#@10\n1.1: 16 A4")
    assert index.measures[0].chord_symbols == [(0, "Am7"), (Fraction(5, 2), "D7/F#")]


@pytest.mark.parametrize("entry", ["Am7", "Am7@16", "Am7@2.5", "@0", "Am7@-1"])
def test_a_chord_symbol_without_a_place_inside_its_bar_is_refused_on_its_page(entry):
    page = f"N1 page=1 div=4 ts=4/4 ks=0\nm1 len=16\nc: {entry}\n1.1: 16 A4"
    with pytest.raises(notes.NotesError, match=f"Page 1: Bar 1: a chord symbol is written as symbol@position.*not '{entry}'"):
        from_notes.score_from_pages([page])


def test_chord_symbols_on_both_sides_of_a_page_turn_keep_their_places():
    pages = ["N1 page=1 div=2 ts=4/4 ks=0\nm1 len=8\nc: C@0\n1.1: 8 C4\nm2 len=4\nc: F@2\n1.1: 4 E4",
             "N1 page=2 div=4 ts=4/4 ks=0\nm1 len=8\nc: G7@4\n1.1: 8 F4\nm2 len=16\nc: C@12\n1.1: 16 G4"]
    joined = from_notes.join_pages(pages)
    assert [line for line in joined.splitlines() if line.startswith("c:")] == ["c: C@0", "c: F@4 G7@12", "c: C@12"]
    assert chord_symbols_of(from_notes.score_from_pages(pages)) == [("1", 0, "C"), ("2", 1, "F"), ("2", 3, "G7"), ("3", 3, "C")]


def test_the_lead_sheet_split_over_two_pages_keeps_every_chord_symbol_in_its_bar():
    lines = LEAD_SHEET_PAGE.splitlines()
    turn = lines.index("m9 len=6")
    second = re.sub(r"^m(\d+)", lambda bar: f"m{int(bar[1]) - 8}", "\n".join([lines[0].replace("page=1", "page=2"), *lines[turn:]]), flags=re.M)
    assert chord_symbols_of(from_notes.score_from_pages(["\n".join(lines[:turn]), second])) == chord_symbols_of(LEAD_SHEET)


@pytest.mark.parametrize("written, listed", [
    ("Am7", "Am7"), ("D7/F#", "D7/F#"), ("Bb", "Bb"), ("B\u266dmaj7", "Bbmaj7"), ("F#m7b5", "F#m7b5"), ("C6/9", "C6/9"),
    ("C7(b9)", "C7(b9)"), ("G/B", "G/B"), ("N.C.", "N.C."), ("H7", None), ("(Am)", None), ("%", None), ("A<&B", "A<&B"),
])
def test_a_chord_symbol_is_printed_as_it_was_written_and_listed_when_it_names_a_chord(written, listed):
    built = from_notes.score_from_pages([f"N1 page=1 div=4 ts=4/4 ks=0\nm1 len=16\nc: {written}@0\n1.1: 16 A4"])
    assert [symbol for _, _, symbol in chord_symbols_of(built)] == ([listed] if listed else [])
    shown = written.replace("\u266d", "b").replace("<", "&lt;").replace("&B", "&amp;B")
    assert drawn_symbols(built) == [shown]


def test_a_chord_symbol_stands_where_no_note_starts_in_pickups_rest_bars_and_triplets():
    page = ("N1 page=1 div=3 ts=2/4 ks=0\nm0 len=3\nc: C@1\n1.1: 3 G4\nm1 len=6\nc: F@0 G7@4\n1.1: 6 r\n2.1: 6 C3\n"
            "m2 len=6\nc: C@5\n1.1: 1 C4 D4 E4 3 C4")
    assert chord_symbols_of(from_notes.score_from_pages([page])) == [
        ("0", Fraction(1, 3), "C"), ("1", 0, "F"), ("1", Fraction(4, 3), "G7"), ("2", Fraction(5, 3), "C")]


def test_a_correction_of_a_carefully_read_bar_keeps_its_chord_symbols():
    before = from_notes.score_from_pages([LEAD_SHEET_PAGE])
    handed_out = correct.bars_from_musicxml(before, 13)
    after = correct.replace_bars(before, handed_out.replace("1.1: 4 G4 1 B4 G4", "1.1: 6 G4"))
    assert after != before and chord_symbols_of(after) == chord_symbols_of(before)
    with pytest.raises(correct.CorrectionError, match="Bar 13: leave out the c: line"):
        correct.replace_bars(before, handed_out.replace("1.1:", "c: C@0\n1.1:"))


TRIAL = Path("/home/kema/sheet-music-gate/careful-vs-reader")
MEI_NS = "{http://www.music-encoding.org/ns/mei}"


def _note_list_pieces():
    pieces = {}
    for page in sorted(DATA.rglob("*.n1")):
        pieces.setdefault(re.sub(r"-page\d+$", "", page.stem), []).append(page)
    for page in sorted(TRIAL.glob("*/page*.n1")):
        pieces.setdefault(page.parent.name, []).append(page)
    return pieces


def _written_clefs(texts: list[str]) -> dict[str, list[tuple]]:
    written = {}
    for page, text in enumerate(texts):
        div = int(re.search(r"div=(\d+)", text)[1])
        bar, name = -1, "0"
        for line in text.splitlines():
            if bar_line := re.match(r"m(\S+) ", line):
                bar, name = bar + 1, bar_line[1]
                continue
            label, _, body = line.partition(":")
            if not notes.VOICE_LABEL.fullmatch(label.strip()):
                continue
            onset = Fraction(0)
            for group in correct._read_voice(body, div, name, label)[1]:
                if group.clef:
                    written.setdefault(label.split(".")[0], []).append(((page, bar, onset), notes.CLEFS[group.clef]))
                if group.names != "r":
                    written.setdefault(label.split(".")[0], []).append(((page, bar, onset), "note"))
                onset += group.duration
    return {staff: sorted(found, key=lambda event: (event[0], event[1] == "note")) for staff, found in written.items()}


def _clefs_a_staff_shows(events: list[tuple], default: tuple) -> list[tuple]:
    before_the_first_note = [clef for _, clef in itertools.takewhile(lambda event: event[1] != "note", events)]
    shown = [(before_the_first_note or [default])[0]]
    for _, clef in events:
        if clef != "note" and clef != shown[-1]:
            shown.append(clef)
    return shown


def _drawn_clefs(mei: ET.Element) -> dict[str, list[tuple]]:
    def clef_of(element, prefix=""):
        shape, line, octave = (element.get(f"{prefix}{name}") for name in ("shape", "line", "dis"))
        sign = 1 if element.get(f"{prefix}dis.place") == "above" else -1
        return shape, int(line), sign * {"8": 1, "15": 2}[octave] if octave else 0

    drawn = {}
    for definition in mei.iter(f"{MEI_NS}staffDef"):
        clef = definition.find(f"{MEI_NS}clef")
        drawn.setdefault(definition.get("n"), [clef_of(clef) if clef is not None else clef_of(definition, "clef.")])
    for measure in mei.iter(f"{MEI_NS}measure"):
        for staff in measure.iter(f"{MEI_NS}staff"):
            for clef in staff.iter(f"{MEI_NS}clef"):
                if clef.get("sameas") is None and clef_of(clef) != drawn[staff.get("n")][-1]:
                    drawn[staff.get("n")].append(clef_of(clef))
    return drawn


@pytest.mark.parametrize("pages", list(_note_list_pieces().values()), ids=list(_note_list_pieces()))
def test_every_staff_shows_the_clefs_its_note_list_states_from_its_first_note_on(pages):
    texts = [paged_file(page) for page in pages]
    drawn = _drawn_clefs(ET.fromstring(load_toolkit(from_notes.score_from_pages(texts)).getMEI()))
    written = _written_clefs(texts)
    wanted = {staff: _clefs_a_staff_shows(events, notes.CLEFS["F" if int(staff) == len(drawn) > 1 else "G"])
              for staff, events in written.items()}
    assert {staff: drawn[staff] for staff in wanted} == wanted



def test_a_clef_stated_on_a_bar_where_every_staff_rests_is_drawn_from_there_on():
    heading, *lines = (DATA / "careful/schubert-kraehe-voice-opening.n1").read_text().splitlines()
    turn = lines.index("m4 len=48")
    pages = [heading + "\n" + "\n".join(lines[:turn]).replace("1.1: 48 r", "1.1: clef=F 48 r", 1),
             heading.replace("page=1", "page=2") + "\n" + "\n".join(lines[turn:]).replace("1.1: 48 r", "1.1: clef=G 48 r", 1)]
    drawn = _drawn_clefs(ET.fromstring(load_toolkit(from_notes.score_from_pages(pages)).getMEI()))
    assert drawn == {"1": _clefs_a_staff_shows(_written_clefs(pages)["1"], notes.CLEFS["G"])} == {"1": [notes.CLEFS["F"], notes.CLEFS["G"]]}

def test_a_careful_reading_covers_every_page_of_a_scan_longer_than_the_quick_reading(tmp_path, monkeypatch):
    import pikepdf
    monkeypatch.setattr(app, "store", app.LocalStore(tmp_path))
    pages_read = []

    def read(data):
        pages_read.append(len(pdf_reader.open_pdf(data).pages))
        return pdf_reader.PdfReading(QUICK_READING.read_bytes(), pages_read[-1], True)

    monkeypatch.setattr(app.pdf_reader, "read_pdf", read)
    pdf = pikepdf.new()
    for _ in range(pdf_reader.READ_PAGES + 4):
        pdf.add_blank_page()
    out = io.BytesIO()
    pdf.save(out)
    asked = text_of(asyncio.run(app.read_pdf_data(out.getvalue(), "other", None, "read_pdf")))
    assert f"it has {pdf_reader.READ_PAGES + 4} pages, " in asked and pages_read == []
    card = asyncio.run(app.read_pdf_data(out.getvalue(), "other", None, "read_pdf"))
    score_id = text_of(card).split("score_id: ")[1].split()[0]
    total = pdf_reader.READ_PAGES + 4
    assert pages_read == [pdf_reader.READ_PAGES]
    steps = text_of(asyncio.run(app.mcp.call_tool("careful_reading", {"score_id": score_id})))
    assert f"A careful reading of this piece's {total} pages" in steps and f"page N of {total}" in steps
    pages = [f"N1 page={bar} div=1 ts=4/4 ks=0\nm{bar} len=4\n1.1: 4 C4" for bar in range(1, total + 1)]
    result = asyncio.run(app.mcp.call_tool("use_careful_reading", {"score_id": score_id, "pages": pages}))
    assert not result.is_error and "It holds" not in text_of(result)
    assert f"read from their {total}-page PDF" in text_of(card)
    assert (f"Only pages 1-{pdf_reader.READ_PAGES} of the {total} were read, to keep the wait short; to analyse the rest, send those "
            "pages as a separate PDF, or ask for the careful reading if I offered it.") in text_of(card)
    assert "reads up to" not in text_of(card)

    card_key = app.card_of(hashlib.sha256(out.getvalue()).hexdigest())
    saved = json.loads(app.store.get(card_key))
    del saved["of_pages"]
    app.store.put(card_key, json.dumps(saved).encode())
    app.store.put(app.reading_key(score_id), json.dumps({"pages": pdf_reader.READ_PAGES}).encode())
    again = asyncio.run(app.read_pdf_data(out.getvalue(), "other", None, "read_pdf"))
    assert pages_read == [pdf_reader.READ_PAGES] and f"read from their {total}-page PDF" in text_of(again)
    assert json.loads(app.store.get(app.reading_key(score_id))) == {"pages": total}


def test_a_pdf_longer_than_the_careful_page_limit_is_read_up_to_its_first_pages_with_music_and_says_what_is_left(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "store", app.LocalStore(tmp_path))
    app.store.put("scores/QUICK1", QUICK_READING.read_bytes())
    total = app.CAREFUL_PAGES + 6
    app.store.put(app.reading_key("QUICK1"), json.dumps({"pages": total}).encode())
    offer = app.careful_warning(total, "other")
    assert f"A careful reading of the first {app.CAREFUL_PAGES} pages with music of this piece's {total} pages is slower" in offer
    steps = text_of(asyncio.run(app.mcp.call_tool("careful_reading", {"score_id": "QUICK1"})))
    assert offer in steps and f"page N of {total} pages" in steps
    assert (f"A careful reading takes the first {app.CAREFUL_PAGES} pages that have music: a helper is started for each of "
            f"pages 1 to {app.CAREFUL_PAGES}, and for each helper that writes NO MUSIC, one more for the next page") in steps
    pages = [f"N1 page={page} div=1 ts=4/4 ks=0\nm{page} len=4\n1.1: 4 C4" for page in range(1, total + 1)]

    def handed_in(numbers):
        return text_of(asyncio.run(app.mcp.call_tool("use_careful_reading", {"score_id": "QUICK1", "pages": [pages[n - 1] for n in numbers]})))

    whole = handed_in(range(1, total + 1))
    assert f"measures 1 to {app.CAREFUL_PAGES}." in whole and "It holds" not in whole
    assert (f"A careful reading takes at most {app.CAREFUL_PAGES} pages with music, so pages {app.CAREFUL_PAGES + 1} to {total} "
            "of the PDF are not in it.") in whole
    assert (f'"This careful reading covers pages 1 to {app.CAREFUL_PAGES} of your PDF\'s {total} pages, as many pages with music '
            f'as a careful reading takes, so pages {app.CAREFUL_PAGES + 1} to {total} are not in it."') in whole
    after_a_title = handed_in(range(3, app.CAREFUL_PAGES + 3))
    assert f"measures 1 to {app.CAREFUL_PAGES}." in after_a_title
    assert f"It holds pages 3 to {app.CAREFUL_PAGES + 2} of the PDF's {total} pages; a page left out is taken to have no music." in after_a_title
    assert "handing it in with the others" not in after_a_title
    assert f"so pages {app.CAREFUL_PAGES + 3} to {total} of the PDF are not in it." in after_a_title
    late = handed_in([app.CAREFUL_PAGES + 1])
    assert "measures 1 to 1." in late and "handing it in with the others gives the whole piece" in late


def test_a_careful_reading_id_says_what_it_is(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "store", app.LocalStore(tmp_path))
    app.store.put("scores/QUICK1", QUICK_READING.read_bytes())
    app.store.put(app.reading_key("QUICK1"), json.dumps({"pages": 3}).encode())
    steps = text_of(asyncio.run(app.mcp.call_tool("careful_reading", {"score_id": "QUICK1"})))
    reading_id = re.search(r"careful reading's own score_id \((\w+)\)", steps)[1]
    for tool, arguments in (("draft_analysis", {}), ("careful_reading", {}),
                            ("render_analysis", {"annotations": {"annotations": [{"type": "harmony", "at": {"measure": 1, "beat": 1}, "label": "i", "key": "e"}]}})):
        refused = asyncio.run(app.mcp.call_tool(tool, {"score_id": reading_id, **arguments}))
        assert refused.is_error and text_of(refused) == app.A_CAREFUL_READING_ID, tool


@pytest.mark.parametrize("pages, minutes", [(1, 10), (3, 10), (4, 20), (10, 20), (11, 35), (20, 35), (26, 35)])
def test_the_time_named_for_a_careful_reading_in_claude_is_the_measured_one_for_its_pages(pages, minutes):
    assert f"takes about {minutes} minutes with one helper per page" in app.careful_warning(pages, "claude")
    assert "minutes" not in app.careful_warning(pages, "chatgpt")


BAR = "N1 page=1 div=4 ts=4/4 ks=0\nm1 len=16\n"
STAFF_KEY_LINE = ("Line {line}: a staff key line looks like 't: 2 ks=0', once for a staff where it prints another key "
                  "signature than the bar line's: the staff, numbered 1 to 32, and the key signature printed on it")
BAD_PAGES = [
    (BAR + "1.1: 16 C4" + " " * note_rules.MAX_CHARS, "The note list is too long"),
    (BAR + "1.1: 16 C4\n1.1w: la\x01", "The note list holds a control character; write only plain text"),
    ("N1 page=1 div=4 ts=4/4\nm1 len=16\n1.1: 16 C4", note_rules.HEADING),
    ("N1 page=1 div=4 ts=4-4 ks=0\nm1 len=16\n1.1: 16 C4", "A time signature looks like ts=3/4, not ts=4-4"),
    ("N1 page=1 div=4 ts= ks=0\nm1 len=16\n1.1: 16 C4", "A time signature looks like ts=3/4, not ts="),
    ("N1 page=1 div=4 ts=4/4 ks=8s\nm1 len=16\n1.1: 16 C4", "A key signature looks like ks=0, ks=2s or ks=3f, not ks=8s"),
    ("N1 page=1 div=4 ts=4/4 ks=0\nm1 len=16 foo\n1.1: 16 C4", "a bar line looks like 'm3 len=96', not 'm1 len=16 foo'"),
    ("N1 page=1 div=4 ts=4/4 ks=0\nm1 len=16 ts=x\n1.1: 16 C4", "A time signature looks like ts=3/4, not ts=x"),
    ("N1 page=1 div=4 ts=4/4 ks=0\n1.1: 16 C4\n" + BAR[28:] + "1.1: 16 C4", "Line 2: a voice line needs a bar line like 'm3 len=96' before it"),
    ("N1 page=1 div=4 ts=4/4 ks=0\nx: f@0\n" + BAR[28:] + "1.1: 16 C4", "Line 2: a marks line needs a bar line like 'm3 len=96' before it"),
    ("N1 page=1 div=4 ts=4/4 ks=0\nc: C@0\n" + BAR[28:] + "1.1: 16 C4", "Line 2: a chord symbol line needs a bar line like 'm3 len=96' before it"),
    ("N1 page=1 div=4 ts=4/4 ks=0", "The note list has no measures"),
    ("N1 page=1 div=1 ts=1/4 ks=0\n" + "\n".join(f"m{bar} len=1\n1.1: 1 C4" for bar in range(1, note_rules.MAX_BARS + 2)),
     "The note list has 1001 bars; at most 1000 can be built"),
    ("N1 page=1 div=4 ts=4/4 ks=0\nm5 len=16\n1.1: 16 C4\nm3 len=16\n1.1: 16 D4",
     "Bar 3: bar numbers go up from one bar to the next, and m5 comes before it"),
    ("N1 page=1 div=4 ts=4/4 ks=0\nm1 len=260\n1.1: 260 C4", "Bar 1: len= makes this bar longer than 64 quarter notes"),
    ("N1 page=1 div=3 ts=4/4 ks=0\nm1 len=12\n1.1: 12 C4\nm2 len=5\n1.1: 4 C4 1 D4", "Bar 2: len= gives a length no bar can have"),
    ("N1 div=4 ts=4/4 ks=0\nm1 len=16\n1.1: 16 C4", note_rules.HEADING),
    (BAR + "1-1: 16 C4", "Line 3: expected 'staff.voice: tokens', e.g. '1.1: 24 C4'"),
    (BAR + "40.1: 16 C4", "Staves are numbered 1 to 32 from the top and voices 1 to 8"),
    (BAR + "0.1: 16 C4", "Bar 1: invalid or repeated voice 0.1"),
    (BAR + "1.1: 16 C4\n1.1: 16 D4", "Bar 1: invalid or repeated voice 1.1"),
    (BAR + "1.1: 16 C4\n2.1: 16 r", "Bar 1: include all 1 staves"),
    (BAR + "1.1: 16 H4", "Bar 1: invalid pitch 'H4'"),
    (BAR + "1.1: 16 C10", "Bar 1: invalid pitch 'C10'"),
    (BAR + "1.1: gr 16 C4", "Grace rests are not supported"),
    (BAR + "1.1: 0 C4 16 C4", "Bar 1: duration must be positive"),
    (BAR + "1.1: C4 16 C4", "Bar 1: note/rest has no duration"),
    ("N1 page=1 div=5 ts=4/4 ks=0\nm1 len=20\n1.1: 7 C4 3 D4 10 E4", "Bar 1: a duration of 7 at div=5 cannot be written as one "
     "note; use plain or dotted note values, notes of a simple tuplet such as a triplet, or tied notes"),
    (BAR + "1.1: 12 C4", "Bar 1, voice 1.1 adds up to 3; expected 4 quarter notes"),
    (BAR + "1.1w: la\n1.1: 16 C4", "Bar 1: the words line 1.1w needs its voice line 1.1 before it"),
    (BAR + "1.1: 16 C4\n1.1w: la la", "Bar 1, 1.1w: 2 entries for 1 sung notes; write one entry for each note that is not "
     "a rest, a grace note or the continuation of a tie, and _ where no syllable is printed"),
    (BAR + "c: C@16\n1.1: 16 C4", "Bar 1: a chord symbol is written as symbol@position, without spaces, with the position "
     "in units from the start of the bar and below its len, e.g. D7@0, not 'C@16'"),
    (BAR + "x: zz\n1.1: 16 C4", "The note list could not be read: unknown mark 'zz'"),
    (BAR + "1.1: 16 C4)", "Bar 1, voice 1.1: a slur ends here that was never started; write ( before its first note"),
    (BAR + "1.1: 16 " + "(" * 17 + "C4" + ")" * 16, "Bar 1, voice 1.1: more than 16 slurs are open at once"),
    (BAR + "1.1: 16 (C4", "A slur starts in voice 1.1 and never ends; close it with ) after its last note"),
    (BAR.replace("len=16", "len=16 rep=twice") + "1.1: 16 C4", "A repeat sign is written rep=start, rep=end or rep=both, not rep=twice"),
    (BAR.replace("len=16", "len=16 ending=a") + "1.1: 16 C4", "An ending is written ending=1, ending=2 and so on, not ending=a"),
    ("N1 page=1 div=4 ts=4/4 ks=0\ni: Flute\n" + BAR[28:] + "1.1: 16 C4", "Line 2: the instruments line looks like 'i: 1=Flute "
     "2=Clarinet in Bb', one number=name for each staff, numbered 1 to 32 from the top"),
    ("N1 page=1 div=4 ts=4/4 ks=0\nt: 1 ks=flat\n" + BAR[28:] + "1.1: 16 C4", STAFF_KEY_LINE.format(line=2)),
    (BAR + "t: 1 ks=1f\nt: 1 ks=2f\n1.1: 16 C4", STAFF_KEY_LINE.format(line=4)),
    (BAR + "1.1: 8va( 16 C4", "An octave line starts in staff 1 and never ends; close it with )8va (or )8vb, )15ma, )15mb) "
     "after the last note under it"),
    (BAR + "1.1: 16 C4 )8va", "Bar 1, staff 1: an octave line ends here that was never started; write 8va( before the first "
     "note under it"),
    (BAR + "1.1: clef=G^15 16 C8", "Bar 1: invalid pitch 'C8' (it sounds as C10, with the clef's 8 and the octave lines)"),
]
RULES_ONLY = {"Staves are numbered 1 to 32 from the top and voices 1 to 8", "The note list has 1001 bars; at most 1000 can be built",
              "Bar 1: len= makes this bar longer than 64 quarter notes",
              "Bar 1: include all 1 staves", "A repeat sign is written rep=start, rep=end or rep=both, not rep=twice",
              "An ending is written ending=1, ending=2 and so on, not ending=a"}


def builds_without_the_rules(page):
    try:
        from_notes.score_from_notes(from_notes.join_pages([page]))
        from_notes.score_from_notes(page)
    except Exception:
        return False
    return True


@pytest.mark.parametrize("page, sentence", BAD_PAGES, ids=[sentence[:50] for _, sentence in BAD_PAGES])
def test_every_page_the_builder_refuses_gets_the_rules_sentence_first(page, sentence):
    assert note_rules.problems(page) == [sentence]
    with pytest.raises(notes.NotesError) as refused:
        from_notes.score_from_pages([page])
    assert str(refused.value) == ("Page 1: " if note_rules.page_number(page) else "Note list 1: ") + sentence
    assert builds_without_the_rules(page) == (sentence in RULES_ONLY)


@pytest.mark.parametrize("pages, sentence", [
    ([f"N1 page={page} div=1 ts=1/4 ks=0\n" + "\n".join(f"m{bar} len=1\n1.1: 1 C4" for bar in range(1, 601)) for page in (1, 2)],
     "The pages have 1200 bars together; at most 1000 can be built"),
    ([BAR + "1.1: 16 C4" + " " * (note_rules.MAX_CHARS // 2), BAR.replace("page=1", "page=2") + "1.1: 16 C4" + " " * (note_rules.MAX_CHARS // 2)], "The pages are longer than 200000 characters together"),
], ids=["bars", "characters"])
def test_pages_too_big_together_are_refused_before_they_are_joined(pages, sentence):
    assert note_rules.join_problems(pages) == [sentence]
    with pytest.raises(notes.NotesError, match=f"^{re.escape(sentence)}$"):
        from_notes.score_from_pages(pages)


BENCH = TRIAL / "bench"
REAL_PAGES = sorted(DATA.rglob("*.n1")) + sorted(TRIAL.glob("*/page*.n1")) + sorted(BENCH.glob("codex/*/page*.n1")) + \
    sorted(BENCH.glob("sonnet/*/page*.n1"))


@pytest.mark.parametrize("page", [paged_file(path) for path in REAL_PAGES] + [page for page, _ in BAD_PAGES],
                         ids=[str(path.relative_to(path.parents[2])) for path in REAL_PAGES] + [s[:50] for _, s in BAD_PAGES])
def test_the_rules_pass_a_page_exactly_when_it_builds(page):
    found = note_rules.problems(page)
    try:
        from_notes.score_from_pages([page])
    except notes.NotesError as refused:
        assert found and str(refused).endswith(found[0])
    else:
        assert found == []


def test_the_real_pages_are_all_in_the_sweep():
    if not TRIAL.exists():
        pytest.skip("the trial's pages are not on this computer")
    assert len(list(BENCH.glob("codex/*/page*.n1"))) == len(list(BENCH.glob("sonnet/*/page*.n1"))) == 4


def music21_written_as(duration):
    found = quarterConversion(opFrac(duration))
    tuplet = found.tuplet
    return ([(shape.type, shape.dots) for shape in found.components],
            (tuplet.numberNotesActual, tuplet.numberNotesNormal, tuplet.durationNormal.type, tuplet.durationNormal.dots) if tuplet else None)


def lengths_up_to_a_whole_note(divs):
    return sorted({Fraction(units, div) for div in divs for units in range(1, 4 * div + 1)})


def test_the_rules_write_every_length_as_the_engraver_does():
    sample = random.Random(960).sample(lengths_up_to_a_whole_note(range(65, 961, 7)), 3000)
    lengths = lengths_up_to_a_whole_note(range(1, 65)) + sample
    assert [length for length in lengths if note_rules.written_as(length) != music21_written_as(length)] == []


def test_the_rules_write_every_length_up_to_div_960_as_the_engraver_does():
    if not os.environ.get("FULL_DURATION_PIN"):
        pytest.skip("about 40 processor minutes; set FULL_DURATION_PIN=1 to run it")
    lengths = lengths_up_to_a_whole_note(range(1, 961))
    assert [length for length in lengths if note_rules.written_as(length) != music21_written_as(length)] == []


REFUSED_BEFORE_THE_RULE_FILE = {9, 15, 17, 18, 19, 21, 23, 25, 27, 29, 30, 31}
GROUPS = {f"{count} notes in {span} quarter{'s' * (span > 1)}":
          f"N1 page=1 div={count} ts=4/4 ks=0\nm1 len={4 * count}\n1.1: {span} " + " ".join(["C5"] * count)
          + (f" {(4 - span) * count} r" if span < 4 else "")
          for count in range(2, 33) if count not in REFUSED_BEFORE_THE_RULE_FILE for span in (1, 2, 4)}
GROUPS["32 128ths"] = "N1 page=1 div=32 ts=4/4 ks=0\nm1 len=128\n1.1: 1 " + " ".join(["C5"] * 32) + " 96 r"
LOCAL_PAGES = sorted(TRIAL.rglob("page*.n1"))


@pytest.mark.parametrize("page", [*GROUPS.values(), *(paged_file(path) for path in sorted(DATA.rglob("*.n1")) + LOCAL_PAGES)],
                         ids=[*GROUPS, *(str(path) for path in sorted(DATA.rglob("*.n1")) + LOCAL_PAGES)])
def test_every_page_that_built_before_the_rule_file_passes_the_rules(page):
    assert note_rules.problems(page) == []
    from_notes.score_from_pages([page])


@pytest.mark.parametrize("count", sorted(REFUSED_BEFORE_THE_RULE_FILE))
def test_a_tuplet_the_engraver_cannot_write_is_refused_by_the_rules(count):
    page = f"N1 page=1 div={count} ts=4/4 ks=0\nm1 len={4 * count}\n1.1: 1 " + " ".join(["C5"] * count) + f" {3 * count} r"
    assert note_rules.problems(page) == [f"Bar 1: a duration of 1 at div={count} cannot be written as one note; use plain or "
                                         "dotted note values, notes of a simple tuplet such as a triplet, or tied notes"]


@pytest.mark.parametrize("text, reported", [
    (BAR + "1.1: 12 C4", "Bar 1, voice 1.1 adds up to 3; expected 4 quarter notes\n1 errors, 0 pitches outside the key signature"),
    (BAR + "1.1: 16 F#4", "0 errors, 1 pitches outside the key signature"),
    ("N1 page=1 div=4 ts=4/4 ks=2f\nt: 1 ks=0\nm1 len=16\n1.1: 16 E5\n2.1: 16 Eb4",
     "0 errors, 0 pitches outside the key signature"),
    ((RULES / "clarinet-own-key-page1.n1").read_text(), "0 errors, 0 pitches outside the key signature"),
    ((RULES / "clarinet-key-change-unstated-page1.n1").read_text(), "0 errors, 0 pitches outside the key signature"),
], ids=["bad", "good", "a-staff-in-its-own-key", "its-own-key-changes", "its-own-key-stays-when-the-page-key-changes"])
def test_the_kit_check_reports_what_the_builder_would_refuse(tmp_path, text, reported):
    python = next((python for python in (sys.executable, shutil.which("python3")) if python and subprocess.run(
        [python, "-c", "import cv2, scipy"], capture_output=True).returncode == 0), None)
    if python is None:
        pytest.skip("no Python with the kit's image packages on this computer")
    page = tmp_path / "page1.n1"
    page.write_text(text)
    kit = Path(__file__).parent.parent / "kit" / "notetool.py"
    printed = subprocess.run([python, str(kit), "check", str(page)], capture_output=True, text=True, check=True).stdout
    assert printed.strip().endswith(reported)


@pytest.mark.parametrize("voice, sentence", [
    ("clef=G^8 8va( 8 F5>~ )8va 8 F5", "Bar 1: invalid pitch 'F5>~' (it sounds as F7>~, with the clef's 8 and the octave lines)"),
    ("8va( 8 (E5 F5))8va 8 r", "Bar 1: write )8va as an entry of its own, with a space before and after it, not 'F5))8va'"),
], ids=["names-what-was-written", "octave-line-stuck-to-a-slur"])
def test_a_check_message_quotes_what_the_helper_wrote(voice, sentence):
    assert note_rules.problems(BAR + "1.1: " + voice)[0] == sentence
    with pytest.raises(notes.NotesError, match=re.escape(sentence)):
        from_notes.score_from_pages([BAR + "1.1: " + voice])


def trial_pages(case, *numbers):
    if not (TRIAL / case).exists():
        pytest.skip("the trial's pages are not on this computer")
    return [paged_file(TRIAL / case / f"page{number}.n1") for number in numbers]


def events_of(score):
    return [(measure.name, event.staff, event.pitch) for measure in ScoreIndex(load_toolkit(score).getMEI()).measures
            for event in measure.events if event.pitch]


def test_two_pages_that_disagree_are_sent_back_once_then_taken_with_the_doubtful_bars_shaded(tmp_path, monkeypatch, caplog):
    pages = trial_pages("c0306c", 1, 2)
    monkeypatch.setattr(app, "store", app.LocalStore(tmp_path))
    app.store.put(app.reading_key("QUICK1"), json.dumps({"pages": 4}).encode())
    caplog.set_level("WARNING", logger="engine.output_checks")
    reading = careful_id()
    first = hand_in(pages, reading)
    assert not first.is_error and "score_id:" not in text_of(first)
    assert "The careful reading is not stored yet" in text_of(first)
    assert "Page 2 has 1 staff in a system and page 1 has 2 staves: count the staves again" in text_of(first)
    assert "around" not in text_of(first)
    assert [record.getMessage() for record in caplog.records] == ["output check failed: pages agree on their staves (pages 2)"]
    caplog.clear()
    second = hand_in(pages, reading)
    assert not second.is_error, text_of(second)
    assert ('Note for the user: "Page 2 of my careful reading did not agree with page 1: it has 1 staff where page 1 has 2 '
            "staves, and its staff 1 could not be matched to one of page 1's, so its music is left out, and a second reading "
            'did not change that. Its bars (17 to 32) are shaded because they may be misread."') in text_of(second)
    code = text_of(second).split()[1]
    assert asyncio.run(app.shaded_bars(code)) == list(range(17, 33))
    assert [event for event in events_of(app.store.get(f"scores/{code}")) if int(event[0]) >= 17] == []
    assert [record.getMessage() for record in caplog.records] == [
        "output check on a second reading: pages agree on their staves (page 2) confirmed"]


ORCHESTRA = ["Flute 1", "Flute 2", "Oboe 1", "Oboe 2", "Clarinet in Bb 1", "Clarinet in Bb 2", "Bassoon 1", "Bassoon 2",
             "Horn in F 1.3", "Horn in F 2.4", "Trumpet in Bb 1", "Trumpet in Bb 2", "Trombone 1", "Trombone 2", "Tuba",
             "Timpani", "Snare drum", "Bass drum", "Cymbals", "Harp", "Harp", "Violins 1", "Violins 2", "Violas", "Cellos",
             "Double bass"]


def with_names(page, kept, line="i: concert"):
    places = {old: new for new, old in enumerate(kept, 1)}
    lines = page.splitlines()
    named = [lines[0], line + " " + " ".join(f"{places[staff]}={ORCHESTRA[staff - 1]}" for staff in kept)] if line else [lines[0]]
    for text in lines[1:]:
        voice = re.fullmatch(r"(\d+)\.(\d+)(w?):(.*)", text)
        if voice and int(voice[1]) not in places:
            continue
        named.append(f"{places[int(voice[1])]}.{voice[2]}{voice[3]}:{voice[4]}" if voice else text)
    return "\n".join(named)


def test_a_later_page_that_leaves_out_resting_staves_and_names_its_instruments_is_taken(tmp_path, monkeypatch):
    fourth, fifth = trial_pages("4a3d12", 4, 5)
    monkeypatch.setattr(app, "store", app.LocalStore(tmp_path))
    app.store.put(app.reading_key("QUICK1"), json.dumps({"pages": 6}).encode())
    resting = [staff for staff in range(1, 27) if not re.search(rf"^{staff}\.\d+: .*[A-G][#b]*\d", fifth, re.M)]
    kept = [staff for staff in range(1, 27) if staff not in resting[:6]]
    unnamed = hand_in([with_names(fourth, range(1, 27), ""), with_names(fifth, kept, "")], careful_id())
    assert "Page 5 has 20 staves in a system and page 4 has 26 staves" in text_of(unnamed)
    taken = hand_in([with_names(fourth, range(1, 27)), with_names(fifth, kept)])
    assert "score_id:" in text_of(taken) and "shaded" not in text_of(taken), text_of(taken)
    score = app.store.get(f"scores/{text_of(taken).split()[1]}")
    root = ET.fromstring(score)
    assert [part.findtext("part-name") for part in root.iter("score-part")] == list(dict.fromkeys(ORCHESTRA))
    assert root.find(".//transpose") is None
    fifth_page = {(name, staff) for name, staff, _ in events_of(score) if int(name) > 7}
    assert {staff for _, staff in fifth_page} == {staff for staff in range(1, 27) if staff not in resting}


def test_a_page_that_takes_its_time_signature_follows_the_one_in_force_at_the_end_of_the_page_before():
    pages = trial_pages("831deb/whole", *range(1, 9))
    taken = [pages[0]] + [re.sub(r"ts=(\S+) ks", r"ts=\1? ks", page, count=1) for page in pages[1:]]
    joined = from_notes.hand_in(taken)
    meters = {measure.number: measure.meter for measure in ScoreIndex(load_toolkit(joined.score).getMEI()).measures}
    assert (meters[93], meters[94], meters[95], meters[122], meters[123], meters[198]) == ("6/8", "6/8", "2/2", "2/2", "2/2", "2/2")
    assert joined.doubts == []
    as_printed = ScoreIndex(load_toolkit(from_notes.score_from_pages(pages)).getMEI())
    assert (as_printed.measure(94).meter, as_printed.measure(123).meter) == ("3/4", "4/4")


def test_an_assumed_time_signature_with_bars_of_another_length_is_a_doubt():
    first = "N1 page=1 div=2 ts=6/8 ks=0\nm1 len=6\n1.1: 6 C4\nm2 len=6\n1.1: 6 D4"
    doubts = from_notes.hand_in([first, "N1 page=2 div=2 ts=4/4? ks=0\nm1 len=8\n1.1: 8 E4"]).doubts
    assert [(doubt.rule, doubt.page) for doubt in doubts] == [(from_notes.TIME, 2)]
    assert doubts[0].reason.startswith("Page 2 takes the time signature 4/4 without one printed, but page 1 ends in 6/8")


def test_a_bar_split_by_a_repeat_sign_is_drawn_as_two_measures_of_one_bar():
    pages = trial_pages("04fc05", 1, 2)
    unmarked = ScoreIndex(load_toolkit(from_notes.score_from_pages(pages)).getMEI()).measures
    assert [measure.number for measure in unmarked] == list(range(22))
    marked = pages[0].replace("m8 len=180", "m8 len=180 rep=end").replace("m10 len=192", "m10 len=192 rep=end", 1)
    score = from_notes.score_from_pages([marked, pages[1]])
    bars = ScoreIndex(load_toolkit(score).getMEI()).measures
    assert [measure.number for measure in bars] == list(range(21)) and bars[8].length == 4 and len(bars[8].segments) == 2
    drawn = ET.fromstring(score).find("part").findall("measure")
    assert [measure.get("number") for measure in drawn[8:11]] == ["8", "8a", "9"]
    assert [(measure.get("number"), line.findtext("bar-style")) for measure in drawn for line in measure.iter("barline")] == [
        ("8", "light-heavy"), ("9", "light-heavy")]


def test_an_octave_clef_and_an_octave_line_turn_printed_pitches_into_sounding_ones_and_the_clef_is_drawn_as_printed():
    page = ("N1 page=1 div=4 ts=4/4 ks=0\nm1 len=16\n1.1: clef=G^8 8 C5 8va( E5 )8va\n2.1: clef=F_8 16 C3\n"
            "m2 len=16\n1.1: 8 C5 clef=G 8 C5\n2.1: 8vb( 16 C3 )8vb")
    score = from_notes.score_from_pages([page])
    assert sorted(events_of(score)) == [("1", 1, "C6"), ("1", 1, "E7"), ("1", 2, "C2"), ("2", 1, "C5"), ("2", 1, "C6"), ("2", 2, "C1")]
    clefs = [(clef.findtext("sign"), clef.findtext("clef-octave-change")) for clef in ET.fromstring(score).iter("clef")]
    assert clefs == [("G", "1"), ("F", "-1"), ("G", None)]




def rules(*names):
    return [(RULES / f"{name}.n1").read_text() for name in names]


def stored(result):
    return app.store.get(f"scores/{text_of(result).split()[1]}")


def parts_of(score):
    root = ET.fromstring(score)
    return [(name.findtext("part-name"), part.findtext("measure/attributes/key/fifths"), part.findtext("measure/attributes/transpose/chromatic"),
             part.findtext("measure/attributes/transpose/octave-change"))
            for name, part in zip(root.iter("score-part"), root.iter("part"))]


@pytest.fixture
def scan_of_three_pages(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "store", app.LocalStore(tmp_path))
    app.store.put(app.reading_key("QUICK1"), json.dumps({"pages": 3}).encode())


def test_a_page_that_disagrees_is_sent_back_once_then_shaded_and_named_by_its_pdf_page(scan_of_three_pages):
    reading = careful_id()
    first = text_of(hand_in(rules("octave-apart-page2", "octave-apart-page3"), reading))
    assert "not stored yet" in first and "Page 2 has staff 1 around G4, page 3 has it around G5 in the same clef" in first
    assert f"score_id {reading}" in first
    assert not list(app.store.folder.glob("usage/*.json"))
    second = hand_in(rules("octave-apart-page2", "octave-apart-page3"), reading)
    assert ('Note for the user: "Page 3 of my careful reading did not agree with page 2: staff 1 sounds about an octave away '
            'from page 2, and a second reading did not change that. Its bars (3 to 4) are shaded') in text_of(second)
    assert asyncio.run(app.shaded_bars(text_of(second).split()[1])) == [3, 4]
    assert json.loads(next(app.store.folder.glob("usage/*.json")).read_text())["draft"] == 1


def test_a_hand_in_with_the_pdfs_score_id_is_shaded_at_once_and_says_it_was_not_checked_again(scan_of_three_pages):
    result = text_of(hand_in(rules("octave-apart-page2", "octave-apart-page3")))
    assert "not stored yet" not in result
    assert "staff 1 sounds about an octave away from page 2, and I could not check it again. Its bars (3 to 4)" in result
    assert app.store.get(app.careful_key("QUICK1")) is None


def test_two_chats_with_one_pdf_each_get_their_own_reading_and_send_back(scan_of_three_pages):
    first_chat, second_chat = careful_id(), careful_id()
    assert first_chat != second_chat
    assert "not stored yet" in text_of(hand_in(rules("octave-apart-page2", "octave-apart-page3"), first_chat))
    assert "not stored yet" in text_of(hand_in(rules("octave-apart-page2", "octave-apart-page3"), second_chat))
    assert "a second reading did not change that" in text_of(hand_in(rules("octave-apart-page2", "octave-apart-page3"), first_chat))


def test_one_page_alone_keeps_its_page_number_and_logs_no_second_reading_of_a_page_it_does_not_hold(scan_of_three_pages, caplog):
    reading = careful_id()
    hand_in(rules("octave-apart-page2", "octave-apart-page3"), reading)
    caplog.set_level("WARNING", logger="engine.output_checks")
    caplog.clear()
    alone = text_of(hand_in(rules("octave-apart-page2"), reading))
    assert "It holds page 2 of the PDF's 3 pages; a page left out is taken to have no music." in alone
    assert [record.getMessage() for record in caplog.records] == []


def test_a_page_with_fewer_staves_is_matched_by_the_names_it_shares_with_the_page_with_most_staves(scan_of_three_pages):
    score = stored(hand_in(rules("three-staves-page1", "violin-rests-page2"), careful_id()))
    assert [name for name, *_ in parts_of(score)] == ["Flute", "Violin", "Cello"]
    assert sorted(events_of(score)) == [("1", 1, "D5"), ("1", 2, "B4"), ("1", 3, "G2"), ("2", 1, "E5"), ("2", 3, "C3")]


def test_pages_with_the_same_number_of_staves_are_matched_by_position_whatever_their_names(scan_of_three_pages):
    result = hand_in(rules("three-staves-page1", "other-spellings-page2"), careful_id())
    assert "score_id:" in text_of(result) and "shaded" not in text_of(result)
    assert [name for name, *_ in parts_of(stored(result))] == ["Flute", "Violin", "Cello"]


def test_a_page_with_fewer_unnamed_staves_is_sent_back_with_the_names_then_shaded_without_a_new_part(scan_of_three_pages):
    reading = careful_id()
    first = text_of(hand_in(rules("three-staves-page1", "two-staves-unnamed-page2"), reading))
    assert ("Page 2 has 2 staves in a system and page 1 has 3 staves: count the staves again. Page 1 names these staves: "
            "Flute, Violin, Cello; write your i: line with these names for the staves your page shows.") in first
    second = hand_in(rules("three-staves-page1", "two-staves-unnamed-page2"), reading)
    assert ("Page 2 of my careful reading did not agree with page 1: it has 2 staves where page 1 has 3 staves, and its "
            "staves 1 and 2 could not be matched to one of page 1's, so their music is left out, and a second reading did not "
            "change that. Its bars (2 to 2)") in text_of(second)
    assert [name for name, *_ in parts_of(stored(second))] == ["Flute", "Violin", "Cello"]
    assert [event for event in events_of(stored(second)) if event[0] == "2"] == []


def test_a_staff_that_matches_no_staff_of_the_page_with_most_staves_is_put_on_none(scan_of_three_pages):
    reading = careful_id()
    first = text_of(hand_in(rules("three-staves-page1", "flute-and-abbreviated-cello-page2"), reading))
    assert "Page 1 does not name Vc.. Page 1 names these staves: Flute, Violin, Cello" in first
    second = text_of(hand_in(rules("three-staves-page1", "flute-and-abbreviated-cello-page2"), reading))
    assert "its staff 2 (Vc.) could not be matched to one of page 1's, so its music is left out" in second
    assert [event for event in events_of(stored(hand_in(rules("three-staves-page1", "flute-and-abbreviated-cello-page2"), reading)))
            if event[0] == "2"] == [("2", 1, "E5")]


def test_a_time_signature_written_with_a_question_mark_gives_way_to_the_one_in_force_when_the_bars_are_as_long():
    pages = rules("meter-printed-page1", "meter-assumed-page2", "meter-printed-page3", "meter-assumed-page4")
    built = from_notes.hand_in(pages)
    meters = [measure.meter for measure in ScoreIndex(load_toolkit(built.score).getMEI()).measures]
    assert meters == ["6/8"] * 4 + ["2/2"] * 4 and built.doubts == []


def test_a_bar_split_by_a_repeat_sign_is_one_bar_8_and_8a_and_two_endings_stay_two_bars(scan_of_three_pages):
    result = hand_in(rules("repeat-and-endings-page1"))
    score = stored(result)
    bar_2 = correct.bars_from_musicxml(score, 2)
    assert bar_2.splitlines()[1:] == ["m2 len=4", "1.1: 3 D5 1 E5"]
    corrected = asyncio.run(app.mcp.call_tool("correct_bars", {"score_id": text_of(result).split()[1],
                                                               "replacement_bars": bar_2.replace("3 D5", "3 F5")}))
    assert not corrected.is_error and "Bar 2: D5 changed to F5." in text_of(corrected)
    drawn = ET.fromstring(score).find("part").findall("measure")
    assert [measure.get("number") for measure in drawn] == ["1", "2", "2a", "3", "4", "5"]
    assert [(measure.get("number"), line.get("location"), line.find("repeat").get("direction"))
            for measure in drawn for line in measure.iter("barline") if line.find("repeat") is not None] == [
        ("1", "left", "forward"), ("2", "right", "backward"), ("3", "left", "forward"), ("4", "right", "backward")]
    assert [measure.number for measure in ScoreIndex(load_toolkit(score).getMEI()).measures] == [1, 2, 3, 4, 5]


def keys_of_parts(score):
    return [(name.findtext("part-name"), [bar.findtext("attributes/key/fifths") for bar in part.findall("measure")],
             part.find(".//transpose") is not None)
            for name, part in zip(ET.fromstring(score).iter("score-part"), ET.fromstring(score).iter("part"))]


def shown_as_printed(parts):
    return (f"My reading shows {parts} as printed: where an instrument is a transposing one, its notes sound at a different "
            "pitch than shown, and the analysis across the parts may be off there.")


CLARINET_SHOWN_AS_PRINTED = shown_as_printed("the Clarinet in Bb part")


@pytest.mark.parametrize("names, parts, pitches, said", [
    (["clarinet-own-key-page1"], [("Clarinet in Bb", ["0", "-1"], False), ("Piano", ["-2", "-3"], False)],
     ["D5", "Bb4"], [CLARINET_SHOWN_AS_PRINTED]),
    (["clarinet-key-change-unstated-page1"], [("Clarinet in Bb", ["0", None], False), ("Piano", ["-2", "-3"], False)],
     ["D5", "B4"], [CLARINET_SHOWN_AS_PRINTED]),
    (["clarinet-named-only-page1"], [("Clarinet in Bb", ["-2"], False), ("Piano", ["-2"], False)], ["D5"],
     [CLARINET_SHOWN_AS_PRINTED]),
    (["clarinet-with-sounds-page1"], [("Clarinet in Bb", ["0"], False), ("Piano", ["-2"], False)], ["D5"],
     [CLARINET_SHOWN_AS_PRINTED]),
    (["clarinet-own-key-page1", "clarinet-in-a-page2", "clarinet-unstated-page3"],
     [("Clarinet in Bb", ["0", "-1", "1", "-2"], False), ("Piano", ["-2", "-3", "-2", None], False)],
     ["D5", "Bb4", "E5", "D5"], [CLARINET_SHOWN_AS_PRINTED]),
    (["octave-instruments-page1"], [("Piccolo", ["0"], False), ("Guitar", ["0"], False), ("Double bass", ["0"], False)],
     ["C6"], []),
    (["horn-and-timpani-page1"], [("Horn in F", ["0"], False), ("Timpani", ["0"], False), ("Cello", ["-2"], False)], ["G4"],
     [shown_as_printed("the Horn in F part")]),
    (["unnamed-staff-own-key-page1"], [("", ["1"], False), ("", ["-2"], False)], ["D5"],
     [shown_as_printed("the part on staff 1")]),
    (["timpani-with-a-tuning-page1"], [("Timpani in A", ["-2"], False), ("Cello", ["-2"], False)], ["A2"],
     [shown_as_printed("the Timpani in A part")]),
    (["concert-horn-page1"], [("Horn in F", ["-2"], False), ("Cello", ["-2"], False)], ["G4"], []),
    (["piano-staves-differ-page1"], [("Piano", ["-2"], False)], ["B4"],
     [shown_as_printed("the Piano part"), "The staves of the Piano part print different key signatures. My reading draws them all with the top staff's key "
      "signature, and their notes keep their printed pitches."]),
    (["key-before-the-turn-page1", "key-after-the-turn-page2"],
     [("Clarinet in Bb", ["0", "-1", None], False), ("Cello", ["-2", None, None], False)], ["D5", "E5", "F5", "G5"],
     [CLARINET_SHOWN_AS_PRINTED]),
    (["transposing-names-alone-page1"],
     [("Horn", ["0"], False), ("Alto Saxophone", ["-2"], False), ("Cor anglais", ["-2"], False), ("Cello", ["-2"], False)], ["G4"],
     [shown_as_printed("the Horn part, the Alto Saxophone part and the Cor anglais part")]),
], ids=["own-key-and-its-change", "change-not-stated", "named-only", "old-sounds", "each-page-its-own", "octave-instruments",
        "horn-by-name-timpani-not", "unnamed", "timpani-with-a-tuning", "concert-pitch", "staves-of-one-part-differ",
        "key-stated-after-a-bar-split-by-the-turn", "named-alone-without-in"])
def test_every_staff_is_written_as_printed_in_the_key_signature_its_page_states_and_named_once_when_it_may_sound_elsewhere(
        names, parts, pitches, said):
    built = from_notes.hand_in(rules(*names))
    assert keys_of_parts(built.score) == parts and built.notes == said and built.doubts == []
    assert [pitch for bar, staff, pitch in events_of(built.score) if staff == 1] == pitches


def test_a_staff_key_line_for_a_staff_the_page_does_not_have_is_refused_by_the_rules_and_the_builder():
    page = "N1 page=1 div=1 ts=4/4 ks=2f\ni: 1=Flute\nt: 7 ks=2s\nm1 len=4\n1.1: 4 D5"
    said = ("Line 3: this staff key line is for staff 7, and the highest staff with a voice line or a name on this page "
            "is 1")
    assert note_rules.problems(page) == [said]
    with pytest.raises(notes.NotesError, match=f"Page 1: {said}"):
        from_notes.hand_in([page])


def test_a_correction_of_a_part_shown_as_printed_takes_the_printed_pitches(scan_of_three_pages):
    code = text_of(hand_in(rules("clarinet-named-only-page1"), careful_id())).split()[1]
    bar = correct.bars_from_musicxml(app.store.get(f"scores/{code}"), 1, part="Clarinet in Bb")
    assert "D5" in bar
    corrected = asyncio.run(app.mcp.call_tool("correct_bars", {"score_id": code, "part": "Clarinet in Bb",
                                                               "replacement_bars": bar.replace("D5", "E5")}))
    assert not corrected.is_error, text_of(corrected)
    score = app.store.get(f"scores/{corrected.structured_content['score_id']}")
    assert [pitch for number, staff, pitch in events_of(score) if staff == 1] == ["E5"]
    assert [part[2] for part in keys_of_parts(score)] == [False, False]
    listed = {tool.name: tool.description for tool in asyncio.run(app.mcp.list_tools())}
    assert "a careful reading, which shows every part as printed and takes the printed pitches" in listed["correct_bars"]


def test_a_page_may_name_only_the_staves_it_prints_names_for():
    built = from_notes.hand_in(rules("one-name-of-three-page1"))
    assert [name for name, *_ in keys_of_parts(built.score)] == ["Flute", "", ""]


def test_a_short_first_bar_is_a_pickup_on_the_lowest_page_and_completes_the_bar_before_on_a_later_page():
    built = from_notes.hand_in(rules("pickup-page2", "completes-the-turn-page3"))
    bars = ScoreIndex(load_toolkit(built.score).getMEI()).measures
    assert [(measure.number, measure.length) for measure in bars] == [(0, 1), (1, 4), (2, 4), (3, 4)] and bars[0].is_pickup
    assert built.doubts == [] and built.bars == {2: [0, 1, 2], 3: [2, 3]}


@pytest.mark.parametrize("pages,numbered", [
    (["mazurka-ends-page1", "mazurka-opens-page2"], [(1, 3), (2, 1), (3, 3), (4, 3)]),
    (["mazurka-ends-page1", "pickup-same-signatures-page2"], [(1, 3), (2, 1), (3, 3)]),
    (["mazurka-ends-page1", "pickup-new-time-page2"], [(1, 3), (2, 1), (3, 2)]),
    (["pickup-page2", "does-not-complete-page3"], [(0, 1), (1, 4), (2, 2), (3, 1), (4, 4)]),
], ids=["new-piece-in-a-new-key", "same-signatures", "new-time", "the-bar-before-short-by-another-amount"])
def test_a_later_page_that_opens_with_a_pickup_is_stored_at_once_unshaded_and_counted_on(scan_of_three_pages, pages, numbered):
    said = text_of(hand_in(rules(*pages), careful_id()))
    assert "not stored yet" not in said and "shaded" not in said
    code = said.split()[1]
    bars = ScoreIndex(load_toolkit(app.store.get(f"scores/{code}")).getMEI()).measures
    assert [(bar.number, bar.length) for bar in bars] == numbered
    assert json.loads(app.store.get(app.doubted_key(code))) == []


def test_a_hand_in_without_its_title_page_names_the_pages_it_holds(scan_of_three_pages):
    result = text_of(hand_in(rules("pickup-page2", "completes-the-turn-page3")))
    assert "measures 0 to 3." in result and "It holds pages 2 and 3 of the PDF's 3 pages; a page left out is taken to have no music." in result


def test_a_correction_keeps_the_careful_readings_doubt_shading(scan_of_three_pages):
    code = text_of(hand_in(rules("octave-apart-page2", "octave-apart-page3"))).split()[1]
    bar_1 = correct.bars_from_musicxml(app.store.get(f"scores/{code}"), 1)
    corrected = asyncio.run(app.mcp.call_tool("correct_bars", {"score_id": code, "replacement_bars": bar_1.replace("4 E4", "4 F4")}))
    assert not corrected.is_error, text_of(corrected)
    assert asyncio.run(app.shaded_bars(corrected.structured_content["score_id"])) == [3, 4]


def test_a_careful_reading_with_several_parts_says_how_to_correct_it(scan_of_three_pages):
    result = text_of(hand_in(rules("three-staves-page1")))
    assert "It has 3 parts, so a correction with correct_bars names the part it is for (part=)" in result


def test_first_and_second_endings_become_brackets_over_their_bars():
    page = ("N1 page=1 div=1 ts=4/4 ks=0\nm1 len=4 rep=start\n1.1: 4 C5\nm2 len=4 ending=1\n1.1: 4 D5\nm3 len=4 ending=1 rep=end\n"
            "1.1: 4 E5\nm4 len=4 ending=2\n1.1: 4 F5")
    bars = ET.fromstring(from_notes.score_from_pages([page])).find("part").findall("measure")
    found = [(bar.get("number"), line.get("location"), line.findtext("repeat") is not None or line.find("repeat") is not None,
              [(ending.get("number"), ending.get("type")) for ending in line.findall("ending")]) for bar in bars for line in bar.findall("barline")]
    assert found == [("1", "left", True, []), ("2", "left", False, [("1", "start")]), ("3", "right", True, [("1", "stop")]),
                     ("4", "left", False, [("2", "start")]), ("4", "right", False, [("2", "stop")])]


def test_the_bench_pages_still_build():
    pages = sorted(BENCH.glob("*/*/page*.n1"))
    if not pages:
        pytest.skip("the trial's pages are not on this computer")
    assert len(pages) == 8
    for page in pages:
        from_notes.score_from_pages([paged_file(page)])


def test_a_whole_piece_over_a_limit_is_not_offered_a_corrected_hand_in(scan_of_three_pages):
    pages = [f"N1 page={page} div=1 ts=1/4 ks=0\n" + "\n".join(f"m{bar} len=1\n1.1: 1 C4" for bar in range(1, 601)) for page in (1, 2)]
    refused = hand_in(pages)
    assert refused.is_error and text_of(refused) == ("The careful reading cannot be built: The pages have 1200 bars together; "
                                                     "at most 1000 can be built")
    one_page = hand_in([BAR + "1.1: 12 C4"])
    assert text_of(one_page).startswith("A page does not fit; a corrected hand-in takes every page again: Page 1: Bar 1,")


def test_every_doubt_of_a_page_reaches_the_user_and_only_a_doubt_sent_back_is_said_to_have_been_read_again(scan_of_three_pages):
    reading = careful_id()
    first = text_of(hand_in(rules("octave-apart-page2", "octave-apart-page3"), reading))
    assert "not stored yet" in first and "without one printed" not in first
    second = text_of(hand_in(rules("octave-apart-page2", "octave-apart-and-assumed-meter-page3"), reading))
    assert ("staff 1 sounds about an octave away from page 2, and a second reading did not change that. Its bars (3 to 4)"
            in second)
    assert "its time signature does not follow from page 2, and I could not check it again. Its bars (3 to 4)" in second


def test_both_doubts_of_one_page_are_said_when_the_page_was_not_sent_back(scan_of_three_pages):
    said = text_of(hand_in(rules("octave-apart-page2", "octave-apart-and-assumed-meter-page3")))
    assert said.count("and I could not check it again. Its bars (3 to 4)") == 2


def test_a_hand_in_at_the_daily_limit_is_refused_before_it_is_built_or_sent_back(scan_of_three_pages):
    reading = careful_id()
    usage = app.store.folder / f"usage/{app.today()}.json"
    usage.parent.mkdir(parents=True, exist_ok=True)
    usage.write_text(json.dumps({"draft": app.DAILY_LIMITS["draft"]}))
    refused = hand_in(rules("octave-apart-page2", "octave-apart-page3"), reading)
    assert refused.is_error and text_of(refused) == app.LIMIT_MESSAGE
    assert "sent_back" not in json.loads(app.store.get(app.careful_key(reading)))


def test_two_short_bars_inside_a_page_without_a_repeat_sign_stay_two_bars():
    page = "N1 page=1 div=1 ts=4/4 ks=0\nm1 len=4\n1.1: clef=G 4 C5\nm2 len=3\n1.1: 3 D5\nm3 len=1\n1.1: 1 E5\nm4 len=4\n1.1: 4 F5"
    measures = ScoreIndex(load_toolkit(from_notes.hand_in([page]).score).getMEI()).measures
    assert [(measure.name, measure.length) for measure in measures] == [("1", 4), ("2", 3), ("3", 1), ("4", 4)]


def test_pages_are_joined_in_page_order_whatever_order_they_are_handed_in():
    built = from_notes.hand_in(rules("completes-the-turn-page3", "pickup-page2"))
    bars = ScoreIndex(load_toolkit(built.score).getMEI()).measures
    assert [(measure.number, measure.length) for measure in bars] == [(0, 1), (1, 4), (2, 4), (3, 4)]
    assert built.doubts == [] and built.bars == {2: [0, 1, 2], 3: [2, 3]}


def test_a_misprinted_beat_keeps_its_printed_values_with_the_last_note_made_up_and_is_no_tuplet():
    score = from_notes.hand_in(rules("misprinted-beat-page1")).score
    durations = [int(note.findtext("duration")) for note in ET.fromstring(score).iter("note")]
    assert durations == [4, 4, 4, 4, 4, 4, 2, 6, 32]
    assert not list(ET.fromstring(score).iter("time-modification"))


def test_notes_under_an_optional_octave_line_are_written_where_they_are_printed():
    score = from_notes.hand_in(rules("octave-line-ad-lib-page2")).score
    assert [pitch for _, _, pitch in events_of(score)] == ["C5", "D5", "E5", "F5", "G5"]
    assert not list(ET.fromstring(score).iter("octave-shift"))
