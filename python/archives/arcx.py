# Provenance group: tools-a; sources (repository-relative):
#   SExtractor/tools/ARCX/arc_unpack.py
#   SExtractor/tools/ARCX/arc_pack.py
#   SExtractor/libs/lzss/lzss.c
# Symbols: unpack_arc_file, pack_arc, lzss_decompress, Padding
# Validation: tests/test_engines_tools_a.py, synthetic fixtures only.
# Rewritten standard-library bytes API; scope: container-unpack.
# SPDX-License-Identifier: GPL-3.0-only
# SExtractor tools/ARCX/arc_unpack.py: unpack_arc_file, commit
# 8d8d976fd04ae54e7c677705af937273d04a376a. Rewritten bounded bytes parser.
# Compression corroborated by libs/lzss/lzss.c: lzss_decompress, Padding=0.
# Original algorithm notice: Haruhiko Okumura (1989), use/distribute/modify freely.
# GARbro-Mod ArcFormats/{ArcARCX,LzssStream}.cs (MIT), commit
# bc26d991ef5cdc0e1ecb32122ee9a48c3375750c: separate variant; see provenance.
"""Sequential tools/ARCX records; NOT GARbro's fixed-index ARCX variant."""
import struct


def lzss(data: bytes, expected: int, *, fill: int = 0, start: int = 0xFEE,
         max_output: int = 64 * 1024 * 1024) -> bytes:
    """4096-byte ring, low-first flag bits; 1=literal; two-byte matches."""
    if not 0 <= expected <= max_output or not 0 <= fill <= 255 or not 0 <= start < 4096:
        raise ValueError("invalid LZSS size/configuration")
    ring = bytearray([fill]) * 4096
    out = bytearray()
    pos, wp = 0, start
    while len(out) < expected:
        if pos >= len(data):
            raise ValueError("truncated LZSS flag")
        flags = data[pos]
        pos += 1
        for bit in range(8):
            if len(out) == expected:
                break
            if flags & (1 << bit):
                if pos >= len(data):
                    raise ValueError("truncated literal")
                values = [data[pos]]
                pos += 1
                for value in values:
                    out.append(value)
                    ring[wp] = value
                    wp = (wp + 1) & 4095
            else:
                if pos + 2 > len(data):
                    raise ValueError("truncated match")
                lo, hi = data[pos:pos + 2]
                pos += 2
                rp, length = lo | ((hi & 240) << 4), (hi & 15) + 3
                if len(out) + length > expected:
                    raise ValueError("LZSS match exceeds declared size")
                for _ in range(length):
                    value = ring[rp]
                    rp = (rp + 1) & 4095
                    out.append(value)
                    ring[wp] = value
                    wp = (wp + 1) & 4095
    if pos != len(data):
        raise ValueError("trailing LZSS bytes")
    return bytes(out)


def unpack(data: bytes, *, variant: str, max_output: int = 64 * 1024 * 1024) -> list[tuple[str, bytes]]:
    if variant != "tools-sequential" or len(data) < 16:
        raise ValueError("explicit tools-sequential variant and 16-byte header required")
    pos, result, total_out = 16, [], 0
    while pos < len(data):
        if pos + 28 > len(data):
            raise ValueError("truncated sequential ARCX record")
        total, name_len, header, packed, size = struct.unpack_from("<5I", data, pos)
        flag = data[pos + 27]
        if header < 28 + name_len or total < header or pos + total > len(data):
            raise ValueError("invalid sequential record size (wrong variant?)")
        if flag not in (0, 1):
            raise ValueError("unknown compression flag")
        name = data[pos + 28:pos + 28 + name_len].rstrip(b"\0").decode("cp932")
        raw = data[pos + header:pos + total]
        if len(raw) != packed or (not flag and size != packed):
            raise ValueError("inconsistent ARCX payload size")
        total_out += size
        if total_out > max_output:
            raise ValueError("aggregate output limit")
        result.append((name, lzss(raw, size, max_output=max_output) if flag else raw))
        pos += total
    return result
