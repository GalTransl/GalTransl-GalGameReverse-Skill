# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2021 arcusmaximus (MIT-derived portions)
# SPDX-FileCopyrightText: msg-tool contributors (GPL-3.0-or-later-derived portions)
# SPDX-FileCopyrightText: 2026 GalTransl contributors
"""Conservative, standalone BGI/Ethornell headered Ver1 analysis and append writer.

Sources (read-only provenance, NEVER runtime dependencies):
VNTextPatch-net8 Ethornell{V1Disassembler,Disassembler,Script}.cs,
MIT, d9c0fab7b72fdcf87d674ef12a84d3829c9188be;
msg-tool src/scripts/bgi/{parser,script}.rs, GPL-3.0-or-later,
f72716cee88554d40c1cdface2812493b14ca653.
The MIT notice is retained in the accompanying bgi_v1_opcodes.py.

Changed implementation: sparse core/stack layout with frozen legacy whitelists; header/target/pool
cross-checks; event-local literal roles; conservative unresolved-VM rejection;
append-only replacement (even shorter strings), followed by automatic rescanning.
Two event profiles share all structural checks: the default literal-argument
profile, and the opt-in PROFILE_VNTEXTPATCH grouping which mirrors upstream's
"top of stack is the argument" heuristic and is recorded as a weaker variant.
No V0, headerless fallback, old ruby/message dialect or complete VM.
Legacy scan_v1_subset/patch_v1_pool retain their caller-proven-length semantics.
"""
from dataclasses import dataclass
import struct

from .bgi_v1_opcodes import (OPERAND_TEMPLATES, operand_template, LAYOUT_STACK,
                             LAYOUT_EXPLICIT, LAYOUT_EXPLICIT565)

MAGIC = b"BurikoCompiledScriptVer1.00\0"


@dataclass(frozen=True)
class Reference:
    operand: int
    address: int
    end: int
    kind: str
    text: str


def code_offset(data: bytes) -> int:
    """Detect by signature, not extension; Ver1 code base = 28 + headerSize."""
    if not data.startswith(MAGIC) or len(data) < len(MAGIC) + 4:
        raise ValueError("not BGI Ver1")
    header_size, = struct.unpack_from("<I", data, len(MAGIC))
    base = len(MAGIC) + header_size
    if header_size < 4 or base > len(data):
        raise ValueError("invalid BGI header size")
    return base


def scan_v1_subset(data: bytes, code_length: int, encoding: str = "cp932") -> tuple[Reference, ...]:
    """Parse 0000,0003,0140,0143,0160,001B,00F4; refuse all other opcodes."""
    base = code_offset(data)
    stop = base + code_length
    if code_length <= 0 or stop > len(data):
        raise ValueError("invalid proven BGI code length")
    pos, stack, refs = base, [], {}
    last_op = None
    while pos < stop:
        if pos + 4 > stop:
            raise ValueError("truncated BGI opcode")
        op, = struct.unpack_from("<I", data, pos)
        last_op = op
        pos += 4
        if op in (0, 3):
            if pos + 4 > stop:
                raise ValueError("truncated BGI operand")
            value, = struct.unpack_from("<I", data, pos)
            if op == 3:
                address = base + value
                if not stop <= address < len(data):
                    raise ValueError("BGI string pointer outside pool")
                end = data.find(b"\0", address)
                if end < 0:
                    raise ValueError("unterminated BGI string")
                refs[pos] = [address, end + 1, "internal",
                             data[address:end].decode(encoding, errors="strict")]
                stack.append(pos)
            pos += 4
        elif op in (0x140, 0x143):
            if not stack:
                raise ValueError("BGI message string stack underflow")
            message = stack.pop()
            if refs[message][3]:
                refs[message][2] = "message"
            if stack:
                name = stack.pop()
                if refs[name][3]:
                    refs[name][2] = "name"
        elif op == 0x160:
            for operand in stack:
                refs[operand][2] = "choice"
            stack.clear()
        elif op in (0x1B, 0xF4):
            if pos != stop:
                raise ValueError("code after terminal opcode is outside this subset")
        else:
            raise ValueError(f"unknown/out-of-subset BGI opcode {op:#x}")
    if last_op not in (0x1B, 0xF4):
        raise ValueError("BGI subset requires a terminal opcode")
    return tuple(Reference(operand, *parts) for operand, parts in sorted(refs.items()))


def patch_v1_pool(data: bytes, code_length: int, replacements: dict[int, str],
                  encoding: str = "cp932") -> bytes:
    """Proven subset file -> rebuilt deduplicated pool, operands remain code-relative.

    Keys are original operand byte offsets. Internal strings are preserved. Pool
    must be fully covered by referenced, non-overlapping strings: unknown tail/gaps
    are refused rather than discarded. No jumps, arbitrary functions or v0 support.
    """
    refs = scan_v1_subset(data, code_length, encoding)
    base = code_offset(data)
    pool_start = base + code_length
    allowed = {ref.operand for ref in refs if ref.kind != "internal"}
    if replacements.keys() - allowed:
        raise ValueError("unknown/internal BGI operand")
    spans = sorted({(ref.address, ref.end) for ref in refs})
    cursor = pool_start
    for start, end in spans:
        if start != cursor:
            raise ValueError("BGI pool contains unproven gaps/suffix references")
        cursor = end
    if cursor != len(data):
        raise ValueError("BGI pool contains unreferenced trailing bytes")
    out, offsets = bytearray(data[:pool_start]), {}
    for ref in refs:
        if ref.operand in replacements:
            text = replacements[ref.operand]
            if not isinstance(text, str) or "\0" in text:
                raise ValueError("invalid BGI cstring")
            raw = text.encode(encoding, errors="strict")
            if b"\0" in raw:
                raise ValueError("encoding incompatible with BGI cstrings")
            raw += b"\0"
        else:
            raw = data[ref.address:ref.end]
        if raw not in offsets:
            offsets[raw] = len(out) - base
            out.extend(raw)
        address = offsets[raw]
        if address > 0xFFFFFFFF:
            raise ValueError("BGI relative address overflow")
        struct.pack_into("<I", out, ref.operand, address)
    return bytes(out)


PROFILE = (
    "bgi-headered-v1/literal-events-v1/"
    "core-inline-u16-stack-v1/counts-or-minimal4-zero-padding"
)
PROFILE_VNTEXTPATCH = (
    "bgi-headered-v1/vntextpatch-events-v1/"
    "core-inline-u16-stack-v1/counts-or-minimal4-zero-padding"
)
# Frozen manifest identities remain readable/writable with their original
# instruction whitelist. New exports use the generic stack layout above.
PROFILE_EXPLICIT = (
    "bgi-headered-v1/literal-events-v1/"
    "vntextpatch-d9c0fab7b72fdcf87d674ef12a84d3829c9188be-explicit568/"
    "counts-or-minimal4-zero-padding"
)
# Opt-in profile that reproduces VNTextPatch's own V1 event grouping (the
# "literal top of stack is the argument" heuristic) instead of requiring
# provably literal arguments. It is strictly weaker evidence: it can turn a
# stored/derived value into a name or a choice, which the default profile
# refuses. Recorded in the manifest as a separate variant so a consumer can
# tell literal rows from heuristic rows. Old message/ruby/flush semantics
# (0x0145/0x014E/0x01B5) remain blocked separately from their known widths.
PROFILE_EXPLICIT_VNTEXTPATCH = (
    "bgi-headered-v1/vntextpatch-events-v1/"
    "vntextpatch-d9c0fab7b72fdcf87d674ef12a84d3829c9188be-explicit568/"
    "counts-or-minimal4-zero-padding"
)
PROFILE_EXPLICIT565 = PROFILE_EXPLICIT.replace('explicit568', 'explicit565')
PROFILE_EXPLICIT565_VNTEXTPATCH = PROFILE_EXPLICIT_VNTEXTPATCH.replace('explicit568', 'explicit565')
_PROFILE_MODES = {
    PROFILE: (LAYOUT_STACK, 'literal'),
    PROFILE_VNTEXTPATCH: (LAYOUT_STACK, 'vntextpatch'),
    PROFILE_EXPLICIT: (LAYOUT_EXPLICIT, 'literal'),
    PROFILE_EXPLICIT_VNTEXTPATCH: (LAYOUT_EXPLICIT, 'vntextpatch'),
    PROFILE_EXPLICIT565: (LAYOUT_EXPLICIT565, 'literal'),
    PROFILE_EXPLICIT565_VNTEXTPATCH: (LAYOUT_EXPLICIT565, 'vntextpatch'),
}
PROFILES = tuple(_PROFILE_MODES)
_TERMINALS = (0x001B, 0x00F4)
_INTERNAL_FLUSH = (0x007E, 0x007F, 0x00FE)
_OLD_DIALECT = (0x0145, 0x014E, 0x01B5)
_CHOICE_FUNCTIONS = ("_SelectEx", "_SelectExtend")


class BgiV1Error(ValueError):
    """Structured fail-closed diagnostic; offsets are absolute file offsets."""

    def __init__(self, code: str, message: str, offset: int | None = None,
                 opcode: int | None = None, *, relative_offset: int | None = None):
        self.code = code
        self.message = message
        self.offset = offset
        self.opcode = opcode
        self.relative_offset = relative_offset
        detail = f"{code}: {message}"
        if offset is not None:
            detail += f" at file offset {offset:#x}"
        if opcode is not None:
            detail += f" (opcode {opcode:#06x})"
        super().__init__(detail)


@dataclass(frozen=True)
class Instruction:
    offset: int
    opcode: int
    operands: tuple[int, ...]


@dataclass(frozen=True)
class Event:
    kind: str
    instruction_offset: int
    message_operand: int
    name_operand: int | None
    speaker_status: str
    choice_group: int | None = None
    choice_index: int | None = None


@dataclass(frozen=True)
class Analysis:
    code_base: int
    code_length: int
    references: tuple[Reference, ...]
    events: tuple[Event, ...]
    profile: str
    boundary: dict
    instructions: tuple[Instruction, ...]
    semantic_diagnostics: tuple[dict, ...] = ()


def _limit(value: int, name: str) -> None:
    if type(value) is not int or value <= 0:
        raise BgiV1Error("malformed", f"{name} must be a positive integer")


def _u32(data: bytes, offset: int, end: int, what: str) -> int:
    if offset + 4 > end:
        raise BgiV1Error("malformed", f"truncated {what}", offset)
    return struct.unpack_from("<I", data, offset)[0]


def _cstring(data: bytes, start: int, stop: int, encoding: str,
             max_string_size: int) -> tuple[str, int]:
    if not 0 <= start < stop:
        raise BgiV1Error("malformed", "string address outside file/pool", start)
    end = data.find(b"\0", start, min(stop, start + max_string_size + 1))
    if end < 0:
        code = "budget_exceeded" if stop - start > max_string_size else "malformed"
        raise BgiV1Error(code, "unterminated or oversized NUL string", start)
    try:
        text = data[start:end].decode(encoding, errors="strict")
    except (UnicodeError, LookupError) as exc:
        raise BgiV1Error("malformed", f"invalid {encoding} string", start) from exc
    return text, end + 1


def _header(data: bytes, encoding: str, max_string_size: int) -> tuple[int, dict]:
    if not data.startswith(MAGIC):
        raise BgiV1Error("malformed", "only headered BGI Ver1 is supported", 0)
    size = _u32(data, len(MAGIC), len(data), "header size")
    base = len(MAGIC) + size
    if size < 4 or base > len(data):
        raise BgiV1Error("malformed", "invalid header size", len(MAGIC))
    # Explicit profile exception: legacy synthetic minimal header has NO tables.
    # This does not reinterpret its first code word as a count or code_length.
    if size == 4:
        return base, {"layout": "minimal4-no-tables", "header_size": size,
                      "referenced_scripts": [], "labels": [], "padding_size": 0}
    pos = len(MAGIC) + 4
    count = _u32(data, pos, base, "referenced script count")
    pos += 4
    if count > base - pos:
        raise BgiV1Error("malformed", "referenced script count exceeds header", pos - 4)
    scripts = []
    for _ in range(count):
        name, pos = _cstring(data, pos, base, encoding, max_string_size)
        scripts.append(name)
    count = _u32(data, pos, base, "label count")
    pos += 4
    if count > (base - pos) // 5:
        raise BgiV1Error("malformed", "label count exceeds header", pos - 4)
    labels = []
    for _ in range(count):
        name, pos = _cstring(data, pos, base, encoding, max_string_size)
        address = _u32(data, pos, base, "label address")
        labels.append({"name": name, "address": address, "operand_offset": pos})
        pos += 4
    if any(data[pos:base]):
        raise BgiV1Error("malformed", "unknown nonzero extra header fields", pos)
    return base, {"layout": "counts-and-nul-tables", "header_size": size,
                  "referenced_scripts": scripts, "labels": labels,
                  "padding_size": base - pos}


def _structure(data: bytes, base: int, header: dict, encoding: str,
               max_code_size: int, max_operations: int,
               max_string_size: int, max_text_bytes: int = 64 << 20,
               *, opcode_layout: str = LAYOUT_STACK) -> tuple[tuple, tuple, dict]:
    """Find one uniquely supported terminal boundary, never a min-ref cut.

    Terminals before the largest label/0001 target cannot end the code. Every
    target must be an instruction start. Referenced strings provide an upper
    bound only. After the first eligible terminal, a speculative linear decode
    up to that upper bound rejects any second eligible terminal. This also
    works when append-only edits leave the entire old pool unreferenced.
    Both the sparse stack layout and legacy explicit layouts share these
    checks. A successful boundary scan alone does not prove VM semantics.
    """
    targets = [{"address": label["address"], "operand_offset": label["operand_offset"],
                "source": "label"} for label in header["labels"]]
    for target in targets:
        if target["address"] % 4 or not 0 <= target["address"] < len(data) - base:
            raise BgiV1Error("malformed", "label target outside aligned code", target["operand_offset"])
    largest = max((t["address"] for t in targets), default=0)
    target_sources = {t["address"]: t["operand_offset"] for t in targets}
    string_cache = {}
    decoded_text_bytes = 0
    pos, pool_bound = base, len(data)
    operations, references, starts, terminals = [], [], set(), []
    candidate = None
    probe_stop = None
    while True:
        if pos >= pool_bound:
            probe_stop = {"offset": pos, "reason": "referenced_pool_bound"}
            break
        if len(operations) >= max_operations:
            # An unfinished ambiguity probe is not proof of a unique boundary.
            raise BgiV1Error("budget_exceeded", "operation limit during boundary scan", pos)
        if pos - base >= max_code_size:
            raise BgiV1Error("budget_exceeded", "code-size limit during boundary scan", pos)
        opcode = None
        try:
            opcode = _u32(data, pos, pool_bound, "opcode before pool boundary")
            template = operand_template(opcode, opcode_layout)
            if template is None:
                raise BgiV1Error("unsupported_opcode", f"opcode outside layout {opcode_layout}",
                                 pos, opcode, relative_offset=pos - base)
            end = pos + 4 + 4 * len(template)
            if end > pool_bound:
                raise BgiV1Error("malformed", "operand overlaps pool or EOF", pos, opcode)
            if end - base > max_code_size:
                raise BgiV1Error("budget_exceeded", "code size exceeds limit", pos, opcode)
            operands = tuple(struct.unpack_from("<I", data, p)[0]
                             for p in range(pos + 4, end, 4))
            starts.add(pos - base)
            for index, (kind, value) in enumerate(zip(template, operands)):
                operand = pos + 4 + index * 4
                if kind == "c":
                    if value % 4 or not 0 <= value < len(data) - base:
                        raise BgiV1Error("malformed", "code target outside aligned code", operand, opcode)
                    if value < end - base and value not in starts:
                        raise BgiV1Error("malformed", "code target lands in an operand", operand, opcode)
                    targets.append({"address": value, "operand_offset": operand, "source": "0001"})
                    target_sources.setdefault(value, operand)
                    largest = max(largest, value)
                elif kind == "m":
                    address = base + value
                    if not end <= address < len(data):
                        raise BgiV1Error("malformed", "string address overlaps code or leaves file", operand, opcode)
                    if address not in string_cache:
                        remaining = max_text_bytes - decoded_text_bytes
                        if remaining <= 0:
                            raise BgiV1Error("budget_exceeded", "unique/overlapping text cache exceeds budget", operand, opcode)
                        parsed_string = _cstring(data, address, len(data), encoding,
                                                 min(max_string_size, remaining - 1))
                        decoded_text_bytes += parsed_string[1] - address
                        string_cache[address] = parsed_string
                    text, string_end = string_cache[address]
                    references.append(Reference(operand, address, string_end, "internal", text))
                    pool_bound = min(pool_bound, address)
            if largest >= pool_bound - base:
                raise BgiV1Error("malformed", "code target reaches referenced string pool", pos, opcode)
            # Only this instruction's operand words can conceal a forward
            # target; avoid a quadratic scan over all prior targets per opcode.
            for address in range(pos - base + 4, end - base, 4):
                if address in target_sources:
                    raise BgiV1Error("malformed", "code target lands in an operand",
                                     target_sources[address], opcode)
            operations.append(Instruction(pos, opcode, operands))
            pos = end
            if opcode in _TERMINALS:
                terminals.append({"offset": end - 4, "opcode": opcode,
                                  "largest_target": largest, "eligible": end - base > largest})
                if end - base > largest:
                    if any(t["address"] not in starts for t in targets):
                        raise BgiV1Error("malformed", "target is not an instruction start", end - 4, opcode)
                    # No-reference code is proved only by an exact EOF terminal.
                    if not references and end != len(data):
                        continue
                    if candidate is not None:
                        raise BgiV1Error("boundary_unknown", "multiple valid terminal/pool boundaries",
                                         end - 4, opcode)
                    candidate = (tuple(operations), tuple(references), list(targets), list(terminals), end)
        except BgiV1Error as exc:
            if candidate is None or exc.code in ("boundary_unknown", "budget_exceeded"):
                raise
            # A zero-high-word opcode outside the chosen layout, or a failed decode
            # after additional complete instructions, could be unaccounted
            # code following an early terminal. Do not hide it as opaque pool.
            # This is an extra rejection rule, NEVER an operand-width guess.
            if exc.code == "unsupported_opcode" and opcode is not None and opcode <= 0xFFFF:
                raise
            if (opcode is not None and operand_template(opcode, opcode_layout) is not None
                    or len(operations) > len(candidate[0])):
                raise BgiV1Error("boundary_unknown", "unproven code-like continuation after terminal",
                                 exc.offset, exc.opcode) from exc
            probe_stop = {"offset": exc.offset, "reason": "not_a_supported_continuation",
                          "diagnostic": exc.code, "opcode": exc.opcode}
            break
    if candidate is None:
        raise BgiV1Error("boundary_unknown", "no terminal beyond all targets with a valid pool boundary", pos)
    if len(operations) > len(candidate[0]):
        raise BgiV1Error("boundary_unknown", "unterminated code-like continuation after terminal", pos)
    operations, references, targets, terminals, end = candidate
    boundary = {"method": "unique-terminal-target-pool-v1", "code_base": base,
                "opcode_layout": opcode_layout,
                "stack_extension_opcodes": sorted({op.opcode for op in operations
                                                    if op.opcode not in OPERAND_TEMPLATES}),
                "code_end": end, "code_length": end - base, "header": header,
                "targets": targets, "terminals": terminals,
                "referenced_pool_min": min((ref.address for ref in references), default=None),
                "referenced_ranges": [[ref.address, ref.end] for ref in references],
                "all_targets_are_instruction_starts": True,
                "all_strings_after_code": True, "alternative_probe": probe_stop}
    return operations, references, boundary


def _classify(operations: tuple[Instruction, ...], references: tuple[Reference, ...],
              base: int, targets: list[dict], profile: str) -> tuple[tuple[Reference, ...], tuple[Event, ...]]:
    if _PROFILE_MODES[profile][1] == 'literal':
        return _classify_strict(operations, references, base, targets)
    if _PROFILE_MODES[profile][1] == 'vntextpatch':
        return _classify_vntextpatch(operations, references, base)
    raise BgiV1Error("malformed", "unknown BGI event profile", 0)


def _classify_vntextpatch(operations: tuple[Instruction, ...],
                          references: tuple[Reference, ...],
                          base: int) -> tuple[tuple[Reference, ...], tuple[Event, ...]]:
    """Reproduce VNTextPatch EthornellV1Disassembler event grouping exactly.

    The only pending-argument model is a stack of 0003 string operands. A
    message takes the top operand as its body and, if the stack is still
    non-empty, the next one as its speaker. A user function call discards its
    callee; when that callee literally reads _SelectEx/_SelectExtend every
    remaining operand becomes an option. No value/taint tracking is performed,
    so a stored or computed value can be assigned a text role: that is the
    documented weakness of this profile.
    """
    refs = {ref.operand: ref for ref in references}
    roles, events, stack = {}, [], []
    choice_group = 0
    for inst in operations:
        opcode = inst.opcode
        if opcode in _OLD_DIALECT:
            raise BgiV1Error("semantic_unsupported", "old message/ruby/flush dialect is not enabled",
                             inst.offset, opcode, relative_offset=inst.offset - base)
        if opcode == 0x0003:
            stack.append(inst.offset + 4)
        elif opcode in _INTERNAL_FLUSH or opcode in _TERMINALS:
            stack.clear()
        elif opcode in (0x0140, 0x0143, 0x0160, 0x001C):
            is_choice = opcode == 0x0160
            if opcode == 0x001C:
                # Upstream returns without popping when nothing is pending.
                if not stack:
                    continue
                function = stack.pop()  # The callee name stays Internal.
                is_choice = refs[function].text in _CHOICE_FUNCTIONS
                if not is_choice:
                    continue  # Arguments of an unknown callee are not text events.
            if is_choice:
                for index, operand in enumerate(stack):
                    roles[operand] = "choice"
                    events.append(Event("choice", inst.offset, operand, None, "absent",
                                        choice_group, index))
                if stack:
                    # Upstream emits nothing for an option-less choice screen.
                    choice_group += 1
                stack.clear()
            else:
                if not stack:
                    # Upstream would throw here; the stack model has diverged.
                    raise BgiV1Error("semantic_unsupported",
                                     "message with an empty pending-value stack",
                                     inst.offset, opcode, relative_offset=inst.offset - base)
                message = stack.pop()
                name = stack.pop() if stack else None
                if name is not None and not refs[name].text:
                    name = None  # Empty speaker is Internal upstream, not a name slot.
                if name is not None:
                    roles[name] = "name"
                if refs[message].text:
                    roles[message] = "message"
                events.append(Event("message", inst.offset, message, name,
                                    "static" if name is not None else "absent"))
    typed = tuple(Reference(ref.operand, ref.address, ref.end,
                            roles.get(ref.operand, "internal"), ref.text)
                  for ref in references)
    return typed, tuple(events)


def _classify_strict(operations: tuple[Instruction, ...], references: tuple[Reference, ...],
                     base: int, targets: list[dict]) -> tuple[tuple[Reference, ...], tuple[Event, ...]]:
    refs = {ref.operand: ref for ref in references}
    roles, events, stack = {}, [], []
    tainted = False
    choice_group = 0
    entries = {t["address"] + base for t in targets}
    for instruction_index, inst in enumerate(operations):
        opcode = inst.opcode
        if inst.offset in entries and stack:
            # Do not merge an incoming path with pending fall-through literals.
            tainted = True
        if opcode in _OLD_DIALECT:
            raise BgiV1Error("semantic_unsupported", "old message/ruby/flush dialect is not enabled",
                             inst.offset, opcode, relative_offset=inst.offset - base)
        if opcode == 0x0003:
            stack.append(inst.offset + 4)
        elif opcode in (0x0000, 0x0001):
            pass  # Literal integer/code-address pushes do not consume strings.
        elif opcode in _INTERNAL_FLUSH or opcode in _TERMINALS:
            stack.clear()
            tainted = False
        elif opcode in (0x0140, 0x0143, 0x0160, 0x001C):
            is_choice = opcode == 0x0160
            if opcode == 0x001C:
                if not stack:
                    tainted = True
                    continue
                function = stack[-1]
                literal_callee = (instruction_index > 0 and inst.offset not in entries
                                  and operations[instruction_index - 1].opcode == 0x0003)
                is_choice = refs[function].text in ("_SelectEx", "_SelectExtend")
                # A directly supplied non-choice callee need not evaluate its
                # numeric arguments just to keep all argument strings Internal.
                if not is_choice and (not tainted or literal_callee):
                    stack.clear()
                    tainted = True  # A return value is still NOT a known name.
                    continue
            # Two fresh, adjacent literal arguments prove both name and body
            # even if unrelated numeric work preceded them. A single literal
            # cannot establish narration in the presence of a dynamic name.
            literal_pair = (opcode in (0x0140, 0x0143) and len(stack) == 2
                            and instruction_index >= 2
                            and all(op.opcode == 0x0003 for op in
                                    operations[instruction_index - 2:instruction_index])
                            and not any(op.offset in entries for op in
                                        operations[instruction_index - 1:instruction_index + 1]))
            if tainted and not literal_pair:
                raise BgiV1Error("semantic_unsupported", "unresolved VM values may participate in text event",
                                 inst.offset, opcode, relative_offset=inst.offset - base)
            if opcode == 0x001C:
                stack.pop()  # The verified choice function name remains Internal.
            if is_choice:
                if not stack:
                    raise BgiV1Error("semantic_unsupported", "choice has no proven literal options", inst.offset, opcode)
                for index, operand in enumerate(stack):
                    roles[operand] = "choice"
                    events.append(Event("choice", inst.offset, operand, None, "absent", choice_group, index))
                choice_group += 1
            else:
                if not 1 <= len(stack) <= 2:
                    raise BgiV1Error("semantic_unsupported", "message needs one or two unambiguous literals",
                                     inst.offset, opcode)
                message = stack[-1]
                name = stack[0] if len(stack) == 2 and refs[stack[0]].text else None
                if name is not None:
                    roles[name] = "name"
                if refs[message].text:
                    roles[message] = "message"
                events.append(Event("message", inst.offset, message, name,
                                    "static" if name is not None else "absent"))
            stack.clear()
            tainted = False
        else:
            # Width knowledge is NOT stack-effect knowledge. In particular,
            # 0002/load/arithmetic must never turn a dynamic name into narration
            # or cause a stale literal to be exported as its replacement.
            tainted = True
    typed = tuple(Reference(ref.operand, ref.address, ref.end,
                            roles.get(ref.operand, "internal"), ref.text) for ref in references)
    return typed, tuple(events)


def scan_v1(data: bytes, *, encoding: str = "cp932", profile: str = PROFILE,
            max_code_size: int = 64 << 20,
            max_operations: int = 1000000, max_string_size: int = 1 << 20,
            max_text_bytes: int = 64 << 20) -> Analysis:
    """Analyze headered Ver1 using a versioned layout and event policy.

    No code_length parameter is accepted. This is bounded static evidence,
    not a VM emulator: competing boundaries fail immediately. Unresolved value
    roles retain structural evidence with semantic_diagnostics; export/patch
    then reject the entire member, never a partial JSON subset. `profile`
    selects the default sparse stack layout with literal-event analysis,
    the weaker PROFILE_VNTEXTPATCH grouping, or a frozen explicit profile.
    All profiles validate boundaries, targets and string references.
    """
    for value, name in ((max_code_size, "max_code_size"), (max_operations, "max_operations"),
                        (max_string_size, "max_string_size"), (max_text_bytes, "max_text_bytes")):
        _limit(value, name)
    if profile not in PROFILES:
        raise BgiV1Error("malformed", "unknown BGI event profile")
    if not isinstance(data, bytes):
        raise BgiV1Error("malformed", "data must be bytes")
    base, header = _header(data, encoding, max_string_size)
    operations, references, boundary = _structure(data, base, header, encoding,
                                                  max_code_size, max_operations, max_string_size,
                                                  max_text_bytes,
                                                  opcode_layout=_PROFILE_MODES[profile][0])
    try:
        references, events = _classify(operations, references, base, boundary["targets"], profile)
    except BgiV1Error as exc:
        if exc.code != "semantic_unsupported":
            raise
        diagnostic = {"code": exc.code, "message": exc.message, "offset": exc.offset,
                      "opcode": exc.opcode, "relative_offset": exc.relative_offset}
        # The original structural refs are still Internal. Do not expose earlier
        # successful events as a misleading partially translatable member.
        return Analysis(base, boundary["code_length"], references, (), profile,
                        boundary, operations, (diagnostic,))
    return Analysis(base, boundary["code_length"], references, events, profile, boundary, operations)


def export_v1(analysis: Analysis) -> tuple[list[dict], list[dict], list[str]]:
    """Export ordered event-local rows, or propagate the first semantic blocker."""
    if analysis.semantic_diagnostics:
        diagnostic = analysis.semantic_diagnostics[0]
        raise BgiV1Error(diagnostic["code"], diagnostic["message"], diagnostic["offset"],
                         diagnostic["opcode"], relative_offset=diagnostic.get("relative_offset"))
    refs = {ref.operand: ref for ref in analysis.references}
    rows, locators, policies = [], [], []
    for event in analysis.events:
        message = refs[event.message_operand]
        if message.kind == "internal":
            continue  # Empty message is an internal operation, not a text row.
        row = {}
        if event.name_operand is not None:
            row["name"] = refs[event.name_operand].text
        row["message"] = message.text
        rows.append(row)
        locators.append({"kind": event.kind, "instruction_offset": event.instruction_offset,
                         "message_operand": event.message_operand, "name_operand": event.name_operand,
                         "speaker_status": event.speaker_status, "choice_group": event.choice_group,
                         "choice_index": event.choice_index})
        policies.append("writable" if event.name_operand is not None else "absent")
    return rows, locators, policies


def _relative_address(absolute: int, base: int, operand: int) -> int:
    relative = absolute - base
    if not 0 <= relative <= 0xFFFFFFFF:
        raise BgiV1Error("overflow", "BGI u32 code-relative string address overflow", operand)
    return relative


def patch_v1(data: bytes, replacements: dict[int, str], *, encoding: str = "cp932",
             profile: str = PROFILE, max_output_size: int = 128 << 20) -> bytes:
    """Append changed strings and repoint only proven translatable operands.

    Old bytes (including shared/suffix strings and opaque tails) are never
    rewritten. Reparse the output from its header, not a cached code_length.
    Emptying a nonempty message/name would change event semantics and is refused.
    The same `profile` is used for the input analysis and the output reparse, so
    a heuristic row can never be written back under the strict profile.
    """
    _limit(max_output_size, "max_output_size")
    if len(data) > max_output_size:
        raise BgiV1Error("budget_exceeded", "input exceeds output-size limit")
    analysis = scan_v1(data, encoding=encoding, profile=profile)
    if not isinstance(replacements, dict):
        raise BgiV1Error("malformed", "replacements must be a dictionary")
    refs = {ref.operand: ref for ref in analysis.references}
    _, locators, _ = export_v1(analysis)
    allowed = {loc[role] for loc in locators for role in ("message_operand", "name_operand")
               if loc[role] is not None}
    for operand in replacements:
        if type(operand) is not int or operand not in allowed:
            raise BgiV1Error("semantic_unsupported", "unknown/internal/unexported BGI operand",
                             operand if type(operand) is int else None)
    out = bytearray(data)
    expected = {}
    for operand, text in sorted(replacements.items()):
        if not isinstance(text, str) or "\0" in text:
            raise BgiV1Error("malformed", "replacement must be a NUL-free string", operand)
        try:
            raw = text.encode(encoding, errors="strict")
        except (UnicodeError, LookupError) as exc:
            raise BgiV1Error("encoding_error", f"replacement is not representable in {encoding}", operand) from exc
        if b"\0" in raw:
            raise BgiV1Error("encoding_error", "encoding is incompatible with NUL strings", operand)
        if not text and refs[operand].kind in ("name", "message"):
            raise BgiV1Error("semantic_unsupported", "empty text changes message/name role", operand)
        if text == refs[operand].text:
            continue
        relative = _relative_address(len(out), analysis.code_base, operand)
        if len(raw) + 1 > max_output_size - len(out):
            raise BgiV1Error("budget_exceeded", "appended strings exceed output-size limit", operand)
        struct.pack_into("<I", out, operand, relative)
        out.extend(raw)
        out.append(0)
        expected[operand] = (analysis.code_base + relative, text)
    result = bytes(out)
    # Always invoke the same automatic scanner, including for an identity writer
    # pass. Appending must not conceal a different or ambiguous code boundary.
    after = scan_v1(result, encoding=encoding, profile=profile)
    export_v1(after)  # Preserve structured diagnostics if reanalysis is blocked.
    if (after.code_base != analysis.code_base or after.code_length != analysis.code_length
            or after.events != analysis.events or len(after.references) != len(analysis.references)):
        raise BgiV1Error("boundary_unknown", "writer changed code boundary or event topology")
    for before, new in zip(analysis.references, after.references):
        address, text = expected.get(before.operand, (before.address, before.text))
        if (new.operand, new.address, new.kind, new.text) != (before.operand, address, before.kind, text):
            raise BgiV1Error("semantic_unsupported", "writer reference verification failed", before.operand)
    return result
