import copy, json, pathlib, subprocess, sys, xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
OMR = pathlib.Path("/home/kema/projects/sheet-music-plugin/spike/omr")
S = pathlib.Path(__file__).parent
dpi, tag = int(sys.argv[1]), sys.argv[2]
sets = {"bench-real": None, "bench": "real-scan"}
if len(sys.argv) > 3 and sys.argv[3] == "olimpic":
    split = json.loads((OMR / "bench-olimpic/split.json").read_text())
    sets = {"bench-olimpic": "inspect"}
items = []
for name, flt in sets.items():
    m = json.loads((OMR / name / "manifest.json").read_text())
    for p in m["pdfs"]:
        if flt == "real-scan" and "real-scan" not in p["pdf"]:
            continue
        if flt == "inspect" and p["piece"] not in {x for k, v in split.items() if "unseen" not in k and isinstance(v, list) for x in v}:
            continue
        items.append((name, OMR / name / p["pdf"]))
runs = OMR / "speed/cache/runs" / tag
runs.mkdir(parents=True, exist_ok=True)
work = S / f"work-{tag}"
def one(it):
    name, pdf = it
    d = work / name / pdf.stem
    out = runs / f"{name}--{pdf.stem}.musicxml"
    if out.exists():
        return
    d.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(OMR / "homr-venv/bin/python"), str(OMR / "rasterize.py"), str(pdf), str(d), str(dpi)], check=True)
    trees = []
    for png in sorted(d.glob("*.png"), key=lambda p: int(p.stem.rsplit("-p", 1)[1])):
        xml = png.with_suffix(".musicxml")
        if not xml.exists():
            r = subprocess.run([str(OMR / "homr-venv/bin/python"), str(S / "homr_safe.py"), str(png)], capture_output=True, text=True, env={"OMP_NUM_THREADS": "4", "PATH": "/usr/bin:/bin", "HOME": str(pathlib.Path.home())})
            if not xml.exists():
                print("FAILED", png, r.stderr[-300:], flush=True)
                continue
        trees.append(ET.parse(xml))
    if not trees:
        return
    base = trees[0].getroot()
    n = 0
    parts = base.findall("part")
    for t in trees[1:]:
        for a, b in zip(parts, t.getroot().findall("part")):
            for ms in b.findall("measure"):
                a.append(copy.deepcopy(ms))
    for p in parts:
        for i, ms in enumerate(p.findall("measure"), 1):
            ms.set("number", str(i))
    trees[0].write(out, encoding="utf-8", xml_declaration=True)
    print("ok", out.name, len(parts), len(parts[0].findall("measure")), flush=True)
with ThreadPoolExecutor(int(sys.argv[4]) if len(sys.argv) > 4 else 3) as ex:
    list(ex.map(one, items))
