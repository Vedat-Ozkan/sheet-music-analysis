import collections, json, re, statistics, sys, warnings, zipfile, io
warnings.filterwarnings("ignore")
from fractions import Fraction as F
from pathlib import Path
sys.path[:0] = ["/home/kema/projects/sheet-music-plugin/spike/omr/speed"]
from barparse import SEMI, root_of, parse, pitches, align_bars

SCR = Path("/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad")
DIAT = dict(zip("CDEFGAB", range(7)))

def walk(data):
    root = root_of(data)
    bars = collections.defaultdict(list)
    clefs = collections.defaultdict(dict)
    for pi, part in enumerate(root.iter("part")):
        div = 1
        state = {}
        for k, m in enumerate(part.iter("measure")):
            cur = F(0); last = F(0)
            for ch in m:
                if ch.tag == "attributes":
                    if ch.findtext("divisions"):
                        div = max(1, int(float(ch.findtext("divisions"))))
                    for c in ch.findall("clef"):
                        state[c.get("number", "1")] = (c.findtext("sign"), int(c.findtext("line") or 2), int(c.findtext("clef-octave-change") or 0))
                elif ch.tag == "backup":
                    cur -= F(int(float(ch.findtext("duration")))) / div
                elif ch.tag == "forward":
                    cur += F(int(float(ch.findtext("duration")))) / div
                elif ch.tag == "note":
                    p = ch.find("pitch")
                    grace = ch.find("grace") is not None
                    dur = F(int(float(ch.findtext("duration") or 0))) / div
                    n = dict(part=pi, bar=k, staff=ch.findtext("staff", "1"), grace=grace, cue=ch.find("cue") is not None, rest=p is None, dur=dur, typ=ch.findtext("type"))
                    chord = ch.find("chord") is not None
                    n["onset"] = last if chord else cur
                    if p is not None:
                        s, o = p.findtext("step"), int(p.findtext("octave"))
                        n.update(step=s, oct=o, alter=int(round(float(p.findtext("alter") or 0))))
                        n["midi"] = (o + 1) * 12 + SEMI[s] + n["alter"]
                        n["clef"] = state.get(n["staff"])
                    bars[k].append(n)
                    if not chord and not grace:
                        last = cur; cur += dur
    return bars

def pos(n):
    c = n["clef"] or ("G", 2, 0)
    ref = {"G": DIAT["G"] + 7 * 4, "F": DIAT["F"] + 7 * 3, "C": DIAT["C"] + 7 * 4}.get(c[0], DIAT["G"] + 28) + 7 * c[2]
    return -((DIAT[n["step"]] + 7 * n["oct"] - ref) + (c[1] - 3) * 2)

def load_trace(path):
    T = dict(export=[], add={}, removed=[], cand=[], weak=[], seed=[], noglyph=[], probe=[])
    for line in open(path):
        t = line.split()
        k = t[0]
        if k == "EXPORT":
            T["export"].append(dict(sheet=int(t[1]), id=int(t[2]), shape=t[3], staff=int(t[4]), p=int(t[5]), x=int(t[6]), y=int(t[7]), w=int(t[8]), h=int(t[9]), measure=t[10], chord=t[11]))
        elif k == "ADD":
            T["add"][(int(t[1]), int(t[2]))] = dict(sheet=int(t[1]), id=int(t[2]), shape=t[3], staff=int(t[4]), p=int(t[5]), x=int(t[6]), y=int(t[7]), w=int(t[8]), h=int(t[9]), grade=float(t[10]))
        elif k == "REMOVE":
            T["removed"].append(dict(sheet=int(t[1]), id=int(t[2]), shape=t[3], staff=int(t[4]), p=int(t[5]), x=int(t[6]), y=int(t[7]), w=int(t[8]), h=int(t[9]), grade=float(t[10]), excl=t[11], where=t[12]))
        elif k == "CAND":
            T["cand"].append(dict(sheet=int(t[1]), staff=int(t[2]), p=int(t[3]), x=int(t[4]), y=int(t[5]), shape=t[6], grade=float(t[7]), st=t[8]))
        elif k == "WEAK":
            T["weak"].append(dict(sheet=int(t[1]), staff=int(t[2]), p=int(t[3]), x=int(t[4]), y=int(t[5]), shape=t[6], d=float(t[7])))
        elif k == "SEEDCONFLICT":
            T["seed"].append(dict(sheet=int(t[1]), staff=int(t[2]), p=int(t[3]), x=int(t[4]), y=int(t[5]), w=int(t[6]), h=int(t[7]), shape=t[8], grade=float(t[9])))
        elif k == "NOGLYPH":
            T["noglyph"].append(dict(sheet=int(t[1]), staff=int(t[2]), p=int(t[3]), x=int(t[4]), y=int(t[5]), w=int(t[6]), h=int(t[7])))
        elif k == "PROBE":
            T["probe"].append(dict(sheet=int(t[1]), staff=int(t[2]), p=int(t[3]), x=int(t[4]), y=int(t[5]), shape=t[6], how=t[7], out=t[8], low=float(t[9][4:])))
    return T

SKIP = ("HeadTrace", "AbstractInter.remove", "AbstractNoteInter.remove", "AbstractChordInter.remove", "HeadChordInter.remove", "AbstractInter.delete")
def rule(where):
    fr = where.split(">")
    keep = [f for f in fr if not f.startswith(SKIP)]
    step = next((f.split(".")[0] for f in fr if "Step." in f and "AbstractSystemStep" not in f and "OmrStep" not in f), "?")
    return (keep[0].split(":")[0] if keep else "?") + "@" + step, keep[:3]

def match_notes(t, o):
    used = set(); pairs = []
    tp = [i for i, n in enumerate(t) if not n["rest"] and not n["grace"] and not n["cue"]]
    op = [i for i, n in enumerate(o) if not n["rest"] and not n["grace"] and not n["cue"]]
    tused = set()
    for strict in (True, False):
        for i in tp:
            if i in tused: continue
            for j in op:
                if j in used or o[j]["midi"] != t[i]["midi"]: continue
                if strict and o[j]["onset"] != t[i]["onset"]: continue
                used.add(j); tused.add(i); pairs.append((i, j)); break
    return pairs, [i for i in tp if i not in tused], [j for j in op if j not in used]

def analyse(name, tdata, omx, trace, bars_wanted):
    T = load_trace(trace)
    tb, ob = walk(tdata), walk(omx)
    pairs = dict(align_bars(parse(tdata), parse(omx)))
    flat = [n for k in sorted(ob) for n in ob[k]]
    exp = T["export"]
    if len(flat) != len(exp):
        print("COUNT MISMATCH", name, len(flat), len(exp))
    for n, e in zip(flat, exp):
        n["head"] = e
    hh = statistics.median([e["h"] for e in exp if "BLACK" in e["shape"] and e["h"] > 3] or [20])
    exported = {(e["sheet"], e["id"]) for e in exp}
    removed = {(r["sheet"], r["id"]) for r in T["removed"]}
    finals = [v for k, v in T["add"].items() if k not in removed and k not in exported]
    rows = []
    allunmatched = {}
    for i, j in pairs.items():
        if i in bars_wanted:
            allunmatched[i] = match_notes(tb[i], ob[j])
    for i in bars_wanted:
        j = pairs.get(i)
        if j is None: continue
        t, o = tb[i], ob[j]
        ps, miss, ext = allunmatched[i]
        anchors = collections.defaultdict(list)
        ostaff = collections.Counter()
        offs = collections.defaultdict(list)
        for a, b in ps:
            h = o[b].get("head")
            if not h: continue
            cx = h["x"] + h["w"] / 2
            anchors[t[a]["staff"]].append((t[a]["onset"], cx))
            ostaff[(t[a]["staff"], h["sheet"], h["staff"])] += 1
            offs[t[a]["staff"]].append(h["p"] - pos(t[a]))
        def staff_map(s):
            c = [(v, k) for k, v in ostaff.items() if k[0] == s]
            if c: return max(c)[1][1:]
            hs = [n["head"] for n in o if n.get("head") and not n["rest"]]
            if not hs: return None
            ids = sorted({(h["sheet"], h["staff"]) for h in hs})
            if len(ids) >= 2:
                return ids[-2:][int(s) - 1] if s in "12" else ids[0]
            return ids[0]
        allx = [n["head"]["x"] for n in o if n.get("head")]
        for mi in miss:
            n = t[mi]
            sm = staff_map(n["staff"])
            same = [x for on, x in anchors[n["staff"]] + [q for s, v in anchors.items() if s != n["staff"] for q in v] if on == n["onset"]]
            al = sorted(anchors[n["staff"]] + [q for s, v in anchors.items() if s != n["staff"] for q in v])
            if same:
                xe = statistics.median(same); tol = 1.6 * hh; conf = "same-onset"
            elif al:
                lo = [a for a in al if a[0] < n["onset"]]; hi = [a for a in al if a[0] > n["onset"]]
                if lo and hi:
                    a, b = lo[-1], hi[0]
                    xe = a[1] + (b[1] - a[1]) * float((n["onset"] - a[0]) / (b[0] - a[0])); tol = max(2.5 * hh, abs(b[1] - a[1]) * 0.45); conf = "interp"
                elif hi:
                    xe = hi[0][1] - 2 * hh; tol = 4 * hh; conf = "edge"
                else:
                    xe = lo[-1][1] + 2 * hh; tol = 4 * hh; conf = "edge"
            elif allx:
                xe = statistics.median(allx); tol = (max(allx) - min(allx)) / 2 + 3 * hh; conf = "bar"
            else:
                rows.append(dict(name=name, bar=i, kind="missing", midi=n["midi"], stage="no_anchor", staff=None)); continue
            off = statistics.median(offs[n["staff"]]) if offs[n["staff"]] else 0
            pe = pos(n) + round(off)
            sh, st = sm if sm else (1, 0)
            def near(rec, dp=0):
                wid = rec.get("w", hh * 1.2)
                return rec["sheet"] == sh and rec["staff"] == st and abs(rec["p"] - pe) == dp and abs(rec["x"] + wid / 2 - xe) <= tol
            r = dict(name=name, bar=i, j=j, kind="missing", midi=n["midi"], onset=str(n["onset"]), rstaff=n["staff"], sheet=sh, staff=st, p=pe, x=round(xe), tol=round(tol), conf=conf, hh=hh)
            unm = [o[x] for x in ext if o[x].get("head")]
            cand = [u for u in unm if near(u["head"])]
            if cand:
                c = min(cand, key=lambda u: abs(u["head"]["x"] - xe))
                r.update(stage="right_place_wrong_alter", got=c["midi"], head=c["head"]["id"]); c["_used"] = 1; rows.append(r); continue
            other = [m for m in sum((ob[k] for k in ob if k != j), []) if m.get("head") and not m["rest"] and near(m["head"])]
            if other:
                c = min(other, key=lambda u: abs(u["head"]["x"] - xe))
                r.update(stage="head_in_other_bar", gotbar=c["bar"], got=c["midi"]); rows.append(r); continue
            fin = [f for f in finals if near(f)]
            if fin:
                c = min(fin, key=lambda u: abs(u["x"] - xe))
                r.update(stage="survived_not_exported", shape=c["shape"], grade=c["grade"], head=c["id"]); rows.append(r); continue
            wrong = [u for u in unm if not u.get("_used") and any(near(u["head"], d) for d in (1, 2))]
            if wrong:
                c = min(wrong, key=lambda u: abs(u["head"]["p"] - pe) * 100 + abs(u["head"]["x"] - xe))
                r.update(stage="head_at_wrong_pitch", got=c["midi"], dp=c["head"]["p"] - pe); c["_used"] = 1; rows.append(r); continue
            rem = [q for q in T["removed"] if near(q)]
            if rem:
                want = "WHOLE" if n["typ"] in ("whole", "breve") else "VOID" if n["typ"] == "half" else "BLACK"
                ok = [q for q in rem if want in q["shape"]]
                c = max(ok, key=lambda q: q["grade"]) if ok else rem[-1]
                rl, frames = rule(c["where"])
                r.update(stage="removed" if ok else "removed_wrong_shape_only", rule=rl, frames=frames, shape=c["shape"], grade=c["grade"], excl=c["excl"], head=c["id"], typ=n["typ"],
                         cands=[(q["shape"], q["grade"], rule(q["where"])[0], q["id"]) for q in rem]); rows.append(r); continue
            pre = [q for q in T["seed"] if near(q)]
            if pre:
                r.update(stage="candidate_seedconflict", grade=pre[0]["grade"]); rows.append(r); continue
            pre = [q for q in T["noglyph"] if near(q)]
            if pre:
                r.update(stage="candidate_noglyph"); rows.append(r); continue
            pre = [q for q in T["weak"] if near(q)]
            if pre:
                r.update(stage="candidate_weak_stemless", shape=pre[0]["shape"], d=min(q["d"] for q in pre)); rows.append(r); continue
            pre = [q for q in T["cand"] if near(q) and q["st"] == "lowgrade"]
            if pre:
                r.update(stage="candidate_lowgrade", grade=max(q["grade"] for q in pre)); rows.append(r); continue
            r.update(stage="no_candidate", typ=n["typ"]); rows.append(r)
        mapped = {(k[1], k[2]) for k in ostaff}
        for ei in ext:
            n = o[ei]
            h = n.get("head")
            r = dict(name=name, bar=i, j=j, kind="extra", midi=n["midi"], onset=str(n["onset"]))
            if not h:
                r.update(stage="extra_nohead"); rows.append(r); continue
            r.update(sheet=h["sheet"], staff=h["staff"], p=h["p"], x=h["x"], y=h["y"], w=h["w"], h=h["h"], shape=h["shape"], head=h["id"], grade=T["add"].get((h["sheet"], h["id"]), {}).get("grade"), hh=hh)
            if n.get("_used"):
                r.update(stage="paired_with_missing")
            elif mapped and (h["sheet"], h["staff"]) not in mapped and t and not any(staff_map(s) == (h["sheet"], h["staff"]) for s in {x["staff"] for x in t}):
                r.update(stage="extra_foreign_staff")
            else:
                r.update(stage="extra_head")
            rows.append(r)
    return rows

def main():
    OUTD = SCR / "heads"
    tag = sys.argv[1]
    runs = OUTD / "runs" / tag
    c = json.loads((SCR / "scan-diag/classified.json").read_text())
    items = {}
    for t in ("native-inspect", "real-z1"):
        for it in json.loads((SCR / "scan-diag/items" / t / "items.json").read_text()):
            items[it["name"]] = it
    rows = []
    for k, v in c.items():
        name = k.split(":", 1)[1]
        wanted = [b["bar"] for b in v if b.get("first") == "note_missing_or_extra"]
        if not wanted: continue
        d = runs / name
        mxl = next(d.glob("*.mxl"))
        rows += analyse(name, Path(items[name]["truth"]).read_bytes(), mxl.read_bytes(), d / "trace.txt", wanted)
    (OUTD / f"attrib-{tag}.json").write_text(json.dumps(rows, default=str, indent=0))
    C = collections.Counter(); B = collections.defaultdict(set); R = collections.Counter(); RB = collections.defaultdict(set); conf = collections.Counter()
    for r in rows:
        key = (r["kind"], r["stage"])
        C[key] += 1; B[key].add((r["name"], r["bar"]))
        if r["stage"].startswith("removed"):
            R[r["rule"]] += 1; RB[r["rule"]].add((r["name"], r["bar"]))
        conf[(r["stage"], r.get("conf"))] += 1
    print("rows", len(rows), "bars", len({(r["name"], r["bar"]) for r in rows}))
    for k, v in C.most_common(): print(k, v, "bars", len(B[k]))
    for k, v in R.most_common(): print(" ", k, v, "bars", len(RB[k]))
    print(conf.most_common(30))
if __name__ == "__main__":
    main()
