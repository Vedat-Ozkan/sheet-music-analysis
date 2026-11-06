import json
import sys
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[2]), str(HERE.parent / "bench"), str(HERE)]
import run as bench  # noqa: E402
import variants  # noqa: E402
from engine import read_pdf as reader  # noqa: E402

SETS = ["bench", "bench-heldout", "bench-heldout2", "bench-heldout3", "bench-real"]


def main():
    name = sys.argv[1]
    sets = sys.argv[2].split(",") if len(sys.argv) > 2 else SETS
    sig, audiveris = variants.signature(name), str(variants.launcher(name))
    out_dir = HERE / "cache" / "runs" / f"{name}-prod"
    out_dir.mkdir(parents=True, exist_ok=True)
    slots, differ = threading.Semaphore(1), []
    for set_name in sets:
        manifest = json.loads((HERE.parent / set_name / "manifest.json").read_text())
        for p in manifest["pdfs"]:
            data = (HERE.parent / set_name / p["pdf"]).read_bytes()
            raw = bench.cached_raw(HERE / "cache" / set_name, sig, slots, [])
            first = raw(data, audiveris, 0, reader.uses_leland(reader.open_pdf(data)), 0, threading.Event())
            stops = first.mxl is not None and len(reader._problem_spots(reader.clean(first.mxl), timing=False)[0]) <= reader.RETRY_ABOVE

            def production(data, audiveris, setting, leland, deadline, stop):
                if setting > 0 and stops:
                    return reader.RawReading(None, [], {"outcome": "stopped"})
                return raw(data, audiveris, setting, leland, deadline, stop)

            stem = f"{set_name}--{Path(p['pdf']).stem}.musicxml"
            try:
                musicxml = reader.read_pdf(data, audiveris, raw=production).musicxml
            except reader.ReadError:
                continue
            (out_dir / stem).write_bytes(musicxml)
            if musicxml != (HERE / "cache" / "runs" / name / stem).read_bytes():
                differ.append(stem)
    print(f"{name}: {len(differ)} readings differ from the benchmark's choice")
    for stem in differ:
        print("  ", stem)


main()
