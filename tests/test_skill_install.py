import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tools.build_skill import ENGINE_SKIP

ROOT = Path(__file__).parent.parent
SCORE = ROOT / "tests/data/chopin_prelude_op28_no4_reading.musicxml"
ANNOTATIONS = {"version": 1, "annotations": [
    {"type": "harmony", "at": {"measure": 1, "beat": 1}, "label": "i", "function": "T", "key": "Em"},
]}


@pytest.fixture(scope="module")
def skill(tmp_path_factory):
    if not shutil.which("uv"):
        pytest.skip("uv is not installed")
    base = tmp_path_factory.mktemp("install")
    environment = base / "venv"
    created = subprocess.run(["uv", "venv", "--python", "3.13", str(environment)], capture_output=True, text=True)
    if created.returncode:
        pytest.skip(f"Python 3.13 is not available to uv: {created.stderr.strip()}")
    packages = re.search(r"^\s*pip install (.+)$", (ROOT / "skill/SKILL.md").read_text(), re.MULTILINE).group(1)
    python = environment / "bin/python"
    installed = subprocess.run(["uv", "pip", "install", "--python", str(python), *packages.split()], capture_output=True, text=True)
    assert installed.returncode == 0, installed.stderr
    scripts = base / "scripts"
    shutil.copytree(ROOT / "skill/scripts", scripts)
    shutil.copytree(ROOT / "engine", scripts / "engine", ignore=lambda _, names: ENGINE_SKIP & set(names) | {"__pycache__"})
    (base / "annotations.json").write_text(json.dumps(ANNOTATIONS))
    return python, scripts, base


def run(skill, script, *arguments):
    python, scripts, _ = skill
    result = subprocess.run([str(python), script, *arguments], cwd=scripts, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return result


def test_notes_table_runs_after_the_documented_install(skill):
    assert run(skill, "notes_table.py", str(SCORE), "--measures", "1-4").stdout.strip()


def test_model_notes_runs_after_the_documented_install(skill):
    assert run(skill, "model_notes.py", str(SCORE), "--measures", "1-4").stdout.strip()


@pytest.mark.parametrize("piano", [False, True])
def test_render_analysis_draws_png_and_pdf_after_the_documented_install(skill, piano):
    _, _, base = skill
    out = base / ("piano" if piano else "plain")
    run(skill, "render_analysis.py", str(SCORE), str(base / "annotations.json"),
        "--out-dir", str(out), "--measures", "1-4", *(["--piano"] if piano else []))
    assert (out / "analysis.png").read_bytes().startswith(b"\x89PNG")
    assert (out / "analysis.pdf").read_bytes().startswith(b"%PDF")
