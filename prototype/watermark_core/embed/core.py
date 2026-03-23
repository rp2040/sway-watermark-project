from __future__ import annotations


def read_ppm(path: str):
    with open(path, "rb") as f:
        head = f.readline().strip()
        if head not in {b"P6", b"P3"}:
            raise ValueError("Only PPM P6/P3 supported")
        def next_token():
            while True:
                line = f.readline()
                if not line:
                    return None
                line = line.strip()
                if line and not line.startswith(b"#"):
                    return line
        dims = next_token().split()
        w, h = int(dims[0]), int(dims[1])
        _ = int(next_token())
        if head == b"P6":
            data = f.read(w * h * 3)
            out = []
            i = 0
            for _y in range(h):
                row = []
                for _x in range(w):
                    row.append([data[i], data[i + 1], data[i + 2]])
                    i += 3
                out.append(row)
            return out
        nums = []
        for line in f:
            nums.extend(int(x) for x in line.strip().split())
        out, i = [], 0
        for _y in range(h):
            row = []
            for _x in range(w):
                row.append([nums[i], nums[i + 1], nums[i + 2]])
                i += 3
            out.append(row)
        return out


def write_ppm(path: str, img):
    h, w = len(img), len(img[0])
    with open(path, "wb") as f:
        f.write(f"P6\n{w} {h}\n255\n".encode())
        for row in img:
            for r, g, b in row:
                f.write(bytes((max(0, min(255, int(r))), max(0, min(255, int(g))), max(0, min(255, int(b))))))


def _luma(pixel):
    r, g, b = pixel
    return 0.299 * r + 0.587 * g + 0.114 * b


def _jnd_map(img):
    h, w = len(img), len(img[0])
    lum = [[_luma(img[y][x]) for x in range(w)] for y in range(h)]
    jnd = [[1.0 for _ in range(w)] for _ in range(h)]
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            local = 0.0
            for yy in (-1, 0, 1):
                for xx in (-1, 0, 1):
                    local += lum[y + yy][x + xx]
            bg = local / 9.0
            gx = abs(lum[y][x + 1] - lum[y][x - 1])
            gy = abs(lum[y + 1][x] - lum[y - 1][x])
            grad = (gx + gy) * 0.5
            jnd[y][x] = 0.6 + 0.4 * min(1.0, grad / 40.0) + 0.2 * min(1.0, abs(bg - 128.0) / 128.0)
    return lum, jnd


def embed_watermark(rgb_img, tw, alpha: float = 0.35):
    h, w = len(rgb_img), len(rgb_img[0])
    lum, jnd = _jnd_map(rgb_img)
    out = [[pix[:] for pix in row] for row in rgb_img]
    for y in range(h):
        for x in range(w):
            delta = tw[y][x] * jnd[y][x] * alpha * 60.0
            r, g, b = out[y][x]
            out[y][x] = [
                max(0, min(255, int(r + delta))),
                max(0, min(255, int(g + delta))),
                max(0, min(255, int(b + delta))),
            ]
    return out
