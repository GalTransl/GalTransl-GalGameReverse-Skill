# Provenance group: tools-a; sources (repository-relative):
#   SExtractor/tools/EmonEngine/eme_pack.py
# Symbols: Arc.pack, Arc.encrypt
# Validation: tests/test_engines_tools_a.py, synthetic fixtures only.
# Rewritten standard-library bytes API; scope: script-container-pack.
# SPDX-License-Identifier: GPL-3.0-only
# SExtractor tools/EmonEngine/eme_pack.py: Arc.pack; commit
# 8d8d976fd04ae54e7c677705af937273d04a376a. Rewrite replaces .pyd compressor
# with valid literal-only LZSS and returns bytes. See provenance/tools-a.json.
"""EME zero-key, subtype-3 script packer; not encrypted/general EME reader."""
import struct


def pack_scripts(entries: list[tuple[str, bytes]]) -> bytes:
    body, index = bytearray(), bytearray()
    for name, raw in entries:
        nb = name.encode("cp932")
        if not 0 < len(nb) < 64 or b"\0" in nb:
            raise ValueError("invalid EME name")
        comp = b"".join(bytes(((1 << len(raw[i:i + 8])) - 1,)) + raw[i:i + 8]
                        for i in range(0, len(raw), 8))
        record = bytearray(0x60)
        record[:len(nb)] = nb
        struct.pack_into("<HHIIIII", record, 0x40, 0x1000, 0x12, 1, 3,
                         len(comp), len(raw), 8 + len(body))
        index += record
        body += bytes(12) + comp
    return b"RREDATA " + body + bytes(40) + index + struct.pack("<I", len(entries))


def zero_key_index(data: bytes) -> list[tuple[str, int, int, int]]:
    if len(data) < 52 or data[:8] != b"RREDATA ":
        raise ValueError("not EME")
    count = struct.unpack_from("<I", data, len(data) - 4)[0]
    start = len(data) - 4 - count * 0x60
    if start < 48 or data[start - 40:start] != bytes(40):
        raise ValueError("encrypted or truncated EME index unsupported")
    out = []
    for pos in range(start, len(data) - 4, 0x60):
        frame, init, flag, subtype, packed, size, off = struct.unpack_from("<HHIIIII", data, pos + 0x40)
        if (frame, init, flag, subtype) != (0x1000, 0x12, 1, 3) or off < 8 or off + 12 + packed > start - 40:
            raise ValueError("unsupported EME script layout")
        out.append((data[pos:pos + 64].split(b"\0", 1)[0].decode("cp932"), off, packed, size))
    return out
