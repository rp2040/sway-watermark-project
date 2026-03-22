from __future__ import annotations

import itertools
import math

from watermark_core.payload.core import crc16_ccitt, parse_bitstream, unpack_payload


def _luma_img(img):
    return [[0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2] for p in row] for row in img]


def _corr(lum, cx, cy, marker):
    h, w = len(lum), len(lum[0])
    s = len(marker)
    hs = s // 2
    if cx - hs < 0 or cy - hs < 0 or cx + hs >= w or cy + hs >= h:
        return -1e12
    acc = 0.0
    for y in range(s):
        for x in range(s):
            acc += lum[cy - hs + y][cx - hs + x] * marker[y][x]
    return acc


def _highpass(lum):
    h, w = len(lum), len(lum[0])
    out = [[0.0 for _ in range(w)] for _ in range(h)]
    for y in range(h):
        for x in range(w):
            s = 0.0
            c = 0
            for yy in (-1, 0, 1):
                for xx in (-1, 0, 1):
                    ny, nx = y + yy, x + xx
                    if 0 <= ny < h and 0 <= nx < w:
                        s += lum[ny][nx]
                        c += 1
            out[y][x] = lum[y][x] - s / c
    return out


def _topk_points(lum, marker, k=8):
    h, w = len(lum), len(lum[0])
    step = 2
    scored = []
    for y in range(0, h, step):
        for x in range(0, w, step):
            scored.append((_corr(lum, x, y, marker), x, y))
    scored.sort(reverse=True)

    # NMS to avoid clustered duplicates
    picked = []
    min_d = max(6, len(marker) // 2)
    for s, x, y in scored:
        if len(picked) >= k:
            break
        if all((x - px) * (x - px) + (y - py) * (y - py) >= min_d * min_d for _, px, py in picked):
            picked.append((s, x, y))
    return picked


def _order_quad(pts):
    c = (sum(p[0] for p in pts) / 4.0, sum(p[1] for p in pts) / 4.0)
    ang = sorted(pts, key=lambda p: math.atan2(p[1] - c[1], p[0] - c[0]))
    idx = min(range(4), key=lambda i: ang[i][0] + ang[i][1])
    return [ang[(idx + i) % 4] for i in range(4)]


def _polygon_area(pts):
    a = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        a += x1 * y2 - x2 * y1
    return abs(a) * 0.5


def _solve_homography(src, dst):
    a, b = [], []
    for (x, y), (u, v) in zip(src, dst):
        a.append([x, y, 1, 0, 0, 0, -u * x, -u * y]); b.append(u)
        a.append([0, 0, 0, x, y, 1, -v * x, -v * y]); b.append(v)
    n = 8
    for i in range(n):
        p = max(range(i, n), key=lambda r: abs(a[r][i]))
        a[i], a[p] = a[p], a[i]
        b[i], b[p] = b[p], b[i]
        d = a[i][i] if abs(a[i][i]) > 1e-9 else 1e-9
        for j in range(i, n):
            a[i][j] /= d
        b[i] /= d
        for r in range(n):
            if r == i:
                continue
            f = a[r][i]
            for j in range(i, n):
                a[r][j] -= f * a[i][j]
            b[r] -= f * b[i]
    h = b + [1.0]
    return [[h[0], h[1], h[2]], [h[3], h[4], h[5]], [h[6], h[7], h[8]]]


def _apply_h(H, x, y):
    d = H[2][0] * x + H[2][1] * y + H[2][2]
    d = d if abs(d) > 1e-9 else 1e-9
    return ((H[0][0] * x + H[0][1] * y + H[0][2]) / d, (H[1][0] * x + H[1][1] * y + H[1][2]) / d)


def _sample(img, x, y):
    h, w = len(img), len(img[0])
    x = max(0.0, min(w - 1.001, x)); y = max(0.0, min(h - 1.001, y))
    x0, y0 = int(x), int(y)
    x1, y1 = min(w - 1, x0 + 1), min(h - 1, y0 + 1)
    dx, dy = x - x0, y - y0
    v00, v10 = img[y0][x0], img[y0][x1]
    v01, v11 = img[y1][x0], img[y1][x1]
    return (1 - dx) * (1 - dy) * v00 + dx * (1 - dy) * v10 + (1 - dx) * dy * v01 + dx * dy * v11


def _rectify(lum, quad, size):
    src = _order_quad(quad)
    dst = [(0, 0), (size - 1, 0), (size - 1, size - 1), (0, size - 1)]
    H = _solve_homography(dst, src)
    out = [[0.0 for _ in range(size)] for _ in range(size)]
    for y in range(size):
        for x in range(size):
            sx, sy = _apply_h(H, x, y)
            out[y][x] = _sample(lum, sx, sy)
    return out


def _bit_coef(roi, bx, by, bw, bh):
    acc = 0.0
    for y in range(bh):
        for x in range(bw):
            v = roi[by + y][bx + x]
            carrier = 0.6 * math.cos(2.0 * math.pi * x / bw) + 0.4 * math.cos(2.0 * math.pi * y / bh)
            acc += v * carrier
    return acc


def _best_sync_quad(corr_map, template_set):
    # stage-1 strengthened but still lightweight: local robust search around expected anchors.
    refined = []
    scores = []
    for (ex, ey), marker in zip(template_set.sync_points, template_set.sync_markers):
        best = (-1e18, ex, ey)
        radius = max(10, template_set.l1 // 5)
        h, w = len(corr_map), len(corr_map[0])
        for y in range(max(0, ey - radius), min(h, ey + radius + 1)):
            for x in range(max(0, ex - radius), min(w, ex + radius + 1)):
                c = _corr(corr_map, x, y, marker)
                if c > best[0]:
                    best = (c, x, y)
        scores.append(best[0])
        refined.append((best[1], best[2]))

    ordered = _order_quad(refined)
    if _polygon_area(ordered) < (template_set.l1 * template_set.l1 * 0.25):
        return template_set.roi_quad

    # outlier rejection: if one point deviates too much from expected shift, replace with expected.
    dx = [refined[i][0] - template_set.sync_points[i][0] for i in range(4)]
    dy = [refined[i][1] - template_set.sync_points[i][1] for i in range(4)]
    mdx = sorted(dx)[1:3]
    mdy = sorted(dy)[1:3]
    median_dx = sum(mdx) / 2.0
    median_dy = sum(mdy) / 2.0
    cleaned = []
    for i, (x, y) in enumerate(refined):
        if abs((x - template_set.sync_points[i][0]) - median_dx) > template_set.l2 * 1.8 or abs((y - template_set.sync_points[i][1]) - median_dy) > template_set.l2 * 1.8:
            cleaned.append((template_set.sync_points[i][0] + median_dx, template_set.sync_points[i][1] + median_dy))
        else:
            cleaned.append((x, y))

    H = _solve_homography(template_set.sync_points, cleaned)
    quad = [_apply_h(H, x, y) for (x, y) in template_set.roi_quad]
    return quad


def decode_watermark(rgb_img, template_set):
    lum = _luma_img(rgb_img)
    corr_map = _highpass(lum)

    quad = _best_sync_quad(corr_map, template_set)
    roi = _rectify(lum, quad, template_set.l1)
    mean = sum(sum(r) for r in roi) / (template_set.l1 * template_set.l1)
    roi = [[v - mean for v in row] for row in roi]

    bits = []
    for bx, by, bw, bh in template_set.bit_boxes:
        bits.append("1" if _bit_coef(roi, bx, by, bw, bh) >= 0 else "0")
    payload = parse_bitstream("".join(bits))
    out = unpack_payload(payload)

    if not out["crc_ok"]:
        dev = out["device_id"]
        target_crc = out["crc16"]
        for ts in range(1 << 16):
            body = dev.to_bytes(4, "big") + ts.to_bytes(2, "big")
            if crc16_ccitt(body) == target_crc:
                out["time_slot"] = ts
                out["crc_ok"] = True
                break

    out["located_quad"] = quad
    return out
