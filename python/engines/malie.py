# Provenance group: tools-a; sources (repository-relative):
#   SExtractor/tools/Malie/light社08年UTF16新版/malie_fmt.py
#   SExtractor/tools/Malie/light社08年UTF16新版/malie_selftest.py
#   SExtractor/tools/Malie/light社12年data5/malie_fmt.py
#   SExtractor/tools/Malie/light社12年data5/malie_selftest.py
# Symbols: ExecImage, Reader, OPERAND_WIDTHS, message_raw, main
# Validation: tests/test_engines_tools_a.py, synthetic fixtures only.
# Rewritten standard-library bytes API; scope: versioned-script-pool-rebuild.
# SPDX-License-Identifier: GPL-3.0-only
# SExtractor tools/Malie/light社08年UTF16新版/{malie_fmt,malie_selftest}.py and
# tools/Malie/light社12年data5/{malie_fmt,malie_selftest}.py: ExecImage,
# OPERAND_WIDTHS, message_raw. Commit 8d8d976fd04ae54e7c677705af937273d04a376a.
# Rewrite: explicit version, bounded parsing, immutable non-message prefix.
# No game keys, LIBP/Camellia, executable IO, or automatic effect deletion.
"""Decrypted Malie EXEC v0/v1/v2 structural reference; no whole-VM assembler."""
import struct

FORMATS = {"utf16-2008-v0", "data5-v1", "data5-v2"}


def instruction_edges(code: bytes, fmt: str) -> set[int]:
    if fmt not in FORMATS:
        raise ValueError("explicit Malie format required")
    widths = {0: 4, 1: 4, 2: 4, 3: 5, 4: 2, 8: 4, 9: 1, 10: 2, 12: 4,
              13: 4, 17: 1, 45: 4, 49: 4, 51: 1}
    pos, edges = 0, {len(code)}
    while pos < len(code):
        edges.add(pos)
        op = code[pos]
        if op > 51 and fmt == "utf16-2008-v0":
            raise ValueError("unknown opcode in 2008 format")
        pos += 1 + widths.get(op, 0)
        if pos > len(code):
            raise ValueError("truncated instruction")
    return edges


def parse(data: bytes, *, fmt: str) -> dict:
    if fmt not in FORMATS:
        raise ValueError("explicit Malie format required")
    pos = 0

    def take(n):
        nonlocal pos
        if n < 0 or pos + n > len(data):
            raise ValueError("truncated EXEC")
        raw = data[pos:pos + n]
        pos += n
        return raw

    def u32():
        return struct.unpack("<I", take(4))[0]

    def string():
        n = u32() & 0x7FFFFFFF
        if n % 2:
            raise ValueError("odd UTF16 name size")
        return take(n)

    def ident():
        string()
        while u32():
            take(4)
        take(16)

    if fmt == "data5-v1":
        if take(2) != b"\0\0":
            raise ValueError("unsupported v1 header")
        while pos + 4 <= len(data) and struct.unpack_from("<I", data, pos)[0] & 0x80000000:
            ident()
    else:
        for _ in range(u32()):
            ident()
    take(4)  # ident tail
    for _ in range(u32()):
        string()
        take(12)
    labels = []
    for _ in range(u32()):
        string()
        labels.append(u32())
    seg3 = take(u32())
    code = take(u32())
    prefix = data[:pos]
    if fmt == "utf16-2008-v0":
        pool = take(u32())
        count = u32()
        offsets = [u32() for _ in range(count)]
        pairs = [(off, (offsets[i + 1] if i + 1 < count else len(pool)) - off)
                 for i, off in enumerate(offsets)]
    else:
        pairs = [(u32(), u32()) for _ in range(u32())]
        pool = take(u32())
    tail = data[pos:]
    if tail and fmt != "data5-v1":
        raise ValueError("unexpected EXEC tail")
    for off, size in pairs:
        if off % 2 or size % 2 or size < 0 or off + size > len(pool):
            raise ValueError("message byte offset/size invalid")
    edges = instruction_edges(code, fmt)
    if any(value not in edges for value in labels):
        raise ValueError("label not on instruction boundary")
    return {"fmt": fmt, "prefix": prefix, "seg3": seg3, "code": code,
            "pool": pool, "pairs": pairs, "tail": tail}


def rebuild_messages(data: bytes, messages: list[bytes], *, fmt: str) -> bytes:
    """Same message IDs; strictly contiguous pools only, preserve code and controls.

    Callers provide complete message bytes including controls. This function does
    not infer name/message splits or reconstruct ruby/voice markup from prose.
    """
    image = parse(data, fmt=fmt)
    pairs, old_pool = image["pairs"], image["pool"]
    if len(messages) != len(pairs):
        raise ValueError("message count cannot change")
    cursor = 0
    for off, size in pairs:
        if off != cursor:
            raise ValueError("shared/gapped pool requires richer relocation; refused")
        cursor += size
    if cursor != len(old_pool):
        raise ValueError("unreferenced pool bytes; refused")
    pool, table = bytearray(), bytearray(struct.pack("<I", len(messages)))
    for raw in messages:
        if len(raw) % 2:
            raise ValueError("odd message length")
        table += struct.pack("<I", len(pool))
        if fmt != "utf16-2008-v0":
            table += struct.pack("<I", len(raw))
        pool += raw
    block = struct.pack("<I", len(pool)) + pool
    suffix = block + table if fmt == "utf16-2008-v0" else table + block
    return image["prefix"] + suffix + image["tail"]


def selftest(data: bytes, *, fmt: str) -> dict:
    image = parse(data, fmt=fmt)
    messages = [image["pool"][off:off + size] for off, size in image["pairs"]]
    return {"fmt": fmt, "messages": len(messages),
            "byte_exact": rebuild_messages(data, messages, fmt=fmt) == data,
            "instruction_boundaries": len(instruction_edges(image["code"], fmt))}
