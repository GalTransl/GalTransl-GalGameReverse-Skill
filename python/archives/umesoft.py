# SPDX-License-Identifier: GPL-3.0-only
# Adapted from SExtractor tools/U-MeSoft/PK_pack.py and src/reg.yaml:U-MeSoft
# Source commit: 8d8d976fd04ae54e7c677705af937273d04a376a
# Upstream attribution: satan53x / SExtractor contributors.
"""U-MeSoft PK index repacker and literal SCR/TBL envelope; no full LZ decoder."""
# Layer split: archives; format algorithms and original notices retained.
# Companion module: python/engines/umesoft.py
import struct


def encode_member(data, *, kind):
    if kind not in ("scr", "tbl"):
        raise ValueError("explicit SCR/TBL member kind required")
    pad = b" " if kind == "scr" else b"\x00"
    raw = data + pad * (8 - len(data) % 8)  # ALWAYS add 1..8 bytes, as upstream
    out = bytearray(struct.pack("<I", len(raw)))
    for pos in range(0, len(raw), 8):
        out.append(0)
        out.extend(b ^ 0x42 for b in raw[pos:pos + 8])
    out.extend(b"\xFF\x00\x00")
    return bytes(out)


def decode_literal_member(data, *, max_output=64 * 1024 * 1024):
    if len(data) < 7:
        raise ValueError("truncated PK member")
    size = struct.unpack_from("<I", data)[0]
    if size % 8 or size > max_output or len(data) != 4 + size + size // 8 + 3:
        raise ValueError("invalid literal PK member size")
    out, pos = bytearray(), 4
    for _ in range(size // 8):
        if data[pos] != 0:
            raise ValueError("compressed PK backreferences not supported")
        out.extend(b ^ 0x42 for b in data[pos + 1:pos + 9])
        pos += 9
    if data[pos:] != b"\xFF\x00\x00":
        raise ValueError("missing PK terminator")
    return bytes(out)


def parse_pk(data):
    if len(data) < 4:
        raise ValueError("PK footer missing")
    size = struct.unpack_from("<I", data, len(data) - 4)[0]
    start = len(data) - 4 - size
    if start < 0:
        raise ValueError("PK index exceeds file")
    entries, pos, previous, seen = [], start, 0, set()
    while pos < len(data) - 4:
        if len(entries) >= 100_000:
            raise ValueError("PK index count exceeds budget")
        n = data[pos]
        pos += 1
        if not n or pos + n + 14 > len(data) - 4:
            raise ValueError("truncated PK index record")
        name = data[pos:pos + n].decode("cp932")
        pos += n
        extra = data[pos:pos + 6]
        size, offset = struct.unpack_from("<II", data, pos + 6)
        pos += 14
        if "\x00" in name or name in seen or offset != previous or size > start - offset:
            raise ValueError("invalid PK name/placement")
        entries.append({"name": name, "extra": extra, "data": data[offset:offset + size]})
        previous = offset + size
        seen.add(name)
    if previous != start:
        raise ValueError("unindexed PK data")
    return entries


def repack_pk(data, replacements):
    """Map member name -> already-encoded stored bytes; preserve six unknown bytes."""
    entries = parse_pk(data)
    if set(replacements) - {e["name"] for e in entries}:
        raise ValueError("unknown PK member")
    body, index = bytearray(), bytearray()
    for entry in entries:
        raw = replacements.get(entry["name"], entry["data"])
        name = entry["name"].encode("cp932")
        index.extend(bytes([len(name)]) + name + entry["extra"] + struct.pack("<II", len(raw), len(body)))
        body.extend(raw)
    return bytes(body + index + struct.pack("<I", len(index)))
