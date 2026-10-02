"""SystemNNN fixed .nnn slots plus .spt item/word-address primitives.

Adapted from VNTextPatch-net8 (MIT), commit
d9c0fab7b72fdcf87d674ef12a84d3829c9188be,
VNTextPatch.Shared/Scripts/SystemNnn/SystemNnnDevScript.cs (GetTextRanges,
WritePatched), SystemNnnReleaseScript.cs (Load/GetSptItems/FormatFileText).
.spt full text-reference relocation is NOT implemented.
"""
from dataclasses import dataclass
from collections.abc import Mapping
import struct

MESSAGE_HEADER = b"--MESSAGEDATA  \0"
COMMAND_HEADER = b"-COMMANDDATA   \0"


@dataclass(frozen=True)
class Slot:
    offset: int
    capacity: int
    message_type: int
    text: str


def read_nnn_slots(data: bytes, *, encoding: str = "cp932") -> tuple[Slot, ...]:
    """Recognize marker-based development format, preserve fixed capacities."""
    slots = []
    occupied = []
    found = False
    for magic in (MESSAGE_HEADER, COMMAND_HEADER):
        pos = 0
        while True:
            at = data.find(magic, pos)
            if at < 0:
                break
            found = True
            header_size = 0x50 if magic == MESSAGE_HEADER else 0x60
            if at + header_size > len(data):
                raise ValueError("truncated NNN section header")
            if magic == MESSAGE_HEADER:
                kind = struct.unpack_from("<i", data, at + 0x10)[0]
                extra = struct.unpack_from("<i", data, at + 0x4C)[0]
                capacity = struct.unpack_from("<i", data, at + 0x3C)[0]
                if extra < 0 or kind not in (0, 1, 2, 3):
                    raise ValueError("unsupported NNN message type/table length")
                start = at + 0x50 + 4 * extra
                selected = kind != 3  # Draw is deliberately not dialogue.
            else:
                command = struct.unpack_from("<i", data, at + 0x20)[0]
                capacity = struct.unpack_from("<i", data, at + 0x24)[0]
                start, kind, selected = at + 0x60, 0, command == 4
            end = start + capacity
            if capacity < 0 or start > len(data) or end > len(data):
                raise ValueError("NNN text capacity exceeds file")
            if any(at < b and end > a for a, b in occupied):
                raise ValueError("overlapping NNN sections")
            occupied.append((at, end))
            if selected:
                stop = data.find(b"\0", start, end)
                if stop < 0:
                    raise ValueError("NNN slot has no bounded NUL terminator")
                slots.append(Slot(start, capacity, kind, data[start:stop].decode(encoding, "strict")))
            pos = end
    if not found:
        raise ValueError("no NNN section signature found")
    return tuple(sorted(slots, key=lambda slot: slot.offset))


def patch_nnn(data: bytes, replacements: Mapping[int, str], *, encoding: str = "cp932") -> bytes:
    """Patch discovered slots, keep original post-NUL padding and all addresses."""
    slots = read_nnn_slots(data, encoding=encoding)
    result = bytearray(data)
    for index, text in replacements.items():
        if type(index) is not int or not 0 <= index < len(slots):
            raise ValueError("unknown NNN slot index")
        if "\0" in text:
            raise ValueError("embedded NUL")
        raw = text.encode(encoding, "strict") + b"\0"
        slot = slots[index]
        if len(raw) > slot.capacity:
            raise ValueError("NNN translation exceeds fixed byte capacity including NUL")
        result[slot.offset:slot.offset + len(raw)] = raw
    return bytes(result)


def word_to_offset(word_address: int) -> int:
    if type(word_address) is not int or not 0 <= word_address < (1 << 31):
        raise ValueError("SPT address must be a nonnegative i32 word index")
    return word_address * 4


def offset_to_word(offset: int) -> int:
    if type(offset) is not int or offset < 0 or offset % 4 or offset // 4 >= (1 << 31):
        raise ValueError("SPT byte offset must be nonnegative and 4-byte aligned")
    return offset // 4


def read_spt_items(data: bytes) -> tuple[dict, ...]:
    """XOR-FF decrypt and walk length-in-WORDS items; no dialogue discovery."""
    if not data or len(data) % 4:
        raise ValueError("SPT must contain complete 4-byte words")
    plain = bytes(b ^ 255 for b in data)
    words = struct.unpack("<" + "i" * (len(plain) // 4), plain)
    result = []
    index = 0
    while index < len(words):
        size = words[index]
        if size < 2 or index + size > len(words):
            raise ValueError("invalid SPT item length in words")
        identify = words[index + 1]
        has_code = identify in (0x66660001, 0x66660006)
        if has_code and size < 3:
            raise ValueError("missing SPT item code")
        code = words[index + 2] if has_code else None
        if code == 0x55550002 and size < 4:
            raise ValueError("missing SPT data table type")
        result.append({"word_index": index, "offset": word_to_offset(index),
                       "length_words": size, "identify": identify, "code": code})
        index += size
    if result[0]["identify"] != 0x66660001 or result[0]["code"] != 0x55550001 or result[0]["length_words"] < 8:
        raise ValueError("invalid SPT data header")
    for count_at, table_at in ((4, 5), (6, 7)):
        count, table = words[count_at], words[table_at]
        if count < 0 or table < 0 or table + count > len(words):
            raise ValueError("SPT text table exceeds file")
    return tuple(result)


def encode_spt_text(text: str, *, encoding: str = "cp932") -> bytes:
    """Return a DECRYPTED NUL-terminated, four-byte-aligned string block."""
    if "\0" in text:
        raise ValueError("embedded NUL")
    raw = text.encode(encoding, "strict") + b"\0"
    return raw + b"\0" * (-len(raw) % 4)
