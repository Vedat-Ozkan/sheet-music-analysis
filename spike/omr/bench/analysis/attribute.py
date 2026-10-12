"""Attribute every truth note not matched by (pitch, onset) to one cause. usage: attribute.py [--dump PDFSUBSTR BAR]"""
import collections, hashlib, io, json, sys, zipfile
from fractions import Fraction
import xml.etree.ElementTree as ET
from pathlib import Path
HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE.parents[1])); sys.path.insert(0, str(HERE.parent))
from compare import align
STEP = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

def rx(data):
    if data[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            n = next(n for n in z.namelist() if n.endswith((".xml", ".musicxml")) and not n.startswith("META-INF"))
            return ET.fromstring(z.read(n))
    return ET.fromstring(data)

def events(data):
    """-> list per measure of notes (midi, onset Fraction, flags dict). Parts pooled; onsets by cursor/backup/forward."""
    root = rx(data); parts = [list(p.iter("measure")) for p in root.iter("part")]
    out = [[] for _ in range(max((len(p) for p in parts), default=0))]; meta = [collections.Counter() for _ in out]
    for ps in parts:
        div = 1
        for k, m in enumerate(ps):
            d = m.find("attributes/divisions")
            if d is not None: div = int(float(d.text))
            cur = Fraction(0); last = Fraction(0)
            for el in m:
                if el.tag == "backup": cur -= Fraction(int(float(el.findtext("duration"))), div)
                elif el.tag == "forward": cur += Fraction(int(float(el.findtext("duration"))), div)
                elif el.tag == "note":
                    dur = Fraction(int(float(el.findtext("duration") or 0)), div)
                    grace = el.find("grace") is not None; chord = el.find("chord") is not None
                    on = last if chord else cur
                    if el.find("rest") is None and el.find("pitch") is not None:
                        p = el.find("pitch")
                        mi = (int(p.findtext("octave")) + 1) * 12 + STEP[p.findtext("step")] + int(round(float(p.findtext("alter") or 0)))
                        fl = {"grace": grace, "tup": el.find("time-modification") is not None, "dot": el.find("dot") is not None,
                              "voice": (el.findtext("voice"), el.findtext("staff"))}
                        out[k].append((mi, on, fl))
                        meta[k]["tup"] += fl["tup"]; meta[k]["grace"] += grace; meta[k]["dot"] += fl["dot"]
                        meta[k]["v:%s" % (fl["voice"],)] += 0
                    if not chord and not grace: last = cur; cur += dur
                    elif not grace: pass
    return out, meta

DELTAS = collections.Counter(); EX = {}
def classify(pdf, truth_path, key):
    omr_path = HERE / "cache" / f"{key}.musicxml"
    meta = json.loads((HERE / "cache" / f"{key}.json").read_text())
    T, Tm = events((HERE / truth_path).read_bytes())
    tn = sum(len(b) for b in T)
    res = collections.Counter(); inv = collections.Counter(); detail = []
    if not omr_path.exists():
        res["a_crash"] = tn; return tn, res, inv, 0, len(T), 0
    O, Om = events(omr_path.read_bytes())
    tk = [collections.Counter((m, 0) for m, _, _ in b) for b in T]; ok = [collections.Counter((m, 0) for m, _, _ in b) for b in O]
    pairs, sp = align([(b,) for b in tk], [(b,) for b in ok])
    pt = {i: j for i, j in pairs}; matched_o = set(pt.values())
    matched = 0
    for i, b in enumerate(T):
        if i not in pt:
            res["a_page_skipped" if meta.get("skipped") else "b_bar_missing"] += len(b); continue
        j = pt[i]; before = res.copy(); binv = inv.copy()
        tc = collections.Counter((m, o) for m, o, _ in b); oc = collections.Counter((m, o) for m, o, _ in O[j])
        matched += sum((tc & oc).values())
        tl = list((tc - oc).elements()); ol = list((oc - tc).elements())
        tflags = {}; oflags = {}
        for m, o, f in b: tflags.setdefault((m, o), []).append(f)
        for m, o, f in O[j]: oflags.setdefault((m, o), []).append(f)
        # (e) same pitch, other onset
        rem_t = []
        for t in tl:
            c = next((x for x in ol if x[0] == t[0]), None)
            if c is None: rem_t.append(t); continue
            ol.remove(c)
            tmm, omm = Tm[i], Om[j]
            tf = tflags[t][0]; cf = next(f for m2, o2, f in O[j] if m2 == c[0] and o2 == c[1])
            if tf["tup"] and not cf["tup"]: sub = "e_tuplet_member_missing"
            elif cf["tup"] and not tf["tup"]: sub = "e_tuplet_member_invented"
            elif tmm["tup"] > omm["tup"]: sub = "e_shifted_by_missing_tuplet_in_bar"
            elif omm["tup"] > tmm["tup"]: sub = "e_shifted_by_invented_tuplet_in_bar"
            elif tmm["grace"] != omm["grace"]: sub = "e_grace"
            elif tmm["dot"] > omm["dot"]: sub = "e_dot_missing"
            elif omm["dot"] > tmm["dot"]: sub = "e_dot_added"
            elif len({f["voice"] for _, _, f in O[j]}) != len({f["voice"] for _, _, f in b}): sub = "e_voice_count"
            else: sub = "e_other_beam_voice_timing"
            res[sub] += 1
            if len(detail) < 0: pass
        # (c) wrong pitch with same onset
        rem2 = []
        for t in rem_t:
            cand = [x for x in ol if x[1] == t[1]]
            best = None
            for x in cand:
                dlt = abs(x[0] - t[0])
                if dlt % 12 == 0: best = (0, x); break
            if not best:
                for x in cand:
                    if abs(x[0] - t[0]) <= 2: best = (1, x); break
            if not best:
                for x in cand:
                    if 19 <= abs(x[0] - t[0]) <= 22: best = (2, x); break
            if not best:
                for x in cand:
                    if 3 <= abs(x[0] - t[0]) <= 9: best = (3, x); break
            if best:
                DELTAS[(best[0], best[1][0]-t[0])] += 1; EX.setdefault(best[0], []).append((pdf, i, j, t[0], best[1][0])); ol.remove(best[1]); res[["c_octave", "c_semitone_or_tone", "c_clef_treble_bass_shift", "c_other_pitch_3_to_9_semitones"][best[0]]] += 1
            else: rem2.append(t)
        # (d) head missing
        for t in rem2:
            fl = tflags[(t[0], t[1])]
            res["d_grace_missing" if all(f["grace"] for f in fl) else "d_head_missing"] += 1
        for x in ol:
            f = oflags[(x[0], x[1])][0]
            inv["invented_grace" if f["grace"] else "invented_tuplet_note" if f["tup"] else "invented_other_in_aligned_bar"] += 1
        import os
        if os.environ.get("DBG") == f"{pdf}:{i}": print("DBG bar", i, "->", j, "matched", sum((tc & oc).values()), "lost", dict(res - before), "inv", dict(inv - binv))
    for j, b in enumerate(O):
        if j not in matched_o: inv["invented_in_extra_bar"] += len(b)
    return tn, res, inv, matched, len(T), len(O)

if __name__ == "__main__":
    base = json.load(open(HERE / "results-baseline.json")); sig = base["audiveris_install"]
    man = json.load(open(HERE / "manifest.json"))
    rows = []; tot = collections.Counter(); eng = collections.defaultdict(collections.Counter)
    itot = collections.Counter(); ieng = collections.defaultdict(collections.Counter)
    for p in man["pdfs"]:
        key = hashlib.sha256((HERE / p["pdf"]).read_bytes() + sig.encode()).hexdigest()[:32]
        tn, res, inv, matched, tb, ob = classify(p["pdf"], man["pieces"][p["piece"]]["truth"], key)
        b = next(r for r in base["pdfs"] if r["pdf"] == p["pdf"])
        rows.append({"pdf": p["pdf"], "engraver": p["engraver"], "truth_notes": tn, "matched_mine": matched,
                     "matched_baseline": b["score"].get("shared_pitch_onset"), "truth_bars": tb, "omr_bars": ob,
                     "lost": dict(res), "invented": dict(inv)})
        tot.update(res); eng[p["engraver"]].update(res); tot["_truth"] += tn; eng[p["engraver"]]["_truth"] += tn
        tot["_matched"] += matched; eng[p["engraver"]]["_matched"] += matched
        itot.update(inv); ieng[p["engraver"]].update(inv)
    json.dump({"total": dict(tot), "by_engraver": {k: dict(v) for k, v in eng.items()},
               "invented_total": dict(itot), "invented_by_engraver": {k: dict(v) for k, v in ieng.items()}, "pdfs": rows},
              open(HERE / "analysis" / "attribution.json", "w"), indent=1)
    print(json.dumps(dict(tot), indent=0)); print(json.dumps(dict(itot)))
    print('DELTAS', DELTAS.most_common(14)); json.dump({k:v[:400] for k,v in EX.items()}, open(HERE/'analysis'/'c_examples.json','w'))
    print(sum(r["matched_mine"] for r in rows), sum(r["matched_baseline"] or 0 for r in rows))
