# Provenance group: tools-a; sources (repository-relative):
#   SExtractor/tools/Mirai/acv1_dat_tool.py
# Symbols: crc64_ecma_msb, parse_index, build_index, xor_payload_dwords, pack_entry
# Validation: tests/test_engines_tools_a.py, synthetic fixtures only.
# Rewritten standard-library bytes API; scope: keyed-script-container-roundtrip.
# SPDX-License-Identifier: GPL-3.0-only
# SExtractor tools/Mirai/acv1_dat_tool.py: crc64_ecma_msb, parse_index,
# xor_payload_dwords, pack_entry. Commit 8d8d976fd04ae54e7c677705af937273d04a376a.
# Rewrite: mandatory caller key, ACV1-only branch, bounded inflate; no IO.
"""Mirai ACV1 script container; legacy NonColor is an explicitly separate module."""
import struct
import zlib

COUNT_XOR = 0x8B6A4E5F


def title_key(title_bytes: bytes) -> int:
    """CRC64-ECMA polynomial, init/final all ones, MSB-first; return low32."""
    crc = 0xFFFFFFFFFFFFFFFF
    for b in title_bytes:
        crc ^= b << 56
        for _ in range(8):
            crc = ((crc << 1) ^ (0x42F0E1EBA9EA3693 if crc >> 63 else 0)) & 0xFFFFFFFFFFFFFFFF
    return (~crc) & 0xFFFFFFFF


def xor_dwords(data: bytes, key: int) -> bytes:
    if not 0 <= key <= 0xFFFFFFFF:
        raise ValueError("key must be u32")
    out = bytearray(data)
    for pos in range(0, len(data) // 4 * 4, 4):
        struct.pack_into("<I", out, pos, struct.unpack_from("<I", data, pos)[0] ^ key)
    return bytes(out)


def inflate(data: bytes, capacity: int, max_output: int) -> bytes:
    if not 0 <= capacity <= max_output:
        raise ValueError("ACV output capacity exceeds limit")
    obj = zlib.decompressobj()
    try:
        raw = obj.decompress(data, capacity + 1)
    except zlib.error as exc:
        raise ValueError("wrong ACV key or invalid zlib stream") from exc
    if len(raw) > capacity or not obj.eof or obj.unused_data or obj.unconsumed_tail:
        raise ValueError("ACV capacity/stream mismatch")
    return raw


def parse(data: bytes) -> tuple[list[dict], bytes]:
    if len(data) < 8 or data[:4] != b"ACV1":
        raise ValueError("Mirai reference requires ACV1; use NonColor for legacy")
    count = struct.unpack_from("<I", data, 4)[0] ^ COUNT_XOR
    end = 8 + count * 21
    if end > len(data):
        raise ValueError("truncated ACV1 index")
    entries = []
    for pos in range(8, end, 21):
        lo, hi, flag, off, size, cap = struct.unpack_from("<IIBIII", data, pos)
        off, size, cap, flag = off ^ lo ^ COUNT_XOR, size ^ lo, cap ^ lo, flag ^ (lo & 255)
        if off < end or off + size > len(data):
            raise ValueError("ACV1 payload outside data section")
        entries.append({"key_lo": lo, "key_hi": hi, "flag": flag, "offset": off,
                        "packed_size": size, "capacity": cap, "stored": data[off:off + size]})
    first = min((e["offset"] for e in entries), default=end)
    return entries, data[end:first]


def unpack(data: bytes, *, crc_low: int, max_output: int = 64 * 1024 * 1024) -> list[bytes]:
    entries, _ = parse(data)
    result, remaining = [], max_output
    for entry in entries:
        raw = inflate(xor_dwords(entry["stored"], crc_low ^ entry["key_lo"]), entry["capacity"], remaining)
        remaining -= len(raw)
        result.append(raw)
    return result


def rebuild(data: bytes, payloads: list[bytes], *, crc_low: int) -> bytes:
    entries, gap = parse(data)
    if len(payloads) != len(entries):
        raise ValueError("ACV1 entry order/count must remain fixed")
    out = bytearray(b"ACV1" + struct.pack("<I", len(entries) ^ COUNT_XOR))
    body = bytearray(gap)
    off = 8 + 21 * len(entries) + len(gap)
    for entry, raw in zip(entries, payloads):
        lo = entry["key_lo"]
        packed = xor_dwords(zlib.compress(raw, 9), crc_low ^ lo)
        out += struct.pack("<IIBIII", lo, entry["key_hi"], entry["flag"] ^ (lo & 255),
                           off ^ COUNT_XOR ^ lo, len(packed) ^ lo, max(len(raw), entry["capacity"]) ^ lo)
        body += packed
        off += len(packed)
    return bytes(out + body)
