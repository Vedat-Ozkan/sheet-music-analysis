import json, sys, zlib
from pathlib import Path
import numpy as np
import pikepdf
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage
from lxml import etree
HOME = Path(__file__).resolve().parent
SCR = Path("/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad")
DS = SCR / "ol/olimpic-1.0-scanned/samples"
OMR = Path("/home/kema/projects/sheet-music-plugin/spike/omr")
BO = OMR / "bench-olimpic"

def sid(name):
    _, w, p, q = name.split("-")
    return w, f"{p}-{q}"

def load(name):
    w, s = sid(name)
    return Image.open(DS / w / f"{s}.png").convert("L")

def interline(a):
    b = a < 128
    whites, blacks = [], []
    for x in range(0, a.shape[1], max(1, a.shape[1] // 120)):
        col = b[:, x]
        edges = np.flatnonzero(np.diff(col.astype(int)))
        runs = np.diff(edges)
        for k, r in enumerate(runs):
            (blacks if col[edges[k] + 1] else whites).append(int(r))
    whites = [w for w in whites if w >= 3]
    return float(np.bincount(whites).argmax() + np.bincount(blacks).argmax())

def staff_rows(a):
    il = interline(a)
    W = a.shape[1]
    strip = (a[:, int(W * 0.07) : int(W * 0.17)] < 128).mean(axis=1)
    peaks = [i for i in range(1, len(strip) - 1) if strip[i] >= strip[i - 1] and strip[i] > strip[i + 1] and strip[i] > 0.45]
    merged = []
    for p in peaks:
        if merged and p - merged[-1] < il * 0.5:
            if strip[p] > strip[merged[-1]]:
                merged[-1] = p
        else:
            merged.append(p)
    fives = []
    i = 0
    while i + 4 < len(merged):
        g = merged[i : i + 5]
        d = np.diff(g)
        if (abs(d - il) < 0.3 * il + 1).all():
            fives.append(g); i += 5
        else:
            i += 1
    return [float(r) for g in fives[-2:] for r in g] if len(fives) >= 2 else []

def to_pdf(im, path, dpi=300):
    W, H = im.size
    pdf = pikepdf.Pdf.new()
    xo = pikepdf.Stream(pdf, b"")
    xo.Type = pikepdf.Name.XObject; xo.Subtype = pikepdf.Name.Image
    xo.Width = W; xo.Height = H; xo.ColorSpace = pikepdf.Name.DeviceGray; xo.BitsPerComponent = 8
    xo.write(zlib.compress(im.tobytes()), filter=pikepdf.Name.FlateDecode)
    pw, ph = W * 72 / dpi, H * 72 / dpi
    page = pdf.add_blank_page(page_size=(pw, ph))
    page.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Im0=xo))
    page.Contents = pdf.make_stream(f"q {pw} 0 0 {ph} 0 0 cm /Im0 Do Q".encode())
    pdf.save(path)

def otsu(a):
    h = np.bincount(a.ravel(), minlength=256).astype(float)
    p = h / h.sum(); w = np.cumsum(p); m = np.cumsum(p * np.arange(256)); t = m[-1]
    s = (t * w - m) ** 2 / (w * (1 - w) + 1e-12)
    return int(s.argmax())

def binarize(im):
    a = np.asarray(im)
    return Image.fromarray(((a > otsu(a)) * 255).astype("uint8"))

def rescale(im, target):
    k = target / interline(np.asarray(im))
    return im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)

def deskew(im):
    k = max(1, im.width // 1500)
    small = im.resize((im.width // k, im.height // k), Image.BILINEAR)
    best, score = 0.0, -1
    for ang in np.arange(-1.5, 1.51, 0.05):
        r = 255 - np.asarray(small.rotate(float(ang), Image.BILINEAR, fillcolor=255), dtype=float)
        s_ = r.sum(axis=1).var()
        if s_ > score:
            best, score = float(ang), s_
    return (im.rotate(best, Image.BICUBIC, fillcolor=255) if abs(best) > 0.04 else im), best

def blank_edges(im):
    a = np.asarray(im).copy()
    lab, _ = ndimage.label(a < 128, structure=np.ones((3, 3)))
    edge = np.unique(np.concatenate([lab[0, :], lab[-1, :]]))
    a[np.isin(lab, edge[edge > 0])] = 255
    return Image.fromarray(a)

def blank_above(im):
    a = np.asarray(im).copy()
    rows = staff_rows(a)
    il = interline(a)
    if len(rows) < 10:
        return im, False
    top = rows[-10]
    a[: max(0, int(top - 4.5 * il))] = 255
    return Image.fromarray(a), True

def real_time(name):
    w, _ = sid(name)
    root = etree.parse(str(DS / w / "p1-s1.musicxml")).getroot()
    t = root.find(".//time")
    return (t.findtext("beats"), t.findtext("beat-type")) if t is not None else None

def truth_info(name):
    root = etree.parse(str(BO / "truth" / f"{name}.musicxml")).getroot()
    t = root.find(".//time")
    k = root.find(".//fifths")
    src = etree.parse(str(DS / sid(name)[0] / f"{sid(name)[1]}.musicxml")).getroot()
    printed = src.find(".//measure").find("attributes").find("time") is not None
    return (t.findtext("beats"), t.findtext("beat-type")), abs(int(k.text)) if k is not None else 0, printed

def insert_time(im, beats, beat_type, fifths):
    a = np.asarray(im)
    il = interline(a)
    rows = staff_rows(a)
    if len(rows) < 10:
        return None
    rows = rows[-10:]
    if abs((rows[4] - rows[0]) - 4 * il) > 1.5 * il or abs((rows[9] - rows[5]) - 4 * il) > 1.5 * il:
        return None
    dark = a < 128
    span = dark[int(rows[0]) : int(rows[-1]) + 1]
    fill = span.mean(axis=0)
    x0 = int(np.argmax(fill > 0.4))
    lo, hi = x0 + int((3.0 + fifths * 0.9) * il), x0 + int((6.5 + fifths * 1.25) * il)
    hi = min(hi, a.shape[1] - 1)
    cut = lo + int(np.argmin(fill[lo:hi]))
    width = int(3.2 * il)
    col = np.repeat(a[:, [cut]], width, axis=1)
    col[: int(rows[0]) - 2] = 255; col[int(rows[-1]) + 3 :] = 255
    out = Image.fromarray(np.concatenate([a[:, :cut], col, a[:, cut:]], axis=1))
    font = ImageFont.truetype(str(SCR / "Leipzig.ttf"), int(round(4 * il)))
    d = ImageDraw.Draw(out)
    cx = cut + width // 2
    for base in (rows[0], rows[5]):
        for txt, y in ((beats, base + il), (beat_type, base + 3 * il)):
            s = "".join(chr(0xE080 + int(c)) for c in txt)
            d.text((cx, y), s, fill=0, font=font, anchor="ms")
    return out
