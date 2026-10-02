"""Artemis PFS container reference: pf0/pf2/pf6/pf8 index, members, writer.

Layout verified against GARbro-Mod ``ArcFormats/Artemis/ArcPFS.cs``
(PfsOpener.OpenPf/OpenPf2/OpenPf0/OpenEntry, commit
bc26d991ef5cdc0e1ecb32122ee9a48c3375750c, MIT), msg-tool
``src/scripts/artemis/archive/pfs.rs`` (commit f72716c..., GPL-3.0-or-later) and a
real multi-volume release::

    "pf8" | u32 index_size | index
    index   = u32 entry count | entry records | optional trailing table
    pf6/pf8 record = u32 name_len | name | u32 unknown | u32 offset | u32 size
                     -> name_len + 16 bytes
    pf2   record   = u32 name_len | name | 12 opaque bytes | u32 offset | u32 size
                     (count at index offset 4; index begins with four zero bytes)
    pf0   record   = 0x104-byte ASCII name | u32 offset | u32 size   (0x10c total)

pf8 (and upstream pf4/5/9) payloads are XORed with ``key = SHA1(index)``, where
``index`` is the **whole declared index** (trailing table included), restarted at
every member.

Two things a strict reader gets wrong on real archives:

* ``index_size`` may exceed the entry records; the remainder is an undocumented
  table that both references ignore. :func:`read_index` keeps it in
  ``ArchiveIndex.trailing`` instead of rejecting the archive, and the writer can
  copy it back verbatim. It must still be hashed, or the XOR key is wrong.
* Names are not always CP932. ``name_encoding=None`` autodetects one codec for the
  whole archive (UTF-8, then CP932); an explicit value is strict.

Multi-volume releases store independent archives in ``root.pfs`` plus
``root.pfs.000``, ``root.pfs.001``... and the engine merges their namespaces.
:func:`resolve_volumes` reports the override chain without inventing a precedence
rule. ``index_size`` counting, entry ``unknown`` fields and padding are preserved
so an unchanged volume can be rebuilt byte for byte.

Reference licences: MIT (morkt / GARbro-Mod), GPL-3.0-or-later (msg-tool). This
module is a re-implementation, not a wrapper around either runtime.
"""

from dataclasses import dataclass, field
import codecs
import hashlib
import io
import os
import struct

MAGIC = b"pf"
SUPPORTED_VERSIONS = (0, 2, 6, 8)
XOR_VERSIONS = (4, 5, 8, 9)
_PF0_NAME = 0x104
_PF0_RECORD = 0x10C
_PF2_PADDING = 12


class PfsError(ValueError):
    """Rejected archive/index/member, with a machine-readable code and stage."""

    def __init__(self, code: str, message: str, stage: str = "index"):
        super().__init__(message)
        self.code = code
        self.stage = stage


@dataclass(frozen=True)
class Entry:
    """Decoded member returned by :func:`extract` (kept for compatibility)."""

    name: str
    data: bytes
    offset: int
    version: int
    unk: int = 0
    ordinal: int = 0


@dataclass(frozen=True)
class IndexEntry:
    ordinal: int
    name: str
    offset: int
    size: int
    unk: int = 0
    #: Raw name bytes and opaque padding, kept so the index can be rebuilt as-is.
    name_bytes: bytes = b""
    padding: bytes = b""


@dataclass(frozen=True)
class ArchiveIndex:
    version: int
    archive_size: int
    index_end: int
    index_sha1: str
    name_encoding: str
    trailing: bytes = b""
    entries: tuple = ()
    key: bytes = b""

    def by_name(self):
        result = {}
        for entry in self.entries:
            result.setdefault(entry.name, []).append(entry)
        return result


@dataclass(frozen=True)
class Member:
    """One member with both its stored bytes and its decoded payload."""

    entry: IndexEntry
    stored: bytes
    data: bytes


@dataclass(frozen=True)
class VolumeMember:
    name: str
    volume: str
    entry: IndexEntry
    #: Volumes this name also appeared in, earliest first.
    overrides: tuple = ()


@dataclass(frozen=True)
class VolumeSet:
    """Merged namespace of several independent PFS volumes (no IO performed)."""

    volumes: tuple = ()
    members: tuple = ()
    order: tuple = field(default=())

    def by_name(self):
        return {member.name: member for member in self.members}


# --------------------------------------------------------------------------- IO


def _as_stream(source):
    """Return (stream, close) for bytes, a filesystem path or a seekable stream."""
    if isinstance(source, (bytes, bytearray, memoryview)):
        return io.BytesIO(bytes(source)), True
    if hasattr(source, "read") and hasattr(source, "seek"):
        return source, False
    try:
        return open(os.fspath(source), "rb"), True
    except TypeError as exc:
        raise PfsError("input_type", "source must be bytes, a path or a seekable stream", "input") from exc


def _size_of(stream):
    position = stream.tell()
    stream.seek(0, os.SEEK_END)
    total = stream.tell()
    stream.seek(position)
    return total


def _read_at(stream, offset, size, total, what="member"):
    if offset < 0 or size < 0 or offset + size > total:
        raise PfsError("range_outside_file", "PFS range lies outside the volume", what)
    stream.seek(offset)
    data = stream.read(size)
    if len(data) != size:
        raise PfsError("short_read", "PFS range was truncated", what)
    return data


# ------------------------------------------------------------------------ names


def _decode_names(raw_names, version, name_encoding):
    """Decode every raw name with one codec; return (names, encoding_used)."""
    if version == 0:
        return [raw.split(b"\0", 1)[0].decode("ascii", errors="strict") for raw in raw_names], "ascii"
    if name_encoding is not None:
        try:
            codecs.lookup(name_encoding)
        except LookupError as exc:
            raise PfsError("unknown_encoding", f"unknown codec: {name_encoding}", "index") from exc
        candidates = (name_encoding,)
    elif version == 2:
        candidates = ("cp932",)          # both references hard-code CP932 for pf2
    else:
        candidates = ("utf-8", "cp932")  # autodetect per archive, never per name
    failure = None
    for encoding in candidates:
        try:
            return [raw.decode(encoding, errors="strict") for raw in raw_names], encoding
        except UnicodeDecodeError as exc:
            failure = exc
    raise PfsError("name_decoding", "PFS names are invalid in every candidate codec", "index") from failure


# ------------------------------------------------------------------------ index


def probe_header(source):
    """Return the PFS version without reading the entry table."""
    stream, close = _as_stream(source)
    try:
        stream.seek(0)
        header = stream.read(3)
        if len(header) < 3 or header[:2] != MAGIC or not header[2:3].isdigit():
            raise PfsError("bad_magic", "not an Artemis PFS header", "index")
        version = header[2] - ord("0")
        if version not in SUPPORTED_VERSIONS:
            raise PfsError("unsupported_version", f"unsupported PFS version pf{version}", "index")
        return version
    finally:
        if close:
            stream.close()


def _parse_records(index, version, count, max_entries):
    """Walk the entry records; return a list of (name_bytes, offset, size, unk, padding)."""
    if not 0 < count <= max_entries:
        raise PfsError("entry_budget", "PFS entry count exceeds the budget", "index")
    records = []
    if version == 0:
        if len(index) != count * _PF0_RECORD:
            raise PfsError("index_size_mismatch", "pf0 index size disagrees with the entry count", "index")
        return records, None
    name_len_offset = 4 if version <= 2 else 0
    pos = name_len_offset + 4
    pad_len = _PF2_PADDING if version == 2 else 4
    if count * (pad_len + 12) > len(index):
        raise PfsError("impossible_count", "PFS entry count cannot fit the index", "index")
    for _ in range(count):
        if pos + 4 > len(index):
            raise PfsError("truncated_index", "PFS index ends inside an entry", "index")
        name_len, = struct.unpack_from("<I", index, pos)
        if not 0 < name_len <= 4096:
            raise PfsError("bad_name_length", "PFS filename length is out of range", "index")
        pos += 4
        if pos + name_len > len(index):
            raise PfsError("truncated_index", "PFS index ends inside a name", "index")
        name = index[pos:pos + name_len]
        pos += name_len
        if pos + pad_len + 8 > len(index):
            raise PfsError("truncated_index", "PFS index ends inside an entry", "index")
        padding = index[pos:pos + pad_len]
        pos += pad_len
        offset, size = struct.unpack_from("<II", index, pos)
        pos += 8
        records.append((name, offset, size, padding))
    return records, pos


def _pf0_records(index, count):
    records = []
    for i in range(count):
        base = i * _PF0_RECORD
        records.append((index[base:base + _PF0_NAME],
                        *struct.unpack_from("<II", index, base + _PF0_NAME),
                        b""))
    return records


def read_index(source, *, name_encoding=None, max_entries: int = 100_000,
               max_index_size: int = 32 << 20, max_archive_size=None) -> ArchiveIndex:
    """Read and validate a PFS header plus entry table; never reads payloads.

    ``max_archive_size=None`` (default) lets a multi-gigabyte volume be indexed
    without holding it in memory; pass a budget to reject large files explicitly.
    """
    for value, label in ((max_entries, "max_entries"), (max_index_size, "max_index_size")):
        if type(value) is not int or value < 0:
            raise PfsError("bad_limit", f"{label} must be a nonnegative integer", "index")
    if max_archive_size is not None and (type(max_archive_size) is not int or max_archive_size < 0):
        raise PfsError("bad_limit", "max_archive_size must be None or a nonnegative integer", "index")
    stream, close = _as_stream(source)
    try:
        stream.seek(0)
        total = _size_of(stream)
        if max_archive_size is not None and total > max_archive_size:
            raise PfsError("archive_budget", "PFS volume exceeds the whole-file budget", "index")
        header = stream.read(7)
        if len(header) < 7 or header[:2] != MAGIC or not header[2:3].isdigit():
            raise PfsError("bad_magic", "not an Artemis PFS header", "index")
        version = header[2] - ord("0")
        if version not in SUPPORTED_VERSIONS:
            raise PfsError("unsupported_version", f"unsupported PFS version pf{version}", "index")

        if version == 0:
            count, = struct.unpack_from("<I", header, 3)
            if not 0 < count <= max_entries or count * _PF0_RECORD > max_index_size:
                raise PfsError("entry_budget", "PFS entry/index budget exceeded", "index")
            index_size = count * _PF0_RECORD
        else:
            index_size, = struct.unpack_from("<I", header, 3)
            if index_size > max_index_size:
                raise PfsError("index_budget", "PFS index exceeds the byte budget", "index")
            count_at = 4 if version == 2 else 0
            if index_size < count_at + 4:
                raise PfsError("truncated_index", "PFS index is shorter than its count field", "index")
            prefix = _read_at(stream, 7 + count_at, 4, total, "index")
            count, = struct.unpack("<I", prefix)

        index_end = 7 + index_size
        if index_end > total:
            raise PfsError("index_outside_file", "PFS index lies outside the volume", "index")
        index = _read_at(stream, 7, index_size, total, "index")
        if version == 0:
            records, used_end = _pf0_records(index, count), len(index)
        else:
            records, used_end = _parse_records(index, version, count, max_entries)

        names, encoding_used = _decode_names([record[0] for record in records], version, name_encoding)
        seen = set()
        entries = []
        for ordinal, (record, name) in enumerate(zip(records, names)):
            raw, offset, size, padding = record
            if not name or "\0" in name:
                raise PfsError("bad_name", "empty or NUL-containing PFS name", "index")
            if name in seen:
                raise PfsError("duplicate_name", f"duplicate PFS name: {name}", "index")
            seen.add(name)
            if offset < index_end or offset + size > total:
                raise PfsError("member_outside_file", f"member lies outside the volume: {name}", "index")
            entries.append(IndexEntry(ordinal, name, offset, size,
                                      int.from_bytes(padding[:4], "little"), raw, padding))
        digest = hashlib.sha1(index, usedforsecurity=False)
        return ArchiveIndex(version=version, archive_size=total, index_end=index_end,
                            index_sha1=digest.hexdigest(), name_encoding=encoding_used,
                            trailing=index[used_end:], entries=tuple(entries),
                            key=digest.digest() if version in XOR_VERSIONS else b"")
    finally:
        if close:
            stream.close()


# --------------------------------------------------------------------- members


def decode(payload: bytes, key: bytes) -> bytes:
    """Apply the pf8 cyclic XOR; an empty key means the payload is plain."""
    if not key:
        return bytes(payload)
    period = len(key)
    return bytes(value ^ key[i % period] for i, value in enumerate(payload))


def read_member(source, index: ArchiveIndex, entry: IndexEntry, *,
                max_stored_size: int = 64 << 20) -> Member:
    """Read and decode one member; a caller-owned stream stays open."""
    if type(max_stored_size) is not int or max_stored_size < 0:
        raise PfsError("bad_limit", "max_stored_size must be a nonnegative integer", "member")
    if entry.size > max_stored_size:
        raise PfsError("stored_budget", f"member exceeds the stored byte budget: {entry.name}", "member")
    stream, close = _as_stream(source)
    try:
        stored = _read_at(stream, entry.offset, entry.size, _size_of(stream))
    finally:
        if close:
            stream.close()
    return Member(entry=entry, stored=stored, data=decode(stored, index.key))


def extract(data: bytes, *, name_encoding=None, max_entries: int = 100_000,
            max_file_size: int = 64 << 20, max_total_size: int = 256 << 20,
            max_index_size: int = 32 << 20, max_archive_size: int = 512 << 20) -> list:
    """In-memory enumeration of one volume; the whole file must fit in memory.

    Kept for compatibility. Use :func:`read_index` plus :func:`read_member` for
    multi-gigabyte volumes, which the whole-file budgets here reject on purpose.
    """
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise PfsError("input_type", "extract() requires in-memory bytes", "input")
    if len(data) > max_archive_size:
        raise PfsError("archive_budget", "PFS input exceeds the whole-file budget", "input")
    for value, label in ((max_file_size, "max_file_size"), (max_total_size, "max_total_size")):
        if type(value) is not int or value < 0:
            raise PfsError("bad_limit", f"{label} must be a nonnegative integer", "index")
    index = read_index(data, name_encoding=name_encoding, max_entries=max_entries,
                       max_index_size=max_index_size, max_archive_size=max_archive_size)
    total = 0
    result = []
    for entry in index.entries:
        if entry.size > max_file_size:
            raise PfsError("member_budget", f"member exceeds the per-file budget: {entry.name}", "member")
        total += entry.size
        if total > max_total_size:
            raise PfsError("total_budget", "PFS output exceeds the total budget", "member")
        member = read_member(data, index, entry, max_stored_size=max_file_size)
        result.append(Entry(member.entry.name, member.data, member.entry.offset,
                            index.version, member.entry.unk, member.entry.ordinal))
    return result


# --------------------------------------------------------------------- volumes


def volume_paths(path) -> list:
    """Return ``[base]`` or ``[base, base.000, base.001, ...]`` for a volume set."""
    base = os.path.abspath(os.fspath(path))
    directory, name = os.path.split(base)
    if not os.path.isdir(directory):
        raise PfsError("missing_directory", "volume set directory does not exist", "input")
    # "root.pfs.010" is a sibling volume, not a distinct archive base.
    head, _, tail = name.rpartition(".")
    stem = head if (tail.isdigit() and head.lower().endswith(".pfs")) else name
    try:
        candidates = sorted(os.listdir(directory))
    except OSError as exc:
        raise PfsError("missing_directory", "volume set directory is unreadable", "input") from exc
    found = []
    for candidate in candidates:
        if candidate == stem:
            found.append(os.path.join(directory, candidate))
        elif candidate.startswith(stem + ".") and candidate[len(stem) + 1:].isdigit():
            found.append(os.path.join(directory, candidate))
    if not found:
        raise PfsError("no_volume", f"no PFS volume found for {name}", "input")
    # Base volume first, then the numbered siblings in numeric order.
    found.sort(key=lambda item: (len(os.path.basename(item)), os.path.basename(item)))
    return found


def resolve_volumes(volumes) -> VolumeSet:
    """Merge already-read indexes; a later volume overrides an earlier name.

    No precedence rule is invented: the override chain is reported and the caller
    decides. Confirm the engine's real load order before trusting the winner.
    """
    winners = {}
    order = []
    for item in volumes:
        try:
            volume_name, index = item[0], item[1]
        except (TypeError, IndexError, KeyError) as exc:
            raise PfsError("bad_volume", "volumes must be (name, ArchiveIndex) pairs", "input") from exc
        if not isinstance(index, ArchiveIndex):
            raise PfsError("bad_volume", "volume entries must be ArchiveIndex objects", "input")
        for entry in index.entries:
            previous = winners.get(entry.name)
            chain = previous.overrides + (previous.volume,) if previous else ()
            winners[entry.name] = VolumeMember(entry.name, volume_name, entry, chain)
            if previous is None:
                order.append(entry.name)
    return VolumeSet(volumes=tuple(item[0] for item in volumes),
                     members=tuple(winners[name] for name in order),
                     order=tuple(order))


# ---------------------------------------------------------------------- writer


def _padding_for(index, ordinal):
    """Return the record padding to write for one entry of an existing index."""
    for entry in index.entries:
        if entry.ordinal == ordinal:
            return entry.padding
    raise PfsError("missing_entry", f"no entry with ordinal {ordinal}", "write")


def build(entries, *, version: int = 8, name_encoding: str = "utf-8",
          trailing: bytes = b"", index_order=None, max_entries: int = 100_000,
          max_total_size: int = 512 << 20) -> bytes:
    """Build a pf0/pf2/pf6/pf8 volume from ``(name, data[, unk[, padding]])``.

    ``entries`` is the **physical** placement order. ``index_order`` optionally
    permutes the entry records inside the index, because real volumes do not keep
    the index in offset order; pass it together with the original ``trailing`` to
    reproduce an existing layout.
    """
    if version not in SUPPORTED_VERSIONS:
        raise PfsError("unsupported_version", f"cannot write pf{version}", "write")
    trailing = bytes(trailing)
    pad_len = _PF2_PADDING if version == 2 else (0 if version == 0 else 4)
    normalised = []
    total = 0
    for item in entries:
        if isinstance(item, (str, bytes)) or not isinstance(item, (tuple, list)) or not 2 <= len(item) <= 4:
            raise PfsError("bad_entry", "entries must be (name, data[, unk[, padding]])", "write")
        name, payload = item[0], item[1]
        unk = item[2] if len(item) >= 3 else 0
        padding = item[3] if len(item) == 4 else None
        if not isinstance(name, str) or not name or "\0" in name:
            raise PfsError("bad_name", "entry names must be nonempty and NUL-free", "write")
        if not isinstance(payload, (bytes, bytearray, memoryview)):
            raise PfsError("bad_entry", f"payload must be bytes: {name}", "write")
        if type(unk) is not int or not 0 <= unk <= 0xFFFFFFFF:
            raise PfsError("bad_entry", f"unknown field out of range: {name}", "write")
        if version == 0:
            try:
                raw = name.encode("ascii", errors="strict")
            except UnicodeEncodeError as exc:
                raise PfsError("bad_name", f"pf0 names are ASCII: {name}", "write") from exc
            if len(raw) > _PF0_NAME:
                raise PfsError("bad_name", f"pf0 name is too long: {name}", "write")
        else:
            try:
                raw = name.encode(name_encoding, errors="strict")
            except (UnicodeEncodeError, LookupError) as exc:
                raise PfsError("bad_name", f"name is not encodable as {name_encoding}: {name}", "write") from exc
        if version != 0 and not 0 < len(raw) <= 4096:
            raise PfsError("bad_name", f"encoded name length out of range: {name}", "write")
        if padding is None:
            padding = struct.pack("<I", unk) if pad_len == 4 else b"\0" * pad_len
        if len(padding) != pad_len:
            raise PfsError("bad_padding", f"padding must be {pad_len} bytes: {name}", "write")
        normalised.append((name, bytes(payload), raw, padding))
        total += len(payload)
    if len(normalised) > max_entries:
        raise PfsError("entry_budget", "too many entries to write", "write")
    if total > max_total_size:
        raise PfsError("total_budget", "payload bytes exceed the write budget", "write")
    if len({item[0] for item in normalised}) != len(normalised):
        raise PfsError("duplicate_name", "duplicate entry name", "write")
    order = list(range(len(normalised))) if index_order is None else list(index_order)
    if sorted(order) != list(range(len(normalised))):
        raise PfsError("bad_order", "index_order must be a permutation of the entries", "write")

    # Record = u32 name_len | name | padding | u32 offset | u32 size.
    entry_index_size = (len(normalised) * _PF0_RECORD if version == 0 else
                        (8 if version == 2 else 4) + sum(4 + len(item[2]) + pad_len + 8
                                                        for item in normalised))
    index_size = entry_index_size + len(trailing)
    position = 7 + index_size
    offsets = {}
    for i, (_name, payload, _raw, _padding) in enumerate(normalised):
        offsets[i] = position
        position += len(payload)

    index = bytearray()
    if version == 0:
        for i, (_name, payload, raw, _padding) in enumerate(normalised):
            index.extend(raw.ljust(_PF0_NAME, b"\0"))
            index.extend(struct.pack("<II", offsets[i], len(payload)))
    else:
        if version == 2:
            index.extend(b"\0" * 4)
        index.extend(struct.pack("<I", len(normalised)))
        for i in order:
            _name, payload, raw, padding = normalised[i]
            index.extend(struct.pack("<I", len(raw)))
            index.extend(raw)
            index.extend(padding)
            index.extend(struct.pack("<II", offsets[i], len(payload)))
    if len(index) != entry_index_size:
        raise PfsError("internal_layout", "recomputed index size disagrees with the layout", "write")
    index.extend(trailing)

    key = hashlib.sha1(bytes(index), usedforsecurity=False).digest() if version in XOR_VERSIONS else b""
    # pf0 stores the entry count where the other versions store index_size.
    header_field = len(normalised) if version == 0 else index_size
    # Assemble into one buffer: avoids a second full-size copy of large volumes.
    output = bytearray()
    output.extend(MAGIC + str(version).encode("ascii") + struct.pack("<I", header_field))
    output.extend(index)
    for _name, payload, _raw, _padding in normalised:
        output.extend(decode(payload, key) if key else payload)
    return bytes(output)


def repack(index: ArchiveIndex, payloads, *, max_entries: int = 100_000,
           max_total_size: int = 512 << 20, version=None) -> bytes:
    """Rebuild a volume from an existing index, replacing selected payloads.

    ``payloads`` maps an ordinal to new decoded bytes and must cover every entry.
    Entry order, each record's unknown field and padding, and the trailing table
    are preserved, and payloads are laid out in the original offset order, so an
    unchanged volume rebuilds to identical bytes.
    """
    physical = sorted(index.entries, key=lambda item: (item.offset, item.ordinal))
    position = {entry.ordinal: i for i, entry in enumerate(physical)}
    data = []
    for entry in physical:
        if entry.ordinal not in payloads:
            raise PfsError("missing_payload", f"no payload supplied for {entry.name}", "write")
        payload = payloads[entry.ordinal]
        if not isinstance(payload, (bytes, bytearray, memoryview)):
            raise PfsError("bad_entry", f"payload must be bytes: {entry.name}", "write")
        data.append((entry.name, payload, entry.unk, entry.padding))
    order = [position[entry.ordinal] for entry in index.entries]
    return build(data, version=index.version if version is None else version,
                 name_encoding=index.name_encoding, trailing=index.trailing,
                 index_order=order, max_entries=max_entries, max_total_size=max_total_size)
