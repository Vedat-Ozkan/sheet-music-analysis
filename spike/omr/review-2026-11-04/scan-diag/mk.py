import json, sys
from imgs import *
split = json.loads((BO / "split.json").read_text())
transform, half = sys.argv[1], sys.argv[2]
names = split[half] if half in split else [n for n in split["inspect"] if any(k in n for k in half.split(","))]
tag = f"{transform}-{half}" if half in split else f"{transform}-few"
out = HOME / "items" / tag; out.mkdir(parents=True, exist_ok=True)
items, notes = [], {}
for n in names:
    im = load(n); a = np.asarray(im); il = interline(a); dpi = 300; note = {"il": il}
    if transform == "native": pass
    elif transform.startswith("page"):
        dpi = 300 * il / int(transform[4:])
    elif transform.startswith("lz"):
        im = rescale(im, int(transform[2:]))
    elif transform.startswith("bin"):
        im = binarize(rescale(im, int(transform[3:])))
    elif transform == "otsu": im = binarize(im)
    elif transform == "deskew": im, note["angle"] = deskew(im)
    elif transform == "edges": im = blank_edges(im)
    elif transform == "above": im, note["ok"] = blank_above(im)
    elif transform in ("time", "timeabove"):
        info, fifths, printed = truth_info(n)
        real = real_time(n)
        note.update(inferred=info, real=real, printed=printed)
        if transform == "timeabove": im, _ = blank_above(im)
        if not printed:
            t = real or info
            new = insert_time(im, t[0], t[1], fifths)
            note["inserted"] = new is not None
            im = new or im
    p = out / f"{n}.pdf"; to_pdf(im, p, dpi)
    items.append({"name": n, "pdf": str(p), "truth": str(BO / "truth" / f"{n}.musicxml")}); notes[n] = note
(out / "items.json").write_text(json.dumps(items)); (out / "notes.json").write_text(json.dumps(notes, indent=0))
print(tag, len(items))
