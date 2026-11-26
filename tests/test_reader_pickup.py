import asyncio
import gzip
import json
import re
from pathlib import Path

import pytest

from engine import notes
from engine.read_pdf import problem_spots, without_slurs
from engine.render import load_toolkit, musicxml_file, written_by_the_pdf_reader
from engine.score import ScoreIndex
from server import app
from tests.test_bar_names import ATTRIBUTES, note, score

DATA = Path(__file__).parent / "data"
MARKED = (DATA / "chopin_prelude_op28_no4_reading.musicxml").read_bytes()


def unmarked(reading: bytes) -> bytes:
    text = reading.decode().replace('<measure number="0" implicit="yes"', '<measure number="0"')
    return re.sub(r'<measure number="(\d+)"', lambda m: f'<measure number="{int(m.group(1)) + 1}"', text).encode()


MISSED = unmarked(MARKED)


def musicxml(path: Path) -> bytes:
    data = path.read_bytes()
    return musicxml_file(gzip.decompress(data) if path.suffix == ".gz" else data)


READINGS = [path for path in sorted(DATA.rglob("*")) if path.name.endswith((".musicxml", ".mxl", ".musicxml.gz"))
            and "verovio-crashes" not in path.parts and written_by_the_pdf_reader(musicxml(path).decode("utf-8", "replace"))]


def first_bar(musicxml: bytes) -> tuple[int, str, bool, bool]:
    index = ScoreIndex(load_toolkit(musicxml).getMEI())
    first = index.measures[0]
    return first.number, first.name, first.is_pickup, first.number in problem_spots(musicxml)[0]


def test_a_pickup_the_reader_marked_is_bar_0_and_not_doubtful():
    assert first_bar(MARKED) == (0, "0", True, False)


def test_a_short_bar_1_the_reader_did_not_mark_stays_bar_1_and_is_doubtful():
    assert written_by_the_pdf_reader(MISSED.decode())
    assert first_bar(MISSED) == (1, "1", False, True)


def test_the_same_bar_in_an_uploaded_file_is_still_taken_for_a_pickup():
    upload = MISSED.replace(b"<software>Audiveris", b"<software>Other")
    assert first_bar(upload)[:3] == (0, "0", True)


def test_a_reading_without_slurs_is_still_a_reading():
    assert first_bar(without_slurs(MISSED)) == (1, "1", False, True)


def correct_bars(score_id: str, bars: str):
    return asyncio.run(app.mcp.call_tool("correct_bars", {"score_id": score_id, "replacement_bars": "N1 div=24 ts=2/2 ks=1s\n" + bars}))


def corrected(result) -> tuple[bytes, list[int], str]:
    assert not result.is_error, result.content[0].text
    code = result.structured_content["score_id"]
    return app.store.get(f"scores/{code}"), json.loads(app.store.get(app.shaded_key(code))), code


@pytest.fixture
def stored(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "store", app.LocalStore(tmp_path))
    app.store.put("scores/MISSED", MISSED)
    app.store.put(app.shaded_key("MISSED"), json.dumps(problem_spots(MISSED)[0]).encode())
    return "MISSED"


def test_correcting_another_bar_keeps_bar_1_numbered_1_and_shaded(stored):
    after, shaded, _ = corrected(correct_bars(stored, "m5 len=96\n1.1: 72 B4 24 A4\n2.5: 12 E3+G#3+D4 E3+G#3+D4 E3+G#3+D4 E3+G#3+D4 E3+G3+D4 E3+G3+D4 E3+G3+C#4 E3+G3+C#4"))
    assert written_by_the_pdf_reader(after.decode())
    assert first_bar(after) == (1, "1", False, True)
    assert 1 in shaded


def test_bar_1_corrected_to_a_whole_bar_stays_bar_1_and_is_no_longer_shaded(stored):
    after, shaded, _ = corrected(correct_bars(stored, "m1 len=96\n1.1: 72 r 18 B3 6 B4\n2.1: 96 r"))
    assert first_bar(after) == (1, "1", False, False)
    assert 1 not in shaded


def test_bar_1_cannot_be_corrected_to_a_short_bar(stored):
    result = correct_bars(stored, "m1 len=24\n1.1: 18 B3 6 B4\n2.1: 24 r")
    assert result.is_error
    assert "expected 4 quarter notes" in result.content[0].text


def test_a_pickup_the_file_numbers_1_before_a_whole_bar_numbered_1_is_bar_0():
    pickup = score([("1", ATTRIBUTES + note("G", 1, "quarter")), ("1", note("C")), ("2", note("D"))])
    pickup = pickup.replace(b'<measure number="1">', b'<measure number="1" implicit="yes">', 1)
    index = ScoreIndex(load_toolkit(pickup).getMEI())
    assert [(m.number, m.name) for m in index.measures] == [(0, "0"), (1, "1"), (2, "2")]
    listed = [line.split()[0] for line in notes.encode(index, *index.numbers(("1", "2"))).splitlines() if line.startswith("m")]
    assert listed == ["m0", "m1", "m2"]


@pytest.mark.parametrize("path", READINGS, ids=lambda path: path.name)
def test_every_reading_in_the_test_data_is_numbered_from_the_readers_own_pickup_mark(path):
    score = musicxml(path)
    marked = 'implicit="yes"' in re.search(r"<measure\s[^>]*>", score.decode("utf-8", "replace")).group(0)
    first = ScoreIndex(load_toolkit(score).getMEI()).measures[0]
    assert first.is_pickup == marked and (first.number == 0) == marked
    if not marked and first.is_short:
        assert first.number in problem_spots(score)[0]


@pytest.mark.parametrize("software", ["Audiveris 5.6", "Other"])
def test_a_score_with_no_bars_loads_with_no_bars(software):
    empty = (f'<?xml version="1.0" encoding="UTF-8"?><score-partwise version="4.0"><identification><encoding>'
             f'<software>{software}</software></encoding></identification><part-list><score-part id="P1">'
             '<part-name>P</part-name></score-part></part-list><part id="P1"></part></score-partwise>').encode()
    assert ScoreIndex(load_toolkit(empty).getMEI()).measures == []
    assert problem_spots(empty)[0] == []
