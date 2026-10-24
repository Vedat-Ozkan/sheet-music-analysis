"""Independent source readings, excluding edited copies of the same analysis."""

from __future__ import annotations

import re
from itertools import combinations
from pathlib import Path


def independent_readings(folder: Path, remote: dict) -> tuple[list[dict], list[dict]]:
    selected, excluded = {}, []
    files = sorted(folder.glob("analysis*.txt"), key=lambda p: p.name == "analysis.txt")
    for path in files:
        text = path.read_text(encoding="utf-8-sig")
        analyst = next((l.split(":", 1)[1].strip() for l in text.splitlines() if l.strip().lower().startswith("analyst:")), "")
        source = remote.get(path.stem + "_source")
        entry = dict(file=path.name, analyst=analyst, source=source)
        if "Beethoven" in str(folder) and "Piano_Sonatas" in str(folder) and path.name == "analysis.txt" and any((folder / f"analysis_{s}.txt").exists() for s in ("DCML", "BPS")):
            excluded.append(dict(**entry, reason="edited conversion; use original source file"))
            continue
        if re.search(r"\bafter\b", analyst, re.I):
            excluded.append(dict(**entry, reason="derivative re-analysis"))
            continue
        if "BCMH" in path.name:
            family = "BCMH"
        elif "DCML" in path.name or "DCML" in analyst or (isinstance(source, str) and "DCMLab/" in source):
            family = "DCML"
        elif "BPS" in path.name or "BPS dataset" in analyst or (isinstance(source, str) and "functional-harmony" in source):
            family = "BPS"
        elif "TAVERN" in analyst:
            family = "TAVERN-B" if path.name == "analysis_B.txt" else "TAVERN-A"
        elif path.name == "analysis_DT.txt":
            family = "TAOM"
        elif source:
            family = "source:" + str(source)
        elif analyst:
            family = "analyst:" + analyst.casefold()
        else:
            excluded.append(dict(**entry, reason="no independent-source provenance"))
            continue
        entry.update(family=family, computer_assisted="computer" in analyst.lower())
        if family in selected:
            excluded.append(dict(**entry, reason="same source as " + selected[family]["file"]))
        else:
            selected[family] = entry
    return list(selected.values()), excluded


def independent_pairs(readings: list[dict]) -> list[tuple[dict, dict]]:
    return list(combinations(readings, 2))
