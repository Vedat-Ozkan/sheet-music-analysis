from __future__ import annotations

import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from tests.data.tabs.make_tab_pdfs import HERE, Piece, bars, musicxml

from engine.read_pdf import problem_spots
from engine.read_tab import read_tab

USERS = HERE.parent / "users"
REVIEW = HERE / "review"
FOLDERS = [HERE, REVIEW, REVIEW / "hand", REVIEW / "round2", REVIEW / "round2" / "hand", USERS]
SILENT_KINDS = ("wrong length", "wrong onset", "missed", "extra")
STEPS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


@dataclass(frozen=True)
class Note:
    bar: int
    onset: Fraction
    string: int
    fret: int
    length: Fraction
    midi: int
    tie_stop: bool
    spelled: str


def notes(data: bytes, capo: int = 0) -> tuple[list[Note], int]:
    root = ET.fromstring(data)
    found, count = [], 0
    for part in root.iter("part"):
        divisions = 1
        drawn_twice = staves_beside_tablature(part)
        for position, measure in enumerate(part.iter("measure")):
            count = max(count, position + 1)
            cursor = onset = Fraction(0)
            for element in measure:
                if element.tag == "attributes" and element.findtext("divisions"):
                    divisions = int(element.findtext("divisions"))
                if element.tag == "backup":
                    cursor -= Fraction(int(element.findtext("duration")), divisions)
                if element.tag == "forward":
                    cursor += Fraction(int(element.findtext("duration")), divisions)
                if element.tag != "note" or element.find("grace") is not None:
                    continue
                length = Fraction(int(element.findtext("duration")), divisions)
                if element.find("chord") is None:
                    onset = cursor
                    cursor += length
                string = element.findtext("notations/technical/string")
                if string is None or element.find("pitch") is None or element.findtext("staff") in drawn_twice:
                    continue
                step = element.findtext("pitch/step")
                alter = int(element.findtext("pitch/alter") or 0)
                midi = 12 * (int(element.findtext("pitch/octave")) + 1) + STEPS[step] + alter + capo
                spelled = step + {1: "#", -1: "b", 2: "##", -2: "bb"}.get(alter, "")
                found.append(Note(position, onset, int(string), int(element.findtext("notations/technical/fret")),
                                  length, midi, any(tie.get("type") == "stop" for tie in element.findall("tie")), spelled))
    return found, count


def staves_beside_tablature(part: ET.Element) -> set[str]:
    clefs = part.findall("measure/attributes/clef")
    tablature = {clef.get("number", "1") for clef in clefs if clef.findtext("sign") == "TAB"}
    return {clef.get("number", "1") for clef in clefs} - tablature if tablature else set()


def truth_of(pdf: Path) -> tuple[bytes, int, int | None, bool] | None:
    source = pdf.with_suffix(".musicxml")
    if source.exists():
        data = source.read_bytes()
        capo = int(ET.fromstring(data).findtext(".//staff-details/capo") or 0)
        return data, capo, None, pdf.parent == HERE
    hand = pdf.with_suffix(".truth.txt")
    if not hand.exists():
        return None
    head, _, body = hand.read_text().partition("\n")
    fields = dict(part.split("=", 1) for part in head.split())
    piece = Piece(pdf.stem, fields["tuning"].split(","), fields["meter"], bars(body), pickup=fields.get("pickup") == "yes")
    return musicxml(piece), int(fields.get("capo", 0)), len(piece.bars), False


def meters(data: bytes) -> list[str]:
    found, current = [], None
    for measure in ET.fromstring(data).find("part").findall("measure"):
        time = measure.find("attributes/time")
        if time is not None:
            current = f"{time.findtext('beats')}/{time.findtext('beat-type')}"
        found.append(current)
    return found


def tuning(data: bytes) -> list[int]:
    lines = ET.fromstring(data).find("part").findall(".//staff-details/staff-tuning")
    return [12 * (int(line.findtext("tuning-octave")) + 1) + STEPS[line.findtext("tuning-step")] + int(line.findtext("tuning-alter") or 0)
            for line in sorted(lines, key=lambda line: -int(line.get("line")))]


def midi_of(name: str) -> int:
    return 12 * (int(name[-1]) + 1) + STEPS[name[0]] + {"#": 1, "b": -1, "♯": 1, "♭": -1}.get(name[1:-1], 0)


def silent_bars(result: dict, wrong_meters: list[int], numbers: list[str], marked: set[int]) -> list[int]:
    wrong = {pair[0].bar if pair[0] else pair[1].bar for kind in SILENT_KINDS for pair in result[kind]} | set(wrong_meters)
    return sorted(position + 1 for position in wrong
                  if position >= len(numbers) or int(numbers[position]) not in marked)


def compare(truth: list[Note], read: list[Note], spelling: bool) -> dict[str, list]:
    left, extra = list(truth), list(read)
    result = {"found": [], "wrong length": [], "wrong pitch": [], "wrong tie": [], "wrong spelling": [],
              "wrong string or fret": [], "wrong onset": [], "missed": [], "extra": []}

    def take(test, kind):
        for expected in list(left):
            match = next((note for note in extra if test(expected, note)), None)
            if match is None:
                continue
            left.remove(expected)
            extra.remove(match)
            if kind != "found":
                result[kind].append((expected, match))
                continue
            result["found"].append((expected, match))
            for problem, differs in (("wrong length", expected.length != match.length), ("wrong pitch", expected.midi != match.midi),
                                     ("wrong tie", expected.tie_stop != match.tie_stop),
                                     ("wrong spelling", spelling and expected.midi == match.midi and expected.spelled != match.spelled)):
                if differs:
                    result[problem].append((expected, match))

    take(lambda a, b: (a.bar, a.onset, a.string, a.fret) == (b.bar, b.onset, b.string, b.fret), "found")
    take(lambda a, b: (a.bar, a.onset) == (b.bar, b.onset) and a.midi == b.midi, "wrong string or fret")
    take(lambda a, b: (a.bar, a.onset, a.string) == (b.bar, b.onset, b.string), "wrong string or fret")
    take(lambda a, b: (a.bar, a.string, a.fret) == (b.bar, b.string, b.fret), "wrong onset")
    result["missed"] = [(note, None) for note in left]
    result["extra"] = [(None, note) for note in extra]
    return result


def describe(note: Note | None) -> str:
    if note is None:
        return "-"
    return (f"bar {note.bar + 1} beat {float(note.onset) + 1:g} string {note.string} fret {note.fret} len {note.length} "
            f"{note.spelled}{'~' if note.tie_stop else ''}")


def measure(pdf: Path, details: bool) -> dict:
    name = pdf.stem
    known = truth_of(pdf)
    started = time.perf_counter()
    try:
        reading = read_tab(pdf.read_bytes())
    except Exception as error:
        return {"file": name, "outcome": f"CRASH {type(error).__name__}: {error}"}
    seconds = time.perf_counter() - started
    if reading is None:
        return {"file": name, "outcome": "refused"}
    read, read_bars = notes(reading.musicxml)
    row = {"file": name, "outcome": "read", "notes read": len(read), "bars read": read_bars, "doubtful": reading.doubtful,
           "tuning": " ".join(reading.tuning) + f" {reading.tuning_from}",
           "meter printed": reading.meter_printed, "seconds": round(seconds, 2)}
    if known is None:
        return row
    truth_data, capo, bar_limit, spelled = known
    truth, truth_bars = notes(truth_data, capo)
    if bar_limit:
        read = [note for note in read if note.bar < bar_limit]
    result = compare(truth, read, spelled and not capo)
    marked = set(problem_spots(reading.musicxml)[0]) | set(reading.doubtful)
    numbers = [measure.get("number") for measure in ET.fromstring(reading.musicxml).find("part").findall("measure")]
    wanted, got = meters(truth_data), meters(reading.musicxml)
    wrong_meters = [] if bar_limit else [position for position in range(len(wanted))
                                         if position >= len(got) or wanted[position] != got[position]]
    truth_tuning = tuning(truth_data)
    row.update({"notes": len(truth), "found": len(result["found"]),
                **{kind: len(pairs) for kind, pairs in result.items() if kind != "found"},
                "bars": truth_bars if not bar_limit else bar_limit, "wrong meter bars": len(wrong_meters),
                "tuning right": [midi_of(name) for name in reading.tuning] == truth_tuning if truth_tuning else None,
                "marked": sorted(marked), "silent wrong bars": silent_bars(result, wrong_meters, numbers, marked)})
    if details:
        for kind, pairs in result.items():
            if kind != "found":
                for expected, got_note in pairs:
                    print(f"   {name} {kind}: truth {describe(expected)} | read {describe(got_note)}")
        if wrong_meters:
            print(f"   {name} meters (bar, truth, read): {[(p + 1, wanted[p], got[p] if p < len(got) else None) for p in wrong_meters]}")
    return row


COLUMNS = [("file", "file"), ("outcome", "outcome"), ("notes", "notes"), ("found", "found"), ("wrong length", "len"),
           ("wrong onset", "onset"), ("wrong pitch", "pitch"), ("wrong string or fret", "fret"), ("missed", "missed"),
           ("extra", "extra"), ("bars", "bars"), ("bars read", "read"), ("wrong meter bars", "meter"),
           ("tuning right", "tuning ok"), ("tuning", "tuning"), ("notes read", "notes read"), ("doubtful", "doubtful"),
           ("meter printed", "meter printed"), ("marked", "shaded or doubtful"),
           ("silent wrong bars", "wrong in silence")]


def table(rows: list[dict]) -> str:
    def cell(row, key):
        value = row.get(key, "")
        if isinstance(value, list):
            return "-" if not value else " ".join(map(str, value)) if len(value) < 9 else f"{len(value)} bars"
        return "" if value is None else str(value)
    lines = ["| " + " | ".join(title for _, title in COLUMNS) + " |", "|" + "---|" * len(COLUMNS)]
    lines += ["| " + " | ".join(cell(row, key) for key, _ in COLUMNS) + " |" for row in rows]
    silent = sum(len(row.get("silent wrong bars", [])) for row in rows)
    wrong_files = [row["file"] for row in rows if row.get("silent wrong bars")]
    return "\n".join(lines) + f"\n\nBars wrong in silence: {silent}, in {len(wrong_files)} files"


def main(arguments: list[str]) -> None:
    details = "--details" in arguments
    names = [argument for argument in arguments if not argument.startswith("--")]
    pdfs = [pdf for folder in FOLDERS for pdf in sorted(folder.glob("*.pdf"))]
    rows = [measure(pdf, details) for pdf in pdfs if not names or any(pdf.stem.startswith(name) for name in names)]
    print(table(rows))


if __name__ == "__main__":
    main(sys.argv[1:])
