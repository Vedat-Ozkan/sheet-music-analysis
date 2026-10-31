from __future__ import annotations

import xml.etree.ElementTree as ET
from itertools import groupby

from engine.score import LETTERS, MEI, XML_ID, ScoreIndex, in_range

LEDGER_LINES = 3
MIN_BARS = 2
KEYBOARDS = {"piano", "keyboard", "harpsichord", "organ"}
BOTTOM_LINE = {("G", "2"): 4 * 7 + 2, ("F", "4"): 2 * 7 + 4}
SIDE_NAMES = {"above": ("high above the {clef} staff", {"bass": "switch to treble clef", "treble": "write them an octave lower under an 8va sign"}),
              "below": ("far below the {clef} staff", {"bass": "write them an octave higher under an 8vb sign", "treble": "switch to bass clef"})}


def _clefs(root: ET.Element) -> dict[tuple[str, int], tuple[int, str]]:
    shapes = {element.get(XML_ID): element for element in root.iter(f"{MEI}clef")}
    current: dict[int, tuple[int, str] | None] = {}
    found = {}

    def read(element: ET.Element, staff: int) -> None:
        element = shapes.get((element.get("sameas") or "").lstrip("#"), element)
        key = (element.get("shape"), element.get("line"))
        shift = 7 if element.get("dis") == "8" and element.get("dis.place") == "above" else -7 if element.get("dis") == "8" else 0
        current[staff] = (BOTTOM_LINE[key] + shift, "treble" if key[0] == "G" else "bass") if key in BOTTOM_LINE else None

    for element in root.iter():
        if element.tag == f"{MEI}staffDef":
            for clef in element.iter(f"{MEI}clef"):
                read(clef, int(element.get("n", "1")))
            if element.get("clef.shape"):
                read(ET.Element("clef", shape=element.get("clef.shape"), line=element.get("clef.line", "")), int(element.get("n", "1")))
        elif element.tag == f"{MEI}measure":
            for staff in element.iter(f"{MEI}staff"):
                for clef in staff.iter(f"{MEI}clef"):
                    read(clef, int(staff.get("n", "1")))
                found.update({(element.get(XML_ID), int(staff.get("n", "1"))): current.get(int(staff.get("n", "1")))})
    return found


def _part_names(root: ET.Element) -> dict[int, str]:
    names = {}
    for group in root.iter(f"{MEI}staffGrp"):
        outer = next((label.text for label in group.findall(f"{MEI}label") if label.text), "")
        for staff in group.findall(f"{MEI}staffDef"):
            own = next((label.text for label in staff.findall(f"{MEI}label") if label.text), "")
            names.setdefault(int(staff.get("n", "1")), own or outer)
    return names


def _steps(pitch: str) -> int:
    return 7 * int(pitch.lstrip("ABCDEFG").lstrip("#b")) + LETTERS.index(pitch[0])


def passages(mei: str, index: ScoreIndex, first: int | None = None, last: int | None = None) -> list[tuple[int, int, int, str, str]]:
    clefs = _clefs(ET.fromstring(mei))
    found = []
    staves = sorted({event.staff for measure in index.measures for event in measure.events})
    for staff in staves:
        heavy: dict[int, str] = {}
        clef_of: dict[int, str] = {}
        for measure in index.measures:
            if not in_range(measure.number, first, last):
                continue
            sides = []
            for event in measure.events:
                if event.staff != staff or event.pitch is None or event.grace:
                    continue
                clef = clefs.get((event.segment, staff))
                if clef is None:
                    continue
                position = _steps(event.pitch) - clef[0]
                lines = (position - 8) // 2 if position >= 10 else (-position) // 2 if position <= -2 else 0
                sides.append(("above" if position > 0 else "below") if lines >= LEDGER_LINES else None)
                clef_of[measure.number] = clef[1]
            for side in ("above", "below"):
                if sides and sides.count(side) * 2 >= len(sides):
                    heavy[measure.number] = side
        bars = sorted(clef_of)
        for side, group in groupby(sorted(heavy.items()), key=lambda item: item[1]):
            numbers = [number for number, _ in group]
            start = prev = numbers[0]
            for number in numbers[1:] + [None]:
                between = [b for b in bars if prev < b < (number if number is not None else prev)]
                if number is not None and len(between) <= 1:
                    prev = number
                    continue
                if bars.index(prev) - bars.index(start) + 1 >= MIN_BARS:
                    found.append((start, prev, staff, side, clef_of[start]))
                start = prev = number
    return sorted(found)


def as_text(mei: str, index: ScoreIndex, first: int | None = None, last: int | None = None) -> str:
    found = passages(mei, index, first, last)
    if not found:
        return ""
    names = _part_names(ET.fromstring(mei))
    hands = len({event.staff for m in index.measures for event in m.events}) == 2
    lines = []
    for start, end, staff, side, clef in found:
        name = names.get(staff, "")
        keyboard = name.lower() in KEYBOARDS or (not name and hands)
        upper = min(s for s, n in names.items() if n == name) if name else 1
        who = ("right hand" if staff == upper else "left hand") if keyboard else f"{name} (staff {staff})" if name else f"staff {staff}"
        place, other = SIDE_NAMES[side]
        switch = "switch to tenor or treble clef" if clef == "bass" and not keyboard and side == "above" else other[clef]
        lines.append(f"Bars {start}–{end}, {who}: notes sit {place.format(clef=clef)}; "
                     f"many editions {switch} here.")
    return ("LEDGER LINES (the clef is the user's; do not change it. Mention each line below once in your reply.)\n"
            + "\n".join(lines))
