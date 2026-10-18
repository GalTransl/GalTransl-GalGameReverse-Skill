# SPDX-License-Identifier: GPL-3.0-only
"""Unity ``.bin``/``.idx`` pair: AES-CBC records with a MsgPack directory.

``.idx`` is a sequence of ``i32 length`` plus that many AES-CBC/PKCS#7 bytes.
Each decrypted record is a MsgPack map with ``fileName`` (str), ``index`` and
``size`` (integers). ``.bin`` stores, per member, ``u32 size`` followed by the
AES-CBC ciphertext; ``index`` points at the ciphertext, not at the size field.

Key and IV are the two ASCII constants used by the reference tool. They are
per-sample dialect parameters, not a property of Unity or of this container in
general; a different build needs its own key pair.

MsgPack support here is the subset the reference writes plus tolerant decoding
of the standard integer/string/float forms. It is not a general MsgPack library.

Provenance: layout, key/IV and the MsgPack field names follow
``GameRes.Unity.ArcBIN`` and ``BinDeserializer`` in the GARbro-derived code
bundled with "翻译肋手 v4.9D". Independent rewrite: strict record bounds, an
explicit check that the padded ciphertext length matches the directory, and a
writer that recomputes offsets from the size-prefixed layout instead of
carrying a running counter that double counts.
"""
from dataclasses import dataclass
import struct

from python.common import aes

KEY = b"c6eahbq9sjuawhvdr9kvhpsm5qv393ga"
IV = b"ARC-PACKPASSWORD"
MAX_ENTRIES = 100_000
MAX_RECORD = 64 << 20
MAX_MEMBER = 256 << 20

POSITIVE_FIXINT = 0x7F
FIXMAP = 0x80
FIXSTR = 0xA0
STR16 = 0xDA
INT32 = 0xD2
NIL = 0xC0
BIN8, BIN16, BIN32 = 0xC4, 0xC5, 0xC6
FLOAT32, FLOAT64 = 0xCA, 0xCB


@dataclass(frozen=True)
class ArcEntry:
    name: str
    offset: int
    size: int


@dataclass(frozen=True)
class IndexEntry:
    name: str
    offset: int
    size: int


class _Unpacker:
    def __init__(self, data):
        self.data = data
        self.pos = 0

    def need(self, count):
        if self.pos + count > len(self.data):
            raise ValueError("MsgPack record is truncated")

    def u8(self):
        self.need(1)
        value = self.data[self.pos]
        self.pos += 1
        return value

    def take(self, count):
        self.need(count)
        value = self.data[self.pos:self.pos + count]
        self.pos += count
        return value

    def number(self):
        marker = self.u8()
        if marker <= POSITIVE_FIXINT:
            return marker
        if marker == NIL:
            return None
        if marker == 0xCC:
            return self.u8()
        if marker == 0xCD:
            return struct.unpack(">H", self.take(2))[0]
        if marker == 0xCE:
            return struct.unpack(">I", self.take(4))[0]
        if marker == 0xCF:
            return struct.unpack(">Q", self.take(8))[0]
        if marker == 0xD0:
            return struct.unpack(">b", self.take(1))[0]
        if marker == 0xD1:
            return struct.unpack(">h", self.take(2))[0]
        if marker == INT32:
            return struct.unpack(">i", self.take(4))[0]
        if marker == 0xD3:
            return struct.unpack(">q", self.take(8))[0]
        raise ValueError(f"unsupported MsgPack scalar {marker:#04x}")

    def string(self):
        marker = self.u8()
        if FIXSTR <= marker <= 0xBF:
            return self.take(marker & 0x1F).decode("utf-8")
        if marker in (0xD9, STR16, 0xDB):
            size = {0xD9: 1, STR16: 2, 0xDB: 4}[marker]
            length = int.from_bytes(self.take(size), "big")
            return self.take(length).decode("utf-8")
        raise ValueError(f"unsupported MsgPack string {marker:#04x}")

    def value(self):
        peek = self.data[self.pos] if self.pos < len(self.data) else None
        if peek is None:
            raise ValueError("MsgPack record is truncated")
        if 0xA0 <= peek <= 0xBF or peek in (0xD9, STR16, 0xDB):
            return self.string()
        if 0x80 <= peek <= 0x8F or peek in (0xDE, 0xDF):
            self.u8()
            count = peek & 0x0F
            if peek == 0xDE:
                count = struct.unpack(">H", self.take(2))[0]
            elif peek == 0xDF:
                count = struct.unpack(">I", self.take(4))[0]
            result = {}
            for _ in range(count):
                key = self.string()
                result[key] = self.value()
            return result
        if 0x90 <= peek <= 0x9F or peek in (0xDC, 0xDD):
            self.u8()
            count = peek & 0x0F
            if peek == 0xDC:
                count = struct.unpack(">H", self.take(2))[0]
            elif peek == 0xDD:
                count = struct.unpack(">I", self.take(4))[0]
            return [self.value() for _ in range(count)]
        if peek in (0xC2, 0xC3):
            self.u8()
            return peek == 0xC3
        if peek in (BIN8, BIN16, BIN32):
            self.u8()
            size = {BIN8: 1, BIN16: 2, BIN32: 4}[peek]
            length = int.from_bytes(self.take(size), "big")
            return self.take(length)
        if peek in (FLOAT32, FLOAT64):
            self.u8()
            return struct.unpack(">f" if peek == FLOAT32 else ">d", self.take(4 if peek == FLOAT32 else 8))[0]
        return self.number()


def unpack_record(data):
    """Decode one MsgPack value and require it to consume the record exactly."""
    unpacker = _Unpacker(data)
    value = unpacker.value()
    if unpacker.pos != len(data):
        raise ValueError("MsgPack record has trailing bytes")
    return value


def _pack_str(text, *, force16=False):
    raw = text.encode("utf-8")
    if not raw:
        return b"\xa0"
    if len(raw) <= 31 and not force16:
        return bytes([0xA0 | len(raw)]) + raw
    if len(raw) <= 0xFFFF:
        return b"\xda" + struct.pack(">H", len(raw)) + raw
    raise ValueError("MsgPack string is too long")


def _pack_int32(value):
    if not -(1 << 31) <= value < (1 << 31):
        raise ValueError("MsgPack integer out of int32 range")
    return b"\xd2" + struct.pack(">I", value & 0xFFFFFFFF)


def pack_record(name, offset, size):
    """Write the reference's three-field map in its original field order."""
    if not isinstance(name, str) or not name:
        raise ValueError("index record needs a fileName")
    return (b"\x83" + _pack_str("fileName") + _pack_str(name, force16=True)
            + _pack_str("index") + _pack_int32(offset)
            + _pack_str("size") + _pack_int32(size))


def read_index(idx_data):
    """Decrypt and parse every directory record of a ``.idx`` file."""
    if not isinstance(idx_data, bytes) or not idx_data:
        raise ValueError("Unity idx is empty")
    entries, pos = [], 0
    while pos < len(idx_data):
        if pos + 4 > len(idx_data):
            raise ValueError("Unity idx record length is truncated")
        size = struct.unpack_from("<i", idx_data, pos)[0]
        pos += 4
        if not 0 < size <= MAX_RECORD or pos + size > len(idx_data):
            raise ValueError("Unity idx record size out of range")
        if size % 16:
            raise ValueError("Unity idx ciphertext is not block aligned")
        plain = aes.cbc_decrypt(idx_data[pos:pos + size], KEY, IV)
        pos += size
        record = unpack_record(plain)
        if not isinstance(record, dict):
            raise ValueError("Unity idx record is not a map")
        name = record.get("fileName")
        offset = record.get("index")
        length = record.get("size")
        if not isinstance(name, str) or not isinstance(offset, int) or not isinstance(length, int):
            raise ValueError("Unity idx record lacks fileName/index/size")
        name = name.lstrip("/\\")
        if not name or not isinstance(length, int) or not 0 <= length <= MAX_MEMBER:
            raise ValueError(f"Unity idx entry {name!r} is invalid")
        entries.append(IndexEntry(name, offset, length))
        if len(entries) > MAX_ENTRIES:
            raise ValueError("Unity idx entry count out of range")
    return tuple(entries)


def read_member(bin_data, entry):
    """Decrypt one member; ``entry.offset`` points at the ciphertext."""
    if not 0 <= entry.offset <= len(bin_data) - entry.size:
        raise ValueError("Unity member is outside the bin file")
    cipher = bin_data[entry.offset:entry.offset + entry.size]
    if entry.size % 16:
        raise ValueError("Unity member ciphertext is not block aligned")
    return aes.cbc_decrypt(cipher, KEY, IV)


def build_bin(members):
    """Write a matching ``(bin, idx)`` pair; members must be unique names."""
    if not isinstance(members, dict) or not 1 <= len(members) <= MAX_ENTRIES:
        raise ValueError("Unity bin needs 1..100000 members")
    bin_data, idx_data = bytearray(), bytearray()
    for name, payload in members.items():
        if not isinstance(name, str) or not isinstance(payload, bytes):
            raise ValueError("invalid Unity member")
        if len(payload) > MAX_MEMBER:
            raise ValueError(f"Unity member {name!r} is too large")
        cipher = aes.cbc_encrypt(payload, KEY, IV)
        offset = len(bin_data) + 4
        bin_data += struct.pack("<I", len(cipher)) + cipher
        record = aes.cbc_encrypt(pack_record(name, offset, len(cipher)), KEY, IV)
        idx_data += struct.pack("<i", len(record)) + record
    result = (bytes(bin_data), bytes(idx_data))
    entries = read_index(result[1])
    if len(entries) != len(members):
        raise ValueError("Unity idx entry count changed on build")
    for entry, (name, payload) in zip(entries, members.items()):
        if entry.name != name or read_member(result[0], entry) != payload:
            raise ValueError(f"Unity member {name!r} does not round trip")
    return result
