"""Strict, bounded DSC FORMAT 1.00 decompression; no script interpretation.

Adapted from msg-tool src/scripts/bgi/archive/dsc.rs, DscDecoder::{new,
unpack, update_key, create_huffman_tree, huffman_decompress}, at commit
f72716cee88554d40c1cdface2812493b14ca653, GPL-3.0-or-later.
Attribution: lifegpc/msg-tool contributors; that file has no separate
copyright notice. This adaptation is free software: you can redistribute it
and/or modify it under the GNU General Public License as published by the
Free Software Foundation, either version 3, or (at your option) any later
version. It is distributed WITHOUT ANY WARRANTY; without even the implied
warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
../../LICENSE and ../../provenance/licenses/GPL-3.0.txt, or
https://www.gnu.org/licenses/.

Also ported/checked against GARbro-Mod ArcFormats/Ethornell/ArcBGI.cs,
BgiDecoderBase.UpdateKey, DscDecoder constructor/Unpack/CreateHuffmanTree/
HuffmanDecompress, at bc26d991ef5cdc0e1ecb32122ee9a48c3375750c (MIT).
Copyright (C) 2014-2015 by morkt

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

Unlike the references, malformed trees, truncated matches and output size
mismatches are fatal, not warnings/partial success. No runtime dependencies
on either project. All offsets in errors are local to the DSC member.

`encode` is the matching DSC writer. It is bounded, deterministic and
self-verifying: every produced member is decoded again and compared before it
is returned. Its LZSS/greedy parser and tree builder are original Python, not a
transcription of the upstream encoder, so encoder and decoder are checked
against each other rather than against one shared assumption.
"""
import heapq
import struct

from .bgi import BgiArchiveError, _limit


MAGIC = b"DSC FORMAT 1.00\0"
MAX_INPUT_SIZE = 64 << 20
_BODY = 0x220
# A 12-bit distance field stores distance - 2, so one-byte distances are not
# representable and matches must span at least two bytes.
MIN_DISTANCE = 2
MAX_DISTANCE = 4097
MAX_MATCH = 257
_MAX_CODE_DEPTH = 24
_UNIFORM_DEPTH = 9  # 2**9 == 512 symbols: always a complete code.
DEFAULT_SEED = 0x12345678
_CHAIN_LIMIT = 256


def _fail(message, code, offset, stage="decode"):
    raise BgiArchiveError(message, code=code, stage=stage, offset=offset)


def _key_bytes(prefix, key, count):
    """The uint32 keystream that masks the 512 code lengths.

    Shared by the reader and the writer so the two cannot drift apart.
    """
    # Preserve uint32 overflow, including the +1 carry into the high word.
    magic = int.from_bytes(prefix, "little") << 16
    for _ in range(count):
        v0 = 20021 * (key & 0xffff)
        v1 = ((magic | (key >> 16)) * 20021 + key * 346) & 0xffffffff
        v1 = (v1 + (v0 >> 16)) & 0xffff
        key = ((v1 << 16) + (v0 & 0xffff) + 1) & 0xffffffff
        yield v1 & 255


def _depths(data, key):
    return [(source - mask) & 255  # NOT XOR
            for source, mask in zip(data[0x20:_BODY], _key_bytes(data[:2], key, 512))]


def _tree(depths, empty):
    codes = sorted((depth, symbol) for symbol, depth in enumerate(depths) if depth)
    if not codes:
        if empty:
            return [], 0
        _fail("empty DSC Huffman tree", "invalid_tree", 0x20)
    maximum = codes[-1][0]  # A depth is a byte: at most 255, never recursion.
    counts = [0] * (maximum + 1)
    for depth, _ in codes:
        counts[depth] += 1
    slots = 1
    for depth in range(1, maximum + 1):
        slots = slots * 2 - counts[depth]
        if slots < 0:
            _fail("oversubscribed DSC Huffman tree", "invalid_tree", 0x20)
    # Upstream's single-symbol encoder emits one depth-1 leaf. Its unused
    # branch remains invalid. Other undersubscribed trees are not accepted.
    if slots and not (len(codes) == 1 and maximum == 1):
        _fail("incomplete DSC Huffman tree", "invalid_tree", 0x20)

    # Canonical codes match the references' breadth-first tree construction.
    # Each node is [zero-child, one-child, symbol], -1 denotes absent.
    nodes = [[-1, -1, -1]]
    code, last_depth = 0, 0
    for depth, symbol in codes:
        code <<= depth - last_depth
        node = 0
        for shift in range(depth - 1, -1, -1):
            bit = (code >> shift) & 1
            if nodes[node][bit] == -1:
                if len(nodes) >= 1023:
                    _fail("DSC Huffman node limit", "invalid_tree", 0x20)
                nodes[node][bit] = len(nodes)
                nodes.append([-1, -1, -1])
            node = nodes[node][bit]
        nodes[node][2] = symbol
        code += 1
        last_depth = depth
    return nodes, maximum


class _Bits:
    def __init__(self, data, work_limit):
        self.data = data
        self.position = _BODY * 8
        self.work_limit = work_limit

    def take(self, width):
        start = self.position
        end = start + width
        if end > len(self.data) * 8:
            _fail("truncated DSC bitstream", "truncated", start // 8)
        if end - _BODY * 8 > self.work_limit:
            _fail("DSC bit-work budget", "decoded_budget", start // 8)
        value = 0
        # At most 12 bits per call; no read/prefetch past the member.
        while width:
            byte, used = divmod(self.position, 8)
            count = min(width, 8 - used)
            value = (value << count) | ((self.data[byte] >> (8 - used - count)) & ((1 << count) - 1))
            self.position += count
            width -= count
        return value

    def finish(self):
        remaining = len(self.data) * 8 - self.position
        if remaining >= 8:
            _fail("trailing DSC bytes", "trailing_data", self.position // 8)
        if remaining and self.data[-1] & ((1 << remaining) - 1):
            _fail("nonzero DSC tail padding", "trailing_data", self.position // 8)


def decode(data: bytes, *, max_output_size: int = 64 << 20,
           max_symbols: int = 64 << 20) -> bytes:
    """Decode exactly one DSC member, or raise BgiArchiveError.

    Input is capped at 64 MiB. max_symbols caps the advertised symbol count
    and bounds bit work to 32 * max_symbols (including 12-bit distances).
    Tree work is bounded by 512 byte-sized lengths and 1023 nodes; output by
    max_output_size. Only zero bits up to the next byte boundary may follow the
    declared symbols. Empty output and a single depth-1 symbol are supported.

    Keep max_symbols >= max_output_size. Every symbol emits at least one byte
    and this function already enforces symbol_count <= output_size, so a smaller
    symbol cap cannot protect anything - it can only reject a member that the
    output cap would have accepted, which callers then tend to report as
    "skipped / not processed" instead of classifying it. Raise it explicitly to
    permit unusually deep codes; lowering it below max_output_size is a mistake.
    """
    _limit(max_output_size, "max_output_size", "decode")
    _limit(max_symbols, "max_symbols", "decode")
    if not isinstance(data, bytes):
        _fail("DSC input must be bytes", "input_type", None)
    if len(data) > MAX_INPUT_SIZE:
        _fail("DSC stored input budget", "stored_budget", 0)
    if not data.startswith(MAGIC):
        code = "truncated" if MAGIC.startswith(data) else "unsupported_codec"
        _fail("unknown/truncated DSC signature", code, 0)
    if len(data) < _BODY:
        _fail("truncated DSC header/code lengths", "truncated", len(data))
    key, output_size, symbol_count = struct.unpack_from("<III", data, 0x10)
    if output_size > max_output_size:
        _fail("DSC decoded size budget", "decoded_budget", 0x14)
    if symbol_count > max_symbols:
        _fail("DSC symbol budget", "decoded_budget", 0x18)
    if not symbol_count <= output_size <= symbol_count * 257:
        _fail("impossible DSC output/symbol lengths", "length_mismatch", 0x14)
    nodes, maximum = _tree(_depths(data, key), not output_size and not symbol_count)
    # Bound input without scanning or copying an arbitrarily long trailer.
    if len(data) - _BODY > (symbol_count * (maximum + 12) + 7) // 8:
        _fail("DSC input longer than declared symbols permit", "trailing_data", _BODY)
    bits = _Bits(data, max_symbols * 32)
    output = bytearray()
    for _ in range(symbol_count):
        node = 0
        while nodes[node][2] < 0:
            node = nodes[node][bits.take(1)]
            if node < 0:
                _fail("unused DSC Huffman branch", "invalid_tree", (bits.position - 1) // 8)
        symbol = nodes[node][2]
        if symbol < 256:
            if len(output) >= output_size:
                _fail("DSC literal exceeds output length", "length_mismatch", bits.position // 8)
            output.append(symbol)
        else:
            length = (symbol & 255) + 2
            distance = bits.take(12) + 2
            if distance > len(output):
                _fail("DSC match before output start", "invalid_backreference", bits.position // 8)
            if length > output_size - len(output):
                _fail("DSC match exceeds output length", "length_mismatch", bits.position // 8)
            # Small (2..257 byte) sequential copy deliberately permits overlap.
            for _ in range(length):
                output.append(output[-distance])
    if len(output) != output_size:
        _fail("DSC exact output length mismatch", "length_mismatch", 0x14)
    bits.finish()
    return bytes(output)


decode_dsc = decode


class _BitWriter:
    """MSB-first bit writer matching the reader's bit order."""

    __slots__ = ("output", "current", "used", "bits")

    def __init__(self):
        self.output = bytearray()
        self.current = 0
        self.used = 0
        self.bits = 0

    def put(self, value, width):
        for shift in range(width - 1, -1, -1):
            self.current = (self.current << 1) | ((value >> shift) & 1)
            self.used += 1
            self.bits += 1
            if self.used == 8:
                self.output.append(self.current)
                self.current = 0
                self.used = 0

    def finish(self):
        if self.used:
            # The reader accepts only zero bits up to the next byte boundary.
            self.output.append(self.current << (8 - self.used))
            self.current = 0
            self.used = 0
        return bytes(self.output)


def _lzss(data):
    """Greedy LZSS over the format's own 512-symbol space.

    Returns (symbol, distance_or_None) pairs. Candidates closer than
    MIN_DISTANCE or further than MAX_DISTANCE are skipped rather than encoded,
    because those distances have no representation in the bitstream.
    """
    operations = []
    head = [-1] * 65536
    previous = [-1] * len(data)
    position = 0
    size = len(data)

    def insert(index):
        if index + 1 < size:
            key = (data[index] << 8) | data[index + 1]
            previous[index] = head[key]
            head[key] = index

    while position < size:
        best_length, best_distance = 0, 0
        if position + 1 < size:
            key = (data[position] << 8) | data[position + 1]
            candidate = head[key]
            floor = max(0, position - MAX_DISTANCE)
            chain = _CHAIN_LIMIT
            maximum = min(MAX_MATCH, size - position)
            while candidate >= floor and chain > 0 and best_length < maximum:
                distance = position - candidate
                if distance >= MIN_DISTANCE:
                    length = 0
                    while (length < maximum
                           and data[candidate + length] == data[position + length]):
                        length += 1
                    if length > best_length:
                        best_length, best_distance = length, distance
                candidate = previous[candidate]
                chain -= 1
        if best_length >= 2:
            operations.append((256 + best_length - 2, best_distance))
            for offset in range(best_length):
                insert(position + offset)
            position += best_length
        else:
            operations.append((data[position], None))
            insert(position)
            position += 1
    return operations


def _tree_depths(frequencies):
    """Huffman code lengths, with a complete fallback when depth would grow."""
    used = [symbol for symbol, count in enumerate(frequencies) if count]
    if not used:
        return [0] * 512
    if len(used) == 1:
        depths = [0] * 512
        depths[used[0]] = 1  # The reader supports exactly this single-symbol case.
        return depths
    heap = [(frequencies[symbol], [symbol]) for symbol in used]
    heapq.heapify(heap)
    depths = [0] * 512
    while len(heap) > 1:
        left = heapq.heappop(heap)
        right = heapq.heappop(heap)
        for symbol in left[1]:
            depths[symbol] += 1
        for symbol in right[1]:
            depths[symbol] += 1
        heapq.heappush(heap, (left[0] + right[0], left[1] + right[1]))
    if max(depths) > _MAX_CODE_DEPTH:
        # A length byte and the reader's bit budget both require a shallow,
        # complete code; 512 depth-9 codes always exist.
        return [_UNIFORM_DEPTH] * 512
    return depths


def _canonical_codes(depths):
    """Same canonical assignment the reader reconstructs from the lengths."""
    codes, code, last = {}, 0, 0
    for depth, symbol in sorted((depth, symbol) for symbol, depth in enumerate(depths) if depth):
        code <<= depth - last
        codes[symbol] = (code, depth)
        code += 1
        last = depth
    return codes


def encode(data: bytes, *, seed: int = DEFAULT_SEED, max_output_size: int = 64 << 20,
           max_symbols: int = 64 << 20, verify: bool = True) -> bytes:
    """Compress `data` into one self-contained DSC FORMAT 1.00 member.

    Deterministic for a given seed and input. Distance 1 is never emitted
    because the format cannot express it. With verify=True the result is decoded
    again and compared, so a writer bug cannot be reported as success.

    max_symbols must stay >= max_output_size for the same reason as in decode():
    the encoded symbol count can never exceed the output length it describes, so
    a lower cap only rejects inputs the output cap already allows.
    """
    _limit(max_output_size, "max_output_size", "encode")
    _limit(max_symbols, "max_symbols", "encode")
    if not isinstance(data, bytes):
        _fail("DSC input must be bytes", "input_type", None, "encode")
    if len(data) > max_output_size:
        _fail("DSC decoded size budget", "decoded_budget", 0, "encode")
    if type(seed) is not int or not 0 <= seed <= 0xffffffff:
        _fail("DSC seed must be a uint32", "invalid_seed", None, "encode")
    operations = _lzss(data)
    if len(operations) > max_symbols:
        _fail("DSC symbol budget", "decoded_budget", 0, "encode")
    frequencies = [0] * 512
    for symbol, _ in operations:
        frequencies[symbol] += 1
    depths = _tree_depths(frequencies)
    codes = _canonical_codes(depths)
    writer = _BitWriter()
    for symbol, distance in operations:
        code, width = codes[symbol]
        writer.put(code, width)
        if distance is not None:
            writer.put(distance - MIN_DISTANCE, 12)
    if writer.bits > max(len(operations), 1) * 32:
        # The reader's own bit-work budget would refuse this member.
        _fail("DSC bit-work budget", "decoded_budget", 0, "encode")
    body = writer.finish()
    table = bytes((depth + mask) & 255
                  for depth, mask in zip(depths, _key_bytes(b"DS", seed, 512)))
    member = (MAGIC + struct.pack("<4I", seed, len(data), len(operations), 0)
              + table + body)
    if verify:
        restored = decode(member, max_output_size=max(max_output_size, len(data)),
                          max_symbols=max(max_symbols, len(operations), 1))
        if restored != data:
            _fail("DSC encoder round-trip mismatch", "encode_mismatch", 0, "encode")
    return member


encode_dsc = encode
