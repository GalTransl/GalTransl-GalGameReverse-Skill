# SPDX-License-Identifier: GPL-3.0-only
"""GxEngine GXP archive: 48-byte header, length-prefixed index, keyed XOR.

Header (little-endian, offsets from file start):
  0  u32  magic, ASCII ``GXP\\0`` (0x00505847)
  20 u32  crypt flag; non-zero means index and payloads are XORed
  24 i32  entry count
  28 i32  index size in bytes
  40 i32  payload area start (absolute); entry offsets are relative to it
  48 ...  index, then payloads

Index: repeated ``i32 total`` + body, where ``total = 36 + 2 * name_chars`` and
body = ``u32 size / 4 opaque / i32 name_chars / i32 c1 / i32 c2 / i32 offset /
4 pad / UTF-16LE name / 4 trailer``.

XOR stream (``j`` = byte index inside the stream):
    mask[j] = (j & 0xFF) ^ KEY[j % 23] ^ archive_ascii_name[j % len(name)]

The index stream restarts at every entry (the 4-byte length takes j = 0..3 and
the body continues at j = 4); payloads use the same formula from j = 0.

Provenance: structure and keystream come from ``GameRes.GxEngine.ArcGPX`` in the
GARbro-derived code bundled with the third-party tool "翻译肋手 v4.9D". This is an
independent rewrite with bounded parsing; every opaque field is kept so a
rebuild can reproduce the original index byte for byte.

Scope: read members, template repack (unchanged payloads stay in place, changed
ones are appended), index re-emission verified against the original. Not
supported: guessing a missing archive name (the keystream needs it), other
magics, or repairing an index whose opaque fields we would have to invent.
"""
from dataclasses import dataclass
import struct

MAGIC = 0x00505847
HEADER_SIZE = 48
KEY = bytes((64, 33, 40, 56, 166, 110, 67, 165, 64, 33, 40, 56, 166, 67, 165,
             100, 62, 101, 36, 32, 70, 110, 116))
OFF_CRYPT, OFF_COUNT, OFF_INDEX_SIZE, OFF_DATA = 20, 24, 28, 40
MAX_INDEX = 64 << 20
MAX_MEMBERS = 1_000_000
MAX_MEMBER = 256 << 20


@dataclass(frozen=True)
class GxpEntry:
    name: str
    size: int
    offset: int          # relative to the payload area
    c1: int
    c2: int
    opaque: bytes        # 4 bytes at body+4
    pad: bytes           # 4 bytes at body+24
    trailer: bytes       # 4 bytes after the name


@dataclass(frozen=True)
class GxpArchive:
    archive_name: str
    header: bytes
    crypt: int
    data_offset: int
    entries: tuple


def keystream(archive_name, length, start=0):
    """XOR mask for ``length`` bytes starting at stream index ``start``."""
    if not isinstance(archive_name, str) or not archive_name:
        raise ValueError("GXP keystream needs the archive file name")
    try:
        raw = archive_name.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError("GXP archive name must be ASCII") from exc
    return bytes((((start + j) & 0xFF) ^ KEY[(start + j) % 23] ^ raw[(start + j) % len(raw)])
                 for j in range(length))


def _xor(data, at, archive_name):
    return bytes(a ^ b for a, b in zip(data, keystream(archive_name, len(data), at)))


def _decrypt_index(index, archive_name):
    """Per-entry stream: 4-byte length at j=0..3, body continues at j=4."""
    out, pos = bytearray(index), 0
    while pos < len(out):
        if pos + 4 > len(out):
            raise ValueError("truncated encrypted GXP index entry")
        out[pos:pos + 4] = _xor(bytes(out[pos:pos + 4]), 0, archive_name)
        total, = struct.unpack_from("<i", out, pos)
        if total < 36 or pos + total > len(out):
            raise ValueError("encrypted GXP entry length out of range")
        out[pos + 4:pos + total] = _xor(bytes(out[pos + 4:pos + total]), 4, archive_name)
        pos += total
    return bytes(out)


def _encrypt_index(index, archive_name):
    out, pos = bytearray(index), 0
    while pos < len(out):
        total, = struct.unpack_from("<i", out, pos)
        if total < 36 or pos + total > len(out):
            raise ValueError("GXP index entry length out of range")
        out[pos:pos + 4] = _xor(bytes(out[pos:pos + 4]), 0, archive_name)
        out[pos + 4:pos + total] = _xor(bytes(out[pos + 4:pos + total]), 4, archive_name)
        pos += total
    return bytes(out)


def open_gpx(data, archive_name):
    """Parse header and index; every bound is checked before use."""
    if not isinstance(data, bytes) or len(data) < HEADER_SIZE:
        raise ValueError("GXP too small")
    if struct.unpack_from("<I", data, 0)[0] != MAGIC:
        raise ValueError("not a GXP archive")
    crypt, = struct.unpack_from("<I", data, OFF_CRYPT)
    count, = struct.unpack_from("<I", data, OFF_COUNT)
    index_size, = struct.unpack_from("<I", data, OFF_INDEX_SIZE)
    data_offset, = struct.unpack_from("<I", data, OFF_DATA)
    if not 0 <= count <= MAX_MEMBERS:
        raise ValueError("GXP entry count out of range")
    if index_size > MAX_INDEX or HEADER_SIZE + index_size > len(data):
        raise ValueError("GXP index exceeds the file")
    if not HEADER_SIZE + index_size <= data_offset <= len(data):
        raise ValueError("GXP payload offset is inconsistent")
    index = data[HEADER_SIZE:HEADER_SIZE + index_size]
    if crypt:
        index = _decrypt_index(index, archive_name)
    entries, pos = [], 0
    for _ in range(count):
        if pos + 4 > len(index):
            raise ValueError("truncated GXP index entry")
        total, = struct.unpack_from("<i", index, pos)
        if total < 36 or pos + total > len(index):
            raise ValueError("GXP index entry length out of range")
        body = index[pos + 4:pos + total]
        size, = struct.unpack_from("<I", body, 0)
        chars, c1, c2, offset = struct.unpack_from("<iiii", body, 8)
        if chars < 0 or 32 + chars * 2 != len(body):
            raise ValueError("GXP name length disagrees with the entry")
        try:
            name = body[28:28 + chars * 2].decode("utf-16-le")
        except UnicodeDecodeError as exc:
            raise ValueError("GXP name is not UTF-16LE") from exc
        if not name or "\0" in name or name.startswith(("/", "\\")) \
                or name.split("\\")[0].strip() in ("", ".", "..") or ".." in name.split("\\"):
            raise ValueError(f"unsafe GXP member name {name!r}")
        if offset < 0 or size > MAX_MEMBER or offset > len(data) - data_offset - size:
            raise ValueError(f"GXP member {name!r} exceeds the payload area")
        entries.append(GxpEntry(name, size, offset, c1, c2, body[4:8], body[24:28],
                                body[28 + chars * 2:]))
        pos += total
    if pos != len(index):
        raise ValueError("trailing bytes in the GXP index")
    return GxpArchive(archive_name, data[:HEADER_SIZE], crypt, data_offset, tuple(entries))


def read_member(data, archive, entry, *, max_size=MAX_MEMBER):
    start = archive.data_offset + entry.offset
    raw = data[start:start + entry.size]
    if len(raw) != entry.size:
        raise ValueError("truncated GXP member")
    if entry.size > max_size:
        raise ValueError("GXP member exceeds budget")
    return _xor(raw, 0, archive.archive_name) if archive.crypt else raw


def _emit_index(entries):
    out = bytearray()
    for entry in entries:
        name = entry.name.encode("utf-16-le", errors="strict")
        out += struct.pack("<i", 36 + len(name))
        out += struct.pack("<I", entry.size) + entry.opaque
        out += struct.pack("<iiii", len(name) // 2, entry.c1, entry.c2, entry.offset)
        out += entry.pad + name + entry.trailer
    return bytes(out)


def pack_gpx(template, archive_name, replacements):
    """Template repack; the rebuilt index must reproduce the original exactly."""
    archive = open_gpx(template, archive_name)
    if not isinstance(replacements, dict) or set(replacements) - {e.name for e in archive.entries}:
        raise ValueError("unknown GXP member")
    index_size, = struct.unpack_from("<I", template, OFF_INDEX_SIZE)
    original = template[HEADER_SIZE:HEADER_SIZE + index_size]
    plain = _decrypt_index(original, archive_name) if archive.crypt else original
    data_region = template[archive.data_offset:]
    appended, updated = bytearray(), []
    for entry in archive.entries:
        if entry.name not in replacements:
            updated.append(entry)
            continue
        raw = replacements[entry.name]
        if not isinstance(raw, bytes) or len(raw) > MAX_MEMBER:
            raise ValueError("invalid GXP member payload")
        stored = _xor(raw, 0, archive_name) if archive.crypt else raw
        updated.append(GxpEntry(entry.name, len(raw), len(data_region) + len(appended),
                                entry.c1, entry.c2, entry.opaque, entry.pad, entry.trailer))
        appended += stored
    index = _emit_index(updated)
    if not appended and index != plain:
        raise ValueError("GXP index is not reproducible; refusing to repack")
    stored_index = _encrypt_index(index, archive_name) if archive.crypt else index
    header = bytearray(archive.header)
    struct.pack_into("<I", header, OFF_COUNT, len(updated))
    struct.pack_into("<I", header, OFF_INDEX_SIZE, len(stored_index))
    struct.pack_into("<I", header, OFF_DATA, HEADER_SIZE + len(stored_index))
    result = bytes(header) + stored_index + bytes(data_region) + bytes(appended)
    check = open_gpx(result, archive_name)
    if len(check.entries) != len(updated):
        raise ValueError("GXP entry count changed on rebuild")
    for before, after in zip(updated, check.entries):
        if (before.name, before.size, before.offset, before.c1, before.c2) != \
                (after.name, after.size, after.offset, after.c1, after.c2):
            raise ValueError("GXP entry round trip differs")
    return result
