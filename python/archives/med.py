# SPDX-License-Identifier: MIT
"""Bounded plaintext MDN0 index reader and template-preserving archive writer.

Index layout adapted from GARbro ArcFormats/DxLib/ArcMED.cs.
Copyright (C) 2016 by morkt

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""
from dataclasses import dataclass
import io
from pathlib import Path
import stat
import struct

from ..common.binary import FormatError
from ..common.safety import _check_existing_ancestors, validate_names

MAX_ARCHIVE = 64 << 20
MAX_MEMBER = 8 << 20
MAX_ENTRIES = 4096


@dataclass(frozen=True)
class Entry:
    name: str
    offset: int
    size: int
    slot: int


def index(stream, size):
    """Read only header/index, validate all ranges before reading any payload."""
    if not 16 <= size <= MAX_ARCHIVE:
        raise FormatError("MDN0 archive size outside budget")
    stream.seek(0)
    header = stream.read(16)
    if len(header) != 16 or header[:4] != b"MDN0":
        raise FormatError("expected plaintext MDN0 script archive")
    width, count = struct.unpack_from("<HH", header, 4)
    if not 9 <= width <= 1024 or not 1 <= count <= MAX_ENTRIES:
        raise FormatError("MDN0 index dimensions outside budget")
    end = 16 + width * count
    if end > size:
        raise FormatError("truncated MDN0 index")
    table = stream.read(end - 16)
    if len(table) != end - 16:
        raise FormatError("truncated MDN0 index")
    entries = []
    for i in range(count):
        slot = i * width
        raw_name = table[slot:slot + width - 8].split(b"\0", 1)[0]
        try:
            name = raw_name.decode("cp932", "strict")
        except UnicodeError as exc:
            raise FormatError("invalid MDN0 member name encoding") from exc
        length, offset = struct.unpack_from("<II", table, slot + width - 8)
        if length > MAX_MEMBER or offset < end or offset + length > size:
            raise FormatError(f"MDN0 member range/budget: {name}")
        entries.append(Entry(name, offset, length, 16 + slot + width - 8))
    names = [e.name for e in entries]
    if validate_names(names) != names or any("/" in n or "\\" in n for n in names):
        raise FormatError("MDN0 requires unique flat member names")
    last = end
    for e in sorted(entries, key=lambda e: e.offset):
        if e.offset < last:
            raise FormatError("overlapping MDN0 members")
        last = e.offset + e.size
    return entries


def read_member(stream, entry):
    if not 0 <= entry.size <= MAX_MEMBER or entry.offset < 16:
        raise FormatError("invalid MDN0 member range")
    stream.seek(entry.offset)
    data = stream.read(entry.size)
    if len(data) != entry.size:
        raise FormatError("truncated MDN0 member")
    return data


def read_archive(path):
    path = Path(path)
    _check_existing_ancestors(path.parent)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or getattr(info, "st_file_attributes", 0) & 0x400:
        raise FormatError("MDN0 input must be an ordinary unlinked file")
    with path.open("rb") as stream:
        entries = index(stream, info.st_size)
        stream.seek(0)
        data = stream.read(MAX_ARCHIVE + 1)
    if len(data) != info.st_size:
        raise FormatError("MDN0 input size changed")
    if index(io.BytesIO(data), len(data)) != entries:
        raise FormatError("MDN0 index changed during read")
    return data, entries


def rebuild(data, replacements):
    entries = index(io.BytesIO(data), len(data))
    if set(replacements) - {e.name for e in entries}:
        raise FormatError("unknown MDN0 replacement member")
    total = len(data)
    for e in entries:
        value = replacements.get(e.name)
        if value is not None:
            if not isinstance(value, bytes) or len(value) > MAX_MEMBER:
                raise FormatError("MDN0 replacement exceeds budget")
            total += len(value) - e.size
        elif e.name in replacements:
            raise FormatError("MDN0 replacement must be bytes")
    if total > MAX_ARCHIVE:
        raise FormatError("rebuilt MDN0 exceeds budget")
    # Preserve physical order, index order, name padding, gaps and trailer.
    out = bytearray()
    cursor = 0
    for e in sorted(entries, key=lambda e: e.offset):
        out.extend(data[cursor:e.offset])
        position = len(out)
        value = replacements.get(e.name, data[e.offset:e.offset + e.size])
        out.extend(value)
        struct.pack_into("<II", out, e.slot, len(value), position)
        cursor = e.offset + e.size
    out.extend(data[cursor:])
    result = bytes(out)
    after = index(io.BytesIO(result), len(result))
    for old, new in zip(entries, after):
        expected = replacements.get(old.name, data[old.offset:old.offset + old.size])
        if result[new.offset:new.offset + new.size] != expected:
            raise FormatError("MDN0 rebuilt member mismatch")
    return result
