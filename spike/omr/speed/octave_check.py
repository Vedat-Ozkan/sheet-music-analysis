import collections
import json
import sys

from pitch_causes import HERE, OMR, bars, xml_root, align, fill, load, SETS


def counts(tb, rb, pairs):
    under = right = wrong_outside = 0
    for i, j in pairs:
        if i >= len(tb) or j >= len(rb):
            continue
        read = collections.Counter((n["start"], n["midi"]) for n in rb[j] if not n["grace"])
        for n in tb[i]:
            if n["grace"]:
                continue
            key = (n["start"], n["midi"])
            hit = read[key] > 0
            if hit:
                read[key] -= 1
            if n["shift"]:
                under += 1
                right += hit
            elif not hit and any(s == n["start"] and abs(m - n["midi"]) % 12 == 0 and m != n["midi"] for s, m in read):
                wrong_outside += 1
    return under, right, wrong_outside


def main():
    variant = sys.argv[1]
    sets = sys.argv[2].split(",") if len(sys.argv) > 2 else SETS
    show = "--aggregate" not in sys.argv
    totals = collections.Counter()
    for name in sets:
        manifest = json.loads((OMR / name / "manifest.json").read_text())["pieces"]
        for reading in sorted((HERE / "cache" / "runs" / variant).glob(f"{name}--*.musicxml")):
            stem = reading.stem.split("--", 1)[1]
            piece = stem.rsplit("--", 1)[0]
            data = reading.read_bytes()
            tdata = (OMR / name / manifest[piece]["truth"]).read_bytes()
            truth, omr = load(tdata)[0], load(data)[0]
            tb, rb = bars(xml_root(tdata)), bars(xml_root(data))
            pairs = fill(align([(b,) for b in truth], [(b,) for b in omr])[0], len(truth), len(omr))
            under, right, outside = counts(tb, rb, pairs)
            totals.update(pdfs=1, under=under, right=right, outside=outside, with_line=bool(under))
            if show and (under or outside):
                print(f"{name}\t{stem}\tunder line {under}\tright {right}\twrong octave outside {outside}")
    print(variant, dict(totals))


if __name__ == "__main__":
    main()
