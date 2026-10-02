# Provenance group: tools-a; sources (repository-relative):
#   SExtractor/tools/IKURA/ikura_decryptor.py
# Symbols: unpack_mpx, unpack_drs, handle_isf_xor
# Validation: tests/test_engines_tools_a.py, synthetic fixtures only.
# Rewritten standard-library bytes API; scope: container-mpx-roundtrip.
# SPDX-License-Identifier: GPL-3.0-only
# SExtractor tools/IKURA/ikura_decryptor.py: unpack_mpx; commit
# 8d8d976fd04ae54e7c677705af937273d04a376a. Rewrite: strict SM2MPX10 reader.
# GARbro-Mod ArcFormats/Ikura/ArcDRS.cs (MIT) supplementary; provenance/tools-a.json.
"""IKURA MPX member index. ISF/SECRETFILTER bytes remain encrypted if present."""
import struct


def unpack_mpx(data: bytes) -> list[tuple[str, bytes]]:
    if len(data) < 32 or data[:8] != b"SM2MPX10":
        raise ValueError("not SM2MPX10 (DRS is a different layout)")
    count = struct.unpack_from("<I", data, 8)[0]
    end = 32 + count * 20
    if end > len(data):
        raise ValueError("truncated MPX index")
    entries = []
    for p in range(32, end, 20):
        name = data[p:p + 12].split(b"\0", 1)[0].decode("ascii")
        off, size = struct.unpack_from("<II", data, p + 12)
        if not name or off < end or off + size > len(data):
            raise ValueError("invalid MPX entry")
        entries.append((name, data[off:off + size]))
    return entries


def rebuild_mpx(data: bytes, payloads: list[bytes]) -> bytes:
    entries = unpack_mpx(data)
    if len(entries) != len(payloads):
        raise ValueError("MPX entry order/count must stay fixed")
    header, table, body = data[:32], bytearray(), bytearray()
    off = 32 + len(entries) * 20
    for i, raw in enumerate(payloads):
        table += data[32 + i * 20:44 + i * 20] + struct.pack("<II", off, len(raw))
        body += raw
        off += len(raw)
    return header + table + body
