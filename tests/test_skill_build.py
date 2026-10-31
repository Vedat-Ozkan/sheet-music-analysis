import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tools.build_skill import ENGINE_SKIP

ROOT = Path(__file__).parent.parent
SCRIPTS = sorted(path.name for path in (ROOT / "skill" / "scripts").glob("*.py"))


@pytest.fixture(scope="module")
def skill(tmp_path_factory):
    scripts = tmp_path_factory.mktemp("skill") / "scripts"
    shutil.copytree(ROOT / "skill" / "scripts", scripts)
    shutil.copytree(ROOT / "engine", scripts / "engine", ignore=lambda _, names: ENGINE_SKIP & set(names))
    return scripts


@pytest.mark.parametrize("script", SCRIPTS)
def test_every_skill_script_starts_without_the_server_only_engine_files(skill, script):
    run = subprocess.run([sys.executable, script, "--help"], cwd=skill, capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
