# SPDX-License-Identifier: GPL-3.0-only
# Adapted from SExtractor tools/SystemC/fpk_pack_SystemB3.py and src/reg.yaml:_BIN_SystemC
# Source commit: 8d8d976fd04ae54e7c677705af937273d04a376a
# Upstream attribution: satan53x / SExtractor contributors.
"""SystemC name headers and Tomefure ACT/DAT/SPT line-reference text dialect.

The ACT/DAT/SPT implementation is based on structural examination of Tomefure.
Only opcode 1 exposes text; all compiled records and line counts are preserved.
"""
# Layer split: engines; format algorithms and original notices retained.
# Companion module: python/archives/systemc.py
import re
import struct

from ..common.binary import FormatError
from ..common.contract import make_manifest, validate_translation

VARIANT = "tomefure-act-dat156-spt32-cp932"
MAX_BYTES = 64 << 20
KNOWN_OPCODES = frozenset({1, 2, 3, 4, 6, 7, 8, 9, 10, 11, 13, 14, 15, 18,
                         19, 20, 22, 24, 26, 27, 29, 33, 34, 35, 36, 37, 38, 40, 41, 42})
LABEL = re.compile(r"^\*\*\*(SC|SS)_([A-Z])(\d+)_(\d+)(?:_|\s|$)")
NAME = re.compile(r"^(.+?)　（([０-９]+)）(.*)$")
CONTROL = re.compile(r"\$[A-Za-z]+|&[A-Za-z]+;")


def systemc_name_header(line):
    """Recognize only the documented name + fullwidth-space/(digit) text header.

    Does not promote all other strings to messages. The caller must already
    have the decoded SystemC text dialect, not arbitrary binary fragments.
    """
    if len(line) > 65536 or not line or re.match(r"[A-Za-z/*]", line):
        return None
    match = re.match(r"^(.+?)　（(?=[０-９])", line)
    return {"name": match[1], "suffix": line[match.end(1):]} if match else None


def _lines(data):
    if len(data) > MAX_BYTES or b"\0" in data:
        raise FormatError("SystemC text exceeds budget or contains NUL")
    raw = data.split(b"\r\n")
    if any(b"\r" in line or b"\n" in line for line in raw):
        raise FormatError("SystemC requires consistent CRLF line endings")
    try:
        return raw, [line.decode("cp932", errors="strict") for line in raw]
    except UnicodeError as exc:
        raise FormatError("SystemC source is not strict CP932") from exc


def _records(data, width):
    if len(data) < 4 or len(data) > MAX_BYTES:
        raise FormatError("SystemC table outside budget")
    count = struct.unpack_from("<I", data)[0]
    if count > 100000 or len(data) != 4 + count * width:
        raise FormatError("SystemC fixed record count/size mismatch")
    return [data[4 + i * width:4 + (i + 1) * width] for i in range(count)]


def _parse(act_name, members):
    """Bind DAT ranges to labels, then require matching SPT text references.

    Name headers can include an extra voice-actor alias. Retain the whole
    header; the JSON name is context only. Header numbers and compiled voice
    numbers must agree. Unreferenced text fails rather than silently vanishing.
    """
    if not re.fullmatch(r"ACT_[A-Z]\.txt", act_name):
        raise FormatError("unsupported SystemC ACT filename")
    dat_name = act_name[:-4] + ".DAT"
    for name in (act_name, dat_name, "charaid.tbl"):
        if name not in members:
            raise FormatError(f"missing SystemC source: {name}")
    raw, lines = _lines(members[act_name])
    sources = {name: members[name] for name in (act_name, dat_name, "charaid.tbl")}
    char_lines = _lines(members["charaid.tbl"])[1]
    characters = []
    for line in char_lines:
        if not line or line.startswith("//"):
            continue
        m = re.fullmatch(r"(.+) ([01])", line)
        if not m:
            raise FormatError("unsupported SystemC character table")
        characters.append(m[1])
    rows, locators, sections, used = [], [], [], set()
    labels = [i for i, line in enumerate(lines) if line.startswith("***")]
    dat_records = _records(members[dat_name], 156)
    if len(dat_records) != len(labels):
        raise FormatError("SystemC DAT/ACT section count mismatch")
    for si, record in enumerate(dat_records):
        fields = struct.unpack_from("<19i", record, 80)
        start, end, route, scene, block = fields[:5]
        header_at = labels[si]
        expected_end = labels[si + 1] if si + 1 < len(labels) else len(lines) - 1
        if start != header_at + 1 or end != expected_end or not 0 <= route < 26:
            raise FormatError("SystemC DAT line range does not match ACT labels")
        label = LABEL.match(lines[header_at])
        if not label or (label[2], int(label[3]), int(label[4])) != (chr(65 + route), scene, block):
            raise FormatError("SystemC DAT identity disagrees with ACT label")
        spt_name = f"{chr(65 + route)}{scene:04d}_{block:02d}.spt"
        if spt_name not in members or spt_name in sources:
            raise FormatError(f"missing or duplicate SPT: {spt_name}")
        sources[spt_name] = members[spt_name]
        section_rows = 0
        last_stop = start
        for ri, code in enumerate(_records(members[spt_name], 32)):
            values = struct.unpack("<8i", code)
            opcode, char_id, voice, reserved, first, count, category, arg = values
            if opcode not in KNOWN_OPCODES:
                raise FormatError(f"unknown SystemC opcode {opcode} in {spt_name}")
            if opcode != 1:
                continue
            if (reserved, category, arg) != (-1, 7, 0) or not 0 < char_id <= len(characters):
                raise FormatError("unsupported SystemC text instruction shape")
            if count < 1 or first < last_stop or first + count > end:
                raise FormatError("SystemC text range outside section or out of order")
            last_stop = first + count
            occupied = set(range(first, first + count))
            if used & occupied:
                raise FormatError("overlapping SystemC text references")
            used.update(occupied)
            part = lines[first:first + count]
            header = NAME.fullmatch(part[0])
            row = {}
            message_line = first
            if header:
                if int(header[2]) != voice or count < 2:
                    raise FormatError("SystemC name header/voice mismatch")
                row["name"] = header[1]
                part = part[1:]
                message_line += 1
            elif voice != 0 or characters[char_id - 1] != "ナレーション":
                raise FormatError("SystemC non-narrator text lacks a name header")
            for line in part:
                if not line.strip() or line.startswith(("//", "***")) or re.match(r"[A-Za-z]+_", line):
                    raise FormatError("SystemC text reference points into a command/blank line")
                if any(ord(c) < 32 for c in line):
                    raise FormatError("unsupported SystemC control character")
                # Fail closed on unknown control syntax, including incomplete tokens.
                stripped = CONTROL.sub("", line)
                if any(c in stripped for c in "$&\\<>[]{}@#%^|~"):
                    raise FormatError("unknown SystemC text control syntax")
            tokens = CONTROL.findall("\n".join(part))
            if set(tokens) - {"$S", "$L", "&heart;"}:
                raise FormatError("unknown SystemC text control token")
            row["message"] = "\n".join(part)
            rows.append(row)
            locators.append({"spt": spt_name, "record": ri, "kind": "selection" if label[1] == "SS" else "message",
                             "header_line": first if header else None, "message_line": message_line,
                             "message_lines": len(part), "character_id": char_id, "voice": voice})
            section_rows += 1
        sections.append({"spt": spt_name, "kind": label[1], "rows": section_rows})
    # Only source text covered by compiled records is exported. Remaining visible
    # prose is an error; comments/directives/labels are retained byte for byte.
    for i, line in enumerate(lines):
        if i not in used and line.strip() and not re.match(r"[A-Za-z/*]", line):
            raise FormatError(f"unreferenced SystemC prose at {act_name}:{i + 1}")
    return rows, locators, sources, sections, raw


def export_act(act_name, members):
    rows, locators, sources, sections, _ = _parse(act_name, members)
    tokens = [list(dict.fromkeys(CONTROL.findall(row["message"]) + (["\n"] if "\n" in row["message"] else [])))
              for row in rows]
    manifest = make_manifest(engine="systemc", variant=VARIANT,
        reference="python/engines/systemc.py", sources=sources, rows=rows, locators=locators,
        encoding="cp932", protected_tokens=tokens,
        settings={"act": act_name, "sections": sections, "line_endings": "CRLF",
                  "name": "context-only; preserve header and compiled character/voice IDs",
                  "newline_policy": "same line count and ordered controls per line"})
    return rows, manifest


def inject_act(act_name, members, original_rows, manifest, translated_rows, *, text_codec=None):
    expected_rows, expected_manifest = export_act(act_name, members)
    if expected_rows != original_rows or expected_manifest != manifest:
        raise FormatError("SystemC export/manifest differs from source parser")
    sources = {item["path"]: members[item["path"]] for item in manifest["sources"]}
    if text_codec is not None:
        # Reserve name headers, commands and unchanged text too. The package
        # adapter must additionally reserve OTHER scripts before calling us.
        text_codec.reserve(members[act_name].decode("cp932"))
        text_codec.reserve(members["charaid.tbl"].decode("cp932"))
    translated = validate_translation(manifest, sources, original_rows, translated_rows, text_codec=text_codec)
    raw, _ = _lines(members[act_name])
    for before, after, rec in zip(original_rows, translated, manifest["records"]):
        old_lines = before["message"].split("\n")
        new_lines = after["message"].split("\n")
        if len(old_lines) != len(new_lines):
            raise FormatError("SystemC message line count changed")
        for i, (old, new) in enumerate(zip(old_lines, new_lines)):
            if old == new:
                continue
            if not new.strip() or any(ord(c) < 32 for c in new):
                raise FormatError("blank line or new SystemC control character")
            if CONTROL.findall(old) != CONTROL.findall(new):
                raise FormatError("SystemC ordered control tokens changed line")
            if NAME.match(new) or new.startswith(("//", "***")) or re.match(r"[A-Za-z]+_", new):
                raise FormatError("translation introduces SystemC command/name syntax")
            if any(c in CONTROL.sub("", new) for c in "$&\\<>[]{}@#%^|~"):
                raise FormatError("translation introduces unknown SystemC text controls")
            encoded = text_codec.encode(new) if text_codec is not None else new.encode("cp932", errors="strict")
            decoded = encoded.decode("cp932")
            if text_codec is not None:
                decoded = text_codec.display(decoded)
            if len(encoded) > 4096 or decoded != new:
                raise FormatError("SystemC line exceeds budget or is not lossless CP932")
            raw[rec["locator"]["message_line"] + i] = encoded
    rebuilt = b"\r\n".join(raw)
    updated = dict(members, **{act_name: rebuilt})
    parsed_rows, parsed_manifest = export_act(act_name, updated)
    if text_codec is not None:
        parsed_rows = [{key: text_codec.display(value) for key, value in row.items()} for row in parsed_rows]
    if parsed_rows != translated or parsed_manifest["records"] != manifest["records"]:
        raise FormatError("SystemC text reparse or compiled bindings changed")
    return rebuilt
