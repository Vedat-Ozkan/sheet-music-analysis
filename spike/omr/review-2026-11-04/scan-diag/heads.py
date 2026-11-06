import sys, json, warnings, collections, re, zipfile
warnings.filterwarnings("ignore")
sys.path[:0] = ["/home/kema/projects/sheet-music-plugin/spike/omr/speed"]
from whole_bars import parse, pitches
from pathlib import Path
import xml.etree.ElementTree as ET
for tag in ("native-inspect", "real-z1"):
    items = json.loads(Path(f"items/{tag}/items.json").read_text())
    T = collections.Counter(); rows = []
    for it in items:
        omr = list(Path("books", tag, it["name"]).glob("*.omr"))
        heads = chords = 0
        grace = small = 0
        if omr:
            z = zipfile.ZipFile(omr[0])
            for n in z.namelist():
                if re.search(r"sheet#\d+\.xml$", n):
                    s = z.read(n).decode("utf8", "replace")
                    heads += len(re.findall(r"<head [^>]*shape=", s))
                    grace += len(re.findall(r'<head [^>]*shape="NOTEHEAD_BLACK_SMALL', s)) + len(re.findall(r'<grace', s))
        tb = parse(Path(it["truth"]).read_bytes())
        tn = sum(sum(pitches(b).values()) for b in tb) + sum(b.grace for b in tb)
        r = Path("runs", tag, it["name"] + ".musicxml")
        rn = 0
        if r.exists():
            ob = parse(r.read_bytes()); rn = sum(sum(pitches(b).values()) for b in ob) + sum(b.grace for b in ob)
        if not omr or not r.exists(): continue
        T["truth"] += tn; T["heads"] += heads; T["read"] += rn; T["n"] += 1
        T["under"] += max(0, tn - heads); T["over"] += max(0, heads - tn); T["lost_export"] += max(0, heads - rn)
        rows.append((it["name"][8:30], tn, heads, rn))
    print(tag, dict(T)); print(sorted(rows, key=lambda x: x[2] - x[1])[:6])
