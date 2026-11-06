import io, json, math, re, zipfile
from imgs import *
omr = list((HOME / "books/real-z1/mozart-k545-1--real-scan-peters").glob("*.omr"))[0]
z = zipfile.ZipFile(omr)
truth = str(OMR / "bench/truth" / sorted(p.name for p in (OMR / "bench/truth").iterdir() if p.name.startswith("mozart-k545-1"))[0])
out = {"control": [], "rotated": []}
for k in range(1, 5):
    slope = float(re.search(r'<skew slope="([^"]+)"', z.read(f"sheet#{k}/sheet#{k}.xml")[:300000].decode("utf8", "replace")).group(1))
    im = Image.open(io.BytesIO(z.read(f"sheet#{k}/BINARY.png"))).convert("L")
    out["control"].append(im); out["rotated"].append(im.rotate(math.degrees(math.atan(slope)), Image.BICUBIC, fillcolor=255))
    print(k, slope, im.size)
for lab, ims in out.items():
    d = HOME / f"items/moz-{lab}"; d.mkdir(parents=True, exist_ok=True)
    pdf = pikepdf.Pdf.new()
    for i, im in enumerate(ims):
        t = d / "tmp.pdf"; to_pdf(im, t); pdf.pages.extend(pikepdf.open(t).pages)
    pdf.save(d / "mozart.pdf"); (d / "tmp.pdf").unlink()
    (d / "items.json").write_text(json.dumps([{"name": "mozart", "pdf": str(d / "mozart.pdf"), "truth": truth}]))
print(truth)
