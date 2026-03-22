import pytest

from watermark_core.detect import decode_watermark
from watermark_core.embed import embed_watermark
from watermark_core.payload.core import DEFAULT_DEVICE_ID, DEFAULT_T0, build_payload, to_bitstream
from watermark_core.template_gen import compose_template
from watermark_core.tests.helpers import apply_jpeg_like, apply_perspective, make_gradient_rgb


def _run_once(attacked, alpha=0.45):
    unix_time = DEFAULT_T0 + 3600
    payload = build_payload(unix_time, DEFAULT_T0, DEFAULT_DEVICE_ID)
    bits = to_bitstream(payload)
    base = make_gradient_rgb(256, 256)
    ts = compose_template(256, 256, bits)
    wm = embed_watermark(base, ts.tw, alpha=alpha)
    src = attacked(wm)
    out = decode_watermark(src, ts)
    assert out["device_id"] == DEFAULT_DEVICE_ID
    assert out["time_slot"] == payload.time_slot
    assert out["crc_ok"]


def test_direct_recovery():
    _run_once(lambda img: img)


def test_perspective_light_recovery():
    # 轻度透视条件：strength <= 0.03 期望稳定恢复
    _run_once(lambda img: apply_perspective(img, strength=0.03))


@pytest.mark.xfail(reason="中等透视(0.05)仍存在失败样本，待进一步提升同步鲁棒性", strict=False)
def test_perspective_medium_recovery():
    _run_once(lambda img: apply_perspective(img, strength=0.05))


def test_jpeg_like_recovery():
    _run_once(lambda img: apply_jpeg_like(img, block=8, q=12), alpha=0.55)
