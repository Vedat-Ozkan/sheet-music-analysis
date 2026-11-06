import sys
import xml.etree.ElementTree as ET
sheet, x0, x1, y0, y1 = sys.argv[1], *map(int, sys.argv[2:6])
root = ET.parse(sheet).getroot()
glyphs = {g.get("id"): (int(g.get("left")), int(g.get("top")), int(g.find("run-table").get("width")), int(g.find("run-table").get("height"))) for g in root.iter("glyph") if g.find("run-table") is not None}
used = set()
for el in root.iter():
    g = el.get("glyph")
    if g in glyphs:
        x, y, w, h = glyphs[g]
        if x < x1 and x + w > x0 and y < y1 and y + h > y0:
            used.add(g)
            print("inter", el.tag, el.get("shape"), el.get("grade"), (x, y, w, h))
for gid, (x, y, w, h) in glyphs.items():
    if gid not in used and x < x1 and x + w > x0 and y < y1 and y + h > y0:
        print("free glyph", gid, (x, y, w, h))
