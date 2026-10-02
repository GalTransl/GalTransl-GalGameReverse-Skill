# SPDX-License-Identifier: GPL-3.0-only
"""MED script text-table boundary calculation; no archive detection by suffix."""
from dataclasses import dataclass
import struct


@dataclass(frozen=True)
class Table:
    start: int
    prefix: bytes
    strings: tuple[bytes, ...]


def parse_table(data: bytes) -> Table:
    """Text starts at LE32[4] + LE16[10]*2 + 0x10; length word excludes 0x10."""
    if len(data) < 16:
        raise ValueError("truncated MED header")
    declared = struct.unpack_from("<I", data)[0]
    if declared != len(data) - 16:
        raise ValueError("MED total length mismatch")
    start = struct.unpack_from("<I", data, 4)[0] + struct.unpack_from("<H", data, 10)[0] * 2 + 16
    if start >= len(data):
        raise ValueError("MED text boundary outside file")
    return Table(start, data[:start], tuple(data[start:].split(b"\0")))


def replace_strings(data: bytes, replacements: dict[int, bytes]) -> bytes:
    """Equal-length strings only: source's unknown prefix may contain offsets.

    Recompute the declared total anyway, preserving every NUL and empty field.
    """
    table = parse_table(data)
    if any(type(i) is not int or not 0 <= i < len(table.strings) for i in replacements):
        raise ValueError("unknown text-table index")
    strings = list(table.strings)
    for index, replacement in replacements.items():
        if b"\0" in replacement:
            raise ValueError("embedded terminator")
        if len(replacement) != len(strings[index]):
            raise NotImplementedError("MED prefix offsets are not understood; no variable-length writer")
        strings[index] = replacement
    result = bytearray(table.prefix + b"\0".join(strings))
    struct.pack_into("<I", result, 0, len(result) - 16)
    return bytes(result)


def classify_text(text: str) -> str | None:
    """Source's bracket-name/ASCII skip rules, not a universal Japanese detector."""
    if not text or 0x20 <= ord(text[0]) <= 0x7E:
        return None
    if text.startswith("【") and text.endswith("】"):
        return "name"
    return "message"
