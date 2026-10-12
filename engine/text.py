"""Text measurement and Roman numeral typesetting for overlay labels."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from fontTools.ttLib import TTFont
from PIL import ImageFont

FONT_DIR = Path(__file__).parent / "fonts"
# Score Serif is Liberation Serif (Times metrics, as Verovio assumes) with ♭ and ♮ added; see tools/build_fonts.py.
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


FIGURE = 0.72  # of the numeral: the textbook range is 0.65-0.85 and this stays readable at chat size
SUSPENSION = re.compile(r"^\d+[–-]\d+$")


def stack(rows: list[str], x: float, size: float, bold: bool = False, right: bool = False) -> tuple[list[Chunk], float]:
    """Figures stacked top row first, hung after a numeral: a lone row is raised, two rows run from above
    the cap top to just below the baseline, three start higher so the last stays near the baseline.
    Returns the chunks and the advance."""
    fsize = size * FIGURE
    count = len(rows)
    top = -size * 0.32 if count == 1 else -size * (0.38 if count == 2 else 0.62)
    widths = [width(row, fsize, bold) for row in rows]
    chunks = [Chunk(row, x + size * 0.02 + (max(widths) - widths[number] if right else 0), top + number * size * 0.5, fsize, bold)
              for number, row in enumerate(rows)]
    return chunks, (max(widths) + size * 0.06) if rows else 0.0


def _numeral_chunks(part: str, size: float, x: float, bold: bool, inversion_letters: bool = False,
                    rows: list[str] | None = None, suspension: str | None = None) -> tuple[list[Chunk], float]:
    """`rows` replaces the figures read from the part (figured-bass style); `suspension` is a "4–3" suffix set as a last row."""
    letter = ''
    # ABRSM letters stay on the baseline while the preceding seventh is raised.
    if inversion_letters and part.endswith(('b', 'c', 'd')) and NUMERAL.fullmatch(part[:-1]):
        part, letter = part[:-1], part[-1]
    match = NUMERAL.match(part)
    if not match:
        return [Chunk(part, x, 0, size, bold)], x + width(part, size, bold)
    chunks: list[Chunk] = []
    # OMT's cadential six-four: lower case with a period.
    base = match["accidental"].translate(SYMBOLS) + ("cad." if match["root"] == "Cad" else match["root"])
    chunks.append(Chunk(base, x, 0, size, bold))
    x += width(base, size, bold)
    if match["quality"]:
        symbol = QUALITIES[match["quality"]]
        raised = symbol == "ø"  # the degree sign already sits high; ø is a lowercase letter
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


def numeral(label: str, size: float, bold: bool = False, *, inversion_letters: bool = False,
            first_rows: list[str] | None = None) -> tuple[list[Chunk], float]:
    """Lay out a RomanText-style label ("V65/ii", "viio7", "bII6") with raised and stacked figures.

    A digit-dash-digit suffix ("V7 4–3") becomes the last figure row; any other text after the first space
    is appended as a smaller plain note. `first_rows` gives the first numeral's figures directly.
    Returns the chunks and the total width.
    """
    main, _, note = label.partition(" ")
    # "V6/5" is a common spelling of V65; a secondary never starts with a digit.
    main = re.sub(r"(\d)/(\d)", r"\1\2", main)
    parts = _split_secondary(main)
    # A suspension on an ABRSM-lettered chord has no stacked form; it stays a caption.
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
    """Where the root letters of the first numeral are centred, from the label's left edge: the point that
    sits over the chord's bass note. Accidentals before the letters do not count."""
    first = chunks[0]
    letters = first.text.lstrip("♭♯")
    return first.dx + width(first.text[: len(first.text) - len(letters)], first.size, first.bold) + width(letters, first.size, first.bold) / 2


def _split_secondary(label: str) -> list[str]:
    """Split "V7/ii" at the slash, but keep the half-diminished spelling "ii/o7" together."""
    return re.split(r"/(?!o)", label)
