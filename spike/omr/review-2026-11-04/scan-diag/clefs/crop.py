import sys, zipfile, io
from pathlib import Path
from PIL import Image, ImageDraw
R = Path("/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad/clefs")
def page(run, name, sheet):
    z = zipfile.ZipFile(next((R / "runs" / run / name).glob("*.omr")))
    return Image.open(io.BytesIO(z.read(f"sheet#{sheet}/BINARY.png"))).convert("L")
out, width = sys.argv[1], int(sys.argv[2])
pieces = []
for spec in sys.argv[3:]:
    run, name, sheet, x0, y0, x1, y1 = spec.split(":")
    c = page(run, name, int(sheet)).crop((int(x0), int(y0), int(x1), int(y1))).point(lambda v: v)
    r = min(1.0 * width / c.width, 3.0)
    pieces.append(c.resize((int(c.width * r), int(c.height * r))))
W = max(p.width for p in pieces); H = sum(p.height + 8 for p in pieces)
im = Image.new("L", (W, H), 180); y = 0
for p in pieces:
    im.paste(p, (0, y)); y += p.height + 8
im.save(R / "crops" / out)
print(im.size)
