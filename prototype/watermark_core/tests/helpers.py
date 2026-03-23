from __future__ import annotations

import math


def make_gradient_rgb(width: int, height: int):
    img = []
    for y in range(height):
        row = []
        for x in range(width):
            r = int(255 * x / max(1, width - 1))
            g = int(255 * y / max(1, height - 1))
            b = int((r + g) / 2)
            row.append([r, g, b])
        img.append(row)
    return img


def _solve_homography(src, dst):
    a, b = [], []
    for (x, y), (u, v) in zip(src, dst):
        a.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        b.append(u)
        a.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        b.append(v)
    for i in range(8):
        p = max(range(i, 8), key=lambda r: abs(a[r][i]))
        a[i], a[p] = a[p], a[i]
        b[i], b[p] = b[p], b[i]
        d = a[i][i] if abs(a[i][i]) > 1e-9 else 1e-9
        for j in range(i, 8):
            a[i][j] /= d
        b[i] /= d
        for r in range(8):
            if r == i:
                continue
            f = a[r][i]
            for j in range(i, 8):
                a[r][j] -= f * a[i][j]
            b[r] -= f * b[i]
    h = b + [1.0]
    return [[h[0], h[1], h[2]], [h[3], h[4], h[5]], [h[6], h[7], h[8]]]


def _apply_h(h, x, y):
    d = h[2][0] * x + h[2][1] * y + h[2][2]
    u = (h[0][0] * x + h[0][1] * y + h[0][2]) / d
    v = (h[1][0] * x + h[1][1] * y + h[1][2]) / d
    return u, v


def _bilinear(img, x, y):
    h, w = len(img), len(img[0])
    x = max(0.0, min(w - 1.001, x))
    y = max(0.0, min(h - 1.001, y))
    x0, y0 = int(x), int(y)
    x1, y1 = min(w - 1, x0 + 1), min(h - 1, y0 + 1)
    dx, dy = x - x0, y - y0
    out = [0, 0, 0]
    for c in range(3):
        v00 = img[y0][x0][c]
        v10 = img[y0][x1][c]
        v01 = img[y1][x0][c]
        v11 = img[y1][x1][c]
        out[c] = int((1 - dx) * (1 - dy) * v00 + dx * (1 - dy) * v10 + (1 - dx) * dy * v01 + dx * dy * v11)
    return out


def apply_perspective(img, strength: float = 0.08):
    h, w = len(img), len(img[0])
    src = [(0, 0), (w - 1, 0), (w - 1, h - 1), (0, h - 1)]
    dx = int(w * strength)
    dy = int(h * strength)
    dst = [(dx, dy), (w - 1 - dx // 2, 0), (w - 1, h - 1 - dy), (0, h - 1)]
    hmat = _solve_homography(dst, src)
    out = [[[0, 0, 0] for _ in range(w)] for _ in range(h)]
    for y in range(h):
        for x in range(w):
            sx, sy = _apply_h(hmat, x, y)
            out[y][x] = _bilinear(img, sx, sy)
    return out


def apply_jpeg_like(img, block: int = 8, q: int = 18):
    h, w = len(img), len(img[0])
    out = [[pix[:] for pix in row] for row in img]
    for by in range(0, h, block):
        for bx in range(0, w, block):
            for y in range(by, min(h, by + block)):
                for x in range(bx, min(w, bx + block)):
                    for c in range(3):
                        out[y][x][c] = max(0, min(255, int(round(out[y][x][c] / q) * q)))
    return out
