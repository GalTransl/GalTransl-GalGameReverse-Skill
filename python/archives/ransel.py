# SPDX-License-Identifier: GPL-3.0-only
# Adapted from SExtractor tools/Ransel/pack_bcd.py
# Source commit: 8d8d976fd04ae54e7c677705af937273d04a376a
# Upstream attribution: satan53x / SExtractor contributors.
"""Ransel paired BinaryCombineData BCD+BCL archive stage, no script guessing."""
MAGIC = b"BinaryCombineData\x00"


def _name(value):
    if not value or any(c in value for c in "\x00\r\n[]"):
        raise ValueError("invalid BCL name")
    value.encode("cp932")
    return value


def pack_bcd(members, *, archive_name):
    """Ordered (name, bytes) entries -> (BCD bytes, CP932 BCL bytes)."""
    archive_name = _name(archive_name)
    members = list(members)
    if not members or len(members) > 100_000:
        raise ValueError("invalid member count")
    out = bytearray(MAGIC)
    lines = ["[BinaryCombineData]", archive_name, ""]
    seen = set()
    for name, raw in members:
        _name(name)
        if name in seen:
            raise ValueError("duplicate BCL name")
        seen.add(name)
        lines.extend(["[" + name + "]", str(len(out)), str(len(raw)), ""])
        out.extend(raw)
    return bytes(out), ("\n".join(lines) + "\n").encode("cp932")


def unpack_bcd(data, index, *, archive_name):
    """Strict paired-index reader; no filesystem writes or path interpretation."""
    if not data.startswith(MAGIC) or len(index) > 16_000_000:
        raise ValueError("invalid BCD/BCL")
    lines = index.decode("cp932").splitlines()
    if len(lines) < 3 or lines[:2] != ["[BinaryCombineData]", _name(archive_name)]:
        raise ValueError("BCL names a different BCD")
    lines = [line for line in lines[2:] if line]
    if len(lines) % 3 or len(lines) // 3 > 100_000:
        raise ValueError("malformed BCL triplets")
    entries, cursor, seen = [], len(MAGIC), set()
    for i in range(0, len(lines), 3):
        label, offset, size = lines[i:i + 3]
        if not label.startswith("[") or not label.endswith("]"):
            raise ValueError("invalid BCL entry label")
        name = _name(label[1:-1])
        if name in seen or not offset.isdecimal() or not size.isdecimal():
            raise ValueError("duplicate name or nondecimal index")
        begin, count = int(offset), int(size)
        if begin != cursor or count > len(data) - begin:
            raise ValueError("noncontiguous or out-of-range BCD member")
        entries.append((name, data[begin:begin + count]))
        seen.add(name)
        cursor += count
    if cursor != len(data):
        raise ValueError("unindexed trailing BCD bytes")
    return entries
