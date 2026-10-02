# SPDX-License-Identifier: GPL-3.0-only
"""Nexas ASM from tools/Nexas/Script_disassembler.py, not arbitrary assembly."""
from dataclasses import dataclass
import re

INSTRUCTION = re.compile(r"^\{0x[0-9A-Fa-f]+\}\t([A-Z_]+|CMD\.[0-9A-Fa-f]+)(?:\t|$)")
STRINGS = {"LOAD_STRING", "LOAD_CUSTOM_TEXT", "SPECIAL_TEXT"}


@dataclass(frozen=True)
class Field:
    line: int
    start: int
    end: int
    opcode: str
    role: str
    text: str


def _opcode(line: str) -> str | None:
    match = INSTRUCTION.match(line)
    return match.group(1) if match else None


def extract_fields(asm: str) -> tuple[Field, ...]:
    """Preserve raw backslash escapes; bounded PUSH/name/LOAD_STRING context check."""
    lines = asm.splitlines(keepends=True)
    fields = []
    absolute = 0
    for i, line in enumerate(lines):
        opcode = _opcode(line)
        if opcode in STRINGS:
            body = line.rstrip("\r\n")
            start = body.find("'")
            if start < 0 or not body.endswith("'") or start == len(body) - 1:
                raise ValueError("malformed Nexas ASM string operand")
            text = body[start + 1:-1]
            if "'" in text or any(c in text for c in "\r\n\t\0"):
                raise ValueError("ambiguous quoting or control in Nexas ASM string")
            # Source presets exclude asset identifiers/ASCII; role is a heuristic.
            if text and not text.isascii() and not re.search(r"\.[a-z]{1,5}$", text):
                is_name = (opcode == "LOAD_STRING" and 1 <= len(text) <= 8
                           and all(not (0x20 <= ord(c) <= 0x7E) for c in text)
                           and i > 0 and i + 1 < len(lines)
                           and _opcode(lines[i - 1]) == "PUSH"
                           and _opcode(lines[i + 1]) == "LOAD_STRING")
                fields.append(Field(i, absolute + start + 1, absolute + len(body) - 1,
                                    opcode, "name" if is_name else "message", text))
        absolute += len(line)
    return tuple(fields)


def replace_fields(asm: str, replacements: dict[int, str]) -> str:
    fields = extract_fields(asm)
    if any(type(i) is not int or not 0 <= i < len(fields) for i in replacements):
        raise ValueError("unknown ASM field")
    for index in sorted(replacements, reverse=True):
        text = replacements[index]
        if any(c in text for c in "'\r\n\t\0"):
            raise ValueError("replacement would break upstream assembler quoting")
        field = fields[index]
        asm = asm[:field.start] + text + asm[field.end:]
    return asm


def assemble_bin(asm: str, *, dat0: bytes, unmatched_strings: object = None) -> bytes:
    raise NotImplementedError("use matching upstream assembler with original dat0/JSON; bin emitter not ported")
