# SPDX-License-Identifier: GPL-3.0-only
"""Bounded UnityFS (AssetBundle) reader and uncompressed rebuilder.

Supports UnityFS archive format versions 6, 7 and 8 with LZMA, LZ4 or LZ4HC
blocks (or none). The blocks/directory info may follow the header or sit at the
end of the file (flag 0x80). Version 7+ aligns the header to 16 bytes and flag
0x200 (``BlockInfoNeedPaddingAtStart``) aligns the first data block to 16.
Older engines reused 0x200 for a vendor encryption scheme, so 0x200 is only
accepted for engine versions that postdate the alignment change.

LZ4 is decoded by a pure-Python block decoder; LZMA uses the standard library.
The writer emits uncompressed data blocks and uncompressed blocks info; it
keeps node order, paths, flags, the engine version strings and the placement
of the blocks info. Every rebuild is reread with this reader and compared per
node. No game code is executed and no Unity runtime is required.

Layout notes are an independent implementation of the published UnityFS
structure; see provenance/unity-containers.json for the format references.
"""
from dataclasses import dataclass
import io
import lzma
import re
import struct

from ..common.binary import FormatError

SIGNATURE = b"UnityFS\0"
LEGACY_SIGNATURES = (b"UnityWeb\0", b"UnityRaw\0", b"UnityArchive\0")
VERSIONS = (6, 7, 8)

COMPRESSION_MASK = 0x3F
FLAG_COMBINED = 0x40
FLAG_INFO_AT_END = 0x80
FLAG_PADDING_AT_START = 0x200
KNOWN_FLAGS = COMPRESSION_MASK | FLAG_COMBINED | FLAG_INFO_AT_END | FLAG_PADDING_AT_START
BLOCK_STREAMED = 0x40
NODE_FLAGS = 0x7  # directory / deleted / serialized-file bits
COMPRESSION_NAMES = {0: "none", 1: "lzma", 2: "lz4", 3: "lz4hc"}

MAX_FILE = 64 << 30
MAX_INFO = 16 << 20
MAX_BLOCKS = 1 << 20
MAX_NODES = 65536
MAX_BLOCK = 2 << 30
MAX_READ = 512 << 20
MAX_REBUILD = 512 << 20

_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)")


def lz4_block(src, size):
    """Decode one raw LZ4 block to exactly ``size`` bytes (LZ4 and LZ4HC)."""
    if not 0 <= size <= MAX_BLOCK:
        raise FormatError("LZ4 output size outside budget")
    src = memoryview(src)
    out = bytearray()
    pos, end = 0, len(src)
    while True:
        if pos >= end:
            raise FormatError("truncated LZ4 sequence")
        token = src[pos]
        pos += 1
        literal = token >> 4
        if literal == 15:
            while True:
                if pos >= end:
                    raise FormatError("truncated LZ4 literal length")
                extra = src[pos]
                pos += 1
                literal += extra
                if extra != 255:
                    break
        if pos + literal > end or len(out) + literal > size:
            raise FormatError("LZ4 literal run out of bounds")
        out += src[pos:pos + literal]
        pos += literal
        if pos == end:
            break
        if pos + 2 > end:
            raise FormatError("truncated LZ4 match offset")
        offset = src[pos] | src[pos + 1] << 8
        pos += 2
        match = token & 15
        if match == 15:
            while True:
                if pos >= end:
                    raise FormatError("truncated LZ4 match length")
                extra = src[pos]
                pos += 1
                match += extra
                if extra != 255:
                    break
        match += 4
        if not 0 < offset <= len(out) or len(out) + match > size:
            raise FormatError("LZ4 match out of bounds")
        start = len(out) - offset
        if offset >= match:
            out += out[start:start + match]
        else:
            pattern = bytes(out[start:])
            out += (pattern * (match // offset + 1))[:match]
    if len(out) != size:
        raise FormatError(f"LZ4 block decoded to {len(out)} bytes, expected {size}")
    return bytes(out)


def lzma_block(src, size):
    """Decode Unity's LZMA block: 5 property bytes + raw LZMA1, no size field."""
    if not 0 <= size <= MAX_BLOCK or len(src) < 5:
        raise FormatError("invalid LZMA block")
    props = src[0]
    if props >= 9 * 5 * 5:
        raise FormatError("invalid LZMA properties")
    lc, lp, pb = props % 9, props // 9 % 5, props // 45
    dict_size = struct.unpack_from("<I", src, 1)[0]
    try:
        decoder = lzma.LZMADecompressor(lzma.FORMAT_RAW, filters=[{
            "id": lzma.FILTER_LZMA1, "lc": lc, "lp": lp, "pb": pb, "dict_size": max(dict_size, 4096)}])
        out = decoder.decompress(bytes(src[5:]), max_length=size)
        if len(out) == size and not decoder.eof:
            # Unity streams have no end marker; anything more is an error.
            if decoder.decompress(b"", max_length=1):
                raise FormatError("LZMA block longer than declared")
    except lzma.LZMAError as exc:
        raise FormatError(f"corrupt LZMA block: {exc}") from exc
    if len(out) != size:
        raise FormatError(f"LZMA block decoded to {len(out)} bytes, expected {size}")
    return out


def decompress(data, size, method):
    if method == 0:
        if len(data) != size:
            raise FormatError("stored UnityFS block size mismatch")
        return bytes(data)
    if method == 1:
        return lzma_block(data, size)
    if method in (2, 3):
        return lz4_block(data, size)
    raise FormatError(f"unsupported UnityFS compression {method} (LZHAM or unknown)")


@dataclass(frozen=True)
class Block:
    uncompressed_size: int
    compressed_size: int
    flags: int
    file_offset: int
    stream_offset: int


@dataclass(frozen=True)
class Node:
    offset: int
    size: int
    flags: int
    path: str


@dataclass(frozen=True)
class Bundle:
    size: int
    version: int
    player_version: str
    engine_version: str
    flags: int
    header_size: int
    info_offset: int
    info_compressed: int
    info_uncompressed: int
    info_hash: bytes
    data_offset: int
    blocks: tuple
    nodes: tuple

    @property
    def compression(self):
        return self.flags & COMPRESSION_MASK

    @property
    def stream_size(self):
        return sum(b.uncompressed_size for b in self.blocks)


def _cstring(data, pos, limit):
    end = data.find(b"\0", pos, pos + limit + 1)
    if end < 0:
        raise FormatError("unterminated UnityFS header string")
    raw = data[pos:end]
    if not all(32 <= c < 127 for c in raw):
        raise FormatError("non-ASCII UnityFS version string")
    return raw.decode("ascii"), end + 1


def padding_flag_is_alignment(engine_version):
    """0x200 means alignment only from these engine versions onward."""
    m = _VERSION_RE.match(engine_version)
    if not m:
        return False
    v = tuple(map(int, m.groups()))
    return (v >= (2023, 0, 0) or (2022, 1, 1) <= v < (2023, 0, 0)
            or (2021, 3, 2) <= v < (2022, 0, 0) or (2020, 3, 34) <= v < (2021, 0, 0))


def is_unityfs(head):
    return head.startswith(SIGNATURE)


def read_header(stream):
    """Parse header, blocks and node table. Raises FormatError on anything unknown."""
    stream.seek(0, 2)
    size = stream.tell()
    if not 64 <= size <= MAX_FILE:
        raise FormatError("UnityFS file size outside budget")
    stream.seek(0)
    head = stream.read(256)
    if any(head.startswith(sig) for sig in LEGACY_SIGNATURES):
        raise FormatError("legacy UnityWeb/UnityRaw bundles are not supported")
    if not head.startswith(SIGNATURE):
        raise FormatError("not a UnityFS bundle")
    pos = len(SIGNATURE)
    version = struct.unpack_from(">I", head, pos)[0]
    pos += 4
    if version not in VERSIONS:
        raise FormatError(f"unsupported UnityFS format version {version}")
    player, pos = _cstring(head, pos, 32)
    engine, pos = _cstring(head, pos, 64)
    if pos + 20 > len(head):
        raise FormatError("truncated UnityFS header")
    declared, info_c, info_u, flags = struct.unpack_from(">qIII", head, pos)
    pos += 20
    if declared != size:
        raise FormatError(f"UnityFS declared size {declared} differs from file size {size}")
    if flags & ~KNOWN_FLAGS:
        raise FormatError(f"unknown UnityFS flags {flags:#x} (possibly encrypted)")
    if not flags & FLAG_COMBINED:
        raise FormatError("UnityFS without combined blocks/directory info is not supported")
    if flags & FLAG_PADDING_AT_START and not padding_flag_is_alignment(engine):
        raise FormatError(f"UnityFS flag 0x200 on engine {engine} may denote encryption; refusing")
    if flags & COMPRESSION_MASK not in COMPRESSION_NAMES:
        raise FormatError(f"unsupported UnityFS blocks-info compression {flags & COMPRESSION_MASK}")
    if not 0 < info_c <= MAX_INFO or not 0 < info_u <= MAX_INFO:
        raise FormatError("UnityFS blocks info size outside budget")
    header_size = pos
    if version >= 7:
        pos += -pos % 16
    if flags & FLAG_INFO_AT_END:
        info_offset = size - info_c
        data_offset = pos
        data_limit = info_offset
    else:
        info_offset = pos
        data_offset = pos + info_c
        data_limit = size
    if flags & FLAG_PADDING_AT_START:
        data_offset += -data_offset % 16
    if not header_size <= info_offset or info_offset + info_c > size or data_offset > data_limit:
        raise FormatError("UnityFS blocks info outside file")
    stream.seek(header_size)
    gap = stream.read(min(info_offset, data_offset) - header_size)
    if any(gap):
        raise FormatError("nonzero UnityFS header padding")
    stream.seek(info_offset)
    packed = stream.read(info_c)
    if len(packed) != info_c:
        raise FormatError("truncated UnityFS blocks info")
    info = decompress(packed, info_u, flags & COMPRESSION_MASK)
    if not flags & FLAG_INFO_AT_END and data_offset > info_offset + info_c:
        stream.seek(info_offset + info_c)
        if any(stream.read(data_offset - info_offset - info_c)):
            raise FormatError("nonzero UnityFS data padding")
    p = 16
    info_hash = info[:16]
    if len(info) < 20:
        raise FormatError("truncated UnityFS blocks info")
    count = struct.unpack_from(">I", info, p)[0]
    p += 4
    if count > MAX_BLOCKS or p + count * 10 + 4 > len(info):
        raise FormatError("UnityFS block count outside budget")
    blocks, file_offset, stream_offset = [], data_offset, 0
    for _ in range(count):
        usize, csize, bflags = struct.unpack_from(">IIH", info, p)
        p += 10
        method = bflags & COMPRESSION_MASK
        if bflags & ~(COMPRESSION_MASK | BLOCK_STREAMED) or method not in COMPRESSION_NAMES:
            raise FormatError(f"unsupported UnityFS block flags {bflags:#x}")
        if usize > MAX_BLOCK or (method == 0 and usize != csize):
            raise FormatError("invalid UnityFS block size")
        blocks.append(Block(usize, csize, bflags, file_offset, stream_offset))
        file_offset += csize
        stream_offset += usize
    if file_offset != data_limit:
        raise FormatError(f"UnityFS block data ends at {file_offset}, expected {data_limit}")
    node_count = struct.unpack_from(">I", info, p)[0]
    p += 4
    if node_count > MAX_NODES:
        raise FormatError("UnityFS node count outside budget")
    nodes, names = [], set()
    for _ in range(node_count):
        if p + 20 > len(info):
            raise FormatError("truncated UnityFS node table")
        offset, nsize, nflags = struct.unpack_from(">qqI", info, p)
        p += 20
        end = info.find(b"\0", p, p + 1025)
        if end <= p:
            raise FormatError("invalid UnityFS node path")
        try:
            path = info[p:end].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise FormatError("UnityFS node path is not UTF-8") from exc
        p = end + 1
        if offset < 0 or nsize < 0 or offset + nsize > stream_offset:
            raise FormatError(f"UnityFS node {path!r} outside data stream")
        if nflags & ~NODE_FLAGS:
            raise FormatError(f"unknown UnityFS node flags {nflags:#x}")
        if path in names:
            raise FormatError(f"duplicate UnityFS node {path!r}")
        names.add(path)
        nodes.append(Node(offset, nsize, nflags, path))
    if p != len(info):
        raise FormatError("unparsed UnityFS blocks info tail")
    return Bundle(size, version, player, engine, flags, header_size, info_offset, info_c, info_u,
                  info_hash, data_offset, tuple(blocks), tuple(nodes))


class BundleReader:
    """Random access over the decompressed stream with a decompression budget."""

    def __init__(self, stream, bundle=None, *, budget=MAX_READ):
        self.stream = stream
        self.bundle = bundle or read_header(stream)
        self.budget = budget
        self.used = 0
        self._cache = {}

    def _block(self, index):
        if index in self._cache:
            return self._cache[index]
        block = self.bundle.blocks[index]
        if self.used + block.uncompressed_size > self.budget:
            raise FormatError("UnityFS decompression budget exceeded")
        self.used += block.uncompressed_size
        self.stream.seek(block.file_offset)
        packed = self.stream.read(block.compressed_size)
        if len(packed) != block.compressed_size:
            raise FormatError("truncated UnityFS block")
        data = decompress(packed, block.uncompressed_size, block.flags & COMPRESSION_MASK)
        if len(self._cache) >= 4:
            self._cache.pop(next(iter(self._cache)))
        self._cache[index] = data
        return data

    def read(self, offset, size):
        if offset < 0 or size < 0 or offset + size > self.bundle.stream_size:
            raise FormatError("UnityFS read outside data stream")
        if size > self.budget:
            raise FormatError("UnityFS read exceeds budget")
        out = bytearray()
        for i, block in enumerate(self.bundle.blocks):
            start, end = block.stream_offset, block.stream_offset + block.uncompressed_size
            if end <= offset or start >= offset + size:
                continue
            lo, hi = max(offset, start) - start, min(offset + size, end) - start
            if block.flags & COMPRESSION_MASK == 0:
                # Stored blocks are read in place instead of whole.
                if self.used + hi - lo > self.budget:
                    raise FormatError("UnityFS read budget exceeded")
                self.used += hi - lo
                self.stream.seek(block.file_offset + lo)
                piece = self.stream.read(hi - lo)
                if len(piece) != hi - lo:
                    raise FormatError("truncated UnityFS block")
                out += piece
            else:
                out += self._block(i)[lo:hi]
        if len(out) != size:
            raise FormatError("UnityFS read incomplete")
        return bytes(out)

    def node(self, node, *, prefix=None):
        size = node.size if prefix is None else min(node.size, prefix)
        return self.read(node.offset, size)


def read_bundle(data, *, budget=MAX_REBUILD):
    """Parse an in-memory bundle and return ``(bundle, {path: bytes})``."""
    stream = io.BytesIO(data)
    bundle = read_header(stream)
    if bundle.stream_size > budget:
        raise FormatError("UnityFS uncompressed size exceeds rebuild budget")
    reader = BundleReader(stream, bundle, budget=budget)
    whole = reader.read(0, bundle.stream_size)
    return bundle, whole, {n.path: whole[n.offset:n.offset + n.size] for n in bundle.nodes}


def _layout(bundle, whole, replacements):
    """Recompose the stream: nodes in offset order, original gaps kept verbatim."""
    order = sorted(bundle.nodes, key=lambda n: (n.offset, n.size))
    out, cursor, offsets = bytearray(), 0, {}
    for node in order:
        if node.offset < cursor:
            raise FormatError("overlapping UnityFS nodes cannot be rebuilt")
        out += whole[cursor:node.offset]
        offsets[node.path] = len(out)
        out += replacements.get(node.path, whole[node.offset:node.offset + node.size])
        cursor = node.offset + node.size
    out += whole[cursor:]
    return bytes(out), offsets


def build(bundle, stream_data, offsets, sizes):
    """Write an uncompressed UnityFS bundle around a prepared data stream.

    Like Unity's own uncompressed bundles, the data is one stored block with
    the streamed flag; the blocks info is stored too.
    """
    if len(stream_data) > 0xFFFFFFFF:
        raise FormatError("stored UnityFS block exceeds 4 GiB")
    blocks = struct.pack(">IIIH", 1, len(stream_data), len(stream_data), BLOCK_STREAMED)
    nodes = bytearray(struct.pack(">I", len(bundle.nodes)))
    for node in bundle.nodes:
        nodes += struct.pack(">qqI", offsets[node.path], sizes[node.path], node.flags)
        nodes += node.path.encode("utf-8") + b"\0"
    info = bundle.info_hash + blocks + bytes(nodes)
    flags = bundle.flags & (FLAG_COMBINED | FLAG_INFO_AT_END | FLAG_PADDING_AT_START)
    header = bytearray(SIGNATURE + struct.pack(">I", bundle.version)
                       + bundle.player_version.encode("ascii") + b"\0"
                       + bundle.engine_version.encode("ascii") + b"\0")
    size_at = len(header)
    header += struct.pack(">qIII", 0, len(info), len(info), flags)
    if bundle.version >= 7:
        header += bytes(-len(header) % 16)
    out = bytearray(header)
    if not flags & FLAG_INFO_AT_END:
        out += info
    if flags & FLAG_PADDING_AT_START:
        out += bytes(-len(out) % 16)
    out += stream_data
    if flags & FLAG_INFO_AT_END:
        out += info
    struct.pack_into(">q", out, size_at, len(out))
    return bytes(out)


def rebuild(data, replacements, *, budget=MAX_REBUILD):
    """Replace node contents by path; returns an uncompressed, verified bundle."""
    if len(data) > MAX_FILE:
        raise FormatError("UnityFS input exceeds budget")
    bundle, whole, contents = read_bundle(data, budget=budget)
    unknown = set(replacements) - set(contents)
    if unknown:
        raise FormatError(f"unknown UnityFS node(s): {sorted(unknown)}")
    for path, payload in replacements.items():
        if not isinstance(payload, bytes):
            raise FormatError(f"UnityFS replacement for {path!r} is not bytes")
    if any(bundle.info_hash) and any(replacements[p] != contents[p] for p in replacements):
        raise FormatError("UnityFS blocks info carries a nonzero data hash; changed content cannot be re-hashed")
    stream_data, offsets = _layout(bundle, whole, replacements)
    if len(stream_data) > budget:
        raise FormatError("rebuilt UnityFS stream exceeds budget")
    sizes = {n.path: len(replacements.get(n.path, contents[n.path])) for n in bundle.nodes}
    result = build(bundle, stream_data, offsets, sizes)
    verify(result, bundle, {p: replacements.get(p, contents[p]) for p in contents}, budget=budget)
    return result


def verify(result, original, expected, *, budget=MAX_REBUILD):
    """Reread ``result`` and compare identity, order, flags and every node."""
    after, _, nodes = read_bundle(result, budget=budget)
    if ((after.version, after.player_version, after.engine_version) !=
            (original.version, original.player_version, original.engine_version)):
        raise FormatError("UnityFS header identity changed on rebuild")
    if [(n.path, n.flags) for n in after.nodes] != [(n.path, n.flags) for n in original.nodes]:
        raise FormatError("UnityFS node order/paths/flags changed on rebuild")
    for path, payload in expected.items():
        if nodes[path] != payload:
            raise FormatError(f"UnityFS node {path!r} differs after rebuild")
    return after


def describe(bundle):
    return {"format": "UnityFS", "format_version": bundle.version, "player_version": bundle.player_version,
            "engine_version": bundle.engine_version, "flags": f"{bundle.flags:#x}",
            "info_compression": COMPRESSION_NAMES[bundle.compression],
            "info_at_end": bool(bundle.flags & FLAG_INFO_AT_END),
            "block_count": len(bundle.blocks),
            "block_compression": sorted({COMPRESSION_NAMES[b.flags & COMPRESSION_MASK] for b in bundle.blocks}),
            "uncompressed_size": bundle.stream_size,
            "nodes": [{"path": n.path, "offset": n.offset, "size": n.size, "flags": n.flags} for n in bundle.nodes]}
