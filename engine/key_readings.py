"""Second readings of key that experts often give: a short key area heard as applied chords in the key around
it, and a run of applied chords to one degree heard as a short modulation to that key.

Measured on 151 pairs of independent expert analyses (engineering log, challenge 72; eval/key_readings.py): spans flagged by these
two rules are spans where the other expert names a different key 0.40 of the time, against 0.18 for random
spans of the same lengths, with 9% of the music flagged.
"""

from __future__ import annotations

from fractions import Fraction

from engine.harmony import LABEL, MAJOR, MINOR, NAMES, _degree_root, _tonic
from engine.score import ScoreIndex

SHORTEST_BARS = 2
LONGEST_RUN = 3
NUMERALS = ["I", "II", "III", "IV", "V", "VI", "VII"]
SHARPS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def _name(pitch: int, minor: bool, home: str) -> str:
    tonic, home_minor = _tonic(home)
    fifths = {0: 0, 7: 1, 2: 2, 9: 3, 4: 4, 11: 5, 6: 6, 1: -5, 8: -4, 3: -3, 10: -2, 5: -1}[(tonic + 3) % 12 if home_minor else tonic]
    name = (SHARPS if fifths > 0 or "#" in home else NAMES)[pitch]
    return name.lower() if minor else name


def _numeral(key: str, home: str) -> str:
    (tonic, minor), (home_tonic, home_minor) = _tonic(key), _tonic(home)
    scale = MINOR if home_minor else MAJOR
    interval = (tonic - home_tonic) % 12
    accidental, degree = ("", scale.index(interval)) if interval in scale else ("b", scale.index((interval + 1) % 12))
    if home_minor and minor and degree in (5, 6) and not accidental:
        accidental = "b"
    return accidental + (NUMERALS[degree].lower() if minor else NUMERALS[degree])


def _in_home(label: str, key: str, home: str) -> str:
    relative = _numeral(key, home)
    match = LABEL.match(label)
    if match and "/" not in label and match["numeral"].upper() == "I" and not match["accidental"]:
        return relative + (match["quality"] or "") + (match["figures"] or "")
    return f"{label}/{relative}"


def _position(index: ScoreIndex, starts: dict[int, Fraction], at: dict) -> Fraction:
    measure = index.measure(at["measure"])
    return starts[at["measure"]] + (Fraction(at.get("beat", 1)).limit_denominator(96) - 1) * measure.beat_length


def alternatives(annotations: list[dict], index: ScoreIndex) -> list[dict]:
    starts, total = {}, Fraction(0)
    for measure in index.measures:
        starts.setdefault(measure.number, total)
        total += measure.length
    chords, key = [], None
    for item in sorted((a for a in annotations if a["type"] == "harmony"), key=lambda a: (index.measure(a["at"]["measure"]).index, a["at"].get("beat", 1))):
        key = item.get("key") or key
        if key:
            chords.append((item, key, _position(index, starts, item["at"])))
    found = []
    areas = []
    for chord in chords:
        if areas and _tonic(areas[-1][-1][1]) == _tonic(chord[1]):
            areas[-1].append(chord)
        else:
            areas.append([chord])
    for number, area in enumerate(areas[1:], start=1):
        home, key = areas[number - 1][0][1], area[0][1]
        end = areas[number + 1][0][2] if number + 1 < len(areas) else total
        bar = index.measure(area[0][0]["at"]["measure"]).length
        if _tonic(home)[0] != _tonic(key)[0] and end - area[0][2] <= SHORTEST_BARS * bar:
            found.append((area[0][0]["at"], area[-1][0]["at"], f"{home}: " + " ".join(_in_home(item["label"].split(" ")[0], key, home) for item, _, _ in area)))
    run: list = []

    def close() -> None:
        applied = [chord for chord in run if "/" in chord[0]["label"]]
        if len(applied) >= LONGEST_RUN:
            item, home, _ = run[0]
            target = item["label"].split(" ")[0].partition("/")[2]
            match = LABEL.match(target)
            tonic, minor = _tonic(home)
            key = _name(_degree_root(match["numeral"], match["accidental"], tonic, minor), match["numeral"].islower(), home)
            labels = [chord[0]["label"].split(" ")[0] for chord in run]
            tonic_label = "i" if key[0].islower() else "I"
            written = [label.partition("/")[0] if "/" in label else tonic_label + (LABEL.match(label)["figures"] or "") if LABEL.match(label) else label for label in labels]
            found.append((run[0][0]["at"], run[-1][0]["at"], f"{key}: " + " ".join(written)))

    for chord in chords:
        label = chord[0]["label"].split(" ")[0]
        head, _, target = label.partition("/")
        current = run[0][0]["label"].split(" ")[0].partition("/")[2] if run else None
        plain = LABEL.match(label)
        if run and current and target == current and chord[1] == run[0][1]:
            run.append(chord)
        elif run and plain and "/" not in label and (plain["figures"] or "") in ("", "6", "64") and label.lstrip("#b").rstrip("0123456789").upper() == current.lstrip("#b").upper() and chord[1] == run[0][1]:
            run.append(chord)
        else:
            close()
            run = [chord] if target and LABEL.match(target) else []
    close()
    found.sort(key=lambda span: (index.measure(span[0]["measure"]).index, span[0].get("beat", 1)))
    kept = []
    for start, end, label in found:
        if kept and (index.measure(start["measure"]).index, start.get("beat", 1)) <= (index.measure(kept[-1]["end"]["measure"]).index, kept[-1]["end"].get("beat") or 99):
            continue
        kept.append({"type": "alternative", "start": {"measure": start["measure"], "beat": start.get("beat", 1)}, "end": {"measure": end["measure"], "beat": end.get("beat", 1)}, "label": label})
    return kept
