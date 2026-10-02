"""NORI fixed-slot extraction/reinsertion; never truncates translations.

Adapted from msg-tool (GPL-3.0-or-later), commit
f72716cee88554d40c1cdface2812493b14ca653,
src/scripts/hexen_haus/bin.rs, BinScript::{new,import_messages}.
Slot discovery is the upstream two-byte heuristic, not a VM parser.
"""
from dataclasses import dataclass
from collections.abc import Mapping


@dataclass(frozen=True)
class Slot:
    offset: int
    capacity: int
    text: str


def _plain(data: bytes) -> bytes:
    if not data.startswith(b"NORI"):
        raise ValueError("expected NORI signature")
    return bytes(b ^ 0x53 for b in data)


def read_slots(data: bytes, *, encoding: str = "cp932") -> tuple[Slot, ...]:
    """Discover source-compatible slots; offsets refer to the whole file."""
    plain = _plain(data)
    marker = plain.find(b"_beginrp")
    if marker < 0 or marker + 16 > len(plain):
        raise ValueError("missing or truncated _beginrp marker")
    start = pos = marker + 16
    if (len(plain) - pos) % 2:
        raise ValueError("odd-length NORI two-byte stream")
    buf = bytearray()
    slots = []

    def emit():
        if len(buf) > 2:
            slots.append(Slot(start, len(buf), bytes(buf).decode(encoding, "strict")))

    while pos < len(plain):
        pair = plain[pos:pos + 2]
        pos += 2
        if pair[0] == 0x53:
            if len(buf) > 2:
                try:
                    keep = bytes(buf[-2:]).decode(encoding, "strict") in ("」", "。", "』")
                except UnicodeDecodeError:
                    keep = False
                if not keep:
                    del buf[-2:]
            emit()
            start = pos
            buf.clear()
        elif pair[1] == 0x53:
            emit()
            start = pos
            buf.clear()
        else:
            buf.extend(pair)
    if len(buf) > 2:
        del buf[-2:]
        emit()
    return tuple(slots)


def patch_slots(data: bytes, replacements: Mapping[int, str], *,
                encoding: str = "cp932") -> bytes:
    """Replace discovered slot indexes; preserve all other bytes and file size.

    Capacity is encoded bytes, not characters. Short text is space padded.
    This intentionally does NOT merge a previous slot into an inferred name.
    """
    slots = read_slots(data, encoding=encoding)
    if any(type(i) is not int or not 0 <= i < len(slots) for i in replacements):
        raise ValueError("unknown slot index")
    plain = bytearray(_plain(data))
    for index, text in replacements.items():
        slot = slots[index]
        raw = text.encode(encoding, "strict")
        if len(raw) > slot.capacity:
            raise ValueError(f"slot {index} needs {len(raw)} bytes; capacity {slot.capacity}")
        raw = raw.ljust(slot.capacity, b" ")
        # 0x53 in either byte is interpreted as a separator by the scanner.
        if 0x53 in raw or b"\0" in raw:
            raise ValueError("translation collides with NORI control bytes")
        plain[slot.offset:slot.offset + slot.capacity] = raw
    return bytes(b ^ 0x53 for b in plain)


def split_name(text: str) -> dict:
    """Split an inline name at 「; never steal a preceding message slot."""
    i = text.find("「")
    return {"name": text[:i] if i > 0 else None,
            "message": text[i:] if i > 0 else text}
