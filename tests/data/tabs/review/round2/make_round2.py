from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))

from make_files import B, BASS, EIGHTS, GUITAR, SCALE, convert, score_xml, tempo, with_signs, words  # noqa: E402

FILES = HERE
QUARTERS = "q:3-0 q:3-2 q:2-0 q:2-1"
REST = {"voices": [["w:r"]], "fullrest": True}


def single(name, bars, **extra):
    return {"name": name, "tuning": GUITAR, "bars": bars, **extra}


def many(name, parts):
    return {"name": name, "parts": parts}


def edit(xml, part, bar, note, group, fragment):
    root = ET.fromstring(xml)
    measure = root.findall("part")[part].findall("measure")[bar]
    target = measure.findall("note")[note]
    notations = target.find("notations")
    if notations is None:
        notations = ET.SubElement(target, "notations")
    if group:
        holder = notations.find(group)
        if holder is None:
            holder = ET.SubElement(notations, group)
    else:
        holder = notations
    holder.append(ET.fromstring(fragment))
    return ET.tostring(root, encoding="unicode")


def edits(*changes):
    def apply(xml):
        for change in changes:
            xml = edit(xml, *change)
        return xml
    return apply


def joined_barlines(xml):
    start = ('<part-group type="start" number="1"><group-symbol>bracket</group-symbol>'
             "<group-barline>yes</group-barline></part-group>")
    xml = xml.replace("<part-list>", "<part-list>" + start, 1)
    return xml.replace("</part-list>", '<part-group type="stop" number="1"/></part-list>', 1)


def hide_rest(bar_number):
    def apply(xml):
        root = ET.fromstring(xml)
        measure = root.find("part").findall("measure")[bar_number]
        for note in measure.findall("note"):
            note.set("print-object", "no")
        return ET.tostring(root, encoding="unicode")
    return apply


def dashed(label, kind, placement="above"):
    if kind == "start":
        return (f'<direction placement="{placement}"><direction-type><words>{label}</words></direction-type>'
                '<direction-type><dashes type="start" number="1"/></direction-type></direction>')
    return f'<direction placement="{placement}"><direction-type><dashes type="stop" number="1"/></direction-type></direction>'


def pieces():
    found = []
    add = found.append
    add(single("r1-one-bar", [B("q:3-0 q:3-2 q:2-0 q:2-1")]))
    add(single("r1-bar-per-system", [B(EIGHTS), B(SCALE, newsystem=True), B("h:1-3 h:2-5", newsystem=True),
                                     B("w:1-0", newsystem=True)]))
    add({**single("r1-three-digit", [B(EIGHTS, before=[tempo(120), words("144")]), B(SCALE, before=[words("100", placement="below")]),
                                     B(EIGHTS, before=[words("365 days")]), B("w:1-12+2-10")] * 3,
                  style={"showMeasureNumber": 1, "measureNumberInterval": 1, "measureNumberSystem": 0}), "first_number": 101})

    add(single("r3-dotted-halves", [B("h.:1-0"), B("h.:2-1"), B("h.:3-2+4-2"), B("h.:5-3"), B("h.:1-3+2-0"), B("h.:6-0")] * 2,
               meter="3/4"))
    add(single("r3-12-8", [B("e:1-0 e:2-1 e:3-2 e:4-2 e:3-2 e:2-1 e:1-0 e:2-1 e:3-2 e:4-2 e:3-2 e:2-1"),
                           B("q.:1-3 q.:1-5 q.:2-5 q.:2-3"), B("h.:3-2 h.:4-2"),
                           B("q:2-0 e:2-1 q:2-3 e:2-5 q:1-0 e:1-1 q.:1-3"), B("w.:1-0")], meter="12/8"))
    add(single("r3-quarter-triplets", [B("q/3:1-0 q/3:2-1 q/3:3-2 h:4-2"), B("h:5-3 q/3:1-3 q/3:1-5 q/3:1-7"),
                                       B("q/3:1-0 q/3:r q/3:3-2 h:4-2"), B("q/3:r q/3:2-1 q/3:3-2 q:4-2 q:5-3"),
                                       B(QUARTERS)]))
    add({**single("r3-uneven-triplet", [B("q/3:1-0 e/3:2-1 q:3-2 h:4-2"), B("e:1-0 e:2-1 q/3:1-3 e/3:1-5 h:2-5"),
                                        B(SCALE), B(EIGHTS)]),
         "change": edits((0, 0, 1, None, '<tuplet type="stop"/>'), (0, 1, 3, None, '<tuplet type="stop"/>'))})
    add(single("r3-fingering-triplet", [B("e/3:1-0f3 e/3:2-1 e/3:3-2 q:4-2f3 h:5-3"),
                                        B("e:1-0 e:2-1f3 e/3:4-2 e/3:4-0 e/3:3-0 h:2-3"),
                                        B("e/3:1-0 e/3:2-1 e/3:3-2f3 e:4-2f3 e:5-3f3 h:2-1"),
                                        B("q:1-0f3 q:2-1f3 q:3-2f3 q:4-2f3")]))
    add(single("r3-short-bar", [B(QUARTERS), B("q:1-0 q:1-1 q:1-3 q:1-5"), B("q:2-1 q:2-3"), B(QUARTERS), B("q:3-0 q:3-2 q:2-0 q:2-1"),
                                B(QUARTERS)]))
    add(single("r3-two-short-bars", [B(SCALE), B(EIGHTS), B("q:2-1 q:2-3 q:2-5"), B("q:1-7"), B(SCALE), B(EIGHTS)]))
    add(single("r3-short-bar-eighths", [B(SCALE), B(EIGHTS), B("q:2-1 q:2-3 e:2-5 e:2-6"), B(SCALE), B(EIGHTS), B(SCALE)]))

    add(single("r4-multirest-2-12", [B(EIGHTS), {**REST, "multirest": 2}, dict(REST), B(SCALE), {**REST, "multirest": 12},
                                     *[dict(REST) for _ in range(11)], B(SCALE), B("w:1-0")],
               style={"createMultiMeasureRests": 1}))
    changing = [B(SCALE, key=-7), B(EIGHTS), B(SCALE), B(EIGHTS, key=7, newsystem=True), B(SCALE), B(EIGHTS),
                B(SCALE, key=-7, time="2/2", newsystem=True), B(EIGHTS), B("w:1-0")]
    add(many("r4-courtesy-staff-tab", [{"part": "Guitar", "standard": True, "bars": changing},
                                       {"part": "Tab", "bars": changing}]))
    lead = [B(EIGHTS), B(SCALE), B("h:1-5 h:1-7"), B(EIGHTS), B(SCALE, newsystem=True), B("w:1-0")]
    low = [B("h:6-0 h:6-3"), B("w:5-3"), B("q:5-0 q:5-2 q:4-0 q:4-2"), B("w:6-0"), B("h:6-1 h:5-1"), B("w:6-0")]
    three = [{"part": "Guitar 1", "standard": True, "bars": lead}, {"part": "Tab 1", "bars": lead}, {"part": "Tab 2", "bars": low}]
    add(many("r4-staff-tab-tab", three))
    add({**many("r4-joined-tabs", [{"part": "Tab 1", "bars": lead}, {"part": "Tab 2", "bars": low}]), "change": joined_barlines})
    add({**many("r4-joined-staff-tab-tab", three), "change": joined_barlines})
    add({**many("r4-tab-above-staff", [{"part": "Tab", "bars": lead}, {"part": "Guitar", "standard": True, "bars": lead}]),
         "change": joined_barlines})
    bass = [B("h:4-0 h:4-3"), B("w:3-3"), B("q:3-0 q:3-2 q:2-0 q:2-2"), B("w:4-0"), B("h:4-1 h:3-1"), B("w:4-0")]
    add(many("r4-guitar-and-bass", [{"part": "Guitar", "bars": lead}, {"part": "Bass", "tuning": BASS, "bars": bass}]))
    add(single("r4-pickup-endings", [B("q:3-2"), B(SCALE, left='<repeat direction="forward"/>'), B(EIGHTS), B(SCALE),
                                     B("h.:1-3", left='<ending number="1" type="start">1.</ending>',
                                       right='<ending number="1" type="stop"/><repeat direction="backward"/>'),
                                     B("w:1-0", left='<ending number="2" type="start">2.</ending>',
                                       right='<ending number="2" type="discontinue"/>'),
                                     B(EIGHTS), B("w:6-0")], pickup=True))
    hidden = [B(QUARTERS) for _ in range(5)] + [dict(REST)] + [B(EIGHTS, newsystem=True), B(SCALE), B("w:1-0")]
    add({**single("r4-hidden-rest-line-end", hidden), "change": hide_rest(5)})

    add({**single("r5-hammer-pull", [B("q:1-0 q:1-3 q:2-3 q:2-1"), B("e:3-0 e:3-2 e:3-0 e:3-2 h:2-1"), B(SCALE)]),
         "change": edits((0, 0, 0, "technical", '<hammer-on type="start" number="1">H</hammer-on>'),
                         (0, 0, 1, "technical", '<hammer-on type="stop" number="1"/>'),
                         (0, 0, 2, "technical", '<pull-off type="start" number="1">P</pull-off>'),
                         (0, 0, 3, "technical", '<pull-off type="stop" number="1"/>'),
                         (0, 0, 0, None, '<slur type="start" number="1"/>'), (0, 0, 1, None, '<slur type="stop" number="1"/>'),
                         (0, 0, 2, None, '<slur type="start" number="1"/>'), (0, 0, 3, None, '<slur type="stop" number="1"/>'))})
    add({**single("r5-slides", [B("q:1-3 q:1-7 q:2-8 q:2-5"), B("h:3-2 h:3-9"), B(SCALE)]),
         "change": edits((0, 0, 0, None, '<slide type="start" number="1" line-type="solid"/>'),
                         (0, 0, 1, None, '<slide type="stop" number="1" line-type="solid"/>'),
                         (0, 0, 2, None, '<glissando type="start" number="1" line-type="solid"/>'),
                         (0, 0, 3, None, '<glissando type="stop" number="1" line-type="solid"/>'),
                         (0, 1, 0, None, '<slide type="start" number="1" line-type="solid"/>'),
                         (0, 1, 1, None, '<slide type="stop" number="1" line-type="solid"/>'))})
    add({**single("r5-bends", [B("q:2-8 q:2-10 q:1-7 q:3-9"), B("h:2-8 h:3-7"), B(SCALE)]),
         "change": edits((0, 0, 0, "technical", "<bend><bend-alter>2</bend-alter></bend>"),
                         (0, 0, 2, "technical", "<bend><bend-alter>1</bend-alter></bend>"),
                         (0, 1, 0, "technical", "<bend><bend-alter>2</bend-alter></bend>"),
                         (0, 1, 0, "technical", "<bend><bend-alter>-2</bend-alter><release/></bend>"))})
    add({**single("r5-vibrato", [B("h:2-8 h:3-7"), B("w:1-5"), B(SCALE)]),
         "change": edits((0, 0, 0, "ornaments", '<wavy-line type="start" number="1"/>'),
                         (0, 0, 0, "ornaments", '<wavy-line type="stop" number="1"/>'),
                         (0, 1, 0, "ornaments", '<trill-mark/>'),
                         (0, 1, 0, "ornaments", '<wavy-line type="start" number="2"/>'),
                         (0, 1, 0, "ornaments", '<wavy-line type="stop" number="2"/>'))})
    add(single("r5-let-ring-pm", [B(EIGHTS, before=[dashed("let ring", "start")]), B(SCALE, before=[dashed("let ring", "stop")]),
                                  B(EIGHTS, before=[dashed("P.M.", "start", "below")]),
                                  B(SCALE, before=[dashed("P.M.", "stop", "below")])]))
    add({**single("r5-harmonics", [B("q:1-12 q:2-12 q:3-7 q:4-5"), B("h:5-12 h:6-7"), B(SCALE)]),
         "change": edits((0, 0, 0, "technical", "<harmonic><natural/></harmonic>"),
                         (0, 0, 1, "technical", "<harmonic><natural/><touching-pitch/></harmonic>"),
                         (0, 0, 2, "technical", "<harmonic><artificial/></harmonic>"),
                         (0, 0, 3, "technical", "<harmonic/>"),
                         (0, 1, 0, "technical", "<harmonic><natural/></harmonic>"))})
    add(single("r5-grace-line-start", [B("s:1-3g q:1-5 q:2-1 q:3-2 q:4-2"), B(SCALE), B("s:2-3g h:2-5 h:3-2", newsystem=True),
                                       B(SCALE)]))

    mixed = [B("q:3-2", before=[tempo(96), words("Capo 2")])]
    theme = [B("e:1-0 e:2-1 e:3-2 e:4-2 q:1-3 q:1-5", "h:6-0 h:5-3"), B("q:2-1 q:2-3 h:1-0", "w:5-0"),
             B("e/3:1-0 e/3:1-1 e/3:1-3 q:1-5 h:1-7", "h:4-2 h:5-3"), B("q.:2-3 e:2-1 q:3-2 q:3-0", "h.:6-3 q:r"),
             B("s:1-0 s:1-1 s:1-3 s:1-5 e:1-7 e:1-8 h:1-10", "w:5-3"), B("h:r q:1-3 q:1-5", "q:5-0 q:5-2 h:r"),
             B("w:r", "q:6-0 q:6-3 q:5-0 q:5-2"), B("h.:1-12 q:2-10~", "h:4-2 h:5-3")]
    second = [B("q:2-10 q:2-8 h:2-5", "h:6-1 h:5-1"), B("e:1-0 q:2-1 e:3-2 h:4-2", "h:6-0 h:5-0"),
              B("q:1-0 q:1-1 q:1-3", "h.:6-0", time="3/4"), B("h:2-1 q:2-3", "h.:5-3"), B("h.:1-0", "h.:6-0"),
              B("e:1-0 e:1-1 e:1-3 e:1-5 e:1-7 e:1-8", "q:5-0 q:4-0 q:3-0"), B("q:2-5 h:2-6", "h.:6-3"), B("h.:3-2", "h.:5-0")]
    again = [B(EIGHTS, time="4/4", key=2), B(SCALE), B("q:1-3 e:1-5 e:1-7 h:2-5"), B("e:6-3 e:6-5 e:5-2 e:5-3 q:4-0 q:4-2"),
             B("h:3-4 q:2-7 q:1-8"), B("w:1-0+2-1+3-0"), dict(REST), B(SCALE)]
    mixed += theme + second + again + [dict(bar) for bar in theme] + [dict(bar) for bar in second[:6]] + [B("h.:1-0", "h.:6-0")]
    add({**single("m1-mixed-piece", mixed, pickup=True),
         "change": edits((0, 3, 0, "technical", '<fingering>3</fingering>'),
                         (0, 18, 0, "technical", '<hammer-on type="start" number="1">H</hammer-on>'),
                         (0, 18, 1, "technical", '<hammer-on type="stop" number="1"/>'),
                         (0, 20, 0, "technical", "<harmonic><natural/></harmonic>"),
                         (0, 21, 0, "technical", "<bend><bend-alter>2</bend-alter></bend>"))})
    return found


def main(names):
    FILES.mkdir(parents=True, exist_ok=True)
    for item in pieces():
        name = item["name"]
        if names and not any(name.startswith(prefix) for prefix in names):
            continue
        xml = score_xml(item)
        if "change" in item:
            xml = item["change"](xml)
        if "first_number" in item:
            root = ET.fromstring(xml.encode())
            for index, measure in enumerate(root.find("part").findall("measure")):
                measure.set("number", str(item["first_number"] + index))
            xml = ET.tostring(root, encoding="unicode")
        source = FILES / f"{name}.musicxml"
        source.write_bytes(with_signs(xml))
        style = None
        if "style" in item:
            style = FILES / f"{name}.mss"
            style.write_text('<?xml version="1.0" encoding="UTF-8"?><museScore version="4.20"><Style>'
                             + "".join(f"<{k}>{v}</{k}>" for k, v in item["style"].items()) + "</Style></museScore>")
        target = FILES / f"{name}.pdf"
        target.unlink(missing_ok=True)
        done = convert(source, target, style)
        print(name, done.returncode, target.stat().st_size if target.exists() else "NO PDF", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
