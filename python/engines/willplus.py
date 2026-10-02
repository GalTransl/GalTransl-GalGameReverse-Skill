"""WillPlus AdvHD WS2 v1 code-slice parser, controls and absolute relocation.
Source: VNTextPatch-net8, VNTextPatch.Shared/Scripts/AdvHd/
AdvHdDisassemblerV1.cs (OperandTemplates), AdvHdDisassemblerBase.cs
(HandleMessage/HandleCharacterName/HandleChoiceScreen), AdvHdScript.cs
(RemoveControlCodes/AddControlCodes), Util/BinaryPatcher.cs (MapOffset/PatchAddress).
Commit d9c0fab7b72fdcf87d674ef12a84d3829c9188be; source license MIT.
NOT an arbitrary WS2 writer: accepts a proven v1 slice, no guessed 8-byte trailer.
"""
from dataclasses import dataclass
import re
import struct


@dataclass(frozen=True)
class Field:
    start: int
    end: int
    kind: str
    raw: str
    text: str


@dataclass(frozen=True)
class Layout:
    fields: tuple[Field, ...]
    addresses: tuple[tuple[int, int], ...]
    boundaries: tuple[int, ...]


def _display(raw, kind):
    if kind == "name":
        for code in ("%LC", "%LF", "%LR"):
            if raw.startswith(code):
                return raw[len(code):]
        return raw
    return re.sub(r"(?:%[A-Za-z0-9_]+)+$", "", raw).replace("\\n", "\n")


def parse_ws2_v1_subset(code: bytes, encoding: str = "cp932") -> Layout:
    """Parse opcodes 00,02,05,06,0F,13,14,15,17; addresses are slice-relative.

    14 is i32/internal-cstring/message-cstring; 15 is name-cstring. Each 0F choice
    is i16/caption/u8/i16 plus a 02/06 jump. Unknown instructions fail closed.
    """
    pos, fields, addresses, boundaries = 0, [], [], []

    def take(size):
        nonlocal pos
        if pos + size > len(code):
            raise ValueError("truncated WS2 instruction")
        start = pos
        pos += size
        return start

    def string(kind):
        nonlocal pos
        start = pos
        end = code.find(b"\0", pos)
        if end < 0:
            raise ValueError("unterminated WS2 string")
        raw = code[start:end].decode(encoding, errors="strict")
        pos = end + 1
        if kind is not None:
            fields.append(Field(start, pos, kind, raw, _display(raw, kind)))

    def jump():
        at = take(4)
        addresses.append((at, struct.unpack_from("<I", code, at)[0]))

    while pos < len(code):
        boundaries.append(pos)
        op = code[take(1)]
        if op in (0, 5, 0x13, 0x17):
            pass
        elif op in (2, 6):
            jump()
        elif op == 0x14:
            take(4)
            string(None)
            string("message")
        elif op == 0x15:
            string("name")
        elif op == 0x0F:
            count = code[take(1)]
            for _ in range(count):
                take(2)
                string("choice")
                take(3)
                boundaries.append(pos)
                jump_op = code[take(1)]
                if jump_op not in (2, 6):
                    raise ValueError("unsupported WS2 choice jump")
                jump()
        else:
            raise ValueError(f"WS2 opcode outside v1 subset: {op:#x}")
    starts = set(boundaries)
    if any(target not in starts for _, target in addresses):
        raise ValueError("WS2 jump target is not a proven instruction boundary")
    return Layout(tuple(fields), tuple(addresses), tuple(boundaries))


def patch_ws2_v1_subset(code: bytes, replacements: dict[int, str],
                        encoding: str = "cp932") -> bytes:
    """Replace by field ordinal and relocate all recognized absolute jump operands.

    Input is the whole zero-based proven code region, not an arbitrary middle slice.
    Footer/archive relocation and all other WS2 versions are outside this function.
    """
    layout = parse_ws2_v1_subset(code, encoding)
    if any(type(k) is not int or not 0 <= k < len(layout.fields) for k in replacements):
        raise ValueError("unknown WS2 field")
    changes = []
    for index, text in sorted(replacements.items()):
        field = layout.fields[index]
        if not isinstance(text, str) or any(c in text for c in "\0%\\"):
            raise ValueError("WS2 replacement must not introduce engine controls")
        if field.kind == "name":
            if field.text.startswith("$"):
                raise ValueError("name variable is context-only")
            if "\n" in text or "\r" in text:
                raise ValueError("newline in WS2 name")
            prefix = next((p for p in ("%LC", "%LF", "%LR") if field.raw.startswith(p)), "")
            text = prefix + text
        else:
            suffix = re.search(r"(?:%[A-Za-z0-9_]+)+$", field.raw)
            text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", " \\n")
            text += suffix.group() if suffix else ""
        raw = text.encode(encoding, errors="strict")
        if b"\0" in raw:
            raise ValueError("encoding incompatible with WS2 cstrings")
        changes.append((field.start, field.end, raw + b"\0"))
    out, cursor, mappings = bytearray(), 0, []
    for start, end, raw in sorted(changes):
        out.extend(code[cursor:start])
        new_start = len(out)
        out.extend(raw)
        mappings.append((start, end, new_start, len(out)))
        cursor = end
    out.extend(code[cursor:])

    def mapped(at):
        delta = 0
        for start, end, new_start, new_end in mappings:
            if at < start:
                break
            if at == start:
                return new_start
            if at < end:
                raise ValueError("address points inside changed WS2 string")
            delta = new_end - end
        return at + delta

    for operand, target in layout.addresses:
        value = mapped(target)
        if value > 0xFFFFFFFF:
            raise ValueError("WS2 address overflow")
        struct.pack_into("<I", out, mapped(operand), value)
    parse_ws2_v1_subset(bytes(out), encoding)
    return bytes(out)
