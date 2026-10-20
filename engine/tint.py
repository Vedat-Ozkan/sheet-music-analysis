from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from engine.overlay import Box, PageLayout, S
from engine.render import Engraving

BOXES = {"svgBoundingBoxes": True, "svgAdditionalAttribute": ["staff@n"]}
SPACE = 180
CHANGED = "#FDD478"
FLAG_BAR = "#FFE066"
FLAG_OPACITY = "0.35"
MARGIN = 500


@dataclass
class Trimmed(Engraving):

    ratios: list[float] = field(default_factory=list)

    def _raster(self, page: int, width: int):
        return super()._raster(page, max(round(width * self.ratios[page - 1]), 1))


def tint(layout: PageLayout, box: Box, fill: str, opacity: str = "1", radius: float = 30) -> None:
    ET.SubElement(layout.under, f"{S}rect", {
        "x": f"{box.x:.0f}", "y": f"{box.y:.0f}", "width": f"{box.width:.0f}", "height": f"{box.height:.0f}",
        "rx": f"{radius:g}", "fill": fill, "fill-opacity": opacity,
    })


def finish(layouts: list[PageLayout], trim: bool = False) -> Engraving:
    pages, ratios = [], []
    for layout in layouts:
        ratio = 1.0
        if trim:
            inner = layout.root.find(f"{S}svg")
            wide = float(inner.get("viewBox").split()[2])
            right = max([box.right for system in layout.systems for box in system.content]
                        + [system.right for system in layout.systems]) + SPACE + MARGIN
            ratio = min(right / wide, 1.0)
            for box in (layout.root, inner):
                x, y, w, h = box.get("viewBox").split()
                box.set("viewBox", f"{x} {y} {float(w) * ratio:g} {h}")
        pages.append(layout.to_svg())
        ratios.append(ratio)
    return Trimmed(pages, ratios)
