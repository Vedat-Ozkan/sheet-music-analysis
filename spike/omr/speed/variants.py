import argparse
import hashlib
import json
import os
import shlex
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
FARM = HERE / "farm"
QUICK = {tuple(line.split()) for line in (HERE / "quick.txt").read_text().splitlines() if line.strip()}
farm = False
ROOT = HERE.parents[2]
BENCH = HERE.parent / "bench"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(BENCH))

import run as bench  # noqa: E402

AUDIVERIS = Path("/tmp/audiveris-5.11.0-sma.2/opt/audiveris/bin/Audiveris")
PRODUCTION_SIGNATURE = "afee6f19bde32f7d"
DPI = "org.audiveris.omr.image.ImageLoading.pdfResolution="
STUBS = "org.audiveris.omr.sheet.Book.processAllStubsInParallel=true"
SYSTEMS = "org.audiveris.omr.ui.action.AdvancedTopics.processSystemsInParallel=true"
PATCHED = "/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad/"
VARIANTS = {
    "production": ([], ""),
    "dpi250": ([DPI + "250"], ""),
    "dpi200": ([DPI + "200"], ""),
    "parallel": ([STUBS, SYSTEMS], ""),
    "parallel-heap2g": ([STUBS, SYSTEMS], "-Xmx2g"),
    "no-ocr": (["org.audiveris.omr.text.tesseract.TesseractOCR.useOCR=false"], ""),
    "stubs": ([STUBS], ""),
    "systems": ([SYSTEMS], ""),
    "production-rerun": ([], "", str(AUDIVERIS)),
    "heads-bitset": ([], "", PATCHED + "aud-heads/bin/Audiveris"),
    "heads-beams": ([], "", PATCHED + "aud-fast/bin/Audiveris"),
    "sma3": ([], "", PATCHED + "aud-sma3/bin/Audiveris"),
    "sma3-repeat": ([], "", PATCHED + "aud-sma3/bin/Audiveris"),
    "sma4": ([], "", PATCHED + "aud-sixnine/bin/Audiveris"),
    "sma4-88": (["org.audiveris.omr.sig.inter.AbstractTimeInter.optionalTimes=6/4, 7/8, 8/8"], "", PATCHED + "aud-sixnine/bin/Audiveris"),
    "sma3-88": (["org.audiveris.omr.sig.inter.AbstractTimeInter.optionalTimes=6/4, 7/8, 8/8"], "", PATCHED + "aud-sma3/bin/Audiveris"),
    "sma5": ([], "", PATCHED + "aud-sma5cand/bin/Audiveris"),
    "sma5-88": (["org.audiveris.omr.sig.inter.AbstractTimeInter.optionalTimes=6/4, 7/8, 8/8"], "", PATCHED + "aud-sma5cand/bin/Audiveris"),
    "sma6dpi": ([], "", PATCHED + "aud-dpi/bin/Audiveris"),
    "int1": ([], "", PATCHED + "aud-int1/bin/Audiveris"),
    "int2": ([], "", PATCHED + "aud-untimed-f3/bin/Audiveris"),
    "int3": ([], "", PATCHED + "aud-int3/bin/Audiveris"),
    "rc2": ([], "", PATCHED + "aud-rc2/bin/Audiveris"),
    "rc2-88": (["org.audiveris.omr.sig.inter.AbstractTimeInter.optionalTimes=6/4, 7/8, 8/8"], "", PATCHED + "aud-rc2/bin/Audiveris"),
    "solver1": ([], "", PATCHED + "aud-solver1/bin/Audiveris"),
    "sma4-leland": (["org.audiveris.omr.ui.symbol.MusicFont.defaultMusicFamily=Leland"], "", PATCHED + "aud-rc2/bin/Audiveris"),
    "sma4-fontmatch": ([], "", PATCHED + "aud-rc2/bin/Audiveris"),
    "pitch1": ([], "", PATCHED + "aud-pitch1/bin/Audiveris"),
    "pitch2": ([], "", PATCHED + "aud-pitch2/bin/Audiveris"),
    "pitch3": ([], "", PATCHED + "aud-pitch3/bin/Audiveris"),
    "pitch4": ([], "", PATCHED + "aud-pitch4/bin/Audiveris"),
    "pitch5": ([], "", PATCHED + "aud-pitch5/bin/Audiveris"),
    "pitch6": ([], "", PATCHED + "aud-pitch6/bin/Audiveris"),
    "pitch7": ([], "", PATCHED + "aud-pitch7/bin/Audiveris"),
    "pitch8": ([], "", PATCHED + "aud-pitch8/bin/Audiveris"),
    "pitch9": ([], "", PATCHED + "aud-pitch9/bin/Audiveris"),
    "pitch10": ([], "", PATCHED + "aud-pitch10/bin/Audiveris"),
    "pitch11": ([], "", PATCHED + "aud-pitch11/bin/Audiveris"),
    "pitch12": ([], "", PATCHED + "aud-pitch12/bin/Audiveris"),
    "pitch13": ([], "", PATCHED + "aud-pitch13/bin/Audiveris"),
    "pitch14": ([], "", PATCHED + "aud-pitch14/bin/Audiveris"),
    "pitch15": ([], "", PATCHED + "aud-pitch15/bin/Audiveris"),
    "pitch16": ([], "", PATCHED + "aud-pitch16/bin/Audiveris"),
    "pitch17": ([], "", PATCHED + "aud-pitch17/bin/Audiveris"),
    "pitch18": ([], "", PATCHED + "aud-pitch18/bin/Audiveris"),
    "pitch19": ([], "", PATCHED + "aud-pitch19/bin/Audiveris"),
    "pitch20": ([], "", PATCHED + "aud-pitch20/bin/Audiveris"),
    "pitch21": ([], "", PATCHED + "aud-pitch21/bin/Audiveris"),
    "pitch22": ([], "", PATCHED + "aud-pitch22/bin/Audiveris"),
    "pitch23": ([], "", PATCHED + "aud-pitch23/bin/Audiveris"),
    "pitch24": ([], "", PATCHED + "aud-pitch24/bin/Audiveris"),
    "pitch25": ([], "", PATCHED + "aud-pitch25/bin/Audiveris"),
    "pitch26": ([], "", PATCHED + "aud-pitch26/bin/Audiveris"),
    "pitch27": ([], "", PATCHED + "aud-pitch27/bin/Audiveris"),
    "pitch28": ([], "", PATCHED + "aud-pitch28/bin/Audiveris"),
    "pitch29": ([], "", PATCHED + "aud-pitch29/bin/Audiveris"),
    "pitch30": ([], "", PATCHED + "aud-pitch30/bin/Audiveris"),
    "pitch31": ([], "", PATCHED + "aud-pitch31/bin/Audiveris"),
    "pitch35": ([], "", PATCHED + "aud-pitch35/bin/Audiveris"),
    "pitch36": ([], "", PATCHED + "aud-pitch36/bin/Audiveris"),
    "pitch36-local": ([], "", PATCHED + "aud-pitch36/bin/Audiveris"),
    "sma4-fontmatch-local": ([], "", PATCHED + "aud-rc2/bin/Audiveris"),
    "pitch37": ([], "", PATCHED + "aud-pitch37/bin/Audiveris"),
    "pitch37-local": ([], "", PATCHED + "aud-pitch37/bin/Audiveris"),
    "pitch38": ([], "", PATCHED + "aud-pitch38/bin/Audiveris"),
    "pitch39": ([], "", PATCHED + "aud-pitch39/bin/Audiveris"),
    "pitch40": ([], "", PATCHED + "aud-pitch40/bin/Audiveris"),
    "pitch41": ([], "", PATCHED + "aud-pitch41/bin/Audiveris"),
    "pitch41r": ([], "", PATCHED + "aud-pitch41/bin/Audiveris"),
    "pitch42": ([], "", PATCHED + "aud-pitch42/bin/Audiveris"),
    "pitch43": ([], "", PATCHED + "aud-pitch43/bin/Audiveris"),
    "pitch44": (["org.audiveris.omr.sheet.key.KeyBuilder.minFlatTrail=0.5"], "", PATCHED + "aud-pitch43/bin/Audiveris"),
    "pitch45": ([], "", PATCHED + "aud-pitch45/bin/Audiveris"),
    "pitch47": ([], "", PATCHED + "aud-pitch47/bin/Audiveris"),
    "pitch51": ([], "", PATCHED + "aud-pitch51/bin/Audiveris"),
    "div1": ([], "", PATCHED + "aud-div1/bin/Audiveris"),
    "tie1": (["org.audiveris.omr.sig.inter.SlurInter.maxTieIntersection=1.0"], "", PATCHED + "aud-pitch51/bin/Audiveris"),
    "tie2": ([], "", PATCHED + "aud-tie2/bin/Audiveris"),
    "marks1": ([], "", PATCHED + "aud-marks1/bin/Audiveris"),
    "pitch49": ([], "", PATCHED + "aud-pitch49/bin/Audiveris"),
    "pitch48": (["org.audiveris.omr.sheet.rhythm.SlotsRetriever.maxAdjacencyXGap=0.2"], "", PATCHED + "aud-pitch47/bin/Audiveris"),
    "pitch46": (["org.audiveris.omr.sheet.key.KeyBuilder.minFlatTrail=0.5"], "", PATCHED + "aud-pitch45/bin/Audiveris"),
    "pitch37-small15": (["org.audiveris.omr.sig.inter.AlterInter.smallMaxHeight=1.5"], "", PATCHED + "aud-pitch37/bin/Audiveris"),
    "pitch36-a": ([], "", PATCHED + "aud-pitch36/bin/Audiveris"),
    "pitch36-b": ([], "", PATCHED + "aud-pitch36/bin/Audiveris"),
    "pitch36-pc1": ([], "", PATCHED + "aud-pitch36/bin/Audiveris"),
    "pitch36-pc2": ([], "", PATCHED + "aud-pitch36/bin/Audiveris"),
    "pitch31-braces": (["org.audiveris.omr.sheet.ProcessingSwitches.disconnectedBracedParts=true"], "", PATCHED + "aud-pitch31/bin/Audiveris"),
    "pitch32": ([], "", PATCHED + "aud-pitch32/bin/Audiveris"),
    "pitch33": ([], "", PATCHED + "aud-pitch33/bin/Audiveris"),
    "pitch33-here": ([], "", PATCHED + "aud-pitch33/bin/Audiveris"),
    "pitch31-here": ([], "", PATCHED + "aud-pitch31/bin/Audiveris"),
    "pitch31-pc1": ([], "", PATCHED + "aud-pitch31/bin/Audiveris"),
    "pitch31-pc2": ([], "", PATCHED + "aud-pitch31/bin/Audiveris"),
    "pitch32-pc1": ([], "", PATCHED + "aud-pitch32/bin/Audiveris"),
    "pitch32-pc2": ([], "", PATCHED + "aud-pitch32/bin/Audiveris"),
    "pitch32-here": ([], "", PATCHED + "aud-pitch32/bin/Audiveris"),
    "heads-beams-systems": ([SYSTEMS], "", PATCHED + "aud-fast/bin/Audiveris"),
}
SETS = ["bench", "bench-heldout", "bench-heldout2", "bench-heldout3", "bench-real"]


def farm_hosts() -> list[tuple[str, int, str]]:
    return [(host, int(slots), user) for host, slots, *rest in (line.split() for line in Path(os.environ.get("FARM_HOSTS", FARM / "hosts")).read_text().splitlines() if line.strip())
            for user in [rest[0] if rest else ""]]


def farm_reachable() -> None:
    import subprocess
    lines = []
    pages = {fields[0]: fields[3] for fields in (line.split() for line in Path(os.environ.get("FARM_HOSTS", FARM / "hosts")).read_text().splitlines()) if len(fields) > 3}
    for host, slots, user in farm_hosts():
        if host != "local":
            answer = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=6", host, "echo up"],
                                    capture_output=True, text=True, timeout=30).stdout
            if "up" not in answer:
                print("skipping", host, "(not answering)", flush=True)
                continue
        lines.append(" ".join(str(field) for field in (host, slots, user, pages.get(host, "")) if field != ""))
    active = FARM / "hosts.active"
    active.write_text("\n".join(lines) + "\n")
    os.environ["FARM_HOSTS"] = str(active)


def farm_sync(name: str) -> None:
    import subprocess
    options, java, *install = VARIANTS[name]
    real = (Path(install[0]) if install else AUDIVERIS).parent.parent
    jar = real / "lib" / "app" / "audiveris.jar"
    want = f"{jar.stat().st_size} {int(jar.stat().st_mtime)}"
    for host, _, user in farm_hosts():
        if host == "local":
            continue
        remote_jar = f"/opt/omr/{real.name}/lib/app/audiveris.jar"
        have = subprocess.run(["ssh", "-o", "BatchMode=yes", host, f"wsl -d Ubuntu -u root -- stat -c '%s %Y' {remote_jar}"],
                              capture_output=True, text=True).stdout.strip()
        if have == want:
            continue
        print("copying", real.name, "to", host, flush=True)
        bundle = Path("/tmp/claude-1000") / f"{real.name}.tgz"
        subprocess.run(["tar", "czf", str(bundle), "-C", str(real.parent), real.name], check=True)
        subprocess.run(["ssh", "-o", "BatchMode=yes", host, f"if not exist C:\\Users\\{user}\\omr mkdir C:\\Users\\{user}\\omr"], check=True)
        subprocess.run(["scp", "-q", "-o", "BatchMode=yes", str(bundle), f"{host}:C:/Users/{user}/omr/"], check=True)
        subprocess.run(["ssh", "-o", "BatchMode=yes", host, f"wsl -d Ubuntu -u root -- bash -c \"rm -rf /opt/omr/{real.name} && mkdir -p /opt/omr && tar xzf /mnt/c/Users/{user}/omr/{real.name}.tgz -C /opt/omr && touch -d @{int(jar.stat().st_mtime)} {remote_jar}\""], check=True)
        bundle.unlink()


def launcher(name: str) -> Path:
    if name == "production":
        return AUDIVERIS
    options, java, *install = VARIANTS[name]
    real = Path(install[0]) if install else AUDIVERIS
    home = HERE / "launchers" / name
    (home / "bin").mkdir(parents=True, exist_ok=True)
    tessdata = home / "tessdata"
    if not tessdata.exists():
        tessdata.symlink_to(real.parent.parent / "tessdata")
    script = home / "bin" / "Audiveris"
    extra = " ".join(f"-option {shlex.quote(option)}" for option in options)
    java_line = f'export _JAVA_OPTIONS="$_JAVA_OPTIONS {java}"\n' if java else ""
    farm_line = f"export FARM_INSTALL={real.parent.parent}\n" if farm else ""
    target = FARM / "audiveris" if farm else real
    script.write_text(f"#!/bin/bash\n{java_line}{farm_line}exec {target} {extra} \"$@\"\n")
    script.chmod(0o755)
    return script


def signature(name: str) -> str:
    if name == "production":
        return PRODUCTION_SIGNATURE
    options, java, *install = VARIANTS[name]
    jar = (Path(install[0]) if install else AUDIVERIS).parent.parent / "lib" / "app" / "audiveris.jar"
    definition = json.dumps([VARIANTS[name], jar.stat().st_size, int(jar.stat().st_mtime)])
    return "speed-" + name + hashlib.sha256(definition.encode()).hexdigest()[:8]


def time_reads(name: str, pdfs: list[Path], out: Path) -> None:
    from engine.read_pdf import read_pdf
    audiveris = str(launcher(name))
    for pdf in pdfs:
        started = time.monotonic()
        try:
            reading = read_pdf(pdf.read_bytes(), audiveris)
            passes, outcome = reading.passes, "ok"
        except Exception as error:  # noqa: BLE001
            passes, outcome = getattr(error, "passes", []), f"{type(error).__name__}: {error}"
        record = {"variant": name, "pdf": pdf.name, "cpus": sorted(os.sched_getaffinity(0)),
                  "wall": round(time.monotonic() - started, 1), "outcome": outcome,
                  "passes": [{key: value for key, value in p.items() if key in ("setting", "outcome", "seconds", "step_seconds", "interlines")} for p in passes]}
        with out.open("a") as sink:
            sink.write(json.dumps(record) + "\n")
        print(f"{name} {pdf.name}: read_pdf wall {record['wall']} s;",
              "; ".join(f"setting {p['setting']} {p['outcome']} {p['seconds']} s" for p in record["passes"]))


def previous_seconds() -> dict[tuple[str, str], float]:
    seconds = {}
    for path in sorted((HERE / "results").glob("bench-*.json"), key=lambda p: p.stat().st_mtime):
        try:
            pdfs = json.loads(path.read_text()).get("pdfs", {})
        except (json.JSONDecodeError, AttributeError):
            continue
        for set_name, rows in pdfs.items():
            for row in rows:
                if not row.get("cached"):
                    seconds[(set_name, row["pdf"])] = row["seconds"]
    return seconds


def run_bench(name: str, sets: list[str], jobs: int, only: list[str], quick: bool = False, both: bool = False) -> None:
    if farm:
        os.environ["BENCH_TIME_SCALE"] = "4"
        farm_reachable()
        farm_sync(name)
        jobs = sum(slots for _, slots, _ in farm_hosts())
    audiveris = str(launcher(name))
    sig = signature(name)
    slots = threading.Semaphore(jobs if farm else min(jobs, 6))
    work = []
    for set_name in sets:
        folder = HERE.parent / set_name
        manifest = json.loads((folder / "manifest.json").read_text())
        cache = folder / "cache" / "raw" if name == "production" else HERE / "cache" / set_name
        cache.mkdir(parents=True, exist_ok=True)
        work += [(set_name, folder, manifest, cache, p) for p in manifest["pdfs"]
                 if (not only or any(s in p["pdf"] for s in only))
                 and (not quick or (set_name, Path(p["pdf"]).stem) in QUICK)]
    seconds = previous_seconds()
    work.sort(key=lambda item: -seconds.get((item[0], item[4]["pdf"]), 1e9))
    runs = HERE / "cache" / "runs" / name
    runs.mkdir(parents=True, exist_ok=True)

    def one(item):
        set_name, folder, manifest, cache, p = item
        out_xml = runs / f"{set_name}--{Path(p['pdf']).stem}.musicxml"
        out_xml.unlink(missing_ok=True)
        result = bench.read(folder / p["pdf"], out_xml, cache, sig, audiveris, slots, production=not both)
        row = {"pdf": p["pdf"], "piece": p["piece"], "engraver": p["engraver"], "pages": p["pages"],
               "crashed": not result["ok"], "error": result.get("error"), "pages_skipped": result.get("skipped", []),
               "seconds": result["seconds"], "cached": result["cached"], "settings_read": result["settings_read"]}
        score = row["score"] = bench.score(folder / manifest["pieces"][p["piece"]]["truth"], out_xml)
        row["truth_notes"] = score.get("truth_notes", 0)
        return set_name, row

    started = time.time()
    with ThreadPoolExecutor(max(1, min(len(work), max(12, jobs)))) as pool:
        done = list(pool.map(one, work))
    result = {"variant": name, "definition": VARIANTS[name], "signature": sig, "wall": round(time.time() - started, 1),
              "settings": "both" if both else "production",
              "totals": {s: bench.summarise([row for set_name, row in done if set_name == s]) for s in sets},
              "pdfs": {s: [row for set_name, row in done if set_name == s] for s in sets}}
    out = HERE / "results" / f"bench-{name}{'-only' if only else '-quick' if quick else ''}{'-both' if both else ''}.json"
    out.write_text(json.dumps(result, indent=1))
    for s in sets:
        t = result["totals"][s]
        print(name, s, {k: t[k] for k in ("pdfs", "crashed", "pages_skipped", "pitch", "pitch_onset", "bar_duration_errors")})


def main():
    parser = argparse.ArgumentParser(description="Speed variants of the PDF reader: time them like production, or score them on the benchmark.")
    sub = parser.add_subparsers(dest="command", required=True)
    timing = sub.add_parser("time")
    timing.add_argument("variant", choices=VARIANTS)
    timing.add_argument("pdfs", nargs="+", type=Path)
    timing.add_argument("--out", type=Path, default=HERE / "results" / "read_pdf_timings.jsonl")
    scoring = sub.add_parser("bench")
    scoring.add_argument("variant", choices=VARIANTS)
    scoring.add_argument("--set", nargs="*", default=SETS)
    scoring.add_argument("--jobs", type=int, default=6)
    scoring.add_argument("--only", nargs="*", default=[])
    scoring.add_argument("--farm", action="store_true", help="spread readings over the machines in farm/hosts")
    scoring.add_argument("--quick", action="store_true", help="only the PDFs listed in quick.txt")
    scoring.add_argument("--both-settings", action="store_true", help="always read both settings instead of stopping like production")
    args = parser.parse_args()
    global farm
    farm = args.command == "bench" and args.farm
    if args.command == "time":
        time_reads(args.variant, args.pdfs, args.out)
    else:
        sets = args.set
        if args.quick and args.set == SETS:
            sets = sorted({set_name for set_name, _ in QUICK}, key=lambda s: (SETS + [s]).index(s))
        run_bench(args.variant, sets, args.jobs, args.only, args.quick, args.both_settings)


if __name__ == "__main__":
    main()
