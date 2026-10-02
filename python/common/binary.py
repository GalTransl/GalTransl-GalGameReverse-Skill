"""Bounded binary primitives and explicit old-to-new offset mapping.

New implementation for this skill. The mapping contract is informed by
VNTextPatch-net8, VNTextPatch.Shared/Util/BinaryPatcher.cs (MIT), commit
 d9c0fab7b72fdcf87d674ef12a84d3829c9188be. No game opcode is inferred here.
See provenance/NOTICE.md. This is NOT a generic script rewriter.
"""

from dataclasses import dataclass
import struct
import zlib


class FormatError(ValueError):
    """Malformed data or a condition outside a reference's supported subset."""


def checked_slice(data: bytes, offset: int, size: int) -> bytes:
    if type(offset) is not int or type(size) is not int:
        raise FormatError("offset and size must be integers")
    if offset < 0 or size < 0 or offset > len(data) or size > len(data) - offset:
        raise FormatError(f"range {offset}+{size} exceeds {len(data)} bytes")
    return data[offset:offset + size]


class Reader:
    def __init__(self, data: bytes):
        self.data = bytes(data)
        self.pos = 0

    def take(self, size: int) -> bytes:
        result = checked_slice(self.data, self.pos, size)
        self.pos += size
        return result

    def unpack(self, fmt: str) -> tuple:
        if not fmt or fmt[0] not in "<>":
            raise FormatError("use an explicit little- or big-endian format")
        return struct.unpack(fmt, self.take(struct.calcsize(fmt)))

    def u32(self) -> int:
        return self.unpack("<I")[0]

    def terminated(self, *, unit: int = 1, max_bytes: int = 1 << 20) -> bytes:
        if unit not in (1, 2, 4) or max_bytes < unit:
            raise FormatError("invalid string scan bounds")
        start = self.pos
        stop = min(len(self.data), start + max_bytes)
        for end in range(start, stop - unit + 1, unit):
            if self.data[end:end + unit] == bytes(unit):
                self.pos = end + unit
                return self.data[start:end]
        raise FormatError("unterminated or oversized string")


def bounded_zlib(data: bytes, *, max_output: int, expected_size: int | None = None) -> bytes:
    """Decode exactly one zlib stream, without unbounded output allocation."""
    if type(max_output) is not int or max_output < 0:
        raise FormatError("invalid output limit")
    if expected_size is not None and not 0 <= expected_size <= max_output:
        raise FormatError("declared output exceeds limit")
    decoder = zlib.decompressobj()
    try:
        result = decoder.decompress(data, max_output + 1)
    except zlib.error as exc:
        raise FormatError(f"invalid zlib stream: {exc}") from exc
    if len(result) > max_output or decoder.unconsumed_tail:
        raise FormatError("decompressed output exceeds limit")
    if not decoder.eof or decoder.unused_data:
        raise FormatError("truncated stream or trailing compressed data")
    if expected_size is not None and len(result) != expected_size:
        raise FormatError("decompressed length disagrees with header")
    return result


@dataclass(frozen=True)
class Edit:
    start: int
    end: int
    replacement: bytes


@dataclass(frozen=True)
class OffsetMap:
    old_size: int
    new_size: int
    edits: tuple[Edit, ...]

    def map(self, offset: int) -> int:
        """Map boundaries/unchanged bytes; reject addresses inside edited spans."""
        if type(offset) is not int or not 0 <= offset <= self.old_size:
            raise FormatError("address outside original file")
        delta = 0
        for edit in self.edits:
            if offset < edit.start:
                break
            if offset == edit.start:
                return offset + delta
            if offset < edit.end:
                raise FormatError("cannot infer an address inside a replaced span")
            delta += len(edit.replacement) - (edit.end - edit.start)
        return offset + delta


def apply_edits(data: bytes, edits: list[Edit]) -> tuple[bytes, OffsetMap]:
    """Apply known nonempty spans, returning an UNFINISHED binary and offset map.

    The caller must still repair every length, pointer, jump, checksum and
    wrapper specific to its format. No automatic string search is performed.
    """
    ordered = tuple(sorted(edits, key=lambda item: item.start))
    chunks = []
    previous = 0
    for edit in ordered:
        if not isinstance(edit.replacement, bytes):
            raise FormatError("replacement must be bytes")
        checked_slice(data, edit.start, edit.end - edit.start)
        if edit.start < previous or edit.start == edit.end:
            raise FormatError("overlapping spans or ambiguous zero-length insertion")
        chunks.extend((data[previous:edit.start], edit.replacement))
        previous = edit.end
    chunks.append(data[previous:])
    result = b"".join(chunks)
    return result, OffsetMap(len(data), len(result), ordered)


def relocate_u32(data: bytes, modified: bytes, mapping: OffsetMap,
                 fields: list[int], *, base: int = 0, unit: int = 1,
                 endian: str = "<") -> bytes:
    """Repair explicitly enumerated u32 references relative to a mapped base.

    Not suitable for signed relative jumps, constant-pool indices, mixed bases,
    pointers into replaced strings, or an incomplete field inventory.
    """
    if endian not in ("<", ">") or type(unit) is not int or unit <= 0:
        raise FormatError("invalid address encoding")
    if len(data) != mapping.old_size or len(modified) != mapping.new_size:
        raise FormatError("offset map belongs to different buffer sizes")
    result = bytearray(modified)
    new_base = mapping.map(base)
    occupied: set[int] = set()
    for field in fields:
        raw = checked_slice(data, field, 4)
        if any(field < edit.end and field + 4 > edit.start for edit in mapping.edits):
            raise FormatError("address field overlaps an edit")
        new_field = mapping.map(field)
        if mapping.map(field + 4) != new_field + 4:
            raise FormatError("address field overlaps an edit")
        if occupied.intersection(range(new_field, new_field + 4)):
            raise FormatError("duplicate or overlapping address fields")
        occupied.update(range(new_field, new_field + 4))
        target = base + struct.unpack(endian + "I", raw)[0] * unit
        delta = mapping.map(target) - new_base
        if delta < 0 or delta % unit or delta // unit > 0xFFFFFFFF:
            raise FormatError("relocated address cannot be represented")
        checked_slice(result, new_field, 4)
        struct.pack_into(endian + "I", result, new_field, delta // unit)
    return bytes(result)
