# SPDX-License-Identifier: GPL-3.0-only
"""GxEngine / Astronauts GXP archive index and bounded member extraction.

Layout verified against real archives of one engine version:

    offset  type      meaning
    0x00    char[4]   "GXP\\0"
    0x04    u32       version (100 in the verified version)
    0x08    u32       marker (0x10203040 in the verified version)
    0x0C    u32       flag[0]
    0x10    u32       flag[1]
    0x14    u32       flag[2]
    0x18    u32       member count
    0x1C    u32       index region size in bytes
    0x20    u64       data region size in bytes
    0x28    u64       data region offset
    0x30..            index region (lightly obfuscated; see below)

Two relations hold on every verified archive and are used both as a cheap
self-check and to reject mis-detected files:

    data_offset == 0x30 + index_size
    data_offset + data_size == file_size

The region between 0x00 and the index is a fixed-size header; the index region
starts after it. The index region itself is stored with a light obfuscation that
is **not** decoded here: this module exposes the confirmed header relations and
a bounded raw reader, and leaves index-item decoding to a dedicated step once
the exact scheme is confirmed for a given version. It never guesses field widths
or decrypts bytes it cannot verify.

The verified archives store the data region **in the clear and uncompressed**:
sizes in the index equal the raw member sizes, and extracted members are directly
readable. Compression or encryption must be confirmed per version before use;
this module does not assume either.
"""

from dataclasses import dataclass
import struct

from ..common.binary import FormatError

MAGIC = b"GXP\x00"
HEADER_SIZE = 0x30
# The header is followed by a fixed stub before the index region. The verified
# version uses a 0x48-byte block here; kept as a named constant so a version
# with a different value is rejected loudly instead of silently misread.
INDEX_PREAMBLE_SIZE = 0x48


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
        return HEADER_SIZE + INDEX_PREAMBLE_SIZE

    @property
    def index_end(self) -> int:
        return self.data_offset


def read_header(data: bytes) -> GxpHeader:
    """Parse and validate the fixed GXP header. Rejects mis-detected files."""
    if len(data) < HEADER_SIZE:
        raise FormatError("truncated GXP header")
    if data[:4] != MAGIC:
        raise FormatError("not a GXP archive (magic mismatch)")
    version = struct.unpack_from("<I", data, 0x04)[0]
    marker = struct.unpack_from("<I", data, 0x08)[0]
    f0c, f10, f14 = struct.unpack_from("<III", data, 0x0C)
    member_count = struct.unpack_from("<I", data, 0x18)[0]
    index_size = struct.unpack_from("<I", data, 0x1C)[0]
    data_size = struct.unpack_from("<Q", data, 0x20)[0]
    data_offset = struct.unpack_from("<Q", data, 0x28)[0]

    header = GxpHeader(version, marker, (f0c, f10, f14), member_count,
                       index_size, data_size, data_offset)

    # Cross-check the two confirmed relations before returning anything.
    if data_offset != HEADER_SIZE + INDEX_PREAMBLE_SIZE + index_size:
        raise FormatError("GXP index/data offset relation does not hold")
    if data_offset + data_size != len(data):
        raise FormatError("GXP data region does not reach end of file")
    if header.index_end > len(data):
        raise FormatError("GXP index region exceeds file")
    return header


def index_bytes(data: bytes, header: GxpHeader | None = None) -> bytes:
    """Return the raw (still obfuscated) index region, bounded by the header."""
    hdr = header or read_header(data)
    return bytes(data[hdr.index_offset:hdr.index_end])


def read_member(data: bytes, offset: int, size: int, header: GxpHeader | None = None) -> bytes:
    """Read one member from the data region with explicit bounds checking.

    `offset` is relative to the start of the data region; `size` is the raw
    member size. Both must come from a decoded index entry -- this function
    never derives them by scanning.
    """
    hdr = header or read_header(data)
    if offset < 0 or size < 0:
        raise FormatError("negative member offset or size")
    start = hdr.data_offset + offset
    end = start + size
    if start < hdr.data_offset or end > hdr.data_offset + hdr.data_size or end > len(data):
        raise FormatError("member range outside GXP data region")
    return bytes(data[start:end])


def describe(data: bytes) -> dict[str, int | str]:
    """Header summary for reporting; no decoding, no guessing."""
    hdr = read_header(data)
    return {
        "magic": MAGIC.decode("ascii", "replace").rstrip("\x00"),
        "version": hdr.version,
        "marker": f"0x{hdr.marker:08X}",
        "member_count": hdr.member_count,
        "index_size": hdr.index_size,
        "data_size": hdr.data_size,
        "data_offset": hdr.data_offset,
        "file_size": len(data),
    }
