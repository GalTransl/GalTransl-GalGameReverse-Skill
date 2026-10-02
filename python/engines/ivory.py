# Provenance group: tools-a; sources (repository-relative):
#   SExtractor/tools/Ivory/OCB.py
# Symbols: generate_keys, process_data, parse_fags_sections, decode_ctex_from_raw, decode_ccod_from_raw
# Validation: tests/test_engines_tools_a.py, synthetic fixtures only.
# Rewritten standard-library bytes API; scope: script-section-cipher.
# SPDX-License-Identifier: GPL-3.0-only
# SExtractor tools/Ivory/OCB.py: generate_keys, process_data, parse_fags_sections.
# Commit 8d8d976fd04ae54e7c677705af937273d04a376a; provenance/tools-a.json.
# Rewrite: bounded bytes-only section parser and word cipher; caller supplies seed.
"""Ivory fAGS OCB section shell and pair-bit permutation; not a full VM."""
import struct


def crypt(data: bytes, seed: int, *, encrypt: bool = False) -> bytes:
    if not 0 <= seed <= 0xFFFFFFFF:
        raise ValueError("seed must be u32")
    out = bytearray(data)
    for off in range(0, len(data) // 4 * 4, 4):
        rotation = (off // 4) & 31
        key = ((seed << rotation) | (seed >> ((32 - rotation) & 31))) & 0xFFFFFFFF
        value = struct.unpack_from("<I", data, off)[0]
        if encrypt:
            value ^= key
        result = 0
        for pair in range(16):
            v = (value >> (pair * 2)) & 3
            k = (key >> (pair * 2)) & 3
            if (k ^ (k >> 1)) & 1:
                v = ((v & 1) << 1) | (v >> 1)
            result |= v << (pair * 2)
        if not encrypt:
            result ^= key
        struct.pack_into("<I", out, off, result)
    return bytes(out)


def sections(data: bytes) -> list[tuple[bytes, int, bytes]]:
    if len(data) < 8 or data[:4] != b"fAGS":
        raise ValueError("not fAGS")
    total = struct.unpack_from("<I", data, 4)[0]
    if not 8 <= total <= len(data):
        raise ValueError("invalid fAGS total")
    pos, out = 8, []
    while pos < total:
        if pos + 12 > total:
            raise ValueError("truncated section")
        size, header = struct.unpack_from("<II", data, pos + 4)
        if not 12 <= header <= size or pos + size > total:
            raise ValueError("invalid section extent")
        out.append((data[pos:pos + 4], header, data[pos:pos + size]))
        pos += size
    return out
