"""Bounded unencrypted PSB v2/v3 SCN tree and reference-local scalar writer.

Layout reference: GARbro-Mod ArcFormats/Emote/ArcPSB.cs (MIT, morkt).
See python/archives/xp3.py for the full MIT license. SCN semantic reference:
msg-tool src/scripts/kirikiri/scn.rs (GPL-3.0-or-later).
Only the observed v2/v3 no-resource SCN layouts are writable.
"""
from dataclasses import dataclass
import struct
import zlib


@dataclass
class Node:
    pos: int
    end: int
    tag: int
    value: object


def array(values):
    count_width = max(1, (len(values).bit_length()+7)//8)
    width = max(1, (max(values, default=0).bit_length()+7)//8)
    if max(width, count_width) > 4: raise ValueError('PSB array too large')
    return (bytes([12+count_width]) + len(values).to_bytes(count_width, 'little')
            + bytes([12+width]) + b''.join(v.to_bytes(width, 'little') for v in values))


class Psb:
    def __init__(self, data):
        self.data = data
        if len(data) > 32 << 20 or data[:8] not in (b'PSB\0\x03\0\0\0', b'PSB\0\x02\0\0\0'):
            raise ValueError('requires plain PSB v2/v3')
        self.version = data[4]; self.header_size = 44 if self.version == 3 else 40
        self.header = list(struct.unpack('<8I', self.take(8, 32)))
        self.header.append(struct.unpack('<I', self.take(40,4))[0] if self.version == 3 else 0)
        length, names, strings, pool, co, cl, cd, root, checksum = self.header
        if not (names == self.header_size <= root < strings < pool <= co < cl < cd == len(data)):
            raise ValueError('unknown PSB section order/resources')
        if length not in ((0,40) if self.version == 2 else (44,)):
            raise ValueError('unknown PSB header length')
        if self.version == 3 and zlib.adler32(data[8:40]) & 0xffffffff != checksum:
            raise ValueError('PSB header checksum mismatch')
        self.root_at, self.strings_at, self.pool_at, self.pool_end = root, strings, pool, co
        a, pos = self.read_array(names); b, end = self.read_array(pos)
        self.keys = {}; pending = [(0, b'')]; visited = set()
        while pending:
            node, text = pending.pop()
            if node in visited or len(text) > 1024: raise ValueError('PSB names cycle/depth')
            visited.add(node)
            if node >= len(a): raise ValueError('PSB names range')
            start = a[node]
            for char in range(min(256, len(b)-start)):
                child = start + char
                if b[child] == node:
                    if char == 0:
                        if child >= len(a): raise ValueError('PSB name terminal')
                        self.keys[a[child]] = text.decode('utf-8')
                    else: pending.append((child, text+bytes([char])))
        offsets, end = self.read_array(strings)
        if end != pool: raise ValueError('PSB string index padding')
        self.strings = []
        for off in offsets:
            at = pool+off
            end = data.find(b'\0', at, co)
            if not pool <= at <= end < co: raise ValueError('PSB string range')
            self.strings.append(data[at:end].decode('utf-8'))
        for at, stop in ((co, cl), (cl, cd)):
            vals, end = self.read_array(at)
            if vals or end != stop: raise ValueError('PSB resources not supported')
        self.nodes = 0; self.cache = {}; self.active = set()
        self.root = self.read_node(root, 0)
        if self.root.end != strings: raise ValueError('PSB tree gap/trailer')

    def take(self, at, count):
        if at < 0 or count < 0 or at+count > len(self.data): raise ValueError('PSB bounds')
        return self.data[at:at+count]

    def read_array(self, at):
        n = self.take(at, 1)[0]-12
        if not 1 <= n <= 4: raise ValueError('PSB array count type')
        count = int.from_bytes(self.take(at+1, n), 'little')
        width = self.take(at+1+n, 1)[0]-12
        if not 1 <= width <= 4 or count > 2_000_000: raise ValueError('PSB array budget/type')
        start = at+2+n; raw = self.take(start, count*width)
        return [int.from_bytes(raw[i:i+width], 'little') for i in range(0, len(raw), width)], start+len(raw)

    def read_node(self, at, depth):
        if at in self.active: raise ValueError('PSB node cycle')
        if at in self.cache: return self.cache[at]
        self.active.add(at)
        self.nodes += 1
        if depth > 100 or self.nodes > 2_000_000 or not self.root_at <= at < self.strings_at:
            raise ValueError('PSB tree range/depth/budget')
        tag = self.data[at]; end = at+1
        if tag in (1, 2, 3, 4, 29): value = None
        elif 5 <= tag <= 12:
            end += tag-4; value = int.from_bytes(self.take(at+1, tag-4), 'little', signed=True)
        elif 21 <= tag <= 24:
            end += tag-20; value = int.from_bytes(self.take(at+1, tag-20), 'little')
            if value >= len(self.strings): raise ValueError('PSB string ID')
        elif tag in (30, 31):
            end += 4 if tag == 30 else 8; value = None
        elif tag in (32, 33):
            keys = None
            if tag == 33:
                keys, end = self.read_array(end)
            offsets, base = self.read_array(end)
            if keys is not None and (len(keys) != len(offsets) or len(set(keys)) != len(keys)):
                raise ValueError('PSB dictionary keys')
            children = []; end = base
            for off in offsets:
                node = self.read_node(base+off, depth+1); children.append(node)
            for start, stop in sorted(set((n.pos, n.end) for n in children)):
                if start != end: raise ValueError('PSB tree gap/partial overlap')
                end = stop
            if keys is None: value = children
            else:
                if any(k not in self.keys for k in keys): raise ValueError('PSB unknown key')
                value = [(k, child) for k, child in zip(keys, children)]
        else: raise ValueError(f'PSB unknown node tag {tag}')
        if end > self.strings_at: raise ValueError('PSB node exceeds tree')
        node = Node(at, end, tag, value)
        self.cache[at] = node; self.active.remove(at)
        return node

    def object(self, node):
        if node.tag != 33: raise ValueError('expected PSB dictionary')
        return {self.keys[k]: v for k,v in node.value}

    def text(self, node):
        if not 21 <= node.tag <= 24: raise ValueError('expected PSB string')
        return self.strings[node.value]

    def patch(self, edits):
        strings = list(self.strings); done = set()
        prefixes = {path[:i] for path in edits for i in range(len(path)+1)}
        def encode(node, path=()):
            if path not in prefixes: return self.data[node.pos:node.end]
            if path in edits:
                after = edits[path]; done.add(path)
                if type(after) is int:
                    if not (node.tag == 4 or 5 <= node.tag <= 12): raise ValueError('expected PSB integer')
                    before = 0 if node.tag == 4 else node.value
                    if before == after: return self.data[node.pos:node.end]
                    if not -(1 << 63) <= after < (1 << 63): raise ValueError('PSB integer overflow')
                    if after == 0: return b'\x04'
                    width = next(n for n in range(1,9) if -(1 << (8*n-1)) <= after < (1 << (8*n-1)))
                    return bytes([4+width])+after.to_bytes(width,'little',signed=True)
                before = self.text(node)
                if not isinstance(after, str) or '\0' in after: raise ValueError('invalid PSB string')
                if before != after:
                    idx = len(strings); strings.append(after)
                    width = max(1, (idx.bit_length()+7)//8)
                    return bytes([20+width])+idx.to_bytes(width, 'little')
            if node.tag not in (32, 33): return self.data[node.pos:node.end]
            children = node.value if node.tag == 32 else [v for k,v in node.value]
            pieces = [encode(c, path+(i,)) for i,c in enumerate(children)]
            if all(p == self.data[c.pos:c.end] for c,p in zip(children, pieces)):
                return self.data[node.pos:node.end]
            offsets = []; pos = 0
            for p in pieces: offsets.append(pos); pos += len(p)
            return (bytes([node.tag]) + (array([k for k,v in node.value]) if node.tag == 33 else b'')
                    + array(offsets) + b''.join(pieces))
        root = encode(self.root)
        if done != set(edits): raise ValueError('unknown PSB node edit')
        if root == self.data[self.root_at:self.strings_at]: return self.data
        pool = bytearray(); offsets = []
        for text in strings:
            offsets.append(len(pool)); pool.extend(text.encode('utf-8')+b'\0')
        index = array(offsets); result = bytearray(self.data[:self.root_at]+root+index+pool)
        co = len(result); result.extend(array([])); cl = len(result); result.extend(array([]))
        header = [self.header[0], self.header_size, self.root_at+len(root), self.root_at+len(root)+len(index), co, cl,
                  len(result), self.root_at]
        struct.pack_into('<8I', result, 8, *header)
        if self.version == 3:
            struct.pack_into('<I', result, 40, zlib.adler32(result[8:40]) & 0xffffffff)
        if len(result) > 32 << 20: raise ValueError('rebuilt PSB budget')
        return bytes(result)
