import io
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest

from engine import check_analysis, correct, draft, ledger
from engine.performance import marked_index, perform
from engine.read_pdf import clean
from engine.render import load_toolkit
from engine.score import ScoreIndex

DATA = Path(__file__).parent / "data"


def score(*bars: str, divisions: int = 1) -> bytes:
    opening = f"<attributes><divisions>{divisions}</divisions><time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>G</sign><line>2</line></clef></attributes>"
    measures = "".join(f'<measure number="{n}">{opening if n == 1 else ""}{bar}</measure>' for n, bar in enumerate(bars, 1))
    return f'<score-partwise version="4.0"><part-list><score-part id="P1"><part-name>Piano</part-name></score-part></part-list><part id="P1">{measures}</part></score-partwise>'.encode()


def note(step: str, octave: int, length: int = 1, voice: int = 1, tie: str = "", lyric: str = "") -> str:
    ties = f'<tie type="{tie}"/>' if tie else ""
    tied = f'<notations><tied type="{tie}"/></notations>' if tie else ""
    words = f"<lyric><text>{lyric}</text></lyric>" if lyric else ""
    kind = {1: "quarter", 2: "half", 4: "whole"}[length]
    return f"<note><pitch><step>{step}</step><octave>{octave}</octave></pitch><duration>{length}</duration>{ties}<voice>{voice}</voice><type>{kind}</type>{tied}{words}</note>"


@pytest.mark.parametrize("name, runs", [
    ("pdf_warnings/haydn_she_never_told_audiveris.musicxml", [(2, 3, 3, "below", "bass"), (37, 39, 3, "below", "bass")]),
    ("pdf_warnings/schubert_die_stadt_ly_raw.mxl", []),
])
def test_a_clef_written_at_the_end_of_a_bar_does_not_change_the_notes_before_it(name, runs):
    mei = load_toolkit((DATA / name).read_bytes()).getMEI()
    assert ledger.passages(mei, ScoreIndex(mei)) == runs


def test_a_key_change_inside_a_bar_applies_only_to_the_labels_after_it():
    change = "<attributes><key><fifths>1</fifths><mode>major</mode></key></attributes>"
    data = score(note("C", 4, 2, lyric="I") + change + note("D", 4, 2, lyric="V"))
    labels = check_analysis.from_musicxml(data, default_key="C")
    assert [label.key for label in labels] == ["C", "G"]


UNISON_BAR = note("C", 5, 4, 1, "start") + "<backup><duration>4</duration></backup>" + note("C", 5, 4, 2, "start")
UNISON_NEXT = note("C", 5, 4, 1, "stop") + "<backup><duration>4</duration></backup>" + note("C", 5, 4, 2, "stop")


def test_two_voices_tied_on_one_pitch_each_keep_their_tie_when_played():
    notes, _, _ = perform(marked_index(score(UNISON_BAR, UNISON_NEXT)))
    assert len(notes) == 2
    assert notes[0].end == notes[1].end


def tie_starts_in_first_bar(data: bytes) -> int:
    bar = ET.fromstring(data).find("part/measure")
    return sum(mark.get("type") == "start" for note_ in bar.findall("note") for mark in note_.findall("tie"))


def test_replacing_the_bar_after_a_unison_removes_both_loose_ties():
    original = score(UNISON_BAR, UNISON_NEXT)
    corrected = correct.bars_from_musicxml(original, 2).replace("C5", "D5")
    assert tie_starts_in_first_bar(correct.replace_bars(original, corrected)) == 0


def test_a_tie_in_one_voice_survives_the_same_pitch_in_another_voice():
    notes, _, _ = perform(marked_index((DATA / "chopin_ballade_op23_pdmx.mxl").read_bytes()))
    assert [(round(note.start), round(note.end)) for note in notes if note.pitch == 70 and abs(note.start - 17009.524) < 1] == [(17010, 21914)]


def test_replacing_the_bar_after_a_unison_keeps_ties_that_still_land():
    original = score(UNISON_BAR, UNISON_NEXT)
    same = correct.bars_from_musicxml(original, 2)
    assert tie_starts_in_first_bar(correct.replace_bars(original, same)) == 2


def shift(kind: str) -> str:
    return f'<direction><direction-type><octave-shift type="{kind}" size="8" number="1"/></direction-type></direction>'


def test_an_octave_line_that_continues_keeps_its_start():
    data = score(shift("down") + note("C", 4, 4), shift("continue") + note("C", 4, 4), shift("stop") + note("C", 4, 4))
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as file:
        file.writestr("score.xml", data)
    kinds = [mark.get("type") for mark in ET.fromstring(clean(archive.getvalue())).iter("octave-shift")]
    assert kinds == ["down", "continue", "stop"]


@pytest.fixture
def worker(monkeypatch, tmp_path):
    def using(script: str) -> draft._Worker:
        runner = tmp_path / "runner.sh"
        runner.write_text("#!/bin/sh\n" + script)
        runner.chmod(0o755)
        monkeypatch.setattr(draft, "ANALYSISGNN_PYTHON", str(runner))
        return draft._Worker()

    return using


def test_a_worker_that_dies_mid_request_is_not_reported_as_slow(worker, tmp_path):
    running = worker("echo ready\nread line\nexit 1\n")
    with pytest.raises(draft.DraftError, match="stopped"):
        running.run(tmp_path / "in", tmp_path / "out")
    assert running.process is None


def test_a_worker_that_dies_before_the_request_arrives_is_a_draft_error(worker, tmp_path):
    running = worker("exec 0<&-\necho ready\nsleep 5\n")
    with pytest.raises(draft.DraftError, match="stopped"):
        running.run(tmp_path / "in", tmp_path / "out")
    assert running.process is None


def test_a_worker_that_is_only_slow_is_reported_as_slow(worker, tmp_path, monkeypatch):
    running = worker("echo ready\nsleep 5\n")
    real = running._reply
    monkeypatch.setattr(running, "_reply", lambda timeout: real(min(timeout, 0.2)) if timeout == 180 else real(timeout))
    with pytest.raises(draft.DraftError, match="in time"):
        running.run(tmp_path / "in", tmp_path / "out")
