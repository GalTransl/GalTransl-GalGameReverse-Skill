"""Majiro MJO code XOR and text/ruby instruction-fragment assembly.
Source: VNTextPatch-net8, VNTextPatch.Shared/Scripts/Majiro/MajiroScript.cs,
ReadHeader/GetEncryptionTable/GetEncryptionValue/AssembleText;
MajiroAssembler.cs (WriteOperands), MajiroOpcodes.cs, MajiroSyscalls.cs.
Commit d9c0fab7b72fdcf87d674ef12a84d3829c9188be; source license MIT.
Fragments are NOT complete MJO patch files: entry/function/branch relocation omitted.
"""
import re
import struct

PLAIN = b"MajiroObjV1.000\0"
ENCRYPTED = b"MajiroObjX1.000\0"


def xor_code(code: bytes) -> bytes:
    """XOR with repeating 1024-byte LE CRC-polynomial table; involutive."""
    table = bytearray()
    for seed in range(256):
        value = seed
        for _ in range(8):
            value = (value >> 1) ^ (0xEDB88320 if value & 1 else 0)
        table.extend(struct.pack("<I", value))
    return bytes(value ^ table[index % 1024] for index, value in enumerate(code))


def _code_base(data):
    if len(data) < 32 or data[:16] not in (PLAIN, ENCRYPTED):
        raise ValueError("not Majiro MJO V/X 1.000")
    functions, = struct.unpack_from("<I", data, 24)
    base = 32 + 8 * functions
    if base > len(data):
        raise ValueError("truncated MJO function table")
    length, = struct.unpack_from("<I", data, base - 4)
    if base + length != len(data):
        raise ValueError("MJO code size mismatch")
    return base


def normalize_mjo(data: bytes, *, encrypted: bool = False) -> bytes:
    """Change only code XOR and signature. Header/table/code lengths stay exact."""
    base = _code_base(data)
    old_encrypted = data[:16] == ENCRYPTED
    body = xor_code(data[base:]) if old_encrypted != encrypted else data[base:]
    return (ENCRYPTED if encrypted else PLAIN) + data[16:base] + body


def _string_instruction(opcode, text, encoding):
    if "\0" in text:
        raise ValueError("NUL in Majiro text")
    raw = text.encode(encoding, errors="strict")
    if b"\0" in raw or len(raw) + 1 > 65535:
        raise ValueError("Majiro u16 string size/encoding invalid")
    return struct.pack("<HH", opcode, len(raw) + 1) + raw + b"\0"


def assemble_text(text: str, encoding: str = "cp932") -> bytes:
    """Display text with [base/reading] and newlines -> Majiro text/proc/ruby/ctrl.

    Uses Ruby syscall 0x3198FD01, ldstr=0801, text=0840, proc=0841, ctrl=0842.
    No names inferred, no wrapping, no entry-point/branch offsets patched here.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    out = bytearray()
    for line_index, line in enumerate(text.split("\n")):
        if line_index:
            out.extend(_string_instruction(0x842, "n", encoding))
        start = 0
        for match in re.finditer(r"\[([^\[\]/]+)/([^\[\]/]+)\]", line):
            plain = line[start:match.start()]
            if "[" in plain or "]" in plain:
                raise ValueError("unsupported Majiro ruby syntax")
            if plain:
                out.extend(_string_instruction(0x840, plain, encoding))
                out.extend(struct.pack("<H", 0x841))
            out.extend(_string_instruction(0x801, match[1], encoding))
            out.extend(_string_instruction(0x801, match[2], encoding))
            out.extend(struct.pack("<HIIH", 0x810, 0x3198FD01, 0, 2))
            start = match.end()
        plain = line[start:]
        if "[" in plain or "]" in plain:
            raise ValueError("unsupported Majiro ruby syntax")
        if plain:
            out.extend(_string_instruction(0x840, plain, encoding))
            out.extend(struct.pack("<H", 0x841))
    return bytes(out)


def disassemble_text(fragment: bytes, encoding: str = "cp932") -> str:
    """Inverse of the canonical fragment assembler; unknown instructions refuse."""
    pos = 0
    output = []

    def string(expected):
        nonlocal pos
        if pos + 4 > len(fragment):
            raise ValueError("truncated Majiro text instruction")
        opcode, size = struct.unpack_from("<HH", fragment, pos)
        if opcode != expected or size == 0 or pos + 4 + size > len(fragment):
            raise ValueError("invalid Majiro text instruction")
        raw = fragment[pos + 4:pos + 4 + size]
        if raw[-1] != 0 or b"\0" in raw[:-1]:
            raise ValueError("Majiro string size/terminator mismatch")
        pos += 4 + size
        return raw[:-1].decode(encoding, errors="strict")

    while pos < len(fragment):
        if pos + 2 > len(fragment):
            raise ValueError("truncated Majiro opcode")
        op, = struct.unpack_from("<H", fragment, pos)
        if op == 0x840:
            output.append(string(op))
            if fragment[pos:pos + 2] != struct.pack("<H", 0x841):
                raise ValueError("text is not followed by proc")
            pos += 2
        elif op == 0x842:
            if string(op) != "n":
                raise ValueError("only ctrl n is supported")
            output.append("\n")
        elif op == 0x801:
            base, ruby = string(op), string(op)
            call = struct.pack("<HIIH", 0x810, 0x3198FD01, 0, 2)
            if fragment[pos:pos + len(call)] != call:
                raise ValueError("ldstr pair is not a canonical Ruby call")
            pos += len(call)
            output.append(f"[{base}/{ruby}]")
        else:
            raise ValueError(f"non-text Majiro opcode {op:#x}")
    return "".join(output)
