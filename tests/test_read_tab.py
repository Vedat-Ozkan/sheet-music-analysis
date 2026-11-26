from pathlib import Path

import pytest

from engine.read_tab import read_tab
from tests.data.tabs.measure import USERS, compare, notes, truth_of

DATA = Path(__file__).parent / "data"
GENERATED = sorted(path.stem for path in (DATA / "tabs").glob("*.musicxml"))


def reading_against_truth(name: str, folder: Path):
    pdf = folder / f"{name}.pdf"
    if not pdf.exists():
        pytest.skip(f"{pdf} is a user's file kept out of the repository")
    truth_data, capo, bar_limit = truth_of(name)
    reading = read_tab(pdf.read_bytes())
    read = [note for note in notes(reading.musicxml)[0] if bar_limit is None or note.bar < bar_limit]
    return reading, compare(notes(truth_data, capo)[0], read, not capo)


@pytest.mark.parametrize("name", GENERATED)
def test_every_note_of_the_generated_tablature_is_read(name):
    reading, result = reading_against_truth(name, DATA / "tabs")
    for kind in ("wrong length", "wrong pitch", "wrong string or fret", "wrong onset", "missed", "extra"):
        assert result[kind] == [], kind
    assert len(result["wrong tie"]) <= 1
    assert reading.doubtful == []


def test_printed_tuning_and_capo_are_used():
    drop_d = read_tab((DATA / "tabs/bwv245-40-drop-d.pdf").read_bytes())
    assert (drop_d.tuning[-1], drop_d.tuning_printed) == ("D2", True)
    capo = read_tab((DATA / "tabs/bwv336-capo.pdf").read_bytes())
    assert (capo.capo, capo.tuning_printed) == (2, False)
    bass = read_tab((DATA / "tabs/bwv418-bass.pdf").read_bytes())
    assert bass.tuning == ["G2", "D2", "A1", "E1"]


@pytest.mark.parametrize("name", ["chopin-28-4-mutopia.pdf", "mozart-k545-1-scan.pdf"])
def test_a_pdf_without_typed_tablature_is_refused(name):
    assert read_tab((DATA / name).read_bytes()) is None


@pytest.mark.parametrize("name, bars, wrong_lengths", [("weird-tab-only-musescore", 58, 0), ("weiss-allemande-tab-only", 32, 1)])
def test_users_tablature_reads_like_the_page(name, bars, wrong_lengths):
    reading, result = reading_against_truth(name, USERS)
    assert len(result["found"]) == len(notes(truth_of(name)[0])[0])
    assert len(result["wrong length"]) <= wrong_lengths
    assert notes(reading.musicxml)[1] == bars


def test_tablature_without_rhythm_marks_its_bars_as_doubtful():
    pdf = USERS / "bond-theme-guitar-tab.pdf"
    if not pdf.exists():
        pytest.skip(f"{pdf} is a user's file kept out of the repository")
    assert 1 in read_tab(pdf.read_bytes()).doubtful
