import pickle, collections, random, json
from pathlib import Path
rows = pickle.load(open(Path(__file__).with_name("marks_rows_tie2.pkl"), "rb"))
by = collections.Counter((r[0], r[1]) for r in rows)
g = collections.defaultdict(list)
for (name, stem), n in by.items():
    eng = stem.rsplit("--", 1)[1]
    g[eng].append((name, stem, n))
print({k: (len(v), sum(x[2] for x in v)) for k, v in g.items()})
quota = {"ms": 9, "vr": 6, "ly": 4, "ly-old": 6, "scan": 5, "lilypond-mutopia": 1, "real-scan-peters": 1, "real-scan-schirmer": 1}
rng = random.Random(20261104)
pick = []
for eng, q in quota.items():
    items = list(g[eng])
    chosen = []
    while items and len(chosen) < q:
        i = rng.choices(range(len(items)), weights=[x[2] for x in items])[0]
        chosen.append(items.pop(i))
    pick += chosen
for p in pick: print(p)
print(sum(p[2] for p in pick), "of", len(rows))
json.dump(pick, open(Path(__file__).with_name("marks_sample.json"), "w"))
