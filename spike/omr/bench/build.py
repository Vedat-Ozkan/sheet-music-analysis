import argparse, json, os, shutil, subprocess, sys, tempfile, zlib, xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
import pikepdf  # noqa: E402
from features import read_xml, totals  # noqa: E402
from pieces import P, REAL  # noqa: E402

MUSESCORE = "/mnt/c/Program Files/MuseScore 4/bin/MuseScore4.exe"
HOMR_PY = ROOT / "spike/omr/homr-venv/bin/python"
M21 = ROOT / ".venv/lib/python3.11/site-packages/music21/corpus"
MAX_PAGES = 12


def find(root: Path, sub: str) -> Path:
    hits = sorted(h for h in root.rglob("*") if h.suffix in (".mxl", ".musicxml", ".xml") and sub in str(h))
    if len(hits) != 1:
        raise SystemExit(f"{sub}: {len(hits)} matches in {root}")
    return hits[0]


def excerpt(data: bytes, bars: int) -> bytes:
    root = ET.fromstring(read_xml(data))
    for part in root.iter("part"):
        for m in list(part.iter("measure"))[bars:]:
            part.remove(m)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def pages(pdf: Path) -> int:
    with pikepdf.open(pdf) as p:
        return len(p.pages)


def musescore(truth: Path, out: Path):
    w = lambda p: subprocess.check_output(["wslpath", "-w", str(p)], text=True).strip()
    subprocess.run([MUSESCORE, "-o", w(out), w(truth)], check=True, capture_output=True, timeout=180)


def verovio(truth: Path, out: Path):
    from engine.render import engrave
    out.write_bytes(engrave(truth.read_bytes()).pdf())


def lilypond(truth: Path, out: Path, lily: Path):
    env = dict(os.environ, PATH=f"{lily}:{os.environ['PATH']}")
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["musicxml2ly", "-o", f"{d}/s.ly", str(truth)], check=True, capture_output=True, env=env, timeout=120, cwd=d)
        subprocess.run(["lilypond", "-o", f"{d}/s", f"{d}/s.ly"], check=True, capture_output=True, env=env, timeout=300, cwd=d)
        shutil.copy(f"{d}/s.pdf", out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lieder", required=True)
    ap.add_argument("--sq", required=True)
    ap.add_argument("--lilypond-bin", required=True)
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    roots = {"truth": ROOT / "spike/omr/truth", "m21": M21, "lieder": Path(a.lieder) / "scores", "sq": Path(a.sq) / "scores"}
    (HERE / "truth").mkdir(exist_ok=True)
    (HERE / "pdfs").mkdir(exist_ok=True)
    manifest = {"pieces": {}, "pdfs": [], "not_built": []}
    for pid, kind, (root, sub), url, lic, bars, engravers in P:
        if a.only and pid not in a.only:
            continue
        src = find(roots[root], sub)
        data = src.read_bytes()
        if bars:
            truth = HERE / "truth" / f"{pid}.musicxml"
            truth.write_bytes(excerpt(data, bars))
        else:
            truth = HERE / "truth" / f"{pid}.mxl"
            truth.write_bytes(data)
        manifest["pieces"][pid] = {"kind": kind, "truth": str(truth.relative_to(HERE)), "source_url": url, "licence": lic,
                                   "excerpt_first_bars": bars, "truth_counts": totals(truth.read_bytes())}
        made = {}
        for eng in engravers:
            out = HERE / "pdfs" / f"{pid}--{'ms' if eng == 'scan' else eng}.pdf" if eng != "scan" else HERE / "pdfs" / f"{pid}--scan.pdf"
            try:
                if eng == "ms":
                    musescore(truth, out)
                elif eng == "vr":
                    verovio(truth, out)
                elif eng == "ly":
                    lilypond(truth, out, Path(a.lilypond_bin))
                elif eng == "scan":
                    base = made.get("ms") or made.get("ly") or made.get("vr")
                    subprocess.run([str(HOMR_PY), str(HERE / "scanify.py"), str(base), str(out), str(zlib.crc32(pid.encode()) % 1000)], check=True, capture_output=True)
                n = pages(out)
                if n > MAX_PAGES:
                    out.unlink()
                    manifest["not_built"].append({"piece": pid, "engraver": eng, "reason": f"{n} pages > {MAX_PAGES}"})
                    continue
                made[eng] = out
                manifest["pdfs"].append({"pdf": f"pdfs/{out.name}", "piece": pid, "engraver": eng, "pages": n})
            except Exception as e:  # noqa: BLE001 - record and go on; the README lists what did not build
                err = getattr(e, "stderr", b"")
                manifest["not_built"].append({"piece": pid, "engraver": eng, "reason": f"{type(e).__name__}: {str(err)[-200:] if err else e}"})
    for pid, eng, path in REAL:
        if a.only and pid not in a.only:
            continue
        p = ROOT / path
        dst = HERE / "pdfs" / f"{pid}--{eng}.pdf"
        shutil.copy(p, dst)
        manifest["pdfs"].append({"pdf": f"pdfs/{dst.name}", "piece": pid, "engraver": eng, "pages": pages(dst)})
    (HERE / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False))
    print(len(manifest["pieces"]), "pieces,", len(manifest["pdfs"]), "pdfs; not built:", manifest["not_built"])


if __name__ == "__main__":
    main()
