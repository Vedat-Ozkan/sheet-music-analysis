import sys
from pathlib import Path

import pypdfium2

pdf, folder, width = sys.argv[1], Path(sys.argv[2]), int(sys.argv[3])
for number, page in enumerate(pypdfium2.PdfDocument(pdf), start=1):
    page.render(scale=width / page.get_width()).to_pil().convert("RGB").save(folder / f"page-{number}.png")
