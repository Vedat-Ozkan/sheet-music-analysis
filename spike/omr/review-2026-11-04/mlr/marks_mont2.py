import pickle, random, collections
from pathlib import Path
from marks_mont import sheet, M
rows = pickle.load(open(M / "marksdiag_ink.pkl", "rb"))
rng = random.Random(11)
false = [m for m in rows if m["cls"] == "false"]
def eng(m): return m["stem"].rsplit("--", 1)[1]
EDIT = ("lilypond-mutopia", "real-scan-peters", "real-scan-schirmer")
sel = {
 "a": [m for m in false if eng(m) in ("ly-old",) and m["bucket"].startswith("music")],
 "b": [m for m in false if eng(m) in ("ms", "ly") and m["bucket"].startswith("music")],
 "c": [m for m in false if eng(m) in EDIT],
 "d": [m for m in false if eng(m) in ("ms","ly","ly-old") and m["bucket"] == "no_char"],
}
for k, r in sel.items():
    rng.shuffle(r)
    sheet(r[:48], M / f"mb_{k}.png", size=140, cols=8)
    print(k, len(r))
pickle.dump({k: r[:48] for k, r in sel.items()}, open(M / "mb.pkl", "wb"))
