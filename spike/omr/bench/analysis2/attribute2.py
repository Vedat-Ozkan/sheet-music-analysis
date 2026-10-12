"""Attribution of lost notes (adapted from ../analysis/attribute.py) for bench/ or bench-heldout/, plus shifted-vs-wrong split.
usage: attribute2.py BENCHDIR RESULTS.json OUT.json [--fix]   (--fix: apply triplet post-fix prototype to the OMR first)"""
import collections, hashlib, json, sys
from fractions import Fraction
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis"))
import attribute as A
from attribute import rx, STEP, align
import xml.etree.ElementTree as ET

def events2(data, fix=None):
    """per measure: (midi, onset, flags) with flags incl. dur (sounding). Voices kept per part/staff/voice."""
    root = rx(data) if not isinstance(data, ET.Element) else data
    parts = [list(p.iter("measure")) for p in root.iter("part")]
    out = [[] for _ in range(max((len(p) for p in parts), default=0))]; meta = [collections.Counter() for _ in out]
    for pi, ps in enumerate(parts):
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
                              "voice": (pi, el.findtext("voice"), el.findtext("staff")), "dur": dur}
                        out[k].append((mi, on, fl))
                        meta[k]["tup"] += fl["tup"]; meta[k]["grace"] += grace; meta[k]["dot"] += fl["dot"]
                    if not chord and not grace: last = cur; cur += dur
    return out, meta

def main():
    bd = Path(sys.argv[1]).resolve(); res = json.load(open(sys.argv[2])); outp = sys.argv[3]; fix = "--fix" in sys.argv
    sig = res["audiveris_install"]; man = json.load(open(bd / "manifest.json"))
    tot = collections.Counter(); eng = collections.defaultdict(collections.Counter); rows = []; inv = collections.Counter()
    split = collections.Counter()
    for p in man["pdfs"]:
        key = hashlib.sha256((bd / p["pdf"]).read_bytes() + sig.encode()).hexdigest()[:32]
        truth = (bd / man["pieces"][p["piece"]]["truth"]).read_bytes()
        meta = json.loads((bd / "cache" / f"{key}.json").read_text())
        omrp = bd / "cache" / f"{key}.musicxml"
        T, Tm = events2(truth); tn = sum(len(b) for b in T); r = collections.Counter()
        if not omrp.exists():
            r["a_crash"] = tn
        else:
            data = omrp.read_bytes()
            if fix:
                sys.path.insert(0, str(Path(__file__).parent)); import tripletfix
                root = rx(data); tripletfix.fix(root); data = root
            O, Om = events2(data)
            tk = [collections.Counter((m, 0) for m, _, _ in b) for b in T]; ok = [collections.Counter((m, 0) for m, _, _ in b) for b in O]
            pairs, _ = align([(b,) for b in tk], [(b,) for b in ok]); pt = dict(pairs); matched = set(pt.values())
            for i, b in enumerate(T):
                if i not in pt:
                    r["a_page_skipped" if meta.get("skipped") else "b_bar_missing"] += len(b); continue
                j = pt[i]
                tc = collections.Counter((m, o) for m, o, _ in b); oc = collections.Counter((m, o) for m, o, _ in O[j])
                tl = list((tc - oc).elements()); ol = list((oc - tc).elements())
                tf = {}; of = {}
                for m, o, f in b: tf.setdefault((m, o), []).append(f)
                for m, o, f in O[j]: of.setdefault((m, o), []).append(f)
                rem = []
                for t in tl:
                    c = next((x for x in ol if x[0] == t[0]), None)
                    if c is None: rem.append(t); continue
                    ol.remove(c); a = tf[t][0]; cf = of[c][0]; tmm, omm = Tm[i], Om[j]
                    if a["tup"] and not cf["tup"]: sub = "e_tuplet_member_missing"
                    elif cf["tup"] and not a["tup"]: sub = "e_tuplet_member_invented"
                    elif tmm["tup"] > omm["tup"]: sub = "e_shifted_by_missing_tuplet_in_bar"
                    elif omm["tup"] > tmm["tup"]: sub = "e_shifted_by_invented_tuplet_in_bar"
                    elif tmm["grace"] != omm["grace"]: sub = "e_grace"
                    elif tmm["dot"] > omm["dot"]: sub = "e_dot_missing"
                    elif omm["dot"] > tmm["dot"]: sub = "e_dot_added"
                    elif len({f["voice"] for _, _, f in O[j]}) != len({f["voice"] for _, _, f in b}): sub = "e_voice_count"
                    else: sub = "e_other_beam_voice_timing"
                    r[sub] += 1
                    # part 4: own duration wrong vs only shifted
                    split["onset_wrong_total"] += 1
                    if a["dur"] != cf["dur"]: split["wrong_itself(duration differs)"] += 1
                    else: split["shifted(same duration, onset off)"] += 1
                    split["sub:" + sub + (":dur_same" if a["dur"] == cf["dur"] else ":dur_diff")] += 1
                rem2 = []
                for t in rem:
                    cand = [x for x in ol if x[1] == t[1]]; best = None
                    for lo, hi, ix in ((0, 0, 0), (1, 2, 1), (19, 22, 2), (3, 9, 3)):
                        for x in cand:
                            dl = abs(x[0] - t[0])
                            if (ix == 0 and dl % 12 == 0) or (ix and lo <= dl <= hi): best = (ix, x); break
                        if best: break
                    if best:
                        ol.remove(best[1]); r[["c_octave", "c_semitone_or_tone", "c_clef_treble_bass_shift", "c_other_pitch_3_to_9_semitones"][best[0]]] += 1
                    else: rem2.append(t)
                for t in rem2:
                    r["d_grace_missing" if all(f["grace"] for f in tf[(t[0], t[1])]) else "d_head_missing"] += 1
                for x in ol: inv["invented_in_aligned_bar"] += 1
            for j, b in enumerate(O):
                if j not in matched: inv["invented_in_extra_bar"] += len(b)
        lost = sum(r.values()); rows.append({"pdf": p["pdf"], "engraver": p["engraver"], "truth_notes": tn, "lost": dict(r), "lost_total": lost})
        tot.update(r); eng[p["engraver"]].update(r); tot["_truth"] += tn; eng[p["engraver"]]["_truth"] += tn
    json.dump({"total": dict(tot), "by_engraver": {k: dict(v) for k, v in eng.items()}, "invented": dict(inv), "split": dict(split), "pdfs": rows}, open(outp, "w"), indent=1)
    T = tot["_truth"]; print("truth", T, "lost", sum(v for k, v in tot.items() if k[0] != "_"), "invented", dict(inv))
    for k, v in sorted(tot.items(), key=lambda kv: -kv[1]):
        if k[0] != "_": print(f"{k:42s}{v:6d} {100*v/T:5.1f}%")
    for k, v in sorted(split.items()): print(k, v)
if __name__ == "__main__":
    main()
