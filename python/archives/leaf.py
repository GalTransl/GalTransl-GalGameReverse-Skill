# Provenance group: tools-a; sources (repository-relative):
#   SExtractor/tools/Leaf/pak_tool.py
# Symbols: parse_pak, extract_payload, lzss_literal_compress
# Validation: tests/test_engines_tools_a.py, synthetic fixtures only.
# Rewritten standard-library bytes API; scope: container-index-raw-pack.
# SPDX-License-Identifier: GPL-3.0-only
# SExtractor tools/Leaf/pak_tool.py: parse_pak, pack (raw branch); commit
# 8d8d976fd04ae54e7c677705af937273d04a376a. Bytes-only rewrite.
"""Leaf KCAP 36-byte-index variant; raw rebuild only, not SDT assembly."""
import struct


def index(data: bytes) -> list[dict]:
    if len(data) < 8 or data[:4] != b"KCAP":
        raise ValueError("not KCAP")
    count = struct.unpack_from("<I", data, 4)[0]
    end = 8 + count * 36
    if end > len(data):
        raise ValueError("truncated KCAP table")
    out = []
    for pos in range(8, end, 36):
        flag = struct.unpack_from("<I", data, pos)[0]
        off, size = struct.unpack_from("<II", data, pos + 28)
        if flag == 0xCCCCCCCC:
            raise ValueError("deleted entry needs original archive handling")
        if off < end or off + size > len(data):
            raise ValueError("KCAP placement invalid")
        out.append({"name": data[pos + 4:pos + 28].split(b"\0", 1)[0].decode("cp932"),
                    "flag": flag, "offset": off, "stored": data[off:off + size]})
    return out


def pack_raw(entries: list[tuple[str, bytes]]) -> bytes:
    table, body = bytearray(), bytearray()
    off = 8 + 36 * len(entries)
    for name, raw in entries:
        nb = name.encode("cp932")
        if not nb or len(nb) >= 24 or b"\0" in nb:
            raise ValueError("invalid KCAP name")
        table += struct.pack("<I24sII", 0, nb, off, len(raw))
        body += raw
        off += len(raw)
    return b"KCAP" + struct.pack("<I", len(entries)) + table + body
