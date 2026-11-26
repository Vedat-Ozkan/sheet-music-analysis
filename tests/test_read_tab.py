import copy
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from engine import correct
from engine.export import export_musicxml
from engine.read_pdf import problem_spots
from engine.read_tab import MORE_THAN_ONE_STAFF, NO_RHYTHM, OutsideScope, read_tab
from engine.render import load_toolkit
from engine.score import ScoreIndex
from tests.data.tabs.measure import FOLDERS, USERS, compare, measure, notes, truth_of

DATA = Path(__file__).parent / "data"
MEI = "{http://www.music-encoding.org/ns/mei}"
BESIDE_A_STAFF = {"greensleeves-staff-and-tab", "bond-theme-guitar-tab"}
GENERATED = sorted(path.stem for path in (DATA / "tabs").glob("*.musicxml") if path.stem not in BESIDE_A_STAFF)


def reading_against_truth(name: str, folder: Path):
    pdf = folder / f"{name}.pdf"
    if not pdf.exists():
        pytest.skip(f"{pdf} is a user's file kept out of the repository")
    truth_data, capo, bar_limit, spelled = truth_of(pdf)
    reading = read_tab(pdf.read_bytes())
    read = [note for note in notes(reading.musicxml)[0] if bar_limit is None or note.bar < bar_limit]
    return reading, compare(notes(truth_data, capo)[0], read, spelled and not capo)


@pytest.mark.parametrize("name", GENERATED)
def test_every_note_of_the_generated_tablature_is_read(name):
    reading, result = reading_against_truth(name, DATA / "tabs")
    for kind in ("wrong length", "wrong pitch", "wrong string or fret", "wrong onset", "missed", "extra"):
        assert result[kind] == [], kind
    assert len(result["wrong tie"]) <= 1


def test_printed_tuning_and_capo_are_used():
    drop_d = read_tab((DATA / "tabs/bwv245-40-drop-d.pdf").read_bytes())
    assert (drop_d.tuning[-1], drop_d.tuning_from) == ("D2", "page")
    capo = read_tab((DATA / "tabs/bwv336-capo.pdf").read_bytes())
    assert (capo.capo, capo.tuning_from) == (2, "standard")
    bass = read_tab((DATA / "tabs/bwv418-bass.pdf").read_bytes())
    assert bass.tuning == ["G2", "D2", "A1", "E1"]


@pytest.mark.parametrize("name", ["chopin-28-4-mutopia.pdf", "mozart-k545-1-scan.pdf"])
def test_a_pdf_without_typed_tablature_is_refused(name):
    assert read_tab((DATA / name).read_bytes()) is None


@pytest.mark.parametrize("name, bars, wrong_lengths", [("weird-tab-only-musescore", 58, 0), ("weiss-allemande-tab-only", 32, 1)])
def test_users_tablature_reads_like_the_page(name, bars, wrong_lengths):
    reading, result = reading_against_truth(name, USERS)
    assert len(result["found"]) == len(notes(truth_of(USERS / f"{name}.pdf")[0])[0])
    assert len(result["wrong length"]) <= wrong_lengths
    assert notes(reading.musicxml)[1] == bars


@pytest.mark.parametrize("path, reason", [("hand/h4-no-rhythm", NO_RHYTHM), ("d4-duet", MORE_THAN_ONE_STAFF),
                                          ("round2/r4-guitar-and-bass", MORE_THAN_ONE_STAFF),
                                          ("round2/r4-joined-tabs", MORE_THAN_ONE_STAFF),
                                          ("round2/hand/h5-second-tab-hidden", MORE_THAN_ONE_STAFF)])
def test_tablature_outside_the_scope_is_refused_with_its_reason(path, reason):
    with pytest.raises(OutsideScope) as refused:
        read_tab((DATA / "tabs/review" / f"{path}.pdf").read_bytes())
    assert str(refused.value) == reason


@pytest.mark.parametrize("pdf", [*(path for path in sorted((DATA / "tabs").glob("*.pdf")) if path.stem not in BESIDE_A_STAFF),
                                 *(USERS / f"{name}.pdf" for name in ("weird-tab-only-musescore", "weiss-allemande-tab-only"))],
                         ids=lambda path: path.stem)
def test_every_sign_the_accidental_rule_wants_is_drawn(pdf):
    if not pdf.exists():
        pytest.skip(f"{pdf} is a user's file kept out of the repository")
    score = read_tab(pdf.read_bytes()).musicxml
    root = ET.fromstring(score)
    fifths = int(root.findtext(".//key/fifths"))
    wanted = {}
    for bar in root.iter("measure"):
        bare = copy.deepcopy(bar)
        for note in bare.findall("note"):
            if note.findtext("staff") == "2":
                bare.remove(note)
        for note in bare.iter("note"):
            for sign in note.findall("accidental"):
                note.remove(sign)
        correct._write_accidentals(bare, fifths)
        wanted[bar.get("number")] = len(bare.findall(".//accidental"))
    mei = ET.fromstring(load_toolkit(score).getMEI())
    drawn = {bar.get("n"): sum(1 for accid in bar.iter(f"{MEI}accid") if accid.get("accid"))
             for bar in mei.iter(f"{MEI}measure")}
    assert {number: count for number, count in wanted.items() if count != drawn.get(number, 0)} == {}


def test_notes_joined_by_a_printed_beam_are_beamed_together():
    root = ET.fromstring(read_tab((DATA / "tabs/romanza.pdf").read_bytes()).musicxml)
    for bar in root.iter("measure"):
        marks = [beam.text for note in bar.iter("note") if note.findtext("staff") == "1"
                 for beam in note.iter("beam") if beam.get("number") == "1"]
        assert marks == ["begin", "continue", "end"] * 3, bar.get("number")


@pytest.mark.parametrize("name", ["romanza", "bwv386-chords", "greensleeves"])
def test_a_tablature_reading_is_drawn_as_a_staff_with_its_tablature_under_it_and_each_note_counted_once(name):
    reading = read_tab((DATA / f"tabs/{name}.pdf").read_bytes())
    mei = load_toolkit(reading.musicxml).getMEI()
    assert len(re.findall(r"<staffDef\b", mei)) == 2 and len(re.findall(r'<staffDef\b[^>]*notationtype="tab', mei)) == 1
    index = ScoreIndex(mei)
    assert sum(1 for bar in index.measures for event in bar.events if event.pitch) == reading.notes
    assert problem_spots(reading.musicxml)[0] == []


def test_tablature_beside_a_five_line_staff_is_left_to_the_staff_reader():
    assert read_tab((DATA / "tabs/greensleeves-staff-and-tab.pdf").read_bytes()) is None
    assert read_tab((DATA / "tabs/greensleeves.pdf").read_bytes()) is not None


REVIEW = DATA / "tabs/review"


@pytest.mark.parametrize("name", ["g1-table-3-rules", "g2-table-5-rules", "g3-table-6-rules", "g4-table-text-and-numbers",
                                  "g5-ascii-tab", "x1-empty", "x2-not-a-pdf", "x3-truncated", "x4-no-pages", "x5-blank-page",
                                  "x6-encrypted-user-password"])
def test_a_ruled_table_or_a_broken_pdf_is_not_tablature(name):
    assert read_tab((REVIEW / "hand" / f"{name}.pdf").read_bytes()) is None


@pytest.mark.parametrize("name, bars", [("b13-rest-bar", 8), ("b16-mostly-halves", 8)])
def test_a_short_last_line_of_tablature_is_read(name, bars):
    assert notes(read_tab((REVIEW / f"{name}.pdf").read_bytes()).musicxml)[1] == bars


@pytest.mark.parametrize("path, tuning, source, capo", [
    ("f5-drop-c", ["E4", "B3", "G3", "D3", "A2", "E2"], "standard", 0),
    ("hand/h8-tuning-words", ["Eb4", "Bb3", "Gb3", "Db3", "Ab2", "Eb2"], "page", 0),
    ("f6-eb-standard-words", ["E4", "B3", "G3", "D3", "A2", "E2"], "standard", 0),
    ("d3-ukulele", ["G2", "D2", "A1", "E1"], "standard", 0),
    ("round2/hand/t01-tuning-dadgad", ["D4", "A3", "G3", "D3", "A2", "D2"], "page", 0),
    ("round2/hand/t09-capo-II", ["E4", "B3", "G3", "D3", "A2", "E2"], "standard", 2),
    ("round2/hand/t11-standard-capo-4", ["E4", "B3", "G3", "D3", "A2", "E2"], "standard", 0),
    ("round2/hand/t16-beat-drop-A", ["E4", "B3", "G3", "D3", "A2", "E2"], "standard", 0),
    ("hand/h5-da-capo-words", ["E4", "B3", "G3", "D3", "A2", "E2"], "standard", 0),
    ("hand/h7-drop-a-story", ["E4", "B3", "G3", "D3", "A2", "E2"], "standard", 0),
])
def test_a_tuning_comes_only_from_a_tuning_line_and_a_capo_only_from_a_capo_line(path, tuning, source, capo):
    reading = read_tab((REVIEW / f"{path}.pdf").read_bytes())
    assert (reading.tuning, reading.tuning_from, reading.capo) == (tuning, source, capo)


DRAWN_ALIKE = {"b14-two-voices": [1], "m1-mixed-piece": [3, 6, 27, 30], "r3-quarter-triplets": [4]}


@pytest.mark.parametrize("pdf", [pdf for folder in FOLDERS for pdf in sorted(folder.glob("*.pdf"))
                                 if truth_of(pdf) is not None], ids=lambda path: path.stem)
def test_no_bar_of_tablature_is_read_wrong_without_being_shaded(pdf):
    row = measure(pdf, False)
    assert row.get("silent wrong bars", []) == DRAWN_ALIKE.get(pdf.stem, [])


@pytest.mark.parametrize("path, bars", [("f1-grace-notes", [1]), ("f3-harmonics", [1, 2]), ("hand/h2-dead-and-hammer", [1, 2]),
                                        ("hand/h3-ghost-notes", [2]), ("b13-rest-bar", [])])
def test_a_sign_on_the_strings_that_is_not_read_marks_its_bar(path, bars):
    reading = read_tab((REVIEW / f"{path}.pdf").read_bytes())
    assert reading.unread == bars and set(bars) <= set(reading.doubtful)


def test_a_bracketed_fret_is_tied_only_to_the_note_just_before_it():
    root = ET.fromstring(read_tab((REVIEW / "hand/h3-ghost-notes.pdf").read_bytes()).musicxml)
    assert list(root.iter("tied")) == []


def test_the_downloaded_analysis_puts_its_labels_on_the_staff_not_on_the_tablature():
    reading = read_tab((DATA / "tabs/greensleeves.pdf").read_bytes())
    analysis = {"annotations": [{"type": "harmony", "at": {"measure": 1, "beat": 1}, "key": "a", "label": "i"},
                                {"type": "harmony", "at": {"measure": 1, "beat": 2.5}, "label": "V"}]}
    root = ET.fromstring(export_musicxml(reading.musicxml, analysis))
    labelled = [note.findtext("staff") for note in root.iter("note") if note.find("lyric") is not None]
    placed = [direction.findtext("staff") for direction in root.iter("direction") if direction.find("direction-type/words") is not None]
    assert labelled + placed and set(labelled + placed) == {"1"}
