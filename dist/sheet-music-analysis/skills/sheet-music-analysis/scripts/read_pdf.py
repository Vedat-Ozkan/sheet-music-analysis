"""Read a PDF of printed music into MusicXML and engrave what was read, for the user to check before the analysis.

    python3 read_pdf.py SCORE.pdf --out-dir DIR [--name score] [--keep-slurs]

Writes DIR/score.musicxml, which the other scripts take as the score, and DIR/score.png (score-p1.png, ... for several
pages). The first run downloads Audiveris 5.11.0 and its English text data from GitHub (about 100 MB) into the temporary folder. Slurs are left
out unless --keep-slurs is given; a reading is kept per file, so asking again for the slurs does not read the PDF again.
"""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

import verovio

from engine.read_pdf import PREVIEW_OPTIONS, READER, PdfReading, ReadError, fit_top_margin, notice, problem_spots, read_pdf, shade, without_slurs
from engine.render import VEROVIO_OPTIONS, Engraving, ScoreError, load_toolkit
from engine.score import ScoreIndex

verovio.enableLog(False)

DEB = "https://github.com/Audiveris/audiveris/releases/download/5.11.0/Audiveris-5.11.0-ubuntu24.04-x86_64.deb"
DEB_SHA256 = "f20113aaa33b3149ec8d6a09b2a7963360e65fafd92d69389987a85bbc3ec7a3"
JAR = "https://github.com/Vedat-Ozkan/audiveris/releases/download/5.11.0-sma.2/audiveris.jar"
JAR_SHA256 = "1fe3060f7cf86d5b7a30daec973107789e1fba85c4e06de70fc9279b1c58edc5"
OCR = "https://github.com/tesseract-ocr/tessdata/raw/ced78752cc61322fb554c280d13360b35b8684e4/eng.traineddata"
OCR_SHA256 = "daa0c97d651c19fba3b25e81317cd697e9908c8208090c94c3905381c23fc047"
HOME = Path(tempfile.gettempdir()) / "audiveris-5.11.0-sma.2"


def audiveris() -> Path:
    launcher = HOME / "opt/audiveris/bin/Audiveris"
    if not launcher.exists():
        install()
    english = HOME / "opt/audiveris/tessdata/eng.traineddata"
    if not english.exists():
        english.parent.mkdir(exist_ok=True)
        part = english.with_suffix(".part")
        urllib.request.urlretrieve(OCR, part)
        if hashlib.sha256(part.read_bytes()).hexdigest() != OCR_SHA256:
            raise OSError("The downloaded OCR data does not match the tested file")
        part.rename(english)
    return launcher


def install() -> None:
    deb, unpacked = HOME.with_suffix(".deb"), HOME.with_suffix(".part")
    urllib.request.urlretrieve(DEB, deb)
    if hashlib.sha256(deb.read_bytes()).hexdigest() != DEB_SHA256:
        raise OSError("The downloaded Audiveris package does not match the tested release")
    shutil.rmtree(unpacked, ignore_errors=True)
    subprocess.run(["dpkg-deb", "-x", str(deb), str(unpacked)], check=True)
    jar = unpacked / "opt/audiveris/lib/app/audiveris.jar"
    urllib.request.urlretrieve(JAR, jar)
    if hashlib.sha256(jar.read_bytes()).hexdigest() != JAR_SHA256:
        raise OSError("The downloaded Audiveris does not match the tested build")
    unpacked.rename(HOME)
    deb.unlink()


def pages(score: bytes, spots) -> Engraving:
    toolkit = load_toolkit(score, PREVIEW_OPTIONS)
    fit_top_margin(toolkit, ScoreIndex(toolkit.getMEI()))
    height = VEROVIO_OPTIONS["pageHeight"]
    count = toolkit.getPageCount()
    while count > 1 and len(re.findall(r'class="measure"', toolkit.renderToSVG(count))) <= 2:
        if height >= VEROVIO_OPTIONS["pageHeight"] * 1.5:
            break
        height += 100
        toolkit.setOptions({"pageHeight": height})
        toolkit.redoLayout()
        if toolkit.getPageCount() < count:
            break
    return shade(toolkit, score, spots)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--name", default="score", help="file name without extension")
    parser.add_argument("--keep-slurs", action="store_true", help="keep the slurs, which are often misread")
    args = parser.parse_args()

    try:
        data = args.pdf.read_bytes()
        cache = HOME.parent / f"read-pdf-{READER}-{hashlib.sha256(data).hexdigest()}.json"
        if cache.exists():
            saved = json.loads(cache.read_text())
            reading = PdfReading(saved["musicxml"].encode(), saved["pages"], saved["scan"], saved["skipped"])
        else:
            reading = read_pdf(data, audiveris=str(audiveris()))
            saved = {"musicxml": reading.musicxml.decode(), "pages": reading.pages, "scan": reading.scan, "skipped": reading.skipped}
            cache.write_text(json.dumps(saved))
        shown = reading.musicxml if args.keep_slurs else without_slurs(reading.musicxml)
        spots = problem_spots(shown)
        engraving = pages(shown, spots)
        message = notice(shown, reading.scan, reading.skipped, args.keep_slurs, spots)
    except (ReadError, ScoreError, OSError, subprocess.CalledProcessError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    args.out_dir.mkdir(parents=True, exist_ok=True)
    score = args.out_dir / f"{args.name}.musicxml"
    score.write_bytes(shown)
    print(score)
    for page in range(1, engraving.page_count + 1):
        suffix = "" if engraving.page_count == 1 else f"-p{page}"
        path = args.out_dir / f"{args.name}{suffix}.png"
        path.write_bytes(engraving.png(page, width=1600))
        print(path)
    print(f"Read {reading.pages} PDF page(s); scanned: {'yes' if reading.scan else 'no'}.")
    print(
        f"Show the user every PNG listed above ({engraving.page_count} page{'s' if engraving.page_count > 1 else ''}, in order), "
        "with this message above them, then wait. Analyse the .musicxml only after they say to go ahead"
        + ("" if args.keep_slurs else "; if they ask to keep the slurs, run this again with --keep-slurs")
        + ":\n" + message
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
