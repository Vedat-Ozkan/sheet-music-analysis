import collections, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from mx import *
S = Path(__file__).parent
# crash share: what the two crashing PDFs would score if they read
stem = "p-29-3--vr"; name = "bench-tune2"
man = json.loads((OMR / name / "manifest.json").read_text())
t = parse((OMR / name / man["pieces"]["p-29-3"]["truth"]).read_bytes())
o = parse((S / "crash1" / f"{stem}.mxl").read_bytes())
pairs = align_bars(t, o)
n = sum(sum(pitches(b).values()) for b in t)
sp = sum(sum((pitches(t[i]) & pitches(o[j])).values()) for i, j in pairs)
st = sum(sum((timed(t[i]) & timed(o[j])).values()) for i, j in pairs)
print(stem, "no-OCR read: notes", n, "pitch", round(sp / n, 4), "pitch+onset", round(st / n, 4))
tot, sh, sho = 148731, 0.9555304543101304 * 148731, 0.8876091736087298 * 148731
print("headline", round(sh / tot, 4), round(sho / tot, 4), "if both crash PDFs read at set averages (pitch .977, onset .91):", round((sh + 2601 * 0.977) / tot, 4), round((sho + 2601 * 0.91) / tot, 4), "excluding them:", round(sh / (tot - 2601), 4), round(sho / (tot - 2601), 4))
# parts
for setn, stem in (("bench", "bach-chorale-269--vr"), ("bench-heldout", "h-schubert-erlkonig--ly"), ("bench-tune2", "p-cornelius-peter-1-botschaft--vr")):
    p = OMR / "speed/cache/runs/pitch39" / f"{setn}--{stem}.musicxml"
    if not p.exists():
        print("missing", stem); continue
    root = root_of(p.read_bytes())
    pl = [(sp_.get("id"), sp_.findtext("part-name")) for sp_ in root.iter("score-part")]
    print(stem, "part-list", pl)
    rows = []
    for part in root.iter("part"):
        ms = list(part.iter("measure"))
        filled = [k for k, m in enumerate(ms) if any(n_.find("pitch") is not None for n_ in m.iter("note"))]
        systems = [k for k, m in enumerate(ms) if m.find("print") is not None and (m.find("print").get("new-system") == "yes" or m.find("print").get("new-page") == "yes")]
        rows.append((part.get("id"), len(ms), "notes in bars", (filled[0], filled[-1], len(filled)) if filled else None, "staves", sorted({n_.findtext("staff", "1") for n_ in part.iter("note")})))
    print("  ", rows)
    ms0 = list(next(root.iter("part")).iter("measure"))
    print("   new-system at", [k for k, m in enumerate(ms0) if m.find("print") is not None and (m.find("print").get("new-system") == "yes" or m.find("print").get("new-page") == "yes")][:14])
