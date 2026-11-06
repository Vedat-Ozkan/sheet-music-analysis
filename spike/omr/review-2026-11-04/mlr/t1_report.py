import pickle, collections, sys, json
from pathlib import Path
S = Path(__file__).parent
rows = pickle.loads((S / "t1.pkl").read_bytes())
sumr = [r for r in rows if r.get("summary")]
bars = [r for r in rows if not r.get("summary")]
print("PDFs", len(sumr), "tbars", sum(r["tbars"] for r in sumr), "obars", sum(r["obars"] for r in sumr), "oflag", sum(r["oflag"] for r in sumr), "tflag", sum(r["tflag"] for r in sumr))
MAIN = {"bench", "bench-heldout", "bench-heldout2", "bench-heldout3"}
def table(sel, label):
    c = collections.Counter()
    for r in sel:
        if r["i"] is None:
            c["read bar with no truth bar"] += 1
            c["read bar with no truth bar, flagged"] += r["of"]
            continue
        if r["j"] is None:
            c["truth bar not paired"] += 1
            c["truth bar not paired, truth flagged"] += r["tf"]
            continue
        c["paired"] += 1
        key = ("R" if r["of"] else "-") + ("T" if r["tf"] else "-")
        c[key] += 1
        c[key + (" exact" if r["exact"] else " wrong")] += 1
    p = c["paired"]
    print(f"\n{label}: paired {p} no-truth {c['read bar with no truth bar']} ({c['read bar with no truth bar, flagged']} flagged) unpaired truth {c['truth bar not paired']}")
    for key, name in (("RT", "flagged in reading AND truth"), ("R-", "flagged in reading only"), ("-T", "flagged in truth only"), ("--", "flagged in neither")):
        n = c[key]
        print(f"  {name:32} {n:5} {100*n/max(p,1):5.1f}%  exact {c[key+' exact']:5} wrong {c[key+' wrong']:5}")
    realrate = c["R-"] / max(p, 1)
    print(f"  subtraction estimate (R total - T total)/paired: {(c['RT']+c['R-']+c['read bar with no truth bar, flagged'] - c['RT']-c['-T'])/max(p,1)*100:.1f}%; bar-by-bar reading-only: {realrate*100:.1f}%; wrong|reading-only {c['R- wrong']/max(c['R-'],1)*100:.0f}%; wrong|unflagged {c['-- wrong']/max(c['--'],1)*100:.1f}%")
table(bars, "ALL")
table([r for r in bars if r["set"] in MAIN], "main four sets")
table([r for r in bars if r["set"] == "bench-tune2"], "tune2")
table([r for r in bars if r["set"] == "bench-oldly"], "oldly")
table([r for r in bars if r["set"] == "bench-real"], "real scans")
pdf_t = collections.Counter()
for r in sumr:
    pdf_t[r["stem"]] += r["tflag"]
print("\ntruth flags by piece, top:", pdf_t.most_common(14), "pdfs with any", sum(1 for v in pdf_t.values() if v))
