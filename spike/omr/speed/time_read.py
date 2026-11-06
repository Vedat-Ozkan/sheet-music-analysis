import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from engine import read_pdf as reader  # noqa: E402

AUDIVERIS = "/tmp/audiveris-5.11.0-sma.2/opt/audiveris/bin/Audiveris"
PRODUCTION_JAVA = "-Xmx1g -Djava.awt.headless=true -Dsun.java2d.uiScale=1"


def read_once(source: Path, setting: int, extra_options: list[str], java: str, audiveris: str, keep: Path | None,
              prefix: list[str]) -> dict:
    work = Path(tempfile.mkdtemp(prefix="speed_"))
    try:
        inputs = []
        for number, path in enumerate([source] if source.is_file() else sorted(source.iterdir())):
            target = work / (f"score{path.suffix}" if source.is_file() else f"p{number:02d}{path.suffix}")
            shutil.copy(path, target)
            inputs.append(str(target))
        env = {key: value for key, value in os.environ.items() if key != "FONTCONFIG_FILE"}
        env.setdefault("TESSDATA_PREFIX", str(Path(audiveris).parent.parent / "tessdata"))
        env.update(HOME=str(work), _JAVA_OPTIONS=f"{PRODUCTION_JAVA} {java}".strip())
        options = list(reader.SETTINGS[setting])
        for option in extra_options:
            options += ["-option", option]
        command = prefix + [audiveris, "-batch", *options, "-export", "-output", str(work), *inputs]
        log = work / "audiveris.txt"
        steps: Counter = Counter()
        current, since, pending = "START", time.monotonic(), b""

        def follow(reader_file) -> None:
            nonlocal current, since, pending
            pending += reader_file.read()
            *lines, pending = pending.split(b"\n")
            for line in lines:
                if match := reader.STEP.search(line.decode(errors="replace")):
                    now = time.monotonic()
                    steps[current] += now - since
                    current, since = match.group(1), now

        started = time.monotonic()
        with open(log, "wb") as sink, open(log, "rb") as reader_file:
            process = subprocess.Popen(command, stdout=sink, stderr=subprocess.STDOUT, env=env)
            while True:
                pid, status, usage = os.wait4(process.pid, os.WNOHANG)
                if pid:
                    break
                time.sleep(0.2)
                follow(reader_file)
            follow(reader_file)
        wall = time.monotonic() - started
        steps[current] += time.monotonic() - since
        output = log.read_text(errors="replace")
        run = reader.AudiverisRun("done", os.waitstatus_to_exitcode(status), output,
                                  {name: round(seconds, 1) for name, seconds in steps.items()})
        facts = reader.audiveris_facts(run)
        scores = sorted(work.glob("*.mxl"))
        record = {"wall": round(wall, 1), "user": round(usage.ru_utime, 1), "sys": round(usage.ru_stime, 1),
                  "cpu_share": round((usage.ru_utime + usage.ru_stime) / wall, 2),
                  "max_rss_mb": round(usage.ru_maxrss / 1024), "exit_code": run.exit_code,
                  "steps": run.step_seconds, "images": facts["images"], "interlines": facts["interlines"],
                  "pages_done": facts["pages_done"], "problems": facts["problems"], "scores": [s.name for s in scores]}
        if scores:
            musicxml = reader.clean(scores[0].read_bytes())
            record["pitched_notes"] = reader._pitched_notes(musicxml)
            record["uneven_bars"] = len(reader._problem_spots(musicxml, timing=False)[0])
            if keep:
                keep.mkdir(parents=True, exist_ok=True)
                for score in scores:
                    shutil.copy(score, keep / score.name)
                shutil.copy(log, keep / "audiveris.txt")
        return record
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description="Time one Audiveris reading as production runs it; run under taskset -c 0,1 to mimic 2 vCPUs.")
    parser.add_argument("source", type=Path, help="a PDF, an image, or a folder of page images read as one book")
    parser.add_argument("--label", required=True)
    parser.add_argument("--setting", type=int, default=0)
    parser.add_argument("--option", action="append", default=[], help="extra Audiveris -option, e.g. org.audiveris.omr.image.ImageLoading.pdfResolution=200")
    parser.add_argument("--java", default="", help="extra JVM flags appended to production's _JAVA_OPTIONS")
    parser.add_argument("--audiveris", default=AUDIVERIS)
    parser.add_argument("--prefix", default="", help="command prefix, e.g. 'nice -n 19'")
    parser.add_argument("--keep", type=Path)
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "results" / "timings.jsonl")
    args = parser.parse_args()
    record = {"label": args.label, "source": args.source.name, "setting": args.setting, "options": args.option,
              "java": args.java, "cpus": sorted(os.sched_getaffinity(0)),
              **read_once(args.source, args.setting, args.option, args.java, args.audiveris, args.keep, args.prefix.split())}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("a") as sink:
        sink.write(json.dumps(record) + "\n")
    top = sorted(record["steps"].items(), key=lambda item: -item[1])[:8]
    print(f"{args.label} {args.source.name}: wall {record['wall']} s, cpu {record['user'] + record['sys']:.1f} s "
          f"({record['cpu_share']}x), rss {record['max_rss_mb']} MB, interlines {record['interlines']}, "
          f"notes {record.get('pitched_notes')}, uneven {record.get('uneven_bars')}")
    print("   ", ", ".join(f"{name} {seconds}" for name, seconds in top))


if __name__ == "__main__":
    main()
