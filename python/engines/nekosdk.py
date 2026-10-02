# SPDX-License-Identifier: GPL-3.0-only
"""NekoSDK ADVSCRIPT2 display/log strings only; choices are NOT parsed."""
from dataclasses import dataclass
import struct

MAGIC = b"NEKOSDK_ADVSCRIPT2"
COMMANDS = tuple(name.encode("cp932") for name in ("[テキスト表示]", "[ログ追加]"))


@dataclass(frozen=True)
class Field:
    length_offset: int
    start: int
    end: int
    role: str
    raw: bytes


def _string(data: bytes, pos: int) -> tuple[int, int, int]:
    if pos < 0 or pos + 4 > len(data):
        raise ValueError("truncated NekoSDK length")
    size = struct.unpack_from("<I", data, pos)[0]
    start, end = pos + 4, pos + 4 + size
    if size < 1 or end > len(data) or data[end - 1] != 0:
        raise ValueError("invalid NekoSDK terminated string")
    if b"\0" in data[start:end - 1]:
        raise ValueError("embedded string terminator")
    return start, end - 1, end


def extract_fields(data: bytes) -> tuple[Field, ...]:
    if not data.startswith(MAGIC):
        raise ValueError("NEKOSDK_ADVSCRIPT2 required")
    candidates = []
    for command in COMMANDS:
        pos = len(MAGIC)
        while True:
            pos = data.find(command, pos)
            if pos < 0:
                break
            candidates.append((pos, command))
            pos += len(command)
    fields = []
    previous_end = len(MAGIC)
    for pos, command in sorted(candidates):
        if pos < previous_end:
            # A command-name byte sequence occurring inside a previous string.
            continue
        length_offset = pos - 4
        if length_offset < len(MAGIC):
            raise ValueError("command overlaps ADVSCRIPT2 header")
        size = struct.unpack_from("<I", data, length_offset)[0]
        if size not in (len(command), len(command) + 1) or pos + size > len(data):
            raise ValueError("command's declared length does not match marker")
        if size == len(command) + 1 and data[pos + len(command)] != 0:
            raise ValueError("invalid command terminator")
        cursor = pos + size
        for role in ("name", "message"):
            start, end, next_pos = _string(data, cursor)
            fields.append(Field(cursor, start, end, role, data[start:end]))
            cursor = next_pos
        previous_end = cursor
    return tuple(fields)


def replace_fields(data: bytes, replacements: dict[int, bytes]) -> bytes:
    """Adjust each known u32 length (including NUL), preserve opaque commands.

    No choice extraction, archive writer, or unknown command relocation is implied.
    """
    fields = extract_fields(data)
    if any(type(i) is not int or not 0 <= i < len(fields) for i in replacements):
        raise ValueError("unknown NekoSDK field")
    out = bytearray(data)
    for index in sorted(replacements, reverse=True):
        field = fields[index]
        replacement = replacements[index]
        if b"\0" in replacement:
            raise ValueError("embedded terminator")
        out[field.length_offset:field.end + 1] = struct.pack("<I", len(replacement) + 1) + replacement + b"\0"
    return bytes(out)
