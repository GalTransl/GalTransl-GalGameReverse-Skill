# Provenance group: tools-a; sources (repository-relative):
#   SExtractor/tools/AST/arc2_pack.py
# Symbols: pack, xorBytes
# Validation: tests/test_engines_tools_a.py, synthetic fixtures only.
# Rewritten standard-library bytes API; scope: container-index.
# SPDX-License-Identifier: GPL-3.0-only
# SExtractor tools/AST/arc2_pack.py: pack, xorBytes; commit
# 8d8d976fd04ae54e7c677705af937273d04a376a. Bytes-only index parser rewrite.
# GARbro-Mod ArcFormats/ArcAST.cs: ArcOpener (MIT), commit in provenance/tools-a.json.
"""ARC1/ARC2 index and stored payloads; compressed .adv bytes stay compressed."""
import struct


def index(data: bytes) -> list[dict]:
    if len(data) < 8 or data[:4] not in (b"ARC1", b"ARC2"):
        raise ValueError("not AST ARC1/2")
    count = struct.unpack_from("<I", data, 4)[0]
    if count > (len(data) - 8) // 9:
        raise ValueError("invalid count")
    pos, records = 8, []
    for _ in range(count):
        if pos + 9 > len(data):
            raise ValueError("truncated index")
        off, size, n = struct.unpack_from("<IIB", data, pos)
        pos += 9
        if not n or pos + n > len(data):
            raise ValueError("truncated/empty name")
        name = data[pos:pos + n]
        if data[:4] == b"ARC2":
            name = bytes(b ^ 255 for b in name)
        records.append({"name": name.decode("cp932"), "offset": off, "unpacked_size": size})
        pos += n
    for i, entry in enumerate(records):
        end = records[i + 1]["offset"] if i + 1 < count else len(data)
        if not pos <= entry["offset"] <= end <= len(data):
            raise ValueError("invalid payload offsets")
        entry["stored"] = data[entry["offset"]:end]
    return records
