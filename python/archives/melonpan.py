# Provenance group: tools-a; sources (repository-relative):
#   SExtractor/tools/Melonpan/ttd_pack.py
#   SExtractor/tools/Melonpan/xorff.py
# Symbols: parse_ttd, xor_file
# Validation: tests/test_engines_tools_a.py, synthetic fixtures only.
# Rewritten standard-library bytes API; scope: container-index-script-xor.
# SPDX-License-Identifier: GPL-3.0-only
# SExtractor tools/Melonpan/ttd_pack.py: parse_ttd; commit
# 8d8d976fd04ae54e7c677705af937273d04a376a. Strict WCW index rewrite; no IO.
"""Melonpan WCW TTD fixed-record width inferred from first payload offset."""
# Layer split: archives; format algorithms and original notices retained.
# Companion module: python/engines/melonpan.py
import struct


def index(data: bytes) -> list[dict]:
    if len(data) < 24 or data[:3] != b"WCW":
        raise ValueError("not WCW TTD")
    count = struct.unpack_from("<I", data, 4)[0]
    first = struct.unpack_from("<I", data, 16)[0]
    if not count or not 12 <= first <= len(data) or (first - 12) % count:
        raise ValueError("invalid TTD count/first offset")
    width = (first - 12) // count
    if width < 13:
        raise ValueError("invalid inferred TTD name width")
    out = []
    for pos in range(12, first, width):
        size, off, unknown = struct.unpack_from("<III", data, pos)
        if off < first or off + size > len(data):
            raise ValueError("TTD payload outside data region")
        name = data[pos + 12:pos + width].split(b"\0", 1)[0].decode("cp932")
        out.append({"name": name, "offset": off, "size": size, "unknown": unknown,
                    "name_width": width - 12, "stored": data[off:off + size]})
    return out
