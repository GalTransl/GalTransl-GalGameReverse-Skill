# Provenance group: tools-a; sources (repository-relative):
#   SExtractor/tools/HCSystem/hcsystem_pak_tool.py
# Symbols: crypt_index, read_index, build_index, cmd_pack
# Validation: tests/test_engines_tools_a.py, synthetic fixtures only.
# Rewritten standard-library bytes API; scope: container-index-raw-pack.
# SPDX-License-Identifier: GPL-3.0-only
# SExtractor tools/HCSystem/hcsystem_pak_tool.py: crypt_index, read_index, build_index.
# Commit 8d8d976fd04ae54e7c677705af937273d04a376a. Pure bytes, strict UTF-16 names.
"""HCSystem PACK index and raw-member rebuilding; compressed members are opaque."""
import struct


def _swap(raw):
    return bytes((b >> 4) | ((b & 15) << 4) for b in raw)


def index(data: bytes) -> list[dict]:
    if len(data) < 12 or data[:4] != b"PACK" or data[8] not in (0, 1):
        raise ValueError("not supported PACK")
    count = struct.unpack_from("<I", data, 4)[0]
    end = 12 + count * 76
    if end > len(data):
        raise ValueError("truncated PACK table")
    table = _swap(data[12:end]) if data[8] else data[12:end]
    out = []
    for p in range(0, len(table), 76):
        name = table[p:p + 64]
        n = next((i for i in range(0, 64, 2) if name[i:i + 2] == b"\0\0"), 64)
        size, packed, off = struct.unpack_from("<III", table, p + 64)
        actual = packed or size
        if off < end or off + actual > len(data):
            raise ValueError("PACK payload outside data section")
        out.append({"name": name[:n].decode("utf-16-le"), "offset": off,
                    "unpacked_size": size, "packed_size": packed, "stored": data[off:off + actual]})
    return out


def pack_raw(entries: list[tuple[str, bytes]], *, encrypted_index: bool = True) -> bytes:
    table, body = bytearray(), bytearray()
    off = 12 + len(entries) * 76
    for name, raw in entries:
        nb = name.encode("utf-16-le")
        if not nb or len(nb) > 62 or "\0" in name:
            raise ValueError("PACK name exceeds 31 UTF-16 code units")
        table += nb.ljust(64, b"\0") + struct.pack("<III", len(raw), 0, off)
        body += raw
        off += len(raw)
    return b"PACK" + struct.pack("<II", len(entries), int(encrypted_index)) + (_swap(table) if encrypted_index else bytes(table)) + body
