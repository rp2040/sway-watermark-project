from __future__ import annotations

import json
import math

from watermark_core.detect import decode_watermark
from watermark_core.embed import write_ppm
from watermark_core.payload.core import DEFAULT_DEVICE_ID, DEFAULT_T0, build_payload, to_bitstream
from watermark_core.template_gen import compose_template


def build_background(width: int, height: int):
    img = []
    for y in range(height):
        row = []
        for x in range(width):
            r = int(40 + 180 * x / max(1, width - 1))
            g = int(30 + 170 * y / max(1, height - 1))
            b = int(20 + 90 * (math.sin((x + y) * 0.03) * 0.5 + 0.5))
            row.append([r, g, b])
        img.append(row)
    return img


def tw_u8_from_template(tpl):
    h, w = tpl.height, tpl.width
    out = [[0 for _ in range(w)] for _ in range(h)]
    for y in range(h):
        for x in range(w):
            v = tpl.tw[y][x]
            n = max(0.0, min(1.0, v * 0.5 + 0.5))
            out[y][x] = int(n * 255.0)
    return out


def apply_shader_like(img, tw_u8, alpha=0.03, use_screen_space=False):
    h, w = len(img), len(img[0])
    out = [[pix[:] for pix in row] for row in img]

    # 模拟多个 surface draw call（系统截图中常见）：每个 surface 的 v_texcoord 都是局部 0..1。
    surfaces = [
        (0, 0, w, h // 2),      # 顶半屏
        (0, h // 2, w, h - h // 2),  # 底半屏
    ]

    for sx, sy, sw, sh in surfaces:
        for y in range(sy, sy + sh):
            for x in range(sx, sx + sw):
                if use_screen_space:
                    u = x / max(1, w - 1)
                    v = y / max(1, h - 1)
                else:
                    # 旧逻辑：每个 surface 内独立使用局部坐标，导致模板在不同 surface 内重复
                    u = (x - sx) / max(1, sw - 1)
                    v = (y - sy) / max(1, sh - 1)

                tx = min(w - 1, max(0, int(round(u * (w - 1)))))
                ty = min(h - 1, max(0, int(round(v * (h - 1)))))
                tw = tw_u8[ty][tx] / 255.0 * 2.0 - 1.0

                c = out[y][x]
                luma = 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]
                jnd = 0.75 + 0.25 * (luma / 255.0)
                m = tw * alpha * jnd * 255.0
                out[y][x] = [int(max(0, min(255, ch + m))) for ch in c]
    return out


def run_case(use_screen_space: bool):
    width, height = 640, 360
    unix_time = DEFAULT_T0 + 300 * 321
    payload = build_payload(unix_time, DEFAULT_T0, DEFAULT_DEVICE_ID)
    bits = to_bitstream(payload)
    tpl = compose_template(width, height, bits)
    tw_u8 = tw_u8_from_template(tpl)

    bg = build_background(width, height)
    screenshot = apply_shader_like(bg, tw_u8, alpha=0.03, use_screen_space=use_screen_space)
    tag = "fixed_screen_space" if use_screen_space else "old_per_surface_uv"
    path = f"/tmp/{tag}.ppm"
    write_ppm(path, screenshot)
    result = decode_watermark(screenshot, tpl)
    ok = (
        result["device_id"] == payload.device_id
        and result["time_slot"] == payload.time_slot
        and result["crc_ok"] is True
    )
    return {
        "case": tag,
        "screenshot": path,
        "expected": {"device_id": payload.device_id, "time_slot": payload.time_slot},
        "detect": {
            "device_id": result["device_id"],
            "time_slot": result["time_slot"],
            "crc_ok": result["crc_ok"],
            "located_quad": result["located_quad"],
        },
        "pass": ok,
    }


def main():
    old_case = run_case(use_screen_space=False)
    new_case = run_case(use_screen_space=True)
    print(json.dumps({"old_case": old_case, "new_case": new_case}, indent=2))
    if not new_case["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
