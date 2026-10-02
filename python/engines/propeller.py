"""Propeller MSC text-field codec, not the opcode/address relocator.

Adapted from VNTextPatch-net8 (MIT), commit
d9c0fab7b72fdcf87d674ef12a84d3829c9188be,
VNTextPatch.Shared/Scripts/Propeller/PropellerScript.cs,
FormattingReplacements, GetParsedString, WritePatched.
"""
import re
import struct

_CODES = {"b": b"\xfc\xfd", "i": b"\xfc\xfe", "u": b"\xfc\xff"}


def write_text_field(text: str) -> bytes:
    """Build i32 byte length + text. Newlines become _r; tags become toggles.

    Input is visible body, not a complete instruction. Names are not invented.
    Balanced <b>/<i>/<u> are the only interpreted markup; unknown markup stays.
    """
    if "\0" in text or "_r" in text or text.startswith("<,>"):
        raise ValueError("reserved NUL/_r/<,> syntax in visible text")
    text = text.replace("\r\n", "\n")
    if "\r" in text:
        raise ValueError("bare CR is unsupported")
    out = bytearray(b"<,>" if "," in text else b"")
    active = set()
    pos = 0
    for match in re.finditer(r"</?([biu])>", text):
        out.extend(text[pos:match.start()].replace("\n", "_r").encode("cp932", "strict"))
        style = match[1]
        closing = match[0].startswith("</")
        if closing != (style in active):
            raise ValueError("unbalanced formatting toggle")
        active.remove(style) if closing else active.add(style)
        out.extend(_CODES[style])
        pos = match.end()
    if active:
        raise ValueError("unclosed formatting toggle")
    out.extend(text[pos:].replace("\n", "_r").encode("cp932", "strict"))
    return struct.pack("<i", len(out)) + bytes(out)


def read_text_field(data: bytes, offset: int = 0) -> tuple[str, int]:
    """Decode one field at a proven boundary, preserving DBCS token boundaries."""
    if offset < 0 or offset + 4 > len(data):
        raise ValueError("truncated MSC text length")
    size = struct.unpack_from("<i", data, offset)[0]
    end = offset + 4 + size
    if size < 0 or end > len(data):
        raise ValueError("invalid MSC text length")
    raw = data[offset + 4:end]
    pos = 3 if raw.startswith(b"<,>") else 0
    active, parts = set(), []
    inverse = {v: k for k, v in _CODES.items()}
    while pos < len(raw):
        pair = raw[pos:pos + 2]
        if pair in inverse:
            style = inverse[pair]
            parts.append(f"</{style}>" if style in active else f"<{style}>")
            active.remove(style) if style in active else active.add(style)
            pos += 2
        elif pair == b"_r":
            parts.append("\n")
            pos += 2
        else:
            width = 2 if 0x81 <= raw[pos] <= 0x9F or 0xE0 <= raw[pos] <= 0xFC else 1
            if pos + width > len(raw) or raw[pos] == 0:
                raise ValueError("truncated SJIS character or embedded NUL")
            parts.append(raw[pos:pos + width].decode("cp932", "strict"))
            pos += width
    if active:
        raise ValueError("unbalanced formatting toggles in field")
    return "".join(parts), end


def split_names(text: str) -> dict:
    """Parse repeated leading 【name】/ groups without losing multi-speaker names."""
    names = []
    while text.startswith("【"):
        end = text.find("】")
        if end <= 1:
            break
        names.append(text[1:end])
        text = text[end + 1:]
        if text.startswith("/"):
            text = text[1:]
    return {"names": tuple(names), "message": text}
