import json
import re
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


def test_the_plugin_reads_no_value_from_the_users_environment(skill):
    reads = [f"{path.relative_to(skill)}:{number}" for path in skill.rglob("*.py")
             for number, line in enumerate(path.read_text().splitlines(), 1)
             if re.search(r"\benvironb?\b|getenv", line) and "os.environ.setdefault" not in line]
    assert not reads


def test_the_marketplace_lists_the_built_plugin_under_its_own_name_and_version():
    marketplace = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
    [entry] = marketplace["plugins"]
    manifest = json.loads((ROOT / entry["source"] / ".claude-plugin" / "plugin.json").read_text())
    assert entry["name"] == manifest["name"]
    assert "version" not in entry
