import pickle, random
from marks_mont import sheet, M
rows = pickle.load(open(M / "marksdiag_ink.pkl", "rb"))
ED = ("lilypond-mutopia", "real-scan-peters", "real-scan-schirmer")
false = [m for m in rows if m["cls"] == "false" and m["stem"].rsplit("--", 1)[1] not in ED]
print(len(false))
rng = random.Random(404)
rng.shuffle(false)
picked = false[:200]
pickle.dump(picked, open(M / "lab.pkl", "wb"))
for p in range(5):
    sheet(picked[p * 40:(p + 1) * 40], M / f"lab{p}.png", cols=8, size=165)
