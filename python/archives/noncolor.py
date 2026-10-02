# Provenance group: tools-a; sources (repository-relative):
#   SExtractor/tools/NonColor/dat_tool.py
# Symbols: parse_header, build_header, xor_payload_dwords, unpack_entry
# Validation: tests/test_engines_tools_a.py, synthetic fixtures only.
# Rewritten standard-library bytes API; scope: keyed-legacy-script-container-roundtrip.
# SPDX-License-Identifier: GPL-3.0-only
# SExtractor tools/NonColor/dat_tool.py: parse_header, build_header, unpack_entry;
# commit 8d8d976fd04ae54e7c677705af937273d04a376a. Explicit legacy-only rewrite.
# Common DWORD/CRC/zlib primitives are local skill code, not upstream imports.
"""NonColor legacy ACV (NO ACV1 magic); preserves the variable header gap."""
import struct
import zlib
from .mirai import title_key, xor_dwords, inflate

COUNT_XOR = 0x26ACA46E


def parse(data: bytes) -> tuple[list[dict], bytes]:
    if len(data) < 4 or data[:4] == b"ACV1":
        raise ValueError("NonColor reference requires legacy ACV; use Mirai for ACV1")
    count = struct.unpack_from("<I", data)[0] ^ COUNT_XOR
    end = 4 + count * 21
    if end > len(data):
        raise ValueError("truncated legacy ACV index")
    entries = []
    for pos in range(4, end, 21):
        lo, hi, flag, off, size, cap = struct.unpack_from("<IIBIII", data, pos)
        off, size, cap, flag = off ^ lo, size ^ lo, cap ^ lo, flag ^ (lo & 255)
        if off < end or off + size > len(data):
            raise ValueError("legacy ACV payload outside data section")
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
        raise ValueError("legacy ACV entry count/order cannot change")
    out = bytearray(struct.pack("<I", len(entries) ^ COUNT_XOR))
    body = bytearray(gap)
    off = 4 + 21 * len(entries) + len(gap)
    for entry, raw in zip(entries, payloads):
        lo = entry["key_lo"]
        packed = xor_dwords(zlib.compress(raw, 9), crc_low ^ lo)
        out += struct.pack("<IIBIII", lo, entry["key_hi"], entry["flag"] ^ (lo & 255),
                           off ^ lo, len(packed) ^ lo, max(len(raw), entry["capacity"]) ^ lo)
        body += packed
        off += len(packed)
    return bytes(out + body)
