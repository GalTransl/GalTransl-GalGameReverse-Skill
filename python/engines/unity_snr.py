# SPDX-License-Identifier: GPL-3.0-only
"""Unity SNR scenario: one MsgPack string with ``\\text`` .. ``\\endtext`` blocks.

The whole file is a single MsgPack string value. Its content is a newline
separated script where every line inside a ``\\text`` / ``\\endtext`` pair is a
display line. This module edits those lines and rebuilds the string without
touching any other line.

Line splitting is literal ``\\n``: a trailing newline produces a final empty
element that is preserved on write-back. Marker lines are recognised by prefix
(``\\text`` and ``\\endtext``), matching the reference tool, because real
scripts annotate them with extra fields on the same line.

Provenance: the MsgPack string wrapper and the marker-prefix rule follow
``GameRes.Unity.ArcSNR`` in the GARbro-derived code bundled with
"翻译肋手 v4.9D". Independent rewrite: exact line preservation instead of
re-joining every line with an appended newline, so a no-op edit is byte
identical.
"""
from dataclasses import dataclass
import struct

from python.archives.unity_arc import unpack_record

START = "\\text"
END = "\\endtext"
MAX_SCRIPT = 64 << 20


@dataclass(frozen=True)
class SnrLine:
    index: int          # 0-based line number
    text: str           # line content without the newline
    in_text: bool       # inside a block, markers excluded


def _unpack_string(data):
    value = unpack_record(data)
    if not isinstance(value, str):
        raise ValueError("SNR payload is not a MsgPack string")
    return value


def pack_string(text):
    """Encode one MsgPack string (fixstr / str8 / str16 / str32)."""
    raw = text.encode("utf-8")
    if len(raw) > MAX_SCRIPT:
        raise ValueError("SNR script exceeds the size budget")
    if len(raw) <= 31:
        return bytes([0xA0 | len(raw)]) + raw
    if len(raw) <= 0xFF:
        return b"\xd9" + bytes([len(raw)]) + raw
    if len(raw) <= 0xFFFF:
        return b"\xda" + struct.pack(">H", len(raw)) + raw
    return b"\xdb" + struct.pack(">I", len(raw)) + raw


def open_snr(data):
    """Return the script text and every line with its in-block flag."""
    script = _unpack_string(data)
    if len(script) > MAX_SCRIPT:
        raise ValueError("SNR script exceeds the size budget")
    lines, inside = [], False
    for index, line in enumerate(script.split("\n")):
        if line.startswith(START):
            inside = True
            lines.append(SnrLine(index, line, False))
        elif line.startswith(END):
            inside = False
            lines.append(SnrLine(index, line, False))
        else:
            lines.append(SnrLine(index, line, inside))
    return script, tuple(lines)


def apply_snr_texts(data, replacements):
    """Replace selected in-block lines; ``{line index: new text}``."""
    script, lines = open_snr(data)
    if not isinstance(replacements, dict) or set(replacements) - set(range(len(lines))):
        raise ValueError("unknown SNR line")
    if any(not lines[index].in_text for index in replacements):
        raise ValueError("only lines inside a \\text block are writable")
    parts = script.split("\n")
    for index, value in replacements.items():
        if not isinstance(value, str) or "\n" in value or "\r" in value:
            raise ValueError("SNR line must be a single line of text")
        if value.startswith(START) or value.startswith(END):
            raise ValueError("SNR line must not open or close a block")
        parts[index] = value
    rebuilt = pack_string("\n".join(parts))
    check, again = open_snr(rebuilt)
    if len(again) != len(lines):
        raise ValueError("SNR line count changed")
    for index, line in enumerate(again):
        expected = replacements.get(index, lines[index].text)
        if line.text != expected or line.in_text != lines[index].in_text:
            raise ValueError(f"SNR line {index} round trip differs")
    return rebuilt
