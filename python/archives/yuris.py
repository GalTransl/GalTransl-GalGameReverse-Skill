"""Bounded YU-RIS YPF indexes and raw/zlib member decoding; no YBN XOR.

Adapted from GARbro-Mod ArcFormats/YuRis/ArcYPF.cs, Parser.ScanDir,
DecryptLength, SwapTable00/04/10, GuessSwapTable and Create; commit
bc26d991ef5cdc0e1ecb32122ee9a48c3375750c. Changes: explicit schemes,
strict bounds/names, index-only streaming and separate member decoding.

Copyright (C) 2014-2018 by morkt
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

from ..common.binary import FormatError, bounded_zlib
from ._bounded import (limit, preserve_position, stream_size, read_at,
                       validate_entries, read_member_bytes)


SWAP_TABLE_10 = bytes.fromhex("09 0b 0d 13 15 1b 20 23 26 29 2c 2f 2e 32")
SWAP_TABLE_04 = bytes.fromhex("0c 10 11 19 1c 1e") + SWAP_TABLE_10
SWAP_TABLE_00 = bytes.fromhex("03 48 06 35") + SWAP_TABLE_04
SUPPORTED_VERSIONS = (0xDE, 0xF7, 0x122, 0x12C, 0x196, 0x1D9, 0x1F4)


@dataclass(frozen=True)
class IndexEntry:
    ordinal: int
    name: str
    offset: int
    size: int
    unpacked_size: int
    packed: bool
    file_type: int
    name_hash: int
    checksum: int
    extra: bytes


@dataclass(frozen=True)
class ArchiveIndex:
    version: int
    archive_size: int
    index_end: int
    directory_bound: int
    entries: tuple[IndexEntry, ...]


def read_index(stream, *, version: int, name_key: int,
               swap_table: bytes | None = None, extra_header_size: int | None = None,
               name_encoding: str = "cp932", verify_name_hash: bool = False,
               max_entries: int = 100_000, max_index_size: int = 16 << 20) -> ArchiveIndex:
    """Read only actual directory records; version/key are caller-proven.

    Version 0x1F4 requires an explicit table (game-specific variants exist).
    Extra bytes default to 8 for 0xDE, 4 for >=0x1D9, otherwise 0; an explicit
    0/4/8 overrides this for a proven scheme. @12 is an upper bound, not a
    payload start: the upstream writer includes the 0x20 header in that value.
    CRC32 checking is opt-in because the upstream reader ignores name hashes.
    All byte budgets are checked before reading, and stream position is restored.
    """
    for key, value in (("max_entries", max_entries), ("max_index_size", max_index_size)):
        limit(value, key)
    if type(version) is not int or version not in SUPPORTED_VERSIONS:
        raise FormatError("unsupported YPF version")
    if type(name_key) is not int or not 0 <= name_key <= 255:
        raise FormatError("YPF name key must be an explicit byte")
    if swap_table is None:
        if version == 0x1F4:
            raise FormatError("YPF 0x1F4 requires a proven swap table")
        swap_table = (SWAP_TABLE_04 if version < 0x100 else
                      SWAP_TABLE_10 if 0x12C <= version < 0x196 else SWAP_TABLE_00)
    if (not isinstance(swap_table, bytes) or len(swap_table) % 2
            or len(set(swap_table)) != len(swap_table)):
        raise FormatError("YPF swap table must contain distinct byte pairs")
    if extra_header_size is None:
        extra_header_size = 4 if version >= 0x1D9 else 8 if version == 0xDE else 0
    if type(extra_header_size) is not int or extra_header_size not in (0, 4, 8):
        raise FormatError("unsupported YPF extra header size")
    lengths = list(range(256))
    for a, b in zip(swap_table[::2], swap_table[1::2]):
        lengths[a], lengths[b] = b, a
    if max_index_size < 0x20:
        raise FormatError("YPF header exceeds index budget")
    with preserve_position(stream):
        archive_size = stream_size(stream)
        header = read_at(stream, 0, 0x20, archive_size)
        magic, actual_version, count, directory_bound = struct.unpack_from("<4sIII", header)
        if magic != b"YPF\0" or actual_version != version:
            raise FormatError("YPF signature/version mismatch")
        if not 0 < count <= max_entries or directory_bound < count * (0x17 + extra_header_size):
            raise FormatError("YPF count/directory bound invalid")
        end = min(archive_size, 0x20 + directory_bound, max_index_size)
        position, entries = 0x20, []
        for ordinal in range(count):
            prefix = read_at(stream, position, 5, end)
            name_hash, encoded_length = struct.unpack("<IB", prefix)
            name_length = lengths[encoded_length ^ 0xFF]
            if not name_length:
                raise FormatError("empty YPF name")
            row = read_at(stream, position + 5, name_length + 0x12 + extra_header_size, end)
            raw_name = bytes(value ^ name_key for value in row[:name_length])
            if verify_name_hash and zlib.crc32(raw_name) != name_hash:
                raise FormatError("YPF name CRC32 mismatch (key/table may be wrong)")
            name = raw_name.decode(name_encoding, errors="strict")
            file_type, packed, unpacked, size, offset, checksum = struct.unpack_from("<BBIIII", row, name_length)
            if packed not in (0, 1):
                raise FormatError("unsupported YPF packing flag")
            if not packed and size != unpacked:
                raise FormatError("YPF raw size mismatch")
            entries.append(IndexEntry(ordinal, name, offset, size, unpacked, bool(packed),
                                      file_type, name_hash, checksum, row[name_length + 0x12:]))
            position += 5 + len(row)
        validate_entries(entries, position, archive_size, max_entries)
        return ArchiveIndex(version, archive_size, position, directory_bound, tuple(entries))


def read_member(stream, index: ArchiveIndex, entry: IndexEntry, *,
                max_stored_size: int = 64 << 20) -> bytes:
    """Read stored bytes of one entry from the same unchanged stream."""
    return read_member_bytes(stream, index, entry, max_stored_size=max_stored_size)


def decode_member(entry: IndexEntry, stored: bytes, *, compression: str = "zlib",
                  verify_checksum: bool = False, max_output_size: int = 64 << 20) -> bytes:
    """Decode raw/zlib only; never apply the separate YSTB ScriptKey.

    The scheme's codec must be known; Snappy is deliberately unsupported.
    Stored Adler32 verification is opt-in, matching upstream writer evidence.
    """
    limit(max_output_size, "max_output_size")
    if compression != "zlib":
        raise FormatError("unsupported YPF compression scheme")
    if not isinstance(stored, bytes) or len(stored) != entry.size:
        raise FormatError("YPF stored size mismatch")
    if entry.unpacked_size > max_output_size:
        raise FormatError("YPF output exceeds budget")
    if verify_checksum and zlib.adler32(stored) != entry.checksum:
        raise FormatError("YPF stored Adler32 mismatch")
    if entry.packed:
        return bounded_zlib(stored, max_output=entry.unpacked_size, expected_size=entry.unpacked_size)
    if len(stored) != entry.unpacked_size:
        raise FormatError("YPF raw size mismatch")
    return stored
