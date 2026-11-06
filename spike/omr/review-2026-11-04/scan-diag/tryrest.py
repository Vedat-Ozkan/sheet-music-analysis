from imgs import *
from scipy.signal import fftconvolve
n = "olimpic-6986302-p1-s2"
im = load(n); a = np.asarray(im).copy(); il = interline(a); print("il", il, a.shape)
cx, cy = 334, 322
hw = int(0.8 * il); hh = int(1.3 * il)
t = (a[cy - hh : cy + hh, cx - hw : cx + hw] < 128).astype(float)
Image.fromarray(a[cy-2*hh:cy+2*hh,cx-2*hw:cx+2*hw]).save("rest_t.png")
b = (a < 128).astype(float)
c = fftconvolve(2 * b - 1, (2 * t - 1)[::-1, ::-1], mode="same")
peak = c.max(); found = []
for y, x in sorted(zip(*np.where(c > 0.72 * peak)), key=lambda p: -c[p]):
    if all(abs(x - u) > 2 * hw or abs(y - v) > 2 * hh for v, u in found):
        found.append((int(y), int(x)))
print(len(found), sorted(found, key=lambda p: p[1]))
out = Image.fromarray(a); 
arr = np.asarray(out).copy()
for y, x in found:
    y0, y1, x0, x1 = y - hh, y + hh, x - hw, x + hw
    left = arr[y0:y1, x0 - hw : x0].copy()
    arr[y0:y1, x0:x1] = np.median(left, axis=1, keepdims=True).astype("uint8")
out = Image.fromarray(arr)
d = ImageDraw.Draw(out); font = ImageFont.truetype(str(SCR / "Leipzig.ttf"), int(4 * il))
for y, x in found:
    d.text((x, y), chr(0xE4E5), fill=0, font=font, anchor="ms")
Path("items/restfix").mkdir(parents=True, exist_ok=True)
to_pdf(out, "items/restfix/" + n + ".pdf")
json.dump([{"name": n, "pdf": str(HOME / "items/restfix" / (n + ".pdf")), "truth": str(BO / "truth" / (n + ".musicxml"))}], open("items/restfix/items.json", "w"))
w, h = out.size; out.crop((0, 0, w // 2, h)).resize((900, h * 900 // (w // 2))).save("look5.png")
