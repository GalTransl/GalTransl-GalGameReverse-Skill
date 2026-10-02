# SPDX-License-Identifier: GPL-3.0-only
"""MoonHir FBX two-bit-control codec and first-block script boundary.

Adapted from SExtractor tools/MoonHir/moonhir_fbx.py; strict bounds replace
source truncation and negative-index behavior. Not an FPK container writer.
"""
import struct

MAGIC = b"FBX\x01gkx"


def decode_payload(packed: bytes, expected_size: int, *, max_output: int = 64 * 1024 * 1024) -> bytes:
    if not 0 <= expected_size <= max_output:
        raise ValueError("invalid FBX output size")
    pos = 0
    control = 1
    output = bytearray()

    def take(size: int) -> bytes:
        nonlocal pos
        if pos + size > len(packed):
            raise ValueError("truncated FBX token")
        result = packed[pos:pos + size]
        pos += size
        return result

    def append(raw: bytes) -> None:
        if len(output) + len(raw) > expected_size:
            raise ValueError("FBX token exceeds declared output")
        output.extend(raw)

    def backref(distance: int, count: int) -> None:
        if distance > len(output) or len(output) + count > expected_size:
            raise ValueError("invalid FBX back-reference")
        for _ in range(count):
            output.append(output[-distance])

    while len(output) < expected_size:
        if control == 1:
            control = take(1)[0] | 0x100
        tag = control & 3
        if tag == 0:
            append(take(1))
        elif tag == 1:
            append(take(take(1)[0] + 2))
        elif tag == 2:
            word = int.from_bytes(take(2), "big")
            backref((word >> 5) + 1, (word & 31) + 4)
        else:
            extra = take(1)[0]
            mode, count = extra >> 6, extra & 63
            if mode == 0:
                count = (count << 8) | take(1)[0]
                append(take(count + 0x102))
            elif mode == 1:
                word = int.from_bytes(take(2), "big")
                backref((word >> 5) + 1, (count << 5 | (word & 31)) + 0x24)
            elif mode == 3:
                take(count)
                control = 4  # restart control group after the shift below
            else:
                raise ValueError("reserved FBX extended token mode 2")
        control >>= 2
    # Source streams may carry a group-break C0 and FF C0 end marker.
    # Return only the exact declared output; wrapper validates packed size.
    if packed[pos:] not in (b"", b"\xff\xc0", b"\xc0\xff\xc0"):
        raise ValueError("unrecognized FBX trailing tokens")
    return bytes(output)


def unpack_fbx(data: bytes, *, max_output: int = 64 * 1024 * 1024) -> bytes:
    if len(data) < 16 or data[:7] != MAGIC:
        raise ValueError("FBX wrapper magic required")
    start = data[7]
    packed_size, size = struct.unpack_from("<II", data, 8)
    if start < 16 or start > len(data) or packed_size != len(data) - start:
        raise ValueError("invalid FBX wrapper sizes")
    return decode_payload(data[start:], size, max_output=max_output)


def pack_fbx_literal(payload: bytes) -> bytes:
    """Valid literal-only FBX, including singleton tails; no compression search."""
    tokens = []
    pos = 0
    while pos < len(payload):
        size = min(0x100, len(payload) - pos)
        if size == 1:
            tokens.append((0, payload[pos:pos + 1]))
        else:
            tokens.append((1, bytes([size - 2]) + payload[pos:pos + size]))
        pos += size
    packed = bytearray()
    for start in range(0, len(tokens), 4):
        group = tokens[start:start + 4]
        control = sum(tag << (i * 2) for i, (tag, _) in enumerate(group))
        if len(group) < 4:
            control |= 3 << (len(group) * 2)
        packed.append(control)
        for _, raw in group:
            packed.extend(raw)
        if len(group) < 4:
            packed.append(0xC0)
    packed.extend(b"\xff\xc0")
    return MAGIC + b"\x10" + struct.pack("<II", len(packed), len(payload)) + packed


def text_block(decoded_script: bytes) -> tuple[int, int, bytes]:
    if len(decoded_script) < 16:
        raise ValueError("truncated MoonHir block directory")
    start, size = struct.unpack_from("<II", decoded_script, 8)
    if start < 16 or start + size > len(decoded_script):
        raise ValueError("first block outside decoded script")
    return start, start + size, decoded_script[start:start + size]


def replace_text_block(decoded_script: bytes, replacement: bytes) -> bytes:
    start, end, raw = text_block(decoded_script)
    if len(replacement) != len(raw):
        raise NotImplementedError("MoonHir later-block relocation not implemented")
    if replacement.count(b"\0") != raw.count(b"\0"):
        raise ValueError("string table cardinality changed")
    # Keep individual string byte lengths to avoid shifting intra-block references.
    if tuple(map(len, replacement.split(b"\0"))) != tuple(map(len, raw.split(b"\0"))):
        raise NotImplementedError("MoonHir intra-block string offsets are unknown")
    return decoded_script[:start] + replacement + decoded_script[end:]
