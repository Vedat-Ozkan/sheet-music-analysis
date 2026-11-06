import collections
import importlib.util
import json
import re
import statistics
import sys
import xml.etree.ElementTree as ET
from fractions import Fraction as F
from pathlib import Path

RUNS = Path(sys.argv[1])
TOOLS = Path(sys.argv[2])
OLD = Path(sys.argv[3])
OUT = Path(sys.argv[4])
BENCH = Path(__file__).resolve().parents[2] / "bench"


def load(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


flagged = load("flagged")
classify = load("classify2")

RANK = {"breve": -1, "whole": 0, "half": 1, "quarter": 2, "eighth": 3, "16th": 4, "32nd": 5, "64th": 6, "128th": 7}
REST_SHAPE = {"breve": {"BREVE_REST"}, "whole": {"WHOLE_REST", "HW_REST_set"}, "half": {"HALF_REST", "HW_REST_set"},
              "quarter": {"QUARTER_REST"}, "eighth": {"EIGHTH_REST"}, "16th": {"ONE_16TH_REST"}, "32nd": {"ONE_32ND_REST"},
              "64th": {"ONE_64TH_REST"}}
HEAD_SHAPE = {0: "WHOLE_NOTE", 1: "NOTEHEAD_VOID", 2: "NOTEHEAD_BLACK"}
ALT = re.compile(r"ALT (.*)$")
MEAS = re.compile(r"MEAS (.*)$")
NO_INK = {"tuplet"}
TOL = (1.0, 2.0)


def fields(text):
    return dict(item.split("=", 1) for item in text.split())


def xs(score):
    out = []
    for part in ET.fromstring(score).iter("part"):
        for k, m in enumerate(part.iter("measure")):
            while len(out) <= k:
                out.append([])
            for el in m:
                if el.tag in ("note", "forward"):
                    x = el.get("default-x")
                    out[k].append((float(x) if x is not None else None, el.find("beam") is not None))
    return out


def read_log(folder):
    alts, meas = [], {}
    for path in folder.glob("audiveris-*.txt"):
        for line in path.read_text(errors="replace").splitlines():
            if m := ALT.search(line):
                a = fields(m.group(1))
                for key in ("grade", "ctx", "rival"):
                    a[key] = float(a[key])
                for key in ("page", "sys", "staff", "x", "y", "w", "h", "il", "glyph"):
                    a[key] = int(a[key])
                alts.append(a)
            elif m := MEAS.search(line):
                f = fields(m.group(1))
                staves = [tuple(int(v) for v in s.split(":")) for s in f["staves"].split(";") if s]
                meas[(int(f["part"]), int(f["pos"]))] = {"page": int(f["page"]), "il": int(f["il"]), "staves": staves}
    best = {}
    for a in alts:
        key = (a["page"], a["shape"], a["x"], a["y"], a["w"], a["h"])
        if key not in best or a["grade"] > best[key]["grade"]:
            best[key] = a
    return list(best.values()), meas


def readings():
    manifest = json.loads((BENCH / "manifest.json").read_text())
    for folder in sorted(RUNS.iterdir()):
        info = folder / "reading.json"
        if not info.exists():
            continue
        meta = json.loads(info.read_text())
        truth = flagged.raw((BENCH / manifest["pieces"][meta["piece"]]["truth"]).read_bytes())
        yield folder, meta, truth, (folder / "reading.musicxml").read_bytes()


def flagged_bars(omr, truth, meta, stem):
    of, _ = flagged.spots(omr)
    tf, _ = flagged.spots(truth)
    O, om = flagged.events(omr)
    T, tm = flagged.events(truth)
    X = xs(omr)
    for k, evs in enumerate(O):
        order = [e for e in evs]
        for e, (x, beamed) in zip(order, X[k] if k < len(X) else []):
            e["x"], e["beamed"] = x, beamed
    pairs = flagged.fill(flagged.align([(flagged.pitches(b),) for b in T], [(flagged.pitches(b),) for b in O])[0], len(T), len(O))
    o2t = {j: i for i, j in pairs}
    for pos, f in sorted(of.items()):
        j, i = pos - 1, o2t.get(pos - 1)
        rec = {"set": "bench", "pdf": stem, "engraver": meta["engraver"], "omr_pos": pos, "omr_number": f["number"], "why": sorted(f["why"]),
               "full": str(f["full"]) if f["full"] is not None else None, "omr_meter": om[j] if j < len(om) else None,
               "truth_pos": None if i is None else i + 1, "omr_events": O[j]}
        if i is not None:
            rec.update(truth_meter=tm[i], truth_flagged=(i + 1) in tf, truth_events=T[i],
                       truth_prev_next_pitches_overlap=[sum((flagged.pitches(T[k]) & flagged.pitches(O[j])).values()) for k in (i - 1, i, i + 1) if 0 <= k < len(T)])
        yield rec


def classify_bar(r):
    a = classify.analyse(r) if r["truth_pos"] is not None else {"present": [], "sole": [], "needed": [], "all_fix": False, "base_fails": True}
    if r["truth_pos"] is not None and r["full"]:
        a.update(classify.truth_structured(r, F(r["full"]), classify.meter_full(r.get("truth_meter"))))
    return classify.bucket(r, a), a


def needed_causes(bucket):
    if bucket.startswith("combo"):
        return bucket.split(":", 1)[1].split("+") if not bucket.endswith("3+") else None
    if bucket.startswith(("voice", "unresolved", "bars_", "measure_")):
        return []
    return [bucket.replace(" (+voice/offset)", "")]


def items(r):
    T, O = classify.prep(r["truth_events"]), classify.prep(r["omr_events"])
    pp, pm, pe = classify.match(T, O, False)
    rp, rm, re_ = classify.match(T, O, True)
    out = []
    for t, o in pp + rp:
        if t["grace"] and not o["grace"]:
            if o["idx"] == o["head"]:
                out.append(("grace_as_real", t, o))
        elif o["grace"] and not t["grace"]:
            out.append(("real_as_grace", t, o))
        elif t["grace"]:
            continue
        elif bool(t["tup"]) != bool(o["tup"]) or (t["tup"] and o["tup"] and t["tup"] != o["tup"]):
            out.append(("tuplet", t, o))
        elif t["type"] != o["type"]:
            out.append(("type", t, o))
        elif t["dots"] != o["dots"]:
            out.append(("dot", t, o))
    seen = {(t["part"], t["voice"], t["on"]) for t, _ in pp + rp}
    for t in pm:
        if not t["grace"] and not t["chord"] and (t["part"], t["voice"], t["on"]) not in seen:
            out.append(("note_missing", t, None))
            seen.add((t["part"], t["voice"], t["on"]))
    for t in rm:
        if not t["mrest"]:
            out.append(("rest_missing", t, None))
    heads = {o["head"] for _, o in pp + rp}
    for o in pe:
        if not o["grace"] and o["idx"] == o["head"] and o["head"] not in heads:
            out.append(("note_extra", None, o))
    for o in re_:
        if not o["mrest"]:
            out.append(("rest_extra", None, o))
    return out, O


def estimate_x(t, O, full):
    same = [o for o in O if o["part"] == t["part"] and not o["grace"] and o.get("x") is not None and not o.get("fwd")]
    staff = [o for o in same if o["staff"] == t["staff"]] or same
    at = [o["x"] for o in staff if o["on"] == t["on"]] or [o["x"] for o in same if o["on"] == t["on"]]
    if at:
        return statistics.median(at)
    before = max((o for o in same if o["on"] < t["on"]), key=lambda o: (o["on"], o["x"]), default=None)
    after = min((o for o in same if o["on"] > t["on"]), key=lambda o: (o["on"], o["x"]), default=None)
    if before and after:
        return before["x"] + (after["x"] - before["x"]) * float((t["on"] - before["on"]) / (after["on"] - before["on"]))
    if before:
        return before["x"] + 25 * float(t["on"] - before["on"])
    if after:
        return max(0.0, after["x"] - 25 * float(after["on"] - t["on"]))
    return 10.0


def need(cause, t, o):
    if cause in NO_INK:
        return "no_ink", None
    if cause == "dot":
        return ("ink", "dot_add") if t["dots"] > o["dots"] else ("no_ink", "dot_drop")
    if cause == "type":
        rt, ro = RANK.get(t["type"], 2), RANK.get(o["type"], 2)
        if o["rest"]:
            return "ink", "rest_type"
        if min(rt, 2) != min(ro, 2):
            return "ink", "head_fill+flags" if rt > 2 else "head_fill"
        if rt > ro:
            return "ink", "flag_up"
        if o.get("beamed"):
            return "no_ink", "beam_down"
        return ("ink", "flag_down") if rt > 2 else ("no_ink", "flag_drop")
    if cause in ("grace_as_real", "note_missing", "note_extra", "rest_missing"):
        return "ink", cause
    return "none", cause


def matches(a, sub, t, o, x, il, tol):
    cx = a["x"] + a["w"] / 2
    if sub == "rest_missing":
        return a["kind"] == "REST" and abs(cx - x) <= tol * il
    if sub == "rest_type":
        return a["kind"] == "REST" and a["shape"] in REST_SHAPE.get(t["type"], ()) and abs(cx - x - 0.6 * il) <= tol * il
    if sub == "dot_add":
        return a["kind"] == "DOT" and 0.6 * il <= cx - x <= (2.5 + tol) * il
    if sub in ("grace_as_real", "note_extra"):
        return a["kind"] == "SMALL_HEAD" and abs(a["x"] - x) <= tol * il
    if sub == "note_missing":
        return a["kind"] in ("HEAD", "SMALL_HEAD") and abs(a["x"] - x) <= tol * il
    if sub in ("head_fill", "head_fill+flags"):
        target = HEAD_SHAPE[min(RANK.get(t["type"], 2), 2)]
        return a["kind"] == "HEAD" and a["shape"] == target and abs(a["x"] - x) <= tol * il
    if sub in ("flag_up", "flag_down"):
        if a["kind"] == "FLAG":
            wanted = RANK.get(t["type"], 2) - 2
            count = int(re.sub(r"\D", "", a["shape"]) or 1) if a["shape"].startswith("FLAG") else 1
            return (sub == "flag_up" or count == wanted) and -tol * il <= cx - x <= (2 + tol) * il
        return sub == "flag_up" and a["kind"] == "BEAM" and a["x"] - tol * il <= x + il and x <= a["x"] + a["w"] + tol * il
    return False


def evidence(item, bar, alts, meas, O, full, probe=None):
    cause, t, o = item
    kind, sub = ("ink", probe) if probe else need(cause, t, o)
    if kind != "ink":
        return {"cause": cause, "sub": sub, "need": kind}
    ref = o if o is not None else t
    m = meas.get((ref["part"] + 1, bar))
    if m is None or not m["staves"]:
        return {"cause": cause, "sub": sub, "need": "ink", "unmapped": True}
    staves = m["staves"]
    staff_index = int(ref["staff"]) - 1
    if staff_index >= len(staves):
        staff_index = len(staves) - 1
    staff_id, left, right = staves[staff_index]
    il = m["il"]
    rel = (o["x"] if o is not None and o.get("x") is not None else estimate_x(t, O, full))
    x = left + rel * il / 10
    out = {"cause": cause, "sub": sub, "need": "ink", "x": round(x), "staff": staff_id, "page": m["page"]}
    for tol in TOL:
        hits = [a for a in alts if a["page"] == m["page"] and a["staff"] == staff_id and matches(a, sub, t, o, x, il, tol)]
        if sub == "head_fill+flags" and hits:
            flags = [a for a in alts if a["page"] == m["page"] and a["staff"] == staff_id and matches(a, "flag_up", t, o, x, il, tol)]
            hits = hits if (flags or RANK.get(t["type"], 2) <= 2) else []
        if hits:
            top = max(hits, key=lambda a: a["grade"])
            out[f"tol{tol:g}"] = {"grade": top["grade"], "ctx": top["ctx"], "rival": top["rival"], "loss": top["loss"], "shape": top["shape"], "n": len(hits)}
    return out


SHORTER = {"half": "quarter", "quarter": "eighth", "eighth": "16th", "16th": "32nd", "32nd": "64th"}


def control(r, alts, meas):
    T, O = classify.prep(r["truth_events"]), classify.prep(r["omr_events"])
    out = []
    for t, o in classify.match(T, O, False)[0]:
        if t["grace"] or o["grace"] or t["type"] != o["type"] or t["dots"] != o["dots"] or t["tup"] != o["tup"] or o["idx"] != o["head"]:
            continue
        probes = [("rest_missing", t), ("grace_as_real", t), ("note_missing", t)]
        if o["type"] in SHORTER:
            probes.append(("flag_up", dict(t, type=SHORTER[o["type"]])))
        if not o["dots"]:
            probes.append(("dot_add", dict(t, dots=1)))
        for sub, fake in probes:
            ev = evidence(("control", fake, o), r["omr_pos"], alts, meas, O, None, probe=sub)
            out.append({"sub": sub, "tol1": ev.get("tol1"), "tol2": ev.get("tol2")})
    return out


def main():
    rows = []
    for folder, meta, truth, omr in readings():
        stem = folder.name
        logs = {s: read_log(folder / f"s{s}") for s in (0, 1) if (folder / f"s{s}").exists()}
        alts, meas = logs[meta["chosen"]]
        other = logs.get(1 - meta["chosen"])
        for r in flagged_bars(omr, truth, meta, stem):
            bucket, a = classify_bar(r)
            row = {"pdf": stem, "engraver": classify.GROUP[meta["engraver"]], "bar": r["omr_pos"], "number": r["omr_number"], "bucket": bucket,
                   "truth_flagged": bool(r.get("truth_flagged")), "chosen": meta["chosen"], "needed": needed_causes(bucket), "items": []}
            if r["truth_pos"] is not None and row["needed"]:
                its, O = items(r)
                full = F(r["full"]) if r["full"] else None
                for item in its:
                    if item[0] in row["needed"]:
                        ev = evidence(item, r["omr_pos"], alts, meas, O, full)
                        if other and ev.get("need") == "ink" and "tol1" not in ev:
                            ev["other_setting"] = "tol1" in evidence(item, r["omr_pos"], other[0], other[1], O, full)
                        row["items"].append(ev)
                row["control"] = control(r, alts, meas)
            rows.append(row)
    OUT.write_text(json.dumps(rows, indent=0, default=str))
    old = {(x["pdf"], x["omr_pos"]): x["bucket"] for x in json.load(open(OLD)) if x["set"] == "bench"}
    new = {(x["pdf"], x["bar"]): x["bucket"] for x in rows}
    pdfs = {x["pdf"] for x in rows} | {p for p, _ in old if (RUNS / p / "reading.json").exists()}
    old_here = {k: v for k, v in old.items() if k[0] in pdfs}
    print(f"drift vs classified3 on {len(pdfs)} PDFs: old {len(old_here)} bars, new {len(new)}, same bar {len(old_here.keys() & new.keys())}, "
          f"same bar+bucket {sum(old_here[k] == new[k] for k in old_here.keys() & new.keys())}")


if __name__ == "__main__":
    main()
