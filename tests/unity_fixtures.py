"""Synthetic UnityFS / serialized-file builders for tests (no game data)."""
import lzma
import struct

from python.archives import unity_serialized as us

COMMON_OFFSETS = {name: offset for offset, name in us.COMMON.items()}


def i32(value):
    return struct.pack("<i", value)


def string(value):
    raw = value.encode("utf-8") if isinstance(value, str) else value
    return i32(len(raw)) + raw + bytes(-len(raw) % 4)


def lz4_literals(data):
    """Valid LZ4 block made of one literal-only sequence."""
    n = len(data)
    if n < 15:
        return bytes([n << 4]) + data
    out = bytearray([0xF0])
    rest = n - 15
    while rest >= 255:
        out.append(255)
        rest -= 255
    out.append(rest)
    return bytes(out) + data


def lz4_repeat(seed, total):
    """``seed`` then an overlapping match repeating it, then 5 literal bytes."""
    tail = seed[:5] if len(seed) >= 5 else seed
    match = total - len(seed) - len(tail)
    assert match >= 4 and len(seed) < 15
    ml = match - 4
    token = len(seed) << 4 | min(ml, 15)
    out = bytearray([token]) + seed + struct.pack("<H", len(seed))
    if ml >= 15:
        rest = ml - 15
        while rest >= 255:
            out.append(255)
            rest -= 255
        out.append(rest)
    expected = bytearray(seed)
    while len(expected) < len(seed) + match:
        expected.append(expected[-len(seed)])
    # final literals must equal the continuing pattern for a simple expectation
    expected += tail
    return bytes(out) + bytes([len(tail) << 4]) + tail, bytes(expected)


def lzma_block(data):
    raw = lzma.compress(data, format=lzma.FORMAT_RAW, filters=[
        {"id": lzma.FILTER_LZMA1, "dict_size": 1 << 16, "lc": 3, "lp": 0, "pb": 2}])
    return bytes([(2 * 5 + 0) * 9 + 3]) + struct.pack("<I", 1 << 16) + raw


def compress(data, method):
    if method == 0:
        return data
    if method == 1:
        return lzma_block(data)
    return lz4_literals(data)


def bundle(nodes, *, version=8, engine="2022.3.27f1", method=3, info_method=2, at_end=False,
           padding=None, block_size=0x40, info_hash=bytes(16), extra_flags=0):
    """``nodes``: list of (path, bytes, flags). Returns UnityFS bytes."""
    if padding is None:
        padding = version >= 7
    stream, table = b"", []
    for path, data, flags in nodes:
        table.append((len(stream), len(data), flags, path))
        stream += data
    chunks = [stream[i:i + block_size] for i in range(0, len(stream), block_size)] or [b""]
    packed = [compress(c, method) for c in chunks]
    info = bytearray(info_hash + struct.pack(">I", len(chunks)))
    for c, p in zip(chunks, packed):
        info += struct.pack(">IIH", len(c), len(p), method)
    info += struct.pack(">I", len(table))
    for offset, size, flags, path in table:
        info += struct.pack(">qqI", offset, size, flags) + path.encode() + b"\0"
    info_packed = compress(bytes(info), info_method)
    flags = info_method | 0x40 | (0x80 if at_end else 0) | (0x200 if padding else 0) | extra_flags
    head = bytearray(b"UnityFS\0" + struct.pack(">I", version) + b"5.x.x\0" + engine.encode() + b"\0")
    size_at = len(head)
    head += struct.pack(">qIII", 0, len(info_packed), len(info), flags)
    if version >= 7:
        head += bytes(-len(head) % 16)
    out = bytearray(head)
    if not at_end:
        out += info_packed
    if padding:
        out += bytes(-len(out) % 16)
    out += b"".join(packed)
    if at_end:
        out += info_packed
    struct.pack_into(">q", out, size_at, len(out))
    return bytes(out)


def type_tree(nodes, version):
    """``nodes``: (level, type, name, meta, flags). Common strings use the table."""
    local = bytearray()
    offsets = {}

    def ref(s):
        if s in COMMON_OFFSETS:
            return COMMON_OFFSETS[s] | 0x80000000
        if s not in offsets:
            offsets[s] = len(local)
            local.extend(s.encode() + b"\0")
        return offsets[s]

    body = bytearray()
    for index, (level, typ, name, meta, flags) in enumerate(nodes):
        size = {"int": 4, "char": 1, "UInt8": 1, "SInt64": 8}.get(typ, -1)
        body += struct.pack("<HBBIIiii", 1, level, flags, ref(typ), ref(name), size, index, meta)
        if version >= 19:
            body += struct.pack("<Q", 0)
    return i32(len(nodes)) + i32(len(local)) + bytes(body) + bytes(local)


def string_nodes(level, name, align=True, script=False):
    meta = 0x4000 if script else 0
    return [(level, "string", name, meta, 0), (level + 1, "Array", "Array", 0x4000 if align else 0, 1),
            (level + 2, "int", "size", 0, 0), (level + 2, "char", "data", 0, 0)]


def textasset_tree(path_name=False):
    nodes = [(0, "TextAsset", "Base", 0x8000, 0)] + string_nodes(1, "m_Name") + string_nodes(1, "m_Script", script=True)
    if path_name:
        nodes += string_nodes(1, "m_PathName")
    return nodes


def monoscript_tree():
    nodes = [(0, "MonoScript", "Base", 0x8000, 0)] + string_nodes(1, "m_Name")
    nodes += [(1, "int", "m_ExecutionOrder", 0, 0), (1, "Hash128", "m_PropertiesHash", 0, 0)]
    nodes += [(2, "UInt8", f"bytes[{k}]", 0, 0) for k in range(16)]
    for field in ("m_ClassName", "m_Namespace", "m_AssemblyName"):
        nodes += string_nodes(1, field)
    return nodes


def textasset(name, script, path_name=None):
    return string(name) + string(script) + (string(path_name) if path_name is not None else b"")


def monoscript(name, cls, namespace=""):
    return string(name) + i32(0) + bytes(16) + string(cls) + string(namespace) + string("Assembly-CSharp.dll")


def behaviour(script_file, script_id, name):
    return struct.pack("<iqB3xiq", 0, 0, 1, script_file, script_id) + string(name) + b"payload"


def serialized(objects, *, version=22, unity="2022.3.27f1", trees=None, externals=(),
               scripts=(), ref_types=0):
    """``objects``: list of (path_id, class_id, bytes). ``trees``: {class_id: nodes}."""
    tree = trees is not None
    classes = list(dict.fromkeys(cls for _, cls, _ in objects))
    m = bytearray(unity.encode() + b"\0" + i32(19) + bytes([1 if tree else 0]) + i32(len(classes)))
    for cls in classes:
        m += i32(cls) + b"\0" + struct.pack("<h", 0 if cls == 114 else -1)
        if cls == 114:
            m += bytes(16)
        m += bytes(16)
        if tree:
            m += type_tree(trees[cls], version)
            if version >= 21:
                m += i32(0)
    header_size = 48 if version >= 22 else 20
    m += i32(len(objects))
    data, entries = bytearray(), []
    for pid, cls, raw in objects:
        m += bytes(-(header_size + len(m)) % 4)
        data += bytes(-len(data) % 8)
        if version >= 22:
            m += struct.pack("<qqIi", pid, len(data), len(raw), classes.index(cls))
        else:
            m += struct.pack("<qIIi", pid, len(data), len(raw), classes.index(cls))
        data += raw
    m += i32(len(scripts))
    for file_index, local in scripts:
        m += i32(file_index)
        m += bytes(-(header_size + len(m)) % 4)
        m += struct.pack("<q", local)
    m += i32(len(externals))
    for ext in externals:
        m += b"\0" + bytes(16) + i32(0) + ext.encode() + b"\0"
    if version >= 20:
        m += i32(ref_types)
    m += b"\0"
    offset = (header_size + len(m) + 15) // 16 * 16
    total = offset + len(data)
    if version >= 22:
        header = struct.pack(">4I", 0, 0, version, 0) + bytes(4) + struct.pack(">IqqQ", len(m), total, offset, 0)
    else:
        header = struct.pack(">4I", len(m), total, version, offset) + bytes(4)
    return header + bytes(m) + bytes(offset - header_size - len(m)) + bytes(data)
