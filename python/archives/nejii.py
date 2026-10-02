# Provenance group: tools-a; sources (repository-relative):
#   SExtractor/tools/NEJII/cdt_pack.py
#   SExtractor/tools/NEJII/nejii_tool.py
# Symbols: pack_cdt, parse_cdt, parse_records, inject_bin
# Validation: tests/test_engines_tools_a.py, synthetic fixtures only.
# Rewritten standard-library bytes API; scope: container-raw-pack-fixed-record-text.
# SPDX-License-Identifier: GPL-3.0-only
# SExtractor tools/NEJII/cdt_pack.py: pack_cdt; commit
# 8d8d976fd04ae54e7c677705af937273d04a376a. Bytes-only raw mode, no lzss extension.
"""NEJII CDT trailer index and fixed 144-byte BIN text records; no LZSS decoder."""
# Layer split: archives; format algorithms and original notices retained.
# Companion module: python/engines/nejii.py
import struct


def pack_raw(entries: list[tuple[str, bytes]]) -> bytes:
    table, body = bytearray(), bytearray()
    for name, raw in entries:
        nb = name.encode("ascii")
        if not nb or len(nb) > 15 or b"\0" in nb:
            raise ValueError("CDT names need at most 15 ASCII bytes")
        table += struct.pack("<16sIIII", nb, len(raw), len(raw), 0, len(body))
        body += raw
    return bytes(body + table + b"RK1\0" + struct.pack("<II", len(entries), len(body)))


def index(data: bytes) -> list[dict]:
    if len(data) < 12 or data[-12:-8] != b"RK1\0":
        raise ValueError("not RK1 CDT")
    count, start = struct.unpack_from("<II", data, len(data) - 8)
    if start + count * 32 != len(data) - 12:
        raise ValueError("invalid CDT trailer index")
    out = []
    for pos in range(start, len(data) - 12, 32):
        nb, size, unpacked, flag, off = struct.unpack_from("<16sIIII", data, pos)
        if flag not in (0, 1) or off + size > start or (flag == 0 and size != unpacked):
            raise ValueError("invalid CDT entry")
        out.append({"name": nb.split(b"\0", 1)[0].decode("ascii"), "packed": bool(flag),
                    "unpacked_size": unpacked, "stored": data[off:off + size]})
    return out
