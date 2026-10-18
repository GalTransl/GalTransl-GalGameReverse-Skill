# SPDX-License-Identifier: GPL-3.0-only
"""Silky ARC resource archive: encrypted name length, big-endian fields, LZSS.

Layout (``TryOpen`` path):
  0  4  u32 little-endian index size (bytes after this field)
  4  .. index, repeated: u8 name length (0 is invalid), name bytes, u32 stored
        size, u32 unpacked size, u32 payload offset, all three big-endian
  The index ends exactly at ``4 + index_size``; payloads follow in file order.

Name bytes are stored with ``b[i] = plain[i] + length - i`` (mod 256), so a
decoded name must still be a NUL-terminated CP932 string inside its span.

Members are LZSS-compressed when ``stored size != unpacked size``. The codec is
the classic Okumura variant with window 4096, lookahead 18, threshold 2, zero
fill, and flag bits written from the least significant bit.

A second, older directory shape exists in the reference as ``TryOpenOLD``:
``i32 count`` then 32-byte names plus little-endian offset/size. The reference
UI never calls it; ``open_arc_old`` is read-only and documented as such.

Provenance: layout and name transform follow ``GameRes.Silky.ArcARC`` in the
GARbro-derived code bundled with "翻译肋手 v4.9D". Independent rewrite: strict
index boundaries, no silent name truncation, and the LZSS writer is bounded
instead of trusting a 2x output buffer.
"""
from dataclasses import dataclass
import struct

HEADER_SIZE = 4
MAX_ENTRIES = 16384
MAX_NAME = 112
MAX_MEMBER = 256 << 20

WINDOW = 4096
LOOKAHEAD = 18
THRESHOLD = 2
FILL = 0
START = WINDOW - LOOKAHEAD


@dataclass(frozen=True)
class ArcEntry:
    name: str
    offset: int
    size: int
    unpacked_size: int

    @property
    def packed(self):
        return self.size != self.unpacked_size


@dataclass(frozen=True)
class ArcArchive:
    index_size: int
    entries: tuple


def decrypt_name(stored):
    """Undo the rolling add applied to stored name bytes."""
    length = len(stored)
    return bytes((value + length - index) & 0xFF for index, value in enumerate(stored))


def encrypt_name(name):
    """Apply the rolling add used for stored name bytes."""
    length = len(name)
    return bytes((value - length + index) & 0xFF for index, value in enumerate(name))


def lzss_decompress(data, unpacked_size):
    """Decode an LZSS stream that must expand to exactly ``unpacked_size``."""
    if not 0 <= unpacked_size <= MAX_MEMBER:
        raise ValueError("Silky LZSS output size out of range")
    window = bytearray([FILL]) * WINDOW
    out = bytearray()
    cursor = 0
    pos = START
    flags = 0
    while len(out) < unpacked_size:
        flags >>= 1
        if not flags & 0x100:
            if cursor >= len(data):
                raise ValueError("Silky LZSS stream ended before the declared size")
            flags = data[cursor] | 0xFF00
            cursor += 1
        if flags & 1:
            if cursor >= len(data):
                raise ValueError("Silky LZSS literal is truncated")
            value = data[cursor]
            cursor += 1
            out.append(value)
            window[pos] = value
            pos = (pos + 1) & (WINDOW - 1)
            continue
        if cursor + 2 > len(data):
            raise ValueError("Silky LZSS match is truncated")
        low, high = data[cursor], data[cursor + 1]
        cursor += 2
        back = low | ((high & 0xF0) << 4)
        length = (high & 0x0F) + THRESHOLD + 1
        if length > LOOKAHEAD:
            raise ValueError("Silky LZSS match length out of range")
        for step in range(length):
            if len(out) >= unpacked_size:
                break
            value = window[(back + step) & (WINDOW - 1)]
            out.append(value)
            window[pos] = value
            pos = (pos + 1) & (WINDOW - 1)
    return bytes(out)


def lzss_compress(data):
    """Greedy Okumura LZSS encoder; returns the stream or ``b""`` for empty input."""
    if not data:
        return b""
    window = bytearray([FILL]) * WINDOW
    out = bytearray()
    literal_flags = 0
    token_count = 0
    pending = bytearray()
    position = 0
    total = len(data)

    def flush(flags):
        return bytes([flags]) + bytes(pending)

    head = {}
    previous = [-1] * total

    def insert(index):
        if index + 3 > total:
            return
        key = data[index:index + 3]
        previous[index] = head.get(key, -1)
        head[key] = index

    while position < total:
        best_length, best_distance = 0, 0
        key = data[position:position + 3]
        if len(key) == 3:
            start = head.get(key, -1)
            limit = min(LOOKAHEAD, total - position)
            steps = 0
            while start >= 0 and steps < 16:
                distance = position - start
                if distance >= WINDOW:
                    break
                length = 0
                while length < limit and data[start + length] == data[position + length]:
                    length += 1
                if length > best_length:
                    best_length, best_distance = length, distance
                    if length == limit:
                        break
                start = previous[start]
                steps += 1
        if best_length < THRESHOLD + 1:
            literal_flags |= 1 << token_count
            pending.append(data[position])
            step = 1
        else:
            back = (START + position - best_distance) & (WINDOW - 1)
            pending.append(back & 0xFF)
            pending.append(((back >> 4) & 0xF0) | (best_length - THRESHOLD - 1))
            step = best_length
        token_count += 1
        for index in range(position, min(position + step, total)):
            insert(index)
        position += step
        if token_count == 8:
            out += flush(literal_flags)
            literal_flags = 0
            token_count = 0
            pending.clear()
    if token_count:
        out += flush(literal_flags)
    return bytes(out)


def _read_index(data):
    index_size, = struct.unpack_from("<I", data, 0)
    end = HEADER_SIZE + index_size
    if index_size < 13 or end > len(data):
        raise ValueError("Silky ARC index size out of range")
    entries, pos = [], HEADER_SIZE
    while pos < end:
        length = data[pos]
        pos += 1
        if length == 0 or length > MAX_NAME:
            raise ValueError("Silky ARC name length out of range")
        if pos + length + 12 > len(data):
            raise ValueError("Silky ARC index entry exceeds the file")
        raw = decrypt_name(data[pos:pos + length])
        pos += length
        cut = raw.find(b"\0")
        if cut < 0:
            raise ValueError("Silky ARC name is not NUL terminated")
        stored, unpacked, offset = struct.unpack_from(">III", data, pos)
        pos += 12
        try:
            name = raw[:cut].decode("cp932")
        except UnicodeDecodeError as exc:
            raise ValueError("Silky ARC name is not CP932") from exc
        if not name or offset < end or offset + stored > len(data):
            raise ValueError(f"Silky ARC member {name!r} exceeds the file")
        if stored > MAX_MEMBER or unpacked > MAX_MEMBER:
            raise ValueError(f"Silky ARC member {name!r} size out of range")
        entries.append(ArcEntry(name, offset, stored, unpacked))
        if len(entries) > MAX_ENTRIES:
            raise ValueError("Silky ARC entry count out of range")
    if pos != end:
        raise ValueError("Silky ARC index does not end on its declared size")
    if not entries:
        raise ValueError("Silky ARC has no entries")
    if len({entry.offset for entry in entries}) != len(entries):
        raise ValueError("Silky ARC duplicate member offset")
    return ArcArchive(index_size, tuple(entries))


def open_arc(data):
    """Parse the ``TryOpen`` directory; returns offsets as absolute file positions."""
    if not isinstance(data, bytes) or len(data) < HEADER_SIZE + 13:
        raise ValueError("Silky ARC too small")
    return _read_index(data)


def open_arc_old(data):
    """Parse the unused legacy directory (32-byte names, little-endian fields)."""
    if not isinstance(data, bytes) or len(data) < 4:
        raise ValueError("Silky ARC too small")
    count, = struct.unpack_from("<i", data, 0)
    if not 1 <= count <= MAX_ENTRIES or 4 + count * 40 > len(data):
        raise ValueError("Silky ARC legacy count out of range")
    entries, pos, seen = [], 4, set()
    for _ in range(count):
        raw = data[pos:pos + 32]
        pos += 32
        cut = raw.find(b"\0")
        if cut <= 0:
            raise ValueError("Silky ARC legacy name is not NUL terminated")
        try:
            name = raw[:cut].decode("cp932")
        except UnicodeDecodeError as exc:
            raise ValueError("Silky ARC legacy name is not CP932") from exc
        offset, size = struct.unpack_from("<II", data, pos)
        pos += 8
        if offset in seen or offset + size > len(data):
            raise ValueError(f"Silky ARC legacy member {name!r} exceeds the file")
        seen.add(offset)
        entries.append(ArcEntry(name, offset, size, size))
    return ArcArchive(pos, tuple(entries))


def read_member(data, entry):
    """Return member bytes, undoing LZSS when the two sizes differ."""
    raw = data[entry.offset:entry.offset + entry.size]
    if len(raw) != entry.size:
        raise ValueError("Silky ARC member is truncated")
    if not entry.packed:
        return raw
    return lzss_decompress(raw, entry.unpacked_size)


def build_arc(members, *, compress=True):
    """Write a ``TryOpen``-shaped archive from ``name -> bytes`` in given order."""
    if not isinstance(members, dict) or not 1 <= len(members) <= MAX_ENTRIES:
        raise ValueError("Silky ARC needs 1..16384 members")
    prepared, index_size = [], 0
    for name, payload in members.items():
        if not isinstance(name, str) or not isinstance(payload, bytes):
            raise ValueError("invalid Silky ARC member")
        try:
            encoded = name.encode("cp932", errors="strict") + b"\0"
        except UnicodeEncodeError as exc:
            raise ValueError(f"Silky ARC name is not CP932: {name!r}") from exc
        if len(encoded) - 1 > MAX_NAME:
            raise ValueError(f"Silky ARC name too long: {name!r}")
        stored = lzss_compress(payload) if compress and payload else b""
        if not stored or len(stored) == len(payload):
            stored = payload
        prepared.append((encrypt_name(encoded), stored, payload, len(payload)))
        index_size += 1 + len(encoded) + 12
    if index_size >= 1 << 32:
        raise ValueError("Silky ARC index too large")
    index, body = bytearray(), bytearray()
    for encoded, stored, payload, unpacked in prepared:
        index += bytes([len(encoded)]) + encoded
        index += struct.pack(">III", len(stored), unpacked,
                             HEADER_SIZE + index_size + len(body))
        body += stored
    if len(index) != index_size:
        raise ValueError("Silky ARC index size drifted")
    result = struct.pack("<I", index_size) + bytes(index) + bytes(body)
    archive = open_arc(result)
    if len(archive.entries) != len(members):
        raise ValueError("Silky ARC entry count changed on build")
    for entry, (name, payload) in zip(archive.entries, members.items()):
        if entry.name != name or read_member(result, entry) != payload:
            raise ValueError(f"Silky ARC member {name!r} does not round trip")
    return result


AI6_NAME = 260
AI6_RECORD = 272
AI6_MAX_NAME = 259


def decrypt_ai6_name(stored):
    """Undo the AI6WIN rolling add; the phase starts one above the length."""
    length = len(stored)
    return bytes((value - length - 1 + index) & 0xFF for index, value in enumerate(stored))


def encrypt_ai6_name(name):
    length = len(name)
    return bytes((value + length + 1 - index) & 0xFF for index, value in enumerate(name))


def open_ai6win(data):
    """Parse the AI6WIN directory (``Silky2`` option): 260-byte names, big-endian."""
    if not isinstance(data, bytes) or len(data) < 4 + AI6_RECORD:
        raise ValueError("AI6WIN archive too small")
    count = struct.unpack_from("<i", data, 0)[0]
    if not 1 <= count <= MAX_ENTRIES or 4 + count * AI6_RECORD > len(data):
        raise ValueError("AI6WIN entry count out of range")
    entries, pos = [], 4
    for _ in range(count):
        raw = data[pos:pos + AI6_NAME]
        pos += AI6_NAME
        cut = raw.find(b"\0")
        if cut <= 0:
            raise ValueError("AI6WIN name is not NUL terminated")
        try:
            name = decrypt_ai6_name(raw[:cut]).decode("cp932")
        except UnicodeDecodeError as exc:
            raise ValueError("AI6WIN name is not CP932") from exc
        stored, unpacked, offset = struct.unpack_from(">III", data, pos)
        pos += 12
        if stored > MAX_MEMBER or unpacked > MAX_MEMBER or offset + stored > len(data):
            raise ValueError(f"AI6WIN member {name!r} exceeds the file")
        entries.append(ArcEntry(name, offset, stored, unpacked))
    if len({entry.offset for entry in entries}) != len(entries):
        raise ValueError("AI6WIN duplicate member offset")
    return ArcArchive(pos, tuple(entries))


def build_ai6win(members, *, compress=True):
    """Write an AI6WIN archive from ``name -> bytes`` in given order."""
    if not isinstance(members, dict) or not 1 <= len(members) <= MAX_ENTRIES:
        raise ValueError("AI6WIN archive needs 1..16384 members")
    index_size = 4 + AI6_RECORD * len(members)
    index, body = bytearray(struct.pack("<i", len(members))), bytearray()
    for name, payload in members.items():
        if not isinstance(name, str) or not isinstance(payload, bytes):
            raise ValueError("invalid AI6WIN member")
        try:
            encoded = name.encode("cp932", errors="strict")
        except UnicodeEncodeError as exc:
            raise ValueError(f"AI6WIN name is not CP932: {name!r}") from exc
        if not encoded or len(encoded) > AI6_MAX_NAME:
            raise ValueError(f"AI6WIN name does not fit 260 bytes: {name!r}")
        stored = lzss_compress(payload) if compress and payload else b""
        if not stored or len(stored) == len(payload):
            stored = payload
        index += encrypt_ai6_name(encoded).ljust(AI6_NAME, b"\0")
        index += struct.pack(">III", len(stored), len(payload), index_size + len(body))
        body += stored
    if len(index) != index_size:
        raise ValueError("AI6WIN index size drifted")
    result = bytes(index) + bytes(body)
    archive = open_ai6win(result)
    for entry, (name, payload) in zip(archive.entries, members.items()):
        if entry.name != name or read_member(result, entry) != payload:
            raise ValueError(f"AI6WIN member {name!r} does not round trip")
    return result
