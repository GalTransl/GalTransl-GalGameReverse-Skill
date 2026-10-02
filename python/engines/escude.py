"""Escu:de ESCR1_00 canonical string pool and engine-specific single-byte mapping.
Source: msg-tool, src/scripts/escude/script.rs, EscudeBinScript::new/import_messages,
StrReplacer::new/replace. Commit f72716cee88554d40c1cdface2812493b14ca653;
source license GPL-3.0-or-later. VM/name enumeration is not implemented.
"""
from dataclasses import dataclass
import struct


@dataclass(frozen=True)
class Script:
    vm: bytes
    unknown: int
    strings: tuple[bytes, ...]


@dataclass(frozen=True)
class Message:
    index: int
    names: tuple[str, ...]
    message: str
    name_writable: bool = False


def read_escr(data: bytes) -> Script:
    """ESCR1_00 -> opaque VM and raw indexed strings; reject non-canonical offsets."""
    if len(data) < 20 or data[:8] != b"ESCR1_00":
        raise ValueError("not ESCR1_00")
    count, = struct.unpack_from("<I", data, 8)
    pos = 12 + count * 4
    if pos + 8 > len(data):
        raise ValueError("truncated ESCR index")
    offsets = struct.unpack_from(f"<{count}I", data, 12) if count else ()
    vm_length, = struct.unpack_from("<I", data, pos)
    pos += 4
    if pos + vm_length + 4 > len(data):
        raise ValueError("truncated ESCR VM")
    vm = data[pos:pos + vm_length]
    pos += vm_length
    unknown, = struct.unpack_from("<I", data, pos)
    pos += 4
    pool_start = pos
    strings = []
    for address in offsets:
        if address != pos - pool_start:
            raise ValueError("ESCR pool has unknown gaps/aliases/order")
        end = data.find(b"\0", pos)
        if end < 0:
            raise ValueError("unterminated ESCR string")
        strings.append(data[pos:end])
        pos = end + 1
    if pos != len(data):
        raise ValueError("unknown ESCR trailing data")
    return Script(vm, unknown, tuple(strings))


def decode_engine_string(raw: bytes) -> str:
    """Escude's !/?/A0..DE mapping -> Unicode, respecting CP932 two-byte trails."""
    glyphs = "！？　。「」、…をぁぃぅぇぉゃゅょっーあいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわん゛゜"
    mapping = dict(zip([0x21, 0x3F, *range(0xA0, 0xDF)], glyphs))
    output, pos = [], 0
    while pos < len(raw):
        byte = raw[pos]
        if byte < 0x80 or 0xA0 <= byte <= 0xDF:
            output.append(mapping[byte] if byte in mapping else bytes((byte,)).decode("cp932"))
            pos += 1
        elif 0x81 <= byte <= 0x9F or 0xE0 <= byte <= 0xEF:
            if pos + 2 > len(raw):
                raise ValueError("incomplete Escude multibyte character")
            output.append(raw[pos:pos + 2].decode("cp932", errors="strict"))
            pos += 2
        else:
            raise ValueError("unsupported Escude JIS byte")
    return "".join(output)


def extract_escr(data: bytes, context_names: dict[int, tuple[str, ...]] | None = None
                 ) -> tuple[Message, ...]:
    """Extract pool order, including empties; external names remain context-only."""
    script = read_escr(data)
    names = context_names or {}
    if names.keys() - set(range(len(script.strings))):
        raise ValueError("context references unknown ESCR string")
    return tuple(Message(i, tuple(names.get(i, ())), decode_engine_string(raw).replace("<r>", "\n"))
                 for i, raw in enumerate(script.strings))


def patch_escr(data: bytes, replacements: dict[int, str], encoding: str = "cp932") -> bytes:
    """Rebuild every pool offset while preserving count, opaque VM and unknown word.

    Only message text can change; enum-script speaker names are not embedded here.
    No VM/string-index count changes, LZW/container handling or reverse kana packing.
    """
    script = read_escr(data)
    if any(type(k) is not int or not 0 <= k < len(script.strings) for k in replacements):
        raise ValueError("unknown ESCR string index")
    pool, offsets = bytearray(), []
    for index, original in enumerate(script.strings):
        raw = original
        if index in replacements:
            text = replacements[index]
            if not isinstance(text, str) or "\0" in text:
                raise ValueError("invalid ESCR text")
            text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<r>")
            raw = text.encode(encoding, errors="strict")
            if b"\0" in raw:
                raise ValueError("encoding incompatible with ESCR cstrings")
        offsets.append(len(pool))
        pool.extend(raw + b"\0")
    if len(pool) > 0xFFFFFFFF:
        raise ValueError("ESCR pool exceeds u32 offsets")
    table = b"".join(struct.pack("<I", value) for value in offsets)
    return (b"ESCR1_00" + struct.pack("<I", len(offsets)) + table
            + struct.pack("<I", len(script.vm)) + script.vm
            + struct.pack("<I", script.unknown) + pool)
