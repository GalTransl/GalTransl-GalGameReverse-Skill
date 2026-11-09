"""Electron asar archives: bounded header parsing, member reads, streamed rebuild.

New implementation for this skill (standard library only). Layout follows the
public asar format used by Electron (electron/asar, MIT): a Chromium pickle
holding the header length, a JSON directory tree with string offsets relative
to the data region, and contiguous member bytes. Members marked ``unpacked``
live in ``<archive>.unpacked/`` and have no bytes inside the archive.

The rebuild keeps every unchanged member byte, the member order and any gaps;
only replaced members change size and later offsets shift. Per-file
``integrity`` records are recomputed for replaced members. An Electron build
that validates the whole header hash from its executable will still reject
a modified archive; that is a deployment check, not something this module
can fix.
"""

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import struct

from python.common.binary import FormatError
from python.common.safety import Limits, logical_path, validate_names

MAX_HEADER_BYTES = 64 << 20
MAX_DEPTH = 64
COPY_CHUNK = 8 << 20


@dataclass(frozen=True)
class Entry:
    path: str
    size: int
    offset: int | None      # relative to the data region; None when unpacked
    unpacked: bool
    integrity: dict | None


@dataclass(frozen=True)
class Index:
    header: dict            # parsed JSON tree, original key order
    header_json: bytes      # exact JSON bytes as stored
    header_padding: bytes   # pickle alignment bytes after the JSON
    data_offset: int        # absolute offset of the data region
    file_size: int
    entries: tuple[Entry, ...]
    links: tuple[str, ...]

    def member(self, path: str) -> Entry:
        for entry in self.entries:
            if entry.path == path:
                return entry
        raise KeyError(path)


def _read_exact(stream, offset: int, size: int) -> bytes:
    stream.seek(offset)
    data = stream.read(size)
    if len(data) != size:
        raise FormatError("truncated asar read")
    return data


def _stream_size(stream) -> int:
    position = stream.tell()
    stream.seek(0, 2)
    size = stream.tell()
    stream.seek(position)
    return size


def _walk(node, prefix, depth, entries, links, limits):
    if depth > MAX_DEPTH:
        raise FormatError("asar directory tree too deep")
    files = node.get("files")
    if not isinstance(files, dict):
        raise FormatError("asar directory node without a files object")
    for name, child in files.items():
        if not isinstance(name, str) or not name or "/" in name or "\\" in name:
            raise FormatError(f"unsafe asar member name: {name!r}")
        path = f"{prefix}/{name}" if prefix else name
        logical_path(path, max_chars=limits.max_path_chars)
        if not isinstance(child, dict):
            raise FormatError(f"asar node is not an object: {path}")
        if "files" in child:
            _walk(child, path, depth + 1, entries, links, limits)
        elif "link" in child:
            links.append(path)
        else:
            size = child.get("size")
            if type(size) is not int or size < 0:
                raise FormatError(f"asar member size is not a nonnegative integer: {path}")
            unpacked = child.get("unpacked") is True
            offset = None
            if not unpacked:
                raw = child.get("offset")
                if not isinstance(raw, str) or not raw.isdigit():
                    raise FormatError(f"asar member offset is not a decimal string: {path}")
                offset = int(raw)
            integrity = child.get("integrity")
            if integrity is not None and not isinstance(integrity, dict):
                raise FormatError(f"asar integrity record is not an object: {path}")
            entries.append(Entry(path, size, offset, unpacked, integrity))
        if len(entries) + len(links) > limits.max_entries:
            raise FormatError("asar entry count exceeds limit")


def read_index(stream, *, limits: Limits = Limits(), max_header: int = MAX_HEADER_BYTES) -> Index:
    """Parse and bound-check the header; never reads member bytes."""
    file_size = _stream_size(stream)
    if file_size < 16:
        raise FormatError("short asar file")
    size_field, header_pickle, payload, json_size = struct.unpack("<4I", _read_exact(stream, 0, 16))
    if size_field != 4 or header_pickle != payload + 4:
        raise FormatError("not an asar header pickle")
    if json_size > max_header or payload != 4 + ((json_size + 3) & ~3):
        raise FormatError("asar header length fields disagree or exceed budget")
    data_offset = 8 + header_pickle
    if data_offset > file_size:
        raise FormatError("asar header runs past end of file")
    header_json = _read_exact(stream, 16, json_size)
    padding = _read_exact(stream, 16 + json_size, payload - 4 - json_size)
    try:
        header = json.loads(header_json.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise FormatError(f"asar header is not UTF-8 JSON: {exc}") from exc
    if not isinstance(header, dict):
        raise FormatError("asar header root is not an object")
    entries, links = [], []
    _walk(header, "", 0, entries, links, limits)
    validate_names([entry.path for entry in entries] + links, limits)
    end = 0
    for entry in sorted((e for e in entries if not e.unpacked), key=lambda e: (e.offset, e.size)):
        if entry.offset < end and entry.size:
            raise FormatError(f"overlapping asar members: {entry.path}")
        end = max(end, entry.offset + entry.size)
    if data_offset + end > file_size:
        raise FormatError("asar member data runs past end of file")
    return Index(header, header_json, padding, data_offset, file_size, tuple(entries), tuple(links))


def read_member(stream, index: Index, entry: Entry, *, max_bytes: int = 128 << 20) -> bytes:
    if entry.unpacked:
        raise FormatError(f"member is stored outside the archive (unpacked): {entry.path}")
    if entry.size > max_bytes:
        raise FormatError(f"asar member exceeds read budget: {entry.path}")
    return _read_exact(stream, index.data_offset + entry.offset, entry.size)


def _integrity(old: dict, data: bytes) -> dict:
    if old.get("algorithm") != "SHA256" or type(old.get("blockSize")) is not int or old["blockSize"] <= 0:
        raise FormatError("unsupported asar integrity record")
    block = old["blockSize"]
    blocks = [hashlib.sha256(data[i:i + block]).hexdigest() for i in range(0, len(data), block)] or \
        [hashlib.sha256(b"").hexdigest()]
    return {"algorithm": "SHA256", "hash": hashlib.sha256(data).hexdigest(),
            "blockSize": block, "blocks": blocks}


def _node(header: dict, path: str) -> dict:
    node = header
    for part in path.split("/"):
        node = node["files"][part]
    return node


def plan_rebuild(index: Index, replacements: dict[str, bytes]) -> tuple[bytes, dict[str, int]]:
    """Return (new header prefix bytes, new relative offsets) for the replacements."""
    packed = {e.path: e for e in index.entries if not e.unpacked}
    for path, data in replacements.items():
        if path not in packed:
            raise FormatError(f"replacement is not a packed asar member: {path}")
        if not isinstance(data, bytes):
            raise FormatError(f"replacement is not bytes: {path}")
    offsets, shift = {}, 0
    for entry in sorted(packed.values(), key=lambda e: (e.offset, e.size)):
        offsets[entry.path] = entry.offset + shift
        if entry.path in replacements:
            shift += len(replacements[entry.path]) - entry.size
    if not replacements:
        header_json, padding = index.header_json, index.header_padding
    else:
        header = deepcopy(index.header)
        for path, entry in packed.items():
            node = _node(header, path)
            node["offset"] = str(offsets[path])
            if path in replacements:
                data = replacements[path]
                node["size"] = len(data)
                if entry.integrity is not None:
                    node["integrity"] = _integrity(entry.integrity, data)
        header_json = json.dumps(header, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        padding = bytes((-len(header_json)) % 4)
    payload = 4 + len(header_json) + len(padding)
    prefix = struct.pack("<4I", 4, payload + 4, payload, len(header_json)) + header_json + padding
    return prefix, offsets


def rebuilt_size(index: Index, replacements: dict[str, bytes]) -> int:
    prefix, _ = plan_rebuild(index, replacements)
    delta = sum(len(data) - index.member(path).size for path, data in replacements.items())
    return len(prefix) + (index.file_size - index.data_offset) + delta


def write_rebuilt(source, index: Index, replacements: dict[str, bytes], sink) -> int:
    """Stream a rebuilt archive into ``sink``; unchanged bytes are copied verbatim."""
    prefix, _ = plan_rebuild(index, replacements)
    sink.write(prefix)
    written = len(prefix)

    def copy(start, end):
        nonlocal written
        source.seek(start)
        remaining = end - start
        while remaining:
            chunk = source.read(min(COPY_CHUNK, remaining))
            if not chunk:
                raise FormatError("asar source shrank during rebuild")
            sink.write(chunk)
            remaining -= len(chunk)
            written += len(chunk)

    cursor = index.data_offset
    for entry in sorted((e for e in index.entries if not e.unpacked), key=lambda e: (e.offset, e.size)):
        start = index.data_offset + entry.offset
        copy(cursor, start)
        if entry.path in replacements:
            sink.write(replacements[entry.path])
            written += len(replacements[entry.path])
        else:
            copy(start, start + entry.size)
        cursor = start + entry.size
    copy(cursor, index.file_size)
    return written


def verify_rebuilt(original, original_index: Index, rebuilt, replacements: dict[str, bytes]) -> dict:
    """Re-read the new archive and compare every packed member with its source."""
    index = read_index(rebuilt)
    old = {e.path: e for e in original_index.entries}
    new = {e.path: e for e in index.entries}
    if list(old) != list(new) or original_index.links != index.links:
        raise FormatError("rebuilt asar member set or order changed")
    compared = 0
    for path, entry in new.items():
        before = old[path]
        if entry.unpacked != before.unpacked:
            raise FormatError(f"rebuilt asar changed unpacked flag: {path}")
        if entry.unpacked:
            continue
        if path in replacements:
            if read_member(rebuilt, index, entry, max_bytes=len(replacements[path])) != replacements[path]:
                raise FormatError(f"rebuilt asar member differs from replacement: {path}")
        else:
            if entry.size != before.size:
                raise FormatError(f"unchanged asar member size changed: {path}")
            remaining, a, b = entry.size, original_index.data_offset + before.offset, index.data_offset + entry.offset
            while remaining:
                step = min(COPY_CHUNK, remaining)
                if _read_exact(original, a, step) != _read_exact(rebuilt, b, step):
                    raise FormatError(f"unchanged asar member bytes differ: {path}")
                a, b, remaining = a + step, b + step, remaining - step
        compared += 1
    return {"members_compared": compared, "replaced": sorted(replacements),
            "header_reserialized": bool(replacements)}
