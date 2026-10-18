# SPDX-License-Identifier: GPL-3.0-only
"""AGE (ARC Game Engine) PAC archive: fixed-width names, two offset layouts.

Header: i16 entry count (0..4000), u8 name width, u32 index size. Records start
at 7 and are ``name[name_width] + offset + size``; two layouts are accepted:
  * index size == 7 + (name_width + 8) * count  -> u32 offset, u32 size
  * index size == 7 + (name_width + 12) * count -> i64 offset, u32 size
Offsets are relative to the index size. Names are NUL padded, CP932.

Some members carry a paged payload: at ``offset + 4`` an i16 ``6`` and a u32
``0x00140010`` mark ``i32 block count`` followed by 6-byte block headers whose
u16 is the block size including 4; the payload bytes of each block are right
rotated by 4 bits. ``read_member`` undoes that rotation, ``encode_member``
reapplies it.

Provenance: header variants, the paged marker and the rotation follow
``GameRes.AGE_SYSTEM.ArcPAC`` in the GARbro-derived code bundled with
"翻译肋手 v4.9D". Independent rewrite with bounded parsing; the reference's
Pack ignores the original name width, this module preserves it.
"""
from dataclasses import dataclass
import struct

HEADER_SIZE = 7
MAX_ENTRIES = 4000
MAX_MEMBER = 256 << 20
PAGED_I16 = 6
PAGED_U32 = 0x00140010


@dataclass(frozen=True)
class PacEntry:
    name: str
    offset: int
    size: int


@dataclass(frozen=True)
class PacArchive:
    name_width: int
    variant: int
    index_size: int
    entries: tuple


def _rot_right(value, bits=4):
    return ((value >> bits) | (value << (8 - bits))) & 0xFF


def _rot_left(value, bits=4):
    return ((value << bits) | (value >> (8 - bits))) & 0xFF


def open_pac(data):
    if not isinstance(data, bytes) or len(data) < HEADER_SIZE + 4:
        raise ValueError("PAC too small")
    count, name_width = struct.unpack_from("<hB", data, 0)
    index_size, = struct.unpack_from("<I", data, 3)
    if not 1 <= count <= MAX_ENTRIES or not 1 <= name_width <= 256:
        raise ValueError("PAC header out of range")
    if index_size >= len(data):
        raise ValueError("PAC index does not fit the file")
    plain = HEADER_SIZE + (name_width + 8) * count
    wide = HEADER_SIZE + (name_width + 12) * count
    if index_size == plain:
        variant = 1
    elif index_size == wide:
        variant = 2
    else:
        raise ValueError("PAC index size matches neither offset layout")
    entries, pos = [], HEADER_SIZE
    for _ in range(count):
        raw_name = data[pos:pos + name_width]
        pos += name_width
        end = raw_name.find(b"\0")
        raw_name = raw_name if end < 0 else raw_name[:end]
        try:
            name = raw_name.decode("cp932")
        except UnicodeDecodeError as exc:
            raise ValueError("PAC name is not CP932") from exc
        if variant == 1:
            offset, size = struct.unpack_from("<II", data, pos)
            pos += 8
        else:
            offset, size = struct.unpack_from("<qI", data, pos)
            pos += 12
        offset += index_size
        if not name or offset < index_size or size > MAX_MEMBER or offset + size > len(data):
            raise ValueError(f"PAC member {name!r} exceeds the file")
        entries.append(PacEntry(name, offset, size))
    if pos != index_size:  # Records must end exactly at the declared index size.
        raise ValueError("PAC record layout disagrees with the index size")
    return PacArchive(name_width, variant, index_size, tuple(entries))


def _paged_ranges(payload):
    """Yield (start, length) payload ranges of a paged member, or nothing."""
    if len(payload) < 10 or struct.unpack_from("<h", payload, 4)[0] != PAGED_I16 \
            or struct.unpack_from("<I", payload, 6)[0] != PAGED_U32:
        return None
    ranges, cursor, count = [], 4, struct.unpack_from("<i", payload, 0)[0]
    if not 0 <= count <= 100_000:
        return None
    for _ in range(count):
        if cursor + 2 > len(payload):
            break
        length = struct.unpack_from("<H", payload, cursor)[0] - 4
        cursor += 6
        if length < 0 or cursor + length > len(payload):
            break
        ranges.append((cursor, length))
        cursor += length
    return ranges


def read_member(data, entry):
    raw = bytearray(data[entry.offset:entry.offset + entry.size])
    if len(raw) != entry.size:
        raise ValueError("truncated PAC member")
    ranges = _paged_ranges(raw)
    if ranges is None:
        return bytes(raw)
    for start, length in ranges:
        for i in range(start, start + length):
            raw[i] = _rot_right(raw[i])
    return bytes(raw)


def encode_member(payload):
    """Reapply the paged rotation so the result matches the stored layout."""
    raw = bytearray(payload)
    ranges = _paged_ranges(raw)
    if ranges is not None:
        for start, length in ranges:
            for i in range(start, start + length):
                raw[i] = _rot_left(raw[i])
    return bytes(raw)


def build_pac(members, *, name_width=48, variant=1):
    """Write a complete PAC from ``name -> bytes`` in insertion order."""
    if not isinstance(members, dict) or not 1 <= len(members) <= MAX_ENTRIES:
        raise ValueError("PAC needs 1..4000 members")
    if variant not in (1, 2):
        raise ValueError("PAC variant must be 1 or 2")
    per = name_width + (8 if variant == 1 else 12)
    index_size = HEADER_SIZE + per * len(members)
    index, payload = bytearray(), bytearray()
    for name, data in members.items():
        if not isinstance(name, str) or not isinstance(data, bytes):
            raise ValueError("invalid PAC member")
        try:
            encoded = name.encode("cp932", errors="strict")
        except UnicodeEncodeError as exc:
            raise ValueError(f"PAC name is not CP932: {name!r}") from exc
        if not encoded or len(encoded) >= name_width:
            raise ValueError(f"PAC name does not fit {name_width} bytes: {name!r}")
        index += encoded.ljust(name_width, b"\0")
        stored = encode_member(data)
        if variant == 1:
            index += struct.pack("<II", len(payload), len(stored))
        else:
            index += struct.pack("<qI", len(payload), len(stored))
        payload += stored
    header = struct.pack("<hB", len(members), name_width) + struct.pack("<I", index_size)
    result = header + bytes(index) + bytes(payload)
    archive = open_pac(result)
    for entry in archive.entries:
        if read_member(result, entry) != members[entry.name]:
            raise ValueError(f"PAC member {entry.name!r} does not round trip")
    return result
