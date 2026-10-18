# SPDX-License-Identifier: GPL-3.0-only
"""EntisGLS .csx "Cotopha" container: chunk directory, conststr table, CS literals.

Container layout (all little-endian, offsets from file start):
  0   8   magic, first five bytes ``Entis`` (remaining three are not interpreted)
  8   4   opaque word
  12  4   opaque word
  16  48  signature block, first 18 bytes ``Cotopha Image file``
  64  ... chunk sequence: 8-byte ASCII name, int64 payload size, payload
          ends at the first zero name byte; bytes from there to EOF are a trailer

``conststr`` payload: int32 entry count, then per entry
  int32 char count, char_count*2 bytes UTF-16LE, int32 extra count, extra*int32.
``image`` payload: CS bytecode whose string literals are ``int32 char count``
  (``0`` = absent, ``0x80000000`` = reference, followed by an int32) plus
  char_count*2 bytes UTF-16LE.

Provenance: the layout and the bytecode operand table follow the GARbro-derived
``GameRes.EntisGLS.ArcCSX`` implementation shipped inside the third-party tool
"翻译肋手 v4.9D" (see the decompiled copy's README). This is an independent
rewrite: strict bounds, unknown opcodes raise instead of resynchronising, and the
whole image payload must be consumed exactly for a walk to be reported.

Scope: directory, conststr read/write (variable length), image literals read and
fixed-length patch. Not supported: other chunk semantics, CS evaluation, growing
image literals (jump targets are not rewritten), chunk reordering.
"""
from dataclasses import dataclass
import struct

MAGIC = b"Entis"
SIGNATURE = b"Cotopha Image file"
HEADER_SIZE = 64
CHUNK_HEADER = 16
CONST = "conststr"
IMAGE = "image"

# CSInstructionCode operand table. Only opcodes whose operand shape is explicit
# in the reference are listed; anything else aborts the walk.
MODE_MAX = 8
VAR_OBJECT = 0
VAR_REFERENCE = 1
VAR_ARRAY = 2
VAR_HASH = 3
VAR_INTEGER = 4
VAR_REAL = 5
VAR_STRING = 6
VAR_INTEGER64 = 7
VAR_POINTER = 8
VAR_CLASS_OBJECT = 9
VAR_BOOLEAN = 10
VAR_INT8 = 11
VAR_UINT8 = 12
VAR_INT16 = 13
VAR_UINT16 = 14
VAR_INT32 = 15
VAR_UINT32 = 16
VAR_MAX_SIMPLE = 16
LITERAL_REFERENCE = 0x80000000


@dataclass(frozen=True)
class Chunk:
    name: str
    offset: int          # offset of the 8-byte name
    payload: bytes

    @property
    def payload_offset(self):
        return self.offset + CHUNK_HEADER


@dataclass(frozen=True)
class Literal:
    """A length-prefixed UTF-16 literal located in the container."""

    section: str
    offset: int          # absolute offset of the length field
    chars: int           # stored char count; 0 means the entry holds no text
    text: str
    extras: tuple = ()

    @property
    def maxlength(self):
        return self.chars * 2

    @property
    def writable(self):
        return self.chars > 0 and self.section == CONST


def _i32(data, pos):
    if pos < 0 or pos + 4 > len(data):
        raise ValueError("truncated int32")
    return struct.unpack_from("<i", data, pos)[0], pos + 4


def parse_chunks(data):
    """Return the chunk directory of a .csx file; trailer bytes stay unparsed."""
    if not isinstance(data, bytes) or len(data) < HEADER_SIZE + CHUNK_HEADER:
        raise ValueError("csx too small")
    if data[:5] != MAGIC or data[16:16 + len(SIGNATURE)] != SIGNATURE:
        raise ValueError("not an Entis Cotopha image file")
    chunks, pos = [], HEADER_SIZE
    while pos < len(data) and data[pos] != 0:
        if pos + CHUNK_HEADER > len(data):
            raise ValueError("truncated chunk header")
        raw = data[pos:pos + 8]
        try:
            name = raw.decode("ascii")
        except UnicodeDecodeError as exc:
            raise ValueError("non-ASCII chunk name") from exc
        size, = struct.unpack_from("<q", data, pos + 8)
        if size < 0 or pos + CHUNK_HEADER + size > len(data):
            raise ValueError(f"chunk {name.strip()!r} exceeds the file")
        chunks.append(Chunk(name.strip(), pos, data[pos + CHUNK_HEADER:pos + CHUNK_HEADER + size]))
        pos += CHUNK_HEADER + size
    if not chunks:
        raise ValueError("csx has no chunks")
    if len({chunk.name for chunk in chunks}) != len(chunks):
        raise ValueError("duplicate chunk name")
    return chunks


def build_csx(original, chunks):
    """Rebuild a .csx from ``original`` header/trailer plus replacement chunks."""
    names = {chunk.name for chunk in chunks}
    kept = [chunk for chunk in parse_chunks(original) if chunk.name not in names]
    ordered = sorted(list(chunks) + kept, key=lambda chunk: chunk.offset)
    body = bytearray()
    for chunk in ordered:
        if len(chunk.name) > 8 or not chunk.name.isascii():
            raise ValueError("chunk name must be ASCII and at most 8 bytes")
        payload = chunk.payload
        if len(payload) > 0x7FFFFFFF:
            raise ValueError("chunk payload exceeds limit")
        body += chunk.name.ljust(8).encode("ascii") + struct.pack("<q", len(payload)) + payload
    trailer_at = max(chunk.offset + CHUNK_HEADER + len(chunk.payload)
                     for chunk in parse_chunks(original))
    trailer = original[trailer_at:] if trailer_at <= len(original) else b""
    return bytes(original[:HEADER_SIZE]) + bytes(body) + trailer


def _chunk(data, name):
    found = [chunk for chunk in parse_chunks(data) if chunk.name == name]
    if len(found) > 1:
        raise ValueError(f"duplicate {name} chunk")
    return found[0] if found else None


def parse_conststr(data):
    """Parse every conststr slot, including empty ones, in declaration order."""
    chunk = _chunk(data, CONST)
    if chunk is None:
        return []
    payload, base = chunk.payload, chunk.payload_offset
    count, pos = _i32(payload, 0)
    if not 0 <= count <= 1_000_000:
        raise ValueError("conststr count out of range")
    entries = []
    for index in range(count):
        at = pos
        chars, pos = _i32(payload, pos)
        if chars < 0 or chars > 0x10000:
            raise ValueError(f"conststr entry {index} char count out of range")
        raw = payload[pos:pos + chars * 2]
        if len(raw) != chars * 2:
            raise ValueError(f"conststr entry {index} is truncated")
        pos += chars * 2
        try:
            text = raw.decode("utf-16-le")
        except UnicodeDecodeError as exc:
            raise ValueError(f"conststr entry {index} is not UTF-16LE") from exc
        extras_count, pos = _i32(payload, pos)
        if not 0 <= extras_count <= 0x10000:
            raise ValueError(f"conststr entry {index} extras out of range")
        extras = []
        for _ in range(extras_count):
            value, pos = _i32(payload, pos)
            extras.append(value)
        entries.append(Literal(CONST, base + at, chars, text, tuple(extras)))
    if pos != len(payload):
        raise ValueError("trailing bytes in conststr payload")
    return entries


def rebuild_conststr(data, replacements):
    """Rewrite conststr slots; entries may grow because the chunk is rebuilt."""
    entries = parse_conststr(data)
    if not isinstance(replacements, dict) or set(replacements) - set(range(len(entries))):
        raise ValueError("unknown conststr entry")
    if any(not entries[index].writable for index in replacements):
        raise ValueError("empty conststr slots are placeholders and stay untouched")
    body = bytearray(struct.pack("<i", len(entries)))
    total = 0
    for index, entry in enumerate(entries):
        text = replacements.get(index, entry.text)
        if not isinstance(text, str) or "\0" in text:
            raise ValueError("invalid conststr text")
        encoded = text.encode("utf-16-le", errors="strict")
        if len(encoded) > 0x20000:
            raise ValueError("conststr entry exceeds limit")
        total += len(encoded)
        if total > 32 << 20:
            raise ValueError("conststr payload exceeds budget")
        body += struct.pack("<i", len(encoded) // 2) + encoded
        body += struct.pack("<i", len(entry.extras))
        body += b"".join(struct.pack("<i", value) for value in entry.extras)
    rebuilt = build_csx(data, [Chunk(CONST, _chunk(data, CONST).offset, bytes(body))])
    check = parse_conststr(rebuilt)
    if len(check) != len(entries):
        raise ValueError("conststr entry count changed")
    for index, (before, after) in enumerate(zip(entries, check)):
        if after.text != replacements.get(index, before.text) or after.extras != before.extras:
            raise ValueError(f"conststr entry {index} round trip differs")
    return rebuilt


class _Walker:
    """Strict CS bytecode walker: every operand is bounded, unknown ops abort."""

    def __init__(self, payload):
        self.data = payload
        self.pos = 0
        self.literals = []

    def need(self, count):
        if self.pos + count > len(self.data):
            raise ValueError(f"image truncated at {self.pos}")

    def u8(self):
        self.need(1)
        value = self.data[self.pos]
        self.pos += 1
        return value

    def i32(self):
        self.need(4)
        value = struct.unpack_from("<i", self.data, self.pos)[0]
        self.pos += 4
        return value

    def u32(self):
        self.need(4)
        value = struct.unpack_from("<I", self.data, self.pos)[0]
        self.pos += 4
        return value

    def i64(self):
        self.need(8)
        value = struct.unpack_from("<q", self.data, self.pos)[0]
        self.pos += 8
        return value

    def f64(self):
        self.need(8)
        value = struct.unpack_from("<d", self.data, self.pos)[0]
        self.pos += 8
        return value

    def literal(self, kind):
        at = self.pos
        chars = self.u32()
        if chars == LITERAL_REFERENCE:
            self.i32()
            return
        if chars == 0:
            return
        if chars > 0x10000:
            raise ValueError(f"{kind} literal at {at} exceeds limit")
        self.need(chars * 2)
        raw = self.data[self.pos:self.pos + chars * 2]
        self.pos += chars * 2
        try:
            text = raw.decode("utf-16-le")
        except UnicodeDecodeError as exc:
            raise ValueError(f"{kind} literal at {at} is not UTF-16LE") from exc
        self.literals.append((at, chars, text))

    def mode_and_type(self):
        mode, var = self.u8(), self.u8()
        if mode > MODE_MAX or var > VAR_UINT32:
            raise ValueError(f"unknown CS mode/type {mode}/{var} at {self.pos - 2}")
        return mode, var

    def immediate(self, var):
        if var in (VAR_OBJECT, VAR_STRING):
            self.literal("string")
        elif var == VAR_INTEGER64:
            self.i64()
        elif var == VAR_REAL:
            self.f64()
        elif var in (VAR_INTEGER, VAR_INT32, VAR_UINT32):
            self.i32()
        elif var in (VAR_BOOLEAN, VAR_INT8, VAR_UINT8):
            self.u8()
        elif var in (VAR_INT16, VAR_UINT16):
            self.need(2)
            self.pos += 2
        elif var == VAR_CLASS_OBJECT:
            self.i32()
        elif var in (VAR_REFERENCE, VAR_ARRAY, VAR_HASH, VAR_POINTER):
            pass
        else:
            raise ValueError(f"unsupported immediate type {var} at {self.pos}")

    def walk(self):
        while self.pos < len(self.data):
            at = self.pos
            opcode = self.u8()
            if opcode >= 0x80:
                raise ValueError(f"byte {opcode:#04x} at {at} cannot start an instruction")
            if opcode == 0:                       # csicNew
                _, var = self.mode_and_type()
                if var == VAR_CLASS_OBJECT:
                    self.i32()
                    self.literal("string")
                elif var == VAR_OBJECT:
                    self.literal("string")
                    self.literal("string")
                else:
                    self.literal("string")
            elif opcode == 2:                     # csicLoad
                mode, var = self.mode_and_type()
                if mode == 0:
                    self.immediate(var)
                elif mode == 5:
                    raise ValueError(f"csicLoad with automatic mode at {at}")
                elif var == VAR_INTEGER:
                    self.i32()
                elif var == VAR_STRING:
                    self.literal("string")
                elif var != VAR_REFERENCE:
                    raise ValueError(f"unsupported csicLoad type {var} at {at}")
            elif opcode == 3:                     # csicStore
                self.u8()
            elif opcode == 4:                     # csicEnter
                self.literal("string")
                count = self.i32()
                if count != -1:
                    if not 0 <= count <= 0x10000:
                        raise ValueError(f"csicEnter arity out of range at {at}")
                    for _ in range(count):
                        var = self.u8()
                        if var > VAR_UINT32:
                            raise ValueError(f"unknown csicEnter type {var} at {at}")
                        if var == VAR_CLASS_OBJECT:
                            self.i32()
                            self.literal("string")
                        elif var == VAR_OBJECT:
                            self.literal("string")
                            self.literal("string")
                        else:
                            self.literal("string")
                else:
                    if self.u8() != 0:
                        raise ValueError(f"undefined extension namespace at {at}")
                    self.i32()
            elif opcode in (6, 24, 28):           # jump / pointer / function pointer
                self.i32()
            elif opcode == 7:                     # csicCJump
                self.u8()
                self.i32()
            elif opcode == 8:                     # csicCall
                self.u8()
                self.i32()
                self.literal("string")
            elif opcode in (9, 18):               # return / exReturn
                self.u8()
            elif opcode == 10:                    # csicElement
                var = self.u8()
                if var == VAR_INTEGER:
                    self.i32()
                elif var == VAR_STRING:
                    self.literal("string")
                else:
                    raise ValueError(f"unsupported csicElement type {var} at {at}")
            elif opcode in (12, 13, 14):          # operate / unary / compare
                self.u8()
            elif opcode == 15:                    # csicExOperate
                kind = self.u8()
                if kind == 0:
                    count = self.u32()
                    if count > 0x10000:
                        raise ValueError(f"array dimension out of range at {at}")
                    self.need(count * 4)
                    self.pos += count * 4
                elif kind not in (1, 2):
                    raise ValueError(f"undefined extra operator {kind} at {at}")
            elif opcode == 16:                    # csicExUniOperate
                kind = self.u8()
                if kind == 0:
                    self.i32()
                    self.i32()
                    self.i32()
                elif kind == 1:
                    self.literal("string")
                elif kind > 6:
                    raise ValueError(f"undefined unary operator {kind} at {at}")
            elif opcode == 17:                    # csicExCall
                self.i32()
                mode, var = self.mode_and_type()
                if mode != 0:
                    raise ValueError(f"csicExCall without immediate mode at {at}")
                if var == VAR_STRING:
                    self.literal("string")
                elif var == VAR_INTEGER:
                    self.i32()
                else:
                    raise ValueError(f"unsupported csicExCall type {var} at {at}")
            elif opcode in (19, 20):              # call member / native member
                self.i32()
                self.i32()
                self.i32()
            elif opcode == 21:                    # csicSwap
                self.u8()
                self.i32()
                self.i32()
            elif opcode == 22:                    # csicCreateBuffer
                self.i32()
            elif opcode == 26:                    # csicReferenceForPointer
                self.u8()
            elif opcode == 29:                    # csicCallNativeFunction
                self.i32()
                self.i32()
            else:
                raise ValueError(f"unhandled CS opcode {opcode} at {at}")
        return self.literals


def parse_image(data):
    """Return image literals; the walk must consume the payload exactly."""
    chunk = _chunk(data, IMAGE)
    if chunk is None:
        return []
    walker = _Walker(chunk.payload)
    found = walker.walk()
    if walker.pos != len(chunk.payload):
        raise ValueError("image walk did not end on the payload boundary")
    base = chunk.payload_offset
    return [Literal(IMAGE, base + at, chars, text) for at, chars, text in found]


def patch_image(data, replacements):
    """Patch image literals in place; text must fit the stored char count."""
    literals = parse_image(data)
    if not isinstance(replacements, dict) or set(replacements) - set(range(len(literals))):
        raise ValueError("unknown image literal")
    buffer = bytearray(data)
    expected = {}
    for index, text in sorted(replacements.items()):
        literal = literals[index]
        if not isinstance(text, str) or "\0" in text:
            raise ValueError("invalid image text")
        encoded = text.encode("utf-16-le", errors="strict")
        if len(encoded) // 2 > literal.chars:
            raise ValueError(f"image literal {index} cannot grow ({literal.chars} chars)")
        padding = literal.chars - len(encoded) // 2
        at = literal.offset + 4
        buffer[at:at + literal.chars * 2] = encoded + b" \x00" * padding
        # Fixed-length slots are space padded, so the reparsed value keeps them.
        expected[index] = text + " " * padding
    check = parse_image(bytes(buffer))
    for index, literal in enumerate(check):
        if literal.text != expected.get(index, literals[index].text):
            raise ValueError(f"image literal {index} round trip differs")
    return bytes(buffer)
