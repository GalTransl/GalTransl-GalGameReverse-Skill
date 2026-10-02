"""ExHibit RLD known operation fragments, indirect names and bounded header XOR.
Source: msg-tool, src/scripts/ex_hibit/rld.rs, OpExt::pack/unpack,
RldScript::xor/name_table/extract_messages/import_messages.
Commit f72716cee88554d40c1cdface2812493b14ca653; source license GPL-3.0-or-later.
Legacy fragment API, retained for compatibility. Complete v3/tag256 RLD IO,
runtime XOR and TAB/1010 choices are in exhibit_rld.py; do not use this module's
legacy XOR cutoff for that profile.
"""
from dataclasses import dataclass, replace
import struct


@dataclass(frozen=True)
class Op:
    opcode: int
    flags: int
    integers: tuple[int, ...]
    strings: tuple[str, ...]


@dataclass(frozen=True)
class Dialogue:
    op_index: int
    names: tuple[str, ...]
    message: str
    name_writable: bool
    name_id: int | None


def xor_rld(data: bytes, xor_key: int, keys: tuple[int, ...]) -> bytes:
    """Apply caller-supplied 256-word key, only [0x10, floor(min(size,FFCF)/4)*4)."""
    if len(data) < 16 or data[:4] != b"\0DLR":
        raise ValueError("not RLD")
    if len(keys) != 256 or any(type(k) is not int or not 0 <= k <= 0xFFFFFFFF
                               for k in (*keys, xor_key)):
        raise ValueError("RLD requires 256 u32 keys and a u32 xor key")
    out = bytearray(data)
    end = min(len(data), 0xFFCF) // 4 * 4
    for index, pos in enumerate(range(16, end, 4)):
        value, = struct.unpack_from("<I", data, pos)
        struct.pack_into("<I", out, pos, value ^ keys[index & 255] ^ xor_key)
    return bytes(out)


def read_ops(data: bytes, encoding: str = "cp932") -> tuple[Op, ...]:
    """Read an already-decrypted exact op region; only 28/48/21/191 are admitted."""
    pos, ops = 0, []
    while pos < len(data):
        if pos + 4 > len(data):
            raise ValueError("truncated RLD op")
        opcode, int_count, flags = struct.unpack_from("<HBB", data, pos)
        pos += 4
        if opcode not in {28, 48, 21, 191}:
            raise ValueError("RLD opcode outside reference subset")
        if pos + 4 * int_count > len(data):
            raise ValueError("truncated RLD integer operands")
        integers = struct.unpack_from(f"<{int_count}I", data, pos) if int_count else ()
        pos += 4 * int_count
        strings = []
        for _ in range(flags & 15):
            end = data.find(b"\0", pos)
            if end < 0:
                raise ValueError("unterminated RLD string")
            strings.append(data[pos:end].decode(encoding, errors="strict"))
            pos = end + 1
        ops.append(Op(opcode, flags & 0xF0, tuple(integers), tuple(strings)))
    return tuple(ops)


def write_ops(ops: tuple[Op, ...], encoding: str = "cp932") -> bytes:
    """Serialize op fragments, NOT a deployable .rld; high flag nibble is retained."""
    out = bytearray()
    for op in ops:
        if op.opcode not in {28, 48, 21, 191} or op.flags not in range(0, 256, 16):
            raise ValueError("unknown RLD op/flags")
        if len(op.integers) > 255 or len(op.strings) > 15:
            raise ValueError("RLD operand count overflow")
        out.extend(struct.pack("<HBB", op.opcode, len(op.integers), op.flags | len(op.strings)))
        for value in op.integers:
            if type(value) is not int or not 0 <= value <= 0xFFFFFFFF:
                raise ValueError("RLD integer overflow")
            out.extend(struct.pack("<I", value))
        for text in op.strings:
            raw = text.encode(encoding, errors="strict")
            if b"\0" in raw:
                raise ValueError("RLD string contains NUL")
            out.extend(raw + b"\0")
    return bytes(out)


def name_table(ops: tuple[Op, ...]) -> dict[int, str]:
    """defChara.rld op48 first-string CSV: field0=ID, field3=display name."""
    names = {}
    for op in ops:
        if op.opcode != 48:
            continue
        parts = op.strings[0].split(",") if op.strings else []
        if len(parts) < 4 or not parts[0].isascii() or not parts[0].isdigit():
            raise ValueError("invalid defChara op48")
        key = int(parts[0])
        if key > 0xFFFFFFFF or key in names:
            raise ValueError("duplicate/out-of-range defChara ID")
        names[key] = parts[3]
    return names


def extract_dialogue(ops: tuple[Op, ...], names: dict[int, str] | None = None
                     ) -> tuple[Dialogue, ...]:
    """Keep indirect IDs and read-only resolved context; do not fake choice support."""
    result = []
    for index, op in enumerate(ops):
        if op.opcode != 28:
            continue
        if len(op.strings) < 2:
            raise ValueError("RLD op28 needs name and message")
        name, message = op.strings[:2]
        if name == "*":
            if not op.integers:
                raise ValueError("indirect RLD name has no ID")
            key = op.integers[0]
            resolved = (names[key],) if names is not None and key in names else ()
            result.append(Dialogue(index, resolved, message, False, key))
        else:
            result.append(Dialogue(index, () if name == "$noname$" else (name,), message,
                                   name != "$noname$" and not name.startswith("$"), None))
    return tuple(result)


def patch_dialogue(ops: tuple[Op, ...], replacements: dict[int, dict[str, str]],
                   names: dict[int, str] | None = None) -> tuple[Op, ...]:
    """Patch op-index -> {message,name}; changing indirect/context names is an error."""
    records = {record.op_index: record for record in extract_dialogue(ops, names)}
    if replacements.keys() - records.keys():
        raise ValueError("unknown dialogue op (choices remain unsupported)")
    out = list(ops)
    for index, changes in replacements.items():
        if changes.keys() - {"name", "message"}:
            raise ValueError("unknown RLD translation field")
        strings = list(ops[index].strings)
        for key, value in changes.items():
            if not isinstance(value, str) or "\0" in value:
                raise ValueError("invalid RLD translation")
            if key == "name":
                if not records[index].name_writable:
                    raise ValueError("indirect/context name must be edited in its definition")
                strings[0] = value
            else:
                strings[1] = value
        out[index] = replace(ops[index], strings=tuple(strings))
    return tuple(out)
