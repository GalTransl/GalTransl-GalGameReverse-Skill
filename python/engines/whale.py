"""Whale plain dialogue/SELECT lexer with [n] and first-character protection.

Adapted from VNTextPatch-net8 (MIT), commit
d9c0fab7b72fdcf87d674ef12a84d3829c9188be,
VNTextPatch.Shared/Scripts/WhaleScript.cs,
GetMessageRanges/GetSelectRanges/GetTextForRead/GetTextForWrite.
CS/MS.HS command arguments are intentionally outside this limited subset.
"""
from dataclasses import dataclass
from collections.abc import Mapping
import re


@dataclass(frozen=True)
class Target:
    start: int
    end: int
    role: str
    text: str
    at_line_start: bool
    kind: str


def extract(script: str) -> tuple[Target, ...]:
    """Return codepoint spans, not byte offsets; SELECT labels never become text."""
    targets = []
    offset = 0
    for full in script.splitlines(keepends=True):
        line = full.rstrip("\r\n")
        if not line or line.isspace() or line.startswith("*"):
            offset += len(full)
            continue

        def add(start, end, role="message", kind="dialogue"):
            targets.append(Target(offset + start, offset + end, role,
                                  line[start:end].replace("[n]", "\n"), start == 0, kind))

        if ord(line[0]) > 255:
            pos = 0
            if line.startswith("【"):
                close = line.find("】")
                if close < 0:
                    raise ValueError("unclosed Whale name bracket")
                name = line[1:close].split(",", 1)[0]
                if not name:
                    raise ValueError("empty Whale name")
                add(1, 1 + len(name), "name")
                pos = close + 1
            if pos < len(line) and line[pos] == "「":
                add(pos + 1, len(line) - (1 if line.endswith("」") else 0))
            elif pos == 0:
                # Narration and parenthesized internal monologue retain wrappers.
                add(0, len(line))
            else:
                raise ValueError("named Whale line without supported 「 dialogue")
        elif line.startswith("SELECT "):
            pos = len("SELECT ")
            matches = []
            while pos < len(line):
                m = re.match(r'"([^",]+),\*(\w+)"', line[pos:])
                if not m:
                    raise ValueError("unsupported Whale SELECT syntax")
                matches.append((pos + m.start(1), pos + m.end(1)))
                pos += m.end()
                gap = re.match(r"[, \t]*", line[pos:])[0]
                pos += len(gap)
            if not matches:
                raise ValueError("empty SELECT")
            for a, b in matches:
                add(a, b, kind="choice")
        offset += len(full)
    return tuple(targets)


def patch(script: str, replacements: Mapping[int, str]) -> str:
    """Replace extracted ordinals and preserve labels, delimiters and EOL bytes."""
    targets = extract(script)
    if any(type(i) is not int or not 0 <= i < len(targets) for i in replacements):
        raise ValueError("unknown Whale target index")
    edits = []
    for i, text in replacements.items():
        target = targets[i]
        if "\0" in text or "[n]" in text:
            raise ValueError("use real newlines, not literal [n], in translation")
        text = text.replace("\r\n", "\n")
        if "\r" in text:
            raise ValueError("bare CR")
        if target.role == "name" and any(c in text for c in "【】,\n"):
            raise ValueError("speaker translation changes Whale name structure")
        if target.kind == "choice" and any(c in text for c in '",'):
            raise ValueError("choice translation changes SELECT structure")
        if not text:
            raise ValueError("empty Whale target is outside this subset")
        if target.at_line_start and ord(text[0]) <= 255:
            text = "　" + text.replace("\n", "\n　")
        edits.append((target.start, target.end, text.replace("\n", "[n]")))
    for start, end, text in sorted(edits, reverse=True):
        script = script[:start] + text + script[end:]
    return script
