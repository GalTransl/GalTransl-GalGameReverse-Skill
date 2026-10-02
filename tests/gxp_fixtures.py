# SPDX-License-Identifier: GPL-3.0-only
"""Synthetic fixtures for the GXP archive reader. No real game data."""

import struct

from python.archives.gxp import HEADER_SIZE, INDEX_PREAMBLE_SIZE, MAGIC


def build_gxp(*members: bytes, version: int = 100, marker: int = 0x10203040,
              index_size: int | None = None) -> bytes:
    """Build a minimal GXP with a fixed-shape header and a raw data region.

    The index region is filled with a deterministic placeholder: the reader
    under test does not decode index items, so the fixture only has to satisfy
    the header relations. Members are concatenated into the data region.
    """
    if index_size is None:
        # Zero-size index is legal for the header relations but useless; use a
        # small deterministic block so tests exercise a non-empty region.
        index_size = 16
    data = b"".join(members)
    data_offset = HEADER_SIZE + INDEX_PREAMBLE_SIZE + index_size

    header = bytearray(HEADER_SIZE)
    header[0:4] = MAGIC
    struct.pack_into("<I", header, 0x04, version)
    struct.pack_into("<I", header, 0x08, marker)
    struct.pack_into("<III", header, 0x0C, 1, 0, 1)
    struct.pack_into("<I", header, 0x18, len(members))
    struct.pack_into("<I", header, 0x1C, index_size)
    struct.pack_into("<Q", header, 0x20, len(data))
    struct.pack_into("<Q", header, 0x28, data_offset)

    preamble = bytes(INDEX_PREAMBLE_SIZE)
    index = bytes((i * 7 + 3) & 0xFF for i in range(index_size))
    return bytes(header) + preamble + index + data
