import io, sys, zlib
import numpy as np
import pypdfium2 as pdfium
from PIL import Image, ImageFilter

src, dst, seed = sys.argv[1], sys.argv[2], int(sys.argv[3])
rng = np.random.default_rng(seed)
pages = []
for page in pdfium.PdfDocument(src):
    img = page.render(scale=300 / 72).to_pil().convert("L")
    angle = float(rng.uniform(-0.8, 0.8))
    img = img.rotate(angle, resample=Image.BICUBIC, expand=False, fillcolor=255)
    img = img.filter(ImageFilter.GaussianBlur(0.8))
    a = np.asarray(img, dtype=np.float32)
    a = 40 + a * (215 / 255)
    a = a * (1 - 0.10 * np.linspace(0, 1, a.shape[1])[None, :] * rng.uniform(0.3, 1))
    a += rng.normal(0, 7, a.shape)
    img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=70)
    pages.append(Image.open(io.BytesIO(buf.getvalue())).convert("L"))
pages[0].save(dst, "PDF", resolution=300, save_all=True, append_images=pages[1:])
