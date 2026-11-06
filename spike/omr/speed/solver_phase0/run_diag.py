import json
import os
import re
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from engine import read_pdf as reader  # noqa: E402

AUDIVERIS = sys.argv[1]
OUT = Path(sys.argv[2])
BENCH = ROOT / "spike/omr/bench"


def persistent_raw(name: str):
    def raw(data, audiveris, options, deadline, stop):
        index = reader.SETTINGS.index(options)
        work = OUT / name / f"s{index}"
        meta = work / "raw.json"
        if not meta.exists():
            work.mkdir(parents=True, exist_ok=True)
            source = work / "score.pdf"
            source.write_bytes(data)
            env = {key: value for key, value in os.environ.items() if key != "FONTCONFIG_FILE"}
            env.setdefault("TESSDATA_PREFIX", str(Path(audiveris).parent.parent / "tessdata"))
            env.update(HOME=str(work), _JAVA_OPTIONS="-Xmx1g -Djava.awt.headless=true -Dsun.java2d.uiScale=1")
            started = time.monotonic()
            run_ = reader.run(audiveris, options, source, str(work), env, time.monotonic() + reader.TIMEOUT, threading.Event())
            facts = reader.audiveris_facts(run_)
            books = sorted(work.glob("*.omr"))
            if run_.ending == "done" and not list(work.glob("*.mxl")) and books:
                export = reader.run(audiveris, options, books[0], str(work), env, time.monotonic() + reader.TIMEOUT, threading.Event())
                facts["outcome"] = "done" if export.ending == "done" else export.ending
            skipped = sorted({int(page) for page in re.findall(r"Sheet \S+#(\d+) flagged as invalid", run_.output)})
            meta.write_text(json.dumps({"facts": facts, "skipped": skipped, "seconds": round(time.monotonic() - started, 1)}))
        info = json.loads(meta.read_text())
        scores = sorted(work.glob("*.mxl"))
        if info["facts"]["outcome"] != "done" or not scores:
            return reader.RawReading(None, [], info["facts"])
        return reader.RawReading(scores[0].read_bytes(), info["skipped"], info["facts"])
    return raw


def chosen_setting(data: bytes, raw) -> int:
    results = [reader._read(data, AUDIVERIS, options, time.monotonic() + 60, raw, threading.Event())[1] for options in reader.SETTINGS]
    readings = [(number, reading) for number, reading in enumerate(results) if reading is not None]
    counts = [reader._pitched_notes(reading[0]) for _, reading in readings]
    complete = [(number, reading) for (number, reading), count in zip(readings, counts) if count >= reader.MIN_NOTES * max(counts)]
    return min(complete, key=lambda item: (len(item[1][1]), len(item[1][2])))[0]


def main():
    manifest = json.loads((BENCH / "manifest.json").read_text())
    rows = {p["pdf"].split("/")[-1][:-4]: p for p in manifest["pdfs"]}
    for stem in sys.argv[3:]:
        done = OUT / stem / "reading.json"
        if done.exists():
            continue
        data = (BENCH / rows[stem]["pdf"]).read_bytes()
        raw = persistent_raw(stem)
        started = time.monotonic()
        reading = reader.read_pdf(data, AUDIVERIS, raw=raw)
        (OUT / stem / "reading.musicxml").write_bytes(reading.musicxml)
        done.write_text(json.dumps({"pdf": rows[stem]["pdf"], "piece": rows[stem]["piece"], "engraver": rows[stem]["engraver"],
                                    "pages": rows[stem]["pages"], "chosen": chosen_setting(data, raw), "skipped": reading.skipped,
                                    "seconds": round(time.monotonic() - started, 1)}))
        print(stem, json.loads(done.read_text()), flush=True)


if __name__ == "__main__":
    main()
