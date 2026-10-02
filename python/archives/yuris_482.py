# SPDX-License-Identifier: GPL-3.0-only
"""YU-RIS 0x1E2 YPF: 64-bit offsets, Murmur2 hashes, template-preserving pack.

Layout/hash algorithms adapted from msg-tool src/scripts/yuris/arc/ypf.rs
and src/utils/murmur2.rs (GPLv3); name-length table from the MIT GARbro-based
yuris module. Only the empirically verified 482 profile is accepted.
"""
from dataclasses import dataclass
import struct
import zlib
from ..common.binary import bounded_zlib
from ..common.safety import validate_names
from .yuris import SWAP_TABLE_00


def murmur2(data: bytes, seed: int = 0) -> int:
    m, mask = 0x5BD1E995, 0xFFFFFFFF
    h = seed ^ len(data)
    end = len(data) // 4 * 4
    for pos in range(0, end, 4):
        k = int.from_bytes(data[pos:pos + 4], "little") * m & mask
        k ^= k >> 24
        k = k * m & mask
        h = ((h * m) ^ k) & mask
    if end != len(data):
        h ^= int.from_bytes(data[end:], "little")
        h = h * m & mask
    h ^= h >> 13
    h = h * m & mask
    return h ^ (h >> 15)


@dataclass(frozen=True)
class Entry:
    name: str
    field_offset: int
    packed: int
    unpacked_size: int
    size: int
    offset: int
    checksum: int


def read_index(stream, *, max_index_size=16 << 20, max_entries=100000):
    """Read only the directory; name XOR FF and SWAP_TABLE_00 are explicit profile."""
    saved = stream.tell()
    try:
        stream.seek(0, 2)
        size = stream.tell()
        stream.seek(0)
        header = stream.read(32)
        if len(header) != 32 or header[:4] != b"YPF\0":
            raise ValueError("expected YPF")
        version, count, end = struct.unpack_from("<III", header, 4)
        if version != 482 or not 0 < count <= max_entries or not 32 < end <= min(size, max_index_size):
            raise ValueError("unsupported version/count/directory size")
        directory = header + stream.read(end - 32)
        if len(directory) != end:
            raise ValueError("short directory read")
        swaps = dict(zip(SWAP_TABLE_00, bytes(x for pair in zip(SWAP_TABLE_00[1::2], SWAP_TABLE_00[::2]) for x in pair)))
        pos, entries = 32, []
        for _ in range(count):
            if pos + 5 > end:
                raise ValueError("truncated directory")
            name_hash, length = struct.unpack_from("<IB", directory, pos)
            length = swaps.get(length ^ 255, length ^ 255)
            if not length or pos + 5 + length + 22 > end:
                raise ValueError("invalid directory row")
            raw = bytes(v ^ 255 for v in directory[pos + 5:pos + 5 + length])
            if murmur2(raw) != name_hash:
                raise ValueError("name Murmur2 mismatch")
            field = pos + 5 + length
            typ, packed, unpacked, stored, offset, checksum = struct.unpack_from("<BBIIQI", directory, field)
            if packed not in (0, 1) or (not packed and unpacked != stored) or offset < end or offset + stored > size:
                raise ValueError("invalid member range/packing")
            entries.append(Entry(raw.decode("cp932"), field, packed, unpacked, stored, offset, checksum))
            pos = field + 22
        if pos != end:
            raise ValueError("unexpected directory padding")
        validate_names([e.name for e in entries])
        physical = sorted(entries, key=lambda e: e.offset)
        for left, right in zip(physical, physical[1:]):
            if left.offset + left.size > right.offset:
                raise ValueError("overlapping archive members")
        return directory, tuple(entries), size
    finally:
        stream.seek(saved)


def decode_member(stored: bytes, entry: Entry, *, max_output=64 << 20):
    if len(stored) != entry.size or entry.unpacked_size > max_output:
        raise ValueError("member size/budget mismatch")
    if murmur2(stored) != entry.checksum:
        raise ValueError("stored Murmur2 mismatch")
    return bounded_zlib(stored, max_output=entry.unpacked_size, expected_size=entry.unpacked_size) if entry.packed else stored


def pack_archive(source: bytes, replacements: dict[str, bytes], *, max_output=256 << 20):
    """Replace uncompressed members; preserve original compressed streams if equal.

    Physical order, gaps, directory hashes and opaque trailing bytes survive.
    Only documented per-member size/offset/hash fields change.
    """
    import io
    directory, entries, _ = read_index(io.BytesIO(source))
    if set(replacements) - {e.name for e in entries}:
        raise ValueError("unknown replacement member")
    out = bytearray(directory)
    cursor = len(directory)
    for entry in sorted(entries, key=lambda e: e.offset):
        old_stored = source[entry.offset:entry.offset + entry.size]
        original = decode_member(old_stored, entry)
        raw = replacements.get(entry.name, original)
        if not isinstance(raw, bytes) or len(raw) > 64 << 20:
            raise ValueError("invalid replacement")
        stored = old_stored if raw == original else zlib.compress(raw, 9) if entry.packed else raw
        if len(out) + entry.offset - cursor + len(stored) > max_output:
            raise ValueError("archive output budget exceeded")
        out.extend(source[cursor:entry.offset])
        struct.pack_into("<IIQI", out, entry.field_offset + 2, len(raw), len(stored), len(out), murmur2(stored))
        out.extend(stored)
        cursor = entry.offset + entry.size
    if len(out) + len(source) - cursor > max_output:
        raise ValueError("archive output budget exceeded")
    out.extend(source[cursor:])
    result = bytes(out)
    read_index(io.BytesIO(result))
    return result
