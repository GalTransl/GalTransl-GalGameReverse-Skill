"""Bounded Softpal PAC v1 / Amuse Craft PAC v2 indexes and member decoding.

Adapted from GARbro-Mod ArcFormats/Softpal/ArcPAC.cs, PacOpener.TryOpen,
ReadIndex/OpenEntry and Pac2Opener.TryOpen; commit
bc26d991ef5cdc0e1ecb32122ee9a48c3375750c. Changes: explicit layout and codec,
index-only streaming, strict names/budgets and no media-type guessing.

Copyright (C) 2016 by morkt
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

from ..common.binary import FormatError
from ._bounded import (limit, preserve_position, stream_size, read_at,
                       validate_entries, read_member_bytes)


@dataclass(frozen=True)
class IndexEntry:
    ordinal: int
    name: str
    offset: int
    size: int


@dataclass(frozen=True)
class ArchiveIndex:
    version: int
    name_size: int
    archive_size: int
    index_end: int
    entries: tuple[IndexEntry, ...]


def read_index(stream, *, version: int, name_size: int | None = None,
               name_encoding: str = "cp932", max_entries: int = 100_000,
               max_index_size: int = 16 << 20) -> ArchiveIndex:
    """v1 requires name_size=16/32; v2 uses 32-byte names and 'PAC ' magic.

    Count is at 0/8, index at 0x3FE/0x804. The first member offset must equal
    the calculated index end, as in upstream's layout check. No payload read.
    """
    limit(max_entries, "max_entries")
    limit(max_index_size, "max_index_size")
    if type(version) is not int or version not in (1, 2):
        raise FormatError("unsupported Softpal PAC version")
    if version == 2 and name_size is None:
        name_size = 32
    if type(name_size) is not int or name_size not in ((16, 32) if version == 1 else (32,)):
        raise FormatError("invalid Softpal PAC filename width")
    index_start = 0x3FE if version == 1 else 0x804
    if max_index_size < index_start:
        raise FormatError("Softpal header exceeds index budget")
    with preserve_position(stream):
        archive_size = stream_size(stream)
        end = min(archive_size, max_index_size)
        header = read_at(stream, 0, 4 if version == 1 else 12, end)
        if version == 2 and header[:4] != b"PAC ":
            raise FormatError("Softpal PAC v2 signature mismatch")
        count, = struct.unpack_from("<I", header, 0 if version == 1 else 8)
        if not 0 < count <= max_entries:
            raise FormatError("Softpal PAC count exceeds budget")
        index_size = count * (name_size + 8)
        index_end = index_start + index_size
        table = read_at(stream, index_start, index_size, end)
        entries = []
        for ordinal in range(count):
            pos = ordinal * (name_size + 8)
            name = table[pos:pos + name_size].split(b"\0", 1)[0].decode(name_encoding, errors="strict")
            size, offset = struct.unpack_from("<II", table, pos + name_size)
            if ordinal == 0 and offset != index_end:
                raise FormatError("Softpal first member does not match index end")
            entries.append(IndexEntry(ordinal, name, offset, size))
        validate_entries(entries, index_end, archive_size, max_entries)
        return ArchiveIndex(version, name_size, archive_size, index_end, tuple(entries))


def read_member(stream, index: ArchiveIndex, entry: IndexEntry, *,
                max_stored_size: int = 64 << 20) -> bytes:
    return read_member_bytes(stream, index, entry, max_stored_size=max_stored_size)


def decode_member(stored: bytes, *, codec: str = "raw", max_output_size: int = 64 << 20) -> bytes:
    """Explicit raw or script-dollar decoding; header/tail remain unchanged.

    script-dollar is only for a proven non-image/non-audio '$' member. It does
    not set TEXT.DAT's marker to '_', infer plaintext, parse Sv20 or decode VAFS.
    """
    limit(max_output_size, "max_output_size")
    if not isinstance(stored, bytes) or len(stored) > max_output_size:
        raise FormatError("Softpal stored type/output budget invalid")
    if codec == "raw":
        return stored
    if codec != "script-dollar":
        raise FormatError("unsupported Softpal member codec")
    if len(stored) < 16 or stored[:1] != b"$":
        raise FormatError("Softpal encrypted script requires a 16-byte '$' header")
    result = bytearray(stored)
    for group, offset in enumerate(range(16, len(result) - 3, 4)):
        shift = (4 + group) & 7
        value = result[offset]
        result[offset] = ((value << shift) | (value >> ((8 - shift) & 7))) & 0xFF
        word, = struct.unpack_from("<I", result, offset)
        struct.pack_into("<I", result, offset, word ^ 0xF7D5859D)
    return bytes(result)
