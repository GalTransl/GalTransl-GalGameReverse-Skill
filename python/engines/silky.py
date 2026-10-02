"""Silky count/index/absolute-offset UTF-16LE MAP, NOT the four-section dialect.
Source: VNTextPatch-net8, VNTextPatch.Shared/Scripts/Silkys/SilkysMapScript.cs,
SilkysMapScript.Load/WritePatched; VNTextPatch.Shared/Util/BinaryPatcher.cs,
BinaryPatcher.MapOffset/PatchAddress. Commit d9c0fab7b72fdcf87d674ef12a84d3829c9188be.
Source license: MIT. Independently implemented; fixes omission of empty-row pointers.
"""
from dataclasses import dataclass
import struct


@dataclass(frozen=True)
class Entry:
    row: int
    index: int
    offset: int
    end: int
    text: str


def read_map(data: bytes) -> tuple[Entry, ...]:
    """Read all rows including empty strings, aliases and non-contiguous indices."""
    if len(data) < 4:
        raise ValueError("truncated MAP count")
    count, = struct.unpack_from("<I", data)
    table_end = 4 + 8 * count
    if table_end > len(data):
        raise ValueError("MAP table outside file")
    result = []
    spans = {}
    for row in range(count):
        index, offset = struct.unpack_from("<II", data, 4 + 8 * row)
        if offset < table_end or offset % 2 or offset + 2 > len(data):
            raise ValueError("invalid UTF-16 MAP pointer")
        end = offset
        while end + 2 <= len(data) and data[end:end + 2] != b"\0\0":
            end += 2
        if end + 2 > len(data):
            raise ValueError("unterminated MAP string")
        text = data[offset:end].decode("utf-16-le", errors="strict")
        result.append(Entry(row, index, offset, end + 2, text))
        spans[offset] = end + 2
    last_end = table_end
    for start, end in sorted(spans.items()):
        if start < last_end:
            raise ValueError("interior/suffix pointers are not supported")
        last_end = end
    return tuple(result)


def patch_map(data: bytes, replacements: dict[int, str]) -> bytes:
    """Replace by ORIGINAL TABLE ROW, not index or filtered extraction order.

    All aliases must receive the same effective text (supply every alias when
    changing one). Unknown gaps/trailer are preserved, never scanned as pointers.
    This is a writer only for the explicitly selected count/index/offset dialect.
    """
    rows = read_map(data)
    if any(type(k) is not int or not 0 <= k < len(rows) for k in replacements):
        raise ValueError("unknown MAP row")
    changes = {}
    for row in rows:
        text = replacements.get(row.row, row.text)
        if not isinstance(text, str) or "\0" in text:
            raise ValueError("MAP text must be a NUL-free string")
        encoded = text.encode("utf-16-le", errors="strict") + b"\0\0"
        if row.offset in changes and changes[row.offset][1] != encoded:
            raise ValueError("conflicting MAP aliases")
        changes[row.offset] = (row.end, encoded)
    out = bytearray()
    cursor = 0
    addresses = {}
    for start, (end, encoded) in sorted(changes.items()):
        out.extend(data[cursor:start])
        addresses[start] = len(out)
        out.extend(encoded)
        cursor = end
    out.extend(data[cursor:])
    for row in rows:  # Deliberately EVERY table row, including empty rows.
        new_offset = addresses[row.offset]
        if new_offset > 0xFFFFFFFF:
            raise ValueError("MAP address overflow")
        struct.pack_into("<I", out, 8 + row.row * 8, new_offset)
    return bytes(out)
