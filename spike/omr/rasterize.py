import sys, pathlib, pypdfium2 as pdfium
pdf = pdfium.PdfDocument(sys.argv[1]); out = pathlib.Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
dpi = int(sys.argv[3]) if len(sys.argv) > 3 else 200
for i, page in enumerate(pdf):
    page.render(scale=dpi / 72).to_pil().convert("RGB").save(out / f"{pathlib.Path(sys.argv[1]).stem}-p{i+1}.png")
