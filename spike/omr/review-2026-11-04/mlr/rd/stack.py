import re, sys, zipfile, io
import xml.etree.ElementTree as ET
from PIL import Image
omr, idx = sys.argv[1], int(sys.argv[2])
z = zipfile.ZipFile(omr)
sheets = sorted({int(m.group(1)) for n in z.namelist() if (m := re.match(r"sheet#(\d+)/sheet#\d+\.xml", n))})
k = 0
for sn in sheets:
    root = ET.fromstring(z.read(f"sheet#{sn}/sheet#{sn}.xml"))
    il = root.find("scale/interline").get("main")
    for s in root.iter("system"):
        for st in s.findall("stack"):
            if k == idx:
                L, Rr = int(st.get("left")), int(st.get("right"))
                ys = []
                for p in s.findall("part"):
                    for t in p.findall("staff"):
                        lines = [float(l.find("point").get("y")) for l in t.find("lines").findall("line")]
                        ys.append((t.get("id"), lines[0], lines[-1]))
                print("sheet", sn, "sys", s.get("id"), "stack", L, Rr, "il", il, ys)
                img = Image.open(io.BytesIO(z.read(f"sheet#{sn}/BINARY.png"))).convert("L")
                y0 = int(ys[0][1] - 30); y1 = int(ys[-1][2] + 30)
                c = img.crop((L - 10, y0, Rr + 10, y1)); c = c.resize((c.width * 2, c.height * 2)); c.save(sys.argv[3]); print("crop origin", L - 10, y0)
                inters = s.find("sig/inters")
                for e in inters:
                    if e.tag == "rest":
                        b = e.find("bounds")
                        x = int(b.get("x"))
                        if L <= x <= Rr: print("kept", e.get("shape"), x, b.get("y"), b.get("w"), b.get("h"), e.get("grade"), e.get("staff"))
                sys.exit()
            k += 1
