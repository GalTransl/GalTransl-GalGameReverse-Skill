"""Hand-built BGI fixtures only, not a production encoder (GPL-3.0-or-later).

Format facts from the exact sources recorded in
provenance/bgi-feedback-archive.json. No imported decoder helpers, upstream
runtime, real-game data or import-time I/O. The key stream uses an independent
closed-form uint32 recurrence rather than the decoder's high/low-word steps.
"""
import struct


DEFAULT_SEED = 0x12345678


def _dsc_frame(depths, output_size, symbol_count, bitstream, *, seed=DEFAULT_SEED):
    """Assemble given (possibly deliberately invalid) lengths and MSB bits."""
    if len(depths) != 512:
        raise ValueError("fixture needs 512 lengths")
    key = seed & 0xffffffff
    table = bytearray()
    for depth in depths:
        mixed = (key * 0x015a4e35) & 0xffffffff
        table.append((depth + ((mixed >> 16) & 255)) & 255)
        key = (mixed + 1) & 0xffffffff
    header = b"DSC FORMAT 1.00\0" + struct.pack("<4I", seed, output_size, symbol_count, 0)
    return header + table + bitstream


def literal_dsc(payload: bytes, seed: int = DEFAULT_SEED) -> bytes:
    """All 256 literals have canonical depth 8: payload is its own MSB stream."""
    if not isinstance(payload, bytes):
        raise TypeError("fixture payload must be bytes")
    return _dsc_frame([8] * 256 + [0] * 256, len(payload), len(payload), payload, seed=seed)


def overlap_dsc() -> bytes:
    """A=0, B=10, match(length=5)=11, distance=2: 01011 + twelve zero bits.

    This manual three-symbol stream produces ABABABA and requires overlapping
    copy semantics; neither a literal fixture nor a general match encoder.
    """
    depths = [0] * 512
    depths[65], depths[66], depths[259] = 1, 2, 2
    return _dsc_frame(depths, 7, 3, b"\x58\0\0")


def pack_archive(files: list[tuple[str, bytes]], version: int = 2) -> bytes:
    """Assemble sequential synthetic V1/V2 records; no filesystem operations."""
    if version == 1:
        magic, stride, name_size = b"PackFile    ", 0x20, 0x10
    elif version == 2:
        magic, stride, name_size = b"BURIKO ARC20", 0x80, 0x60
    else:
        raise ValueError("fixture version must be 1 or 2")
    table, body = bytearray(), bytearray()
    for name, data in files:
        encoded = name.encode("cp932", errors="strict")
        if not encoded or b"\0" in encoded or len(encoded) > name_size:
            raise ValueError("fixture name does not fit")
        row = encoded.ljust(name_size, b"\0") + struct.pack("<II", len(body), len(data))
        table.extend(row.ljust(stride, b"\0"))
        body.extend(data)
    return magic + struct.pack("<I", len(files)) + table + body
