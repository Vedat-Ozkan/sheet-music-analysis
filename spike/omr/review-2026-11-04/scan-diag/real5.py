import json, sys
from pathlib import Path
import pikepdf
OMR = Path("/home/kema/projects/sheet-music-plugin/spike/omr")
def entries():
    for s, want in (("bench-real", None), ("bench", ("mozart-k545-1--real-scan-peters", "chopin-prelude-4--real-scan-schirmer"))):
        m = json.loads((OMR / s / "manifest.json").read_text())
        for e in m["pdfs"]:
            stem = e["pdf"].rsplit("/", 1)[-1][:-4]
            if want is None or stem in want:
                yield stem, OMR / s / e["pdf"], OMR / s / m["pieces"][e["piece"]]["truth"]
zoom = float(sys.argv[1])
out = Path(__file__).parent / "items" / f"real-z{sys.argv[1]}"; out.mkdir(parents=True, exist_ok=True)
items = []
for stem, pdf_path, truth in entries():
    p = out / f"{stem}.pdf"
    if zoom == 1:
        p.write_bytes(pdf_path.read_bytes())
    else:
        pdf = pikepdf.open(pdf_path)
        for page in pdf.pages:
            box = [float(x) for x in page.MediaBox]
            page.contents_coalesce() if hasattr(page, "contents_coalesce") else None
            page.contents_add(pikepdf.Stream(pdf, f"{zoom} 0 0 {zoom} 0 0 cm\n".encode()), prepend=True)
            page.MediaBox = [box[0] * zoom, box[1] * zoom, box[2] * zoom, box[3] * zoom]
            for key in ("/CropBox", "/TrimBox", "/BleedBox", "/ArtBox"):
                if key in page:
                    del page[key]
        pdf.save(p)
    items.append({"name": stem, "pdf": str(p), "truth": str(truth)})
(out / "items.json").write_text(json.dumps(items))
print(out, len(items))
