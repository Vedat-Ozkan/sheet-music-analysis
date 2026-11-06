import collections, pickle, re, sys, json, zipfile, warnings
import xml.etree.ElementTree as ET
from fractions import Fraction as F
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from mx import parse, align_bars, root_of, SEMI, OMR
warnings.filterwarnings("ignore")

ART = {"staccato", "staccatissimo", "accent", "strong-accent", "tenuto", "detached-legato", "spiccato",
       "fermata", "trill-mark", "turn", "inverted-turn", "mordent", "inverted-mordent", "arpeggiate", "delayed-turn", "wavy-line", "tremolo", "shake", "schleifer"}

def walk(data, extra=()):
    tags = ART | set(extra)
    out = []
    for pi, part in enumerate(root_of(data).iter("part")):
        div = 1
        page = 0
        for k, m in enumerate(part.iter("measure")):
            pr = m.find("print")
            if pr is not None and pr.get("new-page") == "yes":
                page += 1
            cursor, last = F(0), F(0)
            for ch in m:
                if ch.tag == "attributes" and ch.findtext("divisions"):
                    div = int(float(ch.findtext("divisions")))
                elif ch.tag == "backup":
                    cursor -= F(int(float(ch.findtext("duration")))) / div
                elif ch.tag == "forward":
                    cursor += F(int(float(ch.findtext("duration")))) / div
                elif ch.tag == "note":
                    grace = ch.find("grace") is not None
                    dur = F(0) if grace else F(int(float(ch.findtext("duration") or 0))) / div
                    is_chord = ch.find("chord") is not None
                    onset = last if is_chord else cursor
                    p = ch.find("pitch")
                    midi = None
                    if p is not None:
                        midi = (int(p.findtext("octave")) + 1) * 12 + SEMI[p.findtext("step")] + int(round(float(p.findtext("alter") or 0)))
                    for n in ch.findall("notations"):
                        for node in n.iter():
                            if node.tag in tags and not (node.tag == "wavy-line" and node.get("type") != "start"):
                                out.append(dict(page=page, part=pi, k=k, onset=onset, midi=midi, grace=grace, tag=node.tag, y=node.get("default-y"), placement=node.get("placement")))
                    if not is_chord:
                        last = cursor
                    if not grace and not is_chord:
                        cursor += dur
    return sorted(out, key=lambda m: (m["page"], m["part"], m["k"]))

def truth_index(bar, tmarks):
    marks = collections.defaultdict(set)
    notes = collections.defaultdict(set)
    for e in bar.events:
        if not e.rest:
            notes[e.onset].update(e.midis)
    for m in tmarks:
        if m["grace"] or m["midi"] is None:
            continue
        marks[(m["tag"], m["onset"])].update(chord_midis(bar, m))
    return marks, notes

def chord_midis(ob_bar, m):
    res = set()
    for e in ob_bar.events:
        if not e.rest and e.onset == m["onset"] and e.part == m["part"] and m["midi"] in e.midis:
            res.update(e.midis)
    return res or {m["midi"]}

def norm_shape(shape):
    s = shape.replace("_BELOW", "").replace("_", "-").lower()
    return {"marcato": "strong-accent", "arpeggiato": "arpeggiate", "non-arpeggiato": "arpeggiate", "trill": "trill-mark", "mordent": "mordent", "mordent-inverted": "inverted-mordent", "turn-inverted": "inverted-turn", "tr": "trill-mark"}.get(s, s)

def analyse(name, stem, d):
    d = Path(d)
    mxl = next(d.glob("*.mxl"), None)
    if mxl is None:
        return None
    data = mxl.read_bytes()
    man = json.loads((OMR / name / "manifest.json").read_text())
    piece = stem.rsplit("--", 1)[0]
    tdata = (OMR / name / man["pieces"][piece]["truth"]).read_bytes()
    tb, ob = parse(tdata), parse(data)
    pairs = {j: i for i, j in align_bars(tb, ob) if j is not None}
    tw = collections.defaultdict(list)
    for m in walk(tdata):
        tw[m["k"]].append(m)
    logs = [l.split("MARKDIAG ")[1].split() for l in (d / "out.txt").read_text(errors="replace").splitlines() if "MARKDIAG" in l]
    marks = walk(data)
    res = []
    if len(logs) != len(marks):
        print("LEN MISMATCH", stem, len(logs), len(marks))
    bad = 0
    pairs_ml = []
    i0 = 0
    while i0 < len(marks):
        i1 = i0
        key = lambda m: (m["part"], m["k"], m["onset"], m["midi"], m["grace"])
        while i1 < len(marks) and key(marks[i1]) == key(marks[i0]):
            i1 += 1
        pool = list(logs[i0:i1])
        for m in marks[i0:i1]:
            hit = next((l for l in pool if norm_shape(l[2]) == m["tag"]), None)
            if hit is None and pool:
                hit = pool[0]
            if hit is not None:
                pool.remove(hit)
                pairs_ml.append((m, hit))
        i0 = i1
    for m, l in pairs_ml:
        m.update(sheet=int(l[0]), inter=int(l[1]), shape=l[2], x=int(l[3]), y=int(l[4]), w=int(l[5]), h=int(l[6]), grade=float(l[7]), ctx=float(l[8]), glyph=l[9])
        if norm_shape(l[2]) != m["tag"]:
            bad += 1
        if m["grace"]:
            m["cls"] = "grace"; res.append(m); continue
        i = pairs.get(m["k"])
        if i is None or m["midi"] is None:
            m["cls"] = "unpaired"; res.append(m); continue
        tm, tn = truth_index(tb[i], tw[i])
        cm = chord_midis(ob[m["k"]], m)
        if not (tn.get(m["onset"], set()) & cm):
            m["cls"] = "wrong_note"
        elif tm.get((m["tag"], m["onset"]), set()) & cm:
            m["cls"] = "true"
        elif tm.get((m["tag"], m["onset"])):
            m["cls"] = "other_note"
        else:
            m["cls"] = "false"
        res.append(m)
    if bad:
        print("tag mismatch", stem, bad, collections.Counter((m["shape"], m["tag"]) for m in res if norm_shape(m["shape"]) != m["tag"]).most_common(5))
    return res

if __name__ == "__main__":
    sample = json.load(open(Path(__file__).with_name("marks_sample.json")))
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("marksdiag")
    A = {}
    for name, stem, n in sample:
        if (root / stem / "done").exists():
            r = analyse(name, stem, root / stem)
            if r is None:
                print("none", stem); continue
            A[stem] = (name, r)
            c = collections.Counter(m["cls"] for m in r)
            print(stem, "base", n, dict(c))
    pickle.dump(A, open(root.with_name(root.name + ".pkl"), "wb"))
