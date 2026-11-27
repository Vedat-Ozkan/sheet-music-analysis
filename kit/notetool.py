import argparse, os, re, sys
import numpy as np, cv2
from scipy.ndimage import median_filter, uniform_filter1d

sys.path.insert(0, os.path.dirname(__file__))
import note_rules

S = 40
PAGE_WIDTH = 2480
CLEF = {'G': 30, 'F': 18, 'C': 24, 'T': 22}
SURE, DOUBT, GUIDE, MARK = (220, 80, 0), (0, 0, 255), (255, 190, 90), (0, 150, 0)
FONT = cv2.FONT_HERSHEY_SIMPLEX
SHEARS = np.arange(-0.05, 0.051, 0.005)
WIDE_BOX = 'is much wider than most bars on this page: it may hold more than one bar, look in the picture for bar lines inside it'


def flat(g, k):
    k |= 1
    bg = cv2.blur(cv2.morphologyEx(g, cv2.MORPH_CLOSE, np.ones((k, k), np.uint8)), (k, k))
    return np.clip(g.astype(np.float32) / np.maximum(bg, 1), 0, 1)


def line_fives(ink):
    t = np.diff(np.pad(ink.T.astype(np.int8), ((0, 0), (1, 1))), axis=1)
    col, s = np.nonzero(t == 1)
    e = np.nonzero(t == -1)[1]
    mid, n = (s + e - 1) / 2, len(col) - 4
    m = np.stack([mid[i:n + i] for i in range(5)])
    d = np.diff(m, axis=0)
    sp = d.mean(0)
    thick = np.stack([(e - s)[i:n + i] for i in range(5)]).max(0)
    ok = (col[4:] == col[:n]) & (np.ptp(d, axis=0) <= np.maximum(1.5, 0.15 * sp)) & (sp >= 3) & (thick < 0.45 * sp)
    return col[:n][ok], m[:, ok], sp[ok]


def find_staves(ink, sp):
    W = ink.shape[1]
    col, m, d = line_fives(ink)
    keep = abs(d - sp) < 0.2 * sp
    col, m = col[keep], m[:, keep]
    tracks = []
    def miss(t, i):
        a, b = t[-1], t[max(0, len(t) - 80)]
        return abs(m[0, i] - m[0, a] - (m[0, a] - m[0, b]) / max(col[a] - col[b], 40) * (col[i] - col[a]))

    for i in range(len(col)):
        t = min(tracks, key=lambda t: miss(t, i), default=None)
        if t is None or miss(t, i) >= 0.4 * sp:
            tracks.append([i])
        elif col[i] > col[t[-1]]:
            t.append(i)
    most = max(len(t) for t in tracks)
    kept = []
    for t in sorted(tracks, key=len, reverse=True):
        x = col[t[len(t) // 2]]
        if len(t) >= 0.1 * most and all(abs(m[0, t[len(t) // 2]] - np.interp(x, col[k], m[0, k])) > 4.5 * sp for k in kept):
            kept.append(t)
    staves = []
    for t in kept:
        size = int(4 * sp) | 1
        L = np.stack([np.interp(np.arange(W), col[t], m[k, t]) for k in range(5)])
        L = uniform_filter1d(median_filter(L, size=(1, size), mode='nearest'), size, axis=1, mode='nearest')
        rows = np.clip(L.round().astype(int), 1, ink.shape[0] - 2)
        on = uniform_filter1d(np.stack([ink[rows + d, np.arange(W)] for d in (-1, 0, 1)]).max(0).mean(0), int(sp) | 1, mode='nearest') >= 0.8
        x0, x1 = col[t[0]], col[t[-1]]
        while x0 > 0 and on[x0 - 1]:
            x0 -= 1
        while x1 < W - 1 and on[x1 + 1]:
            x1 += 1
        staves.append(dict(x0=x0, x1=x1, L=L))
    return sorted(staves, key=lambda s: s['L'][2].mean())


def vfrac(ink, ya, yb, slope, yref):
    H, W = ink.shape
    Y = ya + (yb - ya) * np.linspace(0, 1, 40)[:, None]
    X = np.arange(W) - slope * (Y - yref)
    return ink[np.clip(Y.round().astype(int), 0, H - 1), np.clip(X.round().astype(int), 0, W - 1)].mean(0)


def bar_lines(wide, wider, blobs, staves, sp):
    top = staves[0]['L'][0]
    gaps = list(zip(staves, staves[1:]))

    def clear(y, shear):
        return vfrac(wider, y + 0.3 * sp, y + 1.2 * sp, shear, top) < 0.6

    tries = []
    for shear in SHEARS:
        ok = clear(top - 1.5 * sp, shear) & clear(staves[-1]['L'][4], shear)
        for s in staves:
            for ya, yb in ((s['L'][0], s['L'][4]), (s['L'][0], s['L'][0] + sp / 2), (s['L'][4] - sp / 2, s['L'][4])):
                ok &= vfrac(wide, ya, yb, shear, top) >= 0.9
            ok &= vfrac(blobs, s['L'][0], s['L'][4], shear, top) < 0.2
        tries.append((ok, [vfrac(wide, a['L'][4], b['L'][0], shear, top) for a, b in gaps],
                      [clear(a['L'][4], shear) & clear(b['L'][0] - 1.5 * sp, shear) for a, b in gaps]))
    found = sum(ok for ok, _, _ in tries) > 0
    for k in range(len(gaps)):
        joined = sum(ok & (inked[k] >= 0.9) for ok, inked, _ in tries) > 0
        for ok, inked, apart in tries:
            ok &= inked[k] >= 0.75 if joined.sum() > found.sum() / 2 else apart[k]
    found = sum(ok for ok, _, _ in tries) > 0
    xs = [x for x in np.nonzero(found)[0] if staves[0]['x0'] - sp <= x <= staves[0]['x1'] + sp]
    groups = []
    for x in xs:
        if groups and x - groups[-1][-1] <= 1.2 * sp:
            groups[-1].append(x)
        else:
            groups.append([x])
    return [int(np.mean(g)) for g in groups]


def analyse(path):
    g = cv2.imread(path, 0)
    if g is None:
        raise SystemExit(f'cannot read image {path}')
    spacings = line_fives(flat(g, g.shape[1] // 20) < 0.7)[2]
    if not len(spacings):
        raise SystemExit(f'no staff lines found in {path}')
    sp = np.bincount(np.round(spacings * 2).astype(int)).argmax() / 2
    z = int(np.ceil(12 / sp))
    ink = (flat(cv2.resize(g, None, fx=z, fy=z, interpolation=cv2.INTER_CUBIC), int(4 * sp * z)) < 0.7).astype(np.uint8)
    staves = find_staves(ink, sp * z)
    k = round(sp * z / 12)
    wide = cv2.dilate(ink, np.ones((1, 2 * k + 1), np.uint8))
    wider = cv2.dilate(ink, np.ones((1, 6 * k + 1), np.uint8))
    b = round(0.8 * sp * z)
    blobs = cv2.erode(cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((b, 1), np.uint8)), np.ones((1, b), np.uint8))
    blobs = cv2.dilate(blobs, np.ones((1, 2 * (b // 2) + 1), np.uint8))
    systems = [[staves[0]]]
    for a, b in zip(staves, staves[1:]):
        lo, hi = max(min(a['x0'], b['x0']) - int(2 * sp * z), 0), min(a['x1'], b['x1']) + k
        joined = max(vfrac(wide, a['L'][4], b['L'][0], sh, a['L'][4])[lo:hi].max() for sh in SHEARS) >= 0.9
        systems[-1].append(b) if joined else systems.append([b])
    out, H = [], g.shape[0]
    for st in systems:
        lines = [x // z for x in bar_lines(wide, wider, blobs, st, sp * z)]
        for s in st:
            s.update(x0=s['x0'] // z, x1=s['x1'] // z, L=(s['L'][:, ::z] + 0.5) / z - 0.5)
        x0, x1 = min(s['x0'] for s in st), max(s['x1'] for s in st)
        edges = [x0] + [x for x in lines if x0 + 2 * sp < x < x1 - 2 * sp] + [x1]
        if len(edges) > 2 and x1 - edges[-2] < 6 * sp and not any(x >= x1 - 2 * sp for x in lines):
            edges.pop()
        out.append(dict(staves=st, x0=x0, x1=x1, lines=lines, bars=list(zip(edges, edges[1:])),
                        sp=np.mean([(s['L'][4] - s['L'][0])[x0:x1].mean() / 4 for s in st])))
    for i, sy in enumerate(out):
        mid = (sy['x0'] + sy['x1']) // 2
        top, bottom = sy['staves'][0]['L'][0, mid], sy['staves'][-1]['L'][4, mid]
        above = 0.6 * (top - out[i - 1]['staves'][-1]['L'][4, mid]) if i else top
        below = 0.6 * (out[i + 1]['staves'][0]['L'][0, mid] - bottom) if i + 1 < len(out) else H - bottom
        sy['pad'] = [min(9, d / sy['sp']) for d in (above, below)]
    mark_wide_boxes(out)
    return flat(g, int(4 * sp)), out


def mark_wide_boxes(systems):
    widths = [[(q - p) / sy['sp'] - (4 if n == 0 else 0) for n, (p, q) in enumerate(sy['bars'])] for sy in systems]
    full = [w for ws in widths for w in ws if w > 6]
    for sy, ws in zip(systems, widths):
        sy['wide'] = [n for n, w in enumerate(ws, 1) if len(full) > 2 and w > 1.7 * np.median(full)]


def layout(a):
    img, systems = analyse(a.image)
    H, W = img.shape
    f = 1600 / W
    ov = cv2.cvtColor(cv2.resize((img * 255).astype(np.uint8), None, fx=f, fy=f, interpolation=cv2.INTER_AREA if f < 1 else cv2.INTER_CUBIC), cv2.COLOR_GRAY2BGR)
    print(f'image {W}x{H}: {len(systems)} systems')
    for i, sy in enumerate(systems, 1):
        st = sy['staves']
        print(f"system {i}: x {sy['x0']}-{sy['x1']}, {len(st)} staves, staff spacing {sy['sp']:.1f} px, skew {100 * (st[0]['L'][2, sy['x1']] - st[0]['L'][2, sy['x0']]) / (sy['x1'] - sy['x0']):+.1f}%")
        for j, s in enumerate(st, 1):
            ya, yb = s['L'][:, s['x0']], s['L'][:, s['x1']]
            print(f'  staff {i}.{j}: rows {ya[0]:.0f}-{ya[4]:.0f} at the left end, {yb[0]:.0f}-{yb[4]:.0f} at the right end')
            xs = np.arange(s['x0'], s['x1'], 4)
            for k in (0, 4):
                cv2.polylines(ov, [np.stack([xs * f, s['L'][k, xs] * f], 1).astype(np.int32)], False, SURE, 2)
            cv2.putText(ov, f'{i}.{j}', (max(0, int(s['x0'] * f) - 50), int(ya[2] * f) + 6), FONT, 0.6, SURE, 2)
        print(f"  bar lines ({len(sy['lines'])}): {' '.join(map(str, sy['lines']))}")
        print(f"  bars ({len(sy['bars'])}): " + ', '.join(f'{n}: {p}-{q}' for n, (p, q) in enumerate(sy['bars'], 1)))
        for n in sy['wide']:
            print(f"  bar {n} {WIDE_BOX}")
        ya, yb = int(st[0]['L'][0].min() * f) - 12, int(st[-1]['L'][4].max() * f) + 12
        for x in sy['lines']:
            cv2.line(ov, (int(x * f), ya), (int(x * f), yb), DOUBT, 2)
        for n, (p, q) in enumerate(sy['bars'], 1):
            cv2.putText(ov, f'{n} wide?' if n in sy['wide'] else str(n), (int((p + q) / 2 * f) - 6, ya - 4), FONT, 0.6, DOUBT, 2)
    cv2.imwrite(a.out, ov)


def rectify(img, sy, scale, xa, xb):
    st, k = sy['staves'], scale / sy['sp']
    xs = xa + np.arange(int((xb - xa) * k)) / k
    cols = np.clip(xs.round().astype(int), 0, img.shape[1] - 1)
    T, B = [s['L'][0, cols] for s in st], [s['L'][4, cols] for s in st]
    tops = [sy['pad'][0] * scale + (t.mean() - T[0].mean()) * k for t in T]
    src = [T[0] - sy['pad'][0] * (B[0] - T[0]) / 4] + [v for tb in zip(T, B) for v in tb] + [B[-1] + sy['pad'][1] * (B[-1] - T[-1]) / 4]
    dst = [0] + [v for t in tops for v in (t, t + 4 * scale)] + [tops[-1] + (4 + sy['pad'][1]) * scale]
    pos = np.interp(np.arange(int(dst[-1])), dst, np.arange(len(dst)))
    i = np.minimum(pos.astype(int), len(dst) - 2)
    src = np.array(src)
    my = src[i] + (src[i + 1] - src[i]) * (pos - i)[:, None]
    mx = np.repeat(xs[None], len(my), 0)
    R = cv2.remap(img, mx.astype(np.float32), my.astype(np.float32), cv2.INTER_CUBIC, borderValue=1)
    return np.clip(R, 0, 1), xs, my, [t + 4 * scale for t in tops]


def ledger_steps(ink, cx, out, edge, sign):
    rows = (edge + sign * np.arange(8, 10 * out + 7)).astype(int)
    rows = rows[(rows >= 0) & (rows < len(ink))]
    sides = []
    for side in (ink[rows, cx - 20:cx - 16], ink[rows, cx + 17:cx + 21]):
        on = np.diff(np.pad(side.any(1), 1).astype(np.int8))
        sides.append([8 + (p + q - 1) / 2 for p, q in zip(np.nonzero(on == 1)[0], np.nonzero(on == -1)[0]) if q - p <= 7])
    lines = [l for l in sides[0] if any(abs(l - r) <= 4 for r in sides[1])]
    if lines:
        return 2 * len(lines) + (10 * out - lines[-1]) / 10


def find_heads(R, bottoms):
    s = S // 2
    small = cv2.resize(R, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    ink = (small < 0.65).astype(np.uint8)
    core = cv2.erode(ink, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 11)))
    stems = cv2.morphologyEx((small < 0.85).astype(np.uint8), cv2.MORPH_OPEN, np.ones((30, 1), np.uint8))
    n, lab, stat, _ = cv2.connectedComponentsWithStats(core)
    heads, usual = [], np.median([a for _, _, w, h, a in stat[1:] if 8 <= h <= 20 and w <= 24] or [0])
    for k, (x, y, w, h, area) in enumerate(stat[1:], 1):
        if h < 8 or w > 44 or w > 24 and h < 18 or h <= 20 and area < 0.7 * usual:
            continue
        blob = lab[y:y + h, x:x + w] == k
        for band in np.array_split(np.arange(w), 1 if w <= 24 else 2):
            part = blob[:, band]
            inked = np.nonzero(part.any(1))[0]
            for rows in np.array_split(inked, max(1, round((len(inked) - 12) / 20) + 1)):
                ys, xs = np.nonzero(part[rows])
                cx, cy = x + band[0] + xs.mean(), y + rows[0] + ys.mean()
                if stems[max(0, int(cy - 12)):int(cy + 12), max(0, int(cx - 18)):int(cx + 18)].any():
                    j = int(np.argmin([abs(b / 2 - 2 * s - cy) for b in bottoms]))
                    step = (bottoms[j] / 2 - cy) / (s / 2)
                    out = step - 8 if step > 4 else -step
                    seen = ledger_steps(ink, int(cx), out, bottoms[j] / 2 - (4 * s if step > 4 else 0), -1 if step > 4 else 1) if out > 1.5 else None
                    counted = seen is not None and abs(seen - out) < 1.3
                    out = seen if counted else out
                    heads.append(dict(x=2 * cx, y=2 * cy, staff=j, step=8 + out if step > 4 else -out, loose=out > 1.5 and not counted))
    for h in heads:
        r = round(h['step'])
        near = any(o is not h and np.hypot(o['x'] - h['x'], o['y'] - h['y']) < 1.3 * S for o in heads)
        h['doubt'] = ' '.join(w for w, bad in (('off', abs(h['step'] - r) > 0.3), ('ledger', h['loose']), ('touching', near)) if bad)
    return sorted(heads, key=lambda h: h['x'])


def pitch(step, clef):
    n = CLEF[clef] + step
    return f"{'CDEFGAB'[n % 7]}{n // 7}"


def overlay(R, draw):
    base = cv2.cvtColor((R * 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)
    top = base.copy()
    draw(top)
    return np.where(R[..., None] > 0.6, top, base)


def rulers(crop, xs, ys):
    h, w = crop.shape[:2]
    out = np.full((h + 30, w + 60, 3), 255, np.uint8)
    out[30:, 60:] = crop
    step = next(v for v in (10, 20, 50, 100, 200, 500, 1000) if v * w / (xs[-1] - xs[0]) > 110)
    for m in range(int(xs[0] // step + 1) * step, int(xs[-1]), step):
        u = 60 + int(np.interp(m, xs, np.arange(w)))
        cv2.line(out, (u, 22), (u, 30), 0, 2)
        cv2.putText(out, f'x{m}', (u - 20, 18), FONT, 0.5, 0, 1)
    for m in range(int(ys[0] // step + 1) * step, int(ys[-1]), step):
        v = 30 + int(np.interp(m, ys, np.arange(h)))
        cv2.line(out, (52, v), (60, v), 0, 2)
        cv2.putText(out, f'y{m}', (2, v + 5), FONT, 0.45, 0, 1)
    return out


def label(a):
    img, systems = analyse(a.image)
    clefs = a.clefs.split(',')
    changes = sorted((int(i), int(j), int(x), c) for i, j, x, c in re.findall(r'(\d+)\.(\d+)@(\d+)=(\w+)', a.change))
    if len(changes) != len(a.change.split(',')) - (not a.change) or ({c for *_, c in changes} | set(clefs)) - set(CLEF):
        raise SystemExit('clefs are G F C T; write changes as SYSTEM.STAFF@X=CLEF, for example 2.2@1450=G')
    os.makedirs(a.outdir, exist_ok=True)
    for i, sy in enumerate(systems, 1):
        st = sy['staves']
        if len(st) != len(clefs):
            print(f'system {i}: SKIPPED, the tool traced {len(st)} staves here but --clefs names {len(clefs)}; no crops or labels for this system')
            continue
        pad = int(sy['sp'])
        R, xs, my, bottoms = rectify(img, sy, S, max(0, sy['x0'] - pad), min(img.shape[1], sy['x1'] + pad))
        heads = find_heads(R, bottoms)
        marks = [[(0, clefs[j])] + [(x, c) for ci, cj, x, c in changes if (ci, cj) == (i, j + 1)] for j in range(len(st))]
        clefs = [m[-1][1] for m in marks]
        for h in heads:
            h['src'] = int(xs[min(int(h['x']), len(xs) - 1)])
            h['name'] = pitch(round(h['step']), [c for x, c in marks[h['staff']] if x <= h['src']][-1])

        def draw(im):
            for j, b in enumerate(bottoms):
                reach = min(6, int(sy['pad'][0]) if j == 0 else int((b - 4 * S - bottoms[j - 1]) / S / 2))
                below = min(6, int(sy['pad'][1]) if j == len(st) - 1 else int((bottoms[j + 1] - 4 * S - b) / S / 2))
                for n in [-n for n in range(1, reach + 1)] + list(range(5, 5 + below)):
                    cv2.line(im, (0, int(b - 4 * S + n * S)), (im.shape[1], int(b - 4 * S + n * S)), GUIDE, 1)
                for x, c in marks[j]:
                    u = int(np.searchsorted(xs, x))
                    cv2.putText(im, f'{i}.{j + 1} clef {c}', (u + 4, int(b - 4.4 * S)), FONT, 0.6, MARK, 2)
            for n, (p, q) in enumerate(sy['bars'], 1):
                cv2.putText(im, f'bar {n} wide?' if n in sy['wide'] else f'bar {n}', (int(np.searchsorted(xs, p)) + 8, 24), FONT, 0.8, MARK, 2)

        full = overlay(R, draw)
        for h in heads:
            at = (int(h['x'] + 0.4 * S), int(h['y'] - 0.45 * S))
            cv2.putText(full, h['name'], at, FONT, 0.65, (255, 255, 255), 5)
            cv2.putText(full, h['name'], at, FONT, 0.65, DOUBT if h['doubt'] else SURE, 2)
        print(f"system {i}: " + ', '.join(f"staff {i}.{j + 1} clef " + ' then '.join(c if not x else f'{c} from x={x}' for x, c in m) for j, m in enumerate(marks)))
        wide, parts = 1700 * sy['sp'] / S, []
        for n, (p, q) in enumerate(sy['bars'], 1):
            cuts = np.linspace(p, q, int(np.ceil((q - p) / wide)) + 1)
            parts += [(n, c0, c1) for c0, c1 in zip(cuts, cuts[1:])]
        groups = [[parts[0]]]
        for part in parts[1:]:
            if part[2] - groups[-1][0][1] <= wide:
                groups[-1].append(part)
            else:
                groups.append([part])
        for k, g in enumerate(groups, 1):
            u0, u1 = (int(np.searchsorted(xs, x)) for x in (g[0][1] - pad, g[-1][2] + pad))
            for j0 in range(0, len(st), 2):
                j1 = min(j0 + 2, len(st)) - 1
                v0 = 0 if j0 == 0 else int((bottoms[j0 - 1] + bottoms[j0] - 4 * S) / 2 - 2 * S)
                v1 = len(R) if j1 == len(st) - 1 else int((bottoms[j1] + bottoms[j1 + 1] - 4 * S) / 2 + 2 * S)
                name = f'{a.outdir}/s{i}_{k}' + (f'_staves{j0 + 1}-{j1 + 1}.png' if len(st) > 2 else '.png')
                cv2.imwrite(name, rulers(full[v0:v1, u0:u1], xs[u0:u1], my[v0:v1, u0]))
                print(f' crop {name}: bars {g[0][0]}-{g[-1][0]}, x {int(g[0][1])}-{int(g[-1][2])}, staves {i}.{j0 + 1}-{i}.{j1 + 1}')
        for n, (p, q) in enumerate(sy['bars'], 1):
            print(f' bar {n} (x {p}-{q})' + (f' {WIDE_BOX}' if n in sy['wide'] else ''))
            for j in range(len(st)):
                chords = []
                for h in [h for h in heads if h['staff'] == j and p <= h['src'] < q]:
                    if chords and h['x'] - chords[-1][0]['x'] < 1.4 * S:
                        chords[-1].append(h)
                    else:
                        chords.append([h])
                words = [f"x{c[0]['src']} " + '+'.join(h['name'] + (f"?({h['doubt']})" if h['doubt'] else '') for h in sorted(c, key=lambda h: -h['y'])) for c in chords]
                print(f'  {i}.{j + 1}: ' + ' | '.join(words))


def zoom(a):
    img, systems = analyse(a.image)
    xm, ym = (a.x0 + a.x1) // 2, (a.y0 + a.y1) / 2
    sy = min(systems, key=lambda sy: min(abs(s['L'][2, xm] - ym) for s in sy['staves']))
    j = int(np.argmin([abs(s['L'][2, xm] - ym) for s in sy['staves']]))
    scale = min(100, int(1400 * sy['sp'] / max(a.x1 - a.x0, a.y1 - a.y0)))
    R, xs, my, bottoms = rectify(img, sy, scale, a.x0, a.x1)
    v0, v1 = (int(np.interp(y, my[:, 0], np.arange(len(my)))) for y in (a.y0, a.y1))
    rows = [(n, int(bottoms[j] - n * scale / 2)) for n in range(-16, 26, 2) if v0 + 10 < bottoms[j] - n * scale / 2 < v1 - 10]

    def draw(im):
        for n, y in rows:
            cv2.line(im, (0, y), (im.shape[1], y), MARK if 0 <= n <= 8 else GUIDE, 1)

    out = rulers(overlay(R, draw)[v0:v1], xs, my[v0:v1, 0])
    out = np.hstack([out, np.full((len(out), 110, 3), 255, np.uint8)])
    for n, y in rows:
        text = pitch(n, a.clef) if a.clef else f'line {n // 2 + 1}' if 0 <= n <= 8 else f'ledger {(n - 8) // 2 if n > 0 else n // 2:+d}'
        cv2.putText(out, text, (out.shape[1] - 104, y - v0 + 36), FONT, 0.6, MARK if 0 <= n <= 8 else DOUBT, 2)
    cv2.imwrite(a.out, out)
    print(f'{a.out}: guide lines belong to staff {next(k for k, other in enumerate(systems, 1) if other is sy)}.{j + 1}')


def check(a):
    text = open(a.file).read()
    found = note_rules.problems(text)
    for problem in found:
        print(problem)
    lines = text.splitlines()
    head = re.fullmatch(r'N1 page=[1-9]\d* div=([1-9]\d*) ts=([1-9]\d*)/([1-9]\d*)\?? ks=(0|[1-7][sf])', lines[0].strip()) if lines else None
    notes = 0
    if head:
        div = int(head[1])

        def key(ks):
            return {} if ks == '0' else {l: '#b'[ks[1] == 'f'] for l in ('FCGDAEB' if ks[1] == 's' else 'BEADGCF')[:int(ks[0])]}

        full, opening, bar = div * 4 * int(head[2]) // int(head[3]), head[4], None
        keys, sig = {}, key(opening)
        for line in filter(None, map(str.strip, lines[1:])):
            if stated := note_rules.staff_key(line):
                keys[stated[0]] = key(stated[1])
                continue
            m = re.fullmatch(r'(m\d+) len=(\d+)((?: (?:ts=[1-9]\d*/[1-9]\d*|ks=(?:0|[1-7][sf])|rep=\S+|ending=\S+))*)', line)
            if m:
                bar, length = m[1], int(m[2])
                for kind, value in re.findall(r'(ts|ks)=(\S+)', m[3]):
                    if kind == 'ks':
                        sig = key(value)
                    else:
                        full = div * 4 * int(value.split('/')[0]) // int(value.split('/')[1])
                if length != full:
                    print(f'{bar}: NOTE len={length} but a full bar is {full}; only a pickup, a bar split by a repeat sign or a bar split by the page turn may be shorter')
                continue
            m = re.fullmatch(r'(\d+\.\d+):(.*)', line)
            if not m or bar is None:
                continue
            staff_sig = keys.get(int(m[1].split('.')[0]), sig)
            for t in m[2].split():
                for letter, acc, octave in re.findall(r'([A-G])(##?|bb?)?(\d)', t):
                    if acc != staff_sig.get(letter, ''):
                        print(f'{bar} {m[1]}: {letter}{acc}{octave} departs from the key signature: find its printed accidental')
                        notes += 1
    print(f'{len(found)} errors, {notes} pitches outside the key signature')


def pages(a):
    import pypdfium2
    os.makedirs(a.outdir, exist_ok=True)
    pdf = pypdfium2.PdfDocument(a.file)
    for number, page in enumerate(pdf, 1):
        page.render(scale=PAGE_WIDTH / page.get_width()).to_pil().convert('RGB').save(os.path.join(a.outdir, f'page{number}.png'))
    print(f'{len(pdf)} pages written to {a.outdir}')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name, run, args in (('layout', layout, ['image', 'out']), ('label', label, ['image', 'outdir']),
                            ('zoom', zoom, ['image', 'x0', 'x1', 'y0', 'y1', 'out']), ('check', check, ['file']),
                            ('pages', pages, ['file', 'outdir'])):
        p = sub.add_parser(name)
        for arg in args:
            p.add_argument(arg, type=int if arg[0] in 'xy' else str)
        p.set_defaults(run=run)
    sub.choices['label'].add_argument('--clefs', required=True, help='one clef per staff of a system, top to bottom: G F C T, e.g. G,F')
    sub.choices['label'].add_argument('--change', default='', help='clef changes SYSTEM.STAFF@X=CLEF separated by commas, e.g. 2.2@1450=G,3.2@900=F')
    sub.choices['zoom'].add_argument('--clef', choices=list(CLEF))
    a = ap.parse_args()
    a.run(a)
