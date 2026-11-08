import json
from pathlib import Path

from tools.build_skill import NAME, disallowed

ROOT = Path(__file__).parent.parent


def test_the_built_plugin_ships_only_file_types_claudes_directory_accepts():
    assert disallowed(ROOT / "dist" / NAME) == []


def test_a_script_in_the_plugin_is_refused(tmp_path):
    (tmp_path / "skills").mkdir()
    (tmp_path / "skills" / "run.py").write_text("")
    (tmp_path / "LICENSE").write_text("")
    (tmp_path / "SKILL.md").write_text("")
    assert disallowed(tmp_path) == ["LICENSE", "skills/run.py"]


def test_the_marketplace_lists_the_built_plugin_under_its_own_name_and_version():
    marketplace = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
    [entry] = marketplace["plugins"]
    manifest = json.loads((ROOT / entry["source"] / ".claude-plugin" / "plugin.json").read_text())
    assert entry["name"] == manifest["name"]
    assert "version" not in entry
