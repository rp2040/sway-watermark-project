from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

DEFAULT_DEVICE_ID = 0x1A2B3C4D
DEFAULT_T0 = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp())


@dataclass(frozen=True)
class Payload:
    device_id: int
    time_slot: int
    crc16: int


def crc16_ccitt(data: bytes, poly: int = 0x1021, init: int = 0xFFFF) -> int:
    crc = init
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ poly) & 0xFFFF if (crc & 0x8000) else (crc << 1) & 0xFFFF
    return crc


def _u16(n: int) -> int:
    return n & 0xFFFF


def pack_payload(device_id: int, time_slot: int) -> Payload:
    body = device_id.to_bytes(4, "big") + _u16(time_slot).to_bytes(2, "big")
    crc = crc16_ccitt(body)
    return Payload(device_id=device_id & 0xFFFFFFFF, time_slot=_u16(time_slot), crc16=crc)


def build_payload(unix_time: int, t0: int = DEFAULT_T0, device_id: int = DEFAULT_DEVICE_ID) -> Payload:
    if unix_time < t0:
        raise ValueError("unix_time must be >= T0")
    time_slot = (unix_time - t0) // 300
    return pack_payload(device_id, time_slot)


def to_bitstream(payload: Payload) -> str:
    return f"{payload.device_id:032b}{payload.time_slot:016b}{payload.crc16:016b}"


def parse_bitstream(bits: str) -> Payload:
    if len(bits) != 64 or any(b not in "01" for b in bits):
        raise ValueError("bitstream must be exactly 64 bits")
    device_id = int(bits[:32], 2)
    time_slot = int(bits[32:48], 2)
    crc16 = int(bits[48:], 2)
    return Payload(device_id, time_slot, crc16)


def unpack_payload(payload: Payload) -> dict:
    body = payload.device_id.to_bytes(4, "big") + payload.time_slot.to_bytes(2, "big")
    expected = crc16_ccitt(body)
    return {
        "device_id": payload.device_id,
        "time_slot": payload.time_slot,
        "crc16": payload.crc16,
        "crc_ok": expected == payload.crc16,
        "bitstream": to_bitstream(payload),
    }
