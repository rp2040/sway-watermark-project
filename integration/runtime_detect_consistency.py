from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass

from watermark_core.detect import decode_watermark
from watermark_core.embed import write_ppm
from watermark_core.payload.core import DEFAULT_DEVICE_ID, DEFAULT_T0, crc16_ccitt
from watermark_core.template_gen import compose_template


@dataclass(frozen=True)
class RuntimePayload:
    device_id: int
    time_slot: int
    crc16: int
    bits: str


def runtime_payload_bits(device_id: int, unix_time: int, t0: int = DEFAULT_T0) -> RuntimePayload:
    if unix_time < t0:
        raise ValueError("unix_time must be >= t0")
    time_slot = ((unix_time - t0) // 300) & 0xFFFF
    body = device_id.to_bytes(4, "big") + time_slot.to_bytes(2, "big")
    crc = crc16_ccitt(body)
    payload64 = ((device_id & 0xFFFFFFFF) << 32) | ((time_slot & 0xFFFF) << 16) | crc
    bits = "".join("1" if ((payload64 >> (63 - i)) & 1) else "0" for i in range(64))
    return RuntimePayload(device_id & 0xFFFFFFFF, time_slot, crc, bits)


def marker_value(size: int, marker_id: int, x: int, y: int) -> float:
    hs = size // 2
    dx = x - hs
    dy = y - hs
    r = math.sqrt(dx * dx + dy * dy)
    ring = 1.0 if int(r) % 2 == 0 else -1.0
    chk = 1.0 if ((x + y) & 1) == 0 else -1.0
    val = 0.55 * ring + 0.45 * chk
    if marker_id == 0 and x < hs and y < hs:
        val += 0.9
    elif marker_id == 1 and x >= hs and y < hs:
        val += 0.9
    elif marker_id == 2 and x >= hs and y >= hs:
        val += 0.9
    elif marker_id == 3 and x < hs and y >= hs:
        val += 0.9
    return val


def build_runtime_tw_u8(width: int, height: int, bits: str) -> list[list[int]]:
    n = width * height
    tm = [0.0] * n
    ta = [0.0] * n
    tb = [0.0] * n

    m = min(width, height)
    l1 = max(64, int(0.47 * m))
    l2 = max(11, int(0.06 * m) | 1)
    cx, cy = width // 2, height // 2
    half = l1 // 2
    x0, y0 = cx - half, cy - half

    inner = int(l1 * 0.72)
    inner_x0 = x0 + (l1 - inner) // 2
    inner_y0 = y0 + (l1 - inner) // 2
    cell = max(6, inner // 8)

    idx = 0
    for gy in range(8):
        for gx in range(8):
            sign = 1.0 if bits[idx] == "1" else -1.0
            idx += 1
            bx = inner_x0 + gx * cell
            by = inner_y0 + gy * cell
            for yy in range(cell):
                for xx in range(cell):
                    x = bx + xx
                    y = by + yy
                    if 0 <= x < width and 0 <= y < height:
                        carrier = 0.6 * math.cos(2.0 * math.pi * xx / cell) + 0.4 * math.cos(2.0 * math.pi * yy / cell)
                        tm[y * width + x] += sign * carrier

    mx = max(abs(v) for v in tm) or 1.0
    tm = [v / mx for v in tm]

    s = l2
    offs = s // 2 + 3
    corners = [
        (x0 + offs, y0 + offs),
        (x0 + l1 - offs - 1, y0 + offs),
        (x0 + l1 - offs - 1, y0 + l1 - offs - 1),
        (x0 + offs, y0 + l1 - offs - 1),
    ]

    for i, (cx0, cy0) in enumerate(corners):
        marker = [0.0] * (s * s)
        marker_max = 1e-6
        for yy in range(s):
            for xx in range(s):
                v = marker_value(s, i, xx, yy)
                marker[yy * s + xx] = v
                marker_max = max(marker_max, abs(v))
        for yy in range(s):
            for xx in range(s):
                v = marker[yy * s + xx] / marker_max
                x = cx0 + xx - s // 2
                y = cy0 + yy - s // 2
                if 0 <= x < width and 0 <= y < height:
                    p = y * width + x
                    if i % 2 == 0:
                        ta[p] = v
                    else:
                        tb[p] = v

    tw = [0] * n
    for i in range(n):
        v = 0.72 * tm[i] + 0.16 * ta[i] + 0.12 * tb[i]
        v = max(0.0, min(1.0, v * 0.5 + 0.5))
        tw[i] = int(v * 255.0)

    out = []
    for y in range(height):
        row = []
        for x in range(width):
            row.append(tw[y * width + x])
        out.append(row)
    return out


def to_rgb_img(gray: list[list[int]]) -> list[list[list[int]]]:
    return [[[v, v, v] for v in row] for row in gray]


def main():
    width, height = 320, 240
    unix_time = 1767225600 + 300 * 123
    payload = runtime_payload_bits(DEFAULT_DEVICE_ID, unix_time, DEFAULT_T0)

    tw_u8 = build_runtime_tw_u8(width, height, payload.bits)
    rgb = to_rgb_img(tw_u8)
    write_ppm("/tmp/runtime_tw_ideal.ppm", rgb)

    tpl = compose_template(width, height, payload.bits)
    result = decode_watermark(rgb, tpl)

    ok = (
        result["device_id"] == payload.device_id
        and result["time_slot"] == payload.time_slot
        and result["crc_ok"] is True
    )

    print(
        json.dumps(
            {
                "t0": DEFAULT_T0,
                "runtime_payload": asdict(payload),
                "detect_result": result,
                "pass": ok,
                "export_ppm": "/tmp/runtime_tw_ideal.ppm",
            },
            indent=2,
        )
    )
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
