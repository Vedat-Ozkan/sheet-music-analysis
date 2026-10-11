"""Raster-pad every page of a PDF with white to the first page's size and save as one PDF: pad_pages.py in.pdf out.pdf [dpi]"""
import sys, pypdfium2 as pdfium
from PIL import Image
dpi = int(sys.argv[3]) if len(sys.argv) > 3 else 300
pages = [p.render(scale=dpi / 72).to_pil().convert("RGB") for p in pdfium.PdfDocument(sys.argv[1])]
W, H = max(p.width for p in pages), max(p.height for p in pages)
out = []
for p in pages:
    c = Image.new("RGB", (W, H), "white"); c.paste(p, (0, 0)); out.append(c)
out[0].save(sys.argv[2], save_all=True, append_images=out[1:], resolution=dpi)
