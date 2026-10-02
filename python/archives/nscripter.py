"""Standalone NScripter nscript.dat/SAR/plain NSA reference.

nscript.dat is XOR 0x84 (no intrinsic magic). SAR/NSA use big-endian indexes.
NSA supports method 0 and NBZ/bzip2 (method 4), including the optional two-zero
header prefix. SPB, LZSS, password-encrypted NSA and unknown methods fail.
No compression code from NScripter's separately sourced unpackers is copied.
No NScripter command parser is implied by decrypting bytes. Names are untrusted.

Reference: GARbro-Mod, ArcFormats/NScripter/{Script,ArcSAR,ArcNSA}.cs,
NSOpener.ConvertFrom/ConvertBack, SarOpener.TryOpen/Create,
NsaOpener.ReadIndex/UnpackEntry/Create; commit
bc26d991ef5cdc0e1ecb32122ee9a48c3375750c (MIT file headers).
Copyright (C) 2014-2015, 2023 by morkt

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
import bz2
from dataclasses import dataclass
import struct


@dataclass(frozen=True)
class Entry:
    name: str
    data: bytes
    offset: int
    stored_size: int
    compression: str


def _range(data, offset, size):
    if offset < 0 or size < 0 or offset > len(data) or size > len(data) - offset:
        raise ValueError("NScripter archive range outside input")
    return data[offset:offset + size]


def xor_nscript(data: bytes, *, max_size: int = 64 << 20) -> bytes:
    """Encode/decode nscript.dat; caller establishes filename/engine identity."""
    if not isinstance(data, bytes) or len(data) > max_size:
        raise ValueError("nscript input type/size")
    return bytes(value ^ 0x84 for value in data)


def decode_nbz(data: bytes, *, max_output_size: int = 64 << 20,
               max_input_size: int = 80 << 20) -> bytes:
    """NBZ = big-endian uncompressed length + exactly one bzip2 stream."""
    if not isinstance(data, bytes) or len(data) > max_input_size:
        raise ValueError("NBZ input type/size")
    if min(max_input_size, max_output_size) < 0:
        raise ValueError("negative NBZ limit")
    expected, = struct.unpack(">I", _range(data, 0, 4))
    if expected > max_output_size:
        raise ValueError("NBZ output budget")
    decoder = bz2.BZ2Decompressor()
    try:
        result = decoder.decompress(data[4:], max_length=expected + 1)
    except (OSError, EOFError) as exc:
        raise ValueError("invalid NBZ bzip2 stream") from exc
    if len(result) != expected or not decoder.eof or decoder.unused_data:
        raise ValueError("NBZ size/truncation/trailing-data mismatch")
    return result


def _extract(data, nsa, max_entries, max_file_size, max_total_size, max_archive_size):
    if not isinstance(data, bytes) or len(data) > max_archive_size:
        raise ValueError("NScripter archive input type/size")
    if min(max_entries, max_file_size, max_total_size, max_archive_size) < 0:
        raise ValueError("negative NScripter limit")
    start = 2 if nsa and data[:2] == b"\0\0" else 0
    count, relative_base = struct.unpack(">HI", _range(data, start, 6))
    if not 0 < count <= min(max_entries, 32767):
        raise ValueError("NScripter invalid entry count")
    base, pos = start + relative_base, start + 6
    if not pos <= base <= len(data):
        raise ValueError("NScripter invalid data base")
    records, names, total = [], set(), 0
    for _ in range(count):
        end = data.find(b"\0", pos, min(base, pos + 4097))
        if end <= pos:
            raise ValueError("missing/empty/overlong NScripter filename")
        name = data[pos:end].decode("cp932", errors="strict")
        if name in names:
            raise ValueError("duplicate NScripter filename")
        pos = end + 1
        fields = 13 if nsa else 8
        if fields > base - pos:
            raise ValueError("NScripter index overlaps data")
        if nsa:
            method, rel, stored_size, raw_size = struct.unpack_from(">BIII", data, pos)
        else:
            rel, stored_size = struct.unpack_from(">II", data, pos)
            method, raw_size = 0, stored_size
        pos += fields
        if method not in (0, 4):
            raise ValueError("unsupported NSA compression (SPB/LZSS/unknown)")
        offset = base + rel
        stored = _range(data, offset, stored_size)
        codec = "none"
        # GARbro also recognizes NBZ by suffix even when the index says None.
        if nsa and (method == 4 or name.lower().endswith(".nbz")):
            expected, = struct.unpack(">I", _range(stored, 0, 4))
            if method == 4 and raw_size != expected:
                raise ValueError("NSA/NBZ uncompressed length disagreement")
            if method == 0 and raw_size not in (stored_size, expected):
                raise ValueError("NSA suffix-NBZ length disagreement")
            if total + expected > max_total_size:
                raise ValueError("NScripter total output budget")
            payload = decode_nbz(stored, max_output_size=max_file_size)
            codec = "nbz"
        else:
            if raw_size != stored_size:
                raise ValueError("NSA uncompressed entry size disagreement")
            if stored_size > max_file_size or total + stored_size > max_total_size:
                raise ValueError("NScripter output budget")
            payload = stored
        names.add(name)
        total += len(payload)
        records.append(Entry(name, payload, offset, stored_size, codec))
    if pos != base:
        raise ValueError("unsupported NScripter index padding/variant")
    return records


def extract_sar(data: bytes, *, max_entries: int = 32767,
                max_file_size: int = 64 << 20, max_total_size: int = 256 << 20,
                max_archive_size: int = 512 << 20) -> list[Entry]:
    """Read strict SAR: u16 BE count, u32 BE base, C-string + rel/size."""
    return _extract(data, False, max_entries, max_file_size, max_total_size, max_archive_size)


def extract_nsa(data: bytes, *, max_entries: int = 32767,
                max_file_size: int = 64 << 20, max_total_size: int = 256 << 20,
                max_archive_size: int = 512 << 20) -> list[Entry]:
    """Read plain NSA; decrypting password-protected indexes is unsupported."""
    return _extract(data, True, max_entries, max_file_size, max_total_size, max_archive_size)


def _build(files, nsa, compression, max_total_size, max_archive_size):
    if not 0 < len(files) <= 32767 or compression not in (0, 4):
        raise ValueError("invalid NScripter file count/compression")
    if min(max_total_size, max_archive_size) < 0:
        raise ValueError("negative NScripter budget")
    names, encoded_names, index, body, total = set(), set(), bytearray(), bytearray(), 0
    for name, payload in files:
        if not isinstance(name, str) or not name or "\0" in name or name in names:
            raise ValueError("empty/NUL/duplicate NScripter filename")
        if not isinstance(payload, bytes):
            raise ValueError("NScripter payload requires bytes")
        encoded = name.encode("cp932", errors="strict")
        if len(encoded) > 4096 or encoded in encoded_names:
            raise ValueError("NScripter name limit/duplicate CP932 spelling")
        names.add(name)
        encoded_names.add(encoded)
        total += len(payload)
        if total > min(max_total_size, 0xffffffff):
            raise ValueError("NScripter input budget/u32 limit")
        if nsa and not compression and name.lower().endswith(".nbz"):
            raise ValueError("use compression=4 for decoded .nbz content")
        stored = struct.pack(">I", len(payload)) + bz2.compress(payload) if compression else payload
        index.extend(encoded + b"\0")
        if nsa:
            index.extend(struct.pack(">BIII", compression, len(body), len(stored), len(payload)))
        else:
            index.extend(struct.pack(">II", len(body), len(stored)))
        if 6 + len(index) + len(body) + len(stored) > min(max_archive_size, 0xffffffff):
            raise ValueError("NScripter archive budget/u32 limit")
        body.extend(stored)
    base = 6 + len(index)
    return struct.pack(">HI", len(files), base) + index + body


def build_sar(files: list[tuple[str, bytes]], *, max_total_size: int = 256 << 20,
              max_archive_size: int = 512 << 20) -> bytes:
    """Build a new SAR (strict CP932 names), not a byte-identical patch."""
    return _build(files, False, 0, max_total_size, max_archive_size)


def build_nsa(files: list[tuple[str, bytes]], *, compression: int = 0,
              max_total_size: int = 256 << 20, max_archive_size: int = 512 << 20) -> bytes:
    """Build plain NSA; compression is 0 (raw) or 4 (NBZ) for every input."""
    return _build(files, True, compression, max_total_size, max_archive_size)
