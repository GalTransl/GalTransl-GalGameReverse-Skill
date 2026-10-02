"""Template writer for FilePackVer3.0 + HashVer1.3, unchanged names/order.

New inverse writer based on the GARbro-derived qlie.py reader. HashVer1.3
layout was checked against actual archives; schema cross-reference:
msg-tool src/scripts/qlie/archive/pack/types.rs (GPL-3.0). No 3.1 conversion,
new members, renaming or game key generation. Preserve the verified filename
lookup table because its offsets address the ordinal array, not payloads.
"""
from dataclasses import replace
import struct
from typing import BinaryIO

from .qlie import (Entry, Index, PACK_KEY_NAME, crypt_name, decrypt, decompress,
                   encrypt, hash_v3, read_index, read_member)


def _read(stream, at, size):
    stream.seek(at)
    data = stream.read(size)
    if len(data) != size:
        raise ValueError('truncated QLIE template')
    return data


def hash13_tail(stream: BinaryIO, index: Index, *, max_bytes: int = 32 << 20) -> bytes:
    """Validate every lookup name -> ordinal mapping before preserving tail."""
    size = index.file_size - 28 - index.index_end
    if not 1092 <= size <= max_bytes:
        raise ValueError('unsupported QLIE hash/key tail size')
    tail = _read(stream, index.index_end, size)
    if tail[:16] != b'HashVer1.3\0\0\0\0\0\0':
        raise ValueError('template writer requires HashVer1.3')
    buckets, count, mapping_size, stored = struct.unpack_from('<IIII', tail, 16)
    if (buckets != 256 or count != len(index.entries) or count > 65535
            or mapping_size != count * 2 or 32 + stored + 1060 != len(tail)):
        raise ValueError('invalid HashVer1.3 dimensions')
    if struct.unpack_from('<I', tail, len(tail) - 1028)[0] != 32 + stored:
        raise ValueError('QLIE key trailer hash-size mismatch')
    synthetic = Entry('hash', b'hash', 0, stored, stored, 0, 1, 0)
    data = decrypt(tail[32:32 + stored], synthetic, 0x428, mode='legacy')
    if data[:4] != b'1PC\xff' or len(data) < 12:
        raise ValueError('HashVer1.3 compression signature mismatch')
    data = decompress(data, expected_size=struct.unpack_from('<I', data, 8)[0], max_output=max_bytes)
    pos, refs = 0, []

    def take(n):
        nonlocal pos
        if n < 0 or pos + n > len(data):
            raise ValueError('truncated HashVer1.3 lookup')
        result = data[pos:pos + n]
        pos += n
        return result

    for _ in range(buckets):
        n = int.from_bytes(take(2), 'little')
        if len(refs) + n > count:
            raise ValueError('HashVer1.3 entry count overflow')
        for _ in range(n):
            length = int.from_bytes(take(2), 'little')
            if not 0 < length <= 256:
                raise ValueError('HashVer1.3 filename length mismatch')
            name = take(length)
            offset, _name_hash = struct.unpack('<QI', take(12))
            refs.append((name, offset))
    mapping = struct.unpack('<' + 'H' * count, take(mapping_size))
    if pos != len(data) or len(refs) != count or sorted(mapping) != list(range(count)):
        raise ValueError('HashVer1.3 ordinal array mismatch')
    seen = set()
    for name, offset in refs:
        if offset % 2 or offset >= mapping_size:
            raise ValueError('HashVer1.3 lookup offset outside ordinal array')
        ordinal = mapping[offset // 2]
        if ordinal in seen or name != index.entries[ordinal].raw_name:
            raise ValueError('HashVer1.3 filename/ordinal disagrees with index')
        seen.add(ordinal)
    return tail


def rebuild(source: BinaryIO, destination: BinaryIO, replacements: dict[str, bytes], *,
            mode: str, key_file: bytes | None = None, game_key: bytes | None = None,
            max_replacement: int = 8 << 20, max_total: int = 64 << 20) -> dict:
    """Rebuild into a NEW empty stream; source must be a separate read-only file.

    Existing members only. Changed members use the engine's uncompressed flag
    and retain their encryption mode. Equal replacements are decrypted and
    re-encrypted with the original compressed bytes, enabling exact no-op
    roundtrips through the writer. Unselected media is copied in 1 MiB chunks.
    Caller owns exclusive file creation and partial-output cleanup.
    """
    if source is destination:
        raise ValueError('cannot rebuild QLIE in place')
    destination.seek(0, 2)
    if destination.tell() != 0:
        raise ValueError('QLIE writer requires an empty destination')
    index = read_index(source)
    tail = hash13_tail(source, index)
    by_name = {e.name: e for e in index.entries}
    if len(by_name) != len(index.entries) or not isinstance(replacements, dict) or set(replacements) - by_name.keys():
        raise ValueError('unknown or duplicate QLIE replacement member')
    if PACK_KEY_NAME in replacements:
        raise ValueError('changing the internal QLIE key is unsupported')
    if any(not isinstance(v, bytes) or len(v) > max_replacement for v in replacements.values()):
        raise ValueError('QLIE replacement size/type budget exceeded')
    if sum(map(len, replacements.values())) > max_total:
        raise ValueError('QLIE total replacement budget exceeded')
    keys = {}
    active_key = key_file
    for entry in index.entries:
        keys[entry.name] = active_key
        if entry.name == PACK_KEY_NAME and mode != 'legacy':
            active_key = read_member(source, index, entry, mode=mode, key_file=active_key,
                                     game_key=game_key, max_stored=1 << 20, max_output=1 << 20)
    updated = {}
    cursor, changed, roundtripped = 0, 0, 0

    def copy(at, length):
        if length < 0:
            raise ValueError('overlapping/ambiguous QLIE physical layout')
        source.seek(at)
        while length:
            chunk = source.read(min(length, 1 << 20))
            if not chunk:
                raise ValueError('truncated QLIE template while copying')
            destination.write(chunk)
            length -= len(chunk)

    # Physical order can differ from index order; retain both independently.
    for entry in sorted(index.entries, key=lambda e: e.offset):
        copy(cursor, entry.offset - cursor)
        offset = destination.tell()
        if entry.name in replacements:
            data = replacements[entry.name]
            old = read_member(source, index, entry, mode=mode, key_file=keys[entry.name],
                              game_key=game_key, max_stored=max_replacement, max_output=max_replacement)
            if old == data:
                stored = _read(source, entry.offset, entry.size)
                plain = decrypt(stored, entry, index.arc_key, mode=mode,
                                key_file=keys[entry.name], game_key=game_key)
                encoded = encrypt(plain, entry, index.arc_key, mode=mode,
                                  key_file=keys[entry.name], game_key=game_key)
                if encoded != stored:
                    raise ValueError('QLIE encryption no-op is not byte-identical')
                new_entry = replace(entry, offset=offset)
                roundtripped += 1
            else:
                new_entry = replace(entry, offset=offset, size=len(data), unpacked_size=len(data), packed=0)
                encoded = encrypt(data, new_entry, index.arc_key, mode=mode,
                                  key_file=keys[entry.name], game_key=game_key)
                new_entry = replace(new_entry, checksum=hash_v3(encoded))
                changed += 1
            destination.write(encoded)
            updated[entry.name] = new_entry
        else:
            copy(entry.offset, entry.size)
            updated[entry.name] = replace(entry, offset=offset)
        cursor = entry.offset + entry.size
    copy(cursor, index.index_offset - cursor)
    new_index_offset = destination.tell()
    for entry in index.entries:
        e = updated[entry.name]
        destination.write(struct.pack('<H', len(e.raw_name)) + crypt_name(e.raw_name, index.arc_key))
        destination.write(struct.pack('<QIIIII', e.offset, e.size, e.unpacked_size, e.packed, e.encryption, e.checksum))
    destination.write(tail)
    destination.write(b'FilePackVer3.0\0\0' + struct.pack('<IQ', len(index.entries), new_index_offset))
    destination.flush()
    # Must be a readable output stream: verify lookup data and every replacement.
    check = read_index(destination)
    if hash13_tail(destination, check) != tail:
        raise ValueError('QLIE filename lookup table changed')
    for entry in check.entries:
        if entry.name in replacements:
            actual = read_member(destination, check, entry, mode=mode, key_file=keys[entry.name],
                                 game_key=game_key, max_stored=max_replacement, max_output=max_replacement)
            if actual != replacements[entry.name]:
                raise ValueError('rebuilt QLIE member differs from replacement')
    return {'entries': len(index.entries), 'changed': changed, 'roundtripped': roundtripped,
            'output_size': check.file_size, 'hash_lookup': 'verified-and-preserved',
            'compression': 'changed-members-stored-uncompressed', 'game_launch_tested': False}
