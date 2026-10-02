# SPDX-License-Identifier: GPL-3.0-only
# Adapted from SExtractor tools/SystemC/fpk_pack_SystemB3.py and src/reg.yaml:_BIN_SystemC
# Source commit: 8d8d976fd04ae54e7c677705af937273d04a376a
# Upstream attribution: satan53x / SExtractor contributors.
"""SystemC ZLC2 and encrypted-tail-index FPK (Tomefure variant).

FPK/ZLC2 layout informed by GARbro-Mod ArcFormats/Interheart/ArcFPK.cs,
commit bc26d991ef5cdc0e1ecb32122ee9a48c3375750c.
Copyright (C) 2015-2016 by morkt.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to
deal in the Software without restriction, including without limitation the
rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
sell copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
IN THE SOFTWARE.
"""
# Layer split: archives; format algorithms and original notices retained.
# Companion module: python/engines/systemc.py
import struct
from dataclasses import dataclass

from ..common.binary import FormatError
from ..common.safety import Limits, validate_names


def encode_zlc2_literals(data):
    """ZLC2 + u32 original size + groups (00, up to eight literal bytes)."""
    out = bytearray(b"ZLC2" + struct.pack("<I", len(data)))
    for pos in range(0, len(data), 8):
        out.append(0)
        out.extend(data[pos:pos + 8])
    return bytes(out)


def decode_zlc2_literals(data, *, max_output=64 * 1024 * 1024):
    if len(data) < 8 or data[:4] != b"ZLC2":
        raise ValueError("not ZLC2")
    expected = struct.unpack_from("<I", data, 4)[0]
    if expected > max_output:
        raise ValueError("ZLC2 output exceeds budget")
    out, pos = bytearray(), 8
    while len(out) < expected:
        n = min(8, expected - len(out))
        if pos + n + 1 > len(data) or data[pos] != 0:
            raise ValueError("truncated or nonliteral ZLC2 group; full LZ decoder required")
        out.extend(data[pos + 1:pos + 1 + n])
        pos += n + 1
    if pos != len(data):
        raise ValueError("unparsed ZLC2 tail")
    return bytes(out)


def decode_zlc2(data, *, max_output=64 << 20):
    """MSB-first controls; 12-bit backward distance, 4-bit length plus 3.

    Distance zero means 4096. Overlapping copies are intentional. The format
    reader clips the last match to the declared size; missing input never
    becomes implicit zero bytes. Unused final control bits may be nonzero.
    """
    if len(data) < 8 or data[:4] != b"ZLC2":
        raise FormatError("not ZLC2")
    expected = struct.unpack_from("<I", data, 4)[0]
    if expected > max_output:
        raise FormatError("ZLC2 output exceeds budget")
    out, pos = bytearray(), 8
    while len(out) < expected:
        if pos >= len(data):
            raise FormatError("truncated ZLC2 control")
        control = data[pos]
        pos += 1
        for mask in (128, 64, 32, 16, 8, 4, 2, 1):
            if len(out) == expected:
                break
            if control & mask:
                if pos + 2 > len(data):
                    raise FormatError("truncated ZLC2 match")
                distance = data[pos] | ((data[pos + 1] & 0xF0) << 4)
                distance = distance or 4096
                count = min((data[pos + 1] & 15) + 3, expected - len(out))
                pos += 2
                if distance > len(out):
                    raise FormatError("ZLC2 match before output start")
                for _ in range(count):
                    out.append(out[-distance])
            else:
                if pos >= len(data):
                    raise FormatError("truncated ZLC2 literal")
                out.append(data[pos])
                pos += 1
    if data[pos:] not in (b"", b"\0"):
        raise FormatError("unparsed ZLC2 tail")
    return bytes(out)


def decode_member(data, *, max_output=64 << 20, max_layers=4):
    for _ in range(max_layers):
        if not data.startswith(b"ZLC2"):
            if len(data) > max_output:
                raise FormatError("FPK member exceeds budget")
            return data
        data = decode_zlc2(data, max_output=max_output)
    if data.startswith(b"ZLC2"):
        raise FormatError("too many nested ZLC2 layers")
    return data


@dataclass(frozen=True)
class FpkEntry:
    name: str
    offset: int
    size: int
    raw_index: bytes


@dataclass(frozen=True)
class FpkIndex:
    entries: tuple[FpkEntry, ...]
    offset: int
    key: bytes
    size: int


def read_fpk_index(data, *, limits=Limits()):
    """Read only the high-bit-count, XOR tail-index variant. No guessing widths."""
    if len(data) < 12 or len(data) > limits.max_total_bytes:
        raise FormatError("FPK input outside budget")
    tagged_count = struct.unpack_from("<I", data)[0]
    count = tagged_count & 0x7FFFFFFF
    if not tagged_count & 0x80000000 or not 0 < count <= limits.max_entries:
        raise FormatError("not a supported encrypted-index FPK")
    offset = struct.unpack_from("<I", data, len(data) - 4)[0]
    index_size = count * 36
    if offset < 4 or offset + index_size > len(data) - 8:
        raise FormatError("FPK index outside archive")
    key = data[-8:-4]
    raw = bytes(v ^ key[i & 3] for i, v in enumerate(data[offset:offset + index_size]))
    entries = []
    for pos in range(0, index_size, 36):
        record = raw[pos:pos + 36]
        start, size = struct.unpack_from("<II", record)
        try:
            name = record[8:32].split(b"\0", 1)[0].decode("cp932", errors="strict")
        except UnicodeError as exc:
            raise FormatError("invalid FPK name encoding") from exc
        if not name or "/" in name or "\\" in name:
            raise FormatError("FPK variant requires flat names")
        if start < 4 or start + size > len(data) - 8 or size > limits.max_file_bytes:
            raise FormatError("FPK member outside bounds/budget")
        entries.append(FpkEntry(name, start, size, record))
    validate_names([e.name for e in entries], limits)
    spans = sorted([(e.offset, e.offset + e.size) for e in entries] + [(offset, offset + index_size)])
    end = 4
    for start, stop in spans:
        if start < end:
            raise FormatError("overlapping FPK members/index")
        end = stop
    return FpkIndex(tuple(entries), offset, key, len(data))


def unpack_fpk(data, *, limits=Limits()):
    index = read_fpk_index(data, limits=limits)
    members, total = {}, 0
    for entry in index.entries:
        payload = decode_member(data[entry.offset:entry.offset + entry.size],
                                max_output=min(limits.max_file_bytes, limits.max_total_bytes - total))
        total += len(payload)
        members[entry.name] = payload
    return index, members


def rebuild_fpk(data, replacements, *, limits=Limits()):
    """Rebuild layout and encrypted index, preserving gaps, order and opaque u32s.

    Index can be in the middle of the data (observed in Tomefure). Original
    compressed streams survive unchanged members; edits use one literal layer.
    Sizes include the 8-byte ZLC2 header. Does not write any filesystem path.
    """
    index = read_fpk_index(data, limits=limits)
    if set(replacements) - {e.name for e in index.entries}:
        raise FormatError("replacement is not an FPK member")
    total = 0
    payloads = {}
    for entry in index.entries:
        packed = data[entry.offset:entry.offset + entry.size]
        if entry.name in replacements:
            new = replacements[entry.name]
            if not isinstance(new, bytes) or len(new) > limits.max_file_bytes:
                raise FormatError("FPK replacement outside budget")
            total += len(new)
            if total > limits.max_total_bytes:
                raise FormatError("FPK replacements exceed total budget")
            old = decode_member(packed, max_output=limits.max_file_bytes)
            if new != old:
                packed = encode_zlc2_literals(new) if packed.startswith(b"ZLC2") else new
        payloads[entry.name] = packed
    spans = [(e.offset, e.size, e) for e in index.entries]
    spans.append((index.offset, len(index.entries) * 36, None))
    out, cursor, locations, new_index_offset = bytearray(data[:4]), 4, {}, None
    for start, size, entry in sorted(spans, key=lambda item: item[0]):
        out.extend(data[cursor:start])
        if entry is None:
            new_index_offset = len(out)
            out.extend(bytes(size))
        else:
            locations[entry.name] = len(out)
            out.extend(payloads[entry.name])
        cursor = start + size
        if len(out) > limits.max_total_bytes:
            raise FormatError("rebuilt FPK exceeds budget")
    out.extend(data[cursor:-8])
    raw = bytearray()
    for entry in index.entries:
        record = bytearray(entry.raw_index)
        struct.pack_into("<II", record, 0, locations[entry.name], len(payloads[entry.name]))
        raw.extend(record)
    encrypted = bytes(v ^ index.key[i & 3] for i, v in enumerate(raw))
    out[new_index_offset:new_index_offset + len(raw)] = encrypted
    out.extend(index.key + struct.pack("<I", new_index_offset))
    if len(out) > limits.max_total_bytes:
        raise FormatError("rebuilt FPK exceeds budget")
    read_fpk_index(out, limits=limits)
    return bytes(out)
