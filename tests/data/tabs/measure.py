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
                if string is None or element.find("pitch") is None:
                    continue
                step = element.findtext("pitch/step")
                alter = int(element.findtext("pitch/alter") or 0)
                midi = 12 * (int(element.findtext("pitch/octave")) + 1) + STEPS[step] + alter + capo
                spelled = step + {1: "#", -1: "b", 2: "##", -2: "bb"}.get(alter, "")
                found.append(Note(position, onset, int(string), int(element.findtext("notations/technical/fret")),
                                  length, midi, any(tie.get("type") == "stop" for tie in element.findall("tie")), spelled))
    return found, count


def truth_of(name: str) -> tuple[bytes, int, int | None]:
    source = HERE / f"{name}.musicxml"
    if source.exists():
        data = source.read_bytes()
        capo = int(ET.fromstring(data).findtext(".//staff-details/capo") or 0)
        return data, capo, None
    text = (USERS / f"{name}.truth.txt").read_text()
    head, _, body = text.partition("\n")
    fields = dict(part.split("=", 1) for part in head.split())
    piece = Piece(name, fields["tuning"].split(","), fields["meter"], bars(body), pickup=fields.get("pickup") == "yes")
    return musicxml(piece), int(fields.get("capo", 0)), len(piece.bars)


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


def measure(pdf: Path) -> None:
    name = pdf.stem
    truth_data, capo, bar_limit = truth_of(name)
    started = time.perf_counter()
    reading = read_tab(pdf.read_bytes())
    seconds = time.perf_counter() - started
    if reading is None:
        print(f"{name}: NO TABLATURE READ ({seconds:.1f} s)")
        return
    truth, truth_bars = notes(truth_data, capo)
    read, read_bars = notes(reading.musicxml)
    if bar_limit:
        read = [note for note in read if note.bar < bar_limit]
    result = compare(truth, read, not capo)
    shaded = problem_spots(reading.musicxml)[0]
    counts = ", ".join(f"{kind} {len(pairs)}" for kind, pairs in result.items() if kind != "found")
    print(f"{name}: {len(truth)} notes, found {len(result['found'])}; {counts}; bars truth {truth_bars if not bar_limit else bar_limit} "
          f"read {read_bars}; doubtful {reading.doubtful}; shaded {shaded}; tuning {' '.join(reading.tuning)} "
          f"({'printed' if reading.tuning_printed else 'assumed'}), capo {reading.capo}; "
          f"{reading.pages} pages, {seconds:.2f} s, {seconds / reading.pages:.2f} s per page")
    for kind, pairs in result.items():
        if kind == "found":
            continue
        for expected, got in pairs:
            print(f"   {kind}: truth {describe(expected)} | read {describe(got)}")


def main(names: list[str]) -> None:
    pdfs = sorted(HERE.glob("*.pdf")) + sorted(USERS.glob("*.pdf"))
    for pdf in pdfs:
        has_truth = (HERE / f"{pdf.stem}.musicxml").exists() or (USERS / f"{pdf.stem}.truth.txt").exists()
        if (names and pdf.stem not in names) or not has_truth:
            continue
        measure(pdf)


if __name__ == "__main__":
    main(sys.argv[1:])
