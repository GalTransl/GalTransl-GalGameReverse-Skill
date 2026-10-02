# SPDX-License-Identifier: GPL-3.0-only
"""Synthetic fixtures for the GXP archive reader. No real game data."""

import struct

def build_gxp(*members: bytes, version: int = 100, marker: int = 0x10203040,
              index_size: int = 16, opaque_prefix: bytes = b"") -> bytes:
    """Build a minimal GXP with a fixed-shape header and a raw data region.

    The index region is filled with a deterministic placeholder: the reader
    under test does not decode index items, so the fixture only has to satisfy
    the header relations. Members are concatenated into the data region.
    """
    data = b"".join(members)
    # Independent layout constants: never import the production reader here.
    data_offset = 0x30 + len(opaque_prefix) + index_size

    header = bytearray(0x30)
    header[0:4] = b"GXP\x00"
    struct.pack_into("<I", header, 0x04, version)
    struct.pack_into("<I", header, 0x08, marker)
    struct.pack_into("<III", header, 0x0C, 1, 0, 1)
    struct.pack_into("<I", header, 0x18, len(members))
    struct.pack_into("<I", header, 0x1C, index_size)
    struct.pack_into("<Q", header, 0x20, len(data))
    struct.pack_into("<Q", header, 0x28, data_offset)

    index = bytes((i * 7 + 3) & 0xFF for i in range(index_size))
    return bytes(header) + opaque_prefix + index + data
