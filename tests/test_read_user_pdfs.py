import collections
import functools
import os
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from engine.read_pdf import read_pdf

AUDIVERIS = os.environ.get("AUDIVERIS", "/opt/audiveris/bin/Audiveris")
USERS = Path(__file__).parent / "data" / "users"


@functools.cache
def reading(name: str) -> ET.Element:
    path = USERS / name
    if not os.path.exists(AUDIVERIS):
        pytest.skip("Audiveris is not installed; set AUDIVERIS")
    if not path.exists():
        pytest.skip(f"{path} is a user's file kept out of the repository")
    return ET.fromstring(read_pdf(path.read_bytes(), AUDIVERIS).musicxml)


def test_snare_rolls_are_read_as_rolls_not_triplets():
    root = reading("radetzky-snare-part.pdf")
    first = root.find("part/measure")
    assert first.get("number") == "1" and first.get("implicit") != "yes"
    assert sum(1 for _ in root.iter("tremolo")) >= 10
    assert root.find(".//time-modification") is None


def test_guitar_fingering_is_not_read_as_a_dot_or_a_dynamic():
    root = reading("padrino-classical-guitar.pdf")
    bar = next(measure for measure in root.iter("measure") if measure.get("number") == "11")
    assert bar.find(".//time-modification") is None
    assert root.find(".//dynamics/ff") is None


def test_thin_tab_beams_are_found():
    root = reading("bond-theme-guitar-tab.pdf")
    types = collections.Counter(note.findtext("type") for note in root.iter("note"))
    assert types["eighth"] + types["16th"] > types["quarter"]
