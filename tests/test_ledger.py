"""The draft tells the model about long ledger-line runs; the clef itself is never changed."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import MAIN, ROOT

# A real scan reading: the left hand sits high above the bass staff in bars 42-45 and 58-62.
K545 = MAIN / "spike/omr/bench/cache/runs/results-final--mozart-k545-1--scan.musicxml"
pytestmark = pytest.mark.skipif(not K545.exists(), reason="the benchmark reading is not in this checkout")


def test_notes_table_mentions_the_ledger_runs_of_a_real_reading():
    result = subprocess.run([sys.executable, str(ROOT / "skill/scripts/notes_table.py"), str(K545), "--measures", "38-62"],
                            capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(ROOT)})
    assert result.returncode == 0, result.stderr
    assert "Bars 42–45, left hand: notes sit high above the bass staff; many editions switch to treble clef here." in result.stdout
    assert "Bars 58–62, left hand: notes sit high above the bass staff" in result.stdout
    assert result.stdout.count("many editions switch") == 2


def test_a_range_without_long_runs_adds_nothing():
    result = subprocess.run([sys.executable, str(ROOT / "skill/scripts/notes_table.py"), str(K545), "--measures", "1-30"],
                            capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(ROOT)})
    assert result.returncode == 0, result.stderr
    assert "LEDGER LINES" not in result.stdout
