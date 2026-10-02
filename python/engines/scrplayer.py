# SPDX-License-Identifier: GPL-3.0-only
"""ScrPlayer command/string tables with explicit source opcode profiles 1..6."""
from dataclasses import dataclass
import struct

# 1: translate and relocate; -1: relocate only; 0: numeric operand.
PROFILES = {
    1: {0x5E: (1, -1, 1), 0x65: (0, 1), 0x6B: (-1,), 0x6D: (-1,), 0x6F: (-1,), 0x70: (-1,), 0x72: (-1,), 0x84: (-1,), 0xAA: (1, 1, 1, 1, 1)},
    2: {0x5E: (1, -1, 1), 0x65: (0, 1), 0x6A: (1, 1, 0, -1, -1), 0x6B: (-1,), 0x6C: (-1,), 0x6D: (-1,), 0x6E: (-1,), 0x80: (-1,)},
    3: {0x5E: (0, 0, -1, 1), 0x65: (0, 1), 0x6B: (-1,), 0x6D: (-1,), 0x6F: (-1,), 0x70: (-1,), 0x72: (-1,), 0x7A: (-1,), 0x86: (-1,)},
    4: {0x5E: (1, -1, 1), 0x65: (0, 1), 0x6D: (-1,), 0x6F: (-1,), 0x71: (-1,), 0x72: (-1,), 0x74: (-1,), 0x8A: (-1,)},
    5: {0x5E: (1, -1, 1), 0x64: (0, 1), 0x60: (-1,), 0x6D: (-1,), 0x6F: (-1,), 0x71: (-1,), 0x72: (-1,), 0x74: (-1,), 0x7C: (-1,), 0x7D: (-1,), 0x8A: (-1,)},
    6: {0x5E: (1, -1, 1, 0), 0x64: (0, 1), 0x60: (-1,), 0x6C: (-1,), 0x6E: (-1,), 0x70: (-1,), 0x71: (-1,), 0x73: (-1,), 0x7B: (-1,), 0x7C: (-1,), 0x89: (-1,)},
}


@dataclass(frozen=True)
class Reference:
    command_offset: int
    operand_offset: int
    string_index: int
    translate: bool
    role: str


@dataclass(frozen=True)
class Script:
    header: bytes
    commands: bytes
    strings: tuple[bytes, ...]
    references: tuple[Reference, ...]
    unknown_commands: tuple[int, ...]


def _word(data: bytes, pos: int) -> int:
    if pos < 0 or pos + 4 > len(data):
        raise ValueError("truncated ScrPlayer word")
    return struct.unpack_from("<I", data, pos)[0]


def parse_script(data: bytes, *, version: int) -> Script:
    if version not in PROFILES:
        raise ValueError("select ScrPlayer profile 1..6; ambiguous union version 0 is rejected")
    command_size = _word(data, 0x10)
    start = 0x14
    string_size = _word(data, start + command_size)
    body_start = start + command_size + 4
    if body_start + string_size != len(data):
        raise ValueError("ScrPlayer section lengths disagree")
    commands = data[start:start + command_size]
    plain = bytes(b ^ 0x7F for b in data[body_start:])
    if not plain.endswith(b"\0"):
        raise ValueError("string table requires final terminator")
    strings = tuple(plain.split(b"\0"))
    address_to_index = {}
    address = 0
    for index, text in enumerate(strings):
        address_to_index[address] = index
        address += len(text) + 1
    references = []
    unknown = []
    pos = 0
    config = PROFILES[version]
    while pos < len(commands):
        if pos + 4 > len(commands):
            raise ValueError("truncated command header")
        opcode, length = commands[pos:pos + 2]
        if length < 4 or length % 4 or pos + length > len(commands):
            raise ValueError("invalid command length")
        if opcode not in config:
            unknown.append(pos)
        else:
            kinds = config[opcode]
            if length != 4 + 4 * len(kinds):
                raise ValueError("command operand count disagrees with version")
            for i, kind in enumerate(kinds):
                operand = pos + 4 * (i + 1)
                value = _word(commands, operand)
                if kind == 0 or value == 0xFFFFFFFF:
                    continue
                if value not in address_to_index or value == len(plain):
                    raise ValueError("string operand does not point to a string boundary")
                role = "name" if opcode == 0x5E and i == 0 else "message"
                references.append(Reference(pos, operand, address_to_index[value], kind == 1, role))
        pos += length
    return Script(data[:16], commands, strings, tuple(references), tuple(unknown))


def replace_strings(data: bytes, replacements: dict[int, bytes], *, version: int) -> bytes:
    script = parse_script(data, version=version)
    allowed = {ref.string_index for ref in script.references if ref.translate}
    if any(type(i) is not int or i not in allowed for i in replacements):
        raise ValueError("string is not a translatable command operand")
    strings = list(script.strings)
    changed_size = False
    for i, raw in replacements.items():
        if b"\0" in raw:
            raise ValueError("embedded terminator")
        changed_size |= len(raw) != len(strings[i])
        strings[i] = raw
    if changed_size:
        used = {ref.string_index for ref in script.references}
        if script.unknown_commands or any(text and i not in used for i, text in enumerate(script.strings)):
            raise NotImplementedError("cannot relocate with unknown commands/unreferenced nonempty strings")
    addresses = []
    address = 0
    for text in strings:
        addresses.append(address)
        address += len(text) + 1
    commands = bytearray(script.commands)
    for ref in script.references:
        struct.pack_into("<I", commands, ref.operand_offset, addresses[ref.string_index])
    plain = b"\0".join(strings)
    encrypted = bytes(b ^ 0x7F for b in plain)
    return script.header + struct.pack("<I", len(commands)) + commands + struct.pack("<I", len(encrypted)) + encrypted
