"""Majiro archive V1/V2/V3 reader and fixed-V1 writer, independent of games.

V1 records = CRC32/u32 offset, plus sentinel; length = next offset - offset.
V2 records = CRC32/u32 offset/u32 length. V3 uses u64 hash/u32 offset/u32 length.
Names are consecutive CP932 C strings. Payload bytes are not MJO decryption.
The writer sorts CRC32 hashes and writes the V1 sentinel; it never advertises
V2/V3 writing. Reader hashes are preserved, not treated as authenticity checks.
Names are untrusted; no function performs filesystem I/O.

Reference: GARbro-Mod, ArcFormats/Majiro/ArcMajiro.cs,
ArcOpener.TryOpen/Create, commit
bc26d991ef5cdc0e1ecb32122ee9a48c3375750c (MIT).
Copyright (C) 2014 by morkt

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
from dataclasses import dataclass
import struct
import zlib


@dataclass(frozen=True)
class Entry:
    name: str
    data: bytes
    offset: int
    version: int
    name_hash: int


def _range(data, offset, size):
    if offset < 0 or size < 0 or offset > len(data) or size > len(data) - offset:
        raise ValueError("Majiro range outside input")
    return data[offset:offset + size]


def extract(data: bytes, *, max_entries: int = 100_000,
            max_file_size: int = 64 << 20, max_total_size: int = 256 << 20,
            max_index_size: int = 16 << 20, max_archive_size: int = 512 << 20) -> list[Entry]:
    """Read exact V1/V2/V3 layouts, rejecting incomplete names and bad sentinel."""
    if not isinstance(data, bytes) or len(data) > max_archive_size:
        raise ValueError("Majiro input type/size")
    if min(max_entries, max_file_size, max_total_size, max_index_size, max_archive_size) < 0:
        raise ValueError("negative Majiro limit")
    magic = _range(data, 0, 16)
    if magic not in (b"MajiroArcV1.000\0", b"MajiroArcV2.000\0", b"MajiroArcV3.000\0"):
        raise ValueError("unsupported Majiro magic/version")
    version = magic[10] - ord("0")
    count, names_at, data_at = struct.unpack("<III", _range(data, 16, 12))
    if not 0 < count <= max_entries:
        raise ValueError("Majiro entry count limit")
    stride = 4 * (version + 1)
    table_size = (count + (version == 1)) * stride
    if names_at != 28 + table_size or not names_at < data_at <= len(data):
        raise ValueError("invalid Majiro table/name/data boundaries")
    if data_at - 28 > max_index_size:
        raise ValueError("Majiro index size limit")
    names_blob = _range(data, names_at, data_at - names_at)
    pos, total, entries, seen = 0, 0, [], set()
    for number in range(count):
        end = names_blob.find(b"\0", pos, min(len(names_blob), pos + 4097))
        if end <= pos:
            raise ValueError("Majiro missing/empty/overlong filename")
        name = names_blob[pos:end].decode("cp932", errors="strict")
        if name in seen:
            raise ValueError("duplicate Majiro filename")
        pos = end + 1
        record_at = 28 + number * stride
        if version == 1:
            name_hash, offset = struct.unpack_from("<II", data, record_at)
            next_offset, = struct.unpack_from("<I", data, record_at + stride + 4)
            if next_offset < offset:
                raise ValueError("descending Majiro V1 offsets")
            size = next_offset - offset
        elif version == 2:
            name_hash, offset, size = struct.unpack_from("<III", data, record_at)
        else:
            name_hash, offset, size = struct.unpack_from("<QII", data, record_at)
        if offset < data_at or size > max_file_size or total + size > max_total_size:
            raise ValueError("Majiro data range/output budget")
        payload = _range(data, offset, size)
        entries.append(Entry(name, payload, offset, version, name_hash))
        seen.add(name)
        total += size
    if pos != len(names_blob):
        raise ValueError("unsupported Majiro names padding/extra records")
    if version == 1:
        sentinel_hash, sentinel_end = struct.unpack_from("<II", data, 28 + count * 8)
        if sentinel_hash != 0 or sentinel_end != len(data):
            raise ValueError("invalid Majiro V1 end sentinel/trailing data")
    return entries


def build_v1(files: list[tuple[str, bytes]], *, max_entries: int = 100_000,
             max_total_size: int = 256 << 20, max_archive_size: int = 512 << 20) -> bytes:
    """Create V1 only; input names must be basenames, CP932, unique CRC32.

    Does not silently strip directories, select a game patch archive, or
    round-trip unknown V2/V3 hash semantics. Every offset fits an unsigned u32.
    """
    if not 0 < len(files) <= min(max_entries, 0x7fffffff):
        raise ValueError("Majiro file count limit")
    if min(max_total_size, max_archive_size) < 0:
        raise ValueError("negative Majiro budget")
    rows, seen, hashes, total, names_size = [], set(), set(), 0, 0
    for name, payload in files:
        if (not isinstance(name, str) or not name or name in seen
                or any(c in name for c in "\0/\\:")):
            raise ValueError("Majiro writer requires unique NUL-free basenames")
        if not isinstance(payload, bytes):
            raise ValueError("Majiro payload requires bytes")
        encoded = name.encode("cp932", errors="strict")
        if len(encoded) > 4096:
            raise ValueError("Majiro filename size limit")
        name_hash = zlib.crc32(encoded) & 0xffffffff
        if name_hash in hashes:
            raise ValueError("Majiro writer refuses CRC32 collisions")
        hashes.add(name_hash)
        seen.add(name)
        names_size += len(encoded) + 1
        total += len(payload)
        if total > max_total_size:
            raise ValueError("Majiro input budget")
        rows.append((name_hash, encoded, payload))
    names_at = 28 + (len(rows) + 1) * 8
    data_at = names_at + names_size
    end = data_at + total
    if end > min(max_archive_size, 0xffffffff):
        raise ValueError("Majiro archive/u32 budget")
    rows.sort(key=lambda row: row[0])
    table, names, body, offset = bytearray(), bytearray(), bytearray(), data_at
    for name_hash, encoded, payload in rows:
        table.extend(struct.pack("<II", name_hash, offset))
        names.extend(encoded + b"\0")
        body.extend(payload)
        offset += len(payload)
    table.extend(struct.pack("<II", 0, offset))
    return (b"MajiroArcV1.000\0" + struct.pack("<III", len(rows), names_at, data_at)
            + table + names + body)
