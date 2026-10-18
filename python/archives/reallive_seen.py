# SPDX-License-Identifier: GPL-3.0-only
"""RealLive ``SEEN`` script container: section table, key XOR and LZ stream.

Header: 80000 bytes. The reference walk treats the first 40000 bytes as 5000
records of two little-endian u32 ``(offset, size)``; records with a zero size
are empty slots. Section payload, relative to ``offset``::

    +32  u32  literal prefix length, copied verbatim (at least 44)
    +36  u32  decompressed length, 0 when the tail is stored uncompressed
    +40  u32  leading bytes of the tail XORed with an external key table

The tail starts at ``offset + prefix``. Its first 8 bytes are skipped, then
bits are read least-significant first: 1 is a literal byte, 0 is a
little-endian u16 token whose low nibble plus two is the copy length and whose
high 12 bits are the backward distance. Decompressed bytes 256..512 inclusive
are XORed with a fixed 16-byte table, following the reference condition
``(uint)(index - 256) > 256``.

Provenance: ``WindowsFormsApplication1.Archive.RealLive.ArcSeen`` from the
third-party tool "翻译肋手 v4.9D". Independent rewrite with explicit bounds:
debug leftovers, the hard-coded section index and the in-place mutation of the
file buffer are not carried over. ``KeyTable.mem`` is caller-supplied, never
loaded from a fixed path.
"""
from dataclasses import dataclass
import struct

HEADER_SIZE = 80_000
SECTION_COUNT = 5_000
STREAM_HEADER = 8
MASK_TABLE = (131, 11, 207, 81, 135, 19, 95, 107,
              150, 77, 246, 20, 79, 33, 151, 222)
MASK_START = 256
MASK_END = 512
MIN_SECTION = 44
MAX_SECTION = 64 << 20
MAX_DISTANCE = 0xFFF
MAX_COPY = 17


@dataclass(frozen=True)
class SeenSection:
    index: int
    offset: int
    size: int


@dataclass(frozen=True)
class SeenArchive:
    sections: tuple


def open_seen(data):
    """Index the section table; empty slots and zero-size records are skipped."""
    if not isinstance(data, bytes) or len(data) < HEADER_SIZE:
        raise ValueError("SEEN file is smaller than its 80000-byte header")
    sections = []
    for index in range(SECTION_COUNT):
        offset, size = struct.unpack_from("<II", data, index * 8)
        if size == 0:
            continue
        if offset < HEADER_SIZE or offset > len(data) or size > len(data) - offset:
            raise ValueError(f"SEEN section {index} lies outside the file")
        sections.append(SeenSection(index, offset, size))
    return SeenArchive(tuple(sections))


def read_section(data, section, key_table=None):
    """Rebuild one section payload: literal prefix plus demasked plaintext.

    ``key_table`` is the external ``KeyTable.mem`` image and is required only
    when the section declares an encrypted span.
    """
    if not isinstance(data, bytes) or not isinstance(section, SeenSection):
        raise ValueError("invalid SEEN section input")
    if section.size < MIN_SECTION:
        raise ValueError("SEEN section is smaller than its own header fields")
    if section.offset + section.size > len(data):
        raise ValueError("SEEN section lies outside the file")
    start = section.offset
    prefix_size, unpacked_size, crypto_size = struct.unpack_from("<III", data, start + 32)
    if prefix_size > section.size:
        raise ValueError("SEEN literal prefix exceeds the section")
    if unpacked_size > MAX_SECTION:
        raise ValueError("SEEN decompressed size exceeds the limit")
    prefix = data[start:start + prefix_size]
    if unpacked_size == 0:
        return prefix
    if prefix_size + STREAM_HEADER > section.size:
        raise ValueError("SEEN compressed tail is missing its stream header")
    tail = bytearray(data[start + prefix_size:start + section.size])
    if crypto_size:
        if key_table is None:
            raise ValueError("SEEN section is encrypted; the key table is required")
        if crypto_size > len(tail) or crypto_size > len(key_table):
            raise ValueError("SEEN encrypted span exceeds the section or key table")
        for i in range(crypto_size):
            tail[i] ^= key_table[i]
    plain = lz_decompress(bytes(tail), unpacked_size)
    return prefix + _mask_plaintext(plain)


def _mask_plaintext(plain):
    """Apply the fixed XOR window to the decompressed stream."""
    if len(plain) <= MASK_START:
        return plain
    out = bytearray(plain)
    for i in range(MASK_START, min(len(plain), MASK_END + 1)):
        out[i] ^= MASK_TABLE[(i - MASK_START) % len(MASK_TABLE)]
    return bytes(out)


def lz_decompress(stream, unpacked_size):
    """Decode the reference LZ bit stream after its 8-byte header."""
    if not isinstance(stream, bytes) or not isinstance(unpacked_size, int):
        raise ValueError("invalid SEEN LZ input")
    if not 0 <= unpacked_size <= MAX_SECTION:
        raise ValueError("SEEN LZ size out of range")
    if unpacked_size == 0:
        return b""
    if len(stream) < STREAM_HEADER:
        raise ValueError("SEEN LZ stream is shorter than its header")
    out = bytearray()
    pos = STREAM_HEADER
    while len(out) < unpacked_size:
        if pos >= len(stream):
            raise ValueError("SEEN LZ control byte is missing")
        bits = stream[pos]
        pos += 1
        for _ in range(8):
            if len(out) >= unpacked_size:
                break
            if bits & 1:
                if pos >= len(stream):
                    raise ValueError("SEEN LZ literal is truncated")
                out.append(stream[pos])
                pos += 1
            else:
                if pos + 2 > len(stream):
                    raise ValueError("SEEN LZ back-reference is truncated")
                token = stream[pos] | (stream[pos + 1] << 8)
                pos += 2
                length = (token & 0xF) + 2
                distance = token >> 4
                if distance == 0 or distance > len(out):
                    raise ValueError("SEEN LZ back-reference points before the output")
                source = len(out) - distance
                for k in range(length):
                    out.append(out[source + k])
            bits >>= 1
    return bytes(out)


def lz_compress(payload, header=b"PACK\0\0\0\0"):
    """Encode ``payload`` with greedy matches; the header is stored verbatim.

    This is a plain literal/back-reference encoder for rebuilt sections. It is
    not validated against a game engine and does not try to match the original
    compressor's choices.
    """
    if not isinstance(payload, bytes) or not isinstance(header, bytes):
        raise ValueError("invalid SEEN LZ payload")
    if len(header) != STREAM_HEADER:
        raise ValueError("SEEN LZ header must be 8 bytes")
    out = bytearray(header)
    pos = 0
    while pos < len(payload):
        control_at = len(out)
        out.append(0)
        control = 0
        for bit in range(8):
            if pos >= len(payload):
                break
            length, distance = _longest_match(payload, pos)
            if length >= 2:
                out += struct.pack("<H", (distance << 4) | (length - 2))
                pos += length
            else:
                control |= 1 << bit
                out.append(payload[pos])
                pos += 1
        out[control_at] = control
    return bytes(out)


def _longest_match(payload, pos):
    limit = min(MAX_COPY, len(payload) - pos)
    window = max(0, pos - MAX_DISTANCE)
    for length in range(limit, 1, -1):
        index = payload.rfind(payload[pos:pos + length], window, pos)
        if index >= 0:
            return length, pos - index
    return 0, 0
