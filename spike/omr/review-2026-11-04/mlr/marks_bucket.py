import pickle, collections, sys, random
from pathlib import Path
M = Path(__file__).parent
rows = pickle.load(open(M / "marksdiag_ink.pkl", "rb"))
MUSIC = ("Emmentaler", "Leland", "Leipzig", "Bravura", "Petaluma", "Finale", "Gootville", "MScore", "Sebastian")
def iou(m, c):
    ax, ay, aw, ah = m["x"], m["y"], m["w"], m["h"]
    bx, by, bw, bh = c[2:]
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx)); iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    return ix * iy / max(1, aw * ah + bw * bh - ix * iy)
def bucket(m):
    eng = m["stem"].rsplit("--", 1)[1]
    ch = [c for c in m["pdfchars"] if c[0].strip()]
    text = [c for c in ch if not c[1].startswith(MUSIC) and "GlyphLess" not in c[1]]
    mus = [c for c in ch if c[1].startswith(MUSIC)]
    if text:
        t = "".join(c[0] for c in text)
        if any(x.isdigit() for x in t):
            return "text_digit"
        if t.strip(".,;:!-'") == "":
            return "text_punct"
        return "text_letter"
    if mus:
        best = max(mus, key=lambda c: iou(m, c))
        if iou(m, best) >= 0.4:
            return "music_same_box:" + m["tag"]
        return "music_part_of:" + m["tag"]
    return "no_char"
if __name__ == "__main__":
    for cls in ("false", "true"):
        c = collections.Counter(); ce = collections.Counter()
        for m in rows:
            if m["cls"] != cls: continue
            m["bucket"] = bucket(m)
            eng = m["stem"].rsplit("--", 1)[1]
            c[m["bucket"]] += 1
            ce[(eng, m["bucket"].split(":")[0])] += 1
        print(cls, c.most_common(40))
        print(sorted(ce.items()))
    pickle.dump(rows, open(M / "marksdiag_ink.pkl", "wb"))
