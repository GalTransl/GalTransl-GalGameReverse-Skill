# SPDX-License-Identifier: GPL-3.0-only
# Adapted from SExtractor tools/Patisserie/bin_pack.py
# Source commit: 8d8d976fd04ae54e7c677705af937273d04a376a
# Upstream attribution: Steins;Gate; SExtractor contributors.
"""Patisserie OZ/OFST DATA/DFLT archive stage; names belong to a separate list."""
import struct
import zlib


def pack_oz(members, *, compress=True):
    """Ordered byte members -> OZ archive; do not sort anonymous member indices."""
    members = list(members)
    if not members or len(members) > 100_000:
        raise ValueError("invalid member count")
    chunks = []
    for raw in members:
        packed = zlib.compress(raw) if compress and raw else raw
        if len(packed) < len(raw):
            chunk = b"DFLT" + struct.pack("<II", len(packed), len(raw)) + packed
        else:
            chunk = b"DATA" + struct.pack("<I", len(raw)) + raw
        chunks.append(chunk)
    cursor = 12 + 4 * len(chunks)
    offsets = []
    for chunk in chunks:
        offsets.append(struct.pack("<I", cursor))
        cursor += len(chunk)
    return b"OZ\x00\x01OFST" + struct.pack("<I", len(chunks) * 4) + b"".join(offsets + chunks)


def unpack_oz(data, *, max_output=64 * 1024 * 1024):
    """Return ordered members; reject unknown chunks, overlapping bounds and bombs."""
    if max_output < 0 or len(data) < 16 or data[:8] != b"OZ\x00\x01OFST":
        raise ValueError("not OZ/OFST")
    size = struct.unpack_from("<I", data, 8)[0]
    if not size or size % 4 or size // 4 > 100_000 or 12 + size > len(data):
        raise ValueError("invalid OFST table")
    offsets = list(struct.unpack_from("<%dI" % (size // 4), data, 12)) + [len(data)]
    if offsets[0] != 12 + size or any(a >= b for a, b in zip(offsets, offsets[1:])):
        raise ValueError("invalid member offsets")
    result, used = [], 0
    for begin, end in zip(offsets, offsets[1:]):
        chunk = data[begin:end]
        if len(chunk) < 8:
            raise ValueError("truncated member")
        n = struct.unpack_from("<I", chunk, 4)[0]
        if chunk[:4] == b"DATA":
            if n != len(chunk) - 8 or used + n > max_output:
                raise ValueError("DATA size/budget mismatch")
            raw = chunk[8:]
        elif chunk[:4] == b"DFLT" and len(chunk) >= 12:
            expected = struct.unpack_from("<I", chunk, 8)[0]
            if n != len(chunk) - 12 or expected > max_output - used:
                raise ValueError("DFLT size/budget mismatch")
            dec = zlib.decompressobj()
            raw = dec.decompress(chunk[12:], expected + 1)
            if len(raw) != expected or not dec.eof or dec.unused_data or dec.unconsumed_tail:
                raise ValueError("invalid bounded DFLT stream")
        else:
            raise ValueError("unsupported OZ member type")
        result.append(raw)
        used += len(raw)
    return result
