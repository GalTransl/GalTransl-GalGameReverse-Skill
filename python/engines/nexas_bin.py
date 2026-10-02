# SPDX-License-Identifier: GPL-3.0-only
"""NeXAS extras/count/pairs/string-pool BIN, tested on Aikiss3.

Layout/operand reference: SExtractor 8d8d976fd04ae54e7c677705af937273d04a376a,
tools/Nexas/Script_disassembler.py and Script_assembler_re.py (GPLv3;
upstream credits masagrator/NXGameScripts). No ASM evaluation or renumbering.
"""
from dataclasses import dataclass
import re
import struct

from ..common.binary import FormatError, Reader
from ..common.contract import make_manifest, validate_translation

PROFILE = "aikiss3-extras-v1"
KNOWN_OPCODES = {0, 4, 5, 6, 7, 8, 9, 10, 11, 14, 16, 17, 21, 23, 24,
                 25, 26, 27, 28, 29, 34, 44, 49, 65, 66, 67, 71, 72}
# The scoped profile accepts the syntax actually observed in Aikiss3.
TOKEN = re.compile(r"@(?:v[0-9]{8}|t[0-9]{4}|h[A-Za-z0-9_]*|[mi][0-9]{2}|[nkd])")


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


def controls(text: str) -> list[str]:
    if any(ord(c) < 32 for c in text):
        raise FormatError("use NeXAS @n, not literal control characters")
    tokens = []
    pos = 0
    while (pos := text.find("@", pos)) >= 0:
        match = TOKEN.match(text, pos)
        if not match:
            raise FormatError(f"unknown NeXAS text control at character {pos}")
        tokens.append(match.group())
        pos = match.end()
    return tokens


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


def records(script: Script) -> tuple[list[dict], list[dict]]:
    """Known call-site semantics, never a Japanese-string/resource-name heuristic.

    Special-text assignments are separate occurrences (including preload copies).
    Custom message concatenation retains its control-only suffix in the binary.
    Continuations have no guessed speaker. Repeated text is not deduplicated.
    """
    unknown = {op for op, _ in script.raw_commands} - KNOWN_OPCODES
    if unknown:
        raise FormatError(f"opcode outside {PROFILE}: {sorted(unknown)}")
    rows, locators = [], []
    commands = script.commands

    def add(command, kind, message, name=None):
        prefix, text = _reference(script, message)
        # Empty assignments and control-only text are executable, not translations.
        controls(text)
        if not TOKEN.sub("", text).strip():
            return
        row = {"message": text}
        locator = {"kind": kind, "command": command.index, "message_prefix": prefix}
        if name is not None:
            name_prefix, name_text = _reference(script, name)
            if name_text:
                controls(name_text)
                row["name"] = name_text
                locator["name_prefix"] = name_prefix
        rows.append(row)
        locators.append(locator)

    for j, command in enumerate(commands):
        if _is(command, 7, 0x4006F, 0):
            if j >= 2 and all(_is(c, 5, 1, 1) for c in commands[j-2:j]):
                add(command, "message", commands[j-1], commands[j-2])
            else:
                # Aikiss3: name + (effect + text) + control suffix, then PUSH_MESSAGE.
                pattern = [(5, 1, 1), (4, 0, 1), (6, 1, 1), (9, 1, 0),
                           (4, 0, 0), (6, 1, 1), (9, 1, 0), (5, 1, 0)]
                seq = commands[j-8:j] if j >= 8 else ()
                if len(seq) != 8 or not all(_is(c, *p) for c, p in zip(seq, pattern)):
                    raise FormatError(f"unrecognized PUSH_MESSAGE operands at {command.index}")
                for c in (seq[1], seq[5]):
                    _, control_text = _reference(script, c)
                    controls(control_text)
                    if TOKEN.sub("", control_text):
                        raise FormatError("custom message effect/suffix contains unhandled text")
                add(command, "custom-message", seq[2], seq[0])
        elif _is(command, 7, 0x10071, 0):
            if j < 1 or not _is(commands[j-1], 5, 1, 1):
                raise FormatError("unrecognized message continuation")
            add(command, "continuation", commands[j-1])
        elif _is(command, 7, 0x30066, 0):
            seq = commands[j-3:j] if j >= 3 else ()
            if len(seq) != 3 or not all(_is(c, 5, a, 1) for c, a in zip(seq, (0, 1, 0))):
                raise FormatError("unrecognized selection operands")
            add(command, "choice", seq[1])
        elif command.opcode == 14 and command.argument >> 24 == 0x80:
            add(command, "special-text", command)
        elif command.opcode == 7 and command.argument in (0x20023, 0x20075, 0x20015, 0x10017):
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
                raise FormatError("unrecognized notification operands")
    return rows, locators


def export(data: bytes, *, source_name: str) -> tuple[list[dict], dict]:
    script = parse(data)
    rows, locators = records(script)
    manifest = make_manifest(
        engine="nexas", variant=PROFILE, reference="python/engines/nexas_bin.py",
        sources={source_name: data}, rows=rows, locators=locators, encoding="cp932",
        name_policies=["writable" if "name" in row else "absent" for row in rows],
        protected_tokens=[list(dict.fromkeys(controls(row["message"]))) for row in rows])
    return rows, manifest


def inject(data: bytes, original_rows: list[dict], manifest: dict, translated_rows: list[dict],
           *, source_name: str) -> bytes:
    fresh_rows, fresh_manifest = export(data, source_name=source_name)
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
            if controls(before[field]) != controls(after[field]):
                raise FormatError(f"NeXAS {field} controls changed in order or content")
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
    reread, _ = records(parsed)
    if reread != translated or parsed.trailer != script.trailer:
        raise FormatError("NeXAS writer verification failed")
    expected = list(script.raw_commands)
    for n, prefix in enumerate(sorted(changes), len(script.raw_strings)):
        expected[prefix] = (0, n)
    if parsed.raw_commands != tuple(expected) or parsed.raw_strings[:len(script.raw_strings)] != script.raw_strings:
        raise FormatError("NeXAS nontext structure changed")
    return result
