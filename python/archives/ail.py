# Provenance group: tools-a; sources (repository-relative):
#   SExtractor/tools/Ail/dat_pack_fake_compress.py
# Symbols: AilArchivePacker.pack_archive, AilArchivePacker.lzss_compress
# Validation: tests/test_engines_tools_a.py, synthetic fixtures only.
# Rewritten standard-library bytes API; scope: container-literal-pack.
# SPDX-License-Identifier: GPL-3.0-only
# SExtractor tools/Ail/dat_pack_fake_compress.py: AilArchivePacker.lzss_compress.
# Commit 8d8d976fd04ae54e7c677705af937273d04a376a; provenance/tools-a.json.
# Rewrite: pure literal-only SNL encoder, preserves explicit missing slots.
"""Ail SNL size table and its inverse-polarity literal compression branch."""
import struct


def literal_block(raw: bytes) -> bytes:
    return struct.pack("<HI", 1, len(raw)) + b"".join(b"\0" + raw[i:i + 8]
                                                        for i in range(0, len(raw), 8))


def pack(entries: list[bytes | None]) -> bytes:
    blocks = [literal_block(raw) if raw is not None else b"" for raw in entries]
    return struct.pack("<I", len(blocks)) + b"".join(struct.pack("<I", len(b)) for b in blocks) + b"".join(blocks)


def stored_entries(data: bytes) -> list[bytes | None]:
    if len(data) < 4:
        raise ValueError("truncated SNL")
    count = struct.unpack_from("<I", data)[0]
    pos = 4 + count * 4
    if pos > len(data):
        raise ValueError("truncated size table")
    out = []
    for (size,) in struct.iter_unpack("<I", data[4:pos]):
        if size in (0, 0xFFFFFFFF):
            out.append(None)
            continue
        if pos + size > len(data):
            raise ValueError("payload outside archive")
        out.append(data[pos:pos + size])
        pos += size
    if pos != len(data):
        raise ValueError("unsupported SNL trailing data")
    return out
