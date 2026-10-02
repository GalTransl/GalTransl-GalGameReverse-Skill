# SPDX-License-Identifier: GPL-3.0-only
"""GXP v100 header inspection and bounded RAW region reads.

This is not an index decoder or an archive extractor. Bytes before the data
base remain opaque; neither a fixed preamble nor plaintext members are assumed.
The 0x30 header boundary and data base at 0x28 were cross-checked against
GARbro-Mod ArcFormats/Astronauts/ArcGXP.cs (MIT, Copyright (C) 2016 by morkt).
Source details and the retained MIT license are in provenance/gxp.json.
No upstream code or executable is required at runtime.
"""

from dataclasses import dataclass
import struct
from typing import BinaryIO

from ..common.binary import FormatError

MAGIC = b"GXP\x00"
HEADER_SIZE = 0x30
Source = bytes | BinaryIO


@dataclass(frozen=True)
class GxpHeader:
    version: int
    marker: int
    flags: tuple[int, int, int]
    member_count: int
    index_size: int
    data_size: int
    data_offset: int

    @property
    def index_offset(self) -> int:
        return HEADER_SIZE

    @property
    def index_end(self) -> int:
        return self.data_offset


def _size(source: Source) -> int:
    if isinstance(source, bytes):
        return len(source)
    position = source.tell()
    try:
        source.seek(0, 2)
        return source.tell()
    finally:
        source.seek(position)


def _read(source: Source, offset: int, size: int) -> bytes:
    if isinstance(source, bytes):
        result = source[offset:offset + size]
    else:
        position = source.tell()
        try:
            source.seek(offset)
            result = source.read(size)
        finally:
            source.seek(position)
    if len(result) != size:
        raise FormatError("truncated GXP region")
    return result


def _nonnegative(value: int, label: str) -> None:
    if type(value) is not int or value < 0:
        raise FormatError(f"GXP {label} must be a nonnegative integer")


def read_header(source: Source) -> GxpHeader:
    """Inspect bytes or a seekable binary stream, reading only the 48-byte header.

    Supports version 100 / marker 0x10203040 only. Flags and the field at 0x1C
    are reported without interpreting encryption or individual index records.
    The data span must end at EOF. Stream position is preserved.
    """
    file_size = _size(source)
    if file_size < HEADER_SIZE:
        raise FormatError("truncated GXP header")
    raw = _read(source, 0, HEADER_SIZE)
    if raw[:4] != MAGIC:
        raise FormatError("not a GXP archive (magic mismatch)")
    version, marker, f0c, f10, f14, count, index_size, data_size, data_offset = (
        struct.unpack_from("<7I2Q", raw, 4)
    )
    if version != 100 or marker != 0x10203040:
        raise FormatError("unsupported GXP version/marker")
    if data_offset < HEADER_SIZE or data_offset > file_size:
        raise FormatError("GXP data offset outside archive or overlaps header")
    if data_size != file_size - data_offset:
        raise FormatError("GXP data region does not reach end of file")
    return GxpHeader(version, marker, (f0c, f10, f14), count,
                     index_size, data_size, data_offset)


def _checked_header(source: Source, header: GxpHeader | None) -> GxpHeader:
    actual = read_header(source)
    if header is not None and header != actual:
        raise FormatError("GXP supplied header does not match input")
    return actual


def index_bytes(source: Source, header: GxpHeader | None = None, *,
                max_size: int = 16 << 20) -> bytes:
    """Read the opaque region [0x30, data_offset), not decoded index entries.

    The 0x1C field is not used to invent a preamble length or skip bytes.
    An index parser must establish record boundaries before extraction.
    """
    _nonnegative(max_size, "index budget")
    hdr = _checked_header(source, header)
    size = hdr.index_end - hdr.index_offset
    if size > max_size:
        raise FormatError("GXP index region exceeds budget")
    return _read(source, hdr.index_offset, size)


def read_member(source: Source, offset: int, size: int,
                header: GxpHeader | None = None, *,
                max_size: int = 64 << 20) -> bytes:
    """Read a bounded RAW data span; does not decrypt/decompress a member.

    offset is relative to data_offset. The caller must independently establish
    offset/size from a decoded index entry and enforce cumulative batch budgets.
    Range validation alone does not establish member identity or plaintext.
    """
    _nonnegative(offset, "member offset")
    _nonnegative(size, "member size")
    _nonnegative(max_size, "member budget")
    if size > max_size:
        raise FormatError("GXP member exceeds budget")
    hdr = _checked_header(source, header)
    if offset > hdr.data_size or size > hdr.data_size - offset:
        raise FormatError("member range outside GXP data region")
    return _read(source, hdr.data_offset + offset, size)


def describe(source: Source) -> dict[str, int | str]:
    """Report header fields, without index decoding or payload reads."""
    hdr = read_header(source)
    return {
        "magic": "GXP",
        "version": hdr.version,
        "marker": f"0x{hdr.marker:08X}",
        "member_count": hdr.member_count,
        "index_size": hdr.index_size,
        "raw_index_region_size": hdr.index_end - hdr.index_offset,
        "data_size": hdr.data_size,
        "data_offset": hdr.data_offset,
        "file_size": _size(source),
    }
