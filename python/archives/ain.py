# SPDX-License-Identifier: GPL-3.0-only
"""AliceSoft AI2 container: 16-byte header plus one zlib stream.

Layout: ``AI2\\0`` (4), opaque word (4), uncompressed size (u32 at 8), stored
size (u32 at 12), zlib data from 16. The stored size is checked against the
remaining bytes instead of being trusted for the decompression bound.

Provenance: header fields and the inflate path follow ``ArcAin.TryOpen`` from the
third-party tool "翻译肋手 v4.9D" (GARbro-derived family). Independent rewrite:
the declared sizes must agree with the stream and trailer bytes are refused.
"""
import zlib

MAGIC = b"AI2\0"
HEADER_SIZE = 16
MAX_RAW = 64 << 20


def unpack(data):
    """Inflate an AI2 file; the declared sizes must match exactly."""
    if not isinstance(data, bytes) or len(data) < HEADER_SIZE + 2:
        raise ValueError("AI2 too small")
    if data[:4] != MAGIC:
        raise ValueError("not an AI2 container")
    raw_size, stored_size = (int.from_bytes(data[8:12], "little"),
                             int.from_bytes(data[12:16], "little"))
    if not 0 < raw_size <= MAX_RAW:
        raise ValueError("AI2 uncompressed size out of range")
    if stored_size and stored_size != len(data) - HEADER_SIZE:
        raise ValueError("AI2 stored size disagrees with the file length")
    stream = zlib.decompressobj()
    raw = stream.decompress(data[HEADER_SIZE:], raw_size + 1)
    if len(raw) != raw_size or not stream.eof or stream.unused_data or stream.unconsumed_tail:
        raise ValueError("AI2 zlib stream is truncated, oversized or has a trailer")
    return raw


def repack(original, raw):
    """Recompress ``raw`` into the original header, updating both size words."""
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_RAW:
        raise ValueError("invalid AIN payload")
    if not isinstance(original, bytes) or original[:4] != MAGIC:
        raise ValueError("template is not an AI2 container")
    stored = zlib.compress(raw, 9)
    header = bytearray(original[:HEADER_SIZE])
    header[8:12] = len(raw).to_bytes(4, "little")
    header[12:16] = len(stored).to_bytes(4, "little")
    result = bytes(header) + stored
    if unpack(result) != raw:
        raise ValueError("AI2 repack does not round trip")
    return result
