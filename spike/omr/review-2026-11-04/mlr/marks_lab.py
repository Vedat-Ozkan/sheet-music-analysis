import pickle, collections
from pathlib import Path
M = Path(__file__).parent
lab = pickle.load(open(M / "lab.pkl", "rb"))
L = """F P D D R H D H H D F R L R R L R H D H P H L L D L R L R W D L W D R F L D L P
W D P D F H H W D W R D P D R R R R F W R L L R F H L D H D F L L W D R D P D H
L R R L L R R R P D D H L F W P P P L D L R P D W L H F H L H D D D W W W P R R
H D L R L D R D R H L R F F L P F P D L D L P L H L F D H D H D L H D W P P L L
L D L L D D D R H R H F R P H H D H H P L W H F W L R R L L W H F R L D L D H W""".split()
assert len(L) == 200
for m, l in zip(lab, L):
    m["lab"] = l
pickle.dump(lab, open(M / "lab_done.pkl", "wb"))
print(collections.Counter(L))
c = collections.defaultdict(collections.Counter)
for m in lab:
    dy = m["rel"][1] if m["rel"] else None
    c[m["lab"]]["n"] += 1
    if dy is None: c[m["lab"]]["norel"] += 1
    else:
        for th in (1.5, 2.0, 2.5, 3.0):
            c[m["lab"]][f">={th}"] += dy >= th
    c[m["lab"]]["word"] += bool(m["word"])
    c[m["lab"]]["word_near"] += bool(m["word_near"])
    c[m["lab"]]["vector"] += bool(m["pdfchars"])
for k, v in sorted(c.items()):
    print(k, dict(v))
print(collections.Counter((m["lab"], m["tag"]) for m in lab).most_common(30))
print(collections.Counter((m["lab"], m["stem"].rsplit("--",1)[1]) for m in lab).most_common(40))
