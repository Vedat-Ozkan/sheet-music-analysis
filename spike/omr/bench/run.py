"""Read every benchmark PDF as production does (engine.read_pdf.read_pdf) and score the result.

usage: run.py [--set bench bench-heldout ...] [--out results-baseline.json] [--jobs 6] [--only SUBSTRING ...]
              [--tag TEXT] [--audiveris PATH]
Only Audiveris's own output is cached (<set>/cache/raw/), per PDF and per settings, keyed by sha256 of the PDF, the
settings and a signature of the Audiveris install (file names, sizes, mtimes), so a rebuilt install invalidates the
cache by itself; --tag adds to the key. Everything after Audiveris (cleaning, choosing a reading, triplets) runs from
the current engine code on every run, so changing it costs seconds, not a re-read. --set names benchmark folders next
to this one (same manifest format); all their PDFs share one pool, and each set's results go to <set>/<out>.
--jobs caps Audiveris processes running at once (each takes up to ~1.7 GB, log 35), not PDFs.
"""
import argparse, collections, hashlib, json, os, subprocess, sys, threading, time
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


def cached_raw(cache: Path, sig: str, slots: threading.Semaphore, calls: list):
    """A stand-in for engine.read_pdf.audiveris_read that keeps each Audiveris output in `cache`. Each run gets the full
    TIMEOUT from when it starts, not from when its PDF did: runs wait here for a slot, which production never does.
    Appends (settings index, Audiveris seconds, cached) to `calls`."""
    from engine import read_pdf as reader

    def raw(data, audiveris, options, deadline):
        key = hashlib.sha256(data + sig.encode() + " ".join(options).encode()).hexdigest()[:32]
        meta, mxl = cache / f"{key}.json", cache / f"{key}.mxl"
        index = reader.SETTINGS.index(options)
        if not meta.exists():
            with slots:
                t0 = time.monotonic()
                try:
                    got = reader.audiveris_read(data, audiveris, options, time.monotonic() + reader.TIMEOUT)
                    out = {"timeout": True} if got is None else {"skipped": got[1]}
                    if got:
                        mxl.write_bytes(got[0])
                except reader.ReadError as e:
                    out = {"error": str(e)}
                out["seconds"] = round(time.monotonic() - t0, 1)
                meta.write_text(json.dumps(out))
            calls.append((index, out["seconds"], False))
        else:
            out = json.loads(meta.read_text())
            calls.append((index, out["seconds"], True))
        if "error" in out:
            raise reader.ReadError(out["error"])
        return None if out.get("timeout") else (mxl.read_bytes(), out["skipped"])

    return raw


def read(pdf: Path, out_xml: Path, raw_cache: Path, sig: str, audiveris: str, slots) -> dict:
    """Production's read_pdf over cached Audiveris output; seconds = what the Audiveris runs took in production's order
    (the first reading, then the retries side by side)."""
    from engine.read_pdf import ReadError, read_pdf
    calls, fresh = [], False
    out = {}
    try:
        r = read_pdf(pdf.read_bytes(), audiveris, raw=cached_raw(raw_cache, sig, slots, calls))
        fresh = bool(calls) and not calls[0][2]
        if fresh:
            # Waiting for a slot spent read_pdf's deadline, which can skip the retries production would make; read
            # again with the first reading cached (production skips them only after a first reading of over 210 s)
            calls.clear()
            r = read_pdf(pdf.read_bytes(), audiveris, raw=cached_raw(raw_cache, sig, slots, calls))
        out_xml.write_bytes(r.musicxml)
        out.update(ok=True, pages=r.pages, skipped=r.skipped, scan=r.scan)
    except ReadError as e:
        out.update(ok=False, error=str(e))
    except Exception as e:  # noqa: BLE001
        out.update(ok=False, error=f"{type(e).__name__}: {e}")
    first = [s for i, s, _ in calls if i == 0]
    out["seconds"] = round(sum(first) + max((s for i, s, _ in calls if i != 0), default=0), 1)
    out["cached"] = all(c for _, _, c in calls) and not fresh
    out["settings_read"] = sorted({i for i, _, _ in calls})
    return out


def score(truth: Path, omr: Path) -> dict:
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
    ap.add_argument("--set", nargs="*", default=[HERE.name])
    ap.add_argument("--out", default="results-baseline.json")
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--only", nargs="*", default=[])
    ap.add_argument("--tag", default="")
    ap.add_argument("--audiveris", default=str(DEFAULT_AUDIVERIS))
    a = ap.parse_args()
    # 19 GB machine: 6 readings at ~1.7 GB peak leave room for 12 scorers (Verovio, a few hundred MB each)
    jobs = min(a.jobs, 6)
    slots = threading.Semaphore(jobs)
    sig = install_signature(Path(a.audiveris)) + a.tag
    t0 = time.time()
    work = []  # (set folder, manifest, pdf entry)
    for name in a.set:
        folder = HERE.parent / name
        manifest = json.loads((folder / "manifest.json").read_text())
        (folder / "cache" / "raw").mkdir(parents=True, exist_ok=True)
        (folder / "cache" / "runs").mkdir(exist_ok=True)
        work += [(folder, manifest, p) for p in manifest["pdfs"] if not a.only or any(s in p["pdf"] for s in a.only)]

    def one(item):
        folder, manifest, p = item
        out_xml = folder / "cache" / "runs" / f"{Path(a.out).stem}--{Path(p['pdf']).stem}.musicxml"
        out_xml.unlink(missing_ok=True)
        r = read(folder / p["pdf"], out_xml, folder / "cache" / "raw", sig, a.audiveris, slots)
        row = {"pdf": p["pdf"], "piece": p["piece"], "engraver": p["engraver"], "pages": p["pages"],
               "crashed": not r["ok"], "error": r.get("error"), "pages_skipped": r.get("skipped", []),
               "seconds": r["seconds"], "seconds_per_page": round(r["seconds"] / p["pages"], 1), "cached": r["cached"],
               "settings_read": r["settings_read"], "truth_notes": 0}
        s = row["score"] = score(folder / manifest["pieces"][p["piece"]]["truth"], out_xml)
        row["truth_notes"] = s.get("truth_notes", 0)
        if "shared_pitch" in s:
            row["pitch"] = round(s["shared_pitch"] / s["truth_notes"], 4)
            row["pitch_onset"] = round(s["shared_pitch_onset"] / s["truth_notes"], 4)
        return folder, manifest, row

    # More threads than Audiveris slots: a PDF whose readings are cached only needs the engine and the scorer
    with ThreadPoolExecutor(max(1, min(len(work), 12))) as ex:
        done = list(ex.map(one, work))
    for name in a.set:
        folder = HERE.parent / name
        rows = [row for f, _, row in done if f == folder]
        manifest = next(m for f, m, _ in done if f == folder) if rows else {}
        by_eng = {e: summarise([r for r in rows if r["engraver"] == e]) for e in sorted({r["engraver"] for r in rows})}
        result = {"audiveris_install": sig, "wall_seconds_this_run": round(time.time() - t0, 1), "jobs": jobs,
                  "totals": summarise(rows), "by_engraver": by_eng, "pdfs": rows, "not_built": manifest.get("not_built", [])}
        (folder / a.out).write_text(json.dumps(result, indent=1))
        print(name, json.dumps({k: result["totals"][k] for k in ("pdfs", "crashed", "pitch", "pitch_onset", "bar_duration_errors")}))


if __name__ == "__main__":
    main()
