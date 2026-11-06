import collections, json, sys
sys.path.insert(0, "/home/kema/projects/sheet-music-plugin/spike/omr/speed")
from whole_bars import score_pdf, HERE, OMR
for v in sys.argv[1:]:
    t = collections.Counter()
    for _, st, stem, *_x in json.load(open("rests_set.json")):
        m = json.loads((OMR / st / "manifest.json").read_text())
        piece = next(p["piece"] for p in m["pdfs"] if stem + ".pdf" in p["pdf"])
        score_pdf((OMR / st / m["pieces"][piece]["truth"]).read_bytes(), (HERE / "cache/runs" / v / f"{st}--{stem}.musicxml").read_bytes(), t)
    print(v, t["bars"], t["exact"], round(100 * t["exact"] / t["bars"], 2))
