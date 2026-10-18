# SPDX-License-Identifier: GPL-3.0-only
"""Kaguya early ``message.dat``: sequential length-prefixed XOR blocks.

Header: 13 bytes ``[SCR-MESSAGE]``, a 4-byte version field ending at 0x10, then
one or two extra header bytes. The extra width is selected by the last version
byte: ``< 0x03`` adds 1 byte, ``0x03..0x33`` adds 2, larger values do not belong
to this branch.

Body: repeated ``u32le payload length`` plus payload, where every payload byte
is XORed with 0xFF; the length field itself is not. A zero length marks the end
and the marker plus everything after it is kept verbatim. A file that ends right
after a complete block is also valid; a partial length field or a payload that
crosses EOF is an error.

Payload: the first NUL-terminated string is the speaker, followed by one
``u8 count`` byte. With ``count > 0`` the remaining bytes are ``count``
NUL-terminated message strings. With ``count == 0`` the first string is a choice
line and the rest of the payload is unclassified; it is preserved as a tail and
never exported as dialogue.

No writer existed in the reference tool; the layout rules here follow the
SExtractor ``extract_Kaguya_dat.py`` description already recorded on the engine
page. Rewrites are strict: declared counts must match the strings actually
scanned, and every block must end exactly on its payload boundary before a
writer is offered.
"""
from dataclasses import dataclass, field
import struct

MAGIC = b"[SCR-MESSAGE]"
HEADER_LEN = 13
VERSION_END = 17
MAX_FILE = 64 << 20
MAX_BLOCKS = 65536
MAX_BLOCK = 8 << 20


@dataclass(frozen=True)
class EarlyBlock:
    ordinal: int
    offset: int                 # absolute offset of the u32 length field
    payload_size: int           # declared payload bytes (before XOR)
    name: str
    messages: tuple
    choice: str | None
    count: int
    tail: bytes                 # unclassified trailing payload bytes
    raw_name: bytes = field(default=b"", compare=False, repr=False)
    raw_messages: tuple = field(default=(), compare=False, repr=False)
    raw_choice: bytes = field(default=b"", compare=False, repr=False)


@dataclass(frozen=True)
class EarlyDocument:
    header: bytes
    blocks: tuple
    trailer: bytes


def _xor(data):
    return bytes(value ^ 0xFF for value in data)


def _decode(raw, encoding, what):
    try:
        return raw.decode(encoding)
    except UnicodeDecodeError as exc:
        raise ValueError(f"early Kaguya {what} is not {encoding}") from exc


def _header_width(data):
    if len(data) < VERSION_END:
        raise ValueError("early Kaguya header is truncated")
    last = data[VERSION_END - 1]
    if last < 0x03:
        return 1
    if last < 0x34:
        return 2
    raise ValueError("early Kaguya version field is outside the 02/03 branch")


def _split_strings(payload, start):
    """Split NUL-terminated strings up to the payload end; return raws and cursor."""
    raws, cursor = [], start
    while cursor < len(payload):
        end = payload.find(b"\0", cursor)
        if end < 0:
            raise ValueError("early Kaguya block string is not NUL terminated")
        raws.append(payload[cursor:end])
        cursor = end + 1
    return raws, cursor


def read_early_message(data, *, encoding="cp932", strict=True):
    """Parse a whole early ``message.dat``; ``strict`` also checks declared counts."""
    if not isinstance(data, bytes) or len(data) > MAX_FILE:
        raise ValueError("early Kaguya input is not a bounded bytes object")
    if len(data) < VERSION_END or data[:HEADER_LEN] != MAGIC:
        raise ValueError("not an early Kaguya message table")
    width = _header_width(data)
    pos = VERSION_END + width
    if pos > len(data):
        raise ValueError("early Kaguya header is truncated")
    header = data[:pos]
    blocks = []
    while pos < len(data):
        if pos + 4 > len(data):
            raise ValueError("early Kaguya length field is truncated")
        size = struct.unpack_from("<I", data, pos)[0]
        if size == 0:
            return EarlyDocument(header, tuple(blocks), data[pos:])
        if size > MAX_BLOCK or pos + 4 + size > len(data):
            raise ValueError("early Kaguya block crosses the file")
        payload = _xor(data[pos + 4:pos + 4 + size])
        nul = payload.find(b"\0")
        if nul < 0:
            raise ValueError("early Kaguya block lacks its first NUL")
        if nul + 1 >= len(payload):
            raise ValueError("early Kaguya block lacks its count byte")
        count = payload[nul + 1]
        raw_name = payload[:nul]
        cursor = nul + 2
        name = _decode(raw_name, encoding, "name")
        if count == 0:
            end = payload.find(b"\0", cursor)
            if end < 0:
                raise ValueError("early Kaguya choice string is not NUL terminated")
            choice_raw = payload[cursor:end]
            tail = payload[end + 1:]
            blocks.append(EarlyBlock(
                len(blocks), pos, size, name, (), _decode(choice_raw, encoding, "choice"),
                count, tail, raw_name, (), choice_raw))
        else:
            raw_messages, _ = _split_strings(payload, cursor)
            if strict and len(raw_messages) != count:
                raise ValueError(
                    f"early Kaguya block declares {count} strings but holds {len(raw_messages)}")
            messages = tuple(_decode(raw, encoding, "message") for raw in raw_messages)
            blocks.append(EarlyBlock(
                len(blocks), pos, size, name, messages, None, count, b"",
                raw_name, raw_messages, b""))
        if len(blocks) > MAX_BLOCKS:
            raise ValueError("early Kaguya block count exceeds the budget")
        pos += 4 + size
    return EarlyDocument(header, tuple(blocks), b"")


def _encode(value, encoding, what):
    try:
        return value.encode(encoding, errors="strict")
    except UnicodeEncodeError as exc:
        raise ValueError(f"early Kaguya {what} cannot be encoded as {encoding}") from exc


def patch_early_message(data, changes, *, encoding="cp932", strict=True):
    """Rewrite selected blocks, recomputing each payload length.

    ``changes`` maps a block ordinal to ``{"name": str, "messages": [...],
    "choice": str}``. The message list must keep the original length; blocks
    without a change reuse their original bytes so CP932 aliases stay stable.
    """
    document = read_early_message(data, encoding=encoding, strict=strict)
    if not isinstance(changes, dict) or set(changes) - set(range(len(document.blocks))):
        raise ValueError("unknown early Kaguya block")
    output = bytearray(document.header)
    expected = []
    for block in document.blocks:
        change = changes.get(block.ordinal, {})
        if not isinstance(change, dict) or set(change) - {"name", "messages", "choice"}:
            raise ValueError("invalid early Kaguya change")
        if not change:
            output += data[block.offset:block.offset + 4 + block.payload_size]
            expected.append((block, block.raw_name,
                             block.raw_messages if block.count else block.raw_choice))
            continue
        name_raw = block.raw_name
        if "name" in change:
            name_raw = _encode(change["name"], encoding, "name")
        if block.count == 0:
            if "messages" in change:
                raise ValueError("choice block cannot take messages")
            choice_raw = block.raw_choice
            if "choice" in change:
                choice_raw = _encode(change["choice"], encoding, "choice")
            payload = name_raw + b"\0" + b"\0" + choice_raw + b"\0" + block.tail
        else:
            if "choice" in change:
                raise ValueError("message block cannot take a choice")
            raw_messages = list(block.raw_messages)
            if "messages" in change:
                values = change["messages"]
                if not isinstance(values, (list, tuple)) or len(values) != len(raw_messages):
                    raise ValueError("early Kaguya message count cannot change")
                raw_messages = [_encode(value, encoding, "message") for value in values]
            payload = name_raw + b"\0" + bytes([block.count])
            payload += b"".join(raw + b"\0" for raw in raw_messages)
        if len(payload) > MAX_BLOCK:
            raise ValueError("early Kaguya block exceeds the size budget")
        output += struct.pack("<I", len(payload)) + _xor(payload)
        expected.append((block, name_raw, raw_messages if block.count else choice_raw))
    output += document.trailer
    result = bytes(output)
    again = read_early_message(result, encoding=encoding, strict=strict)
    if len(again.blocks) != len(document.blocks):
        raise ValueError("early Kaguya block count changed on write")
    for index, (block, name_raw, strings) in enumerate(expected):
        check = again.blocks[index]
        want_name = _decode(name_raw, encoding, "name")
        if check.name != want_name:
            raise ValueError(f"early Kaguya block {index} name round trip differs")
        if block.count == 0:
            if check.choice != _decode(strings, encoding, "choice"):
                raise ValueError(f"early Kaguya block {index} choice round trip differs")
        else:
            want = [_decode(raw, encoding, "message") for raw in strings]
            if list(check.messages) != want or check.count != block.count:
                raise ValueError(f"early Kaguya block {index} text round trip differs")
    return result
