"""Mware/Squirrel v2 literal serialization and reference-local copy-on-write.

Adapted from VNTextPatch-net8 (MIT), commit
d9c0fab7b72fdcf87d674ef12a84d3829c9188be,
VNTextPatch.Shared/Scripts/Mware/SquirrelObject.cs (Read/Write) and
MwareScript.cs (MergeIntoLiteralPools/PatchLiteralReferences).
No NUT disassembler, pool relocation or full-file writer is claimed.
"""
from collections.abc import Mapping, Sequence
import struct

NULL, INTEGER, FLOAT, STRING = 0x01000001, 0x05000002, 0x05000004, 0x08000010


def read_literal(data: bytes, offset: int = 0, *, encoding: str = "cp932") -> tuple[object, int]:
    """Return (value, exclusive end) for a known SquirrelObject boundary."""
    if offset < 0 or offset + 4 > len(data):
        raise ValueError("truncated literal tag")
    tag = struct.unpack_from("<I", data, offset)[0]
    pos = offset + 4
    if tag == NULL:
        return None, pos
    if tag not in (INTEGER, FLOAT, STRING):
        raise ValueError("unknown Squirrel literal tag")
    if pos + 4 > len(data):
        raise ValueError("truncated literal payload")
    if tag == INTEGER:
        return struct.unpack_from("<i", data, pos)[0], pos + 4
    if tag == FLOAT:
        return struct.unpack_from("<f", data, pos)[0], pos + 4
    length = struct.unpack_from("<i", data, pos)[0]
    pos += 4
    if length < 0 or pos + length > len(data):
        raise ValueError("invalid literal byte length")
    return data[pos:pos + length].decode(encoding, "strict"), pos + length


def write_literal(value: object, *, encoding: str = "cp932") -> bytes:
    if value is None:
        return struct.pack("<I", NULL)
    if type(value) is int:
        if not -(1 << 31) <= value < 1 << 31:
            raise ValueError("integer literal exceeds i32")
        return struct.pack("<Ii", INTEGER, value)
    if type(value) is float:
        return struct.pack("<If", FLOAT, value)
    if isinstance(value, str):
        raw = value.encode(encoding, "strict")
        return struct.pack("<Ii", STRING, len(raw)) + raw
    raise ValueError("unsupported literal type (bool is not an integer literal)")


def clone_translated_references(values: Sequence[object], indexes: Sequence[int],
                                widths: Sequence[int], replacements: Mapping[int, str], *,
                                encoding: str = "cp932") -> dict:
    """Plan a single pool's translated references, NOT byte offsets in a NUT.

    replacements maps REFERENCE ordinal -> new string, not literal index.
    Every changed reference gets a new literal. Unseen/shared resource uses
    therefore retain the original value. Validate 1-byte/4-byte operand width.
    Return values, indexes, and serialized pool; caller still must relocate.
    """
    if len(indexes) != len(widths):
        raise ValueError("reference/width count mismatch")
    for index, width in zip(indexes, widths):
        if type(index) is not int or not 0 <= index < len(values) or width not in (1, 4):
            raise ValueError("invalid literal reference or operand width")
        if index >= (256 if width == 1 else 1 << 31):
            raise ValueError("original reference does not fit operand width")
    if any(type(i) is not int or not 0 <= i < len(indexes) for i in replacements):
        raise ValueError("unknown reference ordinal")
    new_values, new_indexes = list(values), list(indexes)
    for ref, text in replacements.items():
        old = values[indexes[ref]]
        if not isinstance(old, str) or not isinstance(text, str):
            raise ValueError("translation must target a string literal")
        if text == old:
            continue
        new_index = len(new_values)
        if new_index >= (256 if widths[ref] == 1 else 1 << 31):
            raise ValueError("cloned literal index overflows reference operand")
        new_indexes[ref] = new_index
        new_values.append(text)
    pool = b"".join(write_literal(v, encoding=encoding) for v in new_values)
    return {"values": tuple(new_values), "indexes": tuple(new_indexes), "pool": pool}
