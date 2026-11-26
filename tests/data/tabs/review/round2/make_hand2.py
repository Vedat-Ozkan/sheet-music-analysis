from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "hand"))

from make_hand import line, pdf, tab, text  # noqa: E402

from engine.read_pdf import problem_spots  # noqa: E402
from engine.read_tab import read_tab  # noqa: E402

HAND = HERE / "hand"
XS = [90, 140, 190, 240, 340, 390, 440, 490]
PLAIN = [(x, 1 + index % 6, str(index % 5)) for index, x in enumerate(XS)]
STANDARD = "E4 B3 G3 D3 A2 E2"
BASS = "G2 D2 A1 E1"


def form(rows, columns, lift, step=18, top=700):
    ys = [top - step * index for index in range(6)]
    content = [text(60, 740, "Weekly count sheet", 14)]
    content += [line(60, y, 550, y) for y in ys]
    content += [line(x, ys[-1], x, ys[0]) for x in columns]
    for y, row in zip(ys, rows):
        for x, value in zip(columns, row):
            content.append(text(x + 40, y + lift, value))
    return content


def chart():
    ys = [600 - 30 * index for index in range(6)]
    content = [text(90, 660, "Visitors per month", 14)]
    content += [line(90, y, 530, y, 0.4) for y in ys]
    content += [line(x, ys[-1], x, ys[0], 0.4) for x in range(90, 531, 88)]
    content += [text(76, y - 3.2, value) for y, value in zip(ys, ["50", "40", "30", "20", "10", "0"])]
    content += [text(x, ys[-1] - 16, value) for x, value in zip(range(125, 500, 88), ["Jan", "Feb", "Mar", "Apr", "May"])]
    return content


def system(frets, top, joined=None):
    content = tab(frets, top=top)
    if joined is not None:
        content.append(line(60, joined, 60, top))
    return content


def timed(content, top=650):
    return content + [text(68, top - 16, "4", 16), text(68, top - 34, "4", 16)]


def hidden_part():
    one = [(x, 1, str(n)) for x, n in zip(XS, [1, 2, 3, 4, 5, 6, 7, 8])]
    two = [(x, 6, str(n)) for x, n in zip(XS, [1, 2, 3, 4, 5, 6, 7, 8])]
    content = []
    content += timed(system(one, 700, joined=560), 700) + timed(system(two, 600), 600)
    content += system([(x, 6, "9") for x in XS], 480)
    content += system(one, 360, joined=220) + system(two, 260)
    return content


def bend():
    content = tab([(90, 2, "8"), (140, 1, "7"), (190, 3, "9"), (240, 2, "8"), (340, 1, "5"), (390, 2, "5"), (440, 3, "7"), (490, 3, "5")])
    for x, y in ((96, 642), (196, 634)):
        content.append(f"0.8 w {x} {y} m {x + 14} {y} {x + 18} {y + 8} {x + 18} {y + 22} c S")
        content.append(f"{x + 15} {y + 21} m {x + 18} {y + 27} l {x + 21} {y + 21} l f")
        content.append(text(x + 10, y + 30, "full", 8))
    return content


def word_files():
    four = [(x, 1 + index % 4, str(index % 5)) for index, x in enumerate(XS)]

    def bass_tab(words):
        ys = [650 - 8 * index for index in range(4)]
        content = [line(60, y, 550, y) for y in ys] + [line(x, ys[-1], x, ys[0]) for x in (60, 305, 550)]
        for x, string, value in four:
            content.append(f"1 g {x - 1:.2f} {ys[string - 1] - 4:.2f} 7 8 re f 0 g")
            content.append(text(x, ys[string - 1] - 3.2, value))
            content.append(line(x + 2.5, ys[-1] - 6, x + 2.5, ys[-1] - 28))
        content += [text(60, 720 - 12 * index, value, 10) for index, value in enumerate(words)]
        return content

    def one(*words):
        return pdf([tab(PLAIN, words=words)])

    dadgad = "D4 A3 G3 D3 A2 D2"
    drop_d = "E4 B3 G3 D3 A2 D2"
    half = "D#4 A#3 F#3 C#3 G#2 D#2"
    return {
        "t01-tuning-dadgad": (one("Tuning: DADGAD"), dadgad, 0),
        "t02-drop-D-tuning": (one("drop D tuning"), drop_d, 0),
        "t03-drop-d-lower-tuning": (one("drop d tuning"), drop_d, 0),
        "t04-drop-d-lower-alone": (one("drop d"), drop_d, 0),
        "t05-Dropped-D": (one("Dropped D"), drop_d, 0),
        "t06-Drop-D-hyphen": (one("Drop-D"), drop_d, 0),
        "t07-sixth-string-D": (one("6th string = D"), drop_d, 0),
        "t08-DADGAD-alone": (one("DADGAD"), dadgad, 0),
        "t09-capo-II": (one("Capo II"), STANDARD, 2),
        "t10-capo-3rd-fret": (one("Capo: 3rd fret"), STANDARD, 3),
        "t11-standard-capo-4": (one("Standard tuning, capo 4"), STANDARD, 4),
        "t12-standard-capo-3rd": (one("Standard tuning, capo 3rd fret"), STANDARD, 3),
        "t13-tuning-line-capo-5th": (one("Tuning: DADGAD", "Capo on 5th fret"), dadgad, 5),
        "t14-half-step-down": (one("Half step down"), half, 0),
        "t15-semitone-down": (one("Down one semitone"), half, 0),
        "t16-beat-drop-A": (one("Beat drop A"), STANDARD, 0),
        "t17-irish-tune-title": (one("An Irish Tune"), STANDARD, 0),
        "t18-tuning-on-page-2": (pdf([tab(PLAIN), tab(PLAIN, words=("Tuning: D A D G B E",))]), "page 1 standard, page 2 drop D", 0),
        "t19-ukulele-title": (pdf([bass_tab(("Ukulele",))]), "A4 E4 C4 G4", 0),
        "t20-bouzouki-title": (pdf([bass_tab(("Bouzouki",))]), "D4 A3 D3 G2", 0),
        "t21-baritone-title": (one("Baritone guitar"), "B3 F#3 D3 A2 E2 B1", 0),
    }


def other_files():
    forms = [["12", "30", "7", "41"], ["8", "2", "19", "4"], ["31", "5", "60", "1"], ["22", "14", "9", "3"], ["6", "17", "25", "50"],
             ["11", "4", "2", "18"]]
    columns = [60, 180, 300, 420, 550]
    plain_rows = [[str(n) for n in row] for row in forms]
    return {
        "g1-form-numbers-on-rules": pdf([form(plain_rows, columns[:-1], -3.2) + [line(550, 610, 550, 700)]]),
        "g2-form-written-on-rules": pdf([form(plain_rows, columns[:-1], 1.0) + [line(550, 610, 550, 700)]]),
        "g3-line-chart": pdf([chart()]),
        "h1-dead-notes-open-line": pdf([timed(tab([(90, 4, "x"), (90, 5, "x"), (140, 4, "x"), (140, 5, "x"), (190, 3, "2"),
                                                   (240, 2, "3"), (340, 1, "0"), (390, 2, "1"), (440, 3, "2"), (490, 4, "2")]))]),
        "h2-line-of-dead-notes": pdf([timed(tab(PLAIN, top=700), 700) + tab([(x, s, "x") for x in XS for s in (3, 4)], top=600)
                                      + tab(PLAIN, top=500)]),
        "h3-ghost-after-same-fret": pdf([timed(tab([(90, 1, "5"), (140, 1, "(5)"), (190, 3, "2"), (240, 4, "2"), (340, 4, "0"),
                                                    (390, 3, "2"), (440, 2, "3"), (490, 1, "0")]))]),
        "h4-bend-arrows": pdf([timed(bend())]),
        "h5-second-tab-hidden": pdf([hidden_part()]),
    }


def listing(reading):
    found = []
    for part_number, part in enumerate(ET.fromstring(reading.musicxml).findall("part"), 1):
        for position, measure in enumerate(part.findall("measure"), 1):
            for note in measure.findall("note"):
                string = note.findtext("notations/technical/string")
                if string:
                    found.append(f"P{part_number}.{position}:{string}-{note.findtext('notations/technical/fret')}"
                                 f"({note.findtext('type')}{'~' if note.find('tie') is not None else ''})")
    return found


def main():
    HAND.mkdir(exist_ok=True)
    for name, (data, wanted, capo) in word_files().items():
        (HAND / f"{name}.pdf").write_bytes(data)
        reading = read_tab(data)
        if reading is None:
            print(f"{name}: REFUSED")
            continue
        got = " ".join(reading.tuning)
        verdict = ("right" if got == wanted and reading.capo == capo else
                   "MARKED (unclear)" if reading.tuning_from == "unclear" else "WRONG IN SILENCE")
        print(f"{name}: wanted {wanted} capo {capo} | read {got} capo {reading.capo} from {reading.tuning_from} -> {verdict}")
    for name, data in other_files().items():
        (HAND / f"{name}.pdf").write_bytes(data)
        reading = read_tab(data)
        if reading is None:
            print(f"{name}: REFUSED")
            continue
        bars = len(ET.fromstring(reading.musicxml).find("part").findall("measure"))
        print(f"{name}: READ notes {reading.notes} bars {bars} doubtful {reading.doubtful} unread {reading.unread} "
              f"shaded {problem_spots(reading.musicxml)[0]}\n    {' '.join(listing(reading))}")


if __name__ == "__main__":
    main()
