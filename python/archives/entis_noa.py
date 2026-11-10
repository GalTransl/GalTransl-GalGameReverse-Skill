# SPDX-License-Identifier: MIT
"""Entis ERISA-Archive (.noa) index, member decoding and flat archive writer.

Layout (little-endian; offsets absolute unless noted):
  0x00  8   ``Entis\\x1a\\0\\0``
  0x08  4   format id 0x02000400
  0x0C  4   reserved (0)
  0x10  40  description, ``ERISA-Archive file`` zero padded
  0x38  8   body size (file size - 0x40)
  0x40      ``DirEntry`` record: 8-byte tag, u64 payload size, payload:
              u32 count, then per entry
                u64 size (decoded size), u32 attr, u32 encoding,
                i64 offset (relative to this DirEntry record),
                8-byte ERISA time (sec, min, hour, weekday, day, month, u16 year),
                u32 extra length, extra, u32 name length, name (NUL terminated)
  member    ``filedata`` record: 8-byte tag, u64 stored size, stored bytes
  subdir    (attr & 0x10) record at the entry offset whose payload begins with a
            nested ``DirEntry`` record; nested offsets are relative to that record.

Attributes: 0x10 directory, 0x20/0x40 end-of-directory markers, 0x01000000 the
name is UTF-8 (every observed archive with this bit stores UTF-8 names).
Encodings: 0 raw; 0x80000010 ERISA-N, stored = Nemesis stream + u32 XOR of the
decoded data as little-endian 32-bit words (zero padded); 0x40000000 BSHF;
0xC0000010 BSHF then ERISA-N; 0x20000000 SimpleCrypt32. Encrypted modes need an
explicit password.

Provenance: index layout, attribute/encoding constants and decryption follow
GARbro ``ArcFormats/Entis/ArcNOA.cs`` (MIT, Copyright (C) 2015-2018 by morkt);
bundled notes in engines/garbro/ArcFormats/Entis/ArcNOA.md. The UTF-8 name flag,
the ERISA-N checksum trailer, the header body-size field and the writer layout
are project findings from real archives (see engines/entis-gls.md). The writer
is a new implementation and only emits flat archives with raw or pass-through
members; it never compresses.
"""

from dataclasses import dataclass
import argparse
import json
import struct
import sys
import zlib

from ..common.binary import FormatError
from ..common.safety import Limits, logical_path, validate_names
from .entis_erisa import MAX_OUTPUT, decode_bshf, decode_nemesis

MAGIC = b"Entis\x1a\0\0"
FORMAT_ID = 0x02000400
DESCRIPTION = b"ERISA-Archive file"
HEADER_SIZE = 0x40
RECORD_HEADER = 16
DIR_TAG = b"DirEntry"
FILE_TAG = b"filedata"

ATTR_DIRECTORY = 0x10
ATTR_END_MASK = 0x60
ATTR_KIND_MASK = 0x70
ATTR_UTF8 = 0x01000000

ENC_RAW = 0x00000000
ENC_ERISA_N = 0x80000010
ENC_BSHF = 0x40000000
ENC_SIMPLE32 = 0x20000000
ENC_ERISA_CRYPT = 0xC0000010
ENC_ERISA_CRYPT32 = 0xA0000010
ENCODING_NAMES = {
    ENC_RAW: "raw", ENC_ERISA_N: "erisa-n", ENC_BSHF: "bshf",
    ENC_SIMPLE32: "simplecrypt32", ENC_ERISA_CRYPT: "erisa-crypt",
    ENC_ERISA_CRYPT32: "erisa-crypt32",
}
NEEDS_PASSWORD = {ENC_BSHF, ENC_SIMPLE32, ENC_ERISA_CRYPT}

MAX_ENTRIES = 1 << 20
MAX_DEPTH = 16
MAX_DIR_BYTES = 64 * 1024 * 1024
MAX_NAME = 4096
MAX_EXTRA = 1 << 16


@dataclass(frozen=True)
class NoaEntry:
    path: str
    size: int            # decoded size declared by the index
    attr: int
    encoding: int
    record_offset: int   # absolute offset of the member record header
    tag: bytes
    stored_size: int     # u64 in the member record header
    filetime: bytes
    extra: bytes

    @property
    def data_offset(self):
        return self.record_offset + RECORD_HEADER

    @property
    def encoding_name(self):
        return ENCODING_NAMES.get(self.encoding, f"unknown-{self.encoding:#010x}")


@dataclass(frozen=True)
class NoaIndex:
    entries: tuple
    archive_size: int
    directories: tuple   # nested directory paths (empty for flat archives)

    def owns(self, entry):
        return any(candidate is entry for candidate in self._by_offset.get(entry.record_offset, ()))

    @property
    def _by_offset(self):
        table = self.__dict__.get("_table")
        if table is None:
            table = {}
            for candidate in self.entries:
                table.setdefault(candidate.record_offset, []).append(candidate)
            object.__setattr__(self, "_table", table)
        return table


def _read(stream, offset, size, end):
    if offset < 0 or size < 0 or offset > end or size > end - offset:
        raise FormatError(f"NOA range {offset:#x}+{size:#x} exceeds archive")
    stream.seek(offset)
    data = stream.read(size)
    if len(data) != size:
        raise FormatError("truncated NOA archive")
    return data


def _size(stream):
    stream.seek(0, 2)
    return stream.tell()


def is_noa(header):
    return (len(header) >= 0x22 and header[:8] == MAGIC
            and header[0x10:0x10 + len(DESCRIPTION)] == DESCRIPTION)


def _decode_name(raw, attr, name_encoding):
    end = raw.find(b"\0")
    if end >= 0:
        if any(raw[end:]):
            raise FormatError("data after the NUL terminator of a NOA name")
        raw = raw[:end]
    try:
        if attr & ATTR_UTF8:
            return raw.decode("utf-8")
        if raw.isascii():
            return raw.decode("ascii")
        if not name_encoding:
            raise FormatError("non-ASCII NOA name without the UTF-8 flag: pass name_encoding")
        return raw.decode(name_encoding)
    except UnicodeDecodeError as exc:
        raise FormatError("NOA name does not decode with the selected encoding") from exc


def read_index(stream, *, max_entries=MAX_ENTRIES, max_depth=MAX_DEPTH,
               max_dir_bytes=MAX_DIR_BYTES, name_encoding=None):
    """Parse the full directory tree; offsets and sizes are checked, nothing decoded."""
    end = _size(stream)
    header = _read(stream, 0, HEADER_SIZE, end) if end >= HEADER_SIZE else b""
    if not is_noa(header):
        raise FormatError("not an Entis ERISA-Archive file (NOA)")
    if struct.unpack_from("<I", header, 8)[0] != FORMAT_ID:
        raise FormatError("unsupported NOA format id")
    body, = struct.unpack_from("<Q", header, 0x38)
    if body > end - HEADER_SIZE:
        raise FormatError("NOA header declares more data than the file holds")
    entries, dirs = [], []
    budget = [max_dir_bytes]
    visited = set()

    def parse_dir(at, prefix, depth):
        if depth > max_depth:
            raise FormatError("NOA directory nesting exceeds limit")
        if at in visited:
            raise FormatError("NOA directory cycle")
        visited.add(at)
        head = _read(stream, at, RECORD_HEADER, end)
        if head[:8] != DIR_TAG:
            raise FormatError(f"missing DirEntry record at {at:#x}")
        size, = struct.unpack_from("<Q", head, 8)
        if size < 4 or size > budget[0]:
            raise FormatError("NOA directory size out of range")
        budget[0] -= size
        blob = _read(stream, at + RECORD_HEADER, size, end)
        count, = struct.unpack_from("<I", blob, 0)
        if count > (size - 4) // 40:
            raise FormatError("NOA directory count exceeds its record")
        pos = 4
        stop = False
        for _ in range(count):
            if pos + 36 > size:
                raise FormatError("truncated NOA directory entry")
            dsize, attr, enc, rel, filetime = struct.unpack_from("<QIIq8s", blob, pos)
            pos += 32
            extra_len, = struct.unpack_from("<I", blob, pos)
            pos += 4
            if extra_len > MAX_EXTRA or pos + extra_len + 4 > size:
                raise FormatError("NOA extra data out of range")
            extra = blob[pos:pos + extra_len]
            pos += extra_len
            name_len, = struct.unpack_from("<I", blob, pos)
            pos += 4
            if name_len > MAX_NAME or pos + name_len > size:
                raise FormatError("NOA name out of range")
            name = _decode_name(blob[pos:pos + name_len], attr, name_encoding)
            pos += name_len
            kind = attr & ATTR_KIND_MASK
            if kind & ATTR_END_MASK:
                stop = True          # end/next-directory marker ends this listing
                break
            if not name:
                raise FormatError("empty NOA member name")
            path = logical_path(prefix + name)
            record = at + rel
            rec = _read(stream, record, RECORD_HEADER, end)
            stored, = struct.unpack_from("<Q", rec, 8)
            if stored > end - record - RECORD_HEADER:
                raise FormatError(f"NOA member {path} exceeds archive")
            if kind == ATTR_DIRECTORY:
                dirs.append(path)
                nested = record + RECORD_HEADER
                parse_dir(nested, path + "/", depth + 1)
                continue
            if kind:
                raise FormatError(f"unsupported NOA attribute {attr:#x} for {path}")
            if rec[:8] != FILE_TAG:
                raise FormatError(f"NOA member {path} has record tag {rec[:8]!r}, expected filedata")
            if enc == ENC_RAW and stored != dsize:
                raise FormatError(f"raw NOA member {path} stored size differs from index size")
            if len(entries) >= max_entries:
                raise FormatError("NOA entry count exceeds limit")
            entries.append(NoaEntry(path, dsize, attr, enc, record, rec[:8], stored,
                                    filetime, extra))
        if not stop and pos != size:
            raise FormatError("trailing bytes in NOA directory record")

    parse_dir(HEADER_SIZE, "", 0)
    validate_names([entry.path for entry in entries],
                   Limits(max_entries=max_entries, max_path_chars=MAX_NAME))
    return NoaIndex(tuple(entries), end, tuple(dirs))


def read_index_file(path, **kwargs):
    with open(path, "rb") as stream:
        return read_index(stream, **kwargs)


def xor_checksum(data):
    """ERISA-N trailer: XOR of little-endian u32 words, final word zero padded."""
    padded = bytes(data) + b"\0" * (-len(data) % 4)
    value = 0
    for (word,) in struct.iter_unpack("<I", padded):
        value ^= word
    return value


def _simple_crypt32(data, password, imul_key):
    key = bytearray(password.encode("utf-8"))
    if len(key) < 4:
        raise FormatError("SimpleCrypt32 password must be at least 4 UTF-8 bytes")
    if len(data) % 4:
        raise FormatError("SimpleCrypt32 payload is not a multiple of 4 bytes")
    imul_key = (imul_key ^ zlib.crc32(bytes(key))) & 0xFFFFFFFF
    for i, byte in enumerate(key):
        k = (~byte) & 0xFF
        key[i] = (k ^ (k * 7)) & 0xFF
    words = [w for (w,) in struct.iter_unpack("<I", bytes(key[:len(key) // 4 * 4]))]
    out = bytearray(len(data))
    for i, (value,) in enumerate(struct.iter_unpack("<I", data)):
        struct.pack_into("<I", out, i * 4,
                         ((value * imul_key) & 0xFFFFFFFF) ^ words[i % len(words)])
    return bytes(out)


def read_stored(stream, index, entry):
    """Return the member's stored bytes exactly as they appear in the archive."""
    if not index.owns(entry):
        raise FormatError("member does not belong to this index")
    if _size(stream) != index.archive_size:
        raise FormatError("archive size changed since indexing")
    return _read(stream, entry.data_offset, entry.stored_size, index.archive_size)


def decode_member(entry, stored, *, password=None, max_output=MAX_OUTPUT, verify=True):
    """Decode stored bytes of ``entry``; unknown or keyless encodings are refused."""
    if entry.size > max_output:
        raise FormatError(f"NOA member {entry.path} exceeds the output budget")
    enc = entry.encoding
    if enc in NEEDS_PASSWORD and not password:
        raise FormatError(f"NOA member {entry.path} is encrypted ({entry.encoding_name}); "
                          "a password is required")
    if enc == ENC_RAW:
        return bytes(stored)
    if enc == ENC_ERISA_N:
        if len(stored) < 4:
            raise FormatError("ERISA-N member lacks its checksum")
        data = decode_nemesis(stored[:-4], entry.size, max_output=max_output)
        if verify and xor_checksum(data) != struct.unpack_from("<I", stored, len(stored) - 4)[0]:
            raise FormatError(f"ERISA-N checksum mismatch for {entry.path}")
        return data
    if enc == ENC_BSHF:
        return decode_bshf(stored, password, max_output=max_output)
    if enc == ENC_ERISA_CRYPT:
        plain = decode_bshf(stored, password, max_output=max_output)
        return decode_nemesis(plain, entry.size, max_output=max_output)
    if enc == ENC_SIMPLE32:
        if len(entry.extra) < 8:
            raise FormatError("SimpleCrypt32 member lacks its extra key word")
        return _simple_crypt32(stored, password, struct.unpack_from("<I", entry.extra, 4)[0])
    raise FormatError(f"unsupported NOA encoding {enc:#010x} for {entry.path}")


def read_member(stream, index, entry, **kwargs):
    return decode_member(entry, read_stored(stream, index, entry), **kwargs)


@dataclass(frozen=True)
class NoaMember:
    """A member to write. ``stored`` is written verbatim under ``encoding``."""

    path: str
    stored: bytes
    size: int
    encoding: int = ENC_RAW
    filetime: bytes = b"\0" * 8
    extra: bytes = b""
    attr: int = ATTR_UTF8

    @classmethod
    def raw(cls, path, data, filetime=b"\0" * 8):
        return cls(path, bytes(data), len(data), ENC_RAW, bytes(filetime))


def member_from_entry(stream, index, entry):
    """Pass an existing member through unchanged (no recompression)."""
    return NoaMember(entry.path, read_stored(stream, index, entry), entry.size,
                     entry.encoding, entry.filetime, entry.extra, entry.attr)


def build_noa(members, *, max_total=2 << 30):
    """Write a flat NOA (no subdirectories) with UTF-8 names."""
    members = list(members)
    if not members:
        raise FormatError("NOA needs at least one member")
    paths = validate_names([member.path for member in members],
                           Limits(max_entries=MAX_ENTRIES, max_path_chars=MAX_NAME))
    for member in members:
        if "/" in member.path:
            raise FormatError("NOA writer emits flat archives only (no subdirectories)")
        if member.attr & ATTR_KIND_MASK or not member.attr & ATTR_UTF8:
            raise FormatError("NOA writer needs plain file attributes with the UTF-8 flag")
        if len(member.filetime) != 8 or len(member.extra) > MAX_EXTRA:
            raise FormatError("invalid NOA member metadata")
        if member.encoding == ENC_RAW and len(member.stored) != member.size:
            raise FormatError("raw NOA member size mismatch")
        if member.encoding not in ENCODING_NAMES:
            raise FormatError("unknown NOA encoding")
    names = [path.encode("utf-8") + b"\0" for path in paths]
    dir_size = 4 + sum(36 + len(m.extra) + 4 + len(n) for m, n in zip(members, names))
    offset = RECORD_HEADER + dir_size
    table = bytearray(struct.pack("<I", len(members)))
    for member, name in zip(members, names):
        table += struct.pack("<QIIq", member.size, member.attr, member.encoding, offset)
        table += member.filetime + struct.pack("<I", len(member.extra)) + member.extra
        table += struct.pack("<I", len(name)) + name
        offset += RECORD_HEADER + len(member.stored)
    total = HEADER_SIZE + offset
    if total > max_total:
        raise FormatError("NOA output exceeds budget")
    out = bytearray(MAGIC + struct.pack("<II", FORMAT_ID, 0))
    out += DESCRIPTION.ljust(40, b"\0") + struct.pack("<Q", total - HEADER_SIZE)
    out += DIR_TAG + struct.pack("<Q", dir_size) + table
    for member in members:
        out += FILE_TAG + struct.pack("<Q", len(member.stored)) + member.stored
    result = bytes(out)
    _verify_written(result, members)
    return result


def _verify_written(data, members):
    """Re-read the new archive with the real reader and compare every member."""
    import io
    stream = io.BytesIO(data)
    index = read_index(stream)
    if [e.path for e in index.entries] != [m.path for m in members]:
        raise FormatError("written NOA index differs")
    for entry, member in zip(index.entries, members):
        if (entry.size, entry.encoding, entry.filetime, entry.extra) != \
                (member.size, member.encoding, member.filetime, member.extra):
            raise FormatError(f"written NOA entry {entry.path} differs")
        if read_stored(stream, index, entry) != member.stored:
            raise FormatError(f"written NOA payload {entry.path} differs")


def _main(argv=None):
    parser = argparse.ArgumentParser(description="List or check Entis NOA archives (read-only).")
    sub = parser.add_subparsers(dest="command", required=True)
    ls = sub.add_parser("ls", help="print the index as JSON lines")
    ls.add_argument("archive")
    ls.add_argument("--name-encoding")
    check = sub.add_parser("verify", help="decode every member and verify checksums")
    check.add_argument("archive")
    check.add_argument("--password")
    check.add_argument("--name-encoding")
    args = parser.parse_args(argv)
    with open(args.archive, "rb") as stream:
        index = read_index(stream, name_encoding=args.name_encoding)
        failures = 0
        for entry in index.entries:
            row = {"path": entry.path, "size": entry.size, "stored": entry.stored_size,
                   "encoding": entry.encoding_name, "attr": f"{entry.attr:#x}"}
            if args.command == "verify":
                try:
                    data = read_member(stream, index, entry, password=args.password)
                    row["ok"] = len(data) == entry.size
                except FormatError as exc:
                    row["ok"], row["error"] = False, str(exc)
                failures += not row["ok"]
            print(json.dumps(row, ensure_ascii=False))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(_main())
