import hashlib, json, random, re, sys, zlib, collections
from pathlib import Path
import pikepdf
from PIL import Image
from lxml import etree
D = Path(sys.argv[1])
B = Path("/home/kema/projects/sheet-music-plugin/spike/omr/bench-olimpic")
man = json.loads((B / "manifest.json").read_text())
ids = [l.strip() for l in (D / "samples.test.txt").read_text().splitlines() if l.strip()]
ids.sort(key=lambda s: hashlib.sha256(s.encode()).hexdigest())
per = collections.Counter(); taken = []
for s in ids:
    w = s.split("/")[1]
    if per[w] >= 3: continue
    per[w] += 1; taken.append(s)
    if len(taken) == 80: break
old = {re.sub(r"^olimpic-", "", k) for k in man["pieces"]}
assert {s.split("/")[1] + "-" + s.split("/")[2] for s in taken[:40]} == old, "first 40 do not reproduce"
def mdur(m):
    pos = mx = 0
    for e in m:
        if e.tag == "note":
            if e.find("chord") is None: pos += int(e.findtext("duration") or 0)
        elif e.tag == "backup": pos -= int(e.findtext("duration"))
        elif e.tag == "forward": pos += int(e.findtext("duration"))
        mx = max(mx, pos)
    return mx
inferred = 0
for s in taken[40:]:
    _, w, sid = s.split("/")
    name = f"olimpic-{w}-{sid}"
    root = etree.parse(str(D / (s + ".musicxml"))).getroot()
    ms = root.findall(".//measure")
    div = int(root.findtext(".//divisions"))
    attrs = ms[0].find("attributes")
    if attrs.find("time") is None:
        q = max(mdur(m) for m in ms) / div
        bt = (int(q), 4) if q == int(q) else (int(q * 2), 8)
        t = etree.Element("time"); etree.SubElement(t, "beats").text = str(bt[0]); etree.SubElement(t, "beat-type").text = str(bt[1])
        attrs.find("staves").addprevious(t); inferred += 1
    out = B / "truth" / f"{name}.musicxml"
    etree.ElementTree(root).write(str(out), xml_declaration=True, encoding="utf-8")
    nn = sum(1 for n in root.iter("note") if n.find("rest") is None)
    im = Image.open(D / (s + ".png")).convert("L"); W, H = im.size
    pdf = pikepdf.Pdf.new()
    xo = pikepdf.Stream(pdf, b""); xo.Type = pikepdf.Name.XObject; xo.Subtype = pikepdf.Name.Image
    xo.Width = W; xo.Height = H; xo.ColorSpace = pikepdf.Name.DeviceGray; xo.BitsPerComponent = 8
    xo.write(zlib.compress(im.tobytes()), filter=pikepdf.Name.FlateDecode)
    pw, ph = W * 72 / 300, H * 72 / 300
    page = pdf.add_blank_page(page_size=(pw, ph))
    page.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Im0=xo))
    page.Contents = pdf.make_stream(f"q {pw} 0 0 {ph} 0 0 cm /Im0 Do Q".encode())
    pdf.save(B / "pdfs" / f"{name}--scan.pdf")
    man["pieces"][name] = {"kind": "keyboard", "truth": f"truth/{name}.musicxml", "source": f"OLiMPiC 1.0 Scanned test {s} (CC BY-SA; OpenScore Lieder work {w})", "bars": len(ms), "notes": nn}
    man["pdfs"].append({"pdf": f"pdfs/{name}--scan.pdf", "piece": name, "engraver": "scan", "pages": 1})
(B / "manifest.json").write_text(json.dumps(man, indent=1))
works = sorted({p.split("-")[1] for p in man["pieces"]})
rng = random.Random(20261104)
rng.shuffle(works)
target = len(man["pieces"]) / 2
inspect, count = [], 0
per_work = collections.Counter(p.split("-")[1] for p in man["pieces"])
for w in works:
    if count >= target: break
    inspect.append(w); count += per_work[w]
split = {"method": "random shuffle of works, random.Random(20261104), sorted works; inspect takes works until half the samples; a work is never in both halves",
         "made_before_bar_level_inspection": True,
         "inspect": sorted(p for p in man["pieces"] if p.split("-")[1] in inspect),
         "unseen": sorted(p for p in man["pieces"] if p.split("-")[1] not in inspect)}
(B / "split.json").write_text(json.dumps(split, indent=1))
print(len(man["pieces"]), len(split["inspect"]), len(split["unseen"]), "inferred new", inferred, "bars", sum(p["bars"] for p in man["pieces"].values()))
