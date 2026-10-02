"""Read QLIE IconKeyImage from PE RCDATA/TFORM1 without loading the EXE.

Delphi node/value layout and Picture.Data selection adapted from GARbro-Mod
ArcFormats/Qlie/{ArcQLIE,DelphiDeserializer}.cs, commit
bc26d991ef5cdc0e1ecb32122ee9a48c3375750c. Copyright (C) 2017 morkt;
MIT notice: ../../provenance/licenses/MIT-GARbro.txt.
PE traversal and bounds checks are new. Input is caller-supplied bytes.
"""
import struct


def pe_tform1(data: bytes, *, max_resource: int = 16 << 20) -> bytes:
    """Return the unique RCDATA (10), TFORM1 resource across languages."""
    def take(at, size):
        if at < 0 or size < 0 or at + size > len(data):
            raise ValueError('PE offset outside file')
        return data[at:at + size]

    def u16(at):
        return struct.unpack('<H', take(at, 2))[0]

    def u32(at):
        return struct.unpack('<I', take(at, 4))[0]

    if take(0, 2) != b'MZ':
        raise ValueError('not a PE executable')
    pe = u32(0x3C)
    if take(pe, 4) != b'PE\0\0':
        raise ValueError('invalid PE signature')
    sections, optsize = u16(pe + 6), u16(pe + 20)
    opt = pe + 24
    magic = u16(opt)
    directory = {0x10B: 96, 0x20B: 112}.get(magic)
    if directory is None or optsize < directory + 24 or not 0 < sections <= 96:
        raise ValueError('unsupported PE optional header')
    if u32(opt + directory - 4) < 3:
        raise ValueError('PE has no resource directory')
    resource_rva, resource_size = u32(opt + directory + 16), u32(opt + directory + 20)
    if not 0 < resource_size <= max_resource:
        raise ValueError('PE resource size exceeds budget or is absent')
    sec = opt + optsize

    def rva_offset(rva, size):
        hits = []
        for i in range(sections):
            at = sec + 40 * i
            take(at, 40)
            va, rawsize, raw = u32(at + 12), u32(at + 16), u32(at + 20)
            if va <= rva and rva + size <= va + rawsize:
                hits.append(raw + rva - va)
        if len(hits) != 1:
            raise ValueError('ambiguous or unmapped PE resource RVA')
        take(hits[0], size)
        return hits[0]

    base = rva_offset(resource_rva, resource_size)

    def rel(at, size):
        if at < 0 or at + size > resource_size:
            raise ValueError('resource directory exceeds section')
        return base + at

    def children(offset):
        at = rel(offset, 16)
        count = u16(at + 12) + u16(at + 14)
        if count > 4096:
            raise ValueError('PE resource entry budget exceeded')
        rel(offset + 16, count * 8)
        result = []
        for i in range(count):
            name, target = u32(at + 16 + i * 8), u32(at + 20 + i * 8)
            if name & 0x80000000:
                n = name & 0x7FFFFFFF
                length = u16(rel(n, 2))
                name = take(rel(n + 2, length * 2), length * 2).decode('utf-16le')
            result.append((name, target))
        return result

    def directory_child(offset, name):
        found = [target for key, target in children(offset) if key == name]
        if len(found) != 1 or not found[0] & 0x80000000:
            raise ValueError(f'PE resource directory missing/ambiguous: {name}')
        return found[0] & 0x7FFFFFFF

    languages = directory_child(directory_child(0, 10), 'TFORM1')
    blobs = []
    for _, target in children(languages):
        if target & 0x80000000:
            raise ValueError('unexpected resource directory depth')
        at = rel(target, 16)
        rva, size = u32(at), u32(at + 4)
        if not 0 < size <= max_resource:
            raise ValueError('TFORM1 size exceeds budget')
        if not resource_rva <= rva or rva + size > resource_rva + resource_size:
            raise ValueError('TFORM1 lies outside resource directory')
        blobs.append(take(rva_offset(rva, size), size))
    if not blobs or any(blob != blobs[0] for blob in blobs):
        raise ValueError('missing or conflicting TFORM1 languages')
    return blobs[0]


def icon_key_from_dfm(data: bytes) -> bytes:
    """Parse inert Delphi TPF0 nodes and select direct child IconKeyImage.

    No Delphi classes are instantiated; unsupported value tags fail closed.
    """
    if not data.startswith(b'TPF0') or len(data) > 16 << 20:
        raise ValueError('invalid/oversized QLIE TFORM1')
    pos, nodes, values = 4, 0, 0

    def take(n):
        nonlocal pos
        if n < 0 or pos + n > len(data):
            raise ValueError('truncated Delphi form')
        b = data[pos:pos + n]
        pos += n
        return b

    def byte():
        return take(1)[0]

    def short_string():
        return take(byte()).decode('cp932')

    def value():
        nonlocal values
        values += 1
        if values > 100_000:
            raise ValueError('Delphi value budget exceeded')
        tag = byte()
        widths = {2: 1, 3: 2, 4: 4, 5: 10, 15: 4, 16: 8, 17: 8, 19: 8}
        if tag in widths:
            return take(widths[tag])
        if tag in (6, 7):
            return short_string()
        if tag in (8, 9, 13):
            return None
        if tag in (10, 12, 18, 20):
            n = int.from_bytes(take(4), 'little')
            return take(n * (2 if tag == 18 else 1))
        if tag == 11:
            while byte_count := byte():
                take(byte_count)
            return None
        raise ValueError(f'unsupported Delphi value tag {tag}')

    def node(depth):
        nonlocal nodes
        length = byte()
        if length == 0:
            return None
        nodes += 1
        if depth > 32 or nodes > 10_000:
            raise ValueError('Delphi node budget exceeded')
        cls = take(length).decode('cp932')
        name = short_string()
        props = {}
        while length := byte():
            key = take(length).decode('cp932')
            if key in props:
                raise ValueError('duplicate Delphi property')
            props[key] = value()
        children = []
        while (child := node(depth + 1)) is not None:
            children.append(child)
        return cls, name, props, children

    root = node(0)
    if root is None or pos != len(data):
        raise ValueError('incomplete Delphi form parse')
    icons = [child for child in root[3] if child[1] == 'IconKeyImage']
    if len(icons) != 1:
        raise ValueError('missing/ambiguous IconKeyImage')
    icon = icons[0][2].get('Picture.Data')
    if not isinstance(icon, bytes) or len(icon) < 0x106 or icon[:6] != b'\x05TIcon':
        raise ValueError('unsupported IconKeyImage Picture.Data')
    return icon[6:0x106]


def game_key_from_pe(data: bytes) -> bytes:
    return icon_key_from_dfm(pe_tform1(data))
