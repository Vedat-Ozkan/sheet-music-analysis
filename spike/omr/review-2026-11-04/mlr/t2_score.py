import collections, pickle, sys, time
from fractions import Fraction as F
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from mx import *

S = Path(__file__).parent
def printed_rests(bar):
    c = collections.Counter()
    for e in bar.events:
        if e.rest and not e.hidden:
            c[(e.part, e.onset, e.dur)] += 1
    return c
def tie_set(bar):
    c = collections.Counter()
    for e in bar.events:
        for m, t in e.ties:
            if t == "start":
                c[(m, e.onset)] += 1
    return c
def durs(bar):
    c = collections.Counter()
    for e in bar.events:
        for m in e.midis:
            c[(m, e.onset, e.dur)] += 1
    return c
def marks(bar):
    c = collections.Counter()
    for e in bar.events:
        for k in e.marks:
            c[(k, e.onset)] += 1
    return c
T = collections.defaultdict(collections.Counter)
perpdf = []
pairs_all = {}
t0 = time.time()
for name, stem, piece, eng, data, tdata in readings():
    try:
        tb, ob = parse(tdata), parse(data)
    except Exception as e:
        print("ERR", stem, e); continue
    pairs = align_bars(tb, ob)
    pairs_all[(name, stem)] = pairs
    kinds = ["all", name, "eng:" + ("scan" if name == "bench-real" else eng)]
    row = collections.Counter()
    row["tbars"], row["obars"] = len(tb), len(ob)
    paired = dict(pairs)
    for i, t in enumerate(tb):
        j = paired.get(i)
        row["bars"] += 1
        tn = sum(pitches(t).values())
        row["tnotes"] += tn
        if j is None:
            row["unpaired_t"] += 1
            row["t_rests"] += sum(printed_rests(t).values())
            row["t_ties"] += sum(tie_set(t).values())
            row["t_marks"] += sum(marks(t).values())
            row["t_dyn"] += len(t.dyn)
            continue
        o = ob[j]
        pok = pitches(t) == pitches(o)
        tok = timed(t) == timed(o)
        dok = durs(t) == durs(o)
        rok = printed_rests(t) == printed_rests(o)
        tieok = tie_set(t) == tie_set(o)
        row["pitch_ok"] += pok
        row["timed_ok"] += tok
        row["dur_ok"] += dok
        row["rests_ok"] += rok
        row["ties_ok"] += tieok
        row["whole_ok"] += dok and rok and tieok
        row["shared_p"] += sum((pitches(t) & pitches(o)).values())
        row["shared_t"] += sum((timed(t) & timed(o)).values())
        row["shared_d"] += sum((durs(t) & durs(o)).values())
        row["onotes"] += sum(pitches(o).values())
        tr, orr = printed_rests(t), printed_rests(o)
        row["t_rests"] += sum(tr.values()); row["o_rests"] += sum(orr.values()); row["m_rests"] += sum((tr & orr).values())
        ti, oi = tie_set(t), tie_set(o)
        row["t_ties"] += sum(ti.values()); row["o_ties"] += sum(oi.values()); row["m_ties"] += sum((ti & oi).values())
        tm, om = marks(t), marks(o)
        row["t_marks"] += sum(tm.values()); row["o_marks"] += sum(om.values()); row["m_marks"] += sum((tm & om).values())
        tdyn = collections.Counter(d for d, _ in t.dyn); odyn = collections.Counter(d for d, _ in o.dyn)
        row["t_dyn"] += sum(tdyn.values()); row["o_dyn"] += sum(odyn.values()); row["m_dyn"] += sum((tdyn & odyn).values())
        trep = collections.Counter(r[0] for r in t.repeats); orep = collections.Counter(r[0] for r in o.repeats)
        row["t_rep"] += sum(trep.values()); row["o_rep"] += sum(orep.values()); row["m_rep"] += sum((trep & orep).values())
        row["t_endings"] += t.endings; row["o_endings"] += o.endings
        row["t_grace"] += t.grace; row["o_grace"] += o.grace
        row["m_grace"] += min(t.grace, o.grace)
        row["t_finger"] += t.fingerings; row["o_finger"] += o.fingerings
        row["t_text"] += len(t.texts); row["o_text"] += len(o.texts)
        row["t_wedge"] += t.wedges; row["o_wedge"] += o.wedges
        row["t_pedal"] += t.pedals; row["o_pedal"] += o.pedals
        row["t_breath"] += t.breaths; row["o_breath"] += o.breaths
    tk = next((v for b in tb for v in b.key.values()), None)
    ok = next((v for b in ob for v in b.key.values()), None)
    row["key_first_wrong"] += (tk or 0) != (ok or 0)
    row["key_keyed"] += bool(tk)
    row["extra_bars"] += max(0, len(ob) - len(tb))
    row["short_bars"] += max(0, len(tb) - len(ob))
    row["bar_count_off"] += len(tb) != len(ob)
    row["pdfs"] += 1
    for k in kinds:
        T[k].update(row)
    perpdf.append((name, stem, eng, dict(row), tk, ok))
(S / "t2.pkl").write_bytes(pickle.dumps((dict(T), perpdf, pairs_all)))
def pct(a, b): return f"{100*a/b:.1f}" if b else "-"
print("time", round(time.time() - t0))
order = ["all"] + SETS + sorted(k for k in T if k.startswith("eng:"))
print("group pdfs bars | pitchP timedP durP | barsP barsT barsD barsR barsTie whole | rests R/P ties R/P marks R/P dyn R/P rep R/P grace R | bars off")
for k in order:
    t = T[k]
    if not t: continue
    print(k, t["pdfs"], t["bars"], "|", pct(t["shared_p"], t["tnotes"]), pct(t["shared_t"], t["tnotes"]), pct(t["shared_d"], t["tnotes"]), "|",
          pct(t["pitch_ok"], t["bars"]), pct(t["timed_ok"], t["bars"]), pct(t["dur_ok"], t["bars"]), pct(t["rests_ok"], t["bars"]), pct(t["ties_ok"], t["bars"]), pct(t["whole_ok"], t["bars"]), "|",
          f"{pct(t['m_rests'], t['t_rests'])}/{pct(t['m_rests'], t['o_rests'])}", f"{pct(t['m_ties'], t['t_ties'])}/{pct(t['m_ties'], t['o_ties'])}",
          f"{pct(t['m_marks'], t['t_marks'])}/{pct(t['m_marks'], t['o_marks'])}", f"{pct(t['m_dyn'], t['t_dyn'])}/{pct(t['m_dyn'], t['o_dyn'])}",
          f"{pct(t['m_rep'], t['t_rep'])}/{pct(t['m_rep'], t['o_rep'])}", pct(t["m_grace"], t["t_grace"]), "|", t["bar_count_off"], t["extra_bars"], t["short_bars"], "key1wrong", t["key_first_wrong"])
a = T["all"]
print({k: a[k] for k in ("t_rests", "o_rests", "t_ties", "o_ties", "t_marks", "o_marks", "t_dyn", "o_dyn", "t_rep", "o_rep", "t_endings", "o_endings", "t_grace", "o_grace", "t_finger", "o_finger", "t_text", "o_text", "t_wedge", "o_wedge", "t_pedal", "o_pedal", "t_breath", "o_breath")})
