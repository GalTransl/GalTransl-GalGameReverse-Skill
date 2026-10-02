# Provenance group: tools-a; sources (repository-relative):
#   SExtractor/tools/HotSoup/dpm_pack.py
# Symbols: pack
# Validation: tests/test_engines_tools_a.py, synthetic fixtures only.
# Rewritten standard-library bytes API; scope: container-zero-key-roundtrip.
# SPDX-License-Identifier: GPL-3.0-only
# SExtractor tools/HotSoup/dpm_pack.py: pack; commit
# 8d8d976fd04ae54e7c677705af937273d04a376a. Rewrite: zero-key DPMX only.
"""HSP DPMX nonencrypted container; no AX decompilation or encrypted-key guessing."""
import struct


def pack(entries: list[tuple[str, bytes]]) -> bytes:
    table, body = bytearray(), bytearray()
    for name, raw in entries:
        nb = name.encode("cp932")
        if not 0 < len(nb) <= 16 or b"\0" in nb:
            raise ValueError("DPMX name exceeds 16 bytes")
        table += nb.ljust(16, b"\0") + struct.pack("<IIII", 0xFFFFFFFF, 0, len(body), len(raw))
        body += raw
    return b"DPMX" + struct.pack("<III", 16 + len(table), len(entries), 0) + table + body


def unpack(data: bytes) -> list[tuple[str, bytes]]:
    if len(data) < 16 or data[:4] != b"DPMX":
        raise ValueError("not DPMX")
    base, count = struct.unpack_from("<II", data, 4)
    if not 16 + count * 32 <= base <= len(data):
        raise ValueError("invalid DPMX base/count")
    out = []
    for p in range(16, 16 + count * 32, 32):
        key, off, size = struct.unpack_from("<III", data, p + 20)
        if key:
            raise ValueError("encrypted DPMX is not supported")
        if base + off + size > len(data):
            raise ValueError("DPMX member outside archive")
        name = data[p:p + 16].split(b"\0", 1)[0].decode("cp932")
        out.append((name, data[base + off:base + off + size]))
    return out
