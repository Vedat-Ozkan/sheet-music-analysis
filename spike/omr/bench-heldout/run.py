"""Run Audiveris (as production does, engine.read_pdf.read_pdf) on every benchmark PDF and score the result.

usage: run.py [--out results-baseline.json] [--jobs 3] [--only SUBSTRING ...] [--tag TEXT] [--audiveris PATH]
Audiveris results are cached in cache/ by sha256 of the PDF plus a signature of the Audiveris install (file names,
sizes, mtimes), so a retrained classifier inside the install invalidates the cache by itself. --tag adds to the key.
"""
import argparse, collections, hashlib, json, os, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
DEFAULT_AUDIVERIS = ROOT / "spike/omr/tools/audiveris-deb/x/opt/audiveris/bin/Audiveris"
PY = ROOT / ".venv/bin/python"
KINDS = ("tuplet_notes", "ornaments", "grace", "octave_lines", "clef_changes")


def install_signature(binary: Path) -> str:
    h = hashlib.sha256()
    for dirpath, _, files in sorted(os.walk(binary.parent.parent)):
        for f in sorted(files):
            s = os.stat(os.path.join(dirpath, f))
            h.update(f"{dirpath}/{f}:{s.st_size}:{int(s.st_mtime)}".encode())
    return h.hexdigest()[:16]


def read(pdf: Path, key: str, audiveris: str) -> dict:
    cache = HERE / "cache"
    cache.mkdir(exist_ok=True)
    meta = cache / f"{key}.json"
    if meta.exists():
        return {**json.loads(meta.read_text()), "cached": True}
    from engine.read_pdf import ReadError, read_pdf
    t0 = time.time()
    out = {"cached": False}
    try:
        r = read_pdf(pdf.read_bytes(), audiveris)
        (cache / f"{key}.musicxml").write_bytes(r.musicxml)
        out.update(ok=True, pages=r.pages, skipped=r.skipped, scan=r.scan)
    except ReadError as e:
        out.update(ok=False, error=str(e))
    except Exception as e:  # noqa: BLE001
        out.update(ok=False, error=f"{type(e).__name__}: {e}")
    out["seconds"] = round(time.time() - t0, 1)
    meta.write_text(json.dumps(out))
    return out


def score(truth: Path, key: str) -> dict:
    omr = HERE / "cache" / f"{key}.musicxml"
    if not omr.exists():
        omr = "-"
    p = subprocess.run([str(PY), "-I", str(HERE / "score_one.py"), str(truth), str(omr)], capture_output=True, text=True, timeout=600)
    if p.returncode != 0:
        return {"score_error": f"scoring exit {p.returncode}: {p.stderr.strip()[-200:]}"}
    return json.loads(p.stdout.strip().splitlines()[-1])


def summarise(rows: list[dict]) -> dict:
    """Totals over the given piece rows (sums of counts first, ratios after, so big pieces weigh more)."""
    t = collections.Counter()
    for r in rows:
        t["pdfs"] += 1
        t["pages"] += r["pages"]
        t["crashed"] += r["crashed"]
        t["pages_skipped"] += len(r["pages_skipped"])
        t["seconds"] += r["seconds"]
        t["truth_notes"] += r["truth_notes"]
        s = r.get("score") or {}
        for k in ("omr_notes", "shared_pitch", "shared_pitch_onset", "uneven_bars_omr", "uneven_bars_truth", "truth_bars", "omr_bars"):
            t[k] += s.get(k, 0)
        for k, v in (s.get("kinds") or {}).items():
            for f in ("truth", "found", "invented"):
                t[f"{k}_{f}"] += v[f]
        t["score_errors"] += 1 if "score_error" in s else 0
    n = t["truth_notes"] or 1
    out = {"pdfs": t["pdfs"], "pages": t["pages"], "crashed": t["crashed"], "pages_skipped": t["pages_skipped"],
           "score_errors": t["score_errors"], "seconds_per_page": round(t["seconds"] / max(t["pages"], 1), 1),
           "truth_notes": t["truth_notes"], "omr_notes": t["omr_notes"],
           "pitch": round(t["shared_pitch"] / n, 4), "pitch_onset": round(t["shared_pitch_onset"] / n, 4),
           "bar_duration_errors": t["uneven_bars_omr"], "bar_duration_errors_in_truth": t["uneven_bars_truth"],
           "truth_bars": t["truth_bars"]}
    for k in KINDS:
        out[k] = {f: t[f"{k}_{f}"] for f in ("truth", "found", "invented")}
        out[k]["missed"] = out[k]["truth"] - out[k]["found"]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "results-baseline.json"))
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--only", nargs="*", default=[])
    ap.add_argument("--tag", default="")
    ap.add_argument("--audiveris", default=str(DEFAULT_AUDIVERIS))
    a = ap.parse_args()
    jobs = min(a.jobs, 3)  # each Audiveris takes ~1.3 GB (-Xmx1g); more than 3 was ruled out
    manifest = json.loads((HERE / "manifest.json").read_text())
    pdfs = [p for p in manifest["pdfs"] if not a.only or any(s in p["pdf"] for s in a.only)]
    sig = install_signature(Path(a.audiveris)) + a.tag
    keys = {p["pdf"]: hashlib.sha256((HERE / p["pdf"]).read_bytes() + sig.encode()).hexdigest()[:32] for p in pdfs}
    t0 = time.time()
    with ThreadPoolExecutor(jobs) as ex:
        reads = dict(zip((p["pdf"] for p in pdfs), ex.map(lambda p: read(HERE / p["pdf"], keys[p["pdf"]], a.audiveris), pdfs)))
    rows = []
    for p in pdfs:
        r = reads[p["pdf"]]
        truth = HERE / manifest["pieces"][p["piece"]]["truth"]
        row = {"pdf": p["pdf"], "piece": p["piece"], "engraver": p["engraver"], "pages": p["pages"],
               "crashed": not r["ok"], "error": r.get("error"), "pages_skipped": r.get("skipped", []),
               "seconds": r["seconds"], "seconds_per_page": round(r["seconds"] / p["pages"], 1), "cached": r.get("cached", True),
               "truth_notes": 0}
        s = row["score"] = score(truth, keys[p["pdf"]])
        row["truth_notes"] = s.get("truth_notes", 0)
        if "shared_pitch" in s:
            row["pitch"] = round(s["shared_pitch"] / s["truth_notes"], 4)
            row["pitch_onset"] = round(s["shared_pitch_onset"] / s["truth_notes"], 4)
        rows.append(row)
    by_eng = {e: summarise([r for r in rows if r["engraver"] == e]) for e in sorted({r["engraver"] for r in rows})}
    result = {"audiveris_install": sig, "wall_seconds_this_run": round(time.time() - t0, 1), "jobs": jobs,
              "totals": summarise(rows), "by_engraver": by_eng, "pdfs": rows, "not_built": manifest.get("not_built", [])}
    Path(a.out).write_text(json.dumps(result, indent=1))
    print(json.dumps(result["totals"], indent=1))


if __name__ == "__main__":
    main()
