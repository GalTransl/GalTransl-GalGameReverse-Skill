"""Softpal Sv20 proven text operands, TEXT.DAT append and POINT.DAT labels.
Source: VNTextPatch-net8, VNTextPatch.Shared/Scripts/Softpal/SoftpalScript.cs,
GetStrings/WritePatched/ReadPointDat; SoftpalDisassembler.cs (CodeOffset).
Commit d9c0fab7b72fdcf87d674ef12a84d3829c9188be; source license MIT.
Operand discovery/VM analysis and encrypted TEXT.DAT are NOT implemented.
"""
from dataclasses import dataclass
import struct


@dataclass(frozen=True)
class TextRecord:
    operand: int
    kind: str
    address: int
    text: str


def point_labels(point: bytes, code_size: int) -> tuple[int, ...]:
    """$POINT_LIST_**** offsets -> reversed absolute Sv20 labels (base 0x0c)."""
    if point[:16] != b"$POINT_LIST_****" or (len(point) - 16) % 4:
        raise ValueError("invalid Softpal POINT.DAT")
    labels = tuple(value + 12 for value, in struct.iter_unpack("<I", point[16:]))
    if any(not 12 <= label < code_size for label in labels):
        raise ValueError("POINT.DAT label outside Sv20 code")
    return labels[::-1]


def read_text_records(code: bytes, text: bytes, operands: tuple[tuple[int, str], ...],
                      encoding: str = "cp932") -> tuple[TextRecord, ...]:
    """Known (operand offset, role) -> all texts, including context-only names.

    The operand points to a four-byte metadata word; actual cstring starts +4.
    Only explicitly unencrypted '_' TEXT.DAT is accepted; no fake decryption flag.
    """
    if len(code) < 12 or code[:4] != b"Sv20":
        raise ValueError("not Softpal Sv20")
    if not text.startswith(b"_"):
        raise ValueError("encrypted/unknown TEXT.DAT requires separate verified decoding")
    seen, result = [], []
    for offset, role in operands:
        if role not in {"name", "message", "choice", "context_name"}:
            raise ValueError("unknown Softpal text role")
        if type(offset) is not int or not 12 <= offset <= len(code) - 4:
            raise ValueError("text operand outside Sv20 code")
        if any(abs(offset - other) < 4 for other in seen):
            raise ValueError("duplicate/overlapping Softpal operands")
        seen.append(offset)
        address, = struct.unpack_from("<I", code, offset)
        if address + 4 >= len(text):
            raise ValueError("Softpal text pointer outside TEXT.DAT")
        end = text.find(b"\0", address + 4)
        if end < 0:
            raise ValueError("unterminated Softpal text")
        value = text[address + 4:end].decode(encoding, errors="strict")
        result.append(TextRecord(offset, role, address, value.replace("<br>", "\n")))
    return tuple(result)


def append_text_records(code: bytes, text: bytes, point: bytes,
                        operands: tuple[tuple[int, str], ...],
                        replacements: dict[int, str], encoding: str = "cp932"
                        ) -> tuple[bytes, bytes, bytes]:
    """Return (new Sv20, new TEXT.DAT, identical POINT.DAT); keys are operand offsets.

    Append zero metadata + cstring, patch literal operands only. Code size/labels
    stay fixed. Caller must prove the supplied operands via a complete disassembly.
    """
    records = read_text_records(code, text, operands, encoding)
    point_labels(point, len(code))
    known = {record.operand: record for record in records}
    if replacements.keys() - known.keys():
        raise ValueError("unproven Softpal operand")
    new_code, new_text = bytearray(code), bytearray(text)
    for operand, value in sorted(replacements.items()):
        record = known[operand]
        if record.kind == "context_name" or (record.kind == "name" and record.text.startswith("$")):
            raise ValueError("context/name-variable is not writable")
        if not isinstance(value, str) or "\0" in value:
            raise ValueError("invalid Softpal text")
        value = value.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")
        raw = value.encode(encoding, errors="strict")
        if b"\0" in raw or len(new_text) > 0xFFFFFFFF:
            raise ValueError("Softpal cstring encoding/address overflow")
        struct.pack_into("<I", new_code, operand, len(new_text))
        new_text.extend(b"\0" * 4 + raw + b"\0")
    return bytes(new_code), bytes(new_text), point
