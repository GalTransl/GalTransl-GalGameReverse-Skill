# SPDX-License-Identifier: MIT
# Adapted from huang5-png/rugp-extractor, rugp_extractor.py (MIT).
# Author: huang5-png & Pair AI Assistant
# ReadEncrypted also documented by GARbro, Copyright (C) 2016 by morkt.
# Sources, notices and modifications: provenance/rugp-sources.json.
"""Bounded rUGP ReadEncrypted codec and physical header scan, not a RIO TOC.

Header matches are candidates, not scenario nodes. Short tails have no checksum;
even a successful decode cannot authenticate the key or establish script roles.
No object graph, archive writer, native code, or automatic file output.
"""

from array import array
from dataclasses import dataclass
import struct
import sys
from typing import BinaryIO

from ..common.binary import FormatError

RIO_KEY = 0x7E6B8CE2
ICI_KEY = 0xB29D5A0C
_SIZE_XOR = 0xC92E568B
_CHECK_XOR = 0xC92E568F
_MAX_SIZE = 0x1FFFFFFF


def _uint(value: int, maximum: int, name: str) -> None:
    if type(value) is not int or not 0 <= value <= maximum:
        raise FormatError(f"invalid {name}")


@dataclass(frozen=True)
class BlockHeader:
    offset: int
    plain_size: int
    stored_size: int
    flags: int

    @property
    def end(self) -> int:
        return self.offset + self.stored_size


@dataclass(frozen=True)
class DecodedBlock:
    header: BlockHeader
    data: bytes

    @property
    def checksum_chunks(self) -> int:
        return len(self.data) // 32


def parse_header(data: bytes, offset: int = 0) -> BlockHeader:
    """Read the eight-byte size relation; does not validate payload or a budget."""
    _uint(offset, len(data), "header offset")
    if len(data) - offset < 8:
        raise FormatError("truncated ReadEncrypted header")
    word1, word2 = struct.unpack_from("<II", data, offset)
    size = (~(word1 ^ _SIZE_XOR)) & 0xFFFFFFFF
    encoded_size = word2 ^ _CHECK_XOR
    if size != encoded_size >> 3:
        raise FormatError("invalid ReadEncrypted size relation")
    return BlockHeader(offset, size, 8 + size + 2 * (size // 32), encoded_size & 7)


def decode_block(data: bytes, offset: int = 0, *, key: int = RIO_KEY,
                 max_plain_bytes: int = 16 << 20) -> DecodedBlock:
    """Decode exactly one frame at offset; trailing container bytes are allowed."""
    _uint(key, 0xFFFFFFFF, "key")
    _uint(max_plain_bytes, _MAX_SIZE, "plain byte budget")
    header = parse_header(data, offset)
    if header.plain_size > max_plain_bytes:
        raise FormatError("ReadEncrypted plain byte budget exceeded")
    if header.end > len(data):
        raise FormatError("truncated ReadEncrypted payload or checksum")
    plain = bytearray(header.plain_size)
    src = offset + 8
    for start in range(0, header.plain_size, 32):
        portion = min(32, header.plain_size - start)
        checksum = 0
        for index in range(portion):
            value = data[src + index] ^ (key & 0xFF)
            plain[start + index] = value
            checksum = (checksum + value * (portion - index)) & 0xFFFF
            key = (~(((key >> 15) & 1) + key * 2 + 0xA3B376C9)) & 0xFFFFFFFF
        src += portion
        if portion == 32:
            if struct.unpack_from("<H", data, src)[0] != checksum:
                raise FormatError(f"ReadEncrypted checksum mismatch at {src:#x}")
            src += 2
    return DecodedBlock(header, bytes(plain))


def encrypt_block(plain: bytes, *, key: int = RIO_KEY, flags: int = 0,
                  max_plain_bytes: int = 16 << 20) -> bytes:
    """Encode a standalone frame; this does NOT repair RIO offsets/references."""
    _uint(key, 0xFFFFFFFF, "key")
    _uint(flags, 7, "header flags")
    _uint(max_plain_bytes, _MAX_SIZE, "plain byte budget")
    size = len(plain)
    if size > max_plain_bytes:
        raise FormatError("ReadEncrypted plain byte budget exceeded")
    out = bytearray(struct.pack("<II", (~size ^ _SIZE_XOR) & 0xFFFFFFFF,
                                ((size << 3) | flags) ^ _CHECK_XOR))
    for start in range(0, size, 32):
        portion = min(32, size - start)
        checksum = 0
        for index in range(portion):
            value = plain[start + index]
            out.append(value ^ (key & 0xFF))
            checksum = (checksum + value * (portion - index)) & 0xFFFF
            key = (~(((key >> 15) & 1) + key * 2 + 0xA3B376C9)) & 0xFFFFFFFF
        if portion == 32:
            out.extend(struct.pack("<H", checksum))
    return bytes(out)


def scan_headers(stream: BinaryIO, *, chunk_bytes: int = 1 << 20,
                 max_input_bytes: int = 4 << 30,
                 max_candidates: int = 100_000) -> tuple[BlockHeader, ...]:
    """Scan every physical byte alignment without reading any payload wholesale.

    Seven lookahead bytes cover headers across windows. Each start belongs to
    exactly one window. All sizes are retained, including empty/short blocks,
    oversized declarations and out-of-file ranges; the caller must classify them.
    Requires a seekable binary stream and restores its original position.
    """
    _uint(chunk_bytes, 64 << 20, "scan chunk bytes")
    _uint(max_input_bytes, 1 << 63, "input byte budget")
    _uint(max_candidates, 1_000_000, "candidate budget")
    if chunk_bytes < 8:
        raise FormatError("scan chunk must be at least eight bytes")
    original_pos = stream.tell()
    try:
        stream.seek(0, 2)
        size = stream.tell()
        if size > max_input_bytes:
            raise FormatError("RIO input byte budget exceeded")
        found = []
        for base in range(0, size, chunk_bytes):
            stream.seek(base)
            expected = min(chunk_bytes + 7, size - base)
            buf = stream.read(expected)
            if len(buf) != expected:
                raise FormatError("RIO input changed or short read during scan")
            window = []
            for phase in range(4):
                words = array("I")
                if words.itemsize != 4:
                    raise FormatError("four-byte unsigned array unavailable")
                stop = phase + max(0, (len(buf) - phase) // 4) * 4
                words.frombytes(buf[phase:stop])
                if sys.byteorder != "little":
                    words.byteswap()
                for index in range(len(words) - 1):
                    local = phase + 4 * index
                    if local >= chunk_bytes:
                        break
                    plain_size = (~(words[index] ^ _SIZE_XOR)) & 0xFFFFFFFF
                    if plain_size == (words[index + 1] ^ _CHECK_XOR) >> 3:
                        if len(found) + len(window) >= max_candidates:
                            raise FormatError("ReadEncrypted header candidate budget exceeded")
                        header = parse_header(buf, local)
                        window.append(BlockHeader(base + local, header.plain_size,
                                                  header.stored_size, header.flags))
            found.extend(sorted(window, key=lambda item: item.offset))
        stream.seek(0, 2)
        if stream.tell() != size:
            raise FormatError("RIO input changed size during scan")
        return tuple(found)
    finally:
        stream.seek(original_pos)


def read_block(stream: BinaryIO, header: BlockHeader, *, key: int = RIO_KEY,
               max_plain_bytes: int = 16 << 20) -> DecodedBlock:
    """Read a selected candidate, enforcing its range/budget before allocation."""
    _uint(max_plain_bytes, _MAX_SIZE, "plain byte budget")
    _uint(header.offset, 1 << 63, "block offset")
    _uint(header.plain_size, _MAX_SIZE, "block size")
    if header.plain_size > max_plain_bytes:
        raise FormatError("ReadEncrypted plain byte budget exceeded")
    if header.stored_size != 8 + header.plain_size + 2 * (header.plain_size // 32):
        raise FormatError("invalid indexed stored size")
    original_pos = stream.tell()
    try:
        stream.seek(0, 2)
        if header.end > stream.tell():
            raise FormatError("ReadEncrypted candidate extends beyond input")
        stream.seek(header.offset)
        data = stream.read(header.stored_size)
        local = parse_header(data)
        if (local.plain_size, local.stored_size, local.flags) != (
                header.plain_size, header.stored_size, header.flags):
            raise FormatError("ReadEncrypted header changed since scan")
        decoded = decode_block(data, key=key, max_plain_bytes=max_plain_bytes)
        return DecodedBlock(header, decoded.data)
    finally:
        stream.seek(original_pos)
