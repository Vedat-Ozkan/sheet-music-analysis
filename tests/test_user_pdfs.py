import os
import xml.etree.ElementTree as ET
from pathlib import Path

import anyio
import pytest
from mcp.client.client import Client

from engine import read_pdf as pdf_reader
from server import app

AUDIVERIS = os.environ.get("AUDIVERIS", "/opt/audiveris/bin/Audiveris")
USERS = Path(__file__).parent / "data" / "users"
PARRY = Path(__file__).parent / "data" / "parry-who-can-dwell-false-movement-scan.pdf"
ATTACHED = {"pdf_file": {"download_url": "https://example.com/score.pdf", "file_id": "file-1"}}
READINGS = {}


def reading(name: str) -> pdf_reader.PdfReading:
    path = USERS / name
    if not path.exists():
        pytest.skip(f"{path} is kept only on the owner's machines")
    if not os.path.exists(AUDIVERIS):
        pytest.skip("Audiveris is not installed; set AUDIVERIS")
    if name not in READINGS:
        READINGS[name] = pdf_reader.read_pdf(path.read_bytes(), AUDIVERIS)
    return READINGS[name]


def part_names(score: bytes) -> list[str]:
    return [part.findtext("part-name") for part in ET.fromstring(score).iter("score-part")]


def test_a_bar_the_reader_left_empty_is_shaded():
    score = reading("padrino-classical-guitar.pdf").musicxml
    assert 21 in pdf_reader.problem_spots(score)[0]


def test_guitar_fingering_letters_are_not_read_as_dynamics_or_words():
    root = ET.fromstring(reading("padrino-classical-guitar.pdf").musicxml)
    assert list(root.iter("dynamics")) == []
    assert [words.text for words in root.iter("words")] == ["atempo"]
    assert list(root.iter("fingering")) == [] and list(root.iter("pluck")) == []


def test_an_unlabelled_part_has_no_name_and_a_heading_instrument_names_it():
    assert part_names(reading("padrino-classical-guitar.pdf").musicxml) == [""]
    assert part_names(reading("radetzky-snare-part.pdf").musicxml) == ["Snare Drum"]


def test_tab_staves_with_no_notes_are_left_out():
    root = ET.fromstring(reading("bond-theme-guitar-tab.pdf").musicxml)
    parts = root.findall("part")
    assert len(parts) == 2 and part_names(ET.tostring(root)) == ["", ""]
    assert all(any(note.find("rest") is None for note in part.iter("note")) for part in parts)


def test_a_mostly_doubtful_reading_opens_the_reply_with_a_warning(monkeypatch, tmp_path):
    if not os.path.exists(AUDIVERIS):
        pytest.skip("Audiveris is not installed; set AUDIVERIS")
    scan = PARRY.read_bytes()
    parry = pdf_reader.read_pdf(scan, AUDIVERIS)

    async def download(url):
        return scan

    monkeypatch.setattr(app, "store", app.LocalStore(tmp_path))
    monkeypatch.setattr(app, "download", download)
    monkeypatch.setattr(app.pdf_reader, "read_pdf", lambda data: parry)

    async def call():
        async with Client(app.mcp) as client:
            return await client.call_tool("read_pdf", ATTACHED)

    result = anyio.run(call)
    text = " ".join(part.text for part in result.content if part.type == "text")
    shaded = len(result.structured_content["shaded_bars"])
    assert f'Warning for the user: "Much of this reading is doubtful: {shaded} of its 16 bars' in text
    assert text.index("Much of this reading is doubtful") < text.index("Note for the user about the reading")
