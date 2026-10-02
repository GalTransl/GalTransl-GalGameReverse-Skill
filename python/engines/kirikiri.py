"""Finite KAG text spans; not a TJS/SCN parser or universal .ks writer.
Source: VNTextPatch-net8, VNTextPatch.Shared/Scripts/Kirikiri/KirikiriKsScript.cs,
GetRanges/GetLineRanges/GetLabelRanges/GetNameRanges/GetMessageRanges.
Commit d9c0fab7b72fdcf87d674ef12a84d3829c9188be; source license MIT.
Only #name, label titles, prose and r/l/p/cm/ns/nse tags are editable here.
"""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    kind: str
    text: str
    writable: bool = True


def kag_spans(script: str) -> tuple[Span, ...]:
    """str -> original character spans, retaining separate names and name variables.

    Unknown line commands remain opaque. Unknown inline tags refuse the finite
    dialect rather than expose script parameters as dialogue. No line merging.
    """
    result = []
    offset = 0
    block = None
    role = "message"

    def emit(start, end, kind):
        text = script[start:end]
        if text.strip():
            variable = kind == "name" and text.strip().startswith("$")
            result.append(Span(start, end, "name_variable" if variable else kind,
                               text, not variable))

    for raw in script.splitlines(keepends=True):
        line = raw.rstrip("\r\n")
        if raw[len(line):] not in ("", "\n", "\r", "\r\n"):
            raise ValueError("unsupported KAG line ending")
        clean = line.lstrip(" \t")
        lead = len(line) - len(clean)
        if block:
            if clean in ("[endscript]", "@endscript") and block == "script":
                block = None
            elif clean in ("[endmacro]", "@endmacro") and block == "macro":
                block = None
            offset += len(raw)
            continue
        if clean in ("[iscript]", "@iscript"):
            block = "script"
        elif re.match(r"(?:\[macro(?:\s|\])|@macro(?:\s|$))", clean):
            block = "macro"
        elif clean in ("[endscript]", "@endscript", "[endmacro]", "@endmacro"):
            raise ValueError("unmatched KAG block terminator")
        elif clean.startswith(";") or clean.startswith("@"):
            pass
        elif clean.startswith("#"):
            emit(offset + lead + 1, offset + len(line), "name")
        elif clean.startswith("*"):
            pipe = line.find("|")
            if pipe >= 0:
                emit(offset + pipe + 1, offset + len(line), "title")
        else:
            pos = 0
            for token in re.finditer(r"\[[^\[\]\r\n]*\]", line):
                if "[" in line[pos:token.start()] or "]" in line[pos:token.start()]:
                    raise ValueError("unbalanced KAG bracket")
                emit(offset + pos, offset + token.start(), role)
                command = token.group()[1:-1]
                if command not in {"r", "l", "p", "cm", "ns", "nse"}:
                    raise ValueError(f"inline tag outside finite KAG dialect: {command}")
                if command == "ns":
                    role = "name"
                elif command == "nse":
                    role = "message"
                pos = token.end()
            if "[" in line[pos:] or "]" in line[pos:]:
                raise ValueError("unbalanced KAG bracket")
            emit(offset + pos, offset + len(line), role)
        offset += len(raw)
    if block:
        raise ValueError("unterminated KAG script/macro block")
    return tuple(result)


def patch_kag(script: str, replacements: dict[int, str]) -> str:
    """Span ordinal -> literal text; control tags, line endings and code stay exact."""
    spans = kag_spans(script)
    if any(type(k) is not int or not 0 <= k < len(spans) for k in replacements):
        raise ValueError("unknown KAG span")
    out = script
    for index in sorted(replacements, reverse=True):
        span, text = spans[index], replacements[index]
        if not span.writable:
            raise ValueError("name variable is context-only")
        if not isinstance(text, str) or any(c in text for c in "[]\r\n\0"):
            raise ValueError("translation introduces KAG syntax")
        if text.lstrip().startswith(("@", ";", "*", "#")):
            raise ValueError("translation introduces a line command")
        out = out[:span.start] + text + out[span.end:]
    return out
