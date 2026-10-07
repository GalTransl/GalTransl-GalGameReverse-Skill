"""Pure static Hxv4 resource filter, bounded reader and identity-preserving writer.

Adapted from Cxdec_Tools hxv4_compute.rs / hxv4_shellcode.rs, MIT,
Copyright (c) 2026 bfloat16. Full notice: provenance/kirikiri-cxdec-tools-MIT.txt.
Uses the existing GARbro-derived Cx expression interpreter, never native code.
"""
import struct
import zlib
from .kirikiri_senren import Cipher as CxInterpreter, generate_program
from .kirikiri_hxv4 import MAGIC, chacha, _inflate
from .kirikiri_hxv4 import name_hash, path_hash, index_tag
from python.common.safety import validate_names

U32 = 0xffffffff
U64 = (1 << 64) - 1


def build_flat_patch(members, keys, *, hx_flags=0):
    """Build (original identity, plaintext, basename) triples at the Hx root.

    Explicit patch operation: keeps file ID/key/name hash and replaces the
    directory hash with the root domain, so EVERY member ends up flat no matter
    where it sits in the source archive - scripts, fonts, configs, images and
    audio alike. Basenames are mandatory (a name with a directory separator is
    rejected): a patch is a separate archive, and inheriting the original
    directory hash would leave the member unreachable. Caller selects changed
    resources and verifies loader policy. The standard File index still
    contains internal aliases, not literal names.
    """
    members = list(members)
    names = validate_names([name for _, _, name in members])
    if any('/' in name or '\\' in name for name in names):
        raise ValueError('flat Hx patch requires basenames')
    selected = []
    for (entry, data, supplied), name in zip(members, names):
        if name_hash(name) != entry.get('name_hash'):
            raise ValueError('flat Hx patch name hash mismatch')
        selected.append((dict(entry, path_hash=path_hash('')), data))
    return build(selected, keys, hx_flags=hx_flags)


class Random:
    """Hx SplitMix seeding and the old/new two-word PRNG variants."""
    def __init__(self, seed, method):
        self.method = method
        state = seed | ((seed ^ U32) << 32)
        self.seed = []
        for _ in range(2):
            state = (state + 0x9e3779b97f4a7c15) & U64
            z = ((state ^ (state >> 30)) * 0xbf58476d1ce4e5b9) & U64
            z = ((z ^ (z >> 27)) * 0x94d049bb133111eb) & U64
            self.seed.append(z ^ (z >> 31))

    def next(self):
        a, b = self.seed
        lo = lambda v: v & U32
        hi = lambda v: v >> 32
        pack = lambda l, h: lo(l) | (lo(h) << 32)
        if self.method == 0:
            c = pack(hi(a) ^ hi(b), lo(a) ^ lo(b))
            e = pack(hi(c), lo(c))
            self.seed = [pack((hi(c) << 21) ^ (a >> 15) ^ hi(c),
                              ((hi(a) >> 15) | (lo(a) << 17)) ^ (e >> 11) ^ lo(c)),
                         pack(c >> 4, e >> 4)]
            d = (a + b) & U64
            return (((d << 17) | (hi(d) >> 15)) + a) & U32
        c = a ^ b
        self.seed = [pack(((lo(a) << 24) | (hi(a) >> 8)) ^ (lo(c) << 16) ^ lo(c),
                          (c >> 16) ^ (a >> 8) ^ hi(c)),
                     pack(c >> 27, (hi(c) >> 27) | (lo(c) << 5))]
        d = (5 * a) & U64
        return (((hi(d) >> 25) | (d << 7)) * 9) & U32


def order(raw, mapping):
    if sorted(raw) != list(range(len(mapping))):
        raise ValueError('Hx Cx branch order is not a permutation')
    out = [0] * len(mapping)
    for i, n in enumerate(raw):
        out[n] = mapping[i]
    return tuple(out)


class Cipher(CxInterpreter):
    def __init__(self, keys):
        p = keys['params']
        if len(p) != 22 or len(keys['control_block']) != 4096:
            raise ValueError('Hx payload key sizes')
        # Upstream stores complemented words then complements on lookup.
        self.table = struct.unpack('<1024I', keys['control_block'])
        self.prolog = order(p[14:17], (0, 1, 2))
        self.odd = order(p[8:14], (2, 5, 3, 4, 1, 0))
        self.even = order(p[:8], (0, 2, 3, 1, 5, 6, 7, 4))
        if p[17] & ~0x81:
            raise ValueError('unsupported Hx Cx flags')
        self.method = p[17] >> 7
        self.mask, self.offset = struct.unpack_from('<HH', p, 18)
        self.filter_key = keys['filter_key']
        self.programs = {}

    def pair(self, value):
        value &= U32
        seed, arg = value & 127, value >> 7
        if seed not in self.programs:
            self.programs[seed] = generate_program(Random(seed, self.method).next,
                                                   self.prolog, self.odd, self.even)
        node = self.programs[seed]
        return self.evaluate(node, arg) | (self.evaluate(node, arg ^ U32) << 32)

    def transform(self, data, entry, position=0):
        """Symmetric XOR at logical resource offsets (after segment inflation)."""
        if position < 0:
            raise ValueError('negative Hx resource offset')
        if 'key' not in entry or 'id' not in entry:
            raise ValueError('Hx payload has no verified identity/key mapping')
        key = entry['key'] & U64
        if not entry['id'] & 0x100000000:
            key ^= self.filter_key
        split = self.offset + ((key >> 16) & self.mask)
        h = self.pair(~key) ^ U64
        header = h.to_bytes(8, 'big') + (self.pair(h) ^ U64).to_bytes(8, 'big')
        out = bytearray(data)
        for i in range(min(len(out), max(0, 16-position))):
            out[i] ^= header[position+i]
        end = position + len(out)
        for start, stop, seed in ((position, min(end, split), key),
                                  (max(position, split), end, key >> 32)):
            if stop <= start:
                continue
            k = self.pair(seed)
            mask = (k & 255) or 0xa5
            x, y = start-position, stop-position
            out[x:y] = bytes(out[x:y]).translate(bytes(v ^ mask for v in range(256)))
            p, q = (k >> 48) & 65535, (k >> 32) & 65535
            if p == q:
                q += 1
            for at, m in ((p, (k >> 8) & 255), (q, (k >> 16) & 255)):
                if start <= at < stop:
                    out[at-position] ^= m
        return bytes(out)


def read_member(stream, entry, cipher, *, max_size=32 << 20):
    if not 0 <= entry['size'] <= max_size or entry['flags'] not in (0, 0x80000000):
        raise ValueError('Hx member size/flags')
    if sum(s[2] for s in entry['segments']) != entry['size']:
        raise ValueError('Hx segment totals mismatch')
    parts = []
    for flag, offset, raw, packed in entry['segments']:
        if flag not in (0, 1) or min(offset, raw, packed) < 0 or max(raw, packed) > max_size:
            raise ValueError('Hx segment size/flags')
        stream.seek(offset)
        data = stream.read(packed)
        if len(data) != packed:
            raise ValueError('truncated Hx payload')
        if flag:
            data = _inflate(data, raw, max_size)
        elif len(data) != raw:
            raise ValueError('Hx segment size mismatch')
        parts.append(data)
    data = b''.join(parts)
    if len(data) != entry['size']:
        raise ValueError('Hx member size mismatch')
    if entry['flags']:
        data = cipher.transform(data, entry)
    if zlib.adler32(data) & U32 != entry['checksum']:
        raise ValueError('Hx plaintext checksum mismatch')
    return data


def build(members, keys, *, hx_flags=0, max_total=384 << 20):
    """New encrypted archive from (verified entry, plaintext) pairs.

    Preserves ID, key, name/path hashes; no guessed names, signatures or new IDs.
    Only fully mapped entries are accepted. Does not install into a game.
    """
    members = list(members)
    if not members or len(members) > 100000 or sum(len(d) for _, d in members) > max_total:
        raise ValueError('Hx build budget')
    if hx_flags not in (0, 1):
        raise ValueError('Hx table flags')
    cipher = Cipher(keys)
    chunk = lambda t, d: t + struct.pack('<Q', len(d)) + d
    def obj(v):
        if isinstance(v, bytes): return b'\3' + struct.pack('>I', len(v)) + v
        if isinstance(v, int): return b'\4' + (v & U64).to_bytes(8, 'big')
        return b'\x81' + struct.pack('>I', len(v)) + b''.join(map(obj, v))
    out = bytearray(MAGIC + bytes(8))
    records = []; paths = {}; aliases = set(); hashes = set()
    for e, data in members:
        if not {'id', 'key', 'name_hash', 'path_hash'} <= e.keys():
            raise ValueError('unmapped Hx member cannot be rebuilt')
        if not 0 <= e['id'] <= 0x1ffffffff:
            raise ValueError('Hx identity range')
        n = e['id'] & U32; alias = ''
        while True:
            alias += chr((n & 0x3fff) + 0x5000); n >>= 14
            if not n: break
        pair = (e['path_hash'], e['name_hash'])
        if alias in aliases or pair in hashes:
            raise ValueError('duplicate Hx identity/hash')
        aliases.add(alias); hashes.add(pair)
        path, name = map(bytes.fromhex, pair)
        if len(path) != 8 or len(name) != 32:
            raise ValueError('Hx name/path hash sizes')
        paths.setdefault(path, []).extend([name, [e['id'], e['key']]])
        stored = zlib.compress(cipher.transform(data, e))
        encoded = alias.encode('utf-16le')
        record = chunk(b'info', struct.pack('<IQQH', 0x80000000, len(data), len(stored), len(encoded)//2) + encoded)
        record += chunk(b'adlr', struct.pack('<I', zlib.adler32(data) & U32))
        record += chunk(b'segm', struct.pack('<IQQQ', 1, len(out), len(data), len(stored)))
        records.append(chunk(b'File', record)); out.extend(stored)
    root = obj([v for p, entries in paths.items() for v in (p, entries)])
    suffix = 'a' if hx_flags else 'b'
    key = keys['index_'+suffix]; nonce = bytes(4)+keys['nonce_'+suffix][16:24]
    ciphertext = chacha(struct.pack('<I', len(root)) + zlib.compress(root), key, nonce)
    encrypted = index_tag(ciphertext, key, nonce) + ciphertext
    index = chunk(b'Hxv4', struct.pack('<QIH', len(out), len(encrypted), hx_flags)) + b''.join(records)
    out.extend(encrypted)
    struct.pack_into('<Q', out, 11, len(out))
    packed = zlib.compress(index)
    out.extend(b'\1' + struct.pack('<QQ', len(packed), len(index)) + packed)
    return bytes(out)
