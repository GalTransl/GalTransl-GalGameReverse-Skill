# SPDX-License-Identifier: GPL-3.0-only
"""Kaguya LINK6 sequential records; writer for uncompressed, unencrypted data.

Layout reference: GARbro-Mod bc26d991ef5cdc0e1ecb32122ee9a48c3375750c,
ArcFormats/Kaguya/ArcLINK.cs, LinkReader/Link6Reader. Copyright (C) 2016-2017
morkt, MIT; notice in provenance/licenses/MIT-GARbro.txt. Bounds/writer are new.
No graphics decryption or BMR/LZ decompression is implied by index support.
"""
from dataclasses import dataclass
import io
import struct

from ..common.binary import FormatError
from ..common.safety import Limits, validate_names


@dataclass(frozen=True)
class Entry:
    name: str
    flags: int
    offset: int
    size: int
    record_header: bytes


@dataclass(frozen=True)
class Index:
    prefix: bytes
    entries: tuple[Entry, ...]
    size: int


def _read(stream, count):
    raw = stream.read(count)
    if len(raw) != count:
        raise FormatError("truncated LINK6")
    return raw


def read_index(stream, *, limits: Limits = Limits()) -> Index:
    stream.seek(0, 2)
    size = stream.tell()
    stream.seek(0)
    header = _read(stream, 8)
    if header[:5] != b"LINK6":
        raise FormatError("expected LINK6, not a different LINK dialect")
    prefix = header + _read(stream, header[7])
    entries = []
    while True:
        start = stream.tell()
        raw_size = _read(stream, 4)
        record_size = struct.unpack("<I", raw_size)[0]
        if record_size == 0:
            if stream.tell() != size:
                raise FormatError("trailing bytes after LINK6 terminator")
            break
        if len(entries) >= limits.max_entries or record_size < 17 or start + record_size > size - 4:
            raise FormatError("LINK6 record count/range exceeds bounds")
        fixed = _read(stream, 11)
        flags = struct.unpack_from("<H", fixed)[0]
        name_size = struct.unpack_from("<H", fixed, 9)[0]
        if name_size == 0 or name_size % 2 or name_size > 0x400 or 15 + name_size > record_size:
            raise FormatError("invalid LINK6 UTF16 name length")
        name_raw = _read(stream, name_size)
        try:
            name = name_raw.decode("utf-16-le", errors="strict")
        except UnicodeError as exc:
            raise FormatError("invalid LINK6 name") from exc
        offset = stream.tell()
        entries.append(Entry(name, flags, offset, record_size - 15 - name_size,
                             raw_size + fixed + name_raw))
        stream.seek(start + record_size)
    validate_names([e.name for e in entries], limits)
    return Index(prefix, tuple(entries), size)


def read_member(stream, index: Index, entry: Entry, *, limits: Limits = Limits()) -> bytes:
    if entry not in index.entries or entry.size > limits.max_file_bytes:
        raise FormatError("LINK6 member identity/budget mismatch")
    if entry.flags != 0:
        raise FormatError("this LINK6 reader does not decode compressed/encrypted members")
    stream.seek(entry.offset)
    return _read(stream, entry.size)


def rebuild(stream, index: Index, replacements: dict[str, bytes], *, limits: Limits = Limits()) -> bytes:
    if set(replacements) - {e.name for e in index.entries}:
        raise FormatError("unknown LINK6 replacement")
    if index.size > limits.max_total_bytes:
        raise FormatError("LINK6 input exceeds rebuild budget")
    out = bytearray(index.prefix)
    for entry in index.entries:
        if entry.name in replacements:
            if entry.flags:
                raise FormatError("cannot replace an encoded LINK6 member")
            payload = replacements[entry.name]
            if not isinstance(payload, bytes) or len(payload) > limits.max_file_bytes:
                raise FormatError("LINK6 replacement exceeds budget")
        else:
            if entry.size > limits.max_file_bytes:
                raise FormatError("LINK6 stored member exceeds budget")
            stream.seek(entry.offset)
            payload = _read(stream, entry.size)
        new_size = len(entry.record_header) + len(payload)
        if len(out) + new_size + 4 > limits.max_total_bytes:
            raise FormatError("LINK6 output exceeds budget")
        out.extend(struct.pack("<I", new_size) + entry.record_header[4:])
        out.extend(payload)
    out.extend(b"\0" * 4)
    result = bytes(out)
    read_index(io.BytesIO(result), limits=limits)
    return result
