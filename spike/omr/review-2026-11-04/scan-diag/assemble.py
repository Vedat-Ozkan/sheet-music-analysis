import copy, json, random, re
from imgs import *
split = json.loads((BO / "split.json").read_text())
works = sorted({sid(n)[0] for n in split["inspect"]})
random.Random(7).shuffle(works)
works = works[:12]
PAGES = 2
pdir = HOME / "items/pages"; pdir.mkdir(parents=True, exist_ok=True)
sdir = HOME / "items/singles21"; sdir.mkdir(parents=True, exist_ok=True)
tdir = HOME / "items/pagetruth"; tdir.mkdir(parents=True, exist_ok=True)
pitems, sitems, nitems, info = [], [], [], {}
for w in works:
    files = sorted((DS / w).glob("p*-s*.png"), key=lambda f: tuple(map(int, re.findall(r"\d+", f.stem))))
    pages = {}
    for f in files:
        pages.setdefault(int(f.stem[1:].split("-")[0]), []).append(f)
    numbers = sorted(pages)[:PAGES]
    use = [f for k in numbers for f in pages[k]]
    tree = None; part = None
    for f in use:
        root = etree.parse(str(f.with_suffix(".musicxml"))).getroot()
        if tree is None:
            tree = root; part = root.find(".//part")
        else:
            for m in root.find(".//part").findall("measure"):
                part.append(copy.deepcopy(m))
        name = f"olimpic-{w}-{f.stem}"
        truth = tdir / f"single-{name}.musicxml"
        etree.ElementTree(root if root is not tree else copy.deepcopy(root)).write(str(truth), xml_declaration=True, encoding="utf-8")
    first = etree.parse(str(use[0].with_suffix(".musicxml"))).getroot()
    wtruth = tdir / f"{w}.musicxml"
    etree.ElementTree(tree).write(str(wtruth), xml_declaration=True, encoding="utf-8")
    ims = []
    for k in numbers:
        crops = [Image.open(f).convert("L") for f in pages[k]]
        ims.append(crops)
    il = interline(np.asarray(ims[0][0]))
    dpi = 300 * il / 21
    pdf = pikepdf.Pdf.new()
    for crops in ims:
        W = max(c.width for c in crops); gap = int(1.5 * il)
        canvas = Image.new("L", (W, sum(c.height + gap for c in crops)), 255)
        y = 0
        for c in crops:
            canvas.paste(c, (0, y)); y += c.height + gap
        tmp = pdir / "tmp.pdf"; to_pdf(canvas, tmp, dpi)
        pdf.pages.extend(pikepdf.open(tmp).pages)
    path = pdir / f"{w}.pdf"; pdf.save(path); 
    (pdir / "tmp.pdf").unlink()
    pitems.append({"name": w, "pdf": str(path), "truth": str(wtruth)})
    for f in use:
        name = f"olimpic-{w}-{f.stem}"; im = Image.open(f).convert("L")
        sp = sdir / f"{name}.pdf"; to_pdf(im, sp, 300 * interline(np.asarray(im)) / 21)
        sitems.append({"name": name, "pdf": str(sp), "truth": str(tdir / f"single-{name}.musicxml"), "work": w})
    info[w] = {"il": il, "systems": len(use), "pages": numbers, "time": bool(first.find(".//time") is not None)}
(pdir / "items.json").write_text(json.dumps(pitems)); (sdir / "items.json").write_text(json.dumps(sitems)); (pdir / "info.json").write_text(json.dumps(info, indent=0))
print(works, sum(i["systems"] for i in info.values()), info)
