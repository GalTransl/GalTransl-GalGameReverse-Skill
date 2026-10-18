# SPDX-License-Identifier: GPL-3.0-only
"""VALKYRIA ``.sdt`` script: XOR 0xFF body and MICO text spans.

The whole file is XORed with 0xFF. The plain body is a bytecode stream whose
text is carried by four two-byte little-endian opcodes:

  0xF1FE  u16 0xEEEE  u32 (skipped)  cstring    window text
  0xF58F  u16 0xF1FF               cstring    speaker name
  0xF1FB  6 bytes  u16 0xF1FF      cstring    name (indirect form)
  0xF1E3  u32 0xFFFFFFFF            records   choice list; each record is one
                                               non-zero tag byte then a cstring

``0xF1FF`` alone is not scanned: the reference's ``MSGWNDNAME`` case is
unreachable because 0xFF is not in its first-byte set, so names only appear
through the two combined forms above.

This is a span locator, not a disassembler: unknown bytes are skipped one at a
time, and a recognised header whose string is unterminated aborts instead of
being resynchronised. Output is therefore a candidate set that must be checked
against the surrounding code before it is treated as the full text inventory.

Provenance: opcodes, the XOR and the span shapes follow
``GameRes.VALKYRIA.ArcSDT`` in the GARbro-derived code bundled with
"翻译肋手 v4.9D". Independent rewrite: bounded search, explicit NUL checks,
no ``IndexOf``-returns-minus-one arithmetic, and a fixed-length writer that
refuses to truncate mid-character.
"""
from dataclasses import dataclass
import struct

XOR_MASK = 0xFF
MAX_TEXT = 1 << 20
MAX_SPANS = 1_000_000

TEXT_OPCODE = 0xF1FE
NAME_OPCODE = 0xF58F
INDIRECT_NAME_OPCODE = 0xF1FB
CHOICE_OPCODE = 0xF1E3
TOKEN = 0xF1FF
TEXT_MARK = 0xEEEE


@dataclass(frozen=True)
class Span:
    kind: str        # "text" / "name" / "choice"
    offset: int      # absolute offset of the string bytes in the plain body
    length: int      # byte length before the terminating NUL
    text: str


def xor_body(data):
    """XOR every byte with 0xFF; the transform is its own inverse."""
    if not isinstance(data, bytes):
        raise ValueError("SDT input must be bytes")
    return bytes(value ^ XOR_MASK for value in data)


def _cstring(data, start):
    if start > len(data):
        raise ValueError("SDT string starts outside the file")
    end = data.find(b"\0", start)
    if end < 0:
        raise ValueError("SDT string is not NUL terminated")
    if end - start > MAX_TEXT:
        raise ValueError("SDT string exceeds the size budget")
    return data[start:end], end - start


def _decode(raw, encoding, kind):
    try:
        text = raw.decode(encoding)
    except UnicodeDecodeError as exc:
        raise ValueError(f"SDT {kind} is not {encoding}") from exc
    if "\0" in text:
        raise ValueError(f"SDT {kind} contains an embedded NUL")
    return text


def open_sdt(data, *, encoding="cp932"):
    """Return the XORed plain body and every candidate text span."""
    if not data:
        raise ValueError("SDT file is empty")
    plain = xor_body(data)
    spans, pos, limit = [], 0, len(plain) - 1
    while pos < limit:
        first = plain[pos]
        if first not in (0x8F, 0xFE, 0xFB, 0xE3):
            pos += 1
            continue
        opcode = first | (plain[pos + 1] << 8)
        if opcode == TEXT_OPCODE:
            if pos + 8 > len(plain):
                pos += 1
                continue
            if struct.unpack_from("<H", plain, pos + 2)[0] != TEXT_MARK:
                pos += 1
                continue
            raw, length = _cstring(plain, pos + 8)
            spans.append(Span("text", pos + 8, length, _decode(raw, encoding, "text")))
            if len(spans) > MAX_SPANS:
                raise ValueError("SDT span count exceeds the budget")
            pos += 1
            continue
        if opcode == NAME_OPCODE:
            if pos + 4 > len(plain):
                pos += 1
                continue
            if struct.unpack_from("<H", plain, pos + 2)[0] != TOKEN:
                pos += 1
                continue
            raw, length = _cstring(plain, pos + 4)
            spans.append(Span("name", pos + 4, length, _decode(raw, encoding, "name")))
            pos += 1
            continue
        if opcode == INDIRECT_NAME_OPCODE:
            if pos + 10 > len(plain) or plain[pos + 8:pos + 10] != b"\xff\xf1":
                pos += 1
                continue
            raw, length = _cstring(plain, pos + 10)
            spans.append(Span("name", pos + 10, length, _decode(raw, encoding, "name")))
            pos += 1
            continue
        if opcode == CHOICE_OPCODE:
            if pos + 6 > len(plain) or struct.unpack_from("<I", plain, pos + 2)[0] != 0xFFFFFFFF:
                pos += 1
                continue
            cursor = pos + 6
            while cursor < len(plain):
                flag = plain[cursor]
                cursor += 1
                if flag == 0:
                    break
                raw, length = _cstring(plain, cursor)
                spans.append(Span("choice", cursor, length, _decode(raw, encoding, "choice")))
                if len(spans) > MAX_SPANS:
                    raise ValueError("SDT span count exceeds the budget")
                cursor += length + 1
            pos += 1
            continue
        pos += 1
    return plain, tuple(spans)


def write_sdt(data, replacements, *, read_encoding="cp932", write_encoding="gbk"):
    """Rewrite selected spans at fixed length and re-XOR the body."""
    plain, spans = open_sdt(data, encoding=read_encoding)
    if not isinstance(replacements, dict) or set(replacements) - set(range(len(spans))):
        raise ValueError("unknown SDT span")
    buffer = bytearray(plain)
    expected = {}
    for index, value in sorted(replacements.items()):
        span = spans[index]
        if not isinstance(value, str) or "\0" in value:
            raise ValueError("invalid SDT text")
        try:
            encoded = value.encode(write_encoding, errors="strict")
        except UnicodeEncodeError as exc:
            raise ValueError(f"SDT span {index} is not encodable") from exc
        if len(encoded) > span.length:
            raise ValueError(f"SDT span {index} does not fit {span.length} bytes")
        buffer[span.offset:span.offset + span.length] = encoded + b" " * (span.length - len(encoded))
        expected[index] = value + " " * (span.length - len(encoded))
    _, check = open_sdt(xor_body(bytes(buffer)), encoding=read_encoding)
    if len(check) != len(spans):
        raise ValueError("SDT span count changed on write")
    for index, span in enumerate(check):
        if span.kind != spans[index].kind or span.length != spans[index].length:
            raise ValueError("SDT span identity changed on write")
        if span.text != expected.get(index, spans[index].text):
            raise ValueError(f"SDT span {index} round trip differs")
    return xor_body(bytes(buffer))
