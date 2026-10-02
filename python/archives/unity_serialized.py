# SPDX-License-Identifier: GPL-3.0-only
"""Bounded Unity serialized-file v20 (little endian, stripped TypeTrees).

Standard-library implementation of the published serialized-file layout.
No Unity runtime, game assemblies, textures or external resource files loaded.
This is not a UnityFS reader or a general TypeTree serializer.
"""
from dataclasses import dataclass
import io
from pathlib import Path
import stat
import struct

from ..common.binary import FormatError
from ..common.safety import _check_existing_ancestors

MAX_METADATA = 16 << 20
MAX_OBJECT = 32 << 20
MAX_REBUILD = 128 << 20
MAX_SCAN = 16 << 30


class Reader:
    def __init__(self, data, pos=0):
        if not 0 <= pos <= len(data):
            raise FormatError("invalid Unity reader offset")
        self.data, self.pos = data, pos

    def take(self, size):
        if size < 0 or self.pos + size > len(self.data):
            raise FormatError(f"truncated Unity data at {self.pos:#x}")
        result = self.data[self.pos:self.pos + size]
        self.pos += size
        return result

    def number(self, fmt="i"):
        return struct.unpack("<" + fmt, self.take(struct.calcsize("<" + fmt)))[0]

    def count(self, limit=200000):
        n = self.number()
        if not 0 <= n <= limit:
            raise FormatError(f"Unity array count outside budget at {self.pos - 4:#x}: {n}")
        return n

    def align(self, alignment=4):
        if any(self.take(-self.pos % alignment)):
            raise FormatError("nonzero Unity alignment padding")

    def cstring(self, limit=4096):
        end = self.data.find(b"\0", self.pos, min(len(self.data), self.pos + limit + 1))
        if end < 0:
            raise FormatError("unterminated Unity metadata string")
        value = self.take(end - self.pos).decode("utf-8", "strict")
        self.take(1)
        return value

    def string(self, limit=1 << 20):
        n = self.count(limit)
        value = self.take(n).decode("utf-8", "strict")
        self.align()
        return value


@dataclass(frozen=True)
class Object:
    path_id: int
    offset: int
    size: int
    type_index: int
    class_id: int
    table_offset: int


@dataclass(frozen=True)
class Index:
    size: int
    data_offset: int
    metadata: bytes
    unity_version: str
    platform: int
    objects: tuple
    externals: tuple


def read_index(stream):
    stream.seek(0, 2)
    size = stream.tell()
    if not 20 <= size <= MAX_SCAN:
        raise FormatError("Unity serialized file exceeds scan budget")
    stream.seek(0)
    header = stream.read(20)
    if len(header) != 20:
        raise FormatError("truncated Unity header")
    metadata_size, declared, version, data_offset = struct.unpack(">4I", header[:16])
    if version != 20 or header[16:] != bytes(4):
        raise FormatError("expected little-endian Unity serialized v20")
    if declared != size or not 0 < metadata_size <= MAX_METADATA or not 20 + metadata_size <= data_offset <= size:
        raise FormatError("Unity header size/metadata bounds differ")
    metadata = header + stream.read(metadata_size)
    if len(metadata) != 20 + metadata_size:
        raise FormatError("truncated Unity metadata")
    r = Reader(metadata, 20)
    unity_version, platform = r.cstring(128), r.number()
    if r.number("B") != 0:
        raise FormatError("this Unity v20 profile requires stripped TypeTrees")
    classes = []
    for _ in range(r.count(4096)):
        class_id = r.number()
        stripped = r.number("B")
        r.number("h")  # script type index; preserved in metadata
        if class_id < 0 or stripped not in (0, 1):
            raise FormatError("invalid Unity serialized type")
        if class_id == 114:
            r.take(16)
        r.take(16)
        classes.append(class_id)
    objects, identifiers = [], set()
    for _ in range(r.count()):
        r.align()
        path_id = r.number("q")
        table_offset = r.pos
        offset, length, type_id = r.number("I"), r.number("I"), r.number()
        if (path_id in identifiers or not 0 <= type_id < len(classes)
                or data_offset + offset + length > size):
            raise FormatError("invalid Unity object identity/type/range")
        identifiers.add(path_id)
        objects.append(Object(path_id, data_offset + offset, length, type_id, classes[type_id], table_offset))
    for _ in range(r.count()):
        r.number()
        r.align()
        r.number("q")
    externals = []
    for _ in range(r.count(4096)):
        r.cstring()
        r.take(16)
        r.number()
        externals.append(r.cstring())
    if r.count(4096):
        raise FormatError("Unity reference types require another profile")
    r.cstring()
    if r.pos != len(metadata):
        raise FormatError("unparsed Unity v20 metadata tail")
    end = data_offset
    for obj in sorted(objects, key=lambda o: o.offset):
        if obj.offset < end:
            raise FormatError("overlapping Unity objects")
        end = obj.offset + obj.size
    return Index(size, data_offset, metadata, unity_version, platform, tuple(objects), tuple(externals))


def open_checked(path):
    path = Path(path)
    _check_existing_ancestors(path.parent)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or getattr(info, "st_file_attributes", 0) & 0x400:
        raise FormatError("Unity input must be an ordinary unlinked file")
    return path.open("rb")


def read_object(stream, obj, *, prefix=None):
    size = obj.size if prefix is None else min(obj.size, prefix)
    if not 0 <= size <= MAX_OBJECT:
        raise FormatError("Unity object exceeds read budget")
    stream.seek(obj.offset)
    data = stream.read(size)
    if len(data) != size:
        raise FormatError("truncated Unity object")
    return data


def read_file(path):
    with open_checked(path) as stream:
        index = read_index(stream)
        if index.size > MAX_REBUILD:
            raise FormatError("Unity file exceeds in-memory rebuild budget; index scan is still supported")
        stream.seek(0)
        data = stream.read(MAX_REBUILD + 1)
    if len(data) != index.size or read_index(io.BytesIO(data)) != index:
        raise FormatError("Unity source changed while reading")
    return data, index


def rebuild(data, replacements):
    if len(data) > MAX_REBUILD:
        raise FormatError("Unity file exceeds rebuild budget")
    index = read_index(io.BytesIO(data))
    if set(replacements) - {o.path_id for o in index.objects}:
        raise FormatError("unknown Unity replacement PathID")
    projected = len(data)
    for o in index.objects:
        if o.path_id in replacements:
            new = replacements[o.path_id]
            if not isinstance(new, bytes) or len(new) > MAX_OBJECT:
                raise FormatError("Unity replacement object exceeds budget")
            projected += len(new) - o.size + 7
    if projected > MAX_REBUILD:
        raise FormatError("rebuilt Unity file exceeds budget")
    out, cursor = bytearray(data[:index.data_offset]), index.data_offset
    for obj in sorted(index.objects, key=lambda o: o.offset):
        if obj.offset % 8:
            raise FormatError("Unity writer requires eight-byte object alignment")
        padding = -cursor % 8
        if cursor + padding > obj.offset or any(data[cursor:cursor + padding]):
            raise FormatError("unexpected Unity inter-object alignment")
        out.extend(bytes(-len(out) % 8))
        out.extend(data[cursor + padding:obj.offset])
        position = len(out)
        payload = replacements.get(obj.path_id, data[obj.offset:obj.offset + obj.size])
        out.extend(payload)
        struct.pack_into("<II", out, obj.table_offset, position - index.data_offset, len(payload))
        cursor = obj.offset + obj.size
    out.extend(data[cursor:])
    struct.pack_into(">I", out, 4, len(out))
    result = bytes(out)
    after = read_index(io.BytesIO(result))
    masked = bytearray(after.metadata)
    masked[4:8] = index.metadata[4:8]
    for old, new in zip(index.objects, after.objects):
        if (old.path_id, old.class_id, old.type_index) != (new.path_id, new.class_id, new.type_index):
            raise FormatError("Unity object identity changed")
        masked[old.table_offset:old.table_offset + 8] = index.metadata[old.table_offset:old.table_offset + 8]
        expected = replacements.get(old.path_id, data[old.offset:old.offset + old.size])
        if result[new.offset:new.offset + new.size] != expected:
            raise FormatError("Unity object differs after rebuilding")
    if bytes(masked) != index.metadata:
        raise FormatError("Unity non-object metadata changed")
    return result
