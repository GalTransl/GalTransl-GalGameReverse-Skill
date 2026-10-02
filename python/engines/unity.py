# SPDX-License-Identifier: GPL-3.0-only
"""UTAGE mono DAT aligned string records ONLY, not Unity assets generally."""
from dataclasses import dataclass
import struct


@dataclass(frozen=True)
class AlignedString:
    length_offset: int
    start: int
    end: int
    next_offset: int
    text: str
    raw: bytes


def decode_aligned_string(data: bytes, length_offset: int, *, encoding: str = "utf-8", max_length: int = 16 * 1024 * 1024) -> AlignedString:
    """Explicit candidate offset: LE byte length, bytes, (-length)%4 zero padding.

    No printable-byte regex guessing, so strings cannot absorb the next length.
    """
    if length_offset < 0 or length_offset + 4 > len(data):
        raise ValueError("truncated UTAGE length")
    size = struct.unpack_from("<I", data, length_offset)[0]
    if not 0 <= size <= max_length:
        raise ValueError("UTAGE string length exceeds limit")
    start = length_offset + 4
    end = start + size
    next_offset = end + (-size % 4)
    if next_offset > len(data):
        raise ValueError("truncated UTAGE string/padding")
    if any(data[end:next_offset]):
        raise ValueError("nonzero alignment padding; not the supported profile")
    raw = data[start:end]
    return AlignedString(length_offset, start, end, next_offset, raw.decode(encoding), raw)


def encode_aligned_string(text: str, *, encoding: str = "utf-8") -> bytes:
    """Encode one local record; byte length, not Unicode character count."""
    raw = text.encode(encoding)
    return struct.pack("<I", len(raw)) + raw + bytes(-len(raw) % 4)


def replace_aligned_string(data: bytes, length_offset: int, text: str, *, encoding: str = "utf-8") -> bytes:
    """Whole-DAT patch only when record's aligned footprint does not change.

    Use encode_aligned_string for isolated records. Unknown outer sizes/offsets
    make shifting a full serialized DAT unsafe, so that operation is refused.
    """
    old = decode_aligned_string(data, length_offset, encoding=encoding)
    replacement = encode_aligned_string(text, encoding=encoding)
    if len(replacement) != old.next_offset - length_offset:
        raise NotImplementedError("UTAGE outer DAT/Unity serialized-object relocation not implemented")
    return data[:length_offset] + replacement + data[old.next_offset:]
