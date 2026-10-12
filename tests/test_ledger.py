"""The draft tells the model about long ledger-line runs; the clef itself is never changed."""

import os
import subprocess
import sys
from pathlib import Path

from conftest import ROOT

# A real scan reading: the left hand sits high above the bass staff in bars 42-45 and 58-62.
K545 = ROOT / "tests/data/mozart-k545-1-scan-reading.musicxml"


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


def test_a_bass_clef_string_part_is_named_by_its_part_and_offered_tenor_clef():
    # A real quartet reading: the lowest staff climbs above its bass staff in bars 7-10; it has no hands.
    quartet = ROOT / "tests/data/mozart-quartet-k155-reading.musicxml"
    result = subprocess.run([sys.executable, str(ROOT / "skill/scripts/notes_table.py"), str(quartet), "--measures", "1-12"],
                            capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(ROOT)})
    assert result.returncode == 0, result.stderr
    assert "Bars 7–10, Voice (staff 4): notes sit high above the bass staff; many editions switch to tenor or treble clef here." in result.stdout
    assert "hand" not in result.stdout.split("LEDGER LINES")[1]
