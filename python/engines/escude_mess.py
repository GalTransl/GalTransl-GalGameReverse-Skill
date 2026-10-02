"""Escu:de @mess:__ / @code:__ (Haison profile), independent Python reference.

Original implementation, GPL-3.0-or-later. Format facts verified on the 2026-10-01
user sample against its misc/script.c, misc/script.inc and adv/adv_script.inc.
No game source or assets are included. This is a structural scanner, not a VM.
See engines/escude.md for the speaker scope and source evidence.
"""
from dataclasses import dataclass
import codecs
import re
import struct


REFERENCE = "escude-mess-haison/1"
_PARAM_COUNTS = (
    None, 0, 1, 0, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 0, 1,
    1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 2, 1, 1,
)
_TOKENS = re.compile(r"<[^<>]*>|%\{[^{}]*\}")
# Haison CV/voice/face/wait/graphics/sound operations do not assign text.name.
# Other natives (including frame/clear and external script calls) are barriers.
_NAME_PRESERVING_PROCS = frozenset((29, 30, 31, 38, *range(39, 84)))


@dataclass(frozen=True)
class MessagePool:
    offsets: tuple[int, ...]
    strings: tuple[bytes, ...]


@dataclass(frozen=True)
class Instruction:
    offset: int
    opcode: int
    params: tuple[int, ...]


@dataclass(frozen=True)
class Code:
    vm: bytes
    text: MessagePool
    message_count: int
    instructions: tuple[Instruction, ...]


@dataclass(frozen=True)
class Record:
    index: int
    message: str
    kind: str
    code_offset: int
    line: int | None
    name_id: int | None
    name: str | None
    name_offset: int | None


def _pool(offsets: tuple[int, ...], data: bytes) -> MessagePool:
    pos = 0
    strings = []
    for offset in offsets:
        if offset != pos:
            raise ValueError("noncanonical message pool offset/gap/alias")
        end = data.find(b"\0", pos)
        if end < 0:
            raise ValueError("unterminated message pool string")
        strings.append(data[pos:end])
        pos = end + 1
    if pos != len(data):
        raise ValueError("unknown message pool trailing data")
    return MessagePool(offsets, tuple(strings))


def read_mess(data: bytes, *, max_bytes: int = 64 << 20,
              max_strings: int = 4096) -> MessagePool:
    """Validate count/length/offsets, XOR only the pool (including NUL bytes)."""
    if len(data) > max_bytes or len(data) < 16 or data[:8] != b"@mess:__":
        raise ValueError("not bounded @mess:__")
    count, size = struct.unpack_from("<II", data, 8)
    start = 16 + count * 4
    if count > max_strings or start + size != len(data):
        raise ValueError("invalid @mess:__ count/size")
    offsets = struct.unpack_from(f"<{count}I", data, 16)
    return _pool(offsets, bytes(b ^ 0x55 for b in data[start:]))


def read_code(data: bytes, *, max_bytes: int = 64 << 20,
              max_instructions: int = 1_000_000) -> Code:
    """Scan every opcode with the Haison 1..45 layout; never execute it."""
    if len(data) > max_bytes or len(data) < 24 or data[:8] != b"@code:__":
        raise ValueError("not bounded @code:__")
    size, count, text_size, message_count = struct.unpack_from("<4I", data, 8)
    if message_count > 4096 or count > 4096 or 24 + size + count*4 + text_size != len(data):
        raise ValueError("invalid @code:__ section lengths")
    vm = data[24:24+size]
    offsets = struct.unpack_from(f"<{count}I", data, 24+size)
    text = _pool(offsets, data[24+size+count*4:])
    pos = 0
    instructions = []
    while pos < len(vm):
        start = pos
        opcode = vm[pos]
        if not 1 <= opcode < len(_PARAM_COUNTS):
            raise ValueError(f"unknown Haison opcode {opcode:#x} at {start:#x}")
        count = _PARAM_COUNTS[opcode]
        pos += 1 + 4*count
        if pos > len(vm) or len(instructions) >= max_instructions:
            raise ValueError("truncated/over-budget Haison instructions")
        params = struct.unpack_from(f"<{count}i", vm, start+1)
        instructions.append(Instruction(start, opcode, params))
    boundaries = {ins.offset for ins in instructions}
    for ins in instructions:
        op, args = ins.opcode, ins.params
        if op in (15, 16, 17) and args[0] not in boundaries:
            raise ValueError("Haison jump/call outside instruction boundary")
        if op == 43 and args[1] not in boundaries:
            raise ValueError("Haison option target outside instruction boundary")
        if op in (8, 41, 43) and not 0 <= args[0] < message_count:
            raise ValueError("Haison message index out of range")
        if op == 7 and not 0 <= args[0] < len(text.strings):
            raise ValueError("Haison text index out of range")
        if op == 44 and not 0 <= args[0] < 87:
            raise ValueError("unknown Haison native procedure")
    return Code(vm, text, message_count, tuple(instructions))


def _name_preserving_calls(code: Code) -> set[int]:
    """Prove helper purity on all branch paths, rejecting recursive calls.

    No stack values or game functions are evaluated. Unknown natives, text/page,
    NAME and missing returns prevent a name-preservation claim.
    """
    instructions = {i.offset: i for i in code.instructions}
    cache = {}
    active = set()
    visits = 0

    def pure(entry: int) -> bool:
        nonlocal visits
        if entry in cache:
            return cache[entry]
        if entry in active or len(active) >= 32 or instructions[entry].opcode != 13:
            return False
        active.add(entry)
        todo, seen = [entry], set()
        result, returned = True, False
        while todo:
            at = todo.pop()
            if at in seen:
                continue
            seen.add(at)
            visits += 1
            if visits > 1_000_000:
                raise ValueError("speaker helper analysis exceeds budget")
            ins = instructions.get(at)
            if ins is None:
                result = False
                break
            op, args = ins.opcode, ins.params
            if op in (40, 41, 42, 43) or (op == 44 and args[0] not in _NAME_PRESERVING_PROCS):
                result = False
                break
            if op == 17 and not pure(args[0]):
                result = False
                break
            if op == 18:
                returned = True
                continue
            if op in (15, 16):
                todo.append(args[0])
            if op != 15:
                todo.append(at + 1 + 4*len(args))
        active.remove(entry)
        cache[entry] = result and returned
        return cache[entry]

    return {i.params[0] for i in code.instructions if i.opcode == 17 and pure(i.params[0])}


def extract_pair(code_data: bytes, mess_data: bytes, *,
                 names: tuple[str, ...] | None = None) -> tuple[Record, ...]:
    """Match explicit NAME/TEXT packets and OPTION references to pool slots.

    Unproven calls, branches and PAGE end local speaker evidence. An explicit
    NAME can span only int pushes, argument cleanup, LINE and native CV (30).
    Continuations without PAGE inherit a proven local name; absent name means
    no proven local speaker, not a claim about every possible runtime state.
    Pool order must equal unique semantic-reference order (Haison invariant).
    """
    code = read_code(code_data)
    pool = read_mess(mess_data)
    if len(pool.strings) != code.message_count:
        raise ValueError("@code/@mess message counts disagree")
    targets = {ins.params[0] for ins in code.instructions if ins.opcode in (15, 16, 17)}
    targets.update(ins.params[1] for ins in code.instructions if ins.opcode == 43)
    preserving_calls = _name_preserving_calls(code)
    name_id = name_offset = line = None
    pending_name = False
    records = []
    for ins in code.instructions:
        op, args = ins.opcode, ins.params
        if ins.offset in targets:
            if pending_name:
                raise ValueError("branch enters an explicit speaker packet")
            name_id = name_offset = None
            line = None
        if op == 40:
            if pending_name:
                raise ValueError("unconsumed explicit speaker")
            name_id, name_offset = args[0], ins.offset
            if name_id < 0 or (names is not None and name_id >= len(names)):
                raise ValueError("speaker ID outside supplied name table")
            pending_name = True
        elif op == 45:
            line = args[0]
        elif op in (41, 43):
            index = args[0]
            if index != len(records):
                raise ValueError("non-unique or out-of-order semantic message references")
            selected_name = name_id if op == 41 else None
            name = names[selected_name] if names is not None and selected_name not in (None, 0) else None
            if name and "%{" in name:
                raise ValueError("dynamic speaker name requires runtime context")
            records.append(Record(index, pool.strings[index].decode("cp932", errors="strict"),
                                  "message" if op == 41 else "choice", ins.offset,
                                  line, selected_name, name or None,
                                  name_offset if op == 41 else None))
            pending_name = False
        elif op == 8:
            raise ValueError("PUSH_MESS requires additional consumer analysis")
        elif pending_name:
            if op not in (2, 4) and not (op == 44 and args[0] == 30):
                raise ValueError("unknown operation inside explicit speaker packet")
        elif (op in (13, 14, 15, 16, 18, 42)
              or op == 17 and args[0] not in preserving_calls
              or op == 44 and args[0] not in _NAME_PRESERVING_PROCS):
            name_id = name_offset = None
    if pending_name or len(records) != len(pool.strings):
        raise ValueError("dangling speaker or unclassified message pool entries")
    return tuple(records)


def protected_tokens(text: str) -> tuple[str, ...]:
    """Keep exact control tags, ruby attributes and variable references in order."""
    tokens = tuple(_TOKENS.findall(text))
    remainder = _TOKENS.sub("", text)
    if "<" in remainder or ">" in remainder or "%{" in remainder:
        raise ValueError("unrecognized message control syntax")
    return tokens


def patch_mess(data: bytes, replacements: dict[int, str], *, encoding: str = "cp932") -> bytes:
    """Rebuild offsets/size/XOR; keep unmodified raw bytes and every pool slot.

    Controls stay literal (including <r>); physical newlines are rejected.
    Only message bytes change. The paired @code file must remain unchanged.
    """
    if codecs.lookup(encoding).name != "cp932":
        raise ValueError("Haison profile only validates CP932 message encoding")
    pool = read_mess(data)
    if any(type(k) is not int or not 0 <= k < len(pool.strings) for k in replacements):
        raise ValueError("unknown message pool index")
    output = bytearray()
    offsets = []
    for index, raw in enumerate(pool.strings):
        if index in replacements:
            value = replacements[index]
            if not isinstance(value, str) or any(c in value for c in "\0\r\n"):
                raise ValueError("invalid message: retain literal <r> for newlines")
            if len(value) > (64 << 20):
                raise ValueError("replacement message exceeds budget")
            original = raw.decode("cp932", errors="strict")
            if protected_tokens(value) != protected_tokens(original):
                raise ValueError("message control tokens changed/reordered")
            if value != original:
                raw = value.encode(encoding, errors="strict")
                if b"\0" in raw:
                    raise ValueError("encoding incompatible with message cstrings")
        if len(output) + len(raw) + 1 > (64 << 20):
            raise ValueError("rebuilt message pool exceeds budget")
        offsets.append(len(output))
        output.extend(raw + b"\0")
    if len(output) > (64 << 20):
        raise ValueError("rebuilt message pool exceeds budget")
    result = (b"@mess:__" + struct.pack("<II", len(offsets), len(output))
              + struct.pack(f"<{len(offsets)}I", *offsets)
              + bytes(b ^ 0x55 for b in output))
    read_mess(result)
    return result
