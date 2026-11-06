import collections, json, re, sys, statistics
from pathlib import Path
S = Path("/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad/heads")
tag = sys.argv[1]
rows = json.load(open(S / f"attrib-{tag}.json"))
tr = {}
def load(name):
    if name in tr: return tr[name]
    d = dict(excl={}, nostem={}, stemrm=collections.defaultdict(list), stemlist=[], wrong=collections.defaultdict(list), probe=[])
    for l in open(S / "runs" / tag / name / "trace.txt"):
        t = l.split()
        if t[0] == "EXCL": d["excl"][(int(t[1]), int(t[2]))] = t[3:]
        elif t[0] == "NOSTEM": d["nostem"][(int(t[1]), int(t[2]))] = (t[7][6:], t[8][6:])
        elif t[0] == "STEMREMOVE":
            rec = dict(sheet=int(t[1]), id=int(t[2]), x=int(t[3]), y=int(t[4]), w=int(t[5]), h=int(t[6]), grade=float(t[7]), heads=t[8][6:], where=t[9])
            d["stemlist"].append(rec)
            for h in rec["heads"].strip(",").split(","):
                if h != "-": d["stemrm"][(rec["sheet"], int(h))].append(rec)
        elif t[0] == "WRONGSIDE": d["wrong"][(int(t[1]), int(t[2]))].append(t[3])
        elif t[0] == "PROBE": d["probe"].append(dict(sheet=int(t[1]), staff=int(t[2]), p=int(t[3]), x=int(t[4]), shape=t[6], how=t[7], out=t[8], low=float(t[9][4:])))
    tr[name] = d
    return d
SKIP = ("HeadTrace", "AbstractInter.remove", "AbstractChordInter", "AbstractNoteInter", "StemInter.remove", "SIGraph.deleteInters")
def frame(w):
    return next((f.split(":")[0] for f in w.split(">") if not f.startswith(SKIP)), "?")
C = collections.Counter(); B = collections.defaultdict(set); ex = collections.defaultdict(list)
for r in rows:
    if r["kind"] != "missing": continue
    d = load(r["name"])
    key = None
    if r["stage"].startswith("removed"):
        k = (r["sheet"], r["head"])
        rl = r["rule"].split("@")[0]
        if rl == "SigReducer.checkHeads":
            st, sd = d["nostem"].get(k, ("?", "?"))
            sr = d["stemrm"].get(k)
            wr = d["wrong"].get(k)
            if sr: key = "nostem:stem_removed_by " + frame(sr[-1]["where"])
            elif wr: key = "nostem:wrong_side"
            elif st != "-" : key = "nostem:stem_nearby_unlinked"
            elif sd != "-": key = "nostem:seed_nearby_no_stem"
            else: key = "nostem:no_seed_no_stem"
            r["seeds"] = sd; r["stems"] = st
        elif rl == "SIGraph.reduceExclusions":
            e = d["excl"].get(k)
            key = "excl_by:" + (e[2] if e else "?") + ":" + (e[-1] if e else "?")
        else:
            key = "other:" + rl
        key = r["stage"] + " " + key
    elif r["stage"] in ("no_candidate", "candidate_seedconflict"):
        pb = [q for q in d["probe"] if q["sheet"] == r["sheet"] and q["staff"] == r["staff"] and q["p"] == r["p"] and abs(q["x"] - r["x"]) <= r["tol"] + 1.5 * r["hh"]]
        if not pb:
            key = "nc:not_scanned"
        else:
            ds = [float(q["out"][2:]) for q in pb if q["out"].startswith("d=")]
            r["bestd"] = min(ds) if ds else None; r["low"] = pb[0]["low"]
            outs = collections.Counter(q["out"].split(":")[1].split("#")[0] if q["out"].startswith("over") else q["out"][:3] for q in pb)
            r["outs"] = dict(outs.most_common(4))
            over = sum(v for k2, v in outs.items() if k2 != "d=" and k2 != "d=0")
            if ds and min(ds) <= pb[0]["low"]: key = "nc:below_threshold_but_no_cand"
            elif ds: key = "nc:template_too_far"
            else: key = "nc:all_blocked"
        key = r["stage"] + " " + key
    else:
        key = r["stage"]
    r["sub"] = key
    C[key] += 1; B[key].add((r["name"], r["bar"]))
for k, v in C.most_common(): print(v, len(B[k]), k)
(S / f"detail-{tag}.json").write_text(json.dumps(rows, default=str))
