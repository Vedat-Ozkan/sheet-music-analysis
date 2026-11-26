from __future__ import annotations

import logging
import re

from engine.overlay import PageLayout

log = logging.getLogger(__name__)
SYSTEM_INSIDE_PAGE = "every system lies inside its page"


def page_frame(layout: PageLayout) -> tuple[float, float, float]:
    inner = next(element for element in layout.root.iter() if element.get("class") == "definition-scale")
    height = float(inner.get("viewBox").split()[3])
    offset = re.search(r"translate\(([-\d.]+),\s*([-\d.]+)\)", layout.canvas.get("transform", ""))
    return (float(offset[2]) if offset else 0.0), 0.0, height


def tallest_system(layouts: list[PageLayout]) -> float:
    return max((system.bottom() - system.top() for layout in layouts for system in layout.systems), default=0.0)


def systems_off_the_page(layouts: list[PageLayout]) -> list[int]:
    off = []
    for number, layout in enumerate(layouts, 1):
        shift, top, height = page_frame(layout)
        if any(system.top() + shift < top or system.bottom() + shift > height for system in layout.systems):
            off.append(number)
    return off


def report(rule: str, pages: list[int]) -> None:
    if pages:
        log.warning("output check failed: %s (pages %s)", rule, ", ".join(map(str, pages)))
