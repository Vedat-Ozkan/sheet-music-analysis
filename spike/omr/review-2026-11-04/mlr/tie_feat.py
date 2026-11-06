import collections, json, sys, warnings, pickle
warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/kema/projects/sheet-music-plugin/spike/omr/speed")
from whole_bars import *
from barparse import root_of, SEMI
from fractions import Fraction as F

def notes(root):
    bars = []
    for pi, part in enumerate(root.iter("part")):
        div = 1
        for k, m in enumerate(part.iter("measure")):
            while len(bars) <= k:
                bars.append([])
            cursor, last = F(0), F(0)
            for ch in m:
                if ch.tag == "attributes" and ch.findtext("divisions"):
                    div = int(float(ch.findtext("divisions")))
                elif ch.tag == "backup":
                    cursor -= F(int(float(ch.findtext("duration")))) / div
                elif ch.tag == "forward":
                    cursor += F(int(float(ch.findtext("duration")))) / div
                elif ch.tag == "note":
                    if ch.find("grace") is not None or ch.find("cue") is not None:
                        continue
                    dur = F(int(float(ch.findtext("duration") or 0))) / div
                    chord = ch.find("chord") is not None
                    onset = last if chord else cursor
                    p = ch.find("pitch")
                    if p is not None:
                        midi = (int(p.findtext("octave")) + 1) * 12 + SEMI[p.findtext("step")] + int(round(float(p.findtext("alter") or 0)))
                        ns = ch.find("notations")
                        sl = ns.findall("slur") if ns is not None else []
                        bars[k].append(dict(k=k, part=pi, staff=ch.findtext("staff", "1"), voice=ch.findtext("voice", "1"), onset=onset, dur=dur, midi=midi,
                                            tstart=any(t.get("type") == "start" for t in ch.findall("tie")),
                                            tstop=any(t.get("type") == "stop" for t in ch.findall("tie")),
                                            sstart=[s.get("number", "1") for s in sl if s.get("type") == "start"],
                                            sstop=[s.get("number", "1") for s in sl if s.get("type") == "stop"]))
                    if not chord:
                        last = cursor
                        cursor += dur
    for b in bars:
        b.sort(key=lambda n: n["onset"])
    return bars

def tie_end(bars, k, n):
    for kk in (k, k + 1):
        if kk >= len(bars):
            return None
        for m in bars[kk]:
            if m["part"] == n["part"] and m["midi"] == n["midi"] and m["tstop"] and (kk > k or m["onset"] > n["onset"]):
                return m
    return None

def next_same(bars, k, n):
    for kk in (k, k + 1):
        if kk >= len(bars):
            return None
        for m in bars[kk]:
            if m["part"] == n["part"] and m["staff"] == n["staff"] and m["midi"] == n["midi"] and (kk > k or m["onset"] >= n["onset"] + n["dur"]):
                return m
    return None

def locate(bars, k, part, staff, midi, onset):
    if k is None or k >= len(bars):
        return None
    for m in bars[k]:
        if m["part"] == part and m["staff"] == staff and m["midi"] == midi and m["onset"] == onset:
            return m
    return None

def chord_of(bars, n):
    return [m for m in bars[n["k"]] if m["part"] == n["part"] and m["staff"] == n["staff"] and m["onset"] == n["onset"]]

def slur_across(bars, a, b):
    if a is None or b is None:
        return None
    if not a["sstart"] or not b["sstop"]:
        return False
    return bool(set(a["sstart"]) & set(b["sstop"]))

def classify_all(variant):
    rows = []
    for name in SETS:
        man = json.loads((OMR / name / "manifest.json").read_text())
        for en in man["pdfs"]:
            stem = en["pdf"].rsplit("/", 1)[-1][:-4]
            r = HERE / "cache/runs" / variant / f"{name}--{stem}.musicxml"
            if not r.exists() or not r.stat().st_size:
                continue
            tdata = (OMR / name / man["pieces"][en["piece"]]["truth"]).read_bytes()
            odata = r.read_bytes()
            tb, ob = parse(tdata), parse(odata)
            tn, on = notes(root_of(tdata)), notes(root_of(odata))
            pairs = dict(align_bars(tb, ob))
            inv = {j: i for i, j in pairs.items()}
            for i, t in enumerate(tb):
                j = pairs.get(i)
                if j is None:
                    continue
                o = ob[j]
                tt, ot = ties(t, True), ties(o, True)
                only = sounding(t, True) == sounding(o, True) and rests(t, True) == rests(o, True) and tt != ot
                base = dict(set=name, stem=stem, eng=en["engraver"], i=i, j=j, only=only, tnum=t.number, onum=o.number)
                for (key, midi, onset), c in (tt - ot).items():
                    part, staff = key
                    n = locate(tn, i, part, staff, midi, onset)
                    e = tie_end(tn, i, n) if n else None
                    a = locate(on, j, part, staff, midi, onset)
                    bj = None
                    if e:
                        bj = j if e["k"] == i else pairs.get(e["k"])
                    b = locate(on, bj, part, e["staff"], midi, e["onset"]) if e else None
                    cross = e is not None and e["k"] != i
                    newsys = cross and bj is not None and ob[bj].new_system
                    newpage = cross and bj is not None and ob[bj].new_page
                    rows.append(dict(base, kind="missing", n=c, midi=midi, onset=str(onset), staff=staff, part=part,
                                     endfound=e is not None, cross=cross, newsys=newsys, newpage=newpage,
                                     a=a is not None, b=b is not None,
                                     aslur=bool(a and a["sstart"]), bslur=bool(b and b["sstop"]),
                                     slurab=slur_across(on, a, b),
                                     atstop=bool(a and a["tstop"]), btstart=bool(b and b["tstart"]),
                                     bonset=str(e["onset"]) if e else None, bstaff=e["staff"] if e else None,
                                     dup=sum(1 for m in tn[i] if m["part"] == part and m["staff"] == staff and m["midi"] == midi and m["onset"] == onset),
                                     chordsize=len(chord_of(tn, n)) if n else 0,
                                     staffdiff=e is not None and e["staff"] != staff,
                                     voicediff=e is not None and e["voice"] != n["voice"]))
                for (key, midi, onset), c in (ot - tt).items():
                    part, staff = key
                    a = locate(on, j, part, staff, midi, onset)
                    e = tie_end(on, j, a) if a else None
                    cross = e is not None and e["k"] != j
                    ei = None
                    if e:
                        ei = i if e["k"] == j else inv.get(e["k"])
                    ta = locate(tn, i, part, staff, midi, onset)
                    tbn = locate(tn, ei, part, e["staff"], midi, e["onset"]) if e else None
                    newsys = cross and ob[e["k"]].new_system
                    rows.append(dict(base, kind="extra", n=c, midi=midi, onset=str(onset), staff=staff, part=part,
                                     endfound=e is not None, cross=cross, newsys=newsys,
                                     a=ta is not None, b=tbn is not None,
                                     aslur=bool(ta and ta["sstart"]), bslur=bool(tbn and tbn["sstop"]),
                                     slurab=slur_across(tn, ta, tbn),
                                     chordslur=bool(ta and any(x["sstart"] for x in chord_of(tn, ta))) ,
                                     chordslurb=bool(tbn and any(x["sstop"] for x in chord_of(tn, tbn))),
                                     tbstop=bool(tbn and tbn["tstop"]), tatstart=bool(ta and ta["tstart"]),
                                     gap=None, 
                                     consecutive=bool(ta and tbn and next_same(tn, i, ta) is tbn),
                                     bonset=str(e["onset"]) if e else None))
    return rows

if __name__ == "__main__":
    rows = classify_all(sys.argv[1])
    pickle.dump(rows, open(sys.argv[2], "wb"))
    print(len(rows))
