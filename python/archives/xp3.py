"""Strict, standalone, unencrypted XP3 v1 reference; bytes in, records/bytes out.

Only File/info/segm/adlr, raw or zlib index, and raw/zlib segments are supported.
No executable overlay, chained index, crypt/filter, or obfuscated index support.
The caller must establish that no game-specific filter applies and pass
filter_name="none"; zero info flags alone cannot prove that fact.
Returned names are untrusted and MUST go through the caller's safe output layer.

Format reference: GARbro-Mod, ArcFormats/KiriKiri/ArcXP3.cs,
Xp3Opener.TryOpen/Create/OpenEntry, commit
bc26d991ef5cdc0e1ecb32122ee9a48c3375750c (MIT).
Copyright (C) 2014-2017 by morkt

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
from dataclasses import dataclass
import struct
import zlib

MAGIC = b"XP3\r\n \n\x1a\x8bg\x01"


@dataclass(frozen=True)
class Entry:
    name: str
    data: bytes
    adler32: int
    segment_count: int


def _range(data, offset, size):
    if offset < 0 or size < 0 or offset > len(data) or size > len(data) - offset:
        raise ValueError("XP3 range outside input")
    return data[offset:offset + size]


def _inflate(data, expected, limit):
    if expected < 0 or expected > limit:
        raise ValueError("XP3 inflated size limit")
    decoder = zlib.decompressobj()
    try:
        result = decoder.decompress(data, expected + 1)
    except zlib.error as exc:
        raise ValueError("invalid XP3 zlib stream") from exc
    if (len(result) != expected or not decoder.eof or decoder.unconsumed_tail
            or decoder.unused_data):
        raise ValueError("XP3 zlib size/truncation/trailing-data mismatch")
    return result


def _chunks(data):
    pos = 0
    while pos < len(data):
        tag, size = struct.unpack("<4sQ", _range(data, pos, 12))
        pos += 12
        yield tag, _range(data, pos, size)
        pos += size


def extract(data: bytes, *, filter_name: str, max_entries: int = 100_000,
            max_segments: int = 100_000, max_file_size: int = 64 << 20,
            max_total_size: int = 256 << 20, max_index_size: int = 16 << 20,
            max_archive_size: int = 512 << 20) -> list[Entry]:
    """Decode this strict XP3 subset, validating checksums and every segment.

    Unknown/duplicate sections and encryption flags fail closed. Segment order
    is index order, including legitimate repeated physical segments. Expansion
    budgets count repeated segments rather than unique source ranges.
    """
    if filter_name != "none":
        raise ValueError("unknown XP3 filter; only explicit 'none' is supported")
    if not isinstance(data, bytes) or len(data) > max_archive_size:
        raise ValueError("XP3 input type/size")
    if min(max_entries, max_segments, max_file_size, max_total_size,
           max_index_size, max_archive_size) < 0:
        raise ValueError("negative XP3 limit")
    if _range(data, 0, 11) != MAGIC:
        raise ValueError("not a standalone XP3 archive")
    index_at, = struct.unpack("<Q", _range(data, 11, 8))
    if index_at < 19:
        raise ValueError("XP3 index overlaps header")
    flag = _range(data, index_at, 1)[0]
    if flag == 0:
        size, = struct.unpack("<Q", _range(data, index_at + 1, 8))
        if size > max_index_size:
            raise ValueError("XP3 index size limit")
        index = _range(data, index_at + 9, size)
        index_end = index_at + 9 + size
    elif flag == 1:
        packed, size = struct.unpack("<QQ", _range(data, index_at + 1, 16))
        if packed > max_index_size:
            raise ValueError("XP3 packed index limit")
        index = _inflate(_range(data, index_at + 17, packed), size, max_index_size)
        index_end = index_at + 17 + packed
    else:
        raise ValueError("unsupported XP3 index flags/chaining")
    entries, names, total, segment_total = [], set(), 0, 0
    for tag, record in _chunks(index):
        if tag != b"File" or len(entries) >= max_entries:
            raise ValueError("unknown XP3 index record or entry limit")
        sections = {}
        for section, body in _chunks(record):
            if section not in (b"info", b"segm", b"adlr") or section in sections:
                raise ValueError("unknown/duplicate XP3 section (possible filter)")
            sections[section] = body
        if set(sections) != {b"info", b"segm", b"adlr"}:
            raise ValueError("missing XP3 standard section")
        info = sections[b"info"]
        flags, unpacked, packed, units = struct.unpack("<IQQH", _range(info, 0, 22))
        if flags:
            raise ValueError("encrypted/unknown XP3 info flags")
        if not units or units > 4096 or len(info) != 22 + units * 2:
            raise ValueError("invalid XP3 name length")
        name = info[22:].decode("utf-16-le", errors="strict")
        if "\0" in name or name in names:
            raise ValueError("duplicate/NUL XP3 name")
        if unpacked > max_file_size or total + unpacked > max_total_size:
            raise ValueError("XP3 output budget")
        if len(sections[b"adlr"]) != 4:
            raise ValueError("invalid XP3 adlr size")
        checksum, = struct.unpack("<I", sections[b"adlr"])
        segments = sections[b"segm"]
        if not segments or len(segments) % 28:
            raise ValueError("invalid XP3 segment table")
        count = len(segments) // 28
        segment_total += count
        if segment_total > max_segments:
            raise ValueError("XP3 segment count limit")
        chunks, raw_sum, packed_sum = [], 0, 0
        for pos in range(0, len(segments), 28):
            sf, off, raw_len, packed_len = struct.unpack_from("<IQQQ", segments, pos)
            raw_sum += raw_len
            packed_sum += packed_len
            if raw_sum > unpacked or packed_sum > packed or off < 19:
                raise ValueError("XP3 segment totals/range mismatch")
            if packed_len and off < index_end and off + packed_len > index_at:
                raise ValueError("XP3 segment overlaps index")
            payload = _range(data, off, packed_len)
            if sf == 1:
                payload = _inflate(payload, raw_len, max_file_size)
            elif sf != 0 or raw_len != packed_len:
                raise ValueError("unknown XP3 segment flag/size")
            chunks.append(payload)
        if raw_sum != unpacked or packed_sum != packed:
            raise ValueError("XP3 File totals disagree with segment table")
        payload = b"".join(chunks)
        if zlib.adler32(payload) & 0xffffffff != checksum:
            raise ValueError("XP3 Adler-32 mismatch (possibly unmarked filter)")
        names.add(name)
        total += unpacked
        entries.append(Entry(name, payload, checksum, count))
    if not entries:
        raise ValueError("empty XP3 index")
    return entries


def build(files: list[tuple[str, bytes]], *, filter_name: str,
          compress_index: bool = True, compress_contents: bool = False,
          max_entries: int = 100_000, max_total_size: int = 256 << 20,
          max_archive_size: int = 512 << 20) -> bytes:
    """Build standard v1 XP3, one segment per file; not a game-filter writer.

    This is a new archive, not a byte-identical patch of an existing archive.
    Does not normalize names or decide game patch precedence.
    """
    if filter_name != "none" or not 0 < len(files) <= max_entries:
        raise ValueError("unsupported filter or XP3 file count")
    output, index, names, total = bytearray(MAGIC + b"\0" * 8), bytearray(), set(), 0

    def chunk(tag, body):
        return tag + struct.pack("<Q", len(body)) + body

    for name, payload in files:
        if not isinstance(payload, bytes) or not isinstance(name, str):
            raise ValueError("XP3 requires str names and bytes payloads")
        if not name or "\0" in name or name in names:
            raise ValueError("empty/NUL/duplicate XP3 name")
        encoded = name.encode("utf-16-le", errors="strict")
        if len(encoded) > 8192:
            raise ValueError("XP3 name limit")
        names.add(name)
        total += len(payload)
        if total > max_total_size:
            raise ValueError("XP3 input budget")
        stored = zlib.compress(payload) if compress_contents else payload
        segment = struct.pack("<IQQQ", int(compress_contents), len(output), len(payload), len(stored))
        info = struct.pack("<IQQH", 0, len(payload), len(stored), len(encoded) // 2) + encoded
        record = (chunk(b"info", info) + chunk(b"segm", segment)
                  + chunk(b"adlr", struct.pack("<I", zlib.adler32(payload) & 0xffffffff)))
        index.extend(chunk(b"File", record))
        if len(output) + len(stored) + len(index) + 17 > max_archive_size:
            raise ValueError("XP3 archive budget")
        output.extend(stored)
    struct.pack_into("<Q", output, 11, len(output))
    if compress_index:
        packed = zlib.compress(index)
        output.extend(b"\1" + struct.pack("<QQ", len(packed), len(index)) + packed)
    else:
        output.extend(b"\0" + struct.pack("<Q", len(index)) + index)
    if len(output) > max_archive_size:
        raise ValueError("XP3 archive budget")
    return bytes(output)
