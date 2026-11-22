import re
from pathlib import Path

import pytest

from engine import comparison, harmony

PAIRS = [tuple(line.split("\t")) for line in (Path(__file__).parent / "data" / "label_pairs_in_use.tsv").read_text().splitlines()]
EXTENSION = re.compile(r"(9|11|13)(?=/|$)")
FLAT_THIRD_IN_MINOR = re.compile(r"b[iI]{3}(?![iIvV])")


def intended_difference(key: str, label: str) -> str | None:
    if EXTENSION.search(label.replace("/o", "ø").split("/")[0] + "/"):
        return "the engine reader drops 9ths, 11ths and 13ths"
    if key[0].islower() and FLAT_THIRD_IN_MINOR.match(label):
        return "music21 flattens the natural-minor third again, the engine reader flattens the major one"
    return None


def readings(key: str, label: str):
    ours, theirs = harmony.chord(key, label), comparison.sounding(key, label)
    return (ours.tones, ours.bass), (theirs.tones, theirs.bass) if theirs else None


@pytest.mark.parametrize("key, label", PAIRS)
def test_both_readers_agree_outside_the_intended_differences(key, label):
    ours, theirs = readings(key, label)
    assert theirs is not None
    if ours != theirs:
        assert intended_difference(key, label), f"{key}: {label}"
