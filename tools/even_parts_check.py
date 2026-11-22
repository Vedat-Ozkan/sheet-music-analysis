from __future__ import annotations

import argparse
import gzip
import io
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from engine.read_pdf import _archived_score, clean
from engine.render import written_by_the_pdf_reader

HERE = Path(__file__).resolve().parents[1]
USAGE = """Corpus check: lists every PDF reading whose parts, after read_pdf.clean, do not hold the same bar numbers.
Reads the cached benchmark readings (results-final--*.musicxml under --readings) and every reader-written file in tests/data.

    PYTHONPATH=. .venv/bin/python tools/even_parts_check.py --readings /home/kema/projects/sheet-music-plugin/spike/omr"""


def readings(cache: Path) -> list[Path]:
    cached = sorted(cache.glob("bench*/cache/runs/results-final--*.musicxml"))
    local = sorted(path for path in (HERE / "tests/data").rglob("*")
                   if path.name.removesuffix(".gz").endswith((".musicxml", ".mxl", ".xml"))
                   and written_by_the_pdf_reader(ET.tostring(_archived_score(_archive(_read(path))), encoding="unicode")))
    return cached + local


def _read(path: Path) -> bytes:
    return gzip.decompress(path.read_bytes()) if path.suffix == ".gz" else path.read_bytes()


def _archive(data: bytes) -> bytes:
    if data[:2] == b"PK":
        return data
    sink = io.BytesIO()
    with zipfile.ZipFile(sink, "w") as archive:
        archive.writestr("score.xml", data)
    return sink.getvalue()


def uneven(path: Path) -> list[str]:
    root = ET.fromstring(clean(_archive(_read(path))))
    names = {entry.get("id"): entry.findtext("part-name") or "" for entry in root.iter("score-part")}
    bars = {part.get("id"): [bar.get("number") for bar in part.findall("measure")] for part in root.findall("part")}
    every = set().union(*bars.values())
    if all(numbers == next(iter(bars.values())) for numbers in bars.values()):
        return []
    return [f"{part} {names[part]!r}: {len(numbers)} bars, lacks {sorted(every - set(numbers), key=_order)}"
            for part, numbers in bars.items()]


def _order(number: str) -> tuple:
    digits = "".join(c for c in number if c.isdigit())
    return int(digits or 0), number


def main() -> None:
    parser = argparse.ArgumentParser(description=USAGE, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--readings", type=Path, default=HERE / "spike/omr")
    paths = readings(parser.parse_args().readings)
    found = 0
    for path in paths:
        if lines := uneven(path):
            found += 1
            print(path)
            for line in lines:
                print("   ", line)
    print(f"{found} of {len(paths)} readings have parts with different bars")


if __name__ == "__main__":
    main()
