import asyncio
import copy
import io
import json
import re
import xml.etree.ElementTree as ET
import zipfile
from fractions import Fraction
from pathlib import Path

import pytest

from engine import correct, from_notes, notes
from engine import read_pdf as pdf_reader
from engine.render import load_toolkit
from engine.score import ScoreIndex
from server import app
from tests.test_chord_symbols import LEAD_SHEET, PRINTED, printed_symbols

DATA = Path(__file__).parent / "data"
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


def text_of(result):
    return next(item.text for item in result.content if item.type == "text")


def notes_of(bar):
    return [note for note in bar.findall("note") if note.find("pitch") is not None]


def test_a_scan_is_offered_a_careful_reading_and_the_pages_become_a_score(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "store", app.LocalStore(tmp_path))
    app.store.put("scores/QUICK1", QUICK_READING.read_bytes())
    reading = text_of(app.pdf_card_result({"score_id": "QUICK1", "pages": 3, "scan": True, "measures": "1 to 25", "bars": 25,
                                           "notice": "", "image_url": "", "pdf_url": "", "page_images": []}, "read_pdf", "other"))
    assert "Offer for the user" not in reading and "Shall I go ahead?" not in reading
    assert "it needs no check by the user first" in reading
    assert reading.endswith("\nscore_id QUICK1 is ready for draft_analysis.")
    typeset = text_of(app.pdf_card_result({"score_id": "QUICK1", "pages": 3, "scan": False, "measures": "1 to 25", "bars": 25,
                                           "notice": "", "image_url": "", "pdf_url": "", "page_images": []}, "read_pdf", "other"))
    assert reading == typeset and "careful" not in reading and "quick" not in reading
    assert app.careful_warning(3, "other") in app.CAREFUL_OFFER.format(warning=app.careful_warning(3, "other"))
    assert "takes about 5 minutes a page. To do it" in app.careful_warning(3, "other")
    assert "This piece has 3 pages. Shall I go ahead?" in app.careful_warning(3, "other")
    assert "allowance" not in app.careful_warning(3, "other")
    assert ("takes about 5 minutes a page. I'd start one helper per page, each on Sonnet at medium effort, and that uses a lot of "
            "your plan's usage allowance. As a guide, a 10-page piece") in app.careful_warning(3, "claude")
    assert "download and run a small measuring script from Sheet Music Analysis" in app.careful_warning(3, "other")

    refused = asyncio.run(app.mcp.call_tool("careful_reading", {"score_id": "QUICK1"}))
    assert refused.is_error
    app.store.put(app.scan_key("QUICK1"), json.dumps({"pages": 3}).encode())
    steps = text_of(asyncio.run(app.mcp.call_tool("careful_reading", {"score_id": "QUICK1"})))
    assert f"{app.PUBLIC_BASE_URL}/kit/$f" in steps and "kit/reader.md" in steps and "page N of 3" in steps
    assert "time signature 2/2" in steps and "1 sharps" in steps

    result = asyncio.run(app.mcp.call_tool("use_careful_reading", {"score_id": "QUICK1", "pages": PAGES}))
    assert not result.is_error and "It holds only" not in text_of(result)
    first_page_only = text_of(asyncio.run(app.mcp.call_tool("use_careful_reading", {"score_id": "QUICK1", "pages": PAGES[:1]})))
    assert "It holds only 1 page of the scan's 3 pages, so the rest of the piece is not in it;" in first_page_only
    assert ('Note for the user, if the other pages cannot be read: "This careful reading covers only 1 page of your '
            "scan's 3 pages") in first_page_only
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
    app.store.put(app.scan_key("QUICK1"), json.dumps({"pages": 3}).encode())
    broken = PAGES[0].replace("1.1: 2 (G#3+G#4", "1.1: 4 (G#3+G#4", 1)
    assert broken != PAGES[0]
    result = asyncio.run(app.mcp.call_tool("use_careful_reading", {"score_id": "QUICK1", "pages": [broken, *PAGES[1:]]}))
    assert result.is_error
    assert "Page 1: Bar 0, voice 1.1 adds up to 1" in text_of(result) and "a corrected hand-in takes every page again" in text_of(result)
    second = PAGES[1].replace("m1 len=24", "m1 len=20", 1)
    wrong_second = asyncio.run(app.mcp.call_tool("use_careful_reading", {"score_id": "QUICK1", "pages": [PAGES[0], second, PAGES[2]]}))
    assert wrong_second.is_error and "Page 2: Bar 1, voice 1.1 adds up to" in text_of(wrong_second)
    pickup_as_bar_1 = re.sub(r"^m(\d+)", lambda bar: f"m{int(bar[1]) + 1}", PAGES[0], flags=re.M)
    refused = asyncio.run(app.mcp.call_tool("use_careful_reading", {"score_id": "QUICK1", "pages": [pickup_as_bar_1]}))
    assert refused.is_error and "Page 1: Bar 1: len= makes the first bar shorter" in text_of(refused)
    for pages, reason in (([], "No pages"), ([PAGES[0]] * 4, "This scan has 3 pages"),
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
    app.store.put(app.scan_key("QUICK1"), json.dumps({"pages": 3}).encode())
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
    page = "N1 div=1 ts=2/4 ks=0\nm1 len=2\n1.1: 2 C5\n1.1w: Hal-\n2.1: 2 C3\n2.1w: la\nm2 len=2\n1.1: 2 D5\n1.1w: lo\n2.1: 2 D3\n2.1w: la"
    score = ET.fromstring(from_notes.score_from_notes(page))
    sung = {(note.findtext("staff"), note.findtext("lyric/text")): note.findtext("lyric/syllabic") for note in score.iter("note") if note.find("lyric") is not None}
    assert sung == {("1", "Hal"): "begin", ("1", "lo"): "end", ("2", "la"): "single"}


def test_a_later_page_without_a_time_signature_keeps_the_one_before():
    later = PAGES[1].replace("ts=6/8", "ts=", 1)
    assert later != PAGES[1]
    assert from_notes.join_pages([PAGES[0], later]) == from_notes.join_pages(PAGES[:2])


def test_a_clef_written_after_the_last_note_is_refused_with_where_to_put_it():
    voice_line = next(line for line in PAGES[0].splitlines() if line.startswith("2.1:"))
    with pytest.raises(correct.CorrectionError, match="clef=F is written after the last note"):
        from_notes.score_from_notes(PAGES[0].replace(voice_line, voice_line + " clef=F", 1))


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


def hand_in(pages):
    return asyncio.run(app.mcp.call_tool("use_careful_reading", {"score_id": "QUICK1", "pages": pages}))


@pytest.mark.parametrize("pages, bars", [
    (["N1 div=4 ts=4/4 ks=0\nm1 len=16\n1.1: 16 C4\nm2 len=16\n1.1: 16 D4\nm3 len=8\n1.1: 8 E4",
      "N1 div=4 ts=4/4 ks=0\nm1 len=8\n1.1: 8 F4\n1.2: 8 A3\nm2 len=16\n1.1: 16 G4\nm3 len=16\n1.1: 16 A4"],
     [("1", 4, ["C4"]), ("2", 4, ["D4"]), ("3", 4, ["E4", "F4", "A3"]), ("4", 4, ["G4"]), ("5", 4, ["A4"])]),
    (["N1 div=2 ts=3/4 ks=1s\nm1 len=6\n1.1: 6 G4\nm2 len=4\n1.1: 4 B4",
      "N1 div=2 ts=3/4 ks=1s\nm1 len=2\n1.1: 2 D5\nm2 len=6\n1.1: 6 C5"],
     [("1", 3, ["G4"]), ("2", 3, ["B4", "D5"]), ("3", 3, ["C5"])]),
], ids=["bar-split-across-the-page-turn", "section-pickup-at-the-top-of-a-page"])
def test_a_later_page_may_begin_with_the_rest_of_a_bar_and_the_two_halves_are_one_bar(tmp_path, monkeypatch, pages, bars):
    monkeypatch.setattr(app, "store", app.LocalStore(tmp_path))
    app.store.put(app.scan_key("QUICK1"), json.dumps({"pages": 2}).encode())
    result = hand_in(pages)
    assert not result.is_error, text_of(result)
    code = text_of(result).split()[1]
    assert f"measures 1 to {bars[-1][0]}." in text_of(result)
    assert [(name, float(length), sorted(pitches)) for name, length, pitches in bars_of(code)] == [
        (name, float(length), sorted(pitches)) for name, length, pitches in bars]


def test_a_later_page_that_begins_with_a_short_bar_is_checked_by_its_own_bar_names(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "store", app.LocalStore(tmp_path))
    app.store.put(app.scan_key("QUICK1"), json.dumps({"pages": 2}).encode())
    first = "N1 div=4 ts=4/4 ks=0\nm1 len=16\n1.1: 16 C4\nm2 len=8\n1.1: 8 E4"
    for second, bar in (("N1 div=4 ts=4/4 ks=0\nm1 len=8\n1.1: 4 F4\nm2 len=16\n1.1: 16 G4", "1"),
                        ("N1 div=4 ts=4/4 ks=0\nm1 len=8\n1.1: 8 F4\nm2 len=16\n1.1: 8 G4", "2")):
        refused = hand_in([first, second])
        assert refused.is_error and f"Page 2: Bar {bar}, voice 1.1 adds up to" in text_of(refused), text_of(refused)
        assert "Bar 0" not in text_of(refused) and "-1" not in text_of(refused)
    short_first_page = hand_in(["N1 div=4 ts=4/4 ks=0\nm1 len=8\n1.1: 8 F4\nm2 len=16\n1.1: 16 G4"])
    assert short_first_page.is_error and "Page 1: Bar 1: len= makes the first bar shorter" in text_of(short_first_page)


SPLIT_AT_THE_TURN = ("N1 div=4 ts=4/4 ks=0\nm1 len=16\n1.1: 16 C4\nm2 len=8\n1.1: 8 E4{first}",
                     "N1 div=4 ts=4/4 ks=0\nm1 len=8\n1.1: 8 F4{second}\nm2 len=16\n1.1: 16 G4")


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
    pages = ["N1 div=4 ts=4/4 ks=0\nm1 len=16\n1.1: 16 C4\n1.1w: Ah\nm2 len=8\n1.1: 8 E4" + before_the_turn,
             "N1 div=4 ts=4/4 ks=0\nm1 len=8\n1.1: 4 F4 A4" + after_the_turn + "\nm2 len=16\n1.1: 16 G4\n1.1w: lo"]
    score = ET.fromstring(from_notes.score_from_pages(pages))
    words = [(note.findtext("pitch/step"), note.findtext("lyric/text")) for note in score.iter("note") if note.find("pitch") is not None]
    assert words == [("C", "Ah"), *sung]


@pytest.mark.parametrize("pages, sung", [
    (["N1 div=4 ts=4/4 ks=0\nm1 len=16\n1.1: 8 E4 C4~\n1.1w: Ah ki",
      "N1 div=4 ts=4/4 ks=0\nm1 len=16\n1.1: 8 C4 D4\n1.1w: _ la\nm2 len=16\n1.1: 16 G4\n1.1w: lo"],
     [("E4", "Ah"), ("C4", "ki"), ("C4", None), ("D4", "la"), ("G4", "lo")]),
    (["N1 div=4 ts=4/4 ks=0\nm1 len=16\n1.1: 16 C4\n1.1w: Ah\nm2 len=8\n1.1: 4 E4 D4~\n1.1w: ki ra",
      "N1 div=4 ts=4/4 ks=0\nm1 len=8\n1.1: 4 D4 A4\n1.1w: _ la\nm2 len=16\n1.1: 16 G4\n1.1w: lo"],
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
    pages = ["N1 div=4 ts=4/4 ks=0\nm1 len=16\n1.1: 8 E4 C4~\n1.1w: Ah ki",
             "N1 div=4 ts=4/4 ks=0\nm1 len=16\n1.1: 8 C4 D4\n1.1w: la"]
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
    index = notes.decode("N1 div=4 ts=4/4 ks=0\nm1 len=16\nc: Am7@0 D7/F#@10\n1.1: 16 A4")
    assert index.measures[0].chord_symbols == [(0, "Am7"), (Fraction(5, 2), "D7/F#")]


@pytest.mark.parametrize("entry", ["Am7", "Am7@16", "Am7@2.5", "@0", "Am7@-1"])
def test_a_chord_symbol_without_a_place_inside_its_bar_is_refused_on_its_page(entry):
    page = f"N1 div=4 ts=4/4 ks=0\nm1 len=16\nc: {entry}\n1.1: 16 A4"
    with pytest.raises(notes.NotesError, match=f"Page 1: Bar 1: a chord symbol is written as symbol@position.*not '{entry}'"):
        from_notes.score_from_pages([page])


def test_chord_symbols_on_both_sides_of_a_page_turn_keep_their_places():
    pages = ["N1 div=2 ts=4/4 ks=0\nm1 len=8\nc: C@0\n1.1: 8 C4\nm2 len=4\nc: F@2\n1.1: 4 E4",
             "N1 div=4 ts=4/4 ks=0\nm1 len=8\nc: G7@4\n1.1: 8 F4\nm2 len=16\nc: C@12\n1.1: 16 G4"]
    joined = from_notes.join_pages(pages)
    assert [line for line in joined.splitlines() if line.startswith("c:")] == ["c: C@0", "c: F@4 G7@12", "c: C@12"]
    assert chord_symbols_of(from_notes.score_from_pages(pages)) == [("1", 0, "C"), ("2", 1, "F"), ("2", 3, "G7"), ("3", 3, "C")]


def test_the_lead_sheet_split_over_two_pages_keeps_every_chord_symbol_in_its_bar():
    lines = LEAD_SHEET_PAGE.splitlines()
    turn = lines.index("m9 len=6")
    second = re.sub(r"^m(\d+)", lambda bar: f"m{int(bar[1]) - 8}", "\n".join([lines[0], *lines[turn:]]), flags=re.M)
    assert chord_symbols_of(from_notes.score_from_pages(["\n".join(lines[:turn]), second])) == chord_symbols_of(LEAD_SHEET)


@pytest.mark.parametrize("written, listed", [
    ("Am7", "Am7"), ("D7/F#", "D7/F#"), ("Bb", "Bb"), ("B\u266dmaj7", "Bbmaj7"), ("F#m7b5", "F#m7b5"), ("C6/9", "C6/9"),
    ("C7(b9)", "C7(b9)"), ("G/B", "G/B"), ("N.C.", "N.C."), ("H7", None), ("(Am)", None), ("%", None), ("A<&B", "A<&B"),
])
def test_a_chord_symbol_is_printed_as_it_was_written_and_listed_when_it_names_a_chord(written, listed):
    built = from_notes.score_from_pages([f"N1 div=4 ts=4/4 ks=0\nm1 len=16\nc: {written}@0\n1.1: 16 A4"])
    assert [symbol for _, _, symbol in chord_symbols_of(built)] == ([listed] if listed else [])
    shown = written.replace("\u266d", "b").replace("<", "&lt;").replace("&B", "&amp;B")
    assert drawn_symbols(built) == [shown]


def test_a_chord_symbol_stands_where_no_note_starts_in_pickups_rest_bars_and_triplets():
    page = ("N1 div=3 ts=2/4 ks=0\nm0 len=3\nc: C@1\n1.1: 3 G4\nm1 len=6\nc: F@0 G7@4\n1.1: 6 r\n2.1: 6 C3\n"
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


def _stated_opening_clefs(text: str) -> dict[str, tuple]:
    div = int(re.search(r"div=(\d+)", text)[1])
    stated, done, bar = {}, set(), "0"
    for line in text.splitlines():
        if bar_line := re.match(r"m(\S+) ", line):
            done |= {staff for staff in stated}
            bar = bar_line[1]
            continue
        label, _, body = line.partition(":")
        if not notes.VOICE_LABEL.fullmatch(label.strip()) or label.split(".")[0] in done:
            continue
        groups = correct._read_voice(body, div, bar, label)[1]
        if groups:
            staff = label.split(".")[0]
            clef = notes.CLEFS[groups[0].clef] if groups[0].clef else None
            if clef or staff not in stated:
                stated[staff] = clef
    return stated


@pytest.mark.parametrize("pages", list(_note_list_pieces().values()), ids=list(_note_list_pieces()))
def test_every_staff_starts_in_the_clef_its_first_note_is_written_in(pages):
    texts = [page.read_text() for page in pages]
    mei = ET.fromstring(load_toolkit(from_notes.score_from_pages(texts)).getMEI())
    drawn = {}
    for definition in mei.iter(f"{MEI_NS}staffDef"):
        clef = definition.find(f"{MEI_NS}clef")
        shape, line = (clef.get("shape"), clef.get("line")) if clef is not None else (definition.get("clef.shape"), definition.get("clef.line"))
        octave = (clef if clef is not None else definition).get("clef.dis" if clef is None else "dis")
        drawn.setdefault(definition.get("n"), (shape, int(line), -1 if octave else 0))
    stated = _stated_opening_clefs(texts[0])
    staves = len(drawn)
    wanted = {staff: clef or notes.CLEFS["F" if int(staff) == staves > 1 else "G"] for staff, clef in stated.items()}
    assert {staff: drawn[staff] for staff in wanted} == wanted
    measures = list(mei.iter(f"{MEI_NS}measure"))
    staves = {staff.get("n") for measure in measures for staff in measure.iter(f"{MEI_NS}staff")}
    changed_before_first_note = []
    for number in staves:
        for measure in measures:
            staff = next((staff for staff in measure.iter(f"{MEI_NS}staff") if staff.get("n") == number), None)
            kinds = [element.tag for element in (staff.iter() if staff is not None else [])
                     if element.tag in (f"{MEI_NS}clef", f"{MEI_NS}note")]
            if f"{MEI_NS}note" in kinds:
                if f"{MEI_NS}clef" in kinds[:kinds.index(f"{MEI_NS}note")]:
                    changed_before_first_note.append(number)
                break
    assert changed_before_first_note == []


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
    card = asyncio.run(app.read_pdf_data(out.getvalue(), "other", "read_pdf"))
    score_id = text_of(card).split("score_id: ")[1].split()[0]
    total = pdf_reader.READ_PAGES + 4
    assert pages_read == [pdf_reader.READ_PAGES]
    steps = text_of(asyncio.run(app.mcp.call_tool("careful_reading", {"score_id": score_id})))
    assert f"This piece has {total} pages." in steps and f"page N of {total}" in steps
    pages = [f"N1 div=1 ts=4/4 ks=0\nm{bar} len=4\n1.1: 4 C4" for bar in range(1, total + 1)]
    result = asyncio.run(app.mcp.call_tool("use_careful_reading", {"score_id": score_id, "pages": pages}))
    assert not result.is_error and "It holds only" not in text_of(result)
