"""Template writer for FilePackVer3.0 (HashVer1.3/1.4) and 3.1 + HashVer1.4.

New inverse writer based on the GARbro-derived qlie.py reader; names and
order are unchanged. HashVer1.3/1.4 layouts were checked against actual
archives; schema cross-reference: msg-tool src/scripts/qlie/archive/pack/
{types,v31}.rs (GPL-3.0). No version conversion, new members, renaming or
key generation. Preserve the verified filename lookup table because its
offsets address the ordinal array, not payloads.
"""
from dataclasses import replace
import struct
from typing import BinaryIO

from .qlie import (Entry, Index, PACK_KEY_NAME, checksum, crypt_name, crypt_name31, decrypt,
                   decompress, encrypt, member_keys, read_index, read_member)

# (PACK version, lookup signature) -> header size, bucket-count width, name
# unit (bytes per length unit) and ordinal width. A 3.0 pack may carry either
# table: HashVer1.4 there keeps the 1.3 body (u16 buckets, CP932 byte names,
# u16 ordinals) behind the 68-byte 1.4 header with the compression flag.
LOOKUPS = {('3.0', b'HashVer1.3'): (32, 2, 1, 2),
           ('3.0', b'HashVer1.4'): (68, 2, 1, 2),
           ('3.1', b'HashVer1.4'): (68, 4, 2, 4)}


def _read(stream, at, size):
    stream.seek(at)
    data = stream.read(size)
    if len(data) != size:
        raise ValueError('truncated QLIE template')
    return data


def lookup_version(stream: BinaryIO, index: Index) -> str:
    """Lookup-table signature after the index, e.g. 'HashVer1.3' (not validated)."""
    head = _read(stream, index.index_end, 16)
    return head[:10].decode('ascii', errors='replace')


def _lookup(stream: BinaryIO, index: Index, signature: bytes, max_bytes: int) -> bytes:
    """Validate every lookup name -> ordinal mapping before preserving the tail.

    Header: signature, u32 buckets=256, count, ordinal-array size, stored size;
    1.4 adds a compression flag and 32 opaque bytes kept verbatim. Lookup: per
    bucket n, then n x (u16 length, name, u64 offset into the ordinal array,
    u32 name hash); then the ordinal array.
    """
    layout = LOOKUPS.get((index.version, signature))
    if layout is None:
        raise ValueError(f'FilePackVer{index.version} template writer does not support '
                         f'{signature.decode("ascii", "replace")}')
    header, bucket_width, unit, ordinal_width = layout
    label = signature.decode('ascii')
    size = index.file_size - 28 - index.index_end
    if not header + 1060 <= size <= max_bytes:
        raise ValueError('unsupported QLIE hash/key tail size')
    tail = _read(stream, index.index_end, size)
    if tail[:16] != signature + bytes(6):
        raise ValueError(f'FilePackVer{index.version} template writer requires {label}')
    buckets, count, mapping_size, stored = struct.unpack_from('<IIII', tail, 16)
    compressed = struct.unpack_from('<I', tail, 32)[0] if header == 68 else 1
    if (buckets != 256 or count != len(index.entries) or count >= 1 << (8 * ordinal_width)
            or mapping_size != count * ordinal_width or header + stored + 1060 != len(tail)):
        raise ValueError(f'invalid {label} dimensions')
    if compressed not in (0, 1):
        raise ValueError(f'unknown {label} compression flag')
    if struct.unpack_from('<I', tail, len(tail) - 1028)[0] != header + stored:
        raise ValueError('QLIE key trailer hash-size mismatch')
    synthetic = Entry('hash', b'hash', 0, stored, stored, 0, 1, 0)
    data = decrypt(tail[header:header + stored], synthetic, 0x428, mode='legacy')
    if compressed:  # 1.4 flag 0 (seen in separately built patch packs): encrypted only
        if data[:4] != b'1PC\xff' or len(data) < 12:
            raise ValueError(f'{label} compression signature mismatch')
        data = decompress(data, expected_size=struct.unpack_from('<I', data, 8)[0], max_output=max_bytes)
    pos, refs = 0, []

    def take(n):
        nonlocal pos
        if n < 0 or pos + n > len(data):
            raise ValueError(f'truncated {label} lookup')
        result = data[pos:pos + n]
        pos += n
        return result

    for _ in range(buckets):
        n = int.from_bytes(take(bucket_width), 'little')
        if len(refs) + n > count:
            raise ValueError(f'{label} entry count overflow')
        for _ in range(n):
            length = int.from_bytes(take(2), 'little')
            if not 0 < length <= 256:
                raise ValueError(f'{label} filename length mismatch')
            name = take(unit * length)
            offset, _name_hash = struct.unpack('<QI', take(12))
            refs.append((name, offset))
    mapping = struct.unpack('<' + ('H' if ordinal_width == 2 else 'I') * count, take(mapping_size))
    if pos != len(data) or len(refs) != count or sorted(mapping) != list(range(count)):
        raise ValueError(f'{label} ordinal array mismatch')
    seen = set()
    for name, offset in refs:
        if offset % ordinal_width or offset >= mapping_size:
            raise ValueError(f'{label} lookup offset outside ordinal array')
        ordinal = mapping[offset // ordinal_width]
        if ordinal in seen or name != index.entries[ordinal].raw_name:
            raise ValueError(f'{label} filename/ordinal disagrees with index')
        seen.add(ordinal)
    return tail


def hash13_tail(stream: BinaryIO, index: Index, *, max_bytes: int = 32 << 20) -> bytes:
    """3.0 HashVer1.3 (32-byte header, always 1PC-compressed)."""
    return _lookup(stream, index, b'HashVer1.3', max_bytes)


def hash14_tail(stream: BinaryIO, index: Index, *, max_bytes: int = 32 << 20) -> bytes:
    """HashVer1.4: 3.1 UTF-16LE/u32 body, or 3.0 CP932/u16 body (see LOOKUPS)."""
    return _lookup(stream, index, b'HashVer1.4', max_bytes)


def lookup_tail(stream: BinaryIO, index: Index) -> bytes:
    """Validated hash/key tail for the archive's PACK version and table signature."""
    signature = lookup_version(stream, index).encode('ascii', errors='replace')
    return _lookup(stream, index, signature, 32 << 20)


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
    tail = lookup_tail(source, index)
    by_name = {e.name: e for e in index.entries}
    if len(by_name) != len(index.entries) or not isinstance(replacements, dict) or set(replacements) - by_name.keys():
        raise ValueError('unknown or duplicate QLIE replacement member')
    if PACK_KEY_NAME in replacements:
        raise ValueError('changing the internal QLIE key is unsupported')
    if any(not isinstance(v, bytes) or len(v) > max_replacement for v in replacements.values()):
        raise ValueError('QLIE replacement size/type budget exceeded')
    if sum(map(len, replacements.values())) > max_total:
        raise ValueError('QLIE total replacement budget exceeded')
    keys = dict(zip(by_name, member_keys(source, index, mode=mode, key_file=key_file,
                                         game_key=game_key)))
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
                new_entry = replace(new_entry, checksum=checksum(encoded, index.version))
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
        if index.version == '3.0':
            name = struct.pack('<H', len(e.raw_name)) + crypt_name(e.raw_name, index.arc_key)
        else:
            name = struct.pack('<H', len(e.raw_name) // 2) + crypt_name31(e.raw_name, index.arc_key)
        destination.write(name)
        destination.write(struct.pack('<QIIIII', e.offset, e.size, e.unpacked_size, e.packed, e.encryption, e.checksum))
    destination.write(tail)
    destination.write(b'FilePackVer' + index.version.encode('ascii') + b'\0\0'
                      + struct.pack('<IQ', len(index.entries), new_index_offset))
    destination.flush()
    # Must be a readable output stream: verify lookup data and every replacement.
    check = read_index(destination)
    if check.version != index.version or check.arc_key != index.arc_key or lookup_tail(destination, check) != tail:
        raise ValueError('QLIE filename lookup table changed')
    for entry in check.entries:
        if entry.name in replacements:
            actual = read_member(destination, check, entry, mode=mode, key_file=keys[entry.name],
                                 game_key=game_key, max_stored=max_replacement, max_output=max_replacement)
            if actual != replacements[entry.name]:
                raise ValueError('rebuilt QLIE member differs from replacement')
    return {'entries': len(index.entries), 'changed': changed, 'roundtripped': roundtripped,
            'output_size': check.file_size, 'pack_version': index.version, 'mode': mode,
            'hash_lookup': 'verified-and-preserved',
            'compression': 'changed-members-stored-uncompressed', 'game_launch_tested': False}
