# Provenance group: tools-a; sources (repository-relative):
#   SExtractor/tools/AGSI/agsi_common.py
#   SExtractor/tools/AGSI/agsi_sb_tool.py
#   SExtractor/tools/AGSI/agsi_inject.py
# Symbols: swap_nibble_bytes, read_cstr_decode, rebuild_cstr_files, parse_segments, inject
# Validation: tests/test_engines_tools_a.py, synthetic fixtures only.
# Rewritten standard-library bytes API; scope: script-pool-rebuild.
# SPDX-License-Identifier: GPL-3.0-only
# Adapted from SExtractor tools/AGSI/{agsi_common,agsi_sb_tool,agsi_inject}.py
# Symbols: parse_segments, read_cstr_decode, rebuild_cstr_files, inject.
# Commit: 8d8d976fd04ae54e7c677705af937273d04a376a; see provenance/tools-a.json.
# Rewrite: bytes API, strict bounds/encoding, reject conflicting shared IDs; no IO.
"""SB2 structural reader and existing-index CSTR rebuild, not a VM assembler."""
import struct


def swap_nibbles(data: bytes) -> bytes:
    return bytes((b >> 4) | ((b & 15) << 4) for b in data)


def read_cstr(data: bytes, count: int, *, encoded: bool = True) -> list[bytes]:
    if count < 0 or count * 8 > len(data):
        raise ValueError("truncated CSTR table")
    pool = data[count * 8:]
    if encoded:
        pool = swap_nibbles(pool)
    entries = []
    total = 0
    for off, size in struct.iter_unpack("<II", data[:count * 8]):
        if off != total or off + size > len(pool):
            raise ValueError("CSTR offset/size outside contiguous pool")
        entries.append(pool[off:off + size])
        total += size
    if total != len(pool):
        raise ValueError("unsupported CSTR pool size/alias layout")
    return entries


def build_cstr(entries: list[bytes], *, encoded: bool = True) -> bytes:
    pool, table = bytearray(), bytearray()
    for raw in entries:
        if not raw.endswith(b"\0"):
            raise ValueError("CSTR must include its terminating NUL")
        table += struct.pack("<II", len(pool), len(raw))
        pool += raw
    return bytes(table) + (swap_nibbles(pool) if encoded else bytes(pool))


def inject_cstr(data: bytes, count: int, changes: list[tuple[int, str, str]],
                *, encoding: str = "cp932") -> bytes:
    """Changes are (CSTR index, expected source, translation); CODE is untouched."""
    entries = read_cstr(data, count)
    assigned = {}
    for index, source, text in changes:
        if not 0 <= index < count:
            raise ValueError("CSTR index out of range")
        raw = entries[index]
        if not raw.endswith(b"\0") or b"\0" in raw[:-1]:
            raise ValueError("not a supported NUL-terminated text entry")
        if raw[:-1].decode(encoding) != source:
            raise ValueError("stale source text")
        if "\0" in text:
            raise ValueError("embedded NUL")
        if index in assigned and assigned[index] != text:
            raise ValueError("conflicting shared CSTR reference")
        assigned[index] = text
    if not assigned:
        return data
    for index, text in assigned.items():
        entries[index] = text.encode(encoding) + b"\0"
    return build_cstr(entries)


def split_sb2(data: bytes) -> tuple[bytes, list[tuple[bytes, bytes]]]:
    """Preserve all nine segment payloads plus optional untagged tail."""
    pos = 0

    def take(n):
        nonlocal pos
        if n < 0 or pos + n > len(data):
            raise ValueError("truncated SB2")
        raw = data[pos:pos + n]
        pos += n
        return raw

    def u32():
        return struct.unpack("<I", take(4))[0]

    header = take(0x2C)
    if header[:4] != b"SB2 ":
        raise ValueError("not SB2")
    h = struct.unpack("<11I", header)
    tags = [b"CODE", b"TTBL", b"FTBL", b"FTBL", b"VTBL", b"CSTR", b"CDBL", b"DBG_", b"DBG_"]
    segments = []
    for i, tag in enumerate(tags):
        if take(4) != tag:
            raise ValueError("unexpected SB2 segment order")
        start = pos
        if i == 0:
            take(h[3])
        elif i == 1:
            for _ in range(h[5]):
                take(4)
                take(u32() * 28)
        elif i in (2, 3):
            for _ in range(h[i + 4]):
                take(u32())
                take(12)
        elif i == 4:
            take(h[8] * 12)
        elif i == 5:
            table = take(h[9] * 8)
            take(sum(size for _, size in struct.iter_unpack("<II", table)))
        elif i == 6:
            take(h[10] * 8)
        elif i == 7:
            for _ in range(u32()):
                take(u32())
        else:
            take(u32() * 12)
        segments.append((tag, data[start:pos]))
    if pos < len(data):
        segments.append((b"", data[pos:]))
    return header, segments


def inject_sb2(data: bytes, changes: list[tuple[int, str, str]], *, encoding="cp932") -> bytes:
    header, segments = split_sb2(data)
    count = struct.unpack_from("<I", header, 36)[0]
    return header + b"".join(tag + (inject_cstr(raw, count, changes, encoding=encoding)
                                     if tag == b"CSTR" else raw)
                             for tag, raw in segments)
