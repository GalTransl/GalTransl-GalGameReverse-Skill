"""Bounded FilePackVer3.0/3.1 index, member crypto and 1PC byte-pair decoder.

Adapted from GARbro-Mod ArcFormats/Qlie/{ArcQLIE,Encryption,
QlieMersenneTwister}.cs at bc26d991ef5cdc0e1ecb32122ee9a48c3375750c.
Copyright (C) 2015-2017 morkt; MT: (C) 1997 Makoto Matsumoto and
Takuji Nishimura. MIT notice: ../../provenance/licenses/MIT-GARbro.txt.
3.1 (EncryptionV3_1: UTF-16LE names, rotated checksum, V1/V2 member
ciphers) from the same files. Python adaptation adds strict bounds, explicit
per-version key modes, encrypt inverses and no file writes. Template packing
lives in qlie_writer.py.
"""
from dataclasses import dataclass
import struct
from typing import BinaryIO


MASK32 = 0xFFFFFFFF
PACK_KEY_NAME = "pack_keyfile_kfueheish15538fa9or.key"
VERSIONS = ('3.0', '3.1')
# Key modes are version specific; the crypto routine never infers them.
MODES = {'3.0': ('legacy', 'key-file', 'keyed'), '3.1': ('pack-key', 'default-key')}
_ENCRYPTIONS = {'3.0': (0, 1, 2, 4), '3.1': (0, 1, 2)}


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


def hash_v31(data: bytes) -> int:
    """QLIE 3.1 checksum (also derives the 3.1 ArcKey); whole qwords only."""
    h = key = 0
    for pos in range(0, len(data) - 7, 8):
        h = _add(h, 0xA35793A7A35793A7, 16)
        key = _add(key, struct.unpack_from('<Q', data, pos)[0] ^ h, 16)
        lo, hi = key & MASK32, key >> 32
        key = (((lo << 3) | (lo >> 29)) & MASK32) | (((hi << 3) | (hi >> 29)) & MASK32) << 32

    def s16(value):
        value &= 0xFFFF
        return value - 0x10000 if value & 0x8000 else value
    return (s16(key) * s16(key >> 32) + s16(key >> 16) * s16(key >> 48)) & MASK32


def checksum(data: bytes, version: str) -> int:
    """Per-version checksum of the STORED (encrypted) member bytes."""
    if version == '3.0':
        return hash_v3(data)
    if version == '3.1':
        return hash_v31(data)
    raise ValueError('unsupported QLIE PACK version')


def crypt_name(raw: bytes, arc_key: int) -> bytes:
    key = len(raw) + (arc_key ^ 0x3E)
    return bytes(v ^ ((((i + 1) ^ key) + i + 1) & 255)
                 for i, v in enumerate(raw))


def crypt_name31(raw: bytes, arc_key: int) -> bytes:
    """Symmetric 3.1 UTF-16LE name XOR; len(raw) is twice the char count."""
    if len(raw) % 2:
        raise ValueError('QLIE 3.1 name must be UTF-16LE code units')
    count = len(raw) // 2
    h = ((count * count) ^ count ^ 0x3E13 ^ (arc_key >> 16) ^ arc_key) & 0xFFFF
    key, out = h, bytearray(raw)
    for i in range(count):
        key = (h + i + 8 * key) & MASK32
        out[2 * i] ^= key & 255
        out[2 * i + 1] ^= (key >> 8) & 255
    return bytes(out)


@dataclass(frozen=True)
class Entry:
    name: str
    # Decrypted name bytes (CP932 for 3.0, UTF-16LE for 3.1), NOT index bytes.
    raw_name: bytes
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
    version: str = '3.0'


def read_version(stream: BinaryIO) -> str:
    """Return '3.0' or '3.1' from the 28-byte footer; reject other versions."""
    stream.seek(0, 2)
    size = stream.tell()
    if size < 28:
        raise ValueError('QLIE archive too small')
    stream.seek(size - 28)
    magic = stream.read(16)
    if magic[:11] != b'FilePackVer' or magic[14:] != b'\0\0':
        raise ValueError('missing QLIE FilePackVer footer')
    version = magic[11:14].decode('ascii', errors='replace')
    if version not in VERSIONS:
        raise ValueError(f'unsupported QLIE FilePackVer{version} (supported: 3.0, 3.1)')
    return version


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
    version = read_version(stream)
    size = stream.tell() + 12
    if size < 0x41C:
        raise ValueError('QLIE archive too small')
    stream.seek(size - 12)
    count, start = struct.unpack('<IQ', _read(stream, 12))
    end = size - 0x41C
    if not 0 < count <= max_entries or not 0 <= start < end:
        raise ValueError('invalid QLIE index bounds/count')
    stream.seek(end)
    key_data = _read(stream, 256)
    # 3.1 uses a different checksum for ArcKey and UTF-16LE names whose u16
    # length counts characters (at most 0x100, as in the reference reader).
    key = (hash_v3 if version == '3.0' else hash_v31)(key_data) & 0xFFFFFFF
    unit = 1 if version == '3.0' else 2
    stream.seek(start)
    entries = []
    limit = min(end, start + max_index_bytes)
    for _ in range(count):
        if stream.tell() + 2 > limit:
            raise ValueError('QLIE index budget/boundary exceeded')
        length = struct.unpack('<H', _read(stream, 2))[0]
        if not 0 < length <= 256 or stream.tell() + length * unit + 28 > limit:
            raise ValueError('invalid QLIE name/index length')
        if version == '3.0':
            raw = crypt_name(_read(stream, length), key)
            name = raw.decode('cp932', errors='strict')
        else:
            raw = crypt_name31(_read(stream, 2 * length), key)
            name = raw.decode('utf-16-le', errors='strict')
            if '\0' in name:
                raise ValueError('QLIE 3.1 name contains NUL')
        offset, stored, unpacked, packed, enc, crc = struct.unpack('<QIIIII', _read(stream, 28))
        if offset + stored > start or packed not in (0, 1) or enc not in _ENCRYPTIONS[version]:
            raise ValueError('invalid QLIE payload bounds or unsupported flags')
        if not packed and stored != unpacked:
            raise ValueError('uncompressed QLIE member has conflicting sizes')
        entries.append(Entry(name, raw, offset, stored, unpacked, packed, enc, crc))
    index_end = stream.tell()
    ranges = sorted((e.offset, e.offset + e.size) for e in entries if e.size)
    if any(b[0] < a[1] for a, b in zip(ranges, ranges[1:])):
        raise ValueError('overlapping QLIE payloads')
    return Index(tuple(entries), key, size, start, index_end, version)


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


def _table31(seed: int, key: int) -> list[int]:
    table = []
    for _ in range(0x20):
        x = key * ((seed ^ key) & MASK32)
        seed = ((x >> 32) + x) & MASK32
        table.append(seed)
    return table


def key_data31(key_file: bytes | None) -> bytes:
    """Expand a 3.1 key (decrypted pack_keyfile) to 0x400 bytes.

    None selects the built-in table ('default-key'). Short keys are rejected
    instead of silently falling back to the built-in table.
    """
    data = bytearray(0x400)
    for i in range(256):
        value = (i + 7) * (i + 3)
        struct.pack_into('<I', data, 4 * i, (-value if i % 3 else value) & MASK32)
    if key_file is not None:
        if len(key_file) < 128:
            raise ValueError('QLIE 3.1 key must be at least 128 bytes')
        k, step = key_file[49] % 73 + 128, key_file[79] % 7 + 7
        for i in range(len(data)):
            k = (k + step) % len(key_file)
            data[i] ^= key_file[k]
    return bytes(data)


def _crypt31(data: bytes, entry: Entry, arc_key: int, *, mode: str,
             key_file: bytes | None, encrypting: bool) -> bytes:
    """EncryptionV3_1: method 1 (name/size seeded) or 2 (+expanded key)."""
    if mode == 'default-key' and key_file is not None:
        raise ValueError('default-key mode does not accept a key')
    if entry.encryption == 0 or len(data) < 8:
        return data
    if mode == 'pack-key' and entry.encryption == 2 and key_file is None:
        raise ValueError('QLIE 3.1 pack-key mode needs the decrypted pack_keyfile')
    if len(entry.raw_name) % 2:
        raise ValueError('QLIE 3.1 entry name is not UTF-16LE')
    units = struct.unpack(f'<{len(entry.raw_name) // 2}H', entry.raw_name)
    v2 = entry.encryption == 2
    h, seed = (0x86F7E2, 0x4437F1) if v2 else (0x85F532, 0x33F641)
    for i, unit in enumerate(units):
        h = (h + (unit << (i & 7))) & MASK32
        seed ^= h
    length = len(data)
    mul, magic = (13, 0x56E213) if v2 else (7, 0x8F32DC)
    seed = (seed + (arc_key ^ ((mul * (length & 0xFFFFFF) + length + h
                                + (h ^ length ^ magic)) & MASK32))) & MASK32
    seed = ((13 if v2 else 9) * (seed & 0xFFFFFF)) & MASK32
    table = _table31(seed, 0x8A77F473 if v2 else 0x8DF21431)
    expanded = key_data31(key_file) if v2 else b''
    k = (8 * (table[8] & 0xD)) & 0x7F if v2 else 2 * (table[0xD] & 0xF)
    h = table[6] | table[7] << 32
    out = bytearray(data)
    for pos in range(0, length - 7, 8):
        if v2:
            t = 2 * (k & 0xF)
            t = (table[t] | table[t + 1] << 32) ^ struct.unpack_from('<Q', expanded, 8 * k)[0]
        else:
            t = table[k] | table[k + 1] << 32
        h = _add(h ^ t, t, 32)
        word = struct.unpack_from('<Q', data, pos)[0]
        plain = word if encrypting else word ^ h
        struct.pack_into('<Q', out, pos, word ^ h)
        h = _add(h, plain, 8) ^ plain
        h = _add((h << 1) & 0xFFFFFFFEFFFFFFFE, plain, 16)
        k = (k + 1) & 0x7F if v2 else (k + 2) & 0x1F
    return bytes(out)


def _crypt(data: bytes, entry: Entry, arc_key: int, *, mode: str,
           key_file: bytes | None = None, game_key: bytes | None = None,
           encrypting: bool = False) -> bytes:
    """Explicit mode; never inferred here.

    3.0: legacy (no keys), key-file, or keyed (+256-byte icon). For keyed
    archives, decrypt the PACK_KEY_NAME member with DLL/key.fkey first; later
    entries use that decrypted member as key_file instead.
    3.1: pack-key (method-1 pack_keyfile member, then its plaintext as key for
    method-2 members) or default-key (built-in table, no key at all).
    """
    if len(data) != entry.size:
        raise ValueError('QLIE encrypted size mismatch')
    if mode in MODES['3.1']:
        if game_key is not None:
            raise ValueError('QLIE 3.1 does not use the IconKeyImage key')
        return _crypt31(data, entry, arc_key, mode=mode, key_file=key_file, encrypting=encrypting)
    if mode not in MODES['3.0']:
        raise ValueError('unknown QLIE crypto mode')
    if mode == 'legacy' and (key_file is not None or game_key is not None):
        raise ValueError('legacy mode does not accept keys')
    if mode != 'legacy' and (key_file is None or len(key_file) < 256):
        raise ValueError('QLIE key file is required (at least 256 bytes)')
    if mode == 'keyed' and (game_key is None or len(game_key) != 256):
        raise ValueError('QLIE 256-byte IconKeyImage key is required')
    if mode == 'key-file' and game_key is not None:
        raise ValueError('game key requires keyed mode')
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
    if mode not in MODES[index.version]:
        raise ValueError(f'QLIE mode {mode!r} does not apply to FilePackVer{index.version}')
    stream.seek(entry.offset)
    data = _read(stream, entry.size)
    # PACK 3.0/3.1 hash stored ciphertext, before decryption/decompression.
    if checksum(data, index.version) != entry.checksum:
        raise ValueError('QLIE stored member checksum mismatch')
    data = decrypt(data, entry, index.arc_key, mode=mode, key_file=key_file, game_key=game_key)
    if entry.packed:
        data = decompress(data, expected_size=entry.unpacked_size, max_output=max_output)
    if len(data) != entry.unpacked_size:
        raise ValueError('QLIE decoded member size mismatch')
    return data


CHAINED_MODES = ('key-file', 'keyed', 'pack-key')


def infer_mode(index: Index) -> tuple[str, str]:
    """Pick a key mode from index structure only; returns (mode, evidence).

    3.1: one internal pack_keyfile -> pack-key, otherwise default-key.
    3.0: one internal pack_keyfile -> keyed (needs key.fkey + IconKeyImage);
    archives without it need an explicit legacy/key-file choice.
    Callers must still verify by decoding (checksum + strict 1PC/size).
    """
    hits = [i for i, e in enumerate(index.entries) if e.name == PACK_KEY_NAME]
    if len(hits) > 1:
        raise ValueError('multiple internal QLIE pack_keyfile entries')
    if index.version == '3.1':
        if hits:
            entry = index.entries[hits[0]]
            return 'pack-key', (f'FilePackVer3.1 with internal {PACK_KEY_NAME} at #{hits[0]} '
                                f'(encryption={entry.encryption}); its plaintext keys method-2 members')
        return 'default-key', 'FilePackVer3.1 without internal pack_keyfile: built-in key table'
    if hits:
        return 'keyed', (f'FilePackVer3.0 with internal {PACK_KEY_NAME} at #{hits[0]}: '
                         'needs external key file and EXE IconKeyImage')
    raise ValueError('FilePackVer3.0 without internal pack_keyfile: choose --mode legacy or key-file explicitly')


def external_key_required(index: Index, mode: str) -> bool:
    """True when the chain's first decryption needs a key from outside the PACK."""
    if mode in ('key-file', 'keyed'):
        return True
    if mode == 'pack-key':
        entry = next(e for e in index.entries if e.name == PACK_KEY_NAME)
        return entry.encryption == 2
    return False


def member_keys(stream: BinaryIO, index: Index, *, mode: str, key_file: bytes | None = None,
                game_key: bytes | None = None) -> list[bytes | None]:
    """Per-ordinal key_file for decrypt/encrypt, following the internal key chain.

    Entries up to and including the pack_keyfile use the external key (if any);
    later entries use the decrypted pack_keyfile, which is never reused across
    archives.
    """
    if mode not in MODES[index.version]:
        raise ValueError(f'QLIE mode {mode!r} does not apply to FilePackVer{index.version}')
    if mode == 'pack-key' and not any(e.name == PACK_KEY_NAME for e in index.entries):
        raise ValueError('pack-key mode requires an internal pack_keyfile entry')
    if mode == 'pack-key' and external_key_required(index, mode) and key_file is None:
        raise ValueError('this 3.1 pack_keyfile uses method 2 and needs an external key file')
    keys, active, seen = [], key_file, False
    for entry in index.entries:
        keys.append(active)
        if entry.name == PACK_KEY_NAME and mode in CHAINED_MODES:
            if seen:
                raise ValueError('multiple internal QLIE pack_keyfile entries')
            seen = True
            active = read_member(stream, index, entry, mode=mode, key_file=active, game_key=game_key,
                                 max_stored=1 << 20, max_output=1 << 20)
    return keys
