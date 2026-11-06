import collections, glob, sys
import xml.etree.ElementTree as ET
heights = collections.defaultdict(list)
for f in sorted(glob.glob(sys.argv[1] + "/sheet#*/sheet#*.xml")):
    root = ET.parse(f).getroot()
    inter = int(root.find(".//interline").get("main"))
    glyphs = {g.get("id"): (int(g.get("left")), int(g.get("top")), int(g.find("run-table").get("width")), int(g.find("run-table").get("height")))
              for g in root.iter("glyph") if g.find("run-table") is not None}
    heads = {h.get("id"): h.get("shape") for h in root.iter("head")}
    links = collections.defaultdict(list)
    for rel in root.iter("relation"):
        if rel.find("alter-head") is not None:
            links[rel.get("source")].append(heads.get(rel.get("target")))
    for a in root.iter("alter"):
        g = glyphs.get(a.get("glyph"))
        if g:
            heights[a.get("shape")].append((round(g[3] / inter, 2), f.split("/")[-1], a.get("id"), links.get(a.get("id"))))
for s, h in sorted(heights.items()):
    h.sort()
    print(s, len(h))
    for row in h[:6]: print("   ", row)
    print("    ...", [r[0] for r in h[len(h)//2:len(h)//2+3]], "max", h[-1][0])
