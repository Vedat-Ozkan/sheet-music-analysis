"""Assemble the sandbox skill: the SKILL.md and scripts from skill/, plus the engine they import.

    .venv/bin/python tools/build_skill.py

Writes out/sheet-music-analysis.zip (the skill alone) and out/sheet-music-analysis-plugin.zip (the skill plus
a pointer to the connector, whose address comes from CONNECTOR_URL or the running tunnel).
"""

import json
import os
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
NAME = "sheet-music-analysis"
# The draft model needs its own heavy environment and a server, so it stays out of the sandbox skill.
ENGINE_SKIP = {"draft.py", "models", "__pycache__"}


def main() -> None:
    target = ROOT / "out" / "skill" / NAME
    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(ROOT / "skill", target, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(ROOT / "engine", target / "scripts" / "engine", ignore=lambda _, names: ENGINE_SKIP & set(names))
    references = target / "references"
    references.mkdir(exist_ok=True)
    shutil.copy(ROOT / "docs" / "annotation-spec.md", references / "annotation-spec.md")
    shutil.copy(ROOT / "examples" / "chopin_op9_no2_m1-8.json", references / "example-annotations.json")

    archive = ROOT / "out" / f"{NAME}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(target.rglob("*")):
            if path.is_file():
                bundle.write(path, Path(NAME) / path.relative_to(target))
    files = [path for path in target.rglob("*") if path.is_file()]
    print(f"{archive}: {archive.stat().st_size // 1024} KB, {len(files)} files")
    build_plugin(target)


def build_plugin(skill: Path) -> None:
    """The plugin: the same skill plus a pointer to the connector, installed together."""
    url_file = ROOT / "out" / "tunnel.url"
    server = os.environ.get("CONNECTOR_URL") or (url_file.read_text().strip() + "/mcp" if url_file.exists() else None)
    if not server:
        print("No connector URL (set CONNECTOR_URL or start the tunnel); plugin not built")
        return
    target = ROOT / "out" / "plugin" / NAME
    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(ROOT / "plugin", target)
    shutil.copytree(skill, target / "skills" / NAME)
    (target / ".mcp.json").write_text(json.dumps({"mcpServers": {NAME: {"type": "http", "url": server}}}, indent=2) + "\n")
    archive = ROOT / "out" / f"{NAME}-plugin.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(target.rglob("*")):
            if path.is_file():
                bundle.write(path, Path(NAME) / path.relative_to(target))
    print(f"{archive}: {archive.stat().st_size // 1024} KB, connector {server}")


if __name__ == "__main__":
    main()
