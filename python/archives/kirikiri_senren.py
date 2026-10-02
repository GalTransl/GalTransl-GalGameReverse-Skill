"""Senren Banka Cx filter and bounded XP3 index (not a universal XP3 reader).

Cx algorithm adapted from GARbro-Mod KiriKiriCx.cs/YuzCrypt.cs, MIT,
Copyright (C) 2014-2018 by morkt. See xp3.py for the full MIT license.
Independent expression interpreter; never executes generated native/TJS code.
Profile constants and complemented control block: msg-tool crypt.json/cx_cb,
f72716cee88554d40c1cdface2812493b14ca653, GPL-3.0-or-later.
"""
from dataclasses import dataclass
from functools import lru_cache
import hashlib
from pathlib import Path
import struct
import zlib
from .xp3 import MAGIC, _chunks, _inflate
from python.common.safety import validate_names

MASK = 0xffffffff
CB_SHA = 'da033ef8f93fe5de1ada9de795a36646604b44834837617741c3112c0d5ab004'


class _Full(Exception):
    pass


@lru_cache(maxsize=128)
def program(seed):
    def rnd():
        nonlocal seed
        old = seed
        seed = (1103515245 * old + 12345) & MASK
        return (seed ^ (old << 16) ^ (old >> 16)) & MASK
    return generate_program(rnd, (1, 0, 2), (3, 1, 2, 4, 0, 5), (7, 4, 3, 6, 2, 0, 1, 5))


def generate_program(rnd, prolog, odd, even):
    """Bounded Cx expression builder shared with Hx; random state survives retries."""
    length = 0
    def cost(n):
        nonlocal length
        if length + n > 128:
            raise _Full
        length += n
    def body(stage, binary=True):
        if stage == 1:
            kind = prolog[rnd() % 3]
            if kind == 1:
                cost(2)
                return ('arg',)
            if kind == 0:
                cost(1)
                value = rnd()
                cost(4)
                return ('const', value)
            cost(7)
            value = rnd() & 1023
            cost(4)
            return ('table', ('const', value))
        if binary:
            cost(1)
            left = body(stage - 1, bool(rnd() & 1))
            cost(2)
            right = body(stage - 1, bool(rnd() & 1))
            op = odd[rnd() % 6]
            cost((9, 9, 2, 4, 3, 2)[op])
            cost(1)
            return ('binary', op, right, left)
        node = body(stage - 1, bool(rnd() & 1))
        op = even[rnd() & 7]
        if op <= 3:
            cost((2, 1, 2, 1)[op])
            return ('unary', op, node)
        if op == 4:
            cost(13)
            return ('table', node)
        if op == 5:
            cost(21)
            return ('swap', node)
        if op == 6:
            cost(1)
            value = rnd()
            cost(4)
            return ('xor', node, value)
        add = bool(rnd() & 1)
        cost(1)
        value = rnd()
        cost(4)
        return ('add', node, value if add else -value)
    for stage in range(5, 0, -1):
        length = 0  # Seed deliberately continues after a failed stage.
        try:
            cost(9)
            node = body(stage)
            cost(6)
            return node
        except _Full:
            pass
    raise ValueError('Cx program exceeds length limit')


class Cipher:
    def __init__(self, block):
        if hashlib.sha256(block).hexdigest() != CB_SHA:
            raise ValueError('wrong Senren control block')
        self.table = tuple(x ^ MASK for x in struct.unpack('<1024I', block))

    def evaluate(self, node, arg):
        op = node[0]
        ev = lambda n: self.evaluate(n, arg)
        if op == 'arg': value = arg
        elif op == 'const': value = node[1]
        elif op == 'table': value = self.table[ev(node[1]) & 1023]
        elif op == 'unary':
            a = ev(node[2]); value = (~a, a-1, -a, a+1)[node[1]]
        elif op == 'swap':
            a = ev(node[1]); value = ((a & 0xaaaaaaaa) >> 1) | ((a & 0x55555555) << 1)
        elif op == 'xor': value = ev(node[1]) ^ node[2]
        elif op == 'add': value = ev(node[1]) + node[2]
        elif op == 'binary':
            a, b = ev(node[2]), ev(node[3])
            value = (a >> (b & 15), a << (b & 15), a+b, b-a, a*b, a-b)[node[1]]
        else: raise ValueError('unknown Cx expression')
        return value & MASK

    def transform(self, data, checksum):
        out = bytearray(data)
        boundary = (checksum & 308) + 1846
        for start, end, key in ((0, min(boundary, len(out)), checksum),
                                (min(boundary, len(out)), len(out), checksum ^ (checksum >> 16))):
            node, arg = program(key & 127), key >> 7
            a, b = self.evaluate(node, arg), self.evaluate(node, arg ^ MASK)
            p, q = b >> 16, b & 65535
            if p == q: q += 1
            mask = (a & 255) or 1
            out[start:end] = bytes(out[start:end]).translate(bytes(x ^ mask for x in range(256)))
            if start <= q < end: out[q] ^= (a >> 16) & 255
            if start <= p < end: out[p] ^= (a >> 8) & 255
        return bytes(out)


def default_cipher():
    return Cipher(Path(__file__).with_name('kirikiri_senren_cb.bin').read_bytes())


@dataclass(frozen=True)
class Entry:
    name: str
    checksum: int
    flags: int
    size: int
    segments: tuple


def read_index(stream):
    """Read only bounded index/name tables. Known dummy security entry is excluded."""
    stream.seek(0, 2); total = stream.tell()
    def read(at, size):
        if at < 0 or size < 0 or at + size > total or size > 16 << 20:
            raise ValueError('XP3 metadata range/budget')
        stream.seek(at); data = stream.read(size)
        if len(data) != size: raise ValueError('truncated XP3')
        return data
    if read(0, 11) != MAGIC: raise ValueError('not XP3')
    at, = struct.unpack('<Q', read(11, 8))
    if read(at, 9) == b'\x80' + b'\0'*8:
        at, = struct.unpack('<Q', read(at+9, 8))
    flag = read(at, 1)[0]
    if flag == 1:
        packed, size = struct.unpack('<QQ', read(at+1, 16))
        index = _inflate(read(at+17, packed), size, 16 << 20)
    elif flag == 0:
        size, = struct.unpack('<Q', read(at+1, 8)); index = read(at+9, size)
    else: raise ValueError('unknown Senren XP3 index flags')
    chunks = list(_chunks(index)); names = {}; aliases = {}; entries = []
    sections = [v for k, v in chunks if k == b'sen:']
    if len(sections) != 1: raise ValueError('missing/duplicate sen: table')
    section = sections[0]
    if len(section) != 30 or section[16:] != bytes.fromhex('050043534b600aff074eb1820000'):
        raise ValueError('unknown Senren names section')
    off, size, packed = struct.unpack_from('<QII', section)
    for tag, val in _chunks(_inflate(read(off, packed), size, 16 << 20)):
        if tag != b'hnfn' or len(val) < 8: raise ValueError('unknown names record')
        checksum, units = struct.unpack_from('<IH', val)
        if len(val) != 8+2*units or val[-2:] != b'\0\0':
            raise ValueError('invalid/duplicate name mapping')
        name = val[6:-2].decode('utf-16le')
        names.setdefault(checksum, []).append(name)
        aliases[hashlib.md5(name.lower().encode('utf-16le')).hexdigest()] = (checksum, name)
    for tag, val in chunks:
        if tag == b'sen:': continue
        if tag != b'File': raise ValueError('unknown XP3 record')
        parts = list(_chunks(val)); fields = dict(parts)
        if len(fields) != len(parts) or set(fields) - {b'adlr', b'info', b'segm', b'time'}:
            raise ValueError('unknown/duplicate XP3 fields')
        checksum, = struct.unpack('<I', fields[b'adlr'])
        info = fields[b'info']; flags, size, packed, units = struct.unpack_from('<IQQH', info)
        alias = info[22:22+units*2].decode('utf-16le')
        segs = tuple(struct.iter_unpack('<IQQQ', fields[b'segm']))
        # Original security notice has deliberately false info totals/name size.
        # Pin the exact marker and physical PNG segment rather than skip arbitrary entries.
        if checksum == 0x689792e4 and alias.startswith('$$$') and segs == ((0, 88, 157, 157),):
            if read(40, 7) != b'\x89PNG\n\x1a\n': raise ValueError('invalid dummy entry')
            continue
        if (len(info) != 22+units*2 and not (len(info) == 24+units*2 and info[-2:] == b'\0\0')) or flags not in (0, 0x80000000):
            raise ValueError('unknown XP3 info')
        if alias == '$':
            name = '$'  # Distinct bootstrap entry; do not collide with real startup.tjs.
        elif alias in aliases:
            mapped_hash, name = aliases[alias]
            if mapped_hash != checksum: raise ValueError('name hash mismatch')
        elif alias in names.get(checksum, []):
            name = alias
        elif checksum in names:
            name = names[checksum][0] if len(names[checksum]) == 1 else alias
        else:
            name = alias
        if sum(s[2] for s in segs) != size or sum(s[3] for s in segs) != packed:
            raise ValueError('XP3 member totals mismatch')
        if not segs or any(f not in (0, 1) or o < 40 or o+p > total for f,o,u,p in segs):
            raise ValueError('XP3 segment range/flags')
        entries.append(Entry(name, checksum, flags, size, segs))
    for entry in entries:
        validate_names([entry.name])  # Preserve duplicate index records; selection must disambiguate.
    return entries


def read_member(stream, entry, cipher, *, max_size=32 << 20):
    if entry.size > max_size: raise ValueError('XP3 member budget')
    parts = []
    for flag, offset, raw_size, packed_size in entry.segments:
        if packed_size > max_size: raise ValueError('XP3 stored member budget')
        stream.seek(offset); data = stream.read(packed_size)
        if len(data) != packed_size: raise ValueError('truncated XP3 payload')
        if flag: data = _inflate(data, raw_size, max_size)
        elif len(data) != raw_size: raise ValueError('XP3 segment sizes')
        parts.append(data)
    data = b''.join(parts)
    if entry.flags: data = cipher.transform(data, entry.checksum)
    if zlib.adler32(data) & MASK != entry.checksum:
        raise ValueError('Senren checksum mismatch')
    return data


def build(files, cipher, *, max_total=384 << 20):
    """Build a new encrypted Senren script archive; no external .sig signing.

    Names are explicit, all files have one zlib-compressed encrypted segment.
    It is a new archive, not a byte-identical copy of a source media archive.
    """
    validate_names([n for n,d in files])
    if not files or sum(len(d) for n,d in files) > max_total:
        raise ValueError('Senren build budget')
    chunk = lambda tag, d: tag+struct.pack('<Q', len(d))+d
    result = bytearray(MAGIC+struct.pack('<QI', 23, 1)+b'\x80'+b'\0'*16)
    records = []; names = bytearray()
    for name, data in files:
        checksum = zlib.adler32(data) & MASK
        stored = zlib.compress(cipher.transform(data, checksum))
        encoded = name.encode('utf-16le'); units = len(encoded)//2
        if units > 4096: raise ValueError('Senren filename too long')
        names.extend(chunk(b'hnfn', struct.pack('<IH', checksum, units)+encoded+b'\0\0'))
        record = chunk(b'adlr', struct.pack('<I', checksum))
        record += chunk(b'segm', struct.pack('<IQQQ', 1, len(result), len(data), len(stored)))
        record += chunk(b'info', struct.pack('<IQQH', 0x80000000, len(data), len(stored), units)+encoded+b'\0\0')
        records.append(chunk(b'File', record)); result.extend(stored)
    packed_names = zlib.compress(names)
    section = struct.pack('<QII', len(result), len(names), len(packed_names))+bytes.fromhex('050043534b600aff074eb1820000')
    result.extend(packed_names)
    index = chunk(b'sen:', section)+b''.join(records)
    struct.pack_into('<Q', result, 32, len(result))
    packed = zlib.compress(index)
    result.extend(b'\x01'+struct.pack('<QQ', len(packed), len(index))+packed)
    return bytes(result)

