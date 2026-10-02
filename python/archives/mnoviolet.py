# Provenance group: tools-a; sources (repository-relative):
#   SExtractor/tools/MnoViolet/mnv_tool.py
# Symbols: find_name_size, read_entries, is_script_payload
# Validation: tests/test_engines_tools_a.py, synthetic fixtures only.
# Rewritten standard-library bytes API; scope: container-index-script-header.
# SPDX-License-Identifier: GPL-3.0-only
# SExtractor tools/MnoViolet/mnv_tool.py: find_name_size, read_entries;
# commit 8d8d976fd04ae54e7c677705af937273d04a376a. Pure index/header parsing.
"""M no Violet count+fixed-name DAT; returns stored scripts without decompression."""
# Layer split: archives; format algorithms and original notices retained.
# Companion module: python/engines/mnoviolet.py
import struct


def index(data: bytes) -> tuple[int, list[tuple[str, bytes]]]:
    if len(data) < 4:
        raise ValueError("truncated MNV DAT")
    count = struct.unpack_from("<I", data)[0]
    if not count:
        raise ValueError("empty DAT cannot establish name width")
    candidates = []
    for width in (100, 68, 44):
        end = 4 + (width + 8) * count
        if end <= len(data) and struct.unpack_from("<I", data, 4 + width + 4)[0] == end:
            candidates.append(width)
    if len(candidates) != 1:
        raise ValueError("unknown/ambiguous DAT name width")
    width = candidates[0]
    end = 4 + (width + 8) * count
    out = []
    for p in range(4, end, width + 8):
        size, off = struct.unpack_from("<II", data, p + width)
        name = data[p:p + width].split(b"\0", 1)[0].decode("cp932")
        if not name or off < end or off + size > len(data):
            raise ValueError("invalid DAT placement/name")
        out.append((name, data[off:off + size]))
    return width, out
