"""CatSystem2 CST wrapper, indexed records and append/repoint text slots.
Sources: VNTextPatch-net8, VNTextPatch.Shared/Scripts/CatSystemScript.cs,
Decompress/Load/GetCstStrings (d9c0fab7b72fdcf87d674ef12a84d3829c9188be; MIT);
msg-tool, src/scripts/cat_system/cst.rs, CustomFn::write_patched_string,
CstScript::import_messages (f72716cee88554d40c1cdface2812493b14ca653; GPL-3.0-or-later).
This module uses append/repoint, not dialogue continuation merging.
"""
from dataclasses import dataclass
import re
import struct
import zlib


@dataclass(frozen=True)
class Record:
    index: int
    offset: int
    kind: int
    text: str


@dataclass(frozen=True)
class Scene:
    payload: bytes
    compressed: bool
    index_offset: int
    pool_offset: int
    records: tuple[Record, ...]


@dataclass(frozen=True)
class DialogueExport:
    rows: tuple[dict, ...]
    locators: tuple[dict, ...]
    name_policies: tuple[str, ...]
    protected_tokens: tuple[tuple[str, ...], ...]
    excluded_choices: tuple[int, ...]
    orphan_names: tuple[int, ...]
    name_command_crossings: tuple[tuple[int, tuple[int, ...]], ...]


_CONTROL_TOKEN = re.compile(r"\\(?:[@pn]|[A-Za-z][A-Za-z0-9]*(?:\[[^\]\r\n]*\])?)")
_CHOICE = re.compile(r"^\d+\s+\w+\s+(.+)")
_DYNAMIC_NAME = re.compile(r"^\$[A-Za-z_][A-Za-z0-9_]*(?:\[[^\]\r\n]+\])?$")


def read_cst(data: bytes, encoding: str = "cp932", *,
             max_output: int = 64 * 1024 * 1024) -> Scene:
    """CatScene bytes -> bounded inflated payload and all indexed typed records."""
    if len(data) < 16 or data[:8] != b"CatScene":
        raise ValueError("not CatScene")
    packed, unpacked = struct.unpack_from("<II", data, 8)
    if unpacked > max_output or max_output < 16:
        raise ValueError("CST expansion exceeds limit")
    if packed:
        if packed != len(data) - 16:
            raise ValueError("CST compressed size mismatch")
        decoder = zlib.decompressobj()
        try:
            raw = decoder.decompress(data[16:], unpacked + 1)
        except zlib.error as exc:
            raise ValueError("invalid CST zlib stream") from exc
        if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
            raise ValueError("CST truncated/concatenated/oversized zlib stream")
    else:
        raw = data[16:]
    if len(raw) != unpacked or len(raw) < 16:
        raise ValueError("CST uncompressed size mismatch")
    length, screen_count, index_rel, pool_rel = struct.unpack_from("<IIII", raw)
    index, pool = 16 + index_rel, 16 + pool_rel
    if length != len(raw) - 16 or not 16 <= index <= pool <= len(raw):
        raise ValueError("invalid CST section offsets")
    if (pool - index) % 4:
        raise ValueError("misaligned CST index size")
    # Screen metadata is retained verbatim: no claims about its dialect-specific shape.
    records = []
    for i in range((pool - index) // 4):
        address, = struct.unpack_from("<I", raw, index + 4 * i)
        address += pool
        if address + 3 > len(raw) or raw[address] != 1:
            raise ValueError("invalid CST record pointer/marker")
        kind = raw[address + 1]
        if kind not in {2, 3, 0x20, 0x21, 0x30, 0xF0, 0xF1}:
            raise ValueError("unknown CST record type")
        end = raw.find(b"\0", address + 2)
        if end < 0:
            raise ValueError("unterminated CST record")
        text = raw[address + 2:end].decode(encoding, errors="strict")
        records.append(Record(i, address, kind, text))
    return Scene(raw, bool(packed), index, pool, tuple(records))


def export_cst(value, encoding: str = "cp932") -> DialogueExport:
    """Map raw 0x21/0x20 records to ordered translation rows without merging slots.

    A character record is consumed by the next non-empty message. Dynamic names such as
    ``$str20`` remain context-only. Recognized 0x30 choice captions are separate
    rows; command prefixes are never translated.
    """
    scene = value if isinstance(value, Scene) else read_cst(value, encoding)
    if not isinstance(scene, Scene):
        raise ValueError("export_cst expects CatScene bytes or a Scene")
    rows = []
    locators = []
    policies = []
    protected_tokens = []
    excluded_choices = []
    orphan_names = []
    name_command_crossings = []
    pending_name = None
    intervening_commands = []
    for record in scene.records:
        if record.kind == 0x21:
            if pending_name is not None:
                orphan_names.append(pending_name.index)
            pending_name = record
            intervening_commands = []
            continue
        if record.kind == 0x30:
            if pending_name is not None:
                intervening_commands.append(record.index)
            choice = _CHOICE.fullmatch(record.text)
            if choice is None:
                continue
            text = choice.group(1)
        elif record.kind == 0x20 and record.text:
            choice = None
            text = record.text
        else:
            continue
        if "\r" in text or "\n" in text:
            raise ValueError(f"CST message record {record.index} contains an ambiguous literal line break")
        message = text if choice is not None else text.replace(r"\n", "\n")
        row = {"message": message}
        locator = {"message_record": record.index, "newline": "literal-backslash-n"}
        if choice is not None:
            locator["choice_span"] = (choice.start(1), choice.end(1))
            locator["newline"] = "raw-caption"
            policies.append("absent")
        elif pending_name is None:
            policies.append("absent")
        else:
            row = {"name": pending_name.text, "message": message}
            locator["name_record"] = pending_name.index
            if intervening_commands:
                locator["intervening_command_records"] = tuple(intervening_commands)
                name_command_crossings.append((pending_name.index,
                                               tuple(intervening_commands)))
            policies.append("context" if _DYNAMIC_NAME.fullmatch(pending_name.text)
                            else "writable")
        tokens = set(_CONTROL_TOKEN.findall(message))
        if "\n" in message:
            tokens.add("\n")
        rows.append(row)
        locators.append(locator)
        protected_tokens.append(tuple(sorted(tokens)))
        if choice is None:
            pending_name = None
            intervening_commands = []
    if pending_name is not None:
        orphan_names.append(pending_name.index)
    return DialogueExport(tuple(rows), tuple(locators), tuple(policies),
                          tuple(protected_tokens), tuple(excluded_choices),
                          tuple(orphan_names), tuple(name_command_crossings))


def patch_dialogue(data: bytes, exported: DialogueExport, translated_rows,
                   encoding: str = "cp932") -> bytes:
    """Validate and reparse dialogue and recognized choice-caption replacements."""
    if not isinstance(exported, DialogueExport) or not isinstance(translated_rows, (list, tuple)):
        raise ValueError("invalid CatSystem2 dialogue input")
    if len(translated_rows) != len(exported.rows):
        raise ValueError("CatSystem2 dialogue row count changed")
    if export_cst(data, encoding) != exported:
        raise ValueError("CatSystem2 export differs from reparsed source")
    replacements = {}
    for position, (before, after, locator, policy, tokens) in enumerate(zip(
            exported.rows, translated_rows, exported.locators, exported.name_policies,
            exported.protected_tokens)):
        if not isinstance(after, dict) or set(after) != set(before):
            raise ValueError(f"row {position}: fields changed")
        message = after.get("message")
        if not isinstance(message, str) or "\0" in message or "\r" in message:
            raise ValueError(f"row {position}: invalid message")
        if "choice_span" in locator and "\n" in message:
            raise ValueError(f"row {position}: line break in choice caption")
        for token in tokens:
            if message.count(token) != before["message"].count(token):
                raise ValueError(f"row {position}: protected token changed")
        replacements[locator["message_record"]] = (message if "choice_span" in locator
                                                   else message.replace("\n", r"\n"))
        if policy == "absent":
            if "name" in after:
                raise ValueError(f"row {position}: unexpected name")
        elif policy == "context":
            if after.get("name") != before.get("name"):
                raise ValueError(f"row {position}: context-only name changed")
        elif policy == "writable":
            name = after.get("name")
            if not isinstance(name, str) or "\0" in name:
                raise ValueError(f"row {position}: invalid name")
            replacements[locator["name_record"]] = name
        else:
            raise ValueError(f"row {position}: invalid name policy")
    result = patch_cst(data, replacements, encoding)
    if export_cst(result, encoding).rows != tuple(translated_rows):
        raise ValueError("CatSystem2 reparsed translation differs")
    return result


def patch_cst(data: bytes, replacements: dict[int, str], encoding: str = "cp932") -> bytes:
    """Replace 0x20/0x21 text or a recognized 0x30 caption; append/repoint.

    Choice replacements contain only the caption. Original records,
    aliases, screen metadata and non-text types are left byte-for-byte in the pool.
    """
    scene = read_cst(data, encoding)
    if any(type(k) is not int or not 0 <= k < len(scene.records) for k in replacements):
        raise ValueError("unknown CST record")
    if not replacements:
        return data
    out = bytearray(scene.payload)
    changed = False
    for index, text in sorted(replacements.items()):
        record = scene.records[index]
        choice = _CHOICE.fullmatch(record.text) if record.kind == 0x30 else None
        if record.kind not in (0x20, 0x21) and choice is None:
            raise ValueError("CST slot is not a plain message/name")
        if not isinstance(text, str) or "\0" in text:
            raise ValueError("CST text contains NUL")
        if choice is not None:
            if not text or text != text.lstrip() or any(c in text for c in "\r\n"):
                raise ValueError("invalid CST choice caption")
            text = record.text[:choice.start(1)] + text
        encoded = text.encode(encoding, errors="strict")
        if b"\0" in encoded:
            raise ValueError("encoding is not compatible with CST cstrings")
        if text == record.text:
            continue
        changed = True
        address = len(out) - scene.pool_offset
        if address > 0xFFFFFFFF:
            raise ValueError("CST address overflow")
        struct.pack_into("<I", out, scene.index_offset + 4 * index, address)
        out.extend(bytes((1, record.kind)) + encoded + b"\0")
    if not changed:
        return data
    if len(out) > 64 * 1024 * 1024:
        raise ValueError("CST output exceeds reference limit")
    struct.pack_into("<I", out, 0, len(out) - 16)
    payload = zlib.compress(bytes(out)) if scene.compressed else bytes(out)
    return b"CatScene" + struct.pack("<II", len(payload) if scene.compressed else 0,
                                      len(out)) + payload
