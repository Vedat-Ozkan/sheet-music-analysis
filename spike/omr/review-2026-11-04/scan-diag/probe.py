import collections, json, os, sys, threading, time, warnings
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
warnings.filterwarnings("ignore")
ROOT = Path("/home/kema/projects/sheet-music-plugin")
SPEED = ROOT / "spike/omr/speed"
sys.path[:0] = [str(SPEED), str(ROOT), str(ROOT / "spike/omr/bench")]
LISTING = Path(sys.argv[2]).resolve()
os.chdir(SPEED)
import run as bench
import variants
from whole_bars import score_pdf
from barparse import parse, pitches
from engine import read_pdf as reader
HOME = Path(__file__).resolve().parent
AUD = str(variants.launcher("marks1"))
slots = threading.Semaphore(int(os.environ.get("JOBS", "4")))

def raw(store):
    def inner(data, audiveris, setting, leland, deadline, stop):
        key = f"s{setting}"
        meta, mxl = store.with_suffix(f".{key}.json"), store.with_suffix(f".{key}.mxl")
        if not meta.exists():
            with slots:
                if stop.is_set():
                    return reader.RawReading(None, [], {"outcome": "cancelled"})
                got = reader.audiveris_read(data, AUD, setting, leland, time.monotonic() + reader.TIMEOUT, threading.Event())
            if got.facts["outcome"] == "cancelled":
                return reader.RawReading(None, [], got.facts)
            if got.mxl is not None:
                mxl.write_bytes(got.mxl)
            meta.write_text(json.dumps({"skipped": got.skipped, "facts": got.facts, "ok": got.mxl is not None}))
        m = json.loads(meta.read_text())
        return reader.RawReading(mxl.read_bytes() if m["ok"] else None, m["skipped"], m["facts"])
    return inner

def one(tag, item):
    run = HOME / "runs" / tag
    run.mkdir(parents=True, exist_ok=True)
    out = run / f"{item['name']}.musicxml"
    store = run / item["name"]
    tdata = Path(item["truth"]).read_bytes()
    row = collections.Counter()
    facts = {}
    try:
        r = reader.read_pdf(Path(item["pdf"]).read_bytes(), AUD, raw=bench.production_raw(raw(store)))
        out.write_bytes(r.musicxml)
        score_pdf(tdata, r.musicxml, row)
    except Exception as e:
        bars = parse(tdata)
        row.update(pdfs=1, failed=1, bars=len(bars), wrong=len(bars), notes=sum(sum(pitches(b).values()) for b in bars))
        facts["error"] = f"{type(e).__name__}: {e}"[:200]
    meta = store.with_suffix(".s0.json")
    if meta.exists():
        m = json.loads(meta.read_text())["facts"]
        facts.update(interlines=m.get("interlines"), images=m.get("images"), problems=m.get("problems"), outcome=m.get("outcome"))
    return {"name": item["name"], **row}, facts

def main():
    tag, listing = sys.argv[1], json.loads(LISTING.read_text())
    with ThreadPoolExecutor(8) as pool:
        done = list(pool.map(lambda i: one(tag, i), listing))
    rows = {r["name"]: {**r, "facts": f} for r, f in done}
    (HOME / "results" / f"{tag}.json").write_text(json.dumps(rows, indent=0))
    t = collections.Counter()
    for r, _ in done:
        t.update({k: v for k, v in r.items() if k != "name"})
    b, n = t["bars"] or 1, t["notes"] or 1
    print(f"{tag}: pdfs {t['pdfs']} bars {t['bars']} exact {100*t['exact']/b:.1f} pooled {100*t['exact_pooled']/b:.1f} pt {100*t['pitch_timing_bars']/b:.1f} pitch {100*t['pitch_notes']/n:.1f} timing {100*t['timed_notes']/n:.1f} failed {t['failed']} wrongbarcount {t['wrong_bar_count']}")
main()
