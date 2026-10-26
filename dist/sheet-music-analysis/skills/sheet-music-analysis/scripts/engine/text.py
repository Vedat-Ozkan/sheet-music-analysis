from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from fontTools.ttLib import TTFont
from PIL import ImageFont

FONT_DIR = Path(__file__).parent / "fonts"
MAIN, FALLBACK = "Score Serif", "DejaVu Serif"
FILES = {
    (MAIN, False): "ScoreSerif-Regular.ttf",
    (MAIN, True): "ScoreSerif-Bold.ttf",
    (FALLBACK, False): "DejaVuSerif.ttf",
    (FALLBACK, True): "DejaVuSerif-Bold.ttf",
}
FONT_FILES = [str(path) for path in sorted(FONT_DIR.glob("*.ttf"))]
MEASURE_SIZE = 200


@lru_cache
def _font(family: str, bold: bool) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_DIR / FILES[(family, bold)]), MEASURE_SIZE)


@lru_cache
def _main_coverage() -> frozenset[int]:
    return frozenset(TTFont(FONT_DIR / FILES[(MAIN, False)]).getBestCmap())


def runs(text: str) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for char in text:
        family = MAIN if ord(char) in _main_coverage() else FALLBACK
        if result and result[-1][1] == family:
            result[-1] = (result[-1][0] + char, family)
        else:
            result.append((char, family))
    return result


def width(text: str, size: float, bold: bool = False) -> float:
    return sum(_font(family, bold).getlength(run) for run, family in runs(text)) * size / MEASURE_SIZE


@dataclass
class Chunk:
    text: str
    dx: float
    dy: float
    size: float
    bold: bool = False


NUMERAL = re.compile(
    r"^(?P<accidental>[b#♭♯]*)"
    r"(?P<root>[ivIV]+|N|Ger|It|Fr|Cad)"
    r"(?P<quality>/o|o|°|ø|%|\+)?"
    r"(?P<figures>\d*)$"
)
QUALITIES = {"o": "°", "°": "°", "/o": "ø", "ø": "ø", "%": "ø", "+": "+"}
SYMBOLS = str.maketrans({"b": "♭", "#": "♯"})


def pretty_key(key: str) -> str:
    return key[:1] + key[1:].translate(SYMBOLS)


FIGURE = 0.72
SUSPENSION = re.compile(r"^\d+[–-]\d+$")


def stack(rows: list[str], x: float, size: float, bold: bool = False, right: bool = False) -> tuple[list[Chunk], float]:
    fsize = size * FIGURE
    count = len(rows)
    top = -size * 0.32 if count == 1 else -size * (0.38 if count == 2 else 0.62)
    step = 0.5
    if count == 3 and any(sign in row for row in rows for sign in "♭♯♮"):
        top, step = -size * 0.68, 0.56
    widths = [width(row, fsize, bold) for row in rows]
    chunks = [Chunk(row, x + size * 0.02 + (max(widths) - widths[number] if right else 0), top + number * size * step, fsize, bold)
              for number, row in enumerate(rows)]
    return chunks, (max(widths) + size * 0.06) if rows else 0.0


def _numeral_chunks(part: str, size: float, x: float, bold: bool, inversion_letters: bool = False,
                    rows: list[str] | None = None, suspension: str | None = None) -> tuple[list[Chunk], float]:
    letter = ''
    if inversion_letters and part.endswith(('b', 'c', 'd')) and NUMERAL.fullmatch(part[:-1]):
        part, letter = part[:-1], part[-1]
    match = NUMERAL.match(part)
    if not match:
        return [Chunk(part, x, 0, size, bold)], x + width(part, size, bold)
    chunks: list[Chunk] = []
    base = match["accidental"].translate(SYMBOLS) + ("V" if match["root"] == "Cad" else match["root"])
    chunks.append(Chunk(base, x, 0, size, bold))
    x += width(base, size, bold)
    if match["quality"]:
        symbol = QUALITIES[match["quality"]]
        raised = symbol == "ø"
        quality_size = size * (0.62 if raised else 1)
        chunks.append(Chunk(symbol, x, -size * 0.34 if raised else 0, quality_size, bold))
        x += width(symbol, quality_size, bold)
    figures = list(match["figures"]) if rows is None else list(rows)
    if suspension:
        figures.append(suspension)
    if figures:
        stacked, advance = stack(figures, x, size, bold, right=any(sign in row for row in figures for sign in "♭♯♮"))
        chunks.extend(stacked)
        x += advance
    if letter:
        chunks.append(Chunk(letter, x, 0, size, bold))
        x += width(letter, size, bold)
    return chunks, x


CONTINUATION = re.compile(r"^~\d+$")

def _continuation(digits: str, size: float, bold: bool) -> tuple[list[Chunk], float]:
    dash = width("-", size * FIGURE, bold) + size * 0.12
    figures, advance = stack(list(digits), dash, size, bold)
    dashes = [Chunk("-", 0, figure.dy, figure.size, bold) for figure in figures]
    return figures + dashes, dash + advance


def numeral(label: str, size: float, bold: bool = False, *, inversion_letters: bool = False,
            first_rows: list[str] | None = None) -> tuple[list[Chunk], float]:
    main, _, note = label.partition(" ")
    if CONTINUATION.match(main):
        return _continuation(main[1:], size, bold)
    main = re.sub(r"^cad6/?4$", "Cad64", main, flags=re.IGNORECASE)
    main = re.sub(r"(\d)/(\d)", r"\1\2", main)
    parts = _split_secondary(main)
    suspension = note if SUSPENSION.match(note) and not (inversion_letters and parts[-1][-1:] in "bcd") else None
    if suspension:
        note = ""
    chunks: list[Chunk] = []
    x = 0.0
    for position, part in enumerate(parts):
        if position:
            chunks.append(Chunk("/", x, 0, size, bold))
            x += width("/", size, bold)
        last = position == len(parts) - 1
        part_chunks, x = _numeral_chunks(part, size, x, bold, inversion_letters, first_rows if position == 0 else None,
                                         suspension if last else None)
        chunks.extend(part_chunks)
    if note:
        note_size = size * 0.7
        x += size * 0.25
        chunks.append(Chunk(note, x, 0, note_size, bold))
        x += width(note, note_size, bold)
    return chunks, x


def root_centre(chunks: list[Chunk]) -> float:
    first = chunks[0]
    letters = first.text.lstrip("♭♯")
    return first.dx + width(first.text[: len(first.text) - len(letters)], first.size, first.bold) + width(letters, first.size, first.bold) / 2


def _split_secondary(label: str) -> list[str]:
    return re.split(r"/(?!o)", label)
