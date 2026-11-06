import sys, pickle, collections
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from tie_book import *
from tie_cand import notes
from whole_bars import ties, sounding, rests, OMR
import re, json, xml.etree.ElementTree as ET
from fractions import Fraction as F

def slurs_of(setname, stem, root, variant):
    s = choose_setting(setname, stem, root, variant)
    if s is None:
        return []
    z, stacks = load_book(root / stem / s)
    man = json.loads((OMR / setname / "manifest.json").read_text())
    piece = stem.rsplit("--", 1)[0]
    mxl = sorted((root / stem / s).glob("*.mxl"))[0].read_bytes()
    tb, ob = parse((OMR / setname / man["pieces"][piece]["truth"]).read_bytes()), parse(mxl)
    on = notes(root_of(mxl))
    pairs = {j: i for i, j in align_bars(tb, ob)}
    if len(stacks) != len(ob):
        print("mismatch", stem, len(stacks), len(ob))
        return []
    rows = []
    seen_sys = set()
    for j, st in enumerate(stacks):
        keysys = (st["sheet"], st["sys"])
        if keysys in seen_sys:
            continue
        seen_sys.add(keysys)
        sys_stacks = [(jj, x) for jj, x in enumerate(stacks) if (x["sheet"], x["sys"]) == keysys]
        inters, rels = st["inters"], st["rels"]
        contain = collections.defaultdict(list)
        slur = collections.defaultdict(dict)
        for src, tgt, tag, attr in rels:
            if tag == "containment":
                contain[tgt].append(src)
            elif tag == "slur-head":
                slur[src][attr["side"]] = tgt
        where = {}
        for jj, x in sys_stacks:
            offs = {sl.get("id"): sl.get("time-offset") for sl in x["stack"].findall("slot")}
            for meas in x["measures"]:
                for v in meas.iter("voice"):
                    for e in v.iter("entry"):
                        val = e.find("value")
                        if val is not None and val.get("status") == "BEGIN":
                            where[val.get("chord")] = (jj, 4 * F(offs.get(e.findtext("key"), "0") or "0"))
        for id_, i in inters.items():
            if i["tag"] != "slur":
                continue
            curve = i["el"].find("curve")
            sides = slur.get(id_, {})
            L, R = sides.get("LEFT"), sides.get("RIGHT")
            def stack_at(h):
                x = inters[h]["box"][0]
                return next((jj for jj, q in sys_stacks if q["left"] <= x <= q["right"]), None)
            def time_of(h):
                for c in contain.get(h, []):
                    if c in where:
                        return where[c]
                return None
            row = dict(set=setname, stem=stem, sheet=st["sheet"], sys=st["sys"], id=id_, box=i["box"], il=st["il"], tie=i["attr"].get("tie") == "true", grade=float(i["attr"].get("grade", 0)), ctx=float(i["attr"].get("ctx-grade", 0) or 0), attr=dict(i["attr"]))
            row["L"], row["R"] = L, R
            if curve is not None:
                row["x1"], row["y1"], row["x2"], row["y2"] = [float(curve.get(k)) for k in ("x1", "y1", "x2", "y2")]
            if L: row["lbox"], row["lpitch"], row["lstaff"] = inters[L]["box"], inters[L]["attr"].get("pitch"), inters[L]["attr"].get("staff")
            if R: row["rbox"], row["rpitch"], row["rstaff"] = inters[R]["box"], inters[R]["attr"].get("pitch"), inters[R]["attr"].get("staff")
            if L:
                t = time_of(L)
                row["ltime"] = t
                if t is None: row["lstack"] = stack_at(L)
                j0 = t[0] if t else stack_at(L)
                row["truthbar"] = pairs.get(j0)
                if t and row["truthbar"] is not None:
                    staffs = sorted({a["staff"] for a in on[t[0]]})
                    same = [a for a in on[t[0]] if a["onset"] == t[1]]
                    tt = ties(tb[row["truthbar"]], True)
                    ot = ties(ob[t[0]], True)
                    row["tt"] = {str(k) for k in tt if k[2] == t[1]}
                    row["ot"] = {str(k) for k in ot if k[2] == t[1]}
                    row["extra_here"] = len([k for k in ot - tt if k[2] == t[1]])
                    row["missing_here"] = len([k for k in tt - ot if k[2] == t[1]])
                    row["true_here"] = len([k for k in tt & ot if k[2] == t[1]])
            rows.append(row)
    return rows

if __name__ == "__main__":
    root = S / "mlr/tb"
    allr = []
    for line in open(S / "mlr/sample.txt"):
        name, stem = line.split()
        allr += slurs_of(name, stem, root, "pitch51")
    pickle.dump(allr, open(S / "mlr/geom.pkl", "wb"))
    print(len(allr), sum(r["tie"] for r in allr))
