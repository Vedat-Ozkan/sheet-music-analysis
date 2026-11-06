import sys, re, collections, json, pickle
M = "/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad/mlr"
sys.path.insert(0, M)
from tie_book import *
from tie_cand import notes
from whole_bars import ties, sounding, rests, OMR
from fractions import Fraction as F

PT = re.compile(r"x=(\d+),y=(\d+)(?:,width=(\d+),height=(\d+))?")

def parse_log(path):
    seeds = collections.defaultdict(list)
    removed = collections.defaultdict(list)
    weed = None
    cur = {}
    for l in open(path, errors="replace"):
        if "TD " not in l:
            continue
        sheet = re.search(r"#(\d+)\]", l)
        sheet = int(sheet.group(1)) if sheet else 1
        body = l[l.index("TD "):]
        if body.startswith("TD weed"):
            m = re.search(r"before:(\d+) aftStaff:(\d+) aftShort:(\d+)", body)
            weed = tuple(map(int, m.groups()))
        elif body.startswith("TD side seed"):
            p = PT.findall(body)
            key = (sheet, int(p[0][0]), int(p[0][1]), int(p[1][0]), int(p[1][1]))
            m = re.search(r"rev:(\w+) before:(\d+) after:(\d+)", body)
            r = cur.setdefault(key, dict(key=key, sides={}))
            r["sides"][m.group(1)] = (int(m.group(2)), int(m.group(3)), weed)
            weed = None
        elif body.startswith("TD combos"):
            p = PT.findall(body)
            key = (sheet, int(p[0][0]), int(p[0][1]), int(p[1][0]), int(p[1][1]))
            m = re.search(r"left:(\d+) right:(\d+) inters:(\d+)", body)
            r = cur.setdefault(key, dict(key=key, sides={}))
            r["left"], r["right"], r["inters"] = map(int, m.groups())
            seeds[sheet].append(r)
            r["pending"] = r["inters"] > 0
            last = r
        elif body.startswith("TD prune"):
            m = re.search(r"selected (-?\d+)", body)
            last["selected"] = int(m.group(1))
            hs = re.findall(r"[LR]:(?:HeadInter#(\d+)|null)", body)
            last["L"], last["R"] = (hs + ["", ""])[:2] if len(hs) >= 2 else ("", "")
            t = re.search(r"tie:(\w+)", body)
            last["tie"] = t.group(1) if t else None
            q = PT.findall(body)
            last["sel_box"] = q[1] if len(q) > 1 else None
        elif body.startswith("TD removed"):
            q = PT.findall(body)[0]
            who = "orphan" if "discardOrphans" in body else "abnormal" if "checkAbnormal" in body or "SigReducer" in body else "other"
            removed[(sheet, q[0], q[1])].append(who)
    return seeds, removed

def heads_at(stack):
    contain = collections.defaultdict(list)
    for src, tgt, tag, attr in stack["rels"]:
        if tag == "containment":
            contain[src].append(tgt)
    offs = {sl.get("id"): sl.get("time-offset") for sl in stack["stack"].findall("slot")}
    out = collections.defaultdict(list)
    for pi, meas in enumerate(stack["measures"]):
        for v in meas.iter("voice"):
            for e in v.iter("entry"):
                val = e.find("value")
                if val is not None and val.get("status") == "BEGIN":
                    t = 4 * F(offs.get(e.findtext("key"), "0") or "0")
                    for h in contain.get(val.get("chord"), []):
                        i = stack["inters"].get(h)
                        if i is not None and i["box"] and i["tag"] == "head" or (i is not None and "head" in i["tag"]):
                            out[(pi, t)].append((float(i["attr"].get("pitch", 0)), int(i["attr"].get("staff", 0)), h, i["box"]))
    return out

def fate_of(r, removed):
    sides = r["sides"]
    if r.get("inters", 0) == 0:
        if r.get("left", 0) == 0 or r.get("right", 0) == 0:
            bad = [s for s, v in sides.items() if v[1] == 0]
            ws = [sides[s][2] for s in bad if sides[s][2]]
            if any(w[0] > 0 and w[1] == 0 for w in ws):
                return "F2 purgeStaffLines"
            if any(sides[s][0] == 0 for s in bad):
                return "F2b no model on a side"
            return "F2c other weed"
        return "F3 no inter (bad fit/low grade/no glyph)"
    if r.get("selected", -1) == -1:
        return "F4 ClumpPruner: no links"
    return "F5 selected"

def analyse(setname, stem, setting, rows):
    d = S / "mlr/td" / stem / f"s{setting}"
    seeds, removed = parse_log(d / "log.txt")
    z, stacks = load_book(d)
    man = json.loads((OMR / setname / "manifest.json").read_text())
    piece = stem.rsplit("--", 1)[0]
    mxl = sorted(d.glob("*.mxl"))[0].read_bytes()
    tb, ob = parse((OMR / setname / man["pieces"][piece]["truth"]).read_bytes()), parse(mxl)
    if len(stacks) != len(ob):
        print("skip mismatch", stem)
        return
    on, tn = notes(root_of(mxl)), notes(root_of((OMR / setname / man["pieces"][piece]["truth"]).read_bytes()))
    pairs = dict(align_bars(tb, ob))
    H = [heads_at(s) for s in stacks]
    def head_id(j, part, staff, midi, onset):
        if j is None or j >= len(on):
            return None
        same = sorted({m["midi"] for m in on[j] if m["part"] == part and m["onset"] == onset and m["staff"] == staff}, reverse=True)
        cand = H[j].get((part, onset), [])
        staffs = sorted({c[1] for c in cand})
        all_staffs = sorted({m["staff"] for m in on[j] if m["part"] == part})
        if not cand or midi not in same:
            return None
        idx = all_staffs.index(staff) if staff in all_staffs else 0
        pool = [c for c in cand if len(staffs) == 1 or (idx < len(staffs) and c[1] == staffs[idx])]
        pool = sorted(pool, key=lambda c: c[0])
        uniq = []
        for c in pool:
            if not uniq or uniq[-1][0] != c[0]:
                uniq.append(c)
        if len(uniq) != len(same):
            return None
        return uniq[same.index(midi)]
    for i, t in enumerate(tb):
        j = pairs.get(i)
        if j is None:
            continue
        o = ob[j]
        tt, ot = ties(t, True), ties(o, True)
        only = sounding(t, True) == sounding(o, True) and rests(t, True) == rests(o, True) and tt != ot
        for (key, midi, onset), c in (tt - ot).items():
            part, staff = key
            n = next((m for m in tn[i] if m["part"] == part and m["staff"] == staff and m["midi"] == midi and m["onset"] == onset), None)
            if n is None:
                continue
            e = None
            for kk in (i, i + 1):
                if kk >= len(tn) or e is not None:
                    continue
                for m in tn[kk]:
                    if m["part"] == part and m["midi"] == midi and m["tstop"] and (kk > i or m["onset"] > onset):
                        e = m
                        break
            base = dict(stem=stem, i=i, j=j, staff=staff, midi=midi, onset=str(onset), only=only)
            if e is None:
                rows.append(dict(base, fate="T0 truth tie has no end note"))
                continue
            bj = j if e["k"] == i else pairs.get(e["k"])
            a = next((m for m in on[j] if m["part"] == part and m["staff"] == staff and m["midi"] == midi and m["onset"] == onset), None)
            b = next((m for m in on[bj] if m["part"] == part and m["staff"] == e["staff"] and m["midi"] == midi and m["onset"] == e["onset"]), None) if bj is not None else None
            if a is None or b is None:
                rows.append(dict(base, fate="T1 note at an end not in reading"))
                continue
            L, R = head_id(j, part, staff, midi, onset), head_id(bj, part, e["staff"], midi, e["onset"])
            if L is None or R is None:
                rows.append(dict(base, fate="T2 cannot map to head"))
                continue
            sa, sb = stacks[j], stacks[bj]
            il = sa["il"]
            cross_sys = (sa["sheet"], sa["sys"]) != (sb["sheet"], sb["sys"])
            base["cross_sys"] = cross_sys
            base["cross_page"] = sa["sheet"] != sb["sheet"]
            def region(side):
                if not cross_sys:
                    xa, xb = L[3][0] - 1.5 * il, R[3][0] + R[3][2] + 1.5 * il
                    ya, yb = min(L[3][1], R[3][1]) - 4 * il, max(L[3][1], R[3][1]) + R[3][3] + 4 * il
                    return sa["sheet"], xa, xb, ya, yb
                if side == "L":
                    return sa["sheet"], L[3][0] - 1.5 * il, 99999, L[3][1] - 4 * il, L[3][1] + 4 * il
                return sb["sheet"], 0, R[3][0] + R[3][2] + 1.5 * il, R[3][1] - 4 * il, R[3][1] + 4 * il
            res = []
            for side in (("L", "R") if cross_sys else ("L",)):
                sh, xa, xb, ya, yb = region(side)
                span = (R[3][0] - L[3][0] - L[3][2]) if not cross_sys else 2 * il
                pick = []
                for r in seeds.get(sh, []):
                    _, x1, y1, x2, y2 = r["key"]
                    lo, hi = min(x1, x2), max(x1, x2)
                    if lo >= xa and hi <= xb and ya <= y1 <= yb and ya <= y2 <= yb and hi - lo >= 0.3 * span and hi - lo >= 0.5 * il:
                        pick.append(r)
                if cross_sys and side == "L":
                    pick = [r for r in pick if abs(min(r["key"][2], r["key"][1]+r["key"][3]-r["key"][3]) - L[3][1]) < 4 * il]
                if not pick:
                    res.append("F1 no seed arc")
                    continue
                def rank(r):
                    return (r.get("selected", -1) != -1 and str(r.get("L", "")) in (L[2], R[2]) or str(r.get("R", "")) in (L[2], R[2]), abs(r["key"][3] - r["key"][1]))
                pick.sort(key=rank, reverse=True)
                r = pick[0]
                f = fate_of(r, removed)
                if f == "F5 selected":
                    box = r.get("sel_box")
                    gone = removed.get((sh, box[0], box[1])) if box else None
                    if gone:
                        f = f"F6 selected then removed ({gone[-1]})"
                    elif cross_sys:
                        f = "F7 linked to heads " + ("(this head)" if str(r.get("L")) == L[2] or str(r.get("R")) == R[2] else "(other head)")
                    else:
                        lok, rok = str(r.get("L")) == L[2], str(r.get("R")) == R[2]
                        f = "F8 right heads but not tie" if lok and rok else "F9 one end right head" if lok or rok else "F10 both ends other heads"
                res.append(f)
            rows.append(dict(base, fate=" + ".join(res), L=L[2], R=R[2], lbox=L[3], rbox=R[3], sheet=sa["sheet"]))

if __name__ == "__main__":
    rows = []
    for l in open(M + "/sample_settings.txt"):
        a, b, s = l.split()
        analyse(a, b, s, rows)
    pickle.dump(rows, open(M + "/fate.pkl", "wb"))
    c = collections.Counter()
    for r in rows:
        kind = "x-page" if r.get("cross_page") else "x-sys" if r.get("cross_sys") else "same-sys"
        c[(r["fate"], kind, "only" if r["only"] else "-")] += 1
    for k, v in sorted(c.items()):
        print(v, k)
    print(len(rows))
