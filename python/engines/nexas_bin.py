# SPDX-License-Identifier: GPL-3.0-only
"""NeXAS extras/count/pairs/string-pool BIN with explicit FUNC-id dialects.

Layout/operand reference: SExtractor 8d8d976fd04ae54e7c677705af937273d04a376a,
tools/Nexas/Script_disassembler.py and Script_assembler_re.py (GPLv3;
upstream credits masagrator/NXGameScripts). No ASM evaluation or renumbering.
"""
from dataclasses import dataclass
import re
import struct

from ..common.binary import FormatError, Reader
from ..common.contract import make_manifest, validate_translation
from ..common.line_layout import drops_only_line_breaks

PROFILE = "aikiss3-extras-v1"
KNOWN_OPCODES = {0, 4, 5, 6, 7, 8, 9, 10, 11, 14, 16, 17, 21, 23, 24,
                 25, 26, 27, 28, 29, 34, 44, 49, 65, 66, 67, 71, 72}
# The scoped profile accepts the syntax actually observed in its scripts.
# Voice ids are 8 digits with an optional letter or "_letter" suffix, exactly
# the Voice.pac member stems; an id followed by another ASCII letter, digit
# or "_" has no evidenced boundary and is refused.
TOKEN = re.compile(r"@(?:v[0-9]{8}(?:_?[A-Za-z])?(?![0-9A-Za-z_])|t[0-9]{4}|h[A-Za-z0-9_]*"
                   r"|[mi][0-9]{2}|[nkd])")
# Operand-less binary operators: in every observed site they take no argument
# prefix, carry argument 0 and directly follow the right-operand opcode 6
# (15/22 are then consumed by conditional jump 66 like 16/21/23-26). Each
# command is a fixed 8-byte pair, so admitting them guesses no length; the
# structural shape is still rechecked per site.
STACK_OPERATORS = frozenset({12, 15, 22, 63})


@dataclass(frozen=True)
class Dialect:
    """FUNC ids and control grammar of one NeXAS script generation.

    Selected from message call-site evidence in the scripts (never from a game
    name); see select_dialect().
    """
    profile: str
    message: int        # FUNC: name, message (two single-string arguments)
    continuation: int   # FUNC: one single-string argument, no speaker
    choice: int         # FUNC: PUSH int, PUSH string, PUSH int
    notifications: frozenset
    opcodes: frozenset
    token: re.Pattern
    ruby: bool = False  # @r<base>@<reading>@

    def handled_funcs(self):
        return {self.message, self.continuation, self.choice, *self.notifications}


DIALECT_EXTRAS = Dialect(
    profile=PROFILE, message=0x4006F, continuation=0x10071, choice=0x30066,
    notifications=frozenset({0x20023, 0x20075, 0x20015, 0x10017}),
    opcodes=frozenset(KNOWN_OPCODES), token=TOKEN)
# Earlier function table: the same call shapes sit at lower FUNC ids. Voice ids
# are 8-9 ASCII letters/digits (Voice.pac stems), @s takes four digits; the
# lookaheads reject any token directly followed by a character that could
# extend it, so an ambiguous boundary is refused instead of guessed.
DIALECT_FUNC69 = Dialect(
    profile="nexas-func40069-v1", message=0x40069, continuation=0x1006A, choice=0x30062,
    notifications=frozenset({0x20023, 0x2006E, 0x20015, 0x10017}),
    opcodes=frozenset(KNOWN_OPCODES | STACK_OPERATORS),
    token=re.compile(r"@(?:v[0-9A-Za-z]{8,9}(?![0-9A-Za-z])|[ts][0-9]{4}(?![0-9])"
                     r"|m[0-9]{2}(?![0-9])|h[A-Za-z0-9_]*|[nkd])"),
    ruby=True)
DIALECTS = {d.profile: d for d in (DIALECT_EXTRAS, DIALECT_FUNC69)}
RUBY = re.compile(r"@r([^@]+)@([^@]+)@")


@dataclass(frozen=True)
class Command:
    index: int
    opcode: int
    argument: int
    prefixes: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class Script:
    source: bytes
    commands_offset: int
    raw_commands: tuple[tuple[int, int], ...]
    commands: tuple[Command, ...]
    strings_count_offset: int
    raw_strings: tuple[bytes, ...]
    strings: tuple[str, ...]
    trailer: bytes


def parse(data: bytes, *, max_bytes: int = 32 << 20, max_commands: int = 1_000_000,
          max_strings: int = 100_000) -> Script:
    if len(data) > max_bytes:
        raise FormatError("NeXAS BIN exceeds budget")
    reader = Reader(data)
    extras = reader.u32()
    if extras > max_commands:
        raise FormatError("NeXAS extra table exceeds budget")
    reader.take(extras * 8)
    count = reader.u32()
    if count > max_commands:
        raise FormatError("NeXAS command table exceeds budget")
    start = reader.pos
    raw_commands = tuple(struct.iter_unpack("<II", reader.take(count * 8)))
    commands = []
    prefixes = []
    for i, (op, arg) in enumerate(raw_commands):
        if op == 0:
            prefixes.append((i, arg))
        else:
            commands.append(Command(i, op, arg, tuple(prefixes)))
            prefixes.clear()
    if prefixes:
        raise FormatError("orphan NeXAS argument prefixes")
    strings_count_offset = reader.pos
    count = reader.u32()
    if count > max_strings:
        raise FormatError("NeXAS string table exceeds budget")
    raw_strings = tuple(reader.terminated(max_bytes=1 << 20) for _ in range(count))
    try:
        strings = tuple(s.decode("cp932", errors="strict") for s in raw_strings)
    except UnicodeError as exc:
        raise FormatError("NeXAS string table is not CP932") from exc
    return Script(data, start, raw_commands, tuple(commands), strings_count_offset,
                  raw_strings, strings, data[reader.pos:])


def controls(text: str, dialect: Dialect = DIALECT_EXTRAS) -> list[str]:
    """Ordered control tokens. A ruby span yields "@r", "@", "@" (its base and
    reading stay translatable text, the three markers are fixed)."""
    if any(ord(c) < 32 for c in text):
        raise FormatError("use NeXAS @n, not literal control characters")
    tokens = []
    pos = 0
    while (pos := text.find("@", pos)) >= 0:
        match = dialect.token.match(text, pos)
        if match:
            tokens.append(match.group())
            pos = match.end()
            continue
        ruby = RUBY.match(text, pos) if dialect.ruby else None
        if ruby:
            if dialect.token.match(text, ruby.end() - 1):
                # "@r..@..@n" could be a closing marker or a control; refuse.
                raise FormatError(f"ambiguous NeXAS ruby end {text[ruby.end() - 1:ruby.end() + 4]!r} "
                                  f"at character {ruby.end() - 1}")
            tokens.extend(("@r", "@", "@"))
            pos = ruby.end()
            continue
        raise FormatError(f"unknown NeXAS text control {text[pos:pos + 12]!r} at character {pos}"
                          f" ({dialect.profile})")
    return tokens


def _plain(text: str, dialect: Dialect) -> str:
    """Text with control markers removed (ruby base/reading are kept)."""
    text = dialect.token.sub("", text)
    return RUBY.sub(r"\1\2", text) if dialect.ruby else text


def _protected(tokens: list[str]) -> list[str]:
    return list(dict.fromkeys(token for token in tokens if token not in ("@n", "@")))


def _is(command: Command, op: int, arg: int, count: int | None = None) -> bool:
    return (command.opcode == op and command.argument == arg
            and (count is None or len(command.prefixes) == count))


def _reference(script: Script, command: Command) -> tuple[int, str]:
    if len(command.prefixes) != 1:
        raise FormatError(f"expected one string reference at command {command.index}")
    index, sid = command.prefixes[0]
    if sid >= len(script.strings):
        raise FormatError(f"string index out of range at command {command.index}")
    return index, script.strings[sid]


def _string_run(commands, j) -> int:
    """Number of single-string pushes (op 5, arg 1, one prefix) directly before j."""
    k = j - 1
    while k >= 0 and _is(commands[k], 5, 1, 1):
        k -= 1
    return j - 1 - k


def message_shaped_calls(script: Script, dialect: Dialect) -> dict[int, int]:
    """FUNC ids outside the dialect called with message-shaped operands.

    A call directly preceded by two single-string pushes is how both known
    generations pass (name, message). Such a call to an id the dialect does
    not handle means the selected FUNC table does not fit this script.
    """
    found = {}
    handled = dialect.handled_funcs()
    for j, command in enumerate(script.commands):
        if command.opcode == 7 and command.argument not in handled and _string_run(script.commands, j) >= 2:
            found[command.argument] = found.get(command.argument, 0) + 1
    return found


def message_sites(script: Script, dialect: Dialect) -> int:
    """Message calls of this dialect with the (name, message) operand shape."""
    commands = script.commands
    return sum(1 for j, c in enumerate(commands)
               if _is(c, 7, dialect.message, 0) and _string_run(commands, j) >= 2)


def select_dialect(scripts) -> Dialect:
    """Pick the FUNC table from message call-site evidence across all scripts.

    Exactly one dialect may have (name, message)-shaped calls at its message id;
    none or several is refused rather than exported near-empty.
    """
    scripts = list(scripts)
    evidence = {name: sum(message_sites(s, d) for s in scripts) for name, d in DIALECTS.items()}
    matched = [name for name, count in evidence.items() if count]
    if len(matched) == 1:
        return DIALECTS[matched[0]]
    shaped = {}
    for s in scripts:
        for func, count in message_shaped_calls(s, DIALECT_EXTRAS).items():
            shaped[func] = shaped.get(func, 0) + count
    candidates = ", ".join(f"FUNC {func:#x} x{count}" for func, count in
                           sorted(shaped.items(), key=lambda kv: -kv[1])[:5]) or "none"
    raise FormatError(f"no single NeXAS FUNC dialect fits: message sites {evidence}; "
                      f"(name, message)-shaped calls: {candidates}")


def records(script: Script, dialect: Dialect = DIALECT_EXTRAS) -> tuple[list[dict], list[dict]]:
    """Known call-site semantics, never a Japanese-string/resource-name heuristic.

    Special-text assignments are separate occurrences (including preload copies).
    Custom message concatenation retains its control-only suffix in the binary.
    Continuations have no guessed speaker. Repeated text is not deduplicated.
    """
    unknown = {op for op, _ in script.raw_commands} - dialect.opcodes
    if unknown:
        raise FormatError(f"opcode outside {dialect.profile}: {sorted(unknown)}")
    commands = script.commands
    for j, command in enumerate(commands):
        if command.opcode in STACK_OPERATORS and (
                command.argument or command.prefixes or j == 0 or commands[j - 1].opcode != 6):
            raise FormatError(f"operator opcode {command.opcode} at command {command.index} "
                              "is not an operand-less operator after opcode 6")
    shaped = message_shaped_calls(script, dialect)
    if shaped:
        func, count = max(shaped.items(), key=lambda kv: kv[1])
        raise FormatError(f"(name, message)-shaped call to FUNC {func:#x} (x{count}) "
                          f"outside {dialect.profile}")
    rows, locators = [], []

    def add(command, kind, message, name=None):
        prefix, text = _reference(script, message)
        # Empty assignments and control-only text are executable, not translations.
        try:
            controls(text, dialect)
        except FormatError as exc:
            raise FormatError(f"{exc}; string operand of command {prefix} for {kind} "
                              f"at command {command.index}") from None
        if not _plain(text, dialect).strip():
            return
        row = {"message": text}
        locator = {"kind": kind, "command": command.index, "message_prefix": prefix}
        if name is not None:
            name_prefix, name_text = _reference(script, name)
            if name_text:
                try:
                    controls(name_text, dialect)
                except FormatError as exc:
                    raise FormatError(f"{exc}; name operand of command {name_prefix} "
                                      f"at command {command.index}") from None
                row["name"] = name_text
                locator["name_prefix"] = name_prefix
        rows.append(row)
        locators.append(locator)

    for j, command in enumerate(commands):
        if _is(command, 7, dialect.message, 0):
            if j >= 2 and all(_is(c, 5, 1, 1) for c in commands[j-2:j]):
                add(command, "message", commands[j-1], commands[j-2])
            else:
                # Custom message: name + (effect + text) + control suffix, then PUSH_MESSAGE.
                pattern = [(5, 1, 1), (4, 0, 1), (6, 1, 1), (9, 1, 0),
                           (4, 0, 0), (6, 1, 1), (9, 1, 0), (5, 1, 0)]
                seq = commands[j-8:j] if j >= 8 else ()
                if len(seq) != 8 or not all(_is(c, *p) for c, p in zip(seq, pattern)):
                    raise FormatError(f"unrecognized PUSH_MESSAGE operands at {command.index}")
                for c in (seq[1], seq[5]):
                    _, control_text = _reference(script, c)
                    controls(control_text, dialect)
                    if _plain(control_text, dialect):
                        raise FormatError("custom message effect/suffix contains unhandled text "
                                          f"at command {command.index}")
                add(command, "custom-message", seq[2], seq[0])
        elif _is(command, 7, dialect.continuation, 0):
            if j < 1 or not _is(commands[j-1], 5, 1, 1):
                raise FormatError(f"unrecognized message continuation at {command.index}")
            add(command, "continuation", commands[j-1])
        elif _is(command, 7, dialect.choice, 0):
            seq = commands[j-3:j] if j >= 3 else ()
            if len(seq) != 3 or not all(_is(c, 5, a, 1) for c, a in zip(seq, (0, 1, 0))):
                raise FormatError(f"unrecognized selection operands at {command.index}")
            add(command, "choice", seq[1])
        elif command.opcode == 14 and command.argument >> 24 == 0x80:
            add(command, "special-text", command)
        elif command.opcode == 7 and command.argument in dialect.notifications:
            # Small UI notifications with one explicit string argument; preserve other args.
            args = []
            k = j - 1
            while k >= 0 and commands[k].opcode == 5:
                if _is(commands[k], 5, 1, 1):
                    args.append(commands[k])
                k -= 1
            if len(args) == 1:
                add(command, "notification", args[0])
            else:
                raise FormatError(f"unrecognized notification operands at {command.index}")
    return rows, locators


def dialect_of(manifest: dict) -> Dialect:
    engine = manifest.get("engine") if isinstance(manifest, dict) else None
    dialect = DIALECTS.get(engine.get("variant") if isinstance(engine, dict) else None)
    if dialect is None:
        raise FormatError("NeXAS manifest names an unknown dialect")
    return dialect


def export(data: bytes, *, source_name: str, dialect: Dialect = DIALECT_EXTRAS) -> tuple[list[dict], dict]:
    script = parse(data)
    rows, locators = records(script, dialect)
    manifest = make_manifest(
        engine="nexas", variant=dialect.profile, reference="python/engines/nexas_bin.py",
        sources={source_name: data}, rows=rows, locators=locators, encoding="cp932",
        name_policies=["writable" if "name" in row else "absent" for row in rows],
        protected_tokens=[_protected(controls(row["message"], dialect)) for row in rows])
    return rows, manifest


def inject(data: bytes, original_rows: list[dict], manifest: dict, translated_rows: list[dict],
           *, source_name: str) -> bytes:
    dialect = dialect_of(manifest)
    fresh_rows, fresh_manifest = export(data, source_name=source_name, dialect=dialect)
    if fresh_rows != original_rows or fresh_manifest != manifest:
        raise FormatError("NeXAS manifest or source export no longer matches the parser")
    translated = validate_translation(manifest, {source_name: data}, original_rows, translated_rows)
    script = parse(data)
    prefix_data = bytearray(data[:script.strings_count_offset])
    strings = list(script.raw_strings)
    changes = {}
    for before, after, record in zip(original_rows, translated, manifest["records"]):
        for field in ("message", "name"):
            if field not in before:
                continue
            if not drops_only_line_breaks(controls(before[field], dialect), controls(after[field], dialect),
                                          lambda token: token == "@n"):
                raise FormatError(f"NeXAS {field} controls changed or line breaks added/moved")
            if before[field] == after[field]:
                continue
            raw = after[field].encode("cp932", errors="strict")
            if raw.decode("cp932") != after[field]:
                raise FormatError("NeXAS translation is not losslessly representable in CP932")
            if len(raw) > 1 << 20:
                raise FormatError("NeXAS translation string exceeds budget")
            prefix = record["locator"][f"{field}_prefix"]
            if prefix in changes and changes[prefix] != raw:
                raise FormatError("conflicting translations for one string operand")
            changes[prefix] = raw
    # Clone changed references, preserving original shared resource/string slots.
    for prefix, raw in sorted(changes.items()):
        if script.raw_commands[prefix][0] != 0:
            raise FormatError("locator does not target an argument prefix")
        struct.pack_into("<I", prefix_data, script.commands_offset + prefix * 8 + 4, len(strings))
        strings.append(raw)
    if len(strings) > 100_000:
        raise FormatError("rebuilt NeXAS string table exceeds budget")
    if len(prefix_data) + 4 + sum(len(s) + 1 for s in strings) + len(script.trailer) > 32 << 20:
        raise FormatError("rebuilt NeXAS BIN exceeds budget")
    result = (bytes(prefix_data) + struct.pack("<I", len(strings))
              + b"".join(s + b"\0" for s in strings) + script.trailer)
    parsed = parse(result)
    reread, _ = records(parsed, dialect)
    if reread != translated or parsed.trailer != script.trailer:
        raise FormatError("NeXAS writer verification failed")
    expected = list(script.raw_commands)
    for n, prefix in enumerate(sorted(changes), len(script.raw_strings)):
        expected[prefix] = (0, n)
    if parsed.raw_commands != tuple(expected) or parsed.raw_strings[:len(script.raw_strings)] != script.raw_strings:
        raise FormatError("NeXAS nontext structure changed")
    return result
