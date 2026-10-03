"""Engrave a MusicXML score with Verovio and rasterise the pages."""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from importlib.resources import files

import img2pdf
import resvg_py
import verovio
from PIL import Image

from engine.score import ScoreIndex
from engine.text import FONT_FILES, MAIN as TEXT_FONT

RESOURCE_PATH = str(files("verovio") / "data")
VEROVIO_OPTIONS = {
    "xmlIdChecksum": True,  # element IDs are repeatable across runs
    "svgViewBox": True,
    "pageWidth": 2100,
    "pageHeight": 2970,
    "scale": 40,
    "header": "none",
    "footer": "none",
    "breaks": "auto",
}


class ScoreError(ValueError):
    """The input could not be read as a MusicXML score."""


@dataclass
class Engraving:
    svgs: list[str]

    @property
    def page_count(self) -> int:
        return len(self.svgs)

    def png(self, page: int = 1, width: int = 1400, colors: int = 128) -> bytes:
        """One page as a palette PNG, small enough to send inline in a chat."""
        raw = bytes(
            resvg_py.svg_to_bytes(
                svg_string=self.svgs[page - 1],
                background="#ffffff",
                width=width,
                # Verovio lays text out with Times metrics; Liberation Serif matches them.
                skip_system_fonts=True,
                font_files=FONT_FILES,
                font_family=TEXT_FONT,
                serif_family=TEXT_FONT,
            )
        )
        # Max-coverage keeps the few annotation colours exact; median cut spends the palette on greys.
        image = Image.open(io.BytesIO(raw)).convert("RGB")
        image = image.quantize(colors, method=Image.Quantize.MAXCOVERAGE, dither=Image.Dither.NONE)
        out = io.BytesIO()
        image.save(out, "PNG", optimize=True)
        return out.getvalue()

    def pdf(self, width: int = 2100) -> bytes:
        return img2pdf.convert([self.png(page, width) for page in range(1, self.page_count + 1)])


def load_toolkit(score: bytes, options: dict | None = None) -> verovio.toolkit:
    """Load plain (.musicxml) or compressed (.mxl) MusicXML into a Verovio toolkit."""
    # Verovio's default resource path only applies on the main thread, so it is set per toolkit.
    toolkit = verovio.toolkit(False)
    toolkit.setResourcePath(RESOURCE_PATH)
    toolkit.setOptions({**VEROVIO_OPTIONS, **(options or {})})
    if score[:2] == b"PK":
        loaded = toolkit.loadZipDataBase64(base64.b64encode(score).decode())
    else:
        # Older notation programs write a byte-order mark, which Verovio rejects, or Latin-1 text.
        try:
            text = score.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = score.decode("latin-1")
        loaded = toolkit.loadData(text)
    if not loaded:
        raise ScoreError("Verovio could not read this file as MusicXML")
    return toolkit


def engrave(score: bytes, measures: tuple[int, int] | None = None) -> Engraving:
    """Engrave the whole score, or printed measures first..last on one page cropped to fit."""
    if not measures:
        toolkit = load_toolkit(score)
    else:
        toolkit = load_toolkit(score, {"adjustPageHeight": True, "pageHeight": 60000})
        toolkit.select({"measureRange": ScoreIndex(toolkit.getMEI()).measure_range(*measures)})
        toolkit.redoLayout()
    return Engraving([toolkit.renderToSVG(page) for page in range(1, toolkit.getPageCount() + 1)])
