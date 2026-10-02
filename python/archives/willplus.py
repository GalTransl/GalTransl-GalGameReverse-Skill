"""Bounded Will ARC v1 and Pulltop ARC/AR2 v2 index and member readers.

Adapted from GARbro-Mod ArcFormats/Will/ArcWILL.cs (TryOpen/ReadFileList,
DecodeScript) and ArcPulltop.cs (TryOpen/OpenEntry/OpenPsp), commit
bc26d991ef5cdc0e1ecb32122ee9a48c3375750c. Changes: explicit layouts/codecs,
bounded index-only streaming, strict names/ranges and PSP size validation.

Copyright (C) 2014-2017 by morkt (ArcWILL.cs)
Copyright (C) 2015 by morkt (ArcPulltop.cs)
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

from ..common.binary import FormatError, Reader
from ..common.safety import logical_path
from ._bounded import (limit, preserve_position, stream_size, read_at, check_range,
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
    name_size: int | None
    archive_size: int
    index_end: int
    entries: tuple[IndexEntry, ...]


def read_index(stream, *, version: int, name_size: int | None = None,
               name_encoding: str = "cp932", max_entries: int = 100_000,
               max_index_size: int = 16 << 20, max_name_bytes: int = 4096) -> ArchiveIndex:
    """Explicit v1 (9/13-byte base names) or v2 (UTF-16LE names).

    Neither format has a magic signature. A successful parse is structural
    evidence, not automatic identification. Preserve name case (the upstream
    v1 reader lowercases it); replace any base-name suffix with its group ext.
    Index budgets include the header, all directories and intervening gaps.
    """
    for key, value in (("max_entries", max_entries), ("max_index_size", max_index_size),
                       ("max_name_bytes", max_name_bytes)):
        limit(value, key)
    if type(version) is not int or version not in (1, 2):
        raise FormatError("unsupported Will ARC version")
    if (version == 1 and (type(name_size) is not int or name_size not in (9, 13))) or (version == 2 and name_size is not None):
        raise FormatError("v1 requires name_size=9/13; v2 has variable UTF-16 names")
    if max_index_size < 8 or max_name_bytes < 2:
        raise FormatError("Will header/name budget too small")
    with preserve_position(stream):
        archive_size = stream_size(stream)
        end = min(archive_size, max_index_size)
        if version == 2:
            count, index_size = struct.unpack("<II", read_at(stream, 0, 8, end))
            if not 0 < count <= max_entries or index_size < count * 12:
                raise FormatError("invalid Will v2 count/index size")
            index_end = 8 + index_size
            reader = Reader(read_at(stream, 8, index_size, end))
            entries = []
            for ordinal in range(count):
                size, relative = reader.unpack("<II")
                raw_name = reader.terminated(unit=2, max_bytes=max_name_bytes)
                name = raw_name.decode("utf-16le", errors="strict")
                entries.append(IndexEntry(ordinal, name, index_end + relative, size))
            if reader.pos != index_size:
                raise FormatError("unparsed Will v2 index tail")
        else:
            groups, = struct.unpack("<I", read_at(stream, 0, 4, end))
            if not 0 < groups <= min(255, max_entries):
                raise FormatError("invalid Will v1 extension count")
            header_end = 4 + groups * 12
            table = read_at(stream, 4, groups * 12, end)
            directories, count = [], 0
            for number in range(groups):
                raw_ext, group_count, offset = struct.unpack_from("<4sII", table, number * 12)
                ext = raw_ext.split(b"\0", 1)[0].decode(name_encoding, errors="strict")
                if len(ext) > 3 or any(char in ext for char in ".\\/"):
                    raise FormatError("invalid Will extension")
                count += group_count
                if not 0 < group_count <= 0xFFFF or count > max_entries:
                    raise FormatError("invalid Will v1 member count")
                size = group_count * (name_size + 8)
                check_range(offset, size, end, start=header_end)
                directories.append((offset, size, group_count, ext))
            previous = header_end
            for offset, size, _, _ in sorted(directories):
                if offset < previous:
                    raise FormatError("overlapping Will v1 directories")
                previous = offset + size
            index_end, entries = previous, []
            for offset, size, group_count, ext in directories:
                directory = read_at(stream, offset, size, end)
                for number in range(group_count):
                    pos = number * (name_size + 8)
                    base = directory[pos:pos + name_size].split(b"\0", 1)[0].decode(name_encoding, errors="strict")
                    logical_path(base)
                    if "/" in base or "\\" in base:
                        raise FormatError("Will v1 base names must be flat")
                    name = base.rsplit(".", 1)[0] + "." + ext if ext else base
                    stored_size, member_offset = struct.unpack_from("<II", directory, pos + name_size)
                    entries.append(IndexEntry(len(entries), name, member_offset, stored_size))
        validate_entries(entries, index_end, archive_size, max_entries)
        return ArchiveIndex(version, name_size, archive_size, index_end, tuple(entries))


def read_member(stream, index: ArchiveIndex, entry: IndexEntry, *,
                max_stored_size: int = 64 << 20) -> bytes:
    return read_member_bytes(stream, index, entry, max_stored_size=max_stored_size)


def decode_member(stored: bytes, *, codec: str = "raw", max_output_size: int = 64 << 20) -> bytes:
    """Explicit raw, script-ror2, or psp decoding; never infer by filename.

    Upstream rotates SCR/WSC in v1 and WS2/JSON in v2, except v2 archives whose
    basename contains 'Model'. PSP is a separate LZSS resource codec. A caller
    must prove that rule applies before requesting script-ror2 (exactly once).
    """
    limit(max_output_size, "max_output_size")
    if not isinstance(stored, bytes):
        raise FormatError("Will member must be bytes")
    if codec not in ("raw", "script-ror2", "psp"):
        raise FormatError("unsupported Will member codec")
    if codec != "psp":
        if len(stored) > max_output_size:
            raise FormatError("Will output exceeds budget")
        if codec == "raw":
            return stored
        return bytes((value >> 2) | ((value << 6) & 0xFF) for value in stored)
    reader = Reader(stored)
    expected = reader.u32()
    if expected > max_output_size:
        raise FormatError("Will PSP output exceeds budget")
    frame, frame_pos, output = bytearray(0x1000), 1, bytearray()
    while len(output) < expected:
        control = reader.take(1)[0]
        for bit in range(8):
            if len(output) == expected:
                break
            if control & (1 << bit):
                value = reader.take(1)[0]
                output.append(value)
                frame[frame_pos] = value
                frame_pos = (frame_pos + 1) & 0xFFF
            else:
                hi, lo = reader.take(2)
                offset, count = (hi << 4) | (lo >> 4), 2 + (lo & 15)
                if count > expected - len(output):
                    raise FormatError("Will PSP match exceeds declared output")
                for _ in range(count):
                    value = frame[offset]
                    output.append(value)
                    frame[frame_pos] = value
                    offset, frame_pos = (offset + 1) & 0xFFF, (frame_pos + 1) & 0xFFF
    if reader.pos != len(stored):
        raise FormatError("trailing Will PSP data")
    return bytes(output)
