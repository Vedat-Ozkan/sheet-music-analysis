import collections, json, sys, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
sys.path[:0] = [str(Path(__file__).parent)]
from attrib import analyse
S = Path("/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad/heads")
def ledger_stats(tr):
    acc, dis = set(), collections.Counter()
    for l in tr:
        t = l.split()
        if t[0] == "LEDGER" and t[8] not in ("noref", "null"):
            g, m = t[8].split("/")
            if float(g) >= float(m): acc.add(tuple(t[1:8]))
        if t[0] == "LEDGERDISCARD":
            dis["noprev" if t[8] == "noprev" else "sigma"] += 1
    return len(acc), dis
def summarize(rows, traces, label, nbars):
    C = collections.Counter(); B = collections.defaultdict(set)
    for r in rows:
        k = r["stage"]
        if r["stage"] == "no_candidate":
            near = False
            for l in traces[r["name"]]:
                t = l.split()
                if t[0] == "LEDGERDISCARD" and int(t[1]) == r["sheet"] and int(t[2]) == r["staff"] and int(t[4]) < r["x"] + 1.5 * r["hh"] and int(t[4]) + int(t[6]) > r["x"] - 1.5 * r["hh"] and abs(r["p"]) >= 5:
                    near = True; break
            k = "no_candidate_ledger_discarded" if near else "no_candidate_other"
        if r["stage"].startswith("removed"):
            k = "removed:" + r["rule"].split("@")[0].split(".")[1]
        k = r["kind"] + " " + k
        C[k] += 1; B[k].add((r["name"], r["bar"]))
    print(label, "rows", len(rows), "bars", nbars)
    for k, v in C.most_common(): print(f"  {v:4d} {len(B[k]):4d} {k}")
    a = d = n = 0; dd = collections.Counter()
    for tr in traces.values():
        x, y = ledger_stats(tr); a += x; dd.update(y)
    print("  ledgers accepted", a, "discarded", dict(dd), f"{100 * sum(dd.values()) / max(a, 1):.1f}%")
c = json.loads((S / "cleantrace.json").read_text())
clean = json.loads((S / "clean.json").read_text())
rows = []; tr = {}; nb = 0
for it in clean:
    if c.get(it["name"]) is not True: continue
    d = S / "cleantrace" / it["name"]
    tr[it["name"]] = (d / "trace.txt").read_text().splitlines()
    mxl = next(d.glob("*.mxl"))
    rows += analyse(it["name"], Path(it["truth"]).read_bytes(), mxl.read_bytes(), d / "trace.txt", it["bars"]); nb += len(it["bars"])
(S / "attrib-clean.json").write_text(json.dumps(rows, default=str))
summarize(rows, tr, f"clean PDFs {len(tr)}", nb)
rows = json.loads((S / "attrib-probe1.json").read_text())
tr = {n: (S / "runs/link" / n / "trace.txt").read_text().splitlines() for n in {r["name"] for r in rows}}
summarize(rows, tr, "scans 25", 43)
