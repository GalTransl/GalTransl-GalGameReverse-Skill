# SPDX-License-Identifier: GPL-3.0-only
# Adapted from SExtractor tools/SFA/fga_pack.py and src/reg.yaml:SFA_AOS
# Source commit: 8d8d976fd04ae54e7c677705af937273d04a376a
# Upstream attribution: Steins;Gate; SExtractor contributors.
"""SFA member Huffman codec and a conservative AOS text-dialect recognizer."""
# Layer split: archives; format algorithms and original notices retained.
# Companion module: python/engines/sfa.py
import heapq
import struct
from collections import Counter


def compress_member(data):
    """u32 decoded size + MSB-first pre-order Huffman tree + symbol bitstream."""
    if not data:
        return b""  # the upstream empty-member convention
    heap, serial = [], 0
    for symbol, count in sorted(Counter(data).items()):
        heapq.heappush(heap, (count, serial, symbol))
        serial += 1
    while len(heap) > 1:
        a, _, left = heapq.heappop(heap)
        b, _, right = heapq.heappop(heap)
        heapq.heappush(heap, (a + b, serial, (left, right)))
        serial += 1
    root = heap[0][2]
    out = bytearray(struct.pack("<I", len(data)))
    pending, bits = 0, 0

    def emit(value, width):
        nonlocal pending, bits
        for shift in range(width - 1, -1, -1):
            pending = (pending << 1) | ((value >> shift) & 1)
            bits += 1
            if bits == 8:
                out.append(pending)
                pending = bits = 0

    codes = {}

    def tree(node, code=0, width=0):
        if isinstance(node, int):
            emit(0, 1)
            emit(node, 8)
            codes[node] = (code, width or 1)
        else:
            emit(1, 1)
            tree(node[0], code << 1, width + 1)
            tree(node[1], (code << 1) | 1, width + 1)

    tree(root)
    for symbol in data:
        emit(*codes[symbol])
    if bits:
        out.append(pending << (8 - bits))
    return bytes(out)


def decompress_member(data, *, max_output=64 * 1024 * 1024):
    if not data:
        return b""
    if len(data) < 6:
        raise ValueError("truncated Huffman member")
    size = struct.unpack_from("<I", data)[0]
    if not 0 < size <= max_output:
        raise ValueError("Huffman output exceeds budget")
    bitpos, nodes = 32, 0

    def read(width):
        nonlocal bitpos
        if bitpos + width > len(data) * 8:
            raise ValueError("truncated Huffman bitstream")
        value = 0
        for _ in range(width):
            value = (value << 1) | ((data[bitpos // 8] >> (7 - bitpos % 8)) & 1)
            bitpos += 1
        return value

    def tree(depth=0):
        nonlocal nodes
        nodes += 1
        if depth > 255 or nodes > 511:
            raise ValueError("invalid Huffman tree bounds")
        if read(1) == 0:
            return read(8)
        return tree(depth + 1), tree(depth + 1)

    root = tree()
    out = bytearray()
    for _ in range(size):
        node = root
        while not isinstance(node, int):
            node = node[read(1)]
        out.append(node)
    return bytes(out)
