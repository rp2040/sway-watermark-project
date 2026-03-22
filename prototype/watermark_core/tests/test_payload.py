from watermark_core.payload.core import DEFAULT_DEVICE_ID, DEFAULT_T0, build_payload, parse_bitstream, to_bitstream, unpack_payload


def test_payload_pack_unpack():
    p = build_payload(DEFAULT_T0 + 1234, DEFAULT_T0, DEFAULT_DEVICE_ID)
    bits = to_bitstream(p)
    assert len(bits) == 64
    parsed = parse_bitstream(bits)
    decoded = unpack_payload(parsed)
    assert decoded["device_id"] == DEFAULT_DEVICE_ID
    assert decoded["crc_ok"]
