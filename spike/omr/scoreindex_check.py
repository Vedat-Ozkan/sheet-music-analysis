"""Can the engine read this MusicXML? usage: scoreindex_check.py file(.mxl|.musicxml) ... (run with the repo .venv)"""
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))
from engine.render import load_toolkit
from engine.score import ScoreIndex
for f in sys.argv[1:]:
    try:
        tk = load_toolkit(open(f, "rb").read()); ix = ScoreIndex(tk.getMEI())
        print(f, "OK", len(ix.measures), "measures", ix.meter, ix.key_signature, "pages", tk.getPageCount())
    except Exception as e:
        print(f, "FAIL", type(e).__name__, str(e)[:150])
