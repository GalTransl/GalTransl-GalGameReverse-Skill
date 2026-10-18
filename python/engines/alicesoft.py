# SPDX-License-Identifier: GPL-3.0-only
"""AliceSoft AIN text tables: MSG1 (length-prefixed, ciphered), MSG0 and STR0.

The decompressed AIN body is a concatenation of tagged sections. This module
locates the three text-bearing tables by their tags and validates that each one
parses to a section boundary; it deliberately does not claim a full section
sequence (the other tags have no layout evidence here).

MSG1: ``tag, i32 count, i32 reserved, count * (i32 length, length bytes)``.
  Bytes are ciphered with ``b = b - i - 96`` (decrypt) / ``b = b + i + 96``.
MSG0/STR0: ``tag, i32 count, count * NUL-terminated strings`` (no cipher).

Provenance: the three payload layouts, the cipher and the fixed-length rewrite
come from ``ArcAin`` and the AliceSoft tab of the third-party tool
"翻译肋手 v4.9D". This is an independent rewrite: overlong text is refused
instead of being truncated mid-character, and padding is ciphered in the same
pass as the text so that decrypting the whole slot yields spaces (the reference
restarts the cipher phase for padding, which leaves a non-space tail).

Scope: text read and fixed-length rewrite inside an already inflated AIN body.
Not supported: growing a slot, the AIN opcode/argument model, and EX tables.
"""
from dataclasses import dataclass

TEXT_TAGS = ("MSG1", "MSG0", "STR0")
KNOWN_TAGS = frozenset((
    b"VERS", b"KEYC", b"CODE", b"FUNC", b"GLOB", b"GSET", b"STRT", b"MSG0",
    b"MSG1", b"MAIN", b"MSGF", b"HLL0", b"SWI0", b"GVER", b"STR0", b"FNAM",
    b"OJMP", b"FNCT", b"DELG", b"OBJG", b"ENUM",
))
MAX_TEXT = 1 << 20
MAX_COUNT = 1_000_000


@dataclass(frozen=True)
class AinText:
    table: str
    index: int
    offset: int          # absolute offset of the text bytes in the inflated body
    length: int          # stored byte length (MSG1 field or MSG0/STR0 span)
    encrypted: bool
    text: str

    @property
    def writable(self):
        return self.length > 0


@dataclass(frozen=True)
class AinTable:
    tag: str
    offset: int          # offset of the 4-byte tag
    end: int             # first byte after the last entry
    texts: tuple


def cipher(data, *, decrypt):
    out = bytearray(len(data))
    for i, value in enumerate(data):
        out[i] = (value - i - 96) & 0xFF if decrypt else (value + i + 96) & 0xFF
    return bytes(out)


def _i32(raw, pos):
    if pos + 4 > len(raw):
        raise ValueError("truncated int32")
    return int.from_bytes(raw[pos:pos + 4], "little", signed=True), pos + 4


def _boundary(raw, end):
    """A table must end at EOF or at the next known 4-byte tag."""
    if end == len(raw):
        return True
    return raw[end:end + 4] in KNOWN_TAGS


def _parse_table(raw, tag, pos, encoding):
    start = pos
    pos += 4
    count, pos = _i32(raw, pos)
    if not 0 <= count <= MAX_COUNT:
        raise ValueError("AIN table count out of range")
    texts = []
    if tag == "MSG1":
        _, pos = _i32(raw, pos)          # reserved word, preserved in place
        for index in range(count):
            length, pos = _i32(raw, pos)
            if not 0 <= length <= MAX_TEXT or pos + length > len(raw):
                raise ValueError("AIN MSG1 entry out of range")
            body = cipher(raw[pos:pos + length], decrypt=True)
            try:
                text = body.decode(encoding)
            except UnicodeDecodeError as exc:
                raise ValueError(f"AIN MSG1 entry {index} is not {encoding}") from exc
            # Padding is stored as spaces inside the slot; strip it so that a
            # shorter rewrite reads back as exactly the text that was written.
            texts.append(AinText(tag, index, pos, length, True, text.rstrip(" ")))
            pos += length
    else:
        for index in range(count):
            end = raw.find(b"\0", pos)
            if end < 0 or end - pos > MAX_TEXT:
                raise ValueError("AIN string table entry is not terminated")
            try:
                text = raw[pos:end].decode(encoding)
            except UnicodeDecodeError as exc:
                raise ValueError(f"AIN {tag} entry {index} is not {encoding}") from exc
            texts.append(AinText(tag, index, pos, end - pos, False, text.rstrip(" ")))
            pos = end + 1
    if not _boundary(raw, pos):
        raise ValueError(f"AIN {tag} at {start} does not end on a section boundary")
    return AinTable(tag, start, pos, tuple(texts))


def read_ain(raw, *, encoding="cp932"):
    """Return every text-bearing table found, in stream order.

    A tag is accepted only when its entries parse exactly to the next section
    boundary, so tag-like bytes inside message text are skipped, not trusted.
    """
    if not isinstance(raw, bytes) or not raw:
        raise ValueError("AIN body must be non-empty bytes")
    tables, pos = [], 0
    while pos + 4 <= len(raw):
        tag = raw[pos:pos + 4]
        if tag in known_text_tags():
            try:
                table = _parse_table(raw, tag.decode("ascii"), pos, encoding)
            except ValueError:
                pos += 1
                continue
            tables.append(table)
            pos = table.end
            continue
        pos += 1
    texts = tuple(text for table in tables for text in table.texts)
    if len({(t.table, t.index) for t in texts}) != len(texts):
        raise ValueError("duplicate AIN text locators")
    return tuple(tables), texts


def known_text_tags():
    return {tag.encode("ascii") for tag in TEXT_TAGS}


def rewrite_ain(raw, replacements, *, encoding="cp932"):
    """Rewrite text slots in place; every slot keeps its stored byte length."""
    tables, texts = read_ain(raw, encoding=encoding)
    if not isinstance(replacements, dict) or set(replacements) - set(range(len(texts))):
        raise ValueError("unknown AIN text index")
    if any(not texts[index].writable for index in replacements):
        raise ValueError("empty AIN slots are placeholders and stay untouched")
    buffer = bytearray(raw)
    for index, value in sorted(replacements.items()):
        entry = texts[index]
        if not isinstance(value, str) or "\0" in value:
            raise ValueError("invalid AIN text")
        if value.endswith(" "):
            raise ValueError("trailing spaces are stripped on read and cannot be represented")
        try:
            encoded = value.encode(encoding, errors="strict")
        except UnicodeEncodeError as exc:
            raise ValueError(f"AIN text {index} is not encodable") from exc
        if len(encoded) > entry.length:
            raise ValueError(f"AIN text {index} does not fit {entry.length} bytes")
        # Space padding keeps the stored byte length, so a NUL-terminated entry
        # still ends at its original terminator. Padding with NUL (as the
        # reference does) would split one entry into several empty strings.
        body = encoded + b" " * (entry.length - len(encoded))
        if entry.encrypted:
            body = cipher(body, decrypt=False)
        buffer[entry.offset:entry.offset + entry.length] = body
    check_tables, check = read_ain(bytes(buffer), encoding=encoding)
    if len(check) != len(texts):
        raise ValueError("AIN text count changed on rewrite")
    for index, entry in enumerate(check):
        expected = replacements.get(index, texts[index].text)
        if entry.table != texts[index].table or entry.length != texts[index].length:
            raise ValueError("AIN slot identity changed on rewrite")
        if entry.text != expected:
            raise ValueError(f"AIN text {index} round trip differs")
    return bytes(buffer)
