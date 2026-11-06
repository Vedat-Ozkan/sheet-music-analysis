import collections, glob, json, pickle, re, sys, warnings, zipfile
from pathlib import Path
warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/kema/projects/sheet-music-plugin/spike/omr/speed")
import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw
from barparse import parse, pitches, align_bars, root_of

S = Path("/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad")
HERE = Path("/home/kema/projects/sheet-music-plugin/spike/omr/speed")

def choose_setting(setname, stem, root=None, variant="pitch51"):
    root = root or S / "mlr/tb"
    run = parse((HERE / "cache/runs" / variant / f"{setname}--{stem}.musicxml").read_bytes())
    best, bestv = None, -1
    for s in ("s0", "s1"):
        ms = sorted((root / stem / s).glob("*.mxl"))
        if not ms:
            continue
        ob = parse(ms[0].read_bytes())
        v = sum(sum((pitches(a) & pitches(b)).values()) for a, b in zip(run, ob)) - abs(len(run) - len(ob)) * 100
        if v > bestv:
            best, bestv = s, v
    return best

def load_book(d):
    omr = sorted(Path(d).glob("*.omr"))[0]
    z = zipfile.ZipFile(omr)
    sheets = sorted({int(m.group(1)) for n in z.namelist() if (m := re.match(r"sheet#(\d+)/sheet#\d+\.xml", n))})
    stacks = []
    for sn in sheets:
        root = ET.fromstring(z.read(f"sheet#{sn}/sheet#{sn}.xml"))
        il = int(root.find("scale/interline").get("main"))
        for si, sy in enumerate(root.iter("system")):
            sig = sy.find("sig")
            ys = [float(p.get("y")) for st in sy.iter("staff") if st.find("lines") is not None for l in st.find("lines").findall("line") for p in l.findall("point")]
            inters = {}
            for el in sig.find("inters"):
                b = el.find("bounds")
                inters[el.get("id")] = dict(tag=el.tag, attr=el.attrib, box=(int(b.get("x")), int(b.get("y")), int(b.get("w")), int(b.get("h"))) if b is not None else None, el=el)
            rels = []
            for r in sig.find("relations"):
                kid = list(r)[0]
                rels.append((r.get("source"), r.get("target"), kid.tag, kid.attrib))
            info = dict(sheet=sn, sys=si, top=min(ys), bottom=max(ys), il=il, inters=inters, rels=rels)
            parts = [p for p in sy.findall("part")]
            for pos, st_ in enumerate(sy.findall("stack")):
                if st_.get("special") == "CAUTIONARY":
                    continue
                ms = []
                for p in parts:
                    pm = p.findall("measure")
                    if pos < len(pm):
                        ms.append(pm[pos])
                stacks.append(dict(info, left=int(st_.get("left")), right=int(st_.get("right")), stack=st_, measures=ms))
    return z, stacks

def crop(z, stacks, indices, out, overlay=True, labels=()):
    a = stacks[indices[0]]
    same = [stacks[k] for k in indices if stacks[k]["sheet"] == a["sheet"] and stacks[k]["sys"] == a["sys"]]
    left = min(s["left"] for s in same) - 60
    right = max(s["right"] for s in same) + 60
    top, bottom = a["top"] - 2 * a["il"] - 40, a["bottom"] + 2 * a["il"] + 40
    from io import BytesIO
    img = Image.open(BytesIO(z.read(f"sheet#{a['sheet']}/BINARY.png"))).convert("RGB")
    c = img.crop((max(0, left), max(0, int(top)), min(img.size[0], right), min(img.size[1], int(bottom))))
    ox, oy = max(0, left), max(0, int(top))
    panes = [c]
    if overlay:
        o = c.copy()
        d = ImageDraw.Draw(o)
        for id_, i in a["inters"].items():
            if i["tag"] == "slur" and i["box"]:
                x, y, w, h = i["box"]
                col = (0, 170, 0) if i["attr"].get("tie") == "true" else (0, 80, 255)
                d.rectangle((x - ox, y - oy, x + w - ox, y + h - oy), outline=col, width=2)
        panes.append(o)
    W = max(p.size[0] for p in panes)
    H = sum(p.size[1] for p in panes) + 6
    m = Image.new("RGB", (W, H), "white")
    y = 0
    for p in panes:
        m.paste(p, (0, y))
        y += p.size[1] + 6
    if max(m.size) > 1500:
        f = 1500 / max(m.size)
        m = m.resize((int(m.size[0] * f), int(m.size[1] * f)))
    m.save(out)
