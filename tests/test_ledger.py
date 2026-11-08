from engine import ledger
from engine.render import load_toolkit
from engine.score import ScoreIndex

from conftest import ROOT

K545 = ROOT / "tests/data/mozart-k545-1-simulated-scan-reading.musicxml"


def ledger_text(score, first, last):
    mei = load_toolkit(score.read_bytes()).getMEI()
    return ledger.as_text(mei, ScoreIndex(mei), first, last)


def test_the_ledger_runs_of_a_real_reading_are_named():
    text = ledger_text(K545, 38, 62)
    assert "Bars 42–45, left hand: notes sit high above the bass staff; many editions switch to treble clef here." in text
    assert "Bars 58–62, left hand: notes sit high above the bass staff" in text
    assert text.count("many editions switch") == 2


def test_a_range_without_long_runs_adds_nothing():
    text = ledger_text(K545, 1, 30)
    assert "LEDGER LINES" not in text


def test_a_bass_clef_string_part_is_named_by_its_part_and_offered_tenor_clef():
    quartet = ROOT / "tests/data/mozart-quartet-k155-reading.musicxml"
    text = ledger_text(quartet, 1, 12)
    assert "Bars 7–10, Voice (staff 4): notes sit high above the bass staff; many editions switch to tenor or treble clef here." in text
    assert "hand" not in text.split("LEDGER LINES")[1]


def test_a_run_above_the_treble_staff_is_offered_an_octave_sign_not_a_clef():
    nocturne = ROOT / "tests/data/chopin_nocturne_op9_no2.mxl"
    text = ledger_text(nocturne, 28, 36)
    assert "Bars 31–35, right hand: notes sit high above the treble staff; many editions write them an octave lower under an 8va sign here." in text


def test_transposing_parts_are_judged_by_their_written_notes():
    symphony = ROOT / "tests/data/piano/mozart-41.mxl"
    text = ledger_text(symphony, 1, 30)
    ledger = text.split("LEDGER LINES")[1]
    assert "Contrabasses" not in ledger and "Horn II in C" not in ledger
    assert "Bars 26–27, Bassoon I (staff 4): notes sit high above the bass staff" in ledger
