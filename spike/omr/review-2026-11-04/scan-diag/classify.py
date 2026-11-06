import collections, json, sys, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
sys.path[:0] = ["/home/kema/projects/sheet-music-plugin/spike/omr/speed"]
from whole_bars import OMR, HERE, parse, pitches, exact, sounding, rests, ties
from barparse import align_bars, timed

STEPS = {0:"C",1:"C",2:"D",3:"D",4:"E",5:"F",6:"F",7:"G",8:"G",9:"A",10:"A",11:"B"}

def states(bars):
    clef, key, out = {}, {}, []
    for b in bars:
        clef.update(b.clef); key.update(b.key)
        out.append((dict(clef), dict(key)))
    return out

def staffkey(k):
    return k[1]

def pitch_kinds(t, o):
    missing = pitches(t) - pitches(o)
    extra = pitches(o) - pitches(t)
    kinds = collections.Counter()
    miss = sorted(missing.elements()); ext = sorted(extra.elements())
    for m in list(miss):
        for e in ext:
            if abs(e - m) == 12 or abs(e - m) == 24:
                kinds["octave"] += 1; miss.remove(m); ext.remove(e); break
    for m in list(miss):
        for e in ext:
            if abs(e - m) in (1, 2) and STEPS[e % 12] == STEPS[m % 12]:
                kinds["accidental"] += 1; miss.remove(m); ext.remove(e); break
    for m in list(miss):
        for e in ext:
            if abs(e - m) <= 4:
                kinds["head_position"] += 1; miss.remove(m); ext.remove(e); break
    kinds["missing_note"] += len(miss); kinds["extra_note"] += len(ext)
    return kinds

def time_kinds(t, o):
    def bymidi(b):
        d = collections.defaultdict(list)
        for e in b.events:
            for m in e.midis:
                d[m].append((e.onset, e.dur, e.tuplet))
        return d
    a, c = bymidi(t), bymidi(o)
    kinds = collections.Counter()
    for m in a.keys() & c.keys():
        x, y = sorted(a[m]), sorted(c[m])
        for (on1, d1, tu1), (on2, d2, tu2) in zip(x, y):
            if on1 != on2:
                kinds["onset"] += 1
            elif d1 != d2:
                r = d2 / d1 if d1 else 0
                if tu1 != tu2: kinds["tuplet"] += 1
                elif r in (2, 4, 8, type(r)(1, 2), type(r)(1, 4), type(r)(1, 8)): kinds["dur_beam_flag"] += 1
                elif r in (type(r)(3, 2), type(r)(2, 3), type(r)(3, 4), type(r)(4, 3)): kinds["dot"] += 1
                else: kinds["dur_other"] += 1
    return kinds

def bar_full(b):
    ends = collections.defaultdict(lambda: 0)
    for e in b.events:
        ends[(e.part, e.staff, e.voice)] = max(ends[(e.part, e.staff, e.voice)], e.onset + e.dur)
    return ends

def classify_piece(tdata, odata):
    tb = parse(tdata)
    if odata is None:
        return [{"bar": i, "first": "no_reading", "ok": False} for i in range(len(tb))]
    ob = parse(odata)
    pairs = dict(align_bars(tb, ob))
    ts, os_ = states(tb), states(ob)
    out = []
    last = len(tb) - 1
    for i, t in enumerate(tb):
        j = pairs.get(i)
        if j is None:
            out.append({"bar": i, "first": "unpaired_bar", "ok": False, "n": sum(pitches(t).values())}); continue
        o = ob[j]
        ok = exact(t, o, True)
        row = {"bar": i, "j": j, "ok": ok, "n": sum(pitches(t).values())}
        if ok:
            out.append(row); continue
        clef_bad = sorted(k[1] for k in ts[i][0] if ts[i][0][k][:2] != os_[j][0].get(k, (None, None))[:2])
        tk = next(iter(ts[i][1].values()), 0); ok_ = next(iter(os_[j][1].values()), 0)
        key_bad = tk != ok_
        pk = pitch_kinds(t, o)
        tk2 = time_kinds(t, o) if not sum(pk.values()) else time_kinds(t, o)
        rest_bad = rests(t, False) != rests(o, False)
        tie_bad = ties(t, False) != ties(o, False)
        tie_t = sum(ties(t, False).values()); tie_o = sum(ties(o, False).values())
        pool_ok = exact(t, o, False)
        row.update(clef=clef_bad, key=key_bad, tk=tk, ok_key=ok_, pitch=dict(pk), time=dict(tk2), rest=rest_bad, tie=tie_bad,
                   tie_t=tie_t, tie_o=tie_o, last=i == last, staff_only=pool_ok, count=len(ob))
        if clef_bad and sum(pk.values()): first = "clef"
        elif key_bad and sum(pk.values()): first = "key"
        elif pk["octave"]: first = "octave"
        elif pk["accidental"] and pk["accidental"] >= max(pk["missing_note"], pk["extra_note"], pk["head_position"]): first = "accidental"
        elif pk["missing_note"] or pk["extra_note"]: first = "note_missing_or_extra"
        elif pk["head_position"]: first = "head_position"
        elif sum(tk2.values()): first = "rhythm_" + max(tk2, key=tk2.get)
        elif rest_bad: first = "rest"
        elif tie_bad: first = "tie"
        elif pool_ok: first = "staff_assignment"
        else: first = "other"
        row["first"] = first
        out.append(row)
    return out

def main():
    pass

def old_main():
    variant_dir = sys.argv[1] if len(sys.argv) > 1 else None
    rows = {}
    split = json.loads((OMR / "bench-olimpic/split.json").read_text())
    for n in split["inspect"]:
        r = HERE / "cache/runs/marks1" / f"bench-olimpic--{n}--scan.musicxml"
        data = r.read_bytes() if r.exists() and r.stat().st_size else None
        rows["ol:" + n] = classify_piece((OMR / "bench-olimpic/truth" / f"{n}.musicxml").read_bytes(), data)
    m = json.loads((OMR / "bench-real/manifest.json").read_text())
    for e in m["pdfs"]:
        stem = e["pdf"].rsplit("/", 1)[-1][:-4]
        r = HERE / "cache/runs/marks1" / f"bench-real--{stem}.musicxml"
        rows["real:" + stem] = classify_piece((OMR / "bench-real" / m["pieces"][e["piece"]]["truth"]).read_bytes(), r.read_bytes())
    Path(__file__).with_name("classified.json").write_text(json.dumps(rows, default=str))
    for group in ("ol:", "real:"):
        c = collections.Counter(); bars = 0; okb = 0; multi = collections.Counter()
        for k, v in rows.items():
            if not k.startswith(group): continue
            for r in v:
                bars += 1; okb += r["ok"]
                if not r["ok"]:
                    c[r["first"]] += 1
                    for f in ("rest", "tie", "key", "staff_only"):
                        if r.get(f): multi[f] += 1
                    if r.get("clef"): multi["clef"] += 1
                    for kk, vv in (r.get("pitch") or {}).items():
                        if vv: multi["p_" + kk] += 1
                    for kk, vv in (r.get("time") or {}).items():
                        if vv: multi["t_" + kk] += 1
                    if r.get("tie") and r.get("last"): multi["tie_lastbar"] += 1
        print(group, "bars", bars, "exact", okb, "wrong", bars - okb)
        print(" first:", c.most_common())
        print(" any:", multi.most_common())
def rundir(tag):
    home = Path(__file__).parent
    items = json.loads((home / "items" / tag / "items.json").read_text())
    rows = {}
    for it in items:
        r = home / "runs" / tag / f"{it['name']}.musicxml"
        rows[it["name"]] = classify_piece(Path(it["truth"]).read_bytes(), r.read_bytes() if r.exists() else None)
    c = collections.Counter(); multi = collections.Counter(); pdfs = collections.defaultdict(set); bars = okb = 0
    for k, v in rows.items():
        for r in v:
            bars += 1; okb += r["ok"]
            if not r["ok"]:
                c[r["first"]] += 1; pdfs[r["first"]].add(k)
                for f in ("rest", "tie", "key"):
                    if r.get(f): multi[f] += 1
                if r.get("clef"): multi["clef"] += 1
                if r.get("tie") and r.get("last"): multi["tie_lastbar"] += 1
    print(tag, "bars", bars, "exact", okb, "first(bars/pdfs):", {k: f"{v}/{len(pdfs[k])}" for k, v in c.most_common()}, "any:", dict(multi))
    (home / "results" / f"classified-{tag}.json").write_text(json.dumps(rows, default=str))
if len(sys.argv) > 1:
    for tag in sys.argv[1:]:
        rundir(tag)
else:
    old_main()
