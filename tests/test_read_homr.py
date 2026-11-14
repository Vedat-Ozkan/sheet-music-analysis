import os
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

import pytest

from engine import read_homr
from engine.read_homr import reading_from_pages, regroup_voices
from engine.read_pdf import preview, problem_spots, without_slurs

HOMR = os.environ.get("HOMR", read_homr.HOMR)
PAGES = Path(__file__).parent / "data/homr"
SPLEEN = {1: (PAGES / "satie-spleen-scan-p1.musicxml").read_bytes(), 2: (PAGES / "satie-spleen-scan-p2.musicxml").read_bytes()}


def notes_in_time(measure: ET.Element) -> tuple[Counter, dict[str, list[tuple[int, int]]]]:
    found, voices, cursor, onset = Counter(), defaultdict(list), 0, 0
    for element in measure:
        length = int(element.findtext("duration") or 0)
        if element.tag == "backup":
            cursor -= length
        elif element.tag == "forward":
            cursor += length
        elif element.tag == "note" and element.find("grace") is None:
            if element.find("chord") is None:
                onset = cursor
                cursor += length
                voices[element.findtext("voice", "1")].append((onset, cursor))
            pitch = element.find("pitch")
            found[(element.findtext("staff", "1"), onset, length,
                   None if pitch is None else (pitch.findtext("step"), pitch.findtext("octave"), pitch.findtext("alter")))] += 1
    return found, voices


@pytest.mark.parametrize("page", sorted(PAGES.glob("*.musicxml")), ids=lambda path: path.name)
def test_regrouped_voices_keep_every_note_in_time_and_never_overlap(page):
    for measure in ET.fromstring(page.read_bytes()).iter("measure"):
        before, _ = notes_in_time(measure)
        regroup_voices(measure)
        after, voices = notes_in_time(measure)
        assert after == before, measure.get("number")
        for spans in voices.values():
            assert all(end <= start for (_, end), (start, _) in zip(spans, spans[1:])), measure.get("number")
        written = [element.findtext("voice", "1") if element.tag == "note" else None
                   for element in measure if element.tag in ("note", "backup")]
        runs = [voice for position, voice in enumerate(written) if voice and (position == 0 or written[position - 1] != voice)]
        assert len(runs) == len(set(runs)), measure.get("number")


def test_homr_pages_join_into_one_reading_drawn_like_ours():
    reading = reading_from_pages(SPLEEN, 2, True, [])
    score = without_slurs(reading.musicxml)
    parts = ET.fromstring(score).findall("part")
    assert [len(part.findall("measure")) for part in parts] == [10, 10]
    assert all(len({element.text for element in part.iter("divisions")}) == 1 for part in parts)
    assert preview(score, problem_spots(score)).page_count == 1


def test_a_page_with_no_music_is_reported_missing():
    empty = b"<score-partwise><part-list/></score-partwise>"
    reading = reading_from_pages({1: SPLEEN[1], 2: empty}, 2, True, [])
    assert reading.skipped == [2]


@pytest.mark.skipif(not os.path.exists(HOMR), reason="homr is not installed; set HOMR")
def test_homr_reads_a_real_scan():
    reading = read_homr.read_pdf((Path(__file__).parent / "data/pdf_warnings/kinkel_trennung_scan.pdf").read_bytes(), HOMR)
    assert reading.skipped == []
    assert [record["outcome"] for record in reading.passes] == ["done"] * reading.pages
    assert len(ET.fromstring(reading.musicxml).find("part").findall("measure")) > 10
