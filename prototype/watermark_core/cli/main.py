from __future__ import annotations

import argparse
import json
import time

from watermark_core.detect import decode_watermark
from watermark_core.embed import embed_watermark, read_ppm, write_ppm
from watermark_core.payload.core import DEFAULT_DEVICE_ID, DEFAULT_T0, build_payload, to_bitstream
from watermark_core.template_gen import compose_template


def cmd_payload(args):
    payload = build_payload(args.unix_time or int(time.time()), args.t0, args.device_id)
    print(json.dumps({"device_id": payload.device_id, "time_slot": payload.time_slot, "crc16": payload.crc16, "bitstream": to_bitstream(payload)}, indent=2))


def cmd_template(args):
    bits = args.bits
    t = compose_template(args.width, args.height, bits)
    print(json.dumps({"width": t.width, "height": t.height, "l1": t.l1, "l2": t.l2, "sync_points": t.sync_points, "roi_quad": t.roi_quad}, indent=2))


def cmd_embed(args):
    src = read_ppm(args.input)
    payload = build_payload(args.unix_time or int(time.time()), args.t0, args.device_id)
    bits = to_bitstream(payload)
    t = compose_template(len(src[0]), len(src), bits)
    wm = embed_watermark(src, t.tw, alpha=args.alpha)
    write_ppm(args.output, wm)
    print(json.dumps({"output": args.output, "alpha": args.alpha, "bitstream": bits}, indent=2))


def cmd_detect(args):
    src = read_ppm(args.input)
    payload = build_payload(args.unix_time, args.t0, args.device_id)
    t = compose_template(len(src[0]), len(src), to_bitstream(payload))
    result = decode_watermark(src, t)
    print(json.dumps(result, indent=2))


def build_parser():
    p = argparse.ArgumentParser(description="watermark prototype CLI")
    sp = p.add_subparsers(required=True)

    p1 = sp.add_parser("payload")
    p1.add_argument("--device-id", type=lambda x: int(x, 0), default=DEFAULT_DEVICE_ID)
    p1.add_argument("--unix-time", type=int)
    p1.add_argument("--t0", type=int, default=DEFAULT_T0)
    p1.set_defaults(func=cmd_payload)

    p2 = sp.add_parser("template")
    p2.add_argument("--width", type=int, required=True)
    p2.add_argument("--height", type=int, required=True)
    p2.add_argument("--bits", required=True)
    p2.set_defaults(func=cmd_template)

    p3 = sp.add_parser("embed")
    p3.add_argument("--input", required=True)
    p3.add_argument("--output", required=True)
    p3.add_argument("--alpha", type=float, default=0.35)
    p3.add_argument("--device-id", type=lambda x: int(x, 0), default=DEFAULT_DEVICE_ID)
    p3.add_argument("--unix-time", type=int)
    p3.add_argument("--t0", type=int, default=DEFAULT_T0)
    p3.set_defaults(func=cmd_embed)

    p4 = sp.add_parser("detect")
    p4.add_argument("--input", required=True)
    p4.add_argument("--device-id", type=lambda x: int(x, 0), default=DEFAULT_DEVICE_ID)
    p4.add_argument("--unix-time", type=int, required=True)
    p4.add_argument("--t0", type=int, default=DEFAULT_T0)
    p4.set_defaults(func=cmd_detect)
    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
