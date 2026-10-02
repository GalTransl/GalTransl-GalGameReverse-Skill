# SPDX-License-Identifier: GPL-3.0-only
"""Bounded CScript text/choice records from an explicitly decompressed payload.

No heuristic opcode scanning, native LZSS, or incomplete jump relocation.
"""
from dataclasses import dataclass
import struct


@dataclass(frozen=True)
class Field:
    role: str
    start: int
    end: int
    raw: bytes


@dataclass(frozen=True)
class Record:
    offset: int
    end: int
    version: int
    opcode: int
    fields: tuple[Field, ...]


def _word(data: bytes, pos: int) -> int:
    if pos < 0 or pos + 4 > len(data):
        raise ValueError("truncated CScript u32")
    return struct.unpack_from("<I", data, pos)[0]


def parse_record(payload: bytes, offset: int, *, version: int) -> Record:
    """Read exactly one candidate; source profiles 1, 10, 11 are explicit."""
    if version not in (1, 10, 11):
        raise ValueError("choose opcode profile 1, 10 or 11; no automatic detection")
    opcode = _word(payload, offset)
    message = opcode == (0x3F if version == 1 else 0x11)
    choice = opcode in ((0x15, 0x1A) if version == 1 else (0x14,))
    if not (message or choice):
        raise ValueError("not a supported dialogue/choice opcode")
    pos = offset + 4
    fields = []

    def string(role: str, maximum: int, allow_empty: bool = True) -> None:
        nonlocal pos
        size = _word(payload, pos)
        pos += 4
        if size > maximum or (not size and not allow_empty) or pos + size > len(payload):
            raise ValueError("invalid CScript string length")
        fields.append(Field(role, pos, pos + size, payload[pos:pos + size]))
        pos += size

    if message:
        pos += 0x11 if version == 1 else 4
        string("name", 0x40)
        if version == 1:
            pos += 5
        string("message", 0x200)
        if version != 1 and _word(payload, pos) != 0:
            raise ValueError("new CScript dialogue must be followed by zero word")
    else:
        if version == 1:
            pos += 8
        count = _word(payload, pos)
        if not 2 <= count <= 5:
            raise ValueError("source profile supports 2..5 choices")
        pos += 0x15 if version == 1 else 8
        for index in range(count):
            if index:
                pos += 5 if version == 1 else (4 if version == 11 else 0)
            string("choice", 0xFF if version == 1 else 0x1FF, False)
    if pos > len(payload):
        raise ValueError("record outside payload")
    return Record(offset, pos, version, opcode, tuple(fields))


def replace_record(payload: bytes, record: Record, replacements: dict[int, bytes]) -> bytes:
    """Equal-size fields only, preserving every prefix and any unparsed jumps."""
    if parse_record(payload, record.offset, version=record.version) != record:
        raise ValueError("stale record")
    if any(type(i) is not int or not 0 <= i < len(record.fields) for i in replacements):
        raise ValueError("unknown field")
    out = bytearray(payload)
    for i, replacement in replacements.items():
        field = record.fields[i]
        if len(replacement) != len(field.raw):
            raise NotImplementedError("CScript branch/normal/conditional relocation not implemented")
        out[field.start:field.end] = replacement
    return bytes(out)


def unpack_script(data: bytes) -> bytes:
    raise NotImplementedError("CScript wrapper/LZSS dialect not ported; supply decompressed payload")


def pack_script(payload: bytes) -> bytes:
    raise NotImplementedError("no CScript wrapper writer or LZSS encoder")
