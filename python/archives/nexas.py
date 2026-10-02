# SPDX-License-Identifier: GPL-3.0-only
"""NeXAS PAC tail-index reader/writer (not the legacy front-index dialect).

Format reference: GARbro-Mod bc26d991ef5cdc0e1ecb32122ee9a48c3375750c,
ArcFormats/Nexas/ArcPAC.cs and HuffmanCompression.cs, Copyright (C)
2014-2018 morkt, MIT; notice: provenance/licenses/MIT-GARbro.txt.
Writer and strict bounds are new. Zstandard support needs `zstandard`.
"""
from dataclasses import dataclass
import heapq
import io
import struct
import zlib

from ..common.binary import FormatError, bounded_zlib
from ..common.safety import Limits, validate_names


def huffman_decode(data: bytes, size: int, *, max_output: int = 16 << 20) -> bytes:
    if not 0 <= size <= max_output:
        raise FormatError("Huffman output exceeds budget")
    bitpos = 0
    nodes = 0

    def bits(n):
        nonlocal bitpos
        if bitpos + n > len(data) * 8:
            raise FormatError("truncated Huffman stream")
        value = 0
        for _ in range(n):
            value = (value << 1) | ((data[bitpos // 8] >> (7 - bitpos % 8)) & 1)
            bitpos += 1
        return value

    def tree(depth=0):
        nonlocal nodes
        nodes += 1
        if nodes > 511 or depth > 255:
            raise FormatError("oversized Huffman tree")
        if bits(1):
            return (tree(depth + 1), tree(depth + 1))
        return bits(8)

    root = tree()
    out = bytearray()
    for _ in range(size):
        node = root
        while isinstance(node, tuple):
            node = node[bits(1)]
        out.append(node)
    if len(data) * 8 - bitpos > 7 or bits(len(data) * 8 - bitpos):
        raise FormatError("trailing Huffman data or nonzero padding")
    return bytes(out)


def huffman_encode(data: bytes) -> bytes:
    """Serialize a frequency tree, MSB-first symbols, and zero bit padding."""
    counts = [0] * 256
    for byte in data:
        counts[byte] += 1
    heap = [(count, symbol, symbol) for symbol, count in enumerate(counts) if count]
    if not heap:
        heap = [(1, 0, 0)]
    heapq.heapify(heap)
    serial = 256
    while len(heap) > 1:
        a, _, left = heapq.heappop(heap)
        b, _, right = heapq.heappop(heap)
        heapq.heappush(heap, (a + b, serial, (left, right)))
        serial += 1
    out = bytearray()
    pending = used = 0

    def emit(value, count):
        nonlocal pending, used
        for shift in range(count - 1, -1, -1):
            pending = (pending << 1) | ((value >> shift) & 1)
            used += 1
            if used == 8:
                out.append(pending)
                pending = used = 0

    codes = {}

    def tree(node, code=0, length=0):
        if isinstance(node, int):
            emit(node, 9)
            codes[node] = (code, length)
        else:
            emit(1, 1)
            tree(node[0], code << 1, length + 1)
            tree(node[1], (code << 1) | 1, length + 1)

    tree(heap[0][2])
    for byte in data:
        emit(*codes[byte])
    if used:
        out.append(pending << (8 - used))
    return bytes(out)


@dataclass(frozen=True)
class Entry:
    name: str
    name_raw: bytes
    offset: int
    unpacked_size: int
    packed_size: int


@dataclass(frozen=True)
class Index:
    marker: int
    pack_type: int
    entries: tuple[Entry, ...]
    index_offset: int
    file_size: int


def _read(stream, size):
    data = stream.read(size)
    if len(data) != size:
        raise FormatError("truncated PAC")
    return data


def read_index(stream, *, limits: Limits = Limits(), max_index_bytes: int = 16 << 20) -> Index:
    stream.seek(0, 2)
    size = stream.tell()
    if size < 16:
        raise FormatError("short PAC")
    stream.seek(0)
    magic, count, pack_type = struct.unpack("<4sII", _read(stream, 12))
    # Byte 3 is not reliably NUL: retail PACu and patch PAC\xbf both occur.
    if magic[:3] != b"PAC" or not 0 < count <= limits.max_entries:
        raise FormatError("not a supported PAC header")
    if pack_type not in (0, 2, 3, 4, 5, 6, 7):
        raise FormatError(f"unsupported PAC compression: {pack_type}")
    if count * 76 > max_index_bytes:
        raise FormatError("PAC index exceeds budget")
    stream.seek(size - 4)
    packed_size = struct.unpack("<I", _read(stream, 4))[0]
    offset = size - 4 - packed_size
    if offset < 12 or not 0 < packed_size <= min(max_index_bytes, count * 152):
        raise FormatError("invalid PAC tail index size (front-index PAC unsupported)")
    stream.seek(offset)
    packed = bytes(byte ^ 255 for byte in _read(stream, packed_size))
    raw = huffman_decode(packed, count * 76, max_output=max_index_bytes)
    entries = []
    for i in range(count):
        record = raw[i * 76:(i + 1) * 76]
        name_raw = record[:64]
        end = name_raw.find(b"\0")
        if end <= 0:
            raise FormatError("unterminated or empty PAC name")
        try:
            name = name_raw[:end].decode("cp932")
        except UnicodeError as exc:
            raise FormatError("PAC name is not CP932") from exc
        start, unpacked, stored = struct.unpack_from("<III", record, 64)
        if start < 12 or start + stored > offset:
            raise FormatError(f"PAC member outside payload region: {name}")
        if pack_type in (0, 5) and unpacked != stored:
            raise FormatError("raw PAC member size mismatch")
        entries.append(Entry(name, name_raw, start, unpacked, stored))
    validate_names([e.name for e in entries], limits)
    end = 12
    for entry in sorted(entries, key=lambda e: e.offset):
        if entry.offset < end:
            raise FormatError("overlapping PAC payloads")
        end = entry.offset + entry.packed_size
    return Index(magic[3], pack_type, tuple(entries), offset, size)


def _zstd():
    try:
        import zstandard
    except ImportError as exc:
        raise FormatError("NeXAS types 6/7 require the optional zstandard package") from exc
    return zstandard


def read_member(stream, index: Index, entry: Entry, *, limits: Limits = Limits()) -> bytes:
    if entry not in index.entries:
        raise FormatError("member does not belong to PAC index")
    if max(entry.unpacked_size, entry.packed_size) > limits.max_file_bytes:
        raise FormatError("PAC member exceeds budget")
    stream.seek(entry.offset)
    data = _read(stream, entry.packed_size)
    mode = index.pack_type
    if mode in (0, 5) or (mode in (4, 7) and len(data) == entry.unpacked_size):
        result = data
    elif mode == 2:
        result = huffman_decode(data, entry.unpacked_size, max_output=limits.max_file_bytes)
    elif mode in (3, 4):
        result = bounded_zlib(data, max_output=entry.unpacked_size, expected_size=entry.unpacked_size)
    else:
        zstd = _zstd()
        try:
            declared = zstd.frame_content_size(data)
            if declared not in (zstd.CONTENTSIZE_UNKNOWN, entry.unpacked_size):
                raise FormatError("Zstandard size disagrees with PAC index")
            result = zstd.ZstdDecompressor(max_window_size=max(1024, limits.max_file_bytes // 1024)).decompress(
                data, max_output_size=max(1, entry.unpacked_size), allow_extra_data=False)
        except zstd.ZstdError as exc:
            raise FormatError(f"invalid Zstandard member: {exc}") from exc
    if len(result) != entry.unpacked_size:
        raise FormatError("PAC decoded size mismatch")
    return result


def rebuild(stream, index: Index, replacements: dict[str, bytes], *, limits: Limits = Limits()) -> bytes:
    """Rebuild all offsets and the tail index; copy untouched packed members.

    Mode 4/7 stores compressed data only if smaller, matching reader semantics.
    Header byte 3 and original 64-byte name fields are preserved.
    """
    if set(replacements) - {entry.name for entry in index.entries}:
        raise FormatError("unknown PAC replacement")
    if index.file_size > limits.max_total_bytes:
        raise FormatError("PAC rebuild input exceeds budget")
    output = bytearray(struct.pack("<4sII", b"PAC" + bytes([index.marker]), len(index.entries), index.pack_type))
    directory = bytearray()
    for entry in index.entries:
        if entry.name in replacements:
            payload = replacements[entry.name]
            if not isinstance(payload, bytes) or len(payload) > limits.max_file_bytes:
                raise FormatError("PAC replacement exceeds budget")
            unpacked = len(payload)
            mode = index.pack_type
            if mode == 2:
                packed = huffman_encode(payload)
            elif mode in (3, 4):
                packed = zlib.compress(payload)
            elif mode in (6, 7):
                packed = _zstd().ZstdCompressor(level=3).compress(payload)
            else:
                packed = payload
            if mode in (4, 7) and len(packed) >= unpacked:
                packed = payload
        else:
            if entry.packed_size > limits.max_file_bytes:
                raise FormatError("PAC stored member exceeds budget")
            stream.seek(entry.offset)
            packed = _read(stream, entry.packed_size)
            unpacked = entry.unpacked_size
        directory.extend(entry.name_raw + struct.pack("<III", len(output), unpacked, len(packed)))
        if len(output) + len(packed) > limits.max_total_bytes:
            raise FormatError("PAC rebuild exceeds budget")
        output.extend(packed)
    packed_index = bytes(byte ^ 255 for byte in huffman_encode(bytes(directory)))
    output.extend(packed_index)
    output.extend(struct.pack("<I", len(packed_index)))
    if len(output) > limits.max_total_bytes:
        raise FormatError("PAC rebuild exceeds budget")
    read_index(io.BytesIO(output), limits=limits)
    return bytes(output)
