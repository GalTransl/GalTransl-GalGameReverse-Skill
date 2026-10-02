"""Bounded BGI PackFile/BURIKO ARC20 index, probe and member readers.

The legacy inspect/require_plain API still leaves DSC/BSE opaque. Only the new
explicit decode_member API decompresses DSC; it is NOT a script classifier or
BGI disassembler. BSE and images remain unsupported. Returned names are
untrusted and are never materialized here. No writer or import-time I/O.

Reference: GARbro-Mod, ArcFormats/Ethornell/ArcBGI.cs,
ArcOpener.TryOpen/OpenEntry, Arc2Opener.Open/OpenEntry, DscDecoder constructor;
commit bc26d991ef5cdc0e1ecb32122ee9a48c3375750c (MIT).
Also adapted/checked against msg-tool src/scripts/bgi/archive/{v1,v2}.rs,
BgiFileHeader, BgiArchive::new/open_file and detect_script_type;
commit f72716cee88554d40c1cdface2812493b14ca653 (GPL-3.0-or-later),
lifegpc/msg-tool contributors (no per-file copyright notice).

GPL-derived additions are free software: you can redistribute and/or modify
under the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version. Distributed WITHOUT ANY WARRANTY; without even the implied warranty
of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See ../../LICENSE
and ../../provenance/licenses/GPL-3.0.txt, or https://www.gnu.org/licenses/.
The MIT-derived portions retain the following notice:
Copyright (C) 2014-2015 by morkt

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
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import struct


class BgiArchiveError(ValueError):
    """Structured failure; offsets are archive-absolute, or DSC-local at decode."""

    def __init__(self, message: str, *, code: str, stage: str,
                 offset: int | None = None):
        super().__init__(message)
        self.code = code
        self.stage = stage
        self.offset = offset


@dataclass(frozen=True)
class IndexEntry:
    ordinal: int
    name: str
    offset: int
    size: int
    # Opaque bytes between the u32 size field and the next row. Real BGI v2
    # archives carry non-zero values here (8 of 24 bytes observed); neither
    # referenced reader interprets them, so they are preserved verbatim for a
    # faithful rebuild instead of being normalized to zero.
    extra: bytes = b""


@dataclass(frozen=True)
class ArchiveIndex:
    version: int
    archive_size: int
    index_end: int
    index_sha256: str
    entries: tuple[IndexEntry, ...]


@dataclass(frozen=True)
class MemberProbe:
    codec: str
    unpacked_size: int | None
    header: bytes


@dataclass(frozen=True)
class Entry:
    name: str
    stored_data: bytes
    offset: int
    codec: str
    unpacked_size: int | None


def _range(data, offset, size):
    if offset < 0 or size < 0 or offset > len(data) or size > len(data) - offset:
        raise ValueError("BGI range outside input")
    return data[offset:offset + size]


def inspect(data: bytes, *, name_encoding: str = "cp932",
            max_entries: int = 100_000, max_file_size: int = 64 << 20,
            max_total_size: int = 256 << 20, max_archive_size: int = 512 << 20) -> list[Entry]:
    """Read both indexes; retain opaque DSC/BSE bytes with explicit codec tags.

    Both stored and advertised DSC sizes count against budgets. Unknown DSC
    or BSE versions and recognizable but truncated wrappers are refused.
    """
    if not isinstance(data, bytes) or len(data) > max_archive_size:
        raise ValueError("BGI input type/size")
    if min(max_entries, max_file_size, max_total_size, max_archive_size) < 0:
        raise ValueError("negative BGI limit")
    signature = _range(data, 0, 12)
    if signature == b"PackFile    ":
        stride, name_size = 0x20, 0x10
    elif signature == b"BURIKO ARC20":
        stride, name_size = 0x80, 0x60
    else:
        raise ValueError("unsupported BGI archive signature")
    count, = struct.unpack("<I", _range(data, 12, 4))
    if not 0 < count <= min(max_entries, 0xfffff):
        raise ValueError("BGI entry count limit")
    base = 16 + count * stride
    _range(data, 16, count * stride)
    result, names, total = [], set(), 0
    for number in range(count):
        pos = 16 + number * stride
        name = data[pos:pos + name_size].split(b"\0", 1)[0].decode(name_encoding, errors="strict")
        if not name or name in names:
            raise ValueError("empty/duplicate BGI filename")
        rel, size = struct.unpack_from("<II", data, pos + name_size)
        offset = base + rel
        if size > max_file_size or total + size > max_total_size:
            raise ValueError("BGI stored size budget")
        stored = _range(data, offset, size)
        codec, unpacked = "raw", size
        if stored.startswith(b"DSC"):
            if not stored.startswith(b"DSC FORMAT 1.00\0") or len(stored) < 0x220:
                raise ValueError("unknown/truncated DSC wrapper")
            unpacked, = struct.unpack_from("<I", stored, 0x14)
            codec = "dsc"
        elif stored.startswith(b"BSE"):
            if not stored.startswith(b"BSE 1.") or len(stored) < 0x50:
                raise ValueError("unknown/truncated BSE wrapper")
            version, = struct.unpack_from("<H", stored, 8)
            if version not in (0x100, 0x101):
                raise ValueError("unsupported BSE version")
            codec, unpacked = "bse", None
        elif stored.startswith(b"CompressedBG"):
            codec, unpacked = "compressedbg-image", None
        charge = max(size, unpacked or 0)
        if charge > max_file_size or total + charge > max_total_size:
            raise ValueError("BGI advertised output budget")
        total += charge
        names.add(name)
        result.append(Entry(name, stored, offset, codec, unpacked))
    return result


def require_plain(entry: Entry) -> bytes:
    """Return unwrapped member bytes, or fail rather than claim decompression."""
    if entry.codec != "raw":
        raise ValueError("BGI codec is not implemented: " + entry.codec)
    return entry.stored_data


def _limit(value, name, stage):
    if type(value) is not int or value < 0:
        raise BgiArchiveError("invalid " + name, code="invalid_limit", stage=stage)


def _seek(stream, offset, whence, stage):
    try:
        stream.seek(offset, whence)
    except (AttributeError, OSError, ValueError, TypeError) as exc:
        raise BgiArchiveError("BGI stream must be seekable", code="stream_io",
                              stage=stage, offset=offset) from exc


def _tell(stream, stage):
    try:
        pos = stream.tell()
    except (AttributeError, OSError, ValueError, TypeError) as exc:
        raise BgiArchiveError("cannot determine BGI stream position", code="stream_io",
                              stage=stage) from exc
    if type(pos) is not int or pos < 0:
        raise BgiArchiveError("invalid BGI stream position", code="stream_io", stage=stage)
    return pos


@contextmanager
def _preserve_position(stream, stage):
    pos = _tell(stream, stage)
    try:
        yield
    finally:
        _seek(stream, pos, 0, stage)


def _stream_size(stream, stage):
    _seek(stream, 0, 2, stage)
    return _tell(stream, stage)


def _read_exact(stream, size, offset, stage):
    """Honor partial reads; never use an unbounded read or allocate from EOF."""
    result = bytearray()
    while len(result) < size:
        amount = min(size - len(result), 1 << 20)
        try:
            chunk = stream.read(amount)
        except (AttributeError, OSError, ValueError, TypeError) as exc:
            raise BgiArchiveError("BGI read failed", code="stream_io", stage=stage,
                                  offset=offset + len(result)) from exc
        if not isinstance(chunk, bytes) or len(chunk) > amount:
            raise BgiArchiveError("BGI stream must return bounded bytes", code="stream_io",
                                  stage=stage, offset=offset + len(result))
        if not chunk:
            raise BgiArchiveError("truncated BGI input", code="truncated", stage=stage,
                                  offset=offset + len(result))
        result.extend(chunk)
    return bytes(result)


def _member_range(offset, size, index_end, archive_size, stage):
    if (type(offset) is not int or type(size) is not int or size < 0
            or offset < index_end or offset > archive_size
            or size > archive_size - offset):
        raise BgiArchiveError("BGI member outside archive", code="archive_bounds",
                              stage=stage, offset=offset if type(offset) is int else None)


def read_index(stream, *, name_encoding: str = "cp932", max_entries: int = 100_000,
               max_index_size: int = 16 << 20,
               max_archive_size: int | None = None) -> ArchiveIndex:
    """Read only [0, index_end), restoring the seekable binary stream position.

    max_index_size includes the 16-byte header. No member bytes are read or
    charged, including large videos. None disables the optional whole-archive
    size cap. index_sha256 covers exactly the header AND index, not the payload;
    it is a fingerprint, not authentication or a whole-archive digest.
    """
    for name, value in (("max_entries", max_entries), ("max_index_size", max_index_size)):
        _limit(value, name, "index")
    if max_archive_size is not None:
        _limit(max_archive_size, "max_archive_size", "index")
    if max_index_size < 16:
        raise BgiArchiveError("BGI header exceeds index budget", code="index_budget",
                              stage="index", offset=0)
    with _preserve_position(stream, "index"):
        archive_size = _stream_size(stream, "index")
        if max_archive_size is not None and archive_size > max_archive_size:
            raise BgiArchiveError("BGI archive exceeds index-read size cap", code="index_budget",
                                  stage="index", offset=0)
        _seek(stream, 0, 0, "index")
        header = _read_exact(stream, 16, 0, "index")
        signature = header[:12]
        if signature == b"PackFile    ":
            version, stride, name_size = 1, 0x20, 0x10
        elif signature == b"BURIKO ARC20":
            version, stride, name_size = 2, 0x80, 0x60
        else:
            raise BgiArchiveError("unsupported BGI archive signature", code="archive_signature",
                                  stage="index", offset=0)
        count, = struct.unpack_from("<I", header, 12)
        if not 0 < count <= min(max_entries, 0xfffff):
            raise BgiArchiveError("BGI entry count limit", code="index_budget",
                                  stage="index", offset=12)
        index_end = 16 + count * stride
        if index_end > max_index_size:
            raise BgiArchiveError("BGI index size budget", code="index_budget",
                                  stage="index", offset=12)
        if index_end > archive_size:
            raise BgiArchiveError("BGI index extends past archive", code="archive_bounds",
                                  stage="index", offset=16)
        table = _read_exact(stream, count * stride, 16, "index")
        digest = hashlib.sha256(header)
        digest.update(table)
        entries, names = [], set()
        for ordinal in range(count):
            pos = ordinal * stride
            encoded = table[pos:pos + name_size].split(b"\0", 1)[0]
            try:
                name = encoded.decode(name_encoding, errors="strict")
            except (LookupError, UnicodeError) as exc:
                raise BgiArchiveError("invalid BGI filename encoding", code="index_name",
                                      stage="index", offset=16 + pos) from exc
            if not name or name in names:
                raise BgiArchiveError("empty/duplicate BGI filename", code="index_name",
                                      stage="index", offset=16 + pos)
            rel, size = struct.unpack_from("<II", table, pos + name_size)
            offset = index_end + rel
            _member_range(offset, size, index_end, archive_size, "index")
            entries.append(IndexEntry(ordinal, name, offset, size,
                                      table[pos + name_size + 8:pos + stride]))
            names.add(name)
        return ArchiveIndex(version, archive_size, index_end, digest.hexdigest(), tuple(entries))


def _check_member(stream, index, entry, stage):
    # Identity, not merely equality: callers must select a row returned by this
    # index. This is O(1) and rejects edited/copied rows and rows of other indexes.
    if (not isinstance(index, ArchiveIndex) or not isinstance(entry, IndexEntry)
            or type(entry.ordinal) is not int or not isinstance(index.entries, tuple)
            or not 0 <= entry.ordinal < len(index.entries)
            or index.entries[entry.ordinal] is not entry):
        raise BgiArchiveError("BGI entry does not belong to index", code="index_membership",
                              stage=stage)
    if (index.version not in (1, 2) or type(index.archive_size) is not int
            or type(index.index_end) is not int
            or index.index_end != 16 + len(index.entries) * (0x20 if index.version == 1 else 0x80)
            or not 16 <= index.index_end <= index.archive_size):
        raise BgiArchiveError("invalid BGI index metadata", code="index_membership", stage=stage)
    current_size = _stream_size(stream, stage)
    if current_size != index.archive_size:
        raise BgiArchiveError("BGI archive size changed since indexing", code="archive_changed",
                              stage=stage)
    _member_range(entry.offset, entry.size, index.index_end, current_size, stage)


def _probe_header(header, stored_size, offset, stage):
    codec, unpacked = "raw", stored_size
    if header.startswith(b"DSC"):
        magic = b"DSC FORMAT 1.00\0"
        if not header.startswith(magic):
            code = "truncated" if magic.startswith(header) else "unsupported_codec"
            raise BgiArchiveError("unknown/truncated DSC wrapper", code=code,
                                  stage=stage, offset=offset)
        if stored_size < 0x220:
            raise BgiArchiveError("truncated DSC wrapper", code="truncated", stage=stage,
                                  offset=offset + stored_size)
        unpacked, = struct.unpack_from("<I", header, 0x14)
        codec = "dsc"
    elif header.startswith(b"BSE"):
        if not header.startswith(b"BSE 1."):
            code = "truncated" if b"BSE 1.".startswith(header) else "unsupported_codec"
            raise BgiArchiveError("unknown/truncated BSE wrapper", code=code,
                                  stage=stage, offset=offset)
        if stored_size < 0x50:
            raise BgiArchiveError("truncated BSE wrapper", code="truncated", stage=stage,
                                  offset=offset + stored_size)
        version, = struct.unpack_from("<H", header, 8)
        if version not in (0x100, 0x101):
            raise BgiArchiveError("unsupported BSE version", code="unsupported_codec",
                                  stage=stage, offset=offset + 8)
        codec, unpacked = "bse", None
    elif header.startswith(b"CompressedBG"):
        codec, unpacked = "compressedbg-image", None
    return MemberProbe(codec, unpacked, header)


def probe_member(stream, index: ArchiveIndex, entry: IndexEntry) -> MemberProbe:
    """Read at most 0x220 stored bytes, enough for wrapper/V1 script magic.

    No decompression or advertised-output budget charge. A raw header is not
    proof of script/text content. Position is restored, as with read_member.
    """
    with _preserve_position(stream, "probe"):
        _check_member(stream, index, entry, "probe")
        _seek(stream, entry.offset, 0, "probe")
        header = _read_exact(stream, min(entry.size, 0x220), entry.offset, "probe")
        return _probe_header(header, entry.size, entry.offset, "probe")


def read_member(stream, index: ArchiveIndex, entry: IndexEntry, *,
                max_stored_size: int = 64 << 20) -> Entry:
    """Read one selected member; only stored bytes count against this budget.

    The index is not a security token. Callers must use the same unchanged
    archive; same-size edits are not detected, and reads are not atomic against
    concurrent writes. No per-member call rehashes or reads the entire index.
    """
    _limit(max_stored_size, "max_stored_size", "stored")
    with _preserve_position(stream, "stored"):
        _check_member(stream, index, entry, "stored")
        if entry.size > max_stored_size:
            raise BgiArchiveError("BGI stored size budget", code="stored_budget",
                                  stage="stored", offset=entry.offset)
        _seek(stream, entry.offset, 0, "stored")
        stored = _read_exact(stream, entry.size, entry.offset, "stored")
        probe = _probe_header(stored[:0x220], entry.size, entry.offset, "stored")
        return Entry(entry.name, stored, entry.offset, probe.codec, probe.unpacked_size)


def decode_member(entry: Entry, *, max_output_size: int = 64 << 20,
                  max_symbols: int = 64 << 20) -> bytes:
    """Explicitly unwrap raw/DSC once; never claim the result is a script.

    Does not recursively decode BSE/images/nested DSC or materialize files.
    require_plain remains deliberately stricter and never decodes wrappers.

    Keep max_symbols >= max_output_size (see bgi_dsc.decode): a DSC symbol emits
    at least one byte, so a lower symbol cap only rejects members that the output
    cap already allows. Batch callers that pass a smaller max_symbols while
    keeping the 64 MiB output cap will misreport ordinary large image members as
    "not processed" instead of decoding them and classifying them.
    """
    _limit(max_output_size, "max_output_size", "decode")
    _limit(max_symbols, "max_symbols", "decode")
    if not isinstance(entry, Entry) or not isinstance(entry.stored_data, bytes):
        raise BgiArchiveError("invalid BGI member", code="input_type", stage="decode")
    if entry.codec == "raw":
        if len(entry.stored_data) > max_output_size:
            raise BgiArchiveError("BGI decoded size budget", code="decoded_budget", stage="decode")
        if entry.unpacked_size != len(entry.stored_data):
            raise BgiArchiveError("BGI raw size mismatch", code="length_mismatch", stage="decode")
        return entry.stored_data
    if entry.codec == "dsc":
        from . import bgi_dsc
        output = bgi_dsc.decode(entry.stored_data, max_output_size=max_output_size,
                                max_symbols=max_symbols)
        if entry.unpacked_size != len(output):
            raise BgiArchiveError("BGI DSC metadata size mismatch", code="length_mismatch",
                                  stage="decode", offset=0x14)
        return output
    raise BgiArchiveError("BGI codec is not implemented: " + str(entry.codec),
                          code="unsupported_codec", stage="decode")
