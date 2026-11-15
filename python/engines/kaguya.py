"""Kaguya [SCR-MESSAGE]ver4.0 tables; NOT SExtractor's 02/03 variant.

Adapted from VNTextPatch-net8 (MIT), commit
d9c0fab7b72fdcf87d674ef12a84d3829c9188be,
VNTextPatch.Shared/Scripts/KaguyaScript.cs, ReadString/ReadMessage/
ReadMessageGroup/WriteString/WriteMessage. Preserve indexes, voices and header.
"""
from dataclasses import dataclass, field
import struct

MAGIC = b"[SCR-MESSAGE]ver4.0"


@dataclass(frozen=True)
class Message:
    text: str
    voices: tuple[str, ...] = ()


@dataclass(frozen=True)
class Group:
    name_index: int
    message_indexes: tuple[int, ...]


@dataclass(frozen=True)
class Document:
    header: bytes
    names: tuple[str, ...]
    choices: tuple[str, ...]
    messages: tuple[Message, ...]
    groups: tuple[Group, ...]
    trailer: bytes = b""
    # Decrypted bytes, retained only for unchanged fields (CP932 has aliases).
    raw_names: tuple[bytes, ...] = field(default=(), compare=False, repr=False)
    raw_choices: tuple[bytes, ...] = field(default=(), compare=False, repr=False)
    raw_messages: tuple[bytes, ...] = field(default=(), compare=False, repr=False)


class _Reader:
    def __init__(self, data):
        self.data, self.pos = data, 0

    def take(self, size):
        if size < 0 or self.pos + size > len(self.data):
            raise ValueError("truncated ver4 field")
        result = self.data[self.pos:self.pos + size]
        self.pos += size
        return result

    def integer(self, fmt="<i"):
        return struct.unpack(fmt, self.take(struct.calcsize(fmt)))[0]

    def count(self, minimum):
        count = self.integer()
        if count < 0 or count > 1_000_000 or count > (len(self.data) - self.pos) // minimum:
            raise ValueError("invalid ver4 table count")
        return count


def _recode(raw, before, after):
    # Walk SJIS codepoint boundaries; never replace across two characters.
    result = bytearray()
    pos = 0
    while pos < len(raw):
        width = 2 if 0x81 <= raw[pos] <= 0x9F or 0xE0 <= raw[pos] <= 0xFC else 1
        if pos + width > len(raw):
            raise ValueError("truncated SJIS pair")
        part = raw[pos:pos + width]
        result.extend(after if part == before else part)
        pos += width
    return bytes(result)


def _decode(raw):
    return _recode(raw, b"\xf0\x40", b"\x81\x93").decode("cp932", "strict")


def _encode(text):
    # These are length-prefixed fields; embedded NUL is data, unlike voices.
    return _recode(text.encode("cp932", "strict"), b"\x81\x93", b"\xf0\x40")


def _xor(raw, key):
    return bytes(b ^ key for b in raw)


def _key(header):
    if len(header) != 0x15 or not header.startswith(MAGIC):
        raise ValueError("expected 21-byte ver4 header, not ver02/ver03")
    return header[0x14] if header[0x13] else 0


def _message_block(r, key):
    """One ``i32 size + xor(i32 text size + text + u8 voices + voice names)`` block."""
    body = _Reader(_xor(r.take(r.integer()), key))
    raw = body.take(body.integer())
    voices = []
    for _ in range(body.integer("<B")):
        name = bytearray()
        while True:
            unit = body.take(2)
            if unit == b"\0\0":
                break
            name.extend(unit)
        voices.append(bytes(name).decode("utf-16-le", "strict"))
    if body.pos != len(body.data):
        raise ValueError("unconsumed message bytes")
    return raw, tuple(voices)


def read_message_dat(data: bytes, *, allow_trailer: bool = False,
                     max_bytes: int = 64 << 20) -> Document:
    """Validate ver4 tables; opt in to retaining an uninterpreted suffix.

    Counts define the table boundary. The suffix is never scanned for text or
    treated as additional groups. Strict rejection remains the default.
    """
    if len(data) > max_bytes:
        raise ValueError("ver4 input exceeds budget")
    r = _Reader(data)
    header = r.take(0x15)
    key = _key(header)

    def string():
        size = r.integer("<h")
        return _xor(r.take(size), key)

    raw_names = tuple(string() for _ in range(r.count(2)))
    names = tuple(_decode(s) for s in raw_names)
    raw_choices = tuple(string() for _ in range(r.count(2)))
    choices = tuple(_decode(s) for s in raw_choices)
    messages = []
    raw_messages = []
    for _ in range(r.count(9)):
        raw, voices = _message_block(r, key)
        raw_messages.append(raw)
        messages.append(Message(_decode(raw), voices))
    groups = []
    for _ in range(r.count(5)):
        name = r.integer()
        if name < -1 or name >= len(names):
            raise ValueError("invalid group name index")
        indexes = tuple(r.integer() for _ in range(r.integer("<B")))
        if any(i < 0 or i >= len(messages) for i in indexes):
            raise ValueError("invalid group message index")
        groups.append(Group(name, indexes))
    if r.pos != len(data) and not allow_trailer:
        raise ValueError("unconsumed ver4 trailing bytes")
    return Document(header, names, choices, tuple(messages), tuple(groups), data[r.pos:],
                    raw_names, raw_choices, tuple(raw_messages))


def _stale_record(r, key):
    """Consume one stale message block or group entry; ValueError if neither fits."""
    mark = r.pos
    try:
        _decode(_message_block(r, key)[0])
        return "message_blocks"
    except ValueError:
        r.pos = mark
    name = r.integer()
    indexes = [r.integer() for _ in range(r.integer("<B"))]
    # Bounded, non-empty groups only: zero padding must not count as records.
    if not indexes or not -1 <= name < 1 << 16 or any(not 0 <= i < 1 << 24 for i in indexes):
        raise ValueError("not a stale group")
    return "groups"


def stale_records(trailer: bytes, header: bytes) -> dict:
    """Measure how much of a suffix is leftover ver4 records.

    A message.dat rewritten in place without truncation keeps the tail of the
    longer file it replaced: the end of one record, whole message blocks and/or
    group entries, possibly from several earlier files in a row. Those bytes
    lie outside every declared table, so no group or message index reaches
    them. Records are only counted in runs of four (or up to EOF) so stray
    bytes cannot pass as one; everything else is reported as unexplained.
    """
    key = _key(header)
    r = _Reader(trailer)
    result = {"message_blocks": 0, "groups": 0, "runs": 0, "unexplained_bytes": 0}
    synced = False
    while r.pos < len(trailer):
        mark = r.pos
        if synced:
            try:
                result[_stale_record(r, key)] += 1
                continue
            except ValueError:
                r.pos, synced = mark, False
        run = []
        try:
            while len(run) < 4 and r.pos < len(trailer):
                run.append(_stale_record(r, key))
        except ValueError:
            r.pos = mark + 1
            result["unexplained_bytes"] += 1
            continue
        for kind in run:
            result[kind] += 1
        result["runs"] += 1
        synced = True
    return result


def write_message_dat(doc: Document, *, max_bytes: int = 64 << 20) -> bytes:
    """Rebuild original indexed tables; no name/message deduplication or tunnel."""
    key = _key(doc.header)
    out = bytearray(doc.header)

    def encoded(text, originals, index):
        if index < len(originals) and _decode(originals[index]) == text:
            return originals[index]
        return _encode(text)

    def append(raw):
        if len(out) + len(raw) > max_bytes:
            raise ValueError("ver4 output exceeds budget")
        out.extend(raw)

    for table, originals in ((doc.names, doc.raw_names), (doc.choices, doc.raw_choices)):
        out.extend(struct.pack("<i", len(table)))
        for i, text in enumerate(table):
            raw = encoded(text, originals, i)
            if len(raw) > 32767:
                raise ValueError("ver4 string exceeds signed-i16 length")
            append(struct.pack("<h", len(raw)) + _xor(raw, key))
    out.extend(struct.pack("<i", len(doc.messages)))
    for i, message in enumerate(doc.messages):
        raw = encoded(message.text, doc.raw_messages, i)
        if len(raw) > max_bytes:
            raise ValueError("ver4 message exceeds budget")
        if len(message.voices) > 255:
            raise ValueError("voice count exceeds u8")
        body = bytearray(struct.pack("<i", len(raw)) + raw + bytes([len(message.voices)]))
        for voice in message.voices:
            if "\0" in voice:
                raise ValueError("NUL in voice name")
            body.extend(voice.encode("utf-16-le", "strict") + b"\0\0")
        append(struct.pack("<i", len(body)) + _xor(body, key))
    out.extend(struct.pack("<i", len(doc.groups)))
    for group in doc.groups:
        if group.name_index < -1 or group.name_index >= len(doc.names):
            raise ValueError("invalid group name index")
        if len(group.message_indexes) > 255 or any(i < 0 or i >= len(doc.messages) for i in group.message_indexes):
            raise ValueError("invalid group message indexes/count")
        append(struct.pack("<iB", group.name_index, len(group.message_indexes)))
        for i in group.message_indexes:
            append(struct.pack("<i", i))
    append(doc.trailer)
    return bytes(out)
