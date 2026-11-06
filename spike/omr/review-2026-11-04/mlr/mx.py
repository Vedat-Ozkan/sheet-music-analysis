import collections, io, json, sys, zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from fractions import Fraction as F
from pathlib import Path

R = Path("/home/kema/projects/sheet-music-plugin")
OMR = R / "spike/omr"
SETS = ["bench", "bench-heldout", "bench-heldout2", "bench-heldout3", "bench-real", "bench-tune2", "bench-oldly"]
SEMI = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
LEN = {"breve": F(8), "whole": F(4), "half": F(2), "quarter": F(1), "eighth": F(1, 2), "16th": F(1, 4), "32nd": F(1, 8), "64th": F(1, 16), "128th": F(1, 32)}


@dataclass
class Ev:
    part: int
    staff: str
    voice: str
    onset: F
    dur: F
    typ: str | None
    dots: int
    rest: bool
    hidden: bool
    measure_rest: bool
    midis: list
    steps: list
    x: float | None
    beam: str | None
    tuplet: bool
    stem: str | None
    ties: list = field(default_factory=list)
    marks: list = field(default_factory=list)
    diat: list = field(default_factory=list)


@dataclass
class Bar:
    events: list = field(default_factory=list)
    grace: int = 0
    full: F | None = None
    key: dict = field(default_factory=dict)
    clef: dict = field(default_factory=dict)
    texts: list = field(default_factory=list)
    dyn: list = field(default_factory=list)
    repeats: list = field(default_factory=list)
    endings: int = 0
    width: float | None = None
    number: str = ""
    new_system: bool = False
    new_page: bool = False
    octave: list = field(default_factory=list)
    fingerings: int = 0
    slurs: int = 0
    wedges: int = 0
    pedals: int = 0
    breaths: int = 0


def root_of(data: bytes):
    if data[:2] == b"PK":
        z = zipfile.ZipFile(io.BytesIO(data))
        name = next(n for n in z.namelist() if n.endswith((".xml", ".musicxml")) and not n.startswith("META-INF"))
        data = z.read(name)
    return ET.fromstring(data)


def parse(data: bytes) -> list:
    root = root_of(data)
    bars = []
    for pi, part in enumerate(root.iter("part")):
        div, full = 1, None
        keyst, clefst = {}, {}
        for k, m in enumerate(part.iter("measure")):
            while len(bars) <= k:
                bars.append(Bar())
            b = bars[k]
            b.number = b.number or m.get("number", "")
            try:
                b.width = float(m.get("width")) if m.get("width") and b.width is None else b.width
            except ValueError:
                pass
            pr = m.find("print")
            if pr is not None:
                b.new_system = b.new_system or pr.get("new-system") == "yes" or pr.get("new-page") == "yes"
                b.new_page = b.new_page or pr.get("new-page") == "yes"
            cursor, last = F(0), F(0)
            cur = None
            for ch in m:
                if ch.tag == "attributes":
                    if ch.findtext("divisions"):
                        div = int(float(ch.findtext("divisions")))
                    for t in ch.findall("time"):
                        beats = t.findtext("beats", "")
                        if beats and all(c.strip().isdigit() for c in beats.split("+")) and t.findtext("beat-type"):
                            full = F(sum(int(c) for c in beats.split("+")) * 4, int(t.findtext("beat-type")))
                    for c in ch.findall("clef"):
                        clefst[(pi, c.get("number", "1"))] = (c.findtext("sign"), c.findtext("line"), c.findtext("clef-octave-change"))
                        b.clef[(pi, c.get("number", "1"))] = clefst[(pi, c.get("number", "1"))]
                    for kk in ch.findall("key"):
                        if kk.findtext("fifths") is not None:
                            n = kk.get("number")
                            keyst[(pi, n or "*")] = int(kk.findtext("fifths"))
                            b.key[(pi, n or "*")] = int(kk.findtext("fifths"))
                elif ch.tag == "backup":
                    cursor -= F(int(float(ch.findtext("duration")))) / div
                elif ch.tag == "forward":
                    cursor += F(int(float(ch.findtext("duration")))) / div
                elif ch.tag == "direction":
                    for w in ch.iter("words"):
                        if (w.text or "").strip():
                            b.texts.append((w.text or "").strip())
                    for d in ch.iter("dynamics"):
                        for dd in d:
                            b.dyn.append((dd.tag if dd.tag != "other-dynamics" else (dd.text or "?"), cursor))
                    for o in ch.iter("octave-shift"):
                        b.octave.append(o.get("type"))
                    b.wedges += sum(1 for w in ch.iter("wedge") if w.get("type") in ("crescendo", "diminuendo"))
                    b.pedals += sum(1 for w in ch.iter("pedal") if w.get("type") == "start")
                elif ch.tag == "barline":
                    for r in ch.findall("repeat"):
                        b.repeats.append((r.get("direction"), ch.get("location", "right")))
                    b.endings += sum(1 for e in ch.findall("ending") if e.get("type") == "start")
                elif ch.tag == "note":
                    if ch.find("grace") is not None:
                        b.grace += 1
                        continue
                    if ch.find("cue") is not None:
                        continue
                    dur = F(int(float(ch.findtext("duration") or 0))) / div
                    pitch = ch.find("pitch")
                    typ = ch.findtext("type")
                    midi = None
                    if pitch is not None:
                        step, octv = pitch.findtext("step"), int(pitch.findtext("octave"))
                        alter = int(round(float(pitch.findtext("alter") or 0)))
                        midi = (octv + 1) * 12 + SEMI[step] + alter
                    n = ch.find("notations")
                    ties = [t.get("type") for t in ch.findall("tie")]
                    marks = []
                    if n is not None:
                        for tag in ("staccato", "staccatissimo", "accent", "strong-accent", "tenuto", "detached-legato", "spiccato", "breath-mark", "caesura"):
                            if list(n.iter(tag)):
                                marks.append(tag)
                                if tag in ("breath-mark", "caesura"):
                                    b.breaths += 1
                        if list(n.iter("fermata")):
                            marks.append("fermata")
                        for tag in ("trill-mark", "turn", "inverted-turn", "mordent", "inverted-mordent", "tremolo", "arpeggiate"):
                            if list(n.iter(tag)):
                                marks.append(tag)
                        b.fingerings += len(list(n.iter("fingering")))
                        b.slurs += sum(1 for s in n.findall("slur") if s.get("type") == "start")
                        for s in n.findall("dynamics"):
                            for dd in s:
                                b.dyn.append((dd.tag, cursor))
                    x = ch.get("default-x")
                    x = float(x) if x else None
                    if ch.find("chord") is not None and cur is not None:
                        ev = cur
                        if midi is not None:
                            ev.midis.append(midi)
                            ev.steps.append(step)
                        for t in ties:
                            ev.ties.append((midi, t))
                        ev.marks += marks
                        if x is not None:
                            ev.x = min(ev.x, x) if ev.x is not None else x
                        continue
                    r = ch.find("rest")
                    ev = Ev(pi, ch.findtext("staff", "1"), ch.findtext("voice", "1"), cursor, dur, typ, len(ch.findall("dot")),
                            r is not None, ch.get("print-object") == "no", r is not None and r.get("measure") == "yes",
                            [midi] if midi is not None else [], [step] if midi is not None else [], x,
                            ch.findtext("beam[@number='1']"), ch.find("time-modification") is not None, ch.findtext("stem"))
                    for t in ties:
                        ev.ties.append((midi, t))
                    ev.marks += marks
                    b.events.append(ev)
                    cur = ev
                    cursor += dur
            b.full = full if b.full is None else b.full
    return bars


def pitches(bar: Bar) -> collections.Counter:
    c = collections.Counter()
    for e in bar.events:
        for m in e.midis:
            c[m] += 1
    return c


def timed(bar: Bar) -> collections.Counter:
    c = collections.Counter()
    for e in bar.events:
        for m in e.midis:
            c[(m, e.onset)] += 1
    return c


def align_bars(tb, ob):
    sys.path[:0] = [str(OMR), str(OMR / "bench")]
    n, m = len(tb), len(ob)
    tp = [pitches(b) for b in tb]
    op = [pitches(b) for b in ob]
    S = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        ti = tp[i - 1]
        for j in range(1, m + 1):
            s = sum((ti & op[j - 1]).values())
            S[i][j] = max(S[i - 1][j], S[i][j - 1], S[i - 1][j - 1] + s)
    i, j, pairs = n, m, []
    while i > 0 and j > 0:
        s = sum((tp[i - 1] & op[j - 1]).values())
        if (S[i][j] == S[i - 1][j - 1] + s and s > 0) or (S[i][j] == S[i - 1][j - 1] and S[i][j] != S[i - 1][j] and S[i][j] != S[i][j - 1]):
            pairs.append((i - 1, j - 1))
            i -= 1
            j -= 1
        elif S[i][j] == S[i - 1][j]:
            i -= 1
        else:
            j -= 1
    pairs = pairs[::-1]
    anchors = [(-1, -1)] + pairs + [(n, m)]
    out = list(pairs)
    for (a, b), (c, d) in zip(anchors, anchors[1:]):
        if c - a == d - b:
            out += [(a + k, b + k) for k in range(1, c - a)]
    return sorted(out)


def readings(variant="pitch39", sets=SETS):
    for name in sets:
        man = json.loads((OMR / name / "manifest.json").read_text())
        eng = {Path(p["pdf"]).stem: p["engraver"] for p in man["pdfs"]}
        for reading in sorted((OMR / "speed/cache/runs" / variant).glob(f"{name}--*.musicxml")):
            stem = reading.stem.split("--", 1)[1]
            piece = stem.rsplit("--", 1)[0]
            if piece not in man["pieces"]:
                continue
            yield name, stem, piece, eng.get(stem, stem.rsplit("--", 1)[1]), reading.read_bytes(), (OMR / name / man["pieces"][piece]["truth"]).read_bytes()
