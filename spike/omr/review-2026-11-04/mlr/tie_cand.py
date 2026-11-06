import collections, json, sys, warnings, pickle
warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/kema/projects/sheet-music-plugin/spike/omr/speed")
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
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
                        bars[k].append(dict(k=k, part=pi, staff=ch.findtext("staff", "1"), voice=ch.findtext("voice", "1"), stem=ch.findtext("stem"), onset=onset, dur=dur, midi=midi,
                                            tstart=any(t.get("type") == "start" for t in ch.findall("tie")),
                                            tstop=any(t.get("type") == "stop" for t in ch.findall("tie")),
                                            sstart=[s.get("number", "1") for s in sl if s.get("type") == "start"],
                                            sstop=[s.get("number", "1") for s in sl if s.get("type") == "stop"]))
                    if not chord:
                        last = cursor
                        cursor += dur
    for b in bars:
        b.sort(key=lambda n: (n["onset"], n["midi"]))
    return bars

def between(on, a, b):
    out = []
    for k in range(a["k"], b["k"] + 1):
        for m in on[k]:
            if m["part"] != a["part"] or m["staff"] != a["staff"]:
                continue
            if (k, m["onset"]) > (a["k"], a["onset"]) and (k, m["onset"]) < (b["k"], b["onset"]):
                out.append(m)
    return out

def candidates(on):
    res = []
    for k, bar in enumerate(on):
        for a in bar:
            if a["tstart"]:
                for kk in (k, k + 1):
                    if kk >= len(on): continue
                    hit = [m for m in on[kk] if m["part"] == a["part"] and m["midi"] == a["midi"] and m["tstop"] and (kk > k or m["onset"] > a["onset"])]
                    if hit:
                        res.append(("tie", a, hit[0]))
                        break
            for num in a["sstart"]:
                done = False
                for kk in (k, k + 1):
                    if kk >= len(on) or done: continue
                    for m in on[kk]:
                        if m["part"] == a["part"] and num in m["sstop"] and (kk > k or m["onset"] > a["onset"]):
                            if m["midi"] == a["midi"] and m["staff"] == a["staff"]:
                                res.append(("slur", a, m))
                            done = True
                            break
    return res

if __name__ == '__main__':
    rows = []
    for name in SETS:
        man = json.loads((OMR / name / "manifest.json").read_text())
        for en in man["pdfs"]:
            stem = en["pdf"].rsplit("/", 1)[-1][:-4]
            r = HERE / "cache/runs" / sys.argv[1] / f"{name}--{stem}.musicxml"
            if not r.exists() or not r.stat().st_size:
                continue
            tdata = (OMR / name / man["pieces"][en["piece"]]["truth"]).read_bytes()
            odata = r.read_bytes()
            tb, ob = parse(tdata), parse(odata)
            on = notes(root_of(odata))
            pairs = dict(align_bars(tb, ob))
            inv = {j: i for i, j in pairs.items()}
            for typ, a, b in candidates(on):
                i = inv.get(a["k"])
                tkey = None
                if i is not None:
                    tt = ties(tb[i], True)
                    tkey = tt[((a["part"], a["staff"]), a["midi"], a["onset"])] > 0
                btw = between(on, a, b)
                cont = (a["k"] == b["k"] and a["onset"] + a["dur"] == b["onset"]) or (a["k"] != b["k"] and b["onset"] == 0)
                same_stem = sum(1 for m in btw if m["stem"] == a["stem"])
                same_voice = sum(1 for m in btw if m["voice"] == a["voice"])
                rows.append(dict(set=name, stem=stem, eng=en["engraver"], typ=typ, truth=tkey, k=a["k"], onset=str(a["onset"]), midi=a["midi"], staff=a["staff"], cross=a["k"] != b["k"], nsys=ob[b["k"]].new_system and a["k"] != b["k"],
                                 btw=len(btw), same_stem=same_stem, same_voice=same_voice, cont=cont, vdiff=a["voice"] != b["voice"], sdiff=a["stem"] != b["stem"] and a["stem"] and b["stem"]))
    pickle.dump(rows, open(sys.argv[2], "wb"))
    c = collections.Counter()
    for r in rows:
        c[(r["typ"], "tietrue" if r["truth"] else ("nopair" if r["truth"] is None else "tiefalse"), "btw" if r["btw"] else "nobtw", "same_v" if r["same_voice"] else "-", "same_st" if r["same_stem"] else "-", "cont" if r["cont"] else "noncont")] += 1
    for k in sorted(c, key=str): print(k, c[k])
