# SPDX-License-Identifier: GPL-3.0-only
# Adapted from SExtractor tools/SakanaGL/sxstorage_pack.py (itself a GARbro port).
# Source commit: 8d8d976fd04ae54e7c677705af937273d04a376a
# Upstream attribution: Steins;Gate; SExtractor contributors; GARbro algorithm authors.
"""SakanaGL cipher and already-decoded SX index parser. No Zstandard dependency."""
import struct


def crypt_data(data, *, key_lo, key_hi):
    """Symmetric u32 stream transform; final 1..3 bytes deliberately remain clear."""
    if not 0 <= key_lo <= 0xFFFFFFFF or not 0 <= key_hi <= 0xFFFFFFFF:
        raise ValueError("keys must be unsigned 32-bit integers")
    mask = 0xFFFFFFFF
    lo, hi = key_lo ^ 0x159A55E5, key_hi ^ 0x075BCD15
    v1 = (hi ^ (hi << 11) ^ (((hi ^ (hi << 11)) & mask) >> 8) ^ 0x549139A) & mask
    v2 = (v1 ^ lo ^ (lo << 11) ^ (((lo ^ (lo << 11) ^ (v1 >> 11)) & mask) >> 8)) & mask
    v3 = (v2 ^ (v2 >> 19) ^ 0x8E415C26) & mask
    v4 = (v3 ^ (v3 >> 19) ^ 0x4D9D5BB8) & mask
    out = bytearray(data)
    for pos in range(0, len(data) - 3, 4):
        t1 = (v4 ^ v1 ^ (v1 << 11) ^ (((v1 ^ (v1 << 11) ^ (v4 >> 11)) & mask) >> 8)) & mask
        t2 = (v2 ^ (v2 << 11)) & mask
        v2 = v4
        v4 = (t1 ^ t2 ^ (((t2 ^ (t1 >> 11)) & mask) >> 8)) & mask
        word = struct.unpack_from("<I", data, pos)[0]
        struct.pack_into("<I", out, pos, word ^ (((t1 >> 4) ^ (v4 << 12)) & mask))
        v1, v3 = v3, t1
    return bytes(out)


def member_keys(*, offset, stored_size):
    if offset < 0 or offset % 16 or not 0 <= stored_size <= 0xFFFFFFFF:
        raise ValueError("SX member must have a 16-byte-aligned offset")
    return ((offset >> 4) ^ (stored_size << 16) ^ 0x2E76034B) & 0xFFFFFFFF, ((stored_size >> 16) ^ 0x2E6) & 0xFFFFFFFF


def parse_decoded_index(data, *, max_entries=100_000):
    """Parse ONLY the decrypted/decompressed SX index, with iterative tree bounds.

    Returns names, entries, raw archive metadata, and tree edges. File paths are
    metadata only; nothing is read or written. SSXXDEFL/zstd decoding is absent.
    """
    if data[:8] != b"\x00\x00\x00\x01\x00\x00\x00\x00":
        raise ValueError("unsupported decoded SX index version")
    pos = 8

    def take(size):
        nonlocal pos
        if size < 0 or pos + size > len(data):
            raise ValueError("truncated SX index")
        raw = data[pos:pos + size]
        pos += size
        return raw

    def num(fmt):
        return struct.unpack(fmt, take(struct.calcsize(fmt)))[0]

    count = num(">i")
    if not 0 <= count <= max_entries:
        raise ValueError("invalid SX name count")
    names = [take(num(">B")).decode("utf-8") for _ in range(count)]
    count = num(">i")
    if not 0 <= count <= max_entries:
        raise ValueError("invalid SX entry count")
    entries = []
    for _ in range(count):
        arc, flags, offset16, size = struct.unpack(">HHII", take(12))
        entries.append({"archive": arc, "flags": flags, "offset": offset16 * 16, "size": size,
                        "packed": bool(flags & 3), "encrypted": not bool(flags & 0x10)})
    arc_count = num(">H")
    archives = [take(40) for _ in range(arc_count)]
    if any(e["archive"] >= arc_count for e in entries):
        raise ValueError("invalid SX archive selector")
    unknown = [take(24) for _ in range(num(">H"))]
    pending, edges, visited = [None], [], set()
    while pending:
        parent = pending.pop()
        children, name_id, file_id = struct.unpack(">Hii", take(10))
        if not 0 <= name_id < len(names) or file_id < -1 or file_id >= len(entries):
            raise ValueError("invalid SX tree reference")
        node = len(edges)
        if node >= max_entries:
            raise ValueError("SX tree exceeds node budget")
        edges.append((parent, name_id, file_id))
        if file_id == -1:
            if len(pending) + children > max_entries:
                raise ValueError("SX tree exceeds traversal budget")
            pending.extend([node] * children)
        else:
            if children or file_id in visited:
                raise ValueError("unsupported duplicate/file-with-children SX node")
            visited.add(file_id)
    if pos != len(data):
        raise ValueError("unparsed SX index tail")
    return {"names": names, "entries": entries, "archives": archives, "unknown": unknown, "tree": edges}
