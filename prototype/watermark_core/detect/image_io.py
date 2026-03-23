from __future__ import annotations

import struct
import zlib

from watermark_core.embed import read_ppm


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def _unfilter_scanlines(raw: bytes, width: int, height: int, bpp: int) -> bytes:
    stride = width * bpp
    out = bytearray(height * stride)
    src = 0
    dst = 0
    for _ in range(height):
        ftype = raw[src]
        src += 1
        cur = bytearray(raw[src:src + stride])
        src += stride
        prev_row = out[dst - stride:dst] if dst >= stride else b"\x00" * stride

        if ftype == 0:
            pass
        elif ftype == 1:  # Sub
            for i in range(stride):
                left = cur[i - bpp] if i >= bpp else 0
                cur[i] = (cur[i] + left) & 0xFF
        elif ftype == 2:  # Up
            for i in range(stride):
                cur[i] = (cur[i] + prev_row[i]) & 0xFF
        elif ftype == 3:  # Average
            for i in range(stride):
                left = cur[i - bpp] if i >= bpp else 0
                up = prev_row[i]
                cur[i] = (cur[i] + ((left + up) // 2)) & 0xFF
        elif ftype == 4:  # Paeth
            for i in range(stride):
                left = cur[i - bpp] if i >= bpp else 0
                up = prev_row[i]
                up_left = prev_row[i - bpp] if i >= bpp else 0
                cur[i] = (cur[i] + _paeth(left, up, up_left)) & 0xFF
        else:
            raise ValueError(f"Unsupported PNG filter type: {ftype}")

        out[dst:dst + stride] = cur
        dst += stride
    return bytes(out)


def read_png(path: str):
    with open(path, "rb") as f:
        data = f.read()

    sig = b"\x89PNG\r\n\x1a\n"
    if not data.startswith(sig):
        raise ValueError("Not a PNG file")

    pos = len(sig)
    width = height = None
    bit_depth = color_type = interlace = None
    idat = bytearray()

    while pos + 8 <= len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        ctype = data[pos + 4:pos + 8]
        chunk_data = data[pos + 8:pos + 8 + length]
        pos += 12 + length

        if ctype == b"IHDR":
            width, height, bit_depth, color_type, _comp, _flt, interlace = struct.unpack(">IIBBBBB", chunk_data)
        elif ctype == b"IDAT":
            idat.extend(chunk_data)
        elif ctype == b"IEND":
            break

    if width is None or height is None:
        raise ValueError("PNG missing IHDR")
    if bit_depth != 8:
        raise ValueError(f"Only 8-bit PNG supported, got bit_depth={bit_depth}")
    if interlace != 0:
        raise ValueError("Interlaced PNG not supported")
    if color_type not in (2, 6):
        raise ValueError(f"Only RGB/RGBA PNG supported, got color_type={color_type}")

    bpp = 3 if color_type == 2 else 4
    raw = zlib.decompress(bytes(idat))
    px = _unfilter_scanlines(raw, width, height, bpp)

    out = []
    i = 0
    for _y in range(height):
        row = []
        for _x in range(width):
            r = px[i]
            g = px[i + 1]
            b = px[i + 2]
            row.append([r, g, b])
            i += bpp
        out.append(row)
    return out


def read_image(path: str):
    lower = path.lower()
    if lower.endswith(".ppm"):
        return read_ppm(path)
    if lower.endswith(".png"):
        return read_png(path)
    raise ValueError("Unsupported image format. Supported: .ppm, .png")
