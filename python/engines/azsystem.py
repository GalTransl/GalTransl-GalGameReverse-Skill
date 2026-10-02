# SPDX-License-Identifier: GPL-3.0-only
"""AZSystem decoded ASB records and the tools/asb_decrypt.py v1 wrapper."""
from dataclasses import dataclass
import struct
import zlib


@dataclass(frozen=True)
class TextField:
    start: int
    end: int
    role: str
    raw: bytes


def _u16(data: bytes, pos: int) -> int:
    if pos < 0 or pos + 2 > len(data):
        raise ValueError("truncated u16")
    return struct.unpack_from("<H", data, pos)[0]


def read_text_operand(data: bytes, pos: int) -> tuple[int, tuple[int, int] | None]:
    """One-byte total length; tag 07 is NUL-terminated text, known controls skipped."""
    if pos < 0 or pos + 2 > len(data):
        raise ValueError("truncated operand")
    length, tag = data[pos:pos + 2]
    if length < 2 or pos + length > len(data):
        raise ValueError("invalid operand length")
    if tag == 7:
        if length < 3 or data[pos + length - 1] != 0:
            raise ValueError("text operand lacks terminator")
        return pos + length, (pos + 2, pos + length - 1)
    if tag not in (6, 0x1C, 5, 4):
        raise ValueError(f"unknown operand tag {tag:#x}")
    return pos + length, None


def extract_fields(decoded_asb: bytes, *, version: int) -> tuple[TextField, ...]:
    """Read source versions 0/1/2; offsets refer to the decoded file, not packed ASB."""
    signatures = {0: (0x1F, (0x1D, 0x11, 0x1C)), 1: (0x1B, (0x16,)), 2: (0x1E, (0x1B,))}
    if version not in signatures:
        raise ValueError("supported opcode profiles: 0, 1, 2")
    if len(decoded_asb) < 16:
        raise ValueError("truncated ASB header")
    message, choices = signatures[version]
    fields = []
    pos = 16
    while pos < len(decoded_asb):
        length = _u16(decoded_asb, pos)
        if length < 4 or pos + length > len(decoded_asb):
            raise ValueError("invalid ASB command length")
        record = decoded_asb[pos + 2:pos + length]
        if len(record) >= 6 and record[1:6] == bytes(5) and record[0] in (message, *choices):
            cursor = 10
            if cursor > len(record):
                raise ValueError("truncated text command")
            if record[0] == message:
                for role in ("name", "message"):
                    cursor, span = read_text_operand(record, cursor)
                    if span is None:
                        raise ValueError("message operands must be strings")
                    start, end = (pos + 2 + n for n in span)
                    fields.append(TextField(start, end, role, decoded_asb[start:end]))
            else:
                while cursor < len(record):
                    cursor, span = read_text_operand(record, cursor)
                    if span is not None:
                        start, end = (pos + 2 + n for n in span)
                        fields.append(TextField(start, end, "choice", decoded_asb[start:end]))
        pos += length
    return tuple(fields)


def replace_field(decoded_asb: bytes, field: TextField, replacement: bytes) -> bytes:
    if not 16 <= field.start <= field.end <= len(decoded_asb) or decoded_asb[field.start:field.end] != field.raw:
        raise ValueError("stale field")
    if b"\0" in replacement:
        raise ValueError("embedded terminator")
    if len(replacement) != len(field.raw):
        raise NotImplementedError("full command/jump relocation has not been implemented")
    return decoded_asb[:field.start] + replacement + decoded_asb[field.end:]


def decrypt_v1(packed: bytes, *, max_output: int = 64 * 1024 * 1024) -> bytes:
    """ASB\x1a v1 only: subtract size-XOR key per LE word, then bounded zlib."""
    if len(packed) < 16 or packed[:4] != b"ASB\x1a":
        raise ValueError("ASB v1 signature required; v3 shares magic, choose version externally")
    compressed_size, size = struct.unpack_from("<II", packed, 4)
    if compressed_size != len(packed) - 16 or not 0 <= size <= max_output:
        raise ValueError("invalid compressed/output size")
    buf = bytearray(packed[16:])
    key = size ^ 0x9E370001
    for pos in range(0, len(buf) - 3, 4):
        value = (struct.unpack_from("<I", buf, pos)[0] - key) & 0xFFFFFFFF
        struct.pack_into("<I", buf, pos, value)
    dec = zlib.decompressobj()
    raw = dec.decompress(bytes(buf), size + 1)
    if len(raw) != size or not dec.eof or dec.unused_data or dec.unconsumed_tail:
        raise ValueError("invalid or oversized ASB zlib stream")
    return packed[:16] + raw


def encrypt_v1(decoded: bytes) -> bytes:
    if len(decoded) < 16 or decoded[:4] != b"ASB\x1a":
        raise ValueError("ASB v1 header required")
    raw = decoded[16:]
    buf = bytearray(zlib.compress(raw))
    key = len(raw) ^ 0x9E370001
    for pos in range(0, len(buf) - 3, 4):
        value = (struct.unpack_from("<I", buf, pos)[0] + key) & 0xFFFFFFFF
        struct.pack_into("<I", buf, pos, value)
    return decoded[:4] + struct.pack("<II", len(buf), len(raw)) + decoded[12:16] + buf
