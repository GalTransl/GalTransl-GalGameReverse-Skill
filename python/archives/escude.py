"""Bounded ESC-ARC2 reader and template repacker, with acp literal encoding.

Adapted from msg-tool src/scripts/escude/{archive,crypto,lzw}.rs,
commit f72716cee88554d40c1cdface2812493b14ca653, GPL-3.0-or-later.
Modifications: independent Python, explicit budgets, strict offsets/streams,
no truncated-output or zero-filled success on malformed compressed input.
"""
from dataclasses import dataclass
import hashlib
import struct
from typing import BinaryIO
import io

from python.common.safety import validate_names


@dataclass(frozen=True)
class Entry:
    ordinal: int
    name: str
    offset: int
    size: int


@dataclass(frozen=True)
class Index:
    entries: tuple[Entry, ...]
    archive_size: int
    data_start: int
    index_sha256: str


def _exact(stream: BinaryIO, count: int) -> bytes:
    data = stream.read(count)
    if len(data) != count:
        raise ValueError("truncated ESC-ARC2 data")
    return data


def _next_key(seed: int) -> int:
    seed ^= 0x65AC9365
    return (seed ^ (((seed >> 1) ^ seed) >> 3)
            ^ (((seed << 1) ^ seed) << 3)) & 0xFFFFFFFF


def read_index(stream: BinaryIO, *, max_entries: int = 100_000,
               max_index_bytes: int = 16 << 20) -> Index:
    """Read only the V2 header, encrypted index and plain CP932 name table.

    Names are data: validate_names must run before writing extracted files.
    The index digest is not a hash of the archive payload.
    """
    stream.seek(0, 2)
    size = stream.tell()
    stream.seek(0)
    head = _exact(stream, 20)
    if head[:8] != b"ESC-ARC2":
        raise ValueError("not ESC-ARC2 (V1 is not implemented)")
    seed, count, names_size = struct.unpack_from("<III", head, 8)
    seed = _next_key(seed)
    count ^= seed
    seed = _next_key(seed)
    names_size ^= seed
    if not 0 < count <= max_entries:
        raise ValueError("ESC-ARC2 entry count exceeds budget")
    index_size = count * 12
    data_start = 20 + index_size + names_size
    if index_size + names_size > max_index_bytes or data_start > size:
        raise ValueError("ESC-ARC2 index truncated or exceeds budget")
    encrypted = _exact(stream, index_size)
    names = _exact(stream, names_size)
    words = []
    for word, in struct.iter_unpack("<I", encrypted):
        seed = _next_key(seed)
        words.append(word ^ seed)
    entries = []
    for i in range(count):
        name_pos, offset, length = words[3*i:3*i+3]
        if name_pos >= len(names) or (name_pos and names[name_pos-1] != 0):
            raise ValueError("invalid ESC-ARC2 name offset")
        end = names.find(b"\0", name_pos)
        if end <= name_pos:
            raise ValueError("empty or unterminated ESC-ARC2 name")
        name = names[name_pos:end].decode("cp932", errors="strict")
        if offset < data_start or offset + length > size:
            raise ValueError("ESC-ARC2 member outside payload")
        entries.append(Entry(i, name, offset, length))
    previous_end = data_start
    for entry in sorted(entries, key=lambda e: e.offset):
        if entry.size and entry.offset < previous_end:
            raise ValueError("overlapping ESC-ARC2 members")
        previous_end = max(previous_end, entry.offset + entry.size)
    return Index(tuple(entries), size, data_start,
                 hashlib.sha256(head + encrypted + names).hexdigest())


def probe_member(stream: BinaryIO, entry: Entry, *, limit: int = 32) -> bytes:
    if not 0 <= limit <= 4096:
        raise ValueError("invalid ESC-ARC2 probe budget")
    stream.seek(entry.offset)
    return _exact(stream, min(entry.size, limit))


def decode_acp(data: bytes, *, max_output: int = 64 << 20) -> bytes:
    """Decode acp NUL + BE u32 length + MSB codes, with overlapping copies.

    0x100 ends, 0x101 grows the width, 0x102 resets the offset dictionary.
    The output size is an exact invariant, not permission to truncate a token.
    """
    if len(data) < 8 or data[:4] != b"acp\0":
        raise ValueError("not acp LZW")
    size, = struct.unpack_from(">I", data, 4)
    if size > max_output:
        raise ValueError("acp output exceeds budget")
    pos, bits, buffer = 8, 0, 0
    width = 9
    dictionary = []
    output = bytearray()
    while True:
        while bits < width:
            if pos >= len(data):
                raise ValueError("truncated acp bitstream")
            buffer = (buffer << 8) | data[pos]
            pos += 1
            bits += 8
        bits -= width
        token = buffer >> bits
        buffer &= (1 << bits) - 1
        if token == 0x100:
            if len(output) != size:
                raise ValueError("early acp end code")
            if pos != len(data) or buffer:
                raise ValueError("unknown acp trailing data")
            return bytes(output)
        if token == 0x101:
            width += 1
            if width > 24:
                raise ValueError("acp token width exceeds 24")
            continue
        if token == 0x102:
            width = 9
            dictionary.clear()
            continue
        if len(output) >= size or len(dictionary) >= 0x8900:
            raise ValueError("acp output/dictionary overflow")
        dictionary.append(len(output))
        if token < 0x100:
            output.append(token)
            continue
        ref = token - 0x103
        if not 0 <= ref < len(dictionary) - 1:
            raise ValueError("invalid acp dictionary reference")
        src = dictionary[ref]
        count = dictionary[ref+1] - src + 1
        if len(output) + count > size:
            raise ValueError("acp token exceeds declared output")
        for i in range(count):
            output.append(output[src+i])


def read_member(stream: BinaryIO, entry: Entry, *, max_stored: int = 64 << 20,
                max_output: int = 64 << 20) -> bytes:
    """Read/decode one selected member; callers also enforce a batch budget."""
    if not 0 <= entry.size <= max_stored:
        raise ValueError("ESC-ARC2 stored member exceeds budget")
    stream.seek(entry.offset)
    raw = _exact(stream, entry.size)
    if raw.startswith(b"acp"):
        return decode_acp(raw, max_output=max_output)
    if len(raw) > max_output:
        raise ValueError("ESC-ARC2 plain member exceeds output budget")
    return raw


def encode_acp_literal(data: bytes, *, max_output: int = 64 << 20) -> bytes:
    """Emit 9-bit literals; reset before the decoder's 0x8900-token limit.

    This favors verifiability over compression ratio. Padding bits are zero.
    """
    size = 8 + (9 * (len(data) + max(0, len(data) - 1) // 0x8800 + 1) + 7) // 8
    if size > max_output or len(data) > 0xffffffff:
        raise ValueError('acp encoded output exceeds budget')
    output = bytearray(b'acp\0' + struct.pack('>I', len(data)))
    buffer = bits = 0
    def emit(token):
        nonlocal buffer, bits
        buffer = (buffer << 9) | token
        bits += 9
        while bits >= 8:
            bits -= 8
            output.append((buffer >> bits) & 255)
        buffer &= (1 << bits) - 1
    for i, value in enumerate(data):
        if i and i % 0x8800 == 0:
            emit(0x102)
        emit(value)
    emit(0x100)
    if bits:
        output.append(buffer << (8 - bits))
    return bytes(output)


def repack(template: bytes, replacements: dict[str, bytes], *,
           max_output: int = 128 << 20, max_member: int = 16 << 20) -> bytes:
    """Replace decoded members by normalized names in a contiguous ARC2 template.

    Keep the seed, name bytes, order and untouched stored payloads. Changed acp
    members retain acp wrapping. Unknown gaps, trailers or empty spans fail closed.
    Recompute and encrypt offsets/sizes; no-op rebuilding is byte-identical.
    """
    if len(template) > max_output:
        raise ValueError('ESC-ARC2 template exceeds budget')
    stream = io.BytesIO(template)
    index = read_index(stream)
    names = validate_names([e.name for e in index.entries])
    if set(replacements) - set(names):
        raise ValueError('unknown ESC-ARC2 replacement member')
    if any(not isinstance(v, bytes) or len(v) > max_member for v in replacements.values()):
        raise ValueError('invalid or oversized replacement')
    cursor = index.data_start
    for entry in index.entries:
        if entry.offset != cursor or entry.size == 0:
            raise ValueError('writer requires contiguous ordered nonempty members')
        cursor += entry.size
    if cursor != len(template):
        raise ValueError('writer does not support an archive trailer')
    result = bytearray(template[:index.data_start])
    seed, = struct.unpack_from('<I', template, 8)
    for _ in range(2):
        seed = _next_key(seed)
    for entry, name in zip(index.entries, names):
        stored = template[entry.offset:entry.offset + entry.size]
        if name in replacements:
            before = read_member(stream, entry, max_output=max_member)
            if replacements[name] != before:
                compressed = stored.startswith(b'acp\0')
                stored = (encode_acp_literal(replacements[name], max_output=max_output)
                          if compressed else replacements[name])
                if not stored or (not compressed and stored.startswith(b'acp')):
                    raise ValueError('replacement changes compression signature semantics')
        offset = len(result)
        if offset + len(stored) > min(max_output, 0xffffffff):
            raise ValueError('rebuilt ESC-ARC2 exceeds budget')
        result.extend(stored)
        # The name-offset word stays encrypted with the same key sequence.
        seed = _next_key(seed)
        seed = _next_key(seed)
        struct.pack_into('<I', result, 24 + entry.ordinal * 12, offset ^ seed)
        seed = _next_key(seed)
        struct.pack_into('<I', result, 28 + entry.ordinal * 12, len(stored) ^ seed)
    return bytes(result)
