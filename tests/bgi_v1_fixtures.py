# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 GalTransl contributors
"""Synthetic-only BGI Ver1 fixtures, reusable by archive integration tests.

make_v1_fixture(...) returns bytes. assemble_v1(...) is the low-level builder;
it deliberately does not import the implementation or its opcode table.
"""
import struct

MAGIC = b"BurikoCompiledScriptVer1.00\0"


def assemble_v1(instructions, strings=None, *, referenced_scripts=(), labels=(),
                padding=b"", tail=b"", encoding="cp932", minimal_header=False):
    """Build a synthetic header/code/pool without inferring operand widths.

    Instructions are tuples (opcode, operand, ...), or ('label', label_name).
    A 0001 string operand resolves a code label. A 0003 string operand resolves
    a pool key; (pool_key, byte_delta) gives an explicit shared/suffix alias.
    Other operands are literal u32 values. strings is an insertion-ordered dict
    of pool keys to text or raw bytes, with a NUL appended per value. labels is
    a sequence of symbolic code labels, or a dict of header names to offsets.
    """
    strings = {} if strings is None else strings
    offsets, code_size = {}, 0
    for inst in instructions:
        if inst[0] == "label":
            offsets[inst[1]] = code_size
        else:
            code_size += 4 * len(inst)
    pool, string_offsets = bytearray(), {}
    for key, text in strings.items():
        string_offsets[key] = code_size + len(pool)
        pool.extend(text.encode(encoding) if isinstance(text, str) else text)
        pool.append(0)
    code = bytearray()
    for inst in instructions:
        if inst[0] == "label":
            continue
        opcode = inst[0]
        code.extend(struct.pack("<I", opcode))
        for value in inst[1:]:
            if opcode == 1 and isinstance(value, str):
                value = offsets[value]
            elif opcode == 3 and isinstance(value, str):
                value = string_offsets[value]
            elif opcode == 3 and isinstance(value, tuple):
                value = string_offsets[value[0]] + value[1]
            code.extend(struct.pack("<I", value))
    if minimal_header:
        if referenced_scripts or labels or padding:
            raise ValueError("minimal header cannot contain tables/padding")
        header = struct.pack("<I", 4)
    else:
        tables = bytearray(struct.pack("<I", len(referenced_scripts)))
        for name in referenced_scripts:
            tables.extend(name.encode(encoding) + b"\0")
        label_pairs = labels.items() if isinstance(labels, dict) else ((name, offsets[name]) for name in labels)
        tables.extend(struct.pack("<I", len(labels)))
        for name, address in label_pairs:
            tables.extend(name.encode(encoding) + b"\0" + struct.pack("<I", address))
        tables.extend(padding)
        header = struct.pack("<I", 4 + len(tables)) + tables
    return MAGIC + header + code + pool + tail


def make_v1_fixture(rows=(("Alice", "Hello"), (None, "Narration")), *,
                    choices=(), choice_function=None, first_forward=True,
                    referenced_scripts=("common", "system", "chapter"),
                    labels=("entry",), padding=b"", tail=b"", encoding="cp932"):
    """Return a headered sample with names/messages, optional ordered choices.

    rows is a sequence of (name_or_None, message). None has no name operand;
    an empty string produces an explicit Internal empty-name operand.
    choice_function may be '_SelectEx'/'_SelectExtend' instead of direct 0160.
    The default first instruction is a forward 0001 and the header has tables.
    """
    instructions, strings = [], {}
    if first_forward:
        instructions.append((1, "entry"))
    instructions.append(("label", "entry"))
    for index, (name, message) in enumerate(rows):
        if name is not None:
            key = f"name{index}"
            strings[key] = name
            instructions.append((3, key))
        key = f"message{index}"
        strings[key] = message
        instructions.extend(((3, key), (0x140,)))
    if choices:
        for index, choice in enumerate(choices):
            key = f"choice{index}"
            strings[key] = choice
            instructions.append((3, key))
        if choice_function is not None:
            strings["function"] = choice_function
            instructions.extend(((3, "function"), (0x1C,)))
        else:
            instructions.append((0x160,))
    instructions.append((0x1B,))
    return assemble_v1(instructions, strings, referenced_scripts=referenced_scripts,
                       labels=labels, padding=padding, tail=tail, encoding=encoding)
