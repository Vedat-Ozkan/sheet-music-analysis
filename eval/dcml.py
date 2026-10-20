from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from fractions import Fraction

from music21 import key as m21key
from music21 import roman

from engine.score import ScoreIndex

LABEL = re.compile(
    r"^(?:(?P<globalkey>[A-Ga-g][#b]*)\.)?(?:(?P<localkey>[#b]*[ivIV]+)\.)?"
    r"(?P<numeral>[#b]*(?:[ivIV]+|Ger|It|Fr))(?P<form>[o%M+]|%7|M7)?(?P<figbass>7|65|43|42|2|64|6)?"
    r"(?:\((?P<changes>[^)]*)\))?(?:/(?P<relative>[#b]*[ivIV]+(?:/[#b]*[ivIV]+)?))?(?:\|(?P<cadence>[A-Z]+))?[{}\\]*$"
)
AUGMENTED_SIXTHS = {"Ger": "Ger65", "It": "It6", "Fr": "Fr43"}


def figure(match: re.Match) -> str:
    numeral = match["numeral"]
    if numeral.lstrip("#b") in AUGMENTED_SIXTHS:
        return AUGMENTED_SIXTHS[numeral.lstrip("#b")]
    form = (match["form"] or "").replace("%", "ø")
    figbass = {"2": "42"}.get(match["figbass"] or "", match["figbass"] or "")
    if form == "M" and figbass in ("", "7"):
        form, figbass = "M", "7"
    text = numeral + form + figbass
    return text + (f"/{match['relative']}" if match["relative"] else "")


def key_name(local: str, global_key: m21key.Key) -> str:
    tonic = roman.RomanNumeral(local, global_key).root().name.replace("-", "b")
    return tonic.lower() if local.lstrip("#b")[0].islower() else tonic[0].upper() + tonic[1:]


def to_romantext(tsv: str, index: ScoreIndex) -> str:
    rows = [dict(zip(tsv.splitlines()[0].split("\t"), line.split("\t"))) for line in tsv.splitlines()[1:] if line.strip()]
    current, by_measure = None, {}
    for row in rows:
        if not row.get("numeral") or row["label"].startswith("@"):
            continue
        global_name = row["globalkey"]
        global_key = m21key.Key(global_name[0] + global_name[1:].replace("b", "-") if global_name[0].isupper() else global_name[0] + global_name[1:].replace("b", "-"))
        number = int(row["mn"])
        offset = Fraction(row["mn_onset"]) * 4
        measure = index.measure(number)
        beat = round(float(measure.beat_of(min(offset, measure.length))), 3)
        fake = LABEL.match(row["numeral"] + (row["form"] or "") + (row["figbass"] or "") + (f"/{row['relativeroot']}" if row["relativeroot"] else ""))
        if not fake:
            continue
        here = key_name(row["localkey"], global_key)
        text = f"b{beat:g} " if beat != 1 else ""
        if here != current:
            text += f"{here}: "
            current = here
        by_measure.setdefault(number, []).append(text + figure(fake))
    return "\n".join(f"m{number} " + " ".join(items) for number, items in sorted(by_measure.items()))
