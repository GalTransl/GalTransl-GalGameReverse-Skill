"""Favorite HCB code-region literals, speaker candidates and absolute relocation.
Source: msg-tool, src/scripts/favorite/disasm.rs, OPS/Data::read_func/
find_speak_functions/collect_speaker_names; src/scripts/favorite/hcb.rs,
HcbScript::import_messages. Commit f72716cee88554d40c1cdface2812493b14ca653;
source license GPL-3.0-or-later. NOT a complete HCB/header/ThreadStart writer.
"""
from dataclasses import dataclass
import struct


@dataclass(frozen=True)
class Instruction:
    address: int
    end: int
    opcode: int
    operands: tuple


@dataclass(frozen=True)
class Relocated:
    code: bytes
    addresses: dict[int, int]


def encode_literal(text: str, encoding: str = "cp932") -> bytes:
    """0E + u8(encoded-byte-length INCLUDING NUL) + cstring; max text bytes=254."""
    if not isinstance(text, str) or "\0" in text:
        raise ValueError("invalid Favorite string")
    raw = text.encode(encoding, errors="strict")
    if b"\0" in raw or len(raw) > 254:
        raise ValueError("Favorite literal exceeds u8 byte length or contains NUL")
    return bytes((0x0E, len(raw) + 1)) + raw + b"\0"


def parse_code(code: bytes, *, base: int = 4, encoding: str = "cp932") -> tuple[Instruction, ...]:
    """Known HCB region -> instruction boundaries; no syscalls or guessed opcodes."""
    if type(base) is not int or base < 0 or base + len(code) > 0xFFFFFFFF:
        raise ValueError("invalid Favorite code base")
    templates = {0: "", 1: "BB", 2: "I", 4: "", 5: "", 6: "I", 7: "I",
                 8: "", 9: "", 0xA: "I", 0xB: "H", 0xC: "B", 0xE: "s"}
    pos, instructions = 0, []
    while pos < len(code):
        start, opcode = pos, code[pos]
        pos += 1
        if opcode not in templates:
            raise ValueError(f"Favorite opcode outside subset: {opcode:#x}")
        operands = []
        for template in templates[opcode]:
            if template == "s":
                if pos >= len(code):
                    raise ValueError("missing Favorite length byte")
                size = code[pos]
                pos += 1
                if size == 0 or pos + size > len(code):
                    raise ValueError("invalid Favorite literal length")
                raw = code[pos:pos + size]
                if raw[-1] or b"\0" in raw[:-1]:
                    raise ValueError("Favorite length/NUL mismatch")
                operands.append(raw[:-1].decode(encoding, errors="strict"))
                pos += size
            else:
                size = struct.calcsize("<" + template)
                if pos + size > len(code):
                    raise ValueError("truncated Favorite operand")
                operands.append(struct.unpack_from("<" + template, code, pos)[0])
                pos += size
        instructions.append(Instruction(base + start, base + pos, opcode, tuple(operands)))
    starts = {instruction.address for instruction in instructions}
    for instruction in instructions:
        if instruction.opcode in (2, 6, 7) and instruction.operands[0] not in starts:
            raise ValueError("Favorite call/jump target not a proven instruction boundary")
    return tuple(instructions)


def speaker_candidates(code: bytes, *, base: int = 4, encoding: str = "cp932"
                       ) -> dict[int, tuple[str, ...]]:
    """initstack(3|5,0) -> every non-empty literal until the next initstack.

    This is a source-derived heuristic, not proof: retain all candidates, including
    question-mark names, rather than silently choose the last and discard context.
    """
    instructions = parse_code(code, base=base, encoding=encoding)
    names, current = {}, None
    for instruction in instructions:
        if instruction.opcode == 1:
            current = instruction.address if instruction.operands in ((3, 0), (5, 0)) else None
            if current is not None:
                names[current] = []
        elif current is not None and instruction.opcode == 0xE and instruction.operands[0].strip():
            names[current].append(instruction.operands[0])
    return {key: tuple(values) for key, values in names.items()}


def relocate_code(code: bytes, replacements: dict[int, str], *, base: int = 4,
                  encoding: str = "cp932") -> Relocated:
    """Literal instruction addresses -> text; map all boundaries and 02/06/07 targets.

    Returned map includes old code-end, so an integrator can update HCB script_len
    and the main-script pointer stored there. It must separately prove header/tail,
    ThreadStart pushint pointers and any omitted opcodes before writing a full file.
    Long-line splitting/cloned calls from upstream are intentionally NOT attempted.
    """
    instructions = parse_code(code, base=base, encoding=encoding)
    allowed = {item.address for item in instructions if item.opcode == 0xE}
    if replacements.keys() - allowed:
        raise ValueError("replacement does not identify a Favorite literal")
    output, addresses, jumps = bytearray(), {}, []
    for instruction in instructions:
        addresses[instruction.address] = base + len(output)
        if instruction.address in replacements:
            output.extend(encode_literal(replacements[instruction.address], encoding))
        else:
            if instruction.opcode in (2, 6, 7):
                jumps.append((len(output) + 1, instruction.operands[0]))
            output.extend(code[instruction.address - base:instruction.end - base])
    addresses[base + len(code)] = base + len(output)
    if base + len(output) > 0xFFFFFFFF:
        raise ValueError("Favorite address overflow")
    for position, old_target in jumps:
        struct.pack_into("<I", output, position, addresses[old_target])
    parse_code(bytes(output), base=base, encoding=encoding)
    return Relocated(bytes(output), addresses)
