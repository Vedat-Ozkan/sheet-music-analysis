from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction

from engine.score import ScoreIndex

STEPS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
NAMES = ["C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
MAJOR = [0, 2, 4, 5, 7, 9, 11]
MINOR = [0, 2, 3, 5, 7, 8, 10]
ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7}
LABEL = re.compile(r"^(?P<accidental>[#b-]*)(?P<numeral>[ivIV]+)(?P<quality>o|ø|\+|%)?(?P<major>M)?(?P<figures>7|65|43|42|2|64|6|9|11|13)?$")
SPECIAL = {
    "It6": (8, 0, 6),
    "Ger65": (8, 0, 3, 6),
    "Ger6": (8, 0, 3, 6),
    "Fr43": (8, 0, 2, 6),
    "Fr6": (8, 0, 2, 6),
}


@dataclass(frozen=True)
class Chord:
    root: int
    tones: frozenset[int]
    bass: int
    seventh: int | None
    third: int | None


def _tonic(key: str) -> tuple[int, bool]:
    name = key.strip()
    pc = STEPS[name[0].upper()] + name.count("#") - name[1:].count("b") - name.count("-")
    return pc % 12, name[0].islower()


def _degree_root(numeral: str, accidental: str, tonic: int, minor: bool) -> int:
    degree = ROMAN[numeral.lower()]
    if accidental.strip("#") and accidental.replace("#", "") and not (minor and degree in (6, 7) and numeral.islower()):
        return (tonic + MAJOR[degree - 1] - accidental.count("b") - accidental.count("-") + accidental.count("#")) % 12
    root = tonic + (MINOR if minor else MAJOR)[degree - 1]
    if minor and degree in (6, 7) and numeral.islower():
        root += 1
    if minor and degree in (6, 7) and numeral.islower() and accidental.startswith("#"):
        accidental = accidental[1:]
    root += accidental.count("#") - accidental.count("b") - accidental.count("-")
    return root % 12


def chord(key: str, label: str) -> Chord | None:
    label = re.sub(r"\[[^\]]*\]", "", label.strip().split(" ")[0]).replace("/o", "ø")
    if not label:
        return None
    try:
        tonic, minor = _tonic(key)
    except (KeyError, IndexError):
        return None
    head, _, target = label.partition("/")
    if target and target not in ("o",):
        inner = chord(key, target if re.match(r"^[#b-]*[ivIV]+$", target) else "")
        if inner is None:
            return None
        target_name = NAMES[inner.root]
        return chord(target_name.lower() if target.lstrip("#b-")[0].islower() else target_name, head)
    if label in ("Cad64",):
        third = (tonic + (3 if minor else 4)) % 12
        return Chord(tonic, frozenset({tonic, third, (tonic + 7) % 12}), (tonic + 7) % 12, None, third)
    if label in ("N", "N6"):
        root = (tonic + 1) % 12
        tones = frozenset({root, (root + 4) % 12, (root + 7) % 12})
        return Chord(root, tones, (root + 4) % 12 if label == "N6" else root, None, (root + 4) % 12)
    if label in SPECIAL:
        steps = SPECIAL[label]
        tones = frozenset((tonic + s) % 12 for s in steps)
        return Chord((tonic + steps[0]) % 12, tones, (tonic + steps[0]) % 12, None, None)
    match = LABEL.match(head)
    if not match:
        return None
    numeral, quality, figures = match["numeral"], match["quality"] or "", match["figures"] or ""
    if figures in ("9", "11", "13"):
        figures = "7"
    if match["major"]:
        figures = "M" + (figures or "7")
    root = _degree_root(numeral, match["accidental"], tonic, minor)
    if quality in ("o", "/o", "ø", "%"):
        third, fifth = 3, 6
    elif quality == "+":
        third, fifth = 4, 8
    else:
        third, fifth = (4, 7) if numeral.isupper() else (3, 7)
    seventh = None
    if figures.lstrip("M") in ("7", "65", "43", "42", "2"):
        if figures.startswith("M"):
            seventh = 11
        elif quality == "o":
            seventh = 9
        elif quality in ("ø", "%"):
            seventh = 10
        else:
            if numeral.islower():
                seventh = 10
            else:
                degree = ROMAN[numeral.lower()]
                diatonic = (tonic + (MINOR if minor else MAJOR)[(degree + 5) % 7]) % 12
                seventh = (diatonic - root) % 12
                seventh = seventh if seventh in (10, 11) else 10
    members = [root, (root + third) % 12, (root + fifth) % 12] + ([(root + seventh) % 12] if seventh is not None else [])
    position = {"": 0, "7": 0, "6": 1, "65": 1, "64": 2, "43": 2, "42": 3, "2": 3}[figures.lstrip("M")]
    return Chord(root, frozenset(members), members[position], members[3] if seventh is not None else None, members[1])


def _sounding(index: ScoreIndex, start: tuple[int, Fraction], end: tuple[int, Fraction] | None) -> list[list]:
    from engine.reduce import midi

    numbers = [m.number for m in index.measures]
    if start[0] not in numbers:
        return []
    groups = []
    for measure in index.measures[numbers.index(start[0]) :]:
        if end and measure.number > end[0]:
            break
        notes = [e for e in measure.events if e.pitch and not e.grace]
        for onset in sorted({e.onset for e in notes}):
            if (measure.number, onset) < start or (end and (measure.number, onset) >= end):
                continue
            groups.append([(midi(e.pitch), e.pitch) for e in notes if e.onset <= onset < e.onset + e.duration])
    return groups


def mismatches(annotations: list[dict], index: ScoreIndex) -> list[str]:
    harmonies = sorted((a for a in annotations if a.get("type") == "harmony"), key=lambda a: (a["at"]["measure"], float(a["at"].get("beat", 1))))
    found, key = [], "C"
    for number, item in enumerate(harmonies):
        key = item.get("key", key)
        label = item["label"].split(" ")[0]
        named = chord(key, label)
        if named is None:
            continue
        measure = index.measure(item["at"]["measure"])
        start = (measure.number, measure.offset_of(float(item["at"].get("beat", 1))))
        if number + 1 < len(harmonies):
            following = harmonies[number + 1]["at"]
            after = index.measure(following["measure"])
            end = (after.number, after.offset_of(float(following.get("beat", 1))))
        else:
            end = None
        groups = _sounding(index, start, end)
        if not groups:
            continue
        heard = {pc % 12 for group in groups for pc, _ in group}
        lowest = {min(group)[0] % 12 for group in groups}
        where = f"m{measure.number} b{float(item['at'].get('beat', 1)):g} {label} (in {key})"
        missing = [NAMES[pc] for pc in sorted(named.tones) if pc not in heard]
        if named.seventh is not None and named.seventh not in heard:
            found.append(f"{where}: its seventh, {NAMES[named.seventh]}, never sounds while this chord lasts")
        elif len(missing) * 2 >= len(named.tones):
            found.append(f"{where}: {len(missing)} of its {len(named.tones)} notes ({', '.join(missing)}) never sound while it lasts")
        if named.bass not in lowest and label != "Cad64":
            bottom = NAMES[min(groups[0])[0] % 12]
            found.append(f"{where}: its bass, {NAMES[named.bass]}, is never the lowest note while it lasts (the lowest at its start is {bottom})")
    return found
