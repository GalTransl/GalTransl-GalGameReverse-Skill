"""Itufuru u16 opcode/u16 length/string records, not whole-VM scanning.

Adapted from msg-tool (GPL-3.0-or-later), commit
f72716cee88554d40c1cdface2812493b14ca653,
src/scripts/yaneurao/itufuru/script.rs, ItufuruScript::{new,import_messages}.
"""
import struct

_TEXT_OPS = (0x02, 0x1E)
_RESOURCE_OPS = (0x01, 0x13, 0x27)


def read_record(data: bytes, offset: int = 0, *, encoding: str = "cp932") -> dict:
    """Read at an already established instruction boundary; end is exclusive."""
    if offset < 0 or offset + 4 > len(data):
        raise ValueError("truncated Itufuru record header")
    opcode, size = struct.unpack_from("<HH", data, offset)
    if opcode not in _TEXT_OPS + _RESOURCE_OPS:
        raise ValueError("unsupported Itufuru string opcode")
    end = offset + 4 + size
    if size < 3 or end > len(data):
        raise ValueError("invalid string length (includes NUL)")
    raw = data[offset + 4:end]
    if raw[-1] != 0 or b"\0" in raw[:-1]:
        raise ValueError("length/terminator mismatch")
    if opcode == 2 and not raw[:-1].endswith(b"\n"):
        raise ValueError("opcode 2 requires trailing LF")
    return {"opcode": opcode, "text": raw[:-1].decode(encoding, "strict"),
            "role": "message" if opcode in _TEXT_OPS else "resource",
            "offset": offset, "end": end}


def write_record(opcode: int, text: str, *, encoding: str = "cp932") -> bytes:
    """Build dialogue/choice only; normalize opcode 2's required final LF."""
    if opcode not in _TEXT_OPS:
        raise ValueError("resource strings are not translation targets")
    if "\0" in text:
        raise ValueError("embedded NUL")
    if opcode == 2 and not text.endswith("\n"):
        text += "\n"
    raw = text.encode(encoding, "strict")
    size = len(raw) + 1
    if not 3 <= size <= 65535:
        raise ValueError("Itufuru NUL-inclusive length must fit u16 and be >=3")
    return struct.pack("<HH", opcode, size) + raw + b"\0"
