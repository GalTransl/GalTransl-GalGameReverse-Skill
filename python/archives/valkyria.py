# SPDX-License-Identifier: GPL-3.0-only
"""VALKYRIA ``.dat`` archive: 268-byte records, offsets relative to payload.

Layout: ``u32 index_size`` at 0, where ``index_size`` must be a multiple of 268.
Records start at 4, each ``char name[260]`` (CP932, NUL padded) plus ``u32
offset`` and ``u32 size`` (both little-endian). Offsets are relative to the
payload start, which is ``4 + index_size``.

Provenance: header, record width and the relative offset rule follow
``GameRes.VALKYRIA.ArcDAT`` in the GARbro-derived code bundled with
"翻译肋手 v4.9D". Independent rewrite: bounded record count, explicit NUL
requirement, and a writer that computes the index size from the member count
instead of trusting a caller-supplied value.
"""
from dataclasses import dataclass
import struct

HEADER_SIZE = 4
RECORD_SIZE = 268
NAME_SIZE = 260
MAX_ENTRIES = 4000
MAX_MEMBER = 256 << 20
MAX_NAME = 259


@dataclass(frozen=True)
class DatEntry:
    name: str
    offset: int
    size: int


@dataclass(frozen=True)
class DatArchive:
    index_size: int
    entries: tuple


def open_dat(data):
    """Parse the directory; returns absolute member offsets."""
    if not isinstance(data, bytes) or len(data) < HEADER_SIZE + RECORD_SIZE:
        raise ValueError("VALKYRIA dat too small")
    index_size, = struct.unpack_from("<I", data, 0)
    if index_size == 0 or index_size % RECORD_SIZE:
        raise ValueError("VALKYRIA index size is not a multiple of 268")
    count = index_size // RECORD_SIZE
    if count > MAX_ENTRIES or HEADER_SIZE + index_size > len(data):
        raise ValueError("VALKYRIA index exceeds the file")
    payload = HEADER_SIZE + index_size
    entries, pos = [], HEADER_SIZE
    for _ in range(count):
        raw = data[pos:pos + NAME_SIZE]
        pos += NAME_SIZE
        cut = raw.find(b"\0")
        if cut <= 0:
            raise ValueError("VALKYRIA member name is not NUL terminated")
        try:
            name = raw[:cut].decode("cp932")
        except UnicodeDecodeError as exc:
            raise ValueError("VALKYRIA member name is not CP932") from exc
        offset, size = struct.unpack_from("<II", data, pos)
        pos += 8
        absolute = payload + offset
        if size > MAX_MEMBER or absolute + size > len(data):
            raise ValueError(f"VALKYRIA member {name!r} exceeds the file")
        entries.append(DatEntry(name, absolute, size))
    if len(entries) > 1 and len({entry.offset for entry in entries}) != len(entries):
        raise ValueError("VALKYRIA duplicate member offset")
    return DatArchive(index_size, tuple(entries))


def read_member(data, entry):
    raw = data[entry.offset:entry.offset + entry.size]
    if len(raw) != entry.size:
        raise ValueError("VALKYRIA member is truncated")
    return raw


def build_dat(members):
    """Write a complete ``.dat`` from ``name -> bytes`` in insertion order."""
    if not isinstance(members, dict) or not 1 <= len(members) <= MAX_ENTRIES:
        raise ValueError("VALKYRIA dat needs 1..4000 members")
    index, body = bytearray(), bytearray()
    for name, payload in members.items():
        if not isinstance(name, str) or not isinstance(payload, bytes):
            raise ValueError("invalid VALKYRIA member")
        try:
            encoded = name.encode("cp932", errors="strict")
        except UnicodeEncodeError as exc:
            raise ValueError(f"VALKYRIA name is not CP932: {name!r}") from exc
        if not encoded or len(encoded) > MAX_NAME:
            raise ValueError(f"VALKYRIA name does not fit 260 bytes: {name!r}")
        if len(payload) > MAX_MEMBER:
            raise ValueError(f"VALKYRIA member {name!r} is too large")
        index += encoded.ljust(NAME_SIZE, b"\0")
        index += struct.pack("<II", len(body), len(payload))
        body += payload
    if len(index) != len(members) * RECORD_SIZE:
        raise ValueError("VALKYRIA index size drifted")
    result = struct.pack("<I", len(index)) + bytes(index) + bytes(body)
    archive = open_dat(result)
    if len(archive.entries) != len(members):
        raise ValueError("VALKYRIA entry count changed on build")
    for entry, (name, payload) in zip(archive.entries, members.items()):
        if entry.name != name or read_member(result, entry) != payload:
            raise ValueError(f"VALKYRIA member {name!r} does not round trip")
    return result
