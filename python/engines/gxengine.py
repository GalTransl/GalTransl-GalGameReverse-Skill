# SPDX-License-Identifier: GPL-3.0-only
"""GxEngine V3 MWB wrapper and tagged big-endian-length string fields."""
from dataclasses import dataclass
import re
import struct
import zlib

TAG = re.compile(rb"[\x08\x05]\x1A\x00\x00[\x00-\x02][\x00-\xFF]")


@dataclass(frozen=True)
class Field:
    length_offset: int
    start: int
    end: int
    raw: bytes
    kind: int


def unpack_mwb(data: bytes, *, max_output: int = 64 * 1024 * 1024) -> bytes:
    """Source 0x1c header: LE unpacked/compressed sizes at 0x14/0x18."""
    if len(data) < 0x1C:
        raise ValueError("truncated MWB header")
    size, packed_size = struct.unpack_from("<II", data, 0x14)
    if packed_size != len(data) - 0x1C or not 0 <= size <= max_output:
        raise ValueError("MWB size mismatch or output limit")
    body = data[0x1C:]
    if size == packed_size:
        return body
    dec = zlib.decompressobj()
    raw = dec.decompress(body, size + 1)
    if len(raw) != size or not dec.eof or dec.unused_data or dec.unconsumed_tail:
        raise ValueError("invalid MWB zlib stream")
    return raw


def scan_fields(payload: bytes, *, encoding: str = "utf-8") -> tuple[Field, ...]:
    """The six-byte signature ends in a four-byte BE length; retain 05 controls."""
    fields = []
    pos = 0
    while True:
        match = TAG.search(payload, pos)
        if match is None:
            break
        start = match.end()
        size = int.from_bytes(payload[start - 4:start], "big")
        end = start + size
        if end > len(payload):
            raise ValueError("tagged MWB field exceeds payload")
        raw = payload[start:end]
        raw.decode(encoding)  # strict: do not skip malformed candidates invisibly
        fields.append(Field(start - 4, start, end, raw, payload[match.start()]))
        pos = end
    return tuple(fields)


def replace_fields(data: bytes, replacements: dict[int, str], *, encoding: str = "utf-8", compress: bool = True) -> bytes:
    """Rewrite local field lengths plus wrapper sizes; no GXP archive writing."""
    payload = unpack_mwb(data)
    fields = scan_fields(payload, encoding=encoding)
    if any(type(i) is not int or not 0 <= i < len(fields) for i in replacements):
        raise ValueError("unknown MWB field")
    out = bytearray(payload)
    for index in sorted(replacements, reverse=True):
        field = fields[index]
        raw = replacements[index].encode(encoding)
        # The source recognizer permits only 00 00 [00..02] xx lengths.
        if len(raw) > 0x2FF:
            raise ValueError("replacement exceeds the verified MWB tag-length profile")
        out[field.length_offset:field.end] = struct.pack(">I", len(raw)) + raw
    body = bytes(out)
    packed = zlib.compress(body) if compress else body
    if compress and len(packed) == len(body):
        # Equal sizes are interpreted as uncompressed by this format reader.
        packed = body
    return data[:0x14] + struct.pack("<II", len(body), len(packed)) + packed
