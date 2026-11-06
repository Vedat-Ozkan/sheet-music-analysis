from imgs import *
from scipy.signal import fftconvolve
n = "olimpic-6986302-p1-s2"
exec(open("tryrest.py").read().split("out = Image.fromarray(a);")[0].split("from scipy.signal import fftconvolve")[1].split('n = "olimpic-6986302-p1-s2"')[1])
treble = list(found)
cx, cy = 436, 482
t = (a[cy - hh : cy + hh, cx - hw : cx + hw] < 128).astype(float)
c = fftconvolve(2 * b - 1, (2 * t - 1)[::-1, ::-1], mode="same"); peak = c.max(); bass = []
for y, x in sorted(zip(*np.where(c > 0.8 * peak)), key=lambda p: -c[p]):
    if all(abs(x - u) > 2 * hw or abs(y - v) > 2 * hh for v, u in bass):
        bass.append((int(y), int(x)))
print(len(bass), sorted(bass, key=lambda p: p[1]))
arr = a.copy()
for y, x in treble + bass:
    y0, y1, x0, x1 = y - hh, y + hh, x - hw, x + hw
    arr[y0:y1, x0:x1] = np.median(arr[y0:y1, x0 - hw : x0 - 2], axis=1, keepdims=True).astype("uint8")
out = Image.fromarray(arr); d = ImageDraw.Draw(out); font = ImageFont.truetype(str(SCR / "Leipzig.ttf"), int(4 * il))
for y, x in treble:
    d.text((x, y), chr(0xE4E5), fill=0, font=font, anchor="ms")
rows = staff_rows(a); mid = rows[7]
for y, x in bass:
    d.text((x, mid), chr(0xE4E5), fill=0, font=font, anchor="ms")
Path("items/restfix").mkdir(parents=True, exist_ok=True)
to_pdf(out, "items/restfix/" + n + ".pdf")
json.dump([{"name": n, "pdf": str(HOME / "items/restfix" / (n + ".pdf")), "truth": str(BO / "truth" / (n + ".musicxml"))}], open("items/restfix/items.json", "w"))
w, h = out.size; out.crop((0, 0, w // 2, h)).resize((900, h * 900 // (w // 2))).save("look5.png")
