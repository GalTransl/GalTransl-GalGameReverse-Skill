# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2021 arcusmaximus (MIT-derived portions)
# SPDX-FileCopyrightText: msg-tool contributors (GPL-3.0-or-later-derived portions)
"""QLIE .s line spans with original whitespace and delimiter-preserving patches.
Source: VNTextPatch-net8, VNTextPatch.Shared/Scripts/QlieScript.cs,
GetRanges/GetCommandArgumentRanges/GetTextForRead/GetTextForWrite.
Commit d9c0fab7b72fdcf87d674ef12a84d3829c9188be; source license MIT.
Explicit text dialect only; archive crypto and SJIS tunneling are not implemented.
Save-title parameters: msg-tool src/scripts/qlie/script.rs (GPL-3.0-or-later).
"""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Field:
    start: int
    end: int
    kind: str
    raw: str
    text: str
    writable: bool = True


def qlie_fields(script: str) -> tuple[Field, ...]:
    """Extract bracket names, id,name,message lines, choices and plain prose."""
    fields = []
    offset = 0

    def add(start, end, kind):
        raw = script[start:end]
        fields.append(Field(start, end, kind, raw, raw.replace("[n]", "\n"),
                            not (kind == "name" and raw.startswith("$"))))

    for line in script.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        trimmed = body.strip(" \t")
        start = offset + len(body) - len(body.lstrip(" \t"))
        end = start + len(trimmed)
        if not trimmed:
            pass
        elif trimmed.startswith("^select,"):
            at = start + 8
            for part in trimmed[8:].split(","):
                add(at, at + len(part), "choice")
                at += len(part) + 1
        elif trimmed.startswith("^savetext,"):
            caption = trimmed[10:].split(",", 1)[0]
            if "[" in caption or "]" in caption:
                raise ValueError("unsupported QLIE savetext parameter layout")
            add(start + 10, start + 10 + len(caption), "save-title")
        elif trimmed.startswith(("@", "^", "\\", "％")):
            pass
        elif trimmed.startswith("【") and trimmed.endswith("】"):
            add(start + 1, end - 1, "name")
        else:
            match = re.fullmatch(r"\w+,([^,]+),(.+)", trimmed)
            if match:
                add(start + match.start(1), start + match.end(1), "name")
                add(start + match.start(2), start + match.end(2), "message")
            else:
                add(start, end, "message")
        offset += len(line)
    return tuple(fields)


def patch_qlie(script: str, replacements: dict[int, str]) -> str:
    """Field ordinal -> display text. Newlines become [n]; non-newline tags stay."""
    fields = qlie_fields(script)
    if any(type(k) is not int or not 0 <= k < len(fields) for k in replacements):
        raise ValueError("unknown QLIE field")
    out = script
    for index in sorted(replacements, reverse=True):
        field, text = fields[index], replacements[index]
        if not field.writable:
            raise ValueError("name variable is context-only")
        if not isinstance(text, str) or "\0" in text:
            raise ValueError("invalid QLIE text")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        if field.kind == "name" and any(c in text for c in "\n,【】"):
            raise ValueError("name would change QLIE structure")
        if field.kind in ("choice", "save-title") and "," in text:
            raise ValueError("comma would add a QLIE choice")
        if field.kind == "save-title" and "\n" in text:
            raise ValueError("newline in QLIE save title")
        old_tags = re.findall(r"\[(?!n\])[^\]]*\]", field.raw)
        new_tags = re.findall(r"\[(?!n\])[^\]]*\]", text)
        untagged = re.sub(r"\[[^\[\]]*\]", "", text)
        if "[" in untagged or "]" in untagged:
            raise ValueError("unbalanced QLIE control brackets")
        if old_tags != new_tags:
            raise ValueError("non-newline control tags changed")
        if field.kind != "save-title" and text.lstrip().startswith(("@", "^", "\\", "％", "【")):
            raise ValueError("translation introduces a line command")
        text = text.replace("\n", "[n]")
        out = out[:field.start] + text + out[field.end:]
    # Reject changes that make a formerly plain line look like id,name,message.
    if [f.kind for f in qlie_fields(out)] != [f.kind for f in fields]:
        raise ValueError("translation changes QLIE field structure")
    return out
