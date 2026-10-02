# Provenance group: tools-a; sources (repository-relative):
#   SExtractor/tools/AdvSys3/ExAdvsys3.py
#   SExtractor/tools/AdvSys3/README.md
# Symbols: try_open_arc, extract_arc
# Validation: tests/test_engines_tools_a.py, synthetic fixtures only.
# Rewritten standard-library bytes API; scope: container-roundtrip.
# SPDX-License-Identifier: GPL-3.0-only
# SExtractor tools/AdvSys3/ExAdvsys3.py: try_open_arc, extract_arc.
# Commit 8d8d976fd04ae54e7c677705af937273d04a376a; provenance/tools-a.json.
# Rewrite: lossless counter/terminator metadata; no extension or filesystem IO.
"""AdvSys3 sequential arc*.dat records, not a text/VM assembler."""
import struct


def unpack(data: bytes) -> tuple[list[tuple[str, int, bytes]], bytes]:
    pos, entries = 0, []
    while pos < len(data):
        if len(data) - pos < 4:
            raise ValueError("truncated size")
        size = struct.unpack_from("<I", data, pos)[0]
        if size == 0:
            return entries, data[pos:]
        if len(data) - pos < 10:
            raise ValueError("truncated record")
        counter, n = struct.unpack_from("<IH", data, pos + 4)
        if not 1 <= n <= 256 or pos + 10 + n + size > len(data):
            raise ValueError("invalid name/payload length")
        name = data[pos + 10:pos + 10 + n].decode("utf-8")
        pos += 10 + n
        entries.append((name, counter, data[pos:pos + size]))
        pos += size
    return entries, b""


def pack(entries: list[tuple[str, int, bytes]], trailer: bytes = b"") -> bytes:
    if trailer and (len(trailer) < 4 or trailer[:4] != bytes(4)):
        raise ValueError("trailer must begin with zero-size terminator")
    out = bytearray()
    for name, counter, raw in entries:
        nb = name.encode("utf-8")
        if not 1 <= len(nb) <= 256 or not raw or "\0" in name:
            raise ValueError("invalid record name or empty payload")
        out += struct.pack("<IIH", len(raw), counter, len(nb)) + nb + raw
    return bytes(out) + trailer
