import pickle, sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from tie_tab_labels import label_m, label_e
rows = pickle.load(open(sys.argv[1], "rb"))
stems = {l.split()[1]: l.split()[0] for l in open(sys.argv[2])}
for r in rows:
    if r["stem"] in stems:
        lab = (label_m if r["kind"] == "missing" else label_e)(r)
        if lab[:2] in ("M0", "E0"): continue
        print(r["stem"][:28], "only" if r["only"] else "-   ", r["i"], r["j"], "t#"+str(r["tnum"]), "o#"+str(r["onum"]), r["staff"], r["midi"], r["onset"], r["bonset"], lab[:48])
