"""Bounded FilePackVer3.0 index, member crypto and 1PC byte-pair decoder.

Adapted from GARbro-Mod ArcFormats/Qlie/{ArcQLIE,Encryption,
QlieMersenneTwister}.cs at bc26d991ef5cdc0e1ecb32122ee9a48c3375750c.
Copyright (C) 2015-2017 morkt; MT: (C) 1997 Makoto Matsumoto and
Takuji Nishimura. MIT notice: ../../provenance/licenses/MIT-GARbro.txt.
Python adaptation adds strict bounds, explicit key modes and no file writes.
Only 3.0 is supported. Template packing lives in qlie_writer.py.
"""
from dataclasses import dataclass
import struct
from typing import BinaryIO


MASK32 = 0xFFFFFFFF
PACK_KEY_NAME = "pack_keyfile_kfueheish15538fa9or.key"


def _add(a: int, b: int, bits: int) -> int:
    mask = (1 << bits) - 1
    return sum((((a >> s) + (b >> s)) & mask) << s for s in range(0, 64, bits))


def hash_v3(data: bytes) -> int:
    """QLIE 3.0 checksum; trailing bytes outside complete qwords are ignored."""
    h = key = 0
    for pos in range(0, len(data) - 7, 8):
        h = _add(h, 0x0307030703070307, 16)
        key = _add(key, struct.unpack_from('<Q', data, pos)[0] ^ h, 16)
    return (key ^ (key >> 32)) & MASK32


def crypt_name(raw: bytes, arc_key: int) -> bytes:
    key = len(raw) + (arc_key ^ 0x3E)
    return bytes(v ^ ((((i + 1) ^ key) + i + 1) & 255)
                 for i, v in enumerate(raw))


@dataclass(frozen=True)
class Entry:
    name: str
    raw_name: bytes  # decrypted CP932 name bytes, NOT encrypted index bytes
    offset: int
    size: int
    unpacked_size: int
    packed: int
    encryption: int
    checksum: int


@dataclass(frozen=True)
class Index:
    entries: tuple[Entry, ...]
    arc_key: int
    file_size: int
    index_offset: int
    index_end: int


def _read(stream: BinaryIO, size: int) -> bytes:
    data = stream.read(size)
    if len(data) != size:
        raise ValueError('truncated QLIE archive')
    return data


def read_index(stream: BinaryIO, *, max_entries: int = 100_000,
               max_index_bytes: int = 32 << 20) -> Index:
    """Read metadata only; large media payloads never enter memory.

    Names still require common.safety.validate_names before filesystem output.
    Space between the end of entries and the 0x400-byte key area is a hash
    table, not padding and not additional entries.
    """
    stream.seek(0, 2)
    size = stream.tell()
    if size < 0x41C:
        raise ValueError('QLIE archive too small')
    stream.seek(size - 28)
    footer = _read(stream, 28)
    if footer[:16] != b'FilePackVer3.0\0\0':
        raise ValueError('only FilePackVer3.0 is supported')
    count, start = struct.unpack_from('<IQ', footer, 16)
    end = size - 0x41C
    if not 0 < count <= max_entries or not 0 <= start < end:
        raise ValueError('invalid QLIE index bounds/count')
    stream.seek(end)
    key = hash_v3(_read(stream, 256)) & 0xFFFFFFF
    stream.seek(start)
    entries = []
    for _ in range(count):
        if stream.tell() + 2 > min(end, start + max_index_bytes):
            raise ValueError('QLIE index budget/boundary exceeded')
        length = struct.unpack('<H', _read(stream, 2))[0]
        if not 0 < length <= 256 or stream.tell() + length + 28 > min(end, start + max_index_bytes):
            raise ValueError('invalid QLIE name/index length')
        raw = crypt_name(_read(stream, length), key)
        name = raw.decode('cp932', errors='strict')
        offset, stored, unpacked, packed, enc, checksum = struct.unpack('<QIIIII', _read(stream, 28))
        if offset + stored > start or packed not in (0, 1) or enc not in (0, 1, 2, 4):
            raise ValueError('invalid QLIE payload bounds or unsupported flags')
        if not packed and stored != unpacked:
            raise ValueError('uncompressed QLIE member has conflicting sizes')
        entries.append(Entry(name, raw, offset, stored, unpacked, packed, enc, checksum))
    index_end = stream.tell()
    ranges = sorted((e.offset, e.offset + e.size) for e in entries if e.size)
    if any(b[0] < a[1] for a, b in zip(ranges, ranges[1:])):
        raise ValueError('overlapping QLIE payloads')
    return Index(tuple(entries), key, size, start, index_end)


class _Twister:
    """QLIE's 64-word MT variant, not Python random or standard MT19937."""
    def __init__(self, seed: int, keys: tuple[bytes, ...]):
        self.state = [seed & MASK32]
        for i in range(1, 64):
            prev = self.state[-1]
            self.state.append((0x6611BC19 * (prev ^ (prev >> 30)) + i) & MASK32)
        for data in keys:
            for i in range(min(len(data) // 4, 64)):
                self.state[i] ^= struct.unpack_from('<I', data, 4 * i)[0]
        self.pos = 64

    def rand(self) -> int:
        mt = self.state
        if self.pos >= 64:
            for i in range(63):
                y = (mt[i] & 0x80000000) | ((mt[i + 1] & 0x7FFFFFFF) >> 1)
                mt[i] = mt[(i + 39) % 64] ^ y ^ (0x9908B0DF if mt[i + 1] & 1 else 0)
            y = (mt[63] & 0x80000000) | ((mt[0] & 0x7FFFFFFF) >> 1)
            mt[63] = mt[38] ^ y ^ (0x9908B0DF if mt[62] & 1 else 0)
            self.pos = 0
        y = mt[self.pos]
        self.pos += 1
        y ^= y >> 11
        y ^= (y << 7) & 0x9C4F88E3
        y ^= (y << 15) & 0xE7F70000
        return (y ^ (y >> 18)) & MASK32

    def rand64(self) -> int:
        lo = self.rand()
        return lo | self.rand() << 32


def _crypt(data: bytes, entry: Entry, arc_key: int, *, mode: str,
           key_file: bytes | None = None, game_key: bytes | None = None,
           encrypting: bool = False) -> bytes:
    """Explicit mode: legacy (no keys), key-file, or keyed (+256-byte icon).

    For keyed archives, decrypt the PACK_KEY_NAME member with DLL/key.fkey
    first; later entries use that decrypted member as key_file instead.
    """
    if mode not in ('legacy', 'key-file', 'keyed'):
        raise ValueError('unknown QLIE crypto mode')
    if mode == 'legacy' and (key_file is not None or game_key is not None):
        raise ValueError('legacy mode does not accept keys')
    if mode != 'legacy' and (key_file is None or len(key_file) < 256):
        raise ValueError('QLIE key file is required (at least 256 bytes)')
    if mode == 'keyed' and (game_key is None or len(game_key) != 256):
        raise ValueError('QLIE 256-byte IconKeyImage key is required')
    if mode == 'key-file' and game_key is not None:
        raise ValueError('game key requires keyed mode')
    if len(data) != entry.size:
        raise ValueError('QLIE encrypted size mismatch')
    if entry.encryption == 0:
        return data
    out = bytearray(data)
    if mode == 'legacy':
        h = 0xA73C5F9DA73C5F9D
        x = ((len(data) + arc_key) & MASK32) ^ 0xFEC9753E
        x |= x << 32
        for pos in range(0, len(data) - 7, 8):
            h = _add(h, 0xCE24F523CE24F523, 32) ^ x
            word = struct.unpack_from('<Q', data, pos)[0]
            x = word if encrypting else word ^ h
            struct.pack_into('<Q', out, pos, word ^ h)
    else:
        h, seed = 0x85F532, 0x33F641
        for i, v in enumerate(entry.raw_name):
            h = (h + (i & 255) * v) & MASK32
            seed ^= h
        length = len(data)
        seed = (seed + (arc_key ^ ((7 * (length & 0xFFFFFF) + length + h
                                   + (h ^ length ^ 0x8F32DC)) & MASK32))) & MASK32
        seed = 9 * (seed & 0xFFFFFF)
        keys = (key_file,)
        if mode == 'keyed':
            seed ^= 0x453A
            keys += (game_key,)
        mt = _Twister(seed, keys)
        table = [mt.rand64() for _ in range(16)]
        for _ in range(9):
            mt.rand()
        h, t = mt.rand64(), mt.rand() & 15
        for pos in range(0, length - 7, 8):
            h = _add(h ^ table[t], table[t], 32)
            word = struct.unpack_from('<Q', data, pos)[0]
            d = word if encrypting else word ^ h
            struct.pack_into('<Q', out, pos, word ^ h)
            h = _add(h, d, 8) ^ d
            shifted = ((h << 1) & 0xFFFFFFFEFFFFFFFE)
            h = _add(shifted, d, 16)
            t = (t + 1) & 15
    return bytes(out)


def decrypt(data: bytes, entry: Entry, arc_key: int, *, mode: str,
            key_file: bytes | None = None, game_key: bytes | None = None) -> bytes:
    """Decrypt with explicit legacy/key-file/keyed mode; see module docs."""
    return _crypt(data, entry, arc_key, mode=mode, key_file=key_file, game_key=game_key)


def encrypt(data: bytes, entry: Entry, arc_key: int, *, mode: str,
            key_file: bytes | None = None, game_key: bytes | None = None) -> bytes:
    """Inverse of decrypt; feedback uses plaintext, not previous ciphertext."""
    return _crypt(data, entry, arc_key, mode=mode, key_file=key_file,
                  game_key=game_key, encrypting=True)


def decompress(data: bytes, *, expected_size: int, max_output: int = 64 << 20) -> bytes:
    """Decode 1PC byte pairs; reject cycles, truncation and size mismatches."""
    if len(data) < 12 or data[:4] != b'1PC\xff':
        raise ValueError('missing QLIE 1PC compression header (wrong key?)')
    size = struct.unpack_from('<I', data, 8)[0]
    if size != expected_size or size > max_output:
        raise ValueError('QLIE decompression size/budget mismatch')
    pos = 12
    out = bytearray()

    def take(n):
        nonlocal pos
        if n < 0 or pos + n > len(data):
            raise ValueError('truncated QLIE byte-pair stream')
        result = data[pos:pos + n]
        pos += n
        return result

    while pos < len(data):
        left, right = list(range(256)), [0] * 256
        i = 0
        while i < 256:
            count = take(1)[0]
            if count > 127:
                i += count - 127
                count = 0
            if i > 256:
                raise ValueError('QLIE byte-pair skip exceeds table')
            if i > 255:
                break
            if i + count + 1 > 256:
                raise ValueError('invalid QLIE byte-pair table')
            for _ in range(count + 1):
                left[i] = take(1)[0]
                if left[i] != i:
                    right[i] = take(1)[0]
                i += 1
        width = 2 if data[4] & 1 else 4
        count = int.from_bytes(take(width), 'little')
        encoded = take(count)
        # Expand only used symbols, with cycle/depth and total output limits.
        for symbol in encoded:
            stack = [(symbol, frozenset())]
            while stack:
                symbol, parents = stack.pop()
                if left[symbol] == symbol:
                    if len(out) >= size:
                        raise ValueError('QLIE byte-pair output exceeds declared size')
                    out.append(symbol)
                else:
                    if symbol in parents:
                        raise ValueError('cyclic QLIE byte-pair table')
                    path = parents | {symbol}
                    stack.extend(((right[symbol], path), (left[symbol], path)))
    if len(out) != size:
        raise ValueError('QLIE byte-pair output is shorter than declared size')
    return bytes(out)


def read_member(stream: BinaryIO, index: Index, entry: Entry, *, mode: str,
                key_file: bytes | None = None, game_key: bytes | None = None,
                max_stored: int = 64 << 20, max_output: int = 64 << 20) -> bytes:
    if entry not in index.entries or entry.size > max_stored or entry.unpacked_size > max_output:
        raise ValueError('QLIE member identity/budget mismatch')
    stream.seek(entry.offset)
    data = _read(stream, entry.size)
    # PACK 3.0 hashes stored ciphertext, before decryption/decompression.
    if hash_v3(data) != entry.checksum:
        raise ValueError('QLIE stored member checksum mismatch')
    data = decrypt(data, entry, index.arc_key, mode=mode, key_file=key_file, game_key=game_key)
    if entry.packed:
        data = decompress(data, expected_size=entry.unpacked_size, max_output=max_output)
    if len(data) != entry.unpacked_size:
        raise ValueError('QLIE decoded member size mismatch')
    return data
