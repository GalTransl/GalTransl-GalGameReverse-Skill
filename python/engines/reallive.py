"""RealLive CP932 quoted strings and linebreak instruction fragments only.

Adapted from VNTextPatch-net8 (MIT), commit
d9c0fab7b72fdcf87d674ef12a84d3829c9188be,
VNTextPatch.Shared/Scripts/RealLive/RealLiveAssembler.cs,
WriteString/WriteLineBreak/WriteFunctionCall; RealLiveScript.cs EncodeMessage.
Full VM disassembly/address relocation is deliberately NOT implemented.
"""
import struct

LINE_BREAK = b"#" + struct.pack("<BBHHB", 0, 3, 201, 0, 0)


def _sjis_units(raw):
    pos = 0
    while pos < len(raw):
        width = 2 if 0x81 <= raw[pos] <= 0x9F or 0xE0 <= raw[pos] <= 0xFC else 1
        if pos + width > len(raw):
            raise ValueError("truncated SJIS character")
        unit = raw[pos:pos + width]
        unit.decode("cp932", "strict")
        yield unit
        pos += width


def quote_text(text: str) -> bytes:
    """Assemble one nonempty quoted text token, escaping only ASCII double quotes.

    Reject ASCII backslash because backslash-before-closing-quote is ambiguous
    in this limited codec. A DBCS trail 0x5c (e.g. 表) is NOT a backslash token.
    """
    if not text or any(c in text for c in ("\0", "\n", "\r", "\\")):
        raise ValueError("expected nonempty single-line text without ASCII backslash")
    parts = []
    for unit in _sjis_units(text.encode("cp932", "strict")):
        parts.append(b'\\"' if unit == b'"' else unit)
    return b'"' + b"".join(parts) + b'"'


def unquote_text(data: bytes) -> str:
    """Read exactly one token emitted by quote_text, not arbitrary VM code."""
    if len(data) < 3 or data[:1] != b'"' or data[-1:] != b'"':
        raise ValueError("expected a nonempty quoted text token")
    raw = data[1:-1]
    pos = 0
    out = bytearray()
    while pos < len(raw):
        b = raw[pos]
        if b == 0x5C:
            if raw[pos:pos + 2] != b'\\"':
                raise ValueError("unsupported escape")
            out.append(0x22)
            pos += 2
        elif b == 0x22 or b in (0, 10, 13):
            raise ValueError("unescaped quote/control in token")
        else:
            width = 2 if 0x81 <= b <= 0x9F or 0xE0 <= b <= 0xFC else 1
            if pos + width > len(raw):
                raise ValueError("truncated SJIS unit")
            out.extend(raw[pos:pos + width])
            pos += width
    return out.decode("cp932", "strict")


def assemble_message(message: str, *, name: str | None = None) -> bytes:
    """Build a local message fragment; explicit LF/CRLF become function 201.

    Caller must locate real text ranges and relocate every VM address. This
    result cannot safely be pasted into a SEEN/.rl file by regex replacement.
    """
    text = message.replace("\r\n", "\n")
    if "\r" in text:
        raise ValueError("bare CR")
    out = bytearray()
    if name is not None:
        if not name or any(c in name for c in ('"', "\\", "\0", "\r", "\n", "【", "】")):
            raise ValueError("unsafe unquoted RealLive speaker name")
        out.extend(("【" + name + "】").encode("cp932", "strict"))
    for line in text.split("\n"):
        if line:
            out.extend(quote_text(line))
        out.extend(LINE_BREAK)
    return bytes(out)
