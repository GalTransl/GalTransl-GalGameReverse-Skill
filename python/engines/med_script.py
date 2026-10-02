# SPDX-License-Identifier: GPL-3.0-only
"""MED framed-code/ordinal-string profile; separate from legacy med.py leaf.

Text-boundary formula follows SExtractor extract_MED.py (GPL-3.0).
Frame validation, semantic references and append/retarget writer are new.
Unknown opcodes/shapes stop this profile; they are never guessed/skipped.
"""
from collections import Counter
from dataclasses import dataclass
import re
import struct

from ..common.binary import FormatError
from ..common.contract import make_manifest, validate_rows, validate_translation

PROFILE = "med-framed-ordinal-v1"
MAX_FILE = 8 << 20
# Explicit frame lengths are verified independently of this profile inventory.
# Non-display operands remain opaque and byte-exact; no relocation is needed
# because frames and original string ordinals never move.
SHAPES = {
    0x00: (0,), 0x01: (2,), 0x02: (2,), 0x03: (0,), 0x04: (0,),
    0x06: (6, 9), 0x07: (1,), 0x08: (3,), 0x09: (3,), 0x0a: (8,),
    0x0d: (2,), 0x10: (3,), 0x12: (4, 6, 8), 0x13: (1,), 0x14: (2,),
    0x15: (2,), 0x16: (3,), 0x17: (1,), 0x19: (2,), 0x1a: (3,),
    0x1b: (2,), 0x1c: (2,), 0x1d: (6, 7, 9, 12), 0x1e: (0,),
    0x1f: (0,), 0x20: (0,), 0x21: (9,), 0x22: (13,), 0x25: (2,),
    0x26: (2,), 0x28: (0,), 0x2a: (25,), 0x2c: (2,), 0x2d: (1,),
    0x32: (0,), 0x33: (1,), 0x36: (0,), 0x38: (3,), 0x3b: (8,),
    0x3c: (1,), 0x3d: (10,), 0x4f: (1,), 0x53: (0,), 0x56: (4,),
    0x6a: (2,), 0x6c: (2,), 0x6d: (3,),
}


@dataclass(frozen=True)
class Frame:
    offset: int                 # relative to code start, not whole file
    line: int
    opcode: int
    args: bytes


@dataclass(frozen=True)
class Script:
    header: bytes
    code: bytes
    frames: tuple[Frame, ...]
    targets: tuple[int, ...]
    strings: tuple[bytes, ...]
    labels: tuple[bytes, ...]


def parse(data):
    if not isinstance(data, bytes) or not 17 <= len(data) <= MAX_FILE:
        raise FormatError("MED script size outside budget")
    size, code_size, count, label_count, _ = struct.unpack_from("<IIHHI", data)
    start = 16 + code_size + 2 * label_count
    if size != len(data) - 16 or code_size < 1 or start > len(data):
        raise FormatError("MED size/code/table boundary mismatch")
    code = data[16:16 + code_size]
    frames, pos = [], 0
    while pos < len(code) - 1:
        if pos + 4 > len(code) - 1:
            raise FormatError(f"truncated MED frame at {pos:#x}")
        line, length, opcode = struct.unpack_from("<HBB", code, pos)
        if length < 1 or pos + 3 + length > len(code) - 1:
            raise FormatError(f"invalid MED frame length at {pos:#x}")
        args = code[pos + 4:pos + 3 + length]
        if opcode not in SHAPES or len(args) not in SHAPES[opcode]:
            raise FormatError(f"unsupported MED opcode/shape {opcode:#x} at {pos:#x}: {len(args)} args")
        frames.append(Frame(pos, line, opcode, args))
        pos += 3 + length
    if pos != len(code) - 1 or code[-1] != 0:
        raise FormatError("MED code must end with a single zero sentinel")
    targets = struct.unpack_from(f"<{label_count}H", data, 16 + code_size)
    boundaries = {f.offset for f in frames}
    if any(t not in boundaries for t in targets):
        raise FormatError("MED label target is not a frame boundary")
    pool = data[start:]
    parts = pool.split(b"\0")
    if len(parts) != count + label_count + 1 or parts[-1] != b"":
        raise FormatError("MED primary/label string counts or terminators differ")
    try:
        for raw in parts:
            raw.decode("cp932", "strict")
    except UnicodeError as exc:
        raise FormatError("MED pool is not strict CP932") from exc
    script = Script(data[:16], code, tuple(frames), targets, tuple(parts[:count]), tuple(parts[count:-1]))
    for f in frames:
        if f.opcode in (1, 0x0a, 0x0d, 0x2c):
            idx = struct.unpack_from("<H", f.args)[0]
            if idx == 0xffff and f.opcode in (0x0a, 0x0d):
                continue
            if idx >= count or (f.opcode != 1 and idx >= 0x8000):
                raise FormatError(f"MED display string index out of range at {f.offset:#x}")
    return script


def controls(text):
    # Protect literal engine escapes and possible markup introducers, including
    # tab separators. Unknown backslash commands need a new, evidenced profile.
    if "\0" in text:
        raise FormatError("MED embedded NUL")
    tokens = re.findall(r"\\.|\\$|[\x01-\x1f<>\[\]{}%$@]", text)
    if any(t.startswith("\\") and t != "\\N" for t in tokens):
        raise FormatError("unknown MED text escape")
    return tokens


def records(script):
    rows, locators = [], []
    if rule_definition(script):
        return rows, locators
    speaker = None
    for i, f in enumerate(script.frames):
        if f.opcode == 0x0d:
            idx = struct.unpack_from("<H", f.args)[0]
            speaker = None if idx == 0xffff else f
            if speaker is not None:
                name = script.strings[idx].decode("cp932")
                if not (name.startswith("【") and name.endswith("】")):
                    raise FormatError("MED speaker is not a bracketed display name")
            continue
        if f.opcode in (4, 0x1b, 0x1c, 0x1e, 0x1f):
            speaker = None
        kind = None
        if f.opcode == 1:
            if i + 1 < len(script.frames) and script.frames[i + 1].opcode == 0:
                kind = "message"
        elif f.opcode == 0x0a:
            kind = "choice"
        elif f.opcode == 0x2c:
            kind = "title"
        if kind is None:
            continue
        idx = struct.unpack_from("<H", f.args)[0]
        if idx == 0xffff:
            continue
        text = script.strings[idx].decode("cp932")
        if not text:
            continue
        controls(text)
        row = {}
        name_offset = None
        if kind == "message" and speaker is not None:
            name_idx = struct.unpack_from("<H", speaker.args)[0]
            row["name"] = script.strings[name_idx].decode("cp932")[1:-1]
            controls(row["name"])
            name_offset = speaker.offset
        row["message"] = text
        rows.append(row)
        locators.append({"kind": kind, "frame": f.offset, "line": f.line,
                         "string_id": idx, "name_frame": name_offset})
    return rows, locators


def rule_definition(script):
    """Recognize the rule-table marker, not filenames or ASCII-only dialogue.

    The loader consumes #RULE_DEFINE as mapping data. Check its framed
    literals as tab-separated identifier records; an unknown shape stops.
    Japanese characters inside resource identifiers are not display text.
    """
    if not script.frames or script.frames[0].opcode != 2:
        return False
    idx = struct.unpack_from("<H", script.frames[0].args)[0]
    if idx == 0xffff:
        return False
    if idx >= len(script.strings):
        raise FormatError("MED leading metadata string outside pool")
    marker = script.strings[idx]
    if marker.startswith(b"#RULE") and marker not in (b"#RULE", b"#RULE_DEFINE"):
        raise FormatError("unsupported MED rule-table marker")
    if marker != b"#RULE_DEFINE":
        return False
    for f in script.frames:
        if f.opcode not in (0, 1, 2, 3, 4, 0x10, 0x25):
            raise FormatError("unexpected MED rule-table command")
        if f.opcode == 1:
            text = script.strings[struct.unpack_from("<H", f.args)[0]].decode("cp932")
            fields = re.split(r"\t+", text)
            if (len(fields) != 2 or any(not value or not 0x20 <= ord(value[0]) <= 0x7e for value in fields)
                    or any(ord(c) < 32 and c != "\t" for c in text)):
                raise FormatError("unsupported MED rule-table literal")
    return True


def export(data):
    script = parse(data)
    rows, locators = records(script)
    manifest = make_manifest(engine="med", variant=PROFILE, reference="engines/med.md",
        sources={"script": data}, rows=rows, locators=locators, encoding="cp932",
        name_policies=["writable" if "name" in r else "absent" for r in rows],
        protected_tokens=[list(dict.fromkeys(controls(r["message"]))) for r in rows])
    return rows, manifest


def rebuild(data, translated, manifest=None):
    script = parse(data)
    original, expected = export(data)
    if manifest is not None and manifest != expected:
        raise FormatError("MED manifest differs from original parse")
    translated = validate_translation(expected, {"script": data}, original, validate_rows(translated))
    edits = {}
    for before, after, record in zip(original, translated, expected["records"]):
        loc = record["locator"]
        for key in before:
            if not after[key] or controls(before[key]) != controls(after[key]):
                raise FormatError("MED empty text or changed control sequence")
            if key == "name" and any(c in after[key] for c in "【】"):
                raise FormatError("MED name must exclude display brackets")
        edits[loc["frame"]] = after["message"].encode("cp932", "strict")
        if loc["name_frame"] is not None:
            pos = loc["name_frame"]
            value = ("【" + after["name"] + "】").encode("cp932", "strict")
            if pos in edits and edits[pos] != value:
                raise FormatError("MED fragments sharing a name command need the same translated name")
            edits[pos] = value
    code = bytearray(script.code)
    strings = list(script.strings)
    size = len(data)
    added = {}
    for f in script.frames:
        if f.offset not in edits:
            continue
        idx = struct.unpack_from("<H", f.args)[0]
        value = edits[f.offset]
        if value == script.strings[idx]:
            continue
        if value not in added:
            # A common cap also covers signed operands for names/choices/titles.
            if len(strings) >= 0x8000:
                raise FormatError("MED appended string exceeds signed 16-bit index")
            size += len(value) + 1
            if size > MAX_FILE:
                raise FormatError("rebuilt MED script exceeds budget")
            added[value] = len(strings)
            strings.append(value)
        struct.pack_into("<H", code, f.offset + 4, added[value])
    pool = b"".join(s + b"\0" for s in (*strings, *script.labels))
    labels = struct.pack(f"<{len(script.targets)}H", *script.targets)
    size = 16 + len(code) + len(labels) + len(pool)
    if size > MAX_FILE:
        raise FormatError("rebuilt MED script exceeds budget")
    header = bytearray(script.header)
    struct.pack_into("<I", header, 0, size - 16)
    struct.pack_into("<H", header, 8, len(strings))
    result = bytes(header + code + labels + pool)
    actual = parse(result)
    if records(actual)[0] != translated:
        raise FormatError("MED re-extracted rows differ")
    masked = bytearray(actual.code)
    for f in script.frames:
        if f.offset in edits:
            masked[f.offset + 4:f.offset + 6] = script.code[f.offset + 4:f.offset + 6]
    if (bytes(masked) != script.code or actual.targets != script.targets or actual.labels != script.labels
            or actual.strings[:len(script.strings)] != script.strings or actual.header[4:8] != script.header[4:8]
            or actual.header[10:] != script.header[10:]):
        raise FormatError("MED non-text structure changed")
    return result


def summary(data):
    script = parse(data)
    rows, locators = records(script)
    return {"rows": len(rows), "roles": dict(Counter(r["kind"] for r in locators)),
            "rule_literals": sum(f.opcode == 1 for f in script.frames) if rule_definition(script) else 0,
            "frames": len(script.frames), "primary_strings": len(script.strings),
            "labels": len(script.labels), "opcodes": dict(Counter(f"{f.opcode:02x}" for f in script.frames))}
