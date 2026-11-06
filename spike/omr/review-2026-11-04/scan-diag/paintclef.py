from imgs import *
out = HOME / "items/clefpaint"; out.mkdir(parents=True, exist_ok=True); items = []
for n, staves in (("olimpic-6481218-p5-s1", [1]), ("olimpic-6481218-p7-s2", [0, 1])):
    a = np.asarray(load(n)).copy(); il = interline(a); rows = staff_rows(a); print(n, il, len(rows))
    im = Image.fromarray(a); d = ImageDraw.Draw(im); font = ImageFont.truetype(str(SCR / "Leipzig.ttf"), int(4 * il))
    fill = (a[int(rows[0]) : int(rows[-1])] < 128).mean(axis=0); x0 = int(np.argmax(fill > 0.4))
    arr = a.copy()
    for s in staves:
        top = rows[s * 5]; y0, y1 = int(top - il), int(top + 5 * il)
        xs, xe = x0 + int(0.3 * il), x0 + int(3.6 * il)
        clean = np.median(arr[y0:y1, xe + 2 : xe + 2 + int(il)], axis=1, keepdims=True).astype("uint8")
        arr[y0:y1, xs:xe] = clean
    im = Image.fromarray(arr); d = ImageDraw.Draw(im)
    for s in staves:
        d.text((x0 + int(0.6 * il), rows[s * 5 + 1]), chr(0xE062), fill=0, font=font, anchor="ls")
    p = out / f"{n}.pdf"; to_pdf(im, p); items.append({"name": n, "pdf": str(p), "truth": str(BO / "truth" / f"{n}.musicxml")})
    im.crop((0, 0, im.width // 3, im.height)).resize((700, im.height * 700 // (im.width // 3))).save(f"look7{staves[0]}.png")
(out / "items.json").write_text(json.dumps(items))
