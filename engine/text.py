"""Text measurement and Roman numeral typesetting for overlay labels."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from fontTools.ttLib import TTFont
from PIL import ImageFont

FONT_DIR = Path(__file__).parent / "fonts"
MAIN, FALLBACK = "Liberation Serif", "DejaVu Serif"
FILES = {
    (MAIN, False): "LiberationSerif-Regular.ttf",
    (MAIN, True): "LiberationSerif-Bold.ttf",
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
    """Split text into (run, font family), sending symbols the main font lacks (♭, ♮) to the fallback."""
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
    dx: float  # from the label's left edge
    dy: float  # from the baseline; negative is up
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
    """ "Eb" -> "E♭", "f#" -> "f♯"."""
    return key[:1] + key[1:].translate(SYMBOLS)


def _numeral_chunks(part: str, size: float, x: float, bold: bool) -> tuple[list[Chunk], float]:
    match = NUMERAL.match(part)
    if not match:
        return [Chunk(part, x, 0, size, bold)], x + width(part, size, bold)
    chunks: list[Chunk] = []
    base = match["accidental"].translate(SYMBOLS) + match["root"]
    chunks.append(Chunk(base, x, 0, size, bold))
    x += width(base, size, bold)
    if match["quality"]:
        symbol = QUALITIES[match["quality"]]
        raised = symbol == "ø"  # the degree sign already sits high; ø is a lowercase letter
        quality_size = size * (0.62 if raised else 1)
        chunks.append(Chunk(symbol, x, -size * 0.34 if raised else 0, quality_size, bold))
        x += width(symbol, quality_size, bold)
    figures = match["figures"]
    if figures:
        figure_size = size * 0.58
        if len(figures) == 1:
            chunks.append(Chunk(figures, x + size * 0.03, -size * 0.36, figure_size, bold))
        else:  # stacked, top figure first: 65, 64, 43, 42
            step = size * 0.46
            top = -size * 0.42
            for row, figure in enumerate(figures):
                chunks.append(Chunk(figure, x + size * 0.03, top + row * step, figure_size, bold))
        x += max(width(figure, figure_size, bold) for figure in figures) + size * 0.05
    return chunks, x


def numeral(label: str, size: float, bold: bool = False) -> tuple[list[Chunk], float]:
    """Lay out a RomanText-style label ("V65/ii", "viio7", "bII6") with raised and stacked figures.

    Anything after the first space is appended as a smaller plain note, e.g. "V7 4–3".
    Returns the chunks and the total width.
    """
    main, _, note = label.partition(" ")
    # "V6/5" is a common spelling of V65; a secondary never starts with a digit.
    main = re.sub(r"(\d)/(\d)", r"\1\2", main)
    chunks: list[Chunk] = []
    x = 0.0
    for position, part in enumerate(_split_secondary(main)):
        if position:
            chunks.append(Chunk("/", x, 0, size, bold))
            x += width("/", size, bold)
        part_chunks, x = _numeral_chunks(part, size, x, bold)
        chunks.extend(part_chunks)
    if note:
        note_size = size * 0.7
        x += size * 0.25
        chunks.append(Chunk(note, x, 0, note_size, bold))
        x += width(note, note_size, bold)
    return chunks, x


def _split_secondary(label: str) -> list[str]:
    """Split "V7/ii" at the slash, but keep the half-diminished spelling "ii/o7" together."""
    return re.split(r"/(?!o)", label)
