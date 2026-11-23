"""Draw every score that prints chord symbols with a full set of our marks, and count each printed chord
symbol that overlaps one of our marks or another printed element.

    .venv/bin/python -m tools.chord_symbol_check PATH... [--out FOLDER] [--bars N]

PATH is a score or a folder searched for .mxl, .musicxml and .xml files; only scores with a chord symbol
(a <harmony> with a <root>) are drawn. The first N bars (16 by default) get a
numeral on every downbeat, a cadence, a phrase and a region bracket every four bars, and two callouts. With
--out, each marked page is also written as PNG for looking at.
"""

from __future__ import annotations

import argparse
import io
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from engine.annotate import render
from engine.annotations import AnnotationList
from engine.overlay import S, Box, PageLayout
from engine.render import load_toolkit
from engine.score import ScoreIndex

OVERLAP = 10
NUMERALS = ("I", "IV7", "V65/V", "vi", "ii7", "V7", "I6", "bVII")
_layouts: list[PageLayout] = []
_init, _text, _numerals = PageLayout.__init__, PageLayout._text, PageLayout._draw_harmonies


def _watch_init(self, svg, *args, **kwargs):
    _init(self, svg, *args, **kwargs)
    self.marks = []
    self.symbols = [("".join(group.itertext()).strip(), list(filter(None, map(PageLayout._rect_box, group.iter(f"{S}rect")))))
                    for group in ET.fromstring(svg).iter(f"{S}g") if group.get("class") == "harm"]
    _layouts.append(self)


def _watch_text(self, x, y, string, size, **kwargs):
    box = _text(self, x, y, string, size, **kwargs)
    if kwargs.get("fill") != "#ffffff" and not getattr(self, "in_numerals", False):
        self.marks.append((string, box))
    return box


def _watch_numerals(self, *args, **kwargs):
    self.in_numerals = True
    try:
        return _numerals(self, *args, **kwargs)
    finally:
        self.in_numerals = False


PageLayout.__init__, PageLayout._text, PageLayout._draw_harmonies = _watch_init, _watch_text, _watch_numerals


def musicxml_text(path: Path) -> str:
    data = path.read_bytes()
    if data[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = [name for name in archive.namelist() if not name.startswith("META-INF") and name.endswith((".xml", ".musicxml"))]
            data = archive.read(names[0])
    return data.decode("utf-8", "replace")


def prints_chord_symbols(path: Path) -> bool:
    return bool(re.search(r"<harmony\b(?:(?!</harmony>).)*<root\b", musicxml_text(path), re.S))


def marks_for(score: bytes, bars: int) -> tuple[AnnotationList, tuple[int, int]]:
    chosen = ScoreIndex(load_toolkit(score).getMEI()).measures[:bars]
    annotations = [{"type": "harmony", "at": {"measure": m.number, "beat": 1}, "label": NUMERALS[i % len(NUMERALS)],
                    **({"key": "C"} if i == 0 else {})} for i, m in enumerate(chosen)]
    for group in range(0, len(chosen), 4):
        four = chosen[group:group + 4]
        annotations.append({"type": "cadence", "at": {"measure": four[-1].number, "beat": 1}, "label": "PAC"})
        annotations.append({"type": "phrase", "start": {"measure": four[0].number, "beat": 1}, "end": {"measure": four[-1].number},
                            "label": "abcd"[group // 4 % 4]})
        annotations.append({"type": "region", "start": {"measure": four[0].number, "beat": 1}, "end": {"measure": four[-1].number},
                            "label": "pedal on G"})
    for number, measure in enumerate(chosen[1:3], 1):
        annotations.append({"type": "callout", "at": {"measure": measure.number, "beat": 1}, "number": number})
    return AnnotationList.model_validate({"annotations": annotations}), (chosen[0].number, chosen[-1].number)


def _overlaps(a: Box, b: Box, by: float = 0.0) -> bool:
    return min(a.right, b.right) - max(a.x, b.x) > by and min(a.bottom, b.bottom) - max(a.y, b.y) > by


def chord_symbol_hits(layout: PageLayout) -> tuple[int, list[str]]:
    symbols = [(name, boxes) for name, boxes in layout.symbols if boxes]
    own = [box for _, boxes in symbols for box in boxes]
    printed = [box for system in layout.systems for box in system.content if box not in own]
    ours = layout.marks + layout.harmony_labels
    hits = []
    for position, (name, boxes) in enumerate(symbols):
        for box in boxes:
            hits += [f"{name} / our {string!r}" for string, mark in ours if _overlaps(box, mark)]
            hits += [f"{name} / printed" for other in printed if _overlaps(box, other, OVERLAP)]
            hits += [f"{name} / chord symbol {other_name}" for other_name, others in symbols[:position]
                     for other in others if _overlaps(box, other, OVERLAP)]
    return len(symbols), hits


def check(path: Path, bars: int, out: Path | None) -> tuple[int, list[str]]:
    score = path.read_bytes()
    annotations, measures = marks_for(score, bars)
    _layouts.clear()
    page = render(score, annotations, measures=measures)
    if out:
        out.mkdir(parents=True, exist_ok=True)
        for number in range(1, page.page_count + 1):
            (out / f"{path.stem}-{number}.png").write_bytes(page.png(number))
    found = [chord_symbol_hits(layout) for layout in _layouts[-page.page_count:]]
    return sum(count for count, _ in found), [hit for _, hits in found for hit in hits]


def scores(paths: list[Path]) -> list[Path]:
    found = []
    for path in paths:
        candidates = sorted(p for p in path.rglob("*") if p.suffix in (".mxl", ".musicxml", ".xml")) if path.is_dir() else [path]
        found += [candidate for candidate in candidates if prints_chord_symbols(candidate)]
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--bars", type=int, default=16)
    args = parser.parse_args()
    total_symbols, total_hits, failed = 0, 0, []
    for path in scores(args.paths):
        try:
            count, hits = check(path, args.bars, args.out)
        except Exception as error:
            failed.append(path)
            print(f"{path}: not drawn: {type(error).__name__}: {error}")
            continue
        total_symbols += count
        total_hits += len(hits)
        print(f"{path}: {count} chord symbols drawn, {len(hits)} overlaps" + "".join(f"\n    {hit}" for hit in hits))
    print(f"total: {total_symbols} chord symbols drawn, {total_hits} overlaps, {len(failed)} scores not drawn")


if __name__ == "__main__":
    main()
