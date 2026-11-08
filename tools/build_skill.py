import json
import os
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
NAME = "sheet-music-analysis"
ALLOWED = {".md", ".txt", ".json", ".yaml", ".png", ".jpeg", ".gif", ".webp", ".ico"}


def disallowed(folder: Path) -> list[str]:
    return sorted(str(path.relative_to(folder)) for path in folder.rglob("*")
                  if path.is_file() and path.suffix.lower() not in ALLOWED)


def main() -> None:
    server = os.environ.get("CONNECTOR_URL", "https://mcp.sheetmusicanalysis.com/mcp")
    staging = ROOT / "out" / "plugin" / NAME
    shutil.rmtree(staging, ignore_errors=True)
    shutil.copytree(ROOT / "plugin", staging)
    shutil.copytree(ROOT / "skill", staging / "skills" / NAME)
    (staging / ".mcp.json").write_text(json.dumps({"mcpServers": {NAME: {"type": "http", "url": server}}}, indent=2) + "\n")
    if refused := disallowed(staging):
        raise SystemExit(f"Claude's plugin directory accepts only {', '.join(sorted(ALLOWED))} files: {', '.join(refused)}")
    target = ROOT / "dist" / NAME
    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(staging, target)
    archive = ROOT / "out" / f"{NAME}-plugin.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(target.rglob("*")):
            if path.is_file():
                bundle.write(path, Path(NAME) / path.relative_to(target))
    files = [path for path in target.rglob("*") if path.is_file()]
    print(f"{target}: {len(files)} files, connector {server}; {archive}: {archive.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
