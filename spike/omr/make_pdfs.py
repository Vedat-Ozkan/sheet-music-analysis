import sys, pathlib
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))
from engine.render import engrave
here = pathlib.Path(__file__).parent
for f in sorted((here / "truth").glob("*.mxl")):
    e = engrave(f.read_bytes())
    (here / "pdf" / (f.stem + ".pdf")).write_bytes(e.pdf())
    print(f.stem, len(e.svgs) if hasattr(e, "svgs") else "")
