from __future__ import annotations

import math
from dataclasses import dataclass


def _zeros(h: int, w: int, value: float = 0.0):
    return [[value for _ in range(w)] for _ in range(h)]


def _marker_pattern(size: int, marker_id: int):
    hs = size // 2
    m = [[0.0 for _ in range(size)] for _ in range(size)]
    for y in range(size):
        for x in range(size):
            dx, dy = x - hs, y - hs
            r = math.hypot(dx, dy)
            ring = 1.0 if int(r) % 2 == 0 else -1.0
            chk = 1.0 if ((x + y) & 1) == 0 else -1.0
            val = 0.55 * ring + 0.45 * chk
            # orientation-specific L-shape cue for robust corner identity
            if marker_id == 0 and (x < hs and y < hs):
                val += 0.9
            elif marker_id == 1 and (x >= hs and y < hs):
                val += 0.9
            elif marker_id == 2 and (x >= hs and y >= hs):
                val += 0.9
            elif marker_id == 3 and (x < hs and y >= hs):
                val += 0.9
            m[y][x] = val
    mx = max(abs(v) for row in m for v in row) or 1.0
    return [[v / mx for v in row] for row in m]


@dataclass
class TemplateSet:
    width: int
    height: int
    l1: int
    l2: int
    tm: list
    ta: list
    tb: list
    tw: list
    roi_quad: list
    sync_points: list
    sync_markers: list
    bit_boxes: list


def compose_template(width: int, height: int, bits: str) -> TemplateSet:
    if len(bits) != 64:
        raise ValueError("bitstream must be 64 bits")
    m = min(width, height)
    l1 = max(64, int(0.47 * m))
    l2 = max(11, int(0.06 * m) | 1)
    cx, cy = width // 2, height // 2
    half = l1 // 2
    x0, y0 = cx - half, cy - half

    tm = _zeros(height, width)
    ta = _zeros(height, width)
    tb = _zeros(height, width)

    # message template: 8x8 bit cells with local frequency carrier.
    grid = 8
    inner = int(l1 * 0.72)
    inner_x0 = x0 + (l1 - inner) // 2
    inner_y0 = y0 + (l1 - inner) // 2
    cell = max(6, inner // grid)
    bit_boxes = []
    idx = 0
    for gy in range(grid):
        for gx in range(grid):
            bx = inner_x0 + gx * cell
            by = inner_y0 + gy * cell
            bit = bits[idx]
            idx += 1
            sign = 1.0 if bit == "1" else -1.0
            bit_boxes.append(((inner_x0 - x0) + gx * cell, (inner_y0 - y0) + gy * cell, cell, cell))
            for yy in range(cell):
                for xx in range(cell):
                    x = bx + xx
                    y = by + yy
                    if 0 <= x < width and 0 <= y < height:
                        carrier = 0.6 * math.cos(2.0 * math.pi * xx / cell) + 0.4 * math.cos(2.0 * math.pi * yy / cell)
                        tm[y][x] += sign * carrier

    mx = max(abs(v) for row in tm for v in row) or 1.0
    tm = [[v / mx for v in row] for row in tm]

    s = l2
    offs = s // 2 + 3
    corners = [
        (x0 + offs, y0 + offs),
        (x0 + l1 - offs - 1, y0 + offs),
        (x0 + l1 - offs - 1, y0 + l1 - offs - 1),
        (x0 + offs, y0 + l1 - offs - 1),
    ]
    sync_markers = []
    for i, (px, py) in enumerate(corners):
        marker = _marker_pattern(s, i)
        sync_markers.append(marker)
        target = ta if i % 2 == 0 else tb
        for dy in range(-s // 2, s // 2 + 1):
            for dx in range(-s // 2, s // 2 + 1):
                x, y = px + dx, py + dy
                if 0 <= x < width and 0 <= y < height:
                    target[y][x] = marker[dy + s // 2][dx + s // 2]

    tw = _zeros(height, width)
    for y in range(height):
        for x in range(width):
            tw[y][x] = 0.72 * tm[y][x] + 0.16 * ta[y][x] + 0.12 * tb[y][x]

    roi_quad = [(x0, y0), (x0 + l1 - 1, y0), (x0 + l1 - 1, y0 + l1 - 1), (x0, y0 + l1 - 1)]
    return TemplateSet(width, height, l1, l2, tm, ta, tb, tw, roi_quad, corners, sync_markers, bit_boxes)
