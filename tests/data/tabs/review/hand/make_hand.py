from __future__ import annotations

import io
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from engine.read_tab import read_tab

HAND = Path(__file__).parent / "hand"


def pdf(pages, width=612, height=792):
    objects = ["<< /Type /Catalog /Pages 2 0 R >>", None,
               "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
               "<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>"]
    kids = []
    for content in pages:
        stream = "\n".join(content)
        objects.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] /Contents {len(objects)} 0 R "
                       "/Resources << /Font << /H 3 0 R /C 4 0 R >> >> >>")
        kids.append(f"{len(objects)} 0 R")
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"
    out = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n".encode("latin-1")
    start = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{offset:010} 00000 n \n" for offset in offsets).encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode()
    return out


def text(x, y, value, size=9, font="H"):
    value = value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return f"BT /{font} {size} Tf {x:.2f} {y:.2f} Td ({value}) Tj ET"


def line(x0, y0, x1, y1, width=0.6):
    return f"{width} w {x0:.2f} {y0:.2f} m {x1:.2f} {y1:.2f} l S"


def table(rules, rows, title, step=18, left=60, right=550):
    content = [text(left, 740, title, 16)]
    ys = [700 - step * index for index in range(rules)]
    content += [line(left, y, right, y) for y in ys]
    for y, row in zip(ys, rows):
        for column, value in enumerate(row):
            content.append(text(left + 10 + column * 100, y - step / 2 - 3.2, value))
    return content


def tab(frets, stems=True, words=(), top=650, gap=8):
    ys = [top - gap * index for index in range(6)]
    content = [line(60, y, 550, y) for y in ys]
    content += [line(x, ys[-1], x, ys[0]) for x in (60, 305, 550)]
    for x, string, value in frets:
        content.append(f"1 g {x - 1:.2f} {ys[string - 1] - 4:.2f} {len(value) * 5 + 2} 8 re f 0 g")
        content.append(text(x, ys[string - 1] - 3.2, value))
    if stems:
        for x in sorted({x for x, _, _ in frets}):
            content.append(line(x + 2.5, ys[-1] - 6, x + 2.5, ys[-1] - 28))
    content += [text(60, 720 - 12 * index, value, 10) for index, value in enumerate(words)]
    return content


def files():
    xs = [90, 140, 190, 240, 340, 390, 440, 490]
    plain = [(x, 1 + index % 6, str(index % 5)) for index, x in enumerate(xs)]
    return {
        "g1-table-3-rules": pdf([table(4, [["12", "3", "450", "7"], ["8", "2", "19", "4"], ["31", "5", "60", "1"]], "Opening hours 2026")]),
        "g2-table-5-rules": pdf([table(6, [["1", "2", "15", "30"], ["2", "1", "20", "20"], ["3", "4", "5", "20"], ["4", "6", "2", "12"],
                                           ["5", "3", "9", "27"]], "Invoice 1024")]),
        "g3-table-6-rules": pdf([table(7, [[str(i), str(i * 3), str(i * 7), "2026"] for i in range(1, 7)], "Results")]),
        "g4-table-text-and-numbers": pdf([table(6, [["Bach", "BWV 846", "1722", "4 min"], ["Chopin", "Op. 9", "1832", "5 min"],
                                                    ["Satie", "No. 1", "1888", "3 min"], ["Sor", "Op. 35", "1828", "2 min"],
                                                    ["Giuliani", "Op. 50", "1814", "6 min"]], "Recital programme")]),
        "g5-ascii-tab": pdf([[text(60, 700 - 14 * i, f"{name}|--0--2--3--5--|--7--5--3--2--|", 11, "C") for i, name in enumerate("eBGDAE")]]),
        "h1-hand-tab": pdf([tab(plain)]),
        "h2-dead-and-hammer": pdf([tab([(90, 1, "x"), (140, 1, "3"), (190, 1, "5h7"), (240, 2, "7/9"), (340, 2, "5"), (390, 3, "x"),
                                        (440, 3, "2b4"), (490, 3, "2")])]),
        "h3-ghost-notes": pdf([tab([(90, 1, "5"), (140, 2, "3"), (190, 3, "2"), (240, 4, "2"), (340, 4, "0"), (390, 3, "2"),
                                    (440, 2, "3"), (490, 1, "(5)")])]),
        "h4-no-rhythm": pdf([tab(plain, stems=False)]),
        "h5-da-capo-words": pdf([tab(plain, words=("Play da capo 2 times",))]),
        "h6-drop-c-words": pdf([tab(plain, words=("Drop C",))]),
        "h7-drop-a-story": pdf([tab(plain, words=("Let the volume drop a little in bar 2",))]),
        "h8-tuning-words": pdf([tab(plain, words=("Tuning: Eb Ab Db Gb Bb Eb",))]),
        "h9-capo-on-page-2": pdf([tab(plain), tab(plain, words=("Capo 3",))]),
    }


def broken():
    good = pdf([tab([(90, 1, "5"), (140, 2, "3")])])
    found = {"x1-empty": b"", "x2-not-a-pdf": b"hello, this is not a PDF", "x3-truncated": good[: len(good) // 2],
             "x4-no-pages": pdf([]), "x5-blank-page": pdf([[]])}
    for name, user in (("x6-encrypted-user-password", "secret"), ("x7-encrypted-empty-password", "")):
        writer = PdfWriter()
        writer.append(PdfReader(io.BytesIO(good)))
        writer.encrypt(user_password=user, owner_password="owner", algorithm="RC4-128")
        out = io.BytesIO()
        writer.write(out)
        found[name] = out.getvalue()
    return found


def main():
    HAND.mkdir(exist_ok=True)
    for name, data in {**files(), **broken()}.items():
        (HAND / f"{name}.pdf").write_bytes(data)
        try:
            reading = read_tab(data)
        except Exception as error:
            print(f"{name}: CRASH {type(error).__module__}.{type(error).__name__}: {error}")
            continue
        if reading is None:
            print(f"{name}: REFUSED")
            continue
        import xml.etree.ElementTree as ET
        notes = []
        for position, measure in enumerate(ET.fromstring(reading.musicxml).iter("measure"), 1):
            for note in measure.findall("note"):
                string = note.findtext("notations/technical/string")
                if string:
                    notes.append(f"{position}:{string}-{note.findtext('notations/technical/fret')}({note.findtext('type')}"
                                 f"{'~' if note.find('tie') is not None else ''})")
        print(f"{name}: READ {len(notes)} notes, doubtful {reading.doubtful}, tuning {reading.tuning} printed {reading.tuning_printed} "
              f"capo {reading.capo}\n    {' '.join(notes)}")


if __name__ == "__main__":
    main()
