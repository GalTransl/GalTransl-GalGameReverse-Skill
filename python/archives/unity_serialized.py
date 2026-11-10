# SPDX-License-Identifier: GPL-3.0-only
"""Bounded Unity serialized files, format versions 17-22, little endian.

Parses the header (including the 64-bit header of v22), type table with or
without TypeTrees (v17-v22 node layouts, local and common string tables),
object table (aligned 64-bit PathIDs; 64-bit offsets in v22), script types,
externals and reference types. A generic TypeTree walker reads an object and
reports top-level field spans. ``rebuild`` relocates replaced objects and
keeps every other object, gap and metadata byte.

Standard-library implementation of the published serialized-file layout; see
provenance/unity-containers.json. No Unity runtime, game assemblies, textures
or external resource files are loaded. Big-endian files, versions outside
17-22 and ``ManagedReferencesRegistry`` payloads are rejected.
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
MAX_OBJECTS = 1 << 22
MAX_TYPE_NODES = 1 << 16
MAX_WALK_STEPS = 1 << 22
VERSIONS = range(17, 23)
ALIGN_FLAG = 0x4000

# Unity's built-in TypeTree string table (offset = cumulative NUL-terminated).
COMMON_STRINGS = (
    "AABB", "AnimationClip", "AnimationCurve", "AnimationState", "Array", "Base", "BitField",
    "bitset", "bool", "char", "ColorRGBA", "Component", "data", "deque", "double", "dynamic_array",
    "FastPropertyName", "first", "float", "Font", "GameObject", "Generic Mono", "GradientNEW",
    "GUID", "GUIStyle", "int", "list", "long long", "map", "Matrix4x4f", "MdFour", "MonoBehaviour",
    "MonoScript", "m_ByteSize", "m_Curve", "m_EditorClassIdentifier", "m_EditorHideFlags",
    "m_Enabled", "m_ExtensionPtr", "m_GameObject", "m_Index", "m_IsArray", "m_IsStatic",
    "m_MetaFlag", "m_Name", "m_ObjectHideFlags", "m_PrefabInternal", "m_PrefabParentObject",
    "m_Script", "m_StaticEditorFlags", "m_Type", "m_Version", "Object", "pair", "PPtr<Component>",
    "PPtr<GameObject>", "PPtr<Material>", "PPtr<MonoBehaviour>", "PPtr<MonoScript>",
    "PPtr<Object>", "PPtr<Prefab>", "PPtr<Sprite>", "PPtr<TextAsset>", "PPtr<Texture>",
    "PPtr<Texture2D>", "PPtr<Transform>", "Prefab", "Quaternionf", "Rectf", "RectInt",
    "RectOffset", "second", "set", "short", "size", "SInt16", "SInt32", "SInt64", "SInt8",
    "staticvector", "string", "TextAsset", "TextMesh", "Texture", "Texture2D", "Transform",
    "TypelessData", "UInt16", "UInt32", "UInt64", "UInt8", "unsigned int", "unsigned long long",
    "unsigned short", "vector", "Vector2f", "Vector3f", "Vector4f", "m_ScriptingClassIdentifier",
    "Gradient", "Type*", "int2_storage", "int3_storage", "BoundsInt",
    "m_CorrespondingSourceObject", "m_PrefabInstance", "m_PrefabAsset", "FileSize", "Hash128",
    "RenderingLayerMask",
)
COMMON = {}
_offset = 0
for _name in COMMON_STRINGS:
    COMMON[_offset] = _name
    _offset += len(_name) + 1
del _offset, _name

PRIMITIVES = {
    "bool": 1, "char": 1, "SInt8": 1, "UInt8": 1, "SInt16": 2, "UInt16": 2, "short": 2,
    "unsigned short": 2, "SInt32": 4, "UInt32": 4, "int": 4, "unsigned int": 4, "float": 4,
    "Type*": 4, "SInt64": 8, "UInt64": 8, "long long": 8, "unsigned long long": 8, "double": 8,
    "FileSize": 8,
}
_FORMATS = {1: "B", 2: "H", 4: "I", 8: "Q"}
_SIGNED = {"SInt8": "b", "SInt16": "h", "short": "h", "SInt32": "i", "int": "i",
           "SInt64": "q", "long long": "q", "float": "f", "double": "d"}


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
class TypeNode:
    version: int
    level: int
    flags: int
    type: str
    name: str
    byte_size: int
    index: int
    meta_flag: int
    ref_hash: int


@dataclass(frozen=True)
class SerializedType:
    class_id: int
    stripped: int
    script_index: int
    script_id: bytes
    type_hash: bytes
    nodes: tuple
    dependencies: tuple = ()
    ref_names: tuple = ()


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
    version: int = 20
    type_tree: bool = False
    types: tuple = ()
    scripts: tuple = ()
    ref_types: tuple = ()
    header_size: int = 20

    @property
    def offset_width(self):
        return 8 if self.version >= 22 else 4


def _type_string(offset, local):
    if offset & 0x80000000:
        return COMMON.get(offset & 0x7FFFFFFF)  # None: unknown common string
    if offset >= len(local):
        raise FormatError("TypeTree string offset outside local table")
    end = local.find(b"\0", offset)
    if end < 0:
        raise FormatError("unterminated TypeTree local string")
    return local[offset:end].decode("utf-8", "strict")


def read_type_tree(r, version):
    count = r.count(MAX_TYPE_NODES)
    string_size = r.count(MAX_METADATA)
    width = 32 if version >= 19 else 24
    raw = r.take(count * width)
    local = r.take(string_size)
    nodes = []
    for i in range(count):
        fields = struct.unpack_from("<HBBIIiii", raw, i * width)
        ref_hash = struct.unpack_from("<Q", raw, i * width + 24)[0] if width == 32 else 0
        node = TypeNode(fields[0], fields[1], fields[2], _type_string(fields[3], local),
                        _type_string(fields[4], local), fields[5], fields[6], fields[7], ref_hash)
        if (i == 0 and node.level != 0) or (i and not 1 <= node.level <= nodes[-1].level + 1):
            raise FormatError("invalid TypeTree node levels")
        nodes.append(node)
    if not nodes:
        raise FormatError("empty TypeTree")
    return tuple(nodes)


def _read_type(r, version, tree, ref):
    class_id = r.number()
    stripped = r.number("B")
    script_index = r.number("h")
    if (not ref and class_id < 0) or stripped not in (0, 1) or script_index < -1:
        raise FormatError("invalid Unity serialized type")
    script_id = r.take(16) if (ref and script_index >= 0) or (not ref and class_id == 114) else b""
    type_hash = r.take(16)
    nodes, dependencies, ref_names = (), (), ()
    if tree:
        nodes = read_type_tree(r, version)
        if version >= 21:
            if ref:
                ref_names = (r.cstring(), r.cstring(), r.cstring())
            else:
                dependencies = tuple(r.number() for _ in range(r.count(MAX_TYPE_NODES)))
    return SerializedType(class_id, stripped, script_index, script_id, type_hash, nodes, dependencies, ref_names)


def read_header(head, size):
    """Return ``(version, header_size, metadata_size, data_offset)``; strict."""
    if len(head) < 20:
        raise FormatError("truncated Unity header")
    metadata_size, declared, version, data_offset = struct.unpack(">4I", head[:16])
    if version not in VERSIONS:
        raise FormatError(f"unsupported Unity serialized version {version} (supported 17-22)")
    if head[16] != 0 or any(head[17:20]):
        raise FormatError("expected little-endian Unity serialized file")
    header_size = 20
    if version >= 22:
        if len(head) < 48:
            raise FormatError("truncated Unity v22 header")
        if (metadata_size, declared, data_offset) != (0, 0, 0):
            raise FormatError("unexpected legacy fields in Unity v22 header")
        metadata_size, declared, data_offset, unknown = struct.unpack_from(">IqqQ", head, 20)
        if unknown:
            raise FormatError("unknown nonzero field in Unity v22 header")
        header_size = 48
    if (declared != size or not 0 < metadata_size <= MAX_METADATA
            or not header_size + metadata_size <= data_offset <= size):
        raise FormatError("Unity header size/metadata bounds differ")
    return version, header_size, metadata_size, data_offset


def read_index(stream):
    stream.seek(0, 2)
    size = stream.tell()
    if not 20 <= size <= MAX_SCAN:
        raise FormatError("Unity serialized file exceeds scan budget")
    stream.seek(0)
    head = stream.read(48)
    version, header_size, metadata_size, data_offset = read_header(head, size)
    stream.seek(0)
    metadata = stream.read(header_size + metadata_size)
    if len(metadata) != header_size + metadata_size:
        raise FormatError("truncated Unity metadata")
    r = Reader(metadata, header_size)
    unity_version, platform = r.cstring(128), r.number()
    tree = r.number("B")
    if tree not in (0, 1):
        raise FormatError("invalid Unity TypeTree flag")
    types = tuple(_read_type(r, version, tree, False) for _ in range(r.count(4096)))
    objects, identifiers = [], set()
    wide = version >= 22
    for _ in range(r.count(MAX_OBJECTS)):
        r.align()
        path_id = r.number("q")
        table_offset = r.pos
        offset = r.number("q" if wide else "I")
        length, type_id = r.number("I"), r.number()
        if (path_id in identifiers or not 0 <= type_id < len(types) or offset < 0
                or data_offset + offset + length > size):
            raise FormatError("invalid Unity object identity/type/range")
        identifiers.add(path_id)
        objects.append(Object(path_id, data_offset + offset, length, type_id, types[type_id].class_id, table_offset))
    scripts = []
    for _ in range(r.count()):
        file_index = r.number()
        r.align()
        scripts.append((file_index, r.number("q")))
    externals = []
    for _ in range(r.count(4096)):
        r.cstring()
        r.take(16)
        r.number()
        externals.append(r.cstring())
    ref_types = ()
    if version >= 20:
        ref_types = tuple(_read_type(r, version, tree, True) for _ in range(r.count(4096)))
    r.cstring()
    if r.pos != len(metadata):
        raise FormatError(f"unparsed Unity v{version} metadata tail")
    end = data_offset
    for obj in sorted(objects, key=lambda o: o.offset):
        if obj.offset < end:
            raise FormatError("overlapping Unity objects")
        end = obj.offset + obj.size
    return Index(size, data_offset, metadata, unity_version, platform, tuple(objects), tuple(externals),
                 version, bool(tree), types, tuple(scripts), ref_types, header_size)


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
    wide = index.version >= 22
    entry = "<qI" if wide else "<II"
    entry_size = struct.calcsize(entry)
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
        struct.pack_into(entry, out, obj.table_offset, position - index.data_offset, len(payload))
        cursor = obj.offset + obj.size
    out.extend(data[cursor:])
    size_field = (24, ">q") if wide else (4, ">I")
    struct.pack_into(size_field[1], out, size_field[0], len(out))
    result = bytes(out)
    after = read_index(io.BytesIO(result))
    masked = bytearray(after.metadata)
    width = 8 if wide else 4
    masked[size_field[0]:size_field[0] + width] = index.metadata[size_field[0]:size_field[0] + width]
    for old, new in zip(index.objects, after.objects):
        if (old.path_id, old.class_id, old.type_index) != (new.path_id, new.class_id, new.type_index):
            raise FormatError("Unity object identity changed")
        masked[old.table_offset:old.table_offset + entry_size] = index.metadata[old.table_offset:old.table_offset + entry_size]
        expected = replacements.get(old.path_id, data[old.offset:old.offset + old.size])
        if result[new.offset:new.offset + new.size] != expected:
            raise FormatError("Unity object differs after rebuilding")
    if bytes(masked) != index.metadata:
        raise FormatError("Unity non-object metadata changed")
    return result


# --- TypeTree object walker -------------------------------------------------

@dataclass(frozen=True)
class Field:
    name: str
    type: str
    start: int
    end: int  # after any alignment padding
    value: object


def _children(nodes):
    kids = [[] for _ in nodes]
    stack = []
    for i, node in enumerate(nodes):
        while stack and nodes[stack[-1]].level >= node.level:
            stack.pop()
        if stack:
            kids[stack[-1]].append(i)
        stack.append(i)
    return kids


class _Walker:
    def __init__(self, nodes, data):
        if any(n.type is None or n.name is None for n in nodes):
            raise FormatError("TypeTree uses a common string unknown to this table")
        self.nodes, self.kids, self.r, self.steps = nodes, _children(nodes), Reader(data), 0

    def walk(self, i):
        self.steps += 1
        if self.steps > MAX_WALK_STEPS:
            raise FormatError("TypeTree walk exceeds step budget")
        node, kids, r = self.nodes[i], self.kids[i], self.r
        if node.type == "ManagedReferencesRegistry":
            raise FormatError("ManagedReferencesRegistry payloads are not supported")
        if node.flags & 1:  # Array: size + data
            if len(kids) != 2:
                raise FormatError("malformed TypeTree array")
            count = r.number("i")
            element = self.nodes[kids[1]]
            if not 0 <= count <= len(r.data) - r.pos:
                raise FormatError("TypeTree array count outside object")
            if not self.kids[kids[1]] and element.type in PRIMITIVES:
                width = PRIMITIVES[element.type]
                raw = r.take(count * width)
                value = raw if width == 1 else list(struct.unpack(
                    "<%d%s" % (count, _SIGNED.get(element.type, _FORMATS[width])), raw))
            else:
                value = [self.walk(kids[1]) for _ in range(count)]
        elif node.type == "TypelessData" and not kids:
            value = r.take(r.count(len(r.data)))
        elif not kids:
            width = PRIMITIVES.get(node.type)
            if width is None:
                raise FormatError(f"unknown TypeTree primitive {node.type!r}")
            value = r.number(_SIGNED.get(node.type, _FORMATS[width]))
        elif node.type == "string" and len(kids) == 1 and self.nodes[kids[0]].flags & 1:
            value = self.walk(kids[0])
        else:
            value = {self.nodes[k].name: self.walk(k) for k in kids}
        if node.meta_flag & ALIGN_FLAG:
            r.align()
        return value


def walk_object(nodes, data):
    """Read a whole object by TypeTree; returns top-level ``Field`` spans."""
    walker = _Walker(nodes, data)
    fields = []
    for k in walker.kids[0]:
        start = walker.r.pos
        value = walker.walk(k)
        fields.append(Field(nodes[k].name, nodes[k].type, start, walker.r.pos, value))
    if nodes[0].meta_flag & ALIGN_FLAG:
        walker.r.align()
    if walker.r.pos != len(data):
        raise FormatError(f"TypeTree walk consumed {walker.r.pos} of {len(data)} object bytes")
    return tuple(fields)


class NodeStream(io.RawIOBase):
    """Read-only seekable view of a UnityFS node for ``read_index``."""

    def __init__(self, reader, node):
        self.reader, self.node, self.pos = reader, node, 0

    def readable(self):
        return True

    def seekable(self):
        return True

    def seek(self, offset, whence=0):
        base = (0, self.pos, self.node.size)[whence]
        self.pos = max(0, base + offset)
        return self.pos

    def tell(self):
        return self.pos

    def read(self, size=-1):
        end = self.node.size if size < 0 else min(self.node.size, self.pos + size)
        if end <= self.pos:
            return b""
        data = self.reader.read(self.node.offset + self.pos, end - self.pos)
        self.pos = end
        return data
