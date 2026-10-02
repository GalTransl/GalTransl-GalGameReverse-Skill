"""Circus MES token codec, NOT a complete MES relocator.

Algorithm adapted from msg-tool (GPL-3.0-or-later), commit
f72716cee88554d40c1cdface2812493b14ca653:
src/scripts/circus/{script.rs,info.rs}, CircusMesScript::{new,extract_messages,
import_messages}, ScriptInfo. Explicit game profile is mandatory.
"""
from dataclasses import dataclass
import struct


@dataclass(frozen=True)
class Profile:
    version: int
    byte_pairs: tuple[int, int]
    byte_strings: tuple[int, int]
    strings: tuple[int, int]
    encrypted_strings: tuple[int, int]
    word_quads: tuple[int, int]
    plain_message_opcode: int
    decode_key: int
    name_opcode: int

    def __post_init__(self):
        if not 0 <= self.version <= 65535:
            raise ValueError("version must fit u16")
        for interval in (self.byte_pairs, self.byte_strings, self.strings,
                         self.encrypted_strings, self.word_quads):
            if len(interval) != 2 or not 0 <= interval[0] <= interval[1] <= 255:
                raise ValueError("invalid opcode interval")
        if any(not 0 <= x <= 255 for x in
               (self.plain_message_opcode, self.decode_key, self.name_opcode)):
            raise ValueError("opcode/key must fit u8")


def _contains(interval, value):
    return interval != (255, 255) and interval[0] <= value <= interval[1]


def read_header(data: bytes, *, profile: Profile) -> dict:
    """Validate count-derived header and explicit version; return code offset."""
    if len(data) < 8:
        raise ValueError("truncated MES header")
    count, second = struct.unpack_from("<ii", data)
    if count < 0:
        raise ValueError("negative block count")
    new = second == 3
    version_at = count * (6 if new else 4) + 4
    code_at = version_at + (3 if new else 2)
    if version_at < 4 or code_at > len(data):
        raise ValueError("MES block table exceeds file")
    version = struct.unpack_from("<H", data, version_at)[0]
    if version != profile.version:
        raise ValueError("profile/version mismatch; do not guess a game key")
    return {"version": version, "new_header": new, "code_offset": code_at,
            "block_table_offset": 8 if new else 4}


def read_token(data: bytes, offset: int, *, profile: Profile,
               encoding: str = "cp932") -> dict:
    """Read one instruction at a proven boundary; end is exclusive."""
    if not 0 <= offset < len(data):
        raise ValueError("invalid token offset")
    opcode = data[offset]
    start = offset + 1
    text = None
    if _contains(profile.byte_pairs, opcode):
        end = offset + 3
    elif _contains(profile.byte_strings, opcode):
        start += 1
        end = data.find(b"\0", start) + 1
    elif (_contains(profile.strings, opcode) or
          _contains(profile.encrypted_strings, opcode)):
        end = data.find(b"\0", start) + 1
        if end:
            raw = data[start:end - 1]
            if _contains(profile.encrypted_strings, opcode):
                raw = bytes((b + profile.decode_key) & 255 for b in raw)
                text = raw.decode(encoding, "strict")
            elif opcode == profile.plain_message_opcode:
                text = raw.decode(encoding, "strict")
    elif _contains(profile.word_quads, opcode):
        end = offset + 9
    else:
        raise ValueError(f"unknown opcode {opcode:#x}")
    if end <= start or end > len(data):
        # Empty zero-terminated strings are valid (end == start + 1).
        raise ValueError("truncated instruction or missing terminator")
    return {"offset": offset, "end": end, "opcode": opcode, "text": text,
            "role": "name" if text is not None and opcode == profile.name_opcode
            else "message" if text is not None else None}


def write_text_token(text: str, opcode: int, *, profile: Profile,
                     encoding: str = "cp932") -> bytes:
    """Build only [opcode][encoded text][NUL], rejecting terminator collisions."""
    encrypted = _contains(profile.encrypted_strings, opcode)
    if not encrypted and not (opcode == profile.plain_message_opcode and
                              _contains(profile.strings, opcode)):
        raise ValueError("opcode is not a dialogue/name token in this profile")
    if "\0" in text:
        raise ValueError("NUL in text")
    raw = text.encode(encoding, "strict")
    if encrypted:
        raw = bytes((b - profile.decode_key) & 255 for b in raw)
    if b"\0" in raw:
        raise ValueError("encoded text collides with MES string terminator")
    return bytes([opcode]) + raw + b"\0"
