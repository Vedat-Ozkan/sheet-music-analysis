from __future__ import annotations

import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path
from xml.sax.saxutils import escape

from engine import correct

HERE = Path(__file__).parent
FILES = HERE
MUSESCORE = "/mnt/c/Program Files/MuseScore 4/bin/MuseScore4.exe"
DIVISIONS = 960
GUITAR = ["E4", "B3", "G3", "D3", "A2", "E2"]
SEVEN = GUITAR + ["B1"]
BASS = ["G2", "D2", "A1", "E1"]
BASS5 = BASS + ["B0"]
UKULELE = ["A4", "E4", "C4", "G4"]
NATURAL = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
TYPES = {"w": ("whole", Fraction(4)), "h": ("half", Fraction(2)), "q": ("quarter", Fraction(1)),
         "e": ("eighth", Fraction(1, 2)), "s": ("16th", Fraction(1, 4)), "t": ("32nd", Fraction(1, 8)),
         "x": ("64th", Fraction(1, 16))}
NORMAL = {3: 2, 5: 4, 6: 4, 7: 4}
SPELL = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def midi(name):
    letter, octave = name[0], int(name[-1])
    alter = {"#": 1, "b": -1, "": 0}[name[1:-1]]
    return 12 * (octave + 1) + NATURAL[letter] + alter


def pitch_xml(value, tag="pitch", prefix=""):
    name = SPELL[value % 12]
    alter = f"<{prefix}alter>1</{prefix}alter>" if len(name) > 1 else ""
    return f"<{tag}><{prefix}step>{name[0]}</{prefix}step>{alter}<{prefix}octave>{value // 12 - 1}</{prefix}octave></{tag}>"


def parse(token):
    head, _, body = token.partition(":")
    kind = head[0]
    dots = head.count(".")
    tuplet = int(head.split("/")[1]) if "/" in head else 0
    notes = []
    if body != "r":
        for part in body.split("+"):
            match = re.fullmatch(r"(\d+)-(\d+)((?:f\d)?)(~?)((?:[xgh])?)", part)
            string, fret, finger, tie, mark = match.groups()
            notes.append({"string": int(string), "fret": int(fret), "finger": finger[1:], "tie": bool(tie), "mark": mark})
    length = TYPES[kind][1] * (2 - Fraction(1, 2 ** dots))
    if tuplet:
        length *= Fraction(NORMAL[tuplet], tuplet)
    return {"kind": kind, "dots": dots, "tuplet": tuplet, "notes": notes, "length": length}


def B(*voices, **extra):
    return {"voices": [voice.split() for voice in voices], **extra}


def words(text, circle=False, placement="above"):
    enclosure = ' enclosure="circle"' if circle else ""
    return f'<direction placement="{placement}"><direction-type><words{enclosure}>{escape(text)}</words></direction-type></direction>'


def rehearsal(text):
    return f'<direction placement="above"><direction-type><rehearsal>{escape(text)}</rehearsal></direction-type></direction>'


def tempo(number, unit="quarter"):
    return (f'<direction placement="above"><direction-type><metronome><beat-unit>{unit}</beat-unit><per-minute>{number}</per-minute>'
            f'</metronome></direction-type><sound tempo="{number}"/></direction>')


def part_xml(part_id, piece):
    tuning = piece["tuning"]
    opens = [midi(name) for name in tuning]
    meter = piece.get("meter", "4/4")
    out = [f'<part id="{part_id}">']
    tied = set()
    tuplet_count = 0
    for index, bar in enumerate(piece["bars"]):
        number = index if piece.get("pickup") else index + 1
        implicit = ' implicit="yes"' if piece.get("pickup") and index == 0 else ""
        out.append(f'<measure number="{number}"{implicit}>')
        if bar.get("newsystem"):
            out.append('<print new-system="yes"/>')
        if bar.get("newpage"):
            out.append('<print new-page="yes"/>')
        left = bar.get("left", "")
        if left:
            out.append(f'<barline location="left">{left}</barline>')
        attributes = []
        if index == 0:
            attributes.append(f"<divisions>{DIVISIONS}</divisions>")
        if index == 0 or "key" in bar:
            attributes.append(f"<key><fifths>{bar.get('key', 0)}</fifths></key>")
        if index == 0 or "time" in bar:
            meter = bar.get("time", meter)
            beats, unit = meter.split("/")
            symbol = f' symbol="{bar["symbol"]}"' if "symbol" in bar else ""
            attributes.append(f"<time{symbol}><beats>{beats}</beats><beat-type>{unit}</beat-type></time>")
        if index == 0:
            lines = len(tuning)
            if piece.get("percussion"):
                attributes.append("<clef><sign>percussion</sign></clef>")
            elif piece.get("standard"):
                attributes.append("<clef><sign>G</sign><line>2</line><clef-octave-change>-1</clef-octave-change></clef>")
            else:
                attributes.append(f"<clef><sign>TAB</sign><line>5</line></clef><staff-details><staff-lines>{lines}</staff-lines>")
                for line, name in enumerate(reversed(tuning), 1):
                    attributes.append(f"<staff-tuning line=\"{line}\"><tuning-step>{name[0]}</tuning-step>"
                                      + ("<tuning-alter>%d</tuning-alter>" % (1 if name[1] == "#" else -1) if len(name) > 2 else "")
                                      + f"<tuning-octave>{name[-1]}</tuning-octave></staff-tuning>")
                if piece.get("capo"):
                    attributes.append(f"<capo>{piece['capo']}</capo>")
                attributes.append("</staff-details>")
        if "multirest" in bar:
            attributes.append(f"<measure-style><multiple-rest>{bar['multirest']}</multiple-rest></measure-style>")
        if attributes:
            out.append("<attributes>" + "".join(attributes) + "</attributes>")
        out.extend(bar.get("before", []))
        lyrics = list(bar.get("lyrics", []))
        previous = Fraction(0)
        for voice_index, tokens in enumerate(bar["voices"]):
            if voice_index:
                out.append(f"<backup><duration>{int(previous * DIVISIONS)}</duration></backup>")
            previous = Fraction(0)
            events = [parse(token) for token in tokens]
            run = 0
            for event_index, event in enumerate(events):
                previous += event["length"]
                start_stop = ""
                if event["tuplet"]:
                    if run == 0:
                        tuplet_count += 1
                        start_stop = '<tuplet type="start" bracket="yes"/>'
                    run += 1
                    if run == event["tuplet"]:
                        start_stop = '<tuplet type="stop"/>'
                        run = 0
                duration = int(event["length"] * DIVISIONS)
                if not event["notes"] and len(events) == 1 and bar.get("fullrest"):
                    out.append(f'<note><rest measure="yes"/><duration>{duration}</duration><voice>{voice_index + 1}</voice></note>')
                    continue
                for position, note in enumerate(event["notes"] or [None]):
                    xml = ["<note>"]
                    if note and note["mark"] == "g":
                        xml.append("<grace/>")
                    if position:
                        xml.append("<chord/>")
                    if note is None:
                        xml.append("<rest/>")
                    elif piece.get("percussion"):
                        xml.append("<unpitched><display-step>C</display-step><display-octave>5</display-octave></unpitched>")
                    else:
                        xml.append(pitch_xml(opens[note["string"] - 1] + note["fret"]))
                    if not (note and note["mark"] == "g"):
                        xml.append(f"<duration>{duration}</duration>")
                    key = (voice_index, note["string"]) if note else None
                    held = key in tied
                    if held:
                        xml.append('<tie type="stop"/>')
                    if note and note["tie"]:
                        xml.append('<tie type="start"/>')
                    xml.append(f"<voice>{voice_index + 1}</voice><type>{TYPES[event['kind']][0]}</type>")
                    xml.append("<dot/>" * event["dots"])
                    if event["tuplet"]:
                        xml.append(f"<time-modification><actual-notes>{event['tuplet']}</actual-notes>"
                                   f"<normal-notes>{NORMAL[event['tuplet']]}</normal-notes></time-modification>")
                    if len(bar["voices"]) > 1 and note:
                        xml.append(f"<stem>{'up' if voice_index == 0 else 'down'}</stem>")
                    if note and note["mark"] == "x":
                        xml.append("<notehead>x</notehead>")
                    if note:
                        xml.append("<notations>")
                        if held:
                            xml.append('<tied type="stop"/>')
                        if note["tie"]:
                            xml.append('<tied type="start"/>')
                        tied.discard(key)
                        if note["tie"]:
                            tied.add(key)
                        if start_stop and not position:
                            xml.append(start_stop)
                        for slur_index, kind in bar.get("slurs", []):
                            if slur_index == event_index and not position:
                                xml.append(f'<slur type="{kind}" number="1" placement="above"/>')
                        technical = []
                        if not piece.get("standard") and not piece.get("percussion"):
                            technical.append(f"<string>{note['string']}</string><fret>{note['fret']}</fret>")
                        if note["finger"]:
                            technical.append(f"<fingering>{note['finger']}</fingering>")
                        if note["mark"] == "h":
                            technical.append("<harmonic><natural/></harmonic>")
                        if technical:
                            xml.append("<technical>" + "".join(technical) + "</technical>")
                        xml.append("</notations>")
                    elif start_stop:
                        xml.append("<notations>" + start_stop + "</notations>")
                    if lyrics and voice_index == 0 and not position and note:
                        xml.append(f"<lyric><syllabic>single</syllabic><text>{escape(lyrics.pop(0))}</text></lyric>")
                    xml.append("</note>")
                    out.append("".join(xml))
        right = bar.get("right", "")
        if right:
            out.append(f'<barline location="right">{right}</barline>')
        out.append("</measure>")
    out.append("</part>")
    return "".join(out)


def score_xml(piece):
    parts = piece.get("parts") or [piece]
    head = [f'<?xml version="1.0" encoding="UTF-8"?><score-partwise version="4.0"><work><work-title>{piece["name"]}</work-title></work>']
    if "scale" in piece or "page" in piece:
        scale = piece.get("scale", 7.0)
        head.append(f"<defaults><scaling><millimeters>{scale}</millimeters><tenths>40</tenths></scaling>")
        width, height = piece.get("page", (210, 297))
        tenths = 40 / scale
        head.append(f"<page-layout><page-height>{height * tenths:.0f}</page-height><page-width>{width * tenths:.0f}</page-width>"
                    "<page-margins type=\"both\">" + "".join(f"<{side}-margin>{12 * tenths:.0f}</{side}-margin>"
                    for side in ("left", "right", "top", "bottom")) + "</page-margins></page-layout></defaults>")
    if "credit" in piece:
        head.append("".join(f'<credit page="1"><credit-words default-x="100" default-y="{1500 - 40 * index}">{escape(line)}</credit-words></credit>'
                            for index, line in enumerate(piece["credit"])))
    head.append("<part-list>")
    for index, part in enumerate(parts, 1):
        name = part.get("part", "Guitar")
        head.append(f'<score-part id="P{index}"><part-name>{name}</part-name></score-part>')
    head.append("</part-list>")
    body = "".join(part_xml(f"P{index}", {"tuning": GUITAR, **part}) for index, part in enumerate(parts, 1))
    return "".join(head) + body + "</score-partwise>"


SCALE = "q:3-0 q:3-2 q:2-0 q:2-1"
EIGHTS = "e:1-0 e:2-1 e:3-2 e:4-2 e:5-3 e:4-0 e:3-0 e:2-3"
LINE = [B(EIGHTS), B(SCALE), B("q:1-3 e:1-5 e:1-7 h:2-5"), B("e:6-3 e:6-5 e:5-2 e:5-3 q:4-0 q:4-2"),
        B("h:3-4 q:2-7 q:1-8"), B(EIGHTS), B(SCALE), B("w:1-0+2-1+3-0")]


def with_bars(extra, source=LINE):
    result = [dict(bar) for bar in source]
    for index, values in extra.items():
        result[index].update(values)
    return result


def piece(name, bars, **extra):
    return {"name": name, "tuning": GUITAR, "bars": bars, **extra}


def pieces():
    found = []
    add = found.append
    add(piece("a1-endings", with_bars({
        0: {"left": '<repeat direction="forward"/>'},
        3: {"left": '<ending number="1" type="start">1.</ending>',
            "right": '<ending number="1" type="stop"/><repeat direction="backward"/>'},
        4: {"left": '<ending number="2" type="start">2.</ending>', "right": '<ending number="2" type="discontinue"/>'},
    })))
    add(piece("a2-bar-numbers", LINE + LINE, style={"showMeasureNumber": 1, "measureNumberInterval": 1, "measureNumberSystem": 0}))
    add(piece("a3-fingering", [B("e:1-0f1 e:2-1f2 e:3-2f3 e:4-2f4 e:5-3f3 e:4-0f0 e:3-0f2 e:2-3f3"),
                               B("q:3-0f1 q:3-2f2 q:2-0f3 q:2-1f4"), B("q:1-3f3 e:1-5f4 e:1-7f1 h:2-5f2"),
                               B("h:1-5f1+2-5f2+3-6f3 h:1-3f4+2-3f3")]))
    add(piece("a4-string-circles", with_bars({i: {"before": [words(str(i % 6 + 1), circle=True)]} for i in range(8)})))
    add(piece("a5-tempo", with_bars({0: {"before": [tempo(120)]}, 3: {"before": [tempo(96)]}, 5: {"before": [words("Allegro 144")]}})))
    add(piece("a6-lyrics-digits", with_bars({
        0: {"lyrics": ["1.", "2", "3", "4", "5", "6", "7", "8"]}, 1: {"lyrics": ["24", "hours", "7", "days"]},
        3: {"lyrics": ["19", "99", "was", "the", "year", "3"]}})))
    add(piece("a7-rehearsal", with_bars({0: {"before": [rehearsal("1")]}, 2: {"before": [rehearsal("12")]},
                                         4: {"before": [rehearsal("A3")]}, 6: {"before": [rehearsal("5")]}})))
    rest = {"voices": [["w:r"]], "fullrest": True}
    add(piece("a8-multirest", [B(EIGHTS), B(SCALE), {**rest, "multirest": 4}, dict(rest), dict(rest), dict(rest), B(SCALE),
                               B("w:1-0")], style={"createMultiMeasureRests": 1}))

    low = "h.:6-0 q:r"
    add(piece("a9-fingering-stems-up", [B("e:1-0f1 e:1-1f2 e:1-3f3 e:1-5f4 e:1-0f1 e:1-1f2 e:1-3f3 e:1-5f4", "w:6-0"),
                                        B("q:1-0f3 q:1-1f3 q:1-3f3 q:1-5f3", "h:6-0 h:5-0")] * 2))
    add(piece("a10-circles-below", [B(EIGHTS, before=[words("3", circle=True, placement="below")]),
                                    B(SCALE, before=[words("6", circle=True, placement="below")])] * 3))
    def bracket(kind):
        return (f'<direction placement="below"><direction-type><bracket type="{kind}" number="1" line-end="none" line-type="solid"/>'
                "</direction-type></direction>")
    add(piece("a11-line-under-staff", [B(SCALE, before=[words("P.M.", placement="below"), bracket("start")]), B(SCALE), B(SCALE),
                                       B("q:3-0 q:3-2 q:2-0 q:2-1", before=[bracket("stop")]), B(SCALE)]))

    add(piece("b01-3-4", [B("q:1-0 q:2-1 q:3-2"), B("h:4-2 q:5-3"), B("h.:1-3"), B("e:1-0 e:2-1 e:3-2 e:4-2 e:5-3 e:4-0"),
                          B("q.:3-0 e:3-2 q:2-0"), B("q:r q:2-1 q:1-0")], meter="3/4"))
    add(piece("b02-6-8", [B("e:1-0 e:2-1 e:3-2 e:4-2 e:3-2 e:2-1"), B("q.:1-3 q.:1-5"), B("q:2-0 e:2-1 q:2-3 e:2-5"),
                          B("h.:3-2"), B("q.:4-2 e:4-0 e:4-2 e:4-4"), B("e:1-0 e:r e:1-3 q.:r")], meter="6/8"))
    add(piece("b03-2-2", [B("h:1-0 h:2-1"), B("q:3-0 q:3-2 q:2-0 q:2-1"), B("w:1-3"), B("h.:2-3 q:2-1"),
                          B("e:1-0 e:2-1 e:3-2 e:4-2 h:5-3"), B("h:r q:4-2 q:3-2")], meter="2/2"))
    add(piece("b04-5-4", [B("q:1-0 q:2-1 q:3-2 q:4-2 q:5-3"), B("h.:1-3 h:2-5"), B("w:3-2 q:3-4"),
                          B("e:1-0 e:2-1 e:3-2 e:4-2 e:5-3 e:4-0 e:3-0 e:2-3 q:1-0"), B("h:r h.:4-2")], meter="5/4"))
    add(piece("b05-whole-half", [B("w:1-0"), B("h:2-1 h:3-2"), B("w:1-0+2-1+3-2"), B("h:4-2 q:5-3 q:4-0"), B("w:6-3"),
                                 B("h:1-5+2-5 h:1-7+2-8"), B("h.:2-1 q:3-2"), B("w:5-2")]))
    add(piece("b06-32nd", [B("t:1-0 t:1-1 t:1-2 t:1-3 t:1-4 t:1-5 t:1-6 t:1-7 q:2-1 h:3-2"),
                           B("s.:2-1 t:2-3 e:2-5 q:3-2 h:4-2"), B("e:1-0 t:1-2 t:1-3 t:1-5 t:1-7 q:2-5 h:3-4"),
                           B("t:1-0 t:r t:2-1 t:r e:3-2 q:4-2 h:5-3")]))
    add(piece("b07-64th", [B("x:1-0 x:1-1 x:1-2 x:1-3 x:1-4 x:1-5 x:1-6 x:1-7 e:2-1 q:3-2 h:4-2"), B(SCALE)]))
    add(piece("b08-double-dot", [B("q..:1-0 s:1-1 h:2-1"), B("h..:2-3 e:2-1"), B("e..:1-3 t:1-5 q:1-7 h:2-5"),
                                 B("q:3-2 q..:4-2 s:4-0 q:5-3")]))
    add(piece("b09-quintuplet", [B("s/5:1-0 s/5:1-1 s/5:1-3 s/5:1-5 s/5:1-7 q:2-1 h:3-2"),
                                 B("q:2-3 e/5:1-0 e/5:1-1 e/5:1-3 e/5:1-5 e/5:1-7 q:3-2"),
                                 B("e/3:1-0 e/3:2-1 e/3:3-2 s/6:4-0 s/6:4-2 s/6:4-4 s/6:4-5 s/6:4-7 s/6:4-9 h:5-3")]))
    add(piece("b10-time-change", [B(SCALE), B(EIGHTS), B("q:1-0 q:2-1 q:3-2", time="3/4"), B("h:4-2 q:5-3"),
                                  B("e:1-0 e:2-1 e:3-2 e:4-2 e:3-2 e:2-1", time="6/8"), B("q.:1-3 q.:1-5"),
                                  B("q:1-0 q:2-1", time="2/4"), B("w:1-0", time="4/4")]))
    add(piece("b11-key-change", [B(SCALE, key=2), B("q:2-2 q:1-2 q:1-5 q:3-4"), B("q:2-4 q:3-1 q:4-4 q:5-4", key=-3),
                                 B("q:1-4 q:2-2 q:3-3 q:4-1"), B("q:3-6 q:2-6 q:1-6 q:5-6", key=5), B("w:1-0", key=0)]))
    add(piece("b12-syncopation", [B("e:1-0 q:2-1 q:3-2 q:4-2 e:5-3~"), B("e:5-3 q:2-1 q:3-2 q:4-2 e:1-3~"),
                                  B("h:1-3 q:2-5 q:3-4~"), B("q:3-4 h:2-1 q:1-0+2-0~"), B("w:1-0+2-0~"), B("h:1-0+2-0 h:6-3")]))
    add(piece("b13-rest-bar", [B(EIGHTS), {"voices": [["w:r"]], "fullrest": True}, B(SCALE),
                               {"voices": [["w:r"]], "fullrest": True}, {"voices": [["w:r"]], "fullrest": True}, B(SCALE),
                               B("q:r q:1-0 h:r"), B("w:1-0")]))
    add(piece("b14-two-voices", [B("q:1-0 q:1-1 q:1-3 q:1-5", "w:6-0"), B("h:r q:1-3 q:1-5", "q:5-0 q:5-2 h:r"),
                                 B("w:r", "q:6-0 q:6-3 q:5-0 q:5-2"), B("e:1-0 e:1-1 e:1-3 e:1-5 h:1-7", "h:r h:4-2"),
                                 B("q:r e:2-1 e:2-3 h:2-5", "h.:6-0 q:r"), B("w:1-0", "w:6-0")]))

    add(piece("b15-only-halves", [B("h:1-0 h:2-1"), B("h:3-2 h:4-2"), B("w:5-3"), B("h:1-3 h:2-5"), B("h:3-4 h:4-0"), B("w:1-0")]))
    add(piece("b16-mostly-halves", [B("h:1-0 h:2-1"), B("h:3-2 h:4-2"), B("q:1-0 q:2-1 h:3-2"), B("h:1-3 h:2-5"), B("h:3-4 h:4-0"),
                                    B("h:1-0 h:2-1"), B("h:3-2 h:4-2"), B("w:1-0")]))
    add(piece("b17-pickup", [B("q:3-2"), B(SCALE), B(EIGHTS), B("h.:1-0")], pickup=True))
    add(piece("c1-high-frets", [B("q:1-10+2-1 q:1-11+2-2 q:1-12+2-3 q:1-13+2-4"), B("q:2-14+3-1 q:2-15+3-0 q:3-16+4-2 q:3-17+4-5"),
                                B("e:1-18 e:2-1 e:1-19 e:2-2 e:1-20 e:2-3 e:1-21 e:2-4"),
                                B("e:1-22 e:1-23 e:1-24 e:1-9 e:6-24 e:5-1 e:6-11 e:5-11"),
                                B("s:1-1 s:1-0 s:1-1 s:1-2 s:1-12 s:1-10 s:1-1 s:1-11 s:2-1 s:2-1 s:2-11 s:2-1 q:3-21"),
                                B("h:1-12+2-13+3-12+4-14+5-14+6-12 h:1-0+2-1+3-0+4-2+5-3+6-0"),
                                B("q:1-10+2-10+3-11+4-12+5-12+6-10 q:1-1+2-1+3-2+4-3+5-3+6-1 q:1-15+2-1+3-14+4-2+5-17+6-3 q:1-24+2-24+3-24+4-24+5-24+6-24"),
                                B("w:1-22+2-1+3-19+4-0+5-17+6-5")]))
    add(piece("d1-seven-string", [B("e:7-0 e:7-2 e:6-0 e:6-2 e:5-0 e:5-2 e:4-0 e:4-2"), B("q:7-3 q:3-2 q:2-1 q:1-0"),
                                  B("h:1-0+2-0+3-1+4-2+5-2+6-0+7-0 h:7-5"), B("w:7-0")], tuning=SEVEN))
    add(piece("d2-five-string-bass", [B("q:5-0 q:5-2 q:4-0 q:4-2"), B("q:3-0 q:2-0 q:1-0 q:1-5"), B("h:5-3 h:4-5"),
                                      B("e:5-0 e:4-0 e:3-0 e:2-0 e:1-0 e:1-2 e:1-4 e:1-5")], tuning=BASS5, part="Bass"))
    add(piece("d3-ukulele", [B("q:4-0 q:3-0 q:2-0 q:1-0"), B("h:1-3+2-0+3-0+4-0 h:1-0+2-0+3-0+4-2"), B("e:1-0 e:1-2 e:1-3 e:1-5 q:2-3 q:3-2"),
                             B("w:1-0+2-0")], tuning=UKULELE, part="Ukulele"))
    add({"name": "d4-duet", "parts": [
        {"part": "Guitar 1", "tuning": GUITAR, "bars": [B(EIGHTS), B(SCALE), B("h:1-5 h:1-7"), B("w:1-0")]},
        {"part": "Guitar 2", "tuning": GUITAR, "bars": [B("h:6-0 h:6-3"), B("w:5-3"), B("q:5-0 q:5-2 q:4-0 q:4-2"), B("w:6-0")]}]})
    add(piece("d5-landscape", LINE + LINE + LINE, page=(297, 210)))
    add(piece("d6-small-staff", LINE + LINE, scale=3.5))
    add(piece("d7-large-staff", LINE + LINE, scale=12.0))
    add(piece("d8-three-pages", LINE * 14))

    add(piece("e1-five-line-fingerings", [B("e:1-0f1 e:2-1f2 e:3-2f3 e:4-2f4 e:5-3f3 e:4-0f0 e:3-0f2 e:2-3f3"),
                                          B("q:6-0f1 q:6-3f2 q:1-12f3 q:1-17f4"), B("h:1-5f1+2-5f2+3-6f3 h:6-0f4+5-2f3")] * 10,
              standard=True))
    add(piece("e2-lead-sheet-chords", [B("q:3-0 q:3-2 q:2-0 q:2-1", before=[words("C 032010")], lyrics=["1.", "24", "7", "365"]),
                                       B("h:1-3 h:2-5", before=[words("Am7 x02010")], lyrics=["100", "2000"])] * 12, standard=True))
    add(piece("e3-percussion", [B("e:1-0 e:1-0 e:1-0 e:1-0 e:1-0 e:1-0 e:1-0 e:1-0"),
                                B("q/3:1-0 q/3:1-0 q/3:1-0 h:1-0", before=[words("4x"), words("1 2 3 4", placement="below")])] * 12,
              percussion=True, part="Drums"))
    frame = ('<harmony><root><root-step>C</root-step></root><kind>major</kind><frame><frame-strings>6</frame-strings>'
             '<frame-frets>4</frame-frets>'
             + "".join(f"<frame-note><string>{s}</string><fret>{f}</fret><fingering>{g}</fingering></frame-note>"
                       for s, f, g in [(5, 3, 3), (4, 2, 2), (3, 0, 0), (2, 1, 1), (1, 0, 0)])
             + "</frame></harmony>")
    add(piece("e4-chord-diagrams", [B("h:2-1 h:1-0", before=[frame])] * 16, standard=True))

    add(piece("f1-grace-notes", [B("s:1-3g q:1-5 q:2-1 s:2-3g h:2-5"), B(SCALE)]))
    add(piece("f2-dead-notes", [B("q:3-0 q:3-0x q:2-0 q:2-0x"), B("e:6-0 e:6-0x+5-2x e:6-0 e:6-0x+5-2x h:4-2"), B("w:1-0")]))
    add(piece("f3-harmonics", [B("q:1-12h q:2-12h q:3-7h q:4-5h"), B("h:1-0 h:2-12h"), B(SCALE)]))
    add(piece("f4-slurs-same-note", [B("q:1-5 q:1-5 q:1-5 q:1-5", slurs=[(0, "start"), (1, "stop")]),
                                     B("q:2-3 q:2-5 q:2-3 q:2-1", slurs=[(0, "start"), (3, "stop")]),
                                     B("e:3-2 e:3-4 e:3-2 e:3-4 h:3-2", slurs=[(0, "start"), (1, "stop")])]))
    add(piece("f5-drop-c", [B("q:6-0 q:5-0 q:4-0 q:3-0"), B("q:6-2 q:5-2 q:2-1 q:1-0"), B("w:6-0+5-0+4-0")],
              tuning=["D4", "A3", "F3", "C3", "G2", "C2"], before_all="Drop C"))
    add(piece("f6-eb-standard-words", [B("q:6-0 q:5-0 q:4-0 q:3-0"), B("q:2-0 q:1-0 q:2-1 q:1-3")],
              tuning=["D#4", "A#3", "F#3", "C#3", "G#2", "D#2"], before_all="Tune down 1/2 step"))
    add(piece("f7-open-g-words", [B("q:6-0 q:5-0 q:4-0 q:3-0"), B("q:2-0 q:1-0 q:2-1 q:1-3")],
              tuning=["D4", "B3", "G3", "D3", "G2", "D2"], before_all="Open G tuning"))
    add(piece("f8-underfull-first-bar", [B("q:1-0 q:2-1 q:3-2"), B(SCALE), B(SCALE)]))
    add(piece("f9-same-string-frets-close", [B("t:1-1 t:1-1 t:1-1 t:1-1 t:1-1 t:1-1 t:1-1 t:1-1 t:1-2 t:1-2 t:1-2 t:1-2 t:1-2 t:1-2 t:1-2 t:1-2 t:1-12 t:1-12 t:1-12 t:1-12 t:1-12 t:1-12 t:1-12 t:1-12 t:1-1 t:1-1 t:1-1 t:1-1 t:1-1 t:1-1 t:1-1 t:1-1")] * 2))
    for item in found:
        if "before_all" in item:
            first = dict(item["bars"][0])
            first["before"] = [words(item["before_all"])]
            item["bars"] = [first, *item["bars"][1:]]
    return found


def with_signs(score):
    root = ET.fromstring(score)
    for part in root.iter("part"):
        fifths = 0
        for measure in part.iter("measure"):
            fifths = int(measure.findtext("attributes/key/fifths") or fifths)
            correct._write_accidentals(measure, fifths)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def windows(path):
    return subprocess.run(["wslpath", "-w", str(path)], check=True, capture_output=True, text=True).stdout.strip()


def convert(source, target, style=None):
    command = [MUSESCORE]
    if style:
        command += ["-S", windows(style)]
    command += ["-o", windows(target), windows(source)]
    return subprocess.run(command, timeout=180, capture_output=True, text=True, errors="replace")


def main(names):
    FILES.mkdir(exist_ok=True)
    for item in pieces():
        name = item["name"]
        if names and not any(name.startswith(prefix) for prefix in names):
            continue
        source = FILES / f"{name}.musicxml"
        source.write_bytes(with_signs(score_xml(item)))
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
