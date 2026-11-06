import glob, re, sys
import xml.etree.ElementTree as ET
LINE = re.compile(r"SMADIAG sheet (\d+) glyph (\d+) bounds java.awt.Rectangle\[x=(\d+),y=(\d+),width=(\d+),height=(\d+)\] raw \[(.*?)\] checked")
for d in sys.argv[1:]:
    kept = {}
    for f in glob.glob(d + "/book/sheet#*/sheet#*.xml"):
        n = int(re.search(r"sheet#(\d+)\.xml", f).group(1))
        root = ET.parse(f).getroot()
        inter = int(root.find(".//interline").get("main"))
        glyphs = {g.get("id"): (int(g.get("left")), int(g.get("top")), int(g.find("run-table").get("width")), int(g.find("run-table").get("height"))) for g in root.iter("glyph") if g.find("run-table") is not None}
        kept[n] = ([glyphs.get(c.get("glyph")) for c in root.iter("clef") if c.get("glyph") in glyphs], inter)
    seen = {}
    for line in open(d + "/run.txt", errors="replace"):
        m = LINE.search(line)
        if not m:
            continue
        sheet, gid, x, y, w, h = map(int, m.groups()[:6])
        evals = re.findall(r"([A-Z_0-9]+)\(([\d.]+)\)", m.group(7))
        clef = {s: float(g) for s, g in evals if "CLEF" in s}
        key = (sheet, x // 10, y // 10)
        best = max(clef.values())
        if key not in seen or best > seen[key][0]:
            seen[key] = (best, clef, (x, y, w, h))
    print("==", d.split("/")[-1])
    for (sheet, _, _), (best, clef, (x, y, w, h)) in sorted(seen.items()):
        boxes, inter = kept.get(sheet, ([], 21))
        hit = any(b and b[0] < x + w and b[0] + b[2] > x and b[1] < y + h and b[1] + b[3] > y for b in boxes)
        total = {}
        for s, g in clef.items():
            base = s.replace("_SMALL", "")
            total[base] = total.get(base, 0) + g
        if best >= 0.2 and not hit:
            print(f"  MISSED sheet {sheet} at {x},{y} h={h / inter:.1f} {clef}  summed {max(total.values()):.2f}")
