"""Bounded BGI PackFile/BURIKO ARC20 rewriter; no image/BSE encoding.

Pairs with archives/bgi.py. Only the container layout documented there is
produced: signature, u32 count, then fixed-stride name/offset/size rows, then
the stored members in the caller's order. Member payloads are treated as
opaque bytes, so this writer never invents an encoding for images, audio or
BSE; DSC re-compression is done by archives/bgi_dsc.encode before a member is
handed here.

Reference: GARbro-Mod, ArcFormats/Ethornell/ArcBGI.cs, ArcOpener/Arc2Opener
(BgiArchiveWriter layout) at bc26d991ef5cdc0e1ecb32122ee9a48c3375750c (MIT);
also checked against msg-tool src/scripts/bgi/archive/{v1,v2}.rs,
BgiArchiveWriter::{new_file,write_header} at
f72716cee88554d40c1cdface2812493b14ca653 (GPL-3.0-or-later).

GPL-derived additions are free software: you can redistribute and/or modify
under the terms of the GNU General Public License as published by the Free
Software Foundation, either version 3 of the License, or (at your option) any
later version. Distributed WITHOUT ANY WARRANTY; without even the implied
warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
../../LICENSE and ../../provenance/licenses/GPL-3.0.txt.
"""
import io
import struct

from . import bgi_dsc
from .bgi import BgiArchiveError, read_index, read_member, _limit

# version -> (signature, table stride, encoded name field size)
LAYOUTS = {
    1: (b"PackFile    ", 0x20, 0x10),
    2: (b"BURIKO ARC20", 0x80, 0x60),
}


def _fail(message, code, offset=None, stage="write"):
    raise BgiArchiveError(message, code=code, stage=stage, offset=offset)


def row_length(version: int) -> int:
    """Bytes that follow the u32 size field in one index row."""
    signature, stride, name_size = LAYOUTS[version]
    return stride - name_size - 8


def build_archive(members, *, version: int = 2, name_encoding: str = "cp932",
                  max_members: int = 100_000, max_total_size: int = 512 << 20,
                  verify: bool = True) -> bytes:
    """Assemble one archive from ordered member tuples.

    Each member is (name, stored_bytes) or (name, stored_bytes, extra), where
    `extra` is the row_length(version) opaque byte region that follows the size
    field. Real BGI v2 archives store non-zero bytes there; their meaning is
    unknown to both referenced readers, which ignore them, so a faithful rebuild
    must carry them over rather than silently zero them. The original region is
    available as IndexEntry.extra from archives/bgi.py's read_index.

    Names must round-trip through name_encoding, fit the fixed name field and be
    unique; order is preserved because it is part of the member identity. With
    verify=True the result is re-indexed and every member re-read through the
    reader in this package, so a layout mistake cannot be returned as success.
    """
    _limit(max_members, "max_members", "write")
    _limit(max_total_size, "max_total_size", "write")
    if version not in LAYOUTS:
        _fail("unsupported BGI archive version", "unsupported_version")
    signature, stride, name_size = LAYOUTS[version]
    trailing = row_length(version)
    try:
        "".encode(name_encoding, errors="strict")
    except (LookupError, UnicodeError):
        _fail("invalid BGI name encoding", "invalid_encoding")

    rows = []
    for member in members:
        if not isinstance(member, tuple) or len(member) not in (2, 3):
            _fail("BGI members must be (name, bytes[, extra]) tuples", "input_type")
        name, payload = member[0], member[1]
        extra = member[2] if len(member) == 3 else b"\0" * trailing
        if not isinstance(name, str) or not isinstance(payload, bytes):
            _fail("BGI members must be (str, bytes) pairs", "input_type")
        if not isinstance(extra, bytes) or len(extra) != trailing:
            _fail("BGI row extra region has the wrong length", "row_extra")
        rows.append((name, payload, extra))
    if not rows:
        # The reader requires 0 < count, so an empty archive is not representable.
        _fail("a BGI archive needs at least one member", "empty_archive")
    if len(rows) > max_members:
        _fail("BGI member count budget", "manifest_budget")

    table, body, names, total = bytearray(), bytearray(), set(), 0
    for name, payload, extra in rows:
        try:
            encoded = name.encode(name_encoding, errors="strict")
        except (LookupError, UnicodeError):
            _fail("BGI member name is not representable", "invalid_name")
        if not encoded or b"\0" in encoded or len(encoded) > name_size:
            _fail("BGI member name does not fit its fixed field", "invalid_name")
        if name in names:
            _fail("duplicate BGI member name", "duplicate_name")
        names.add(name)
        total += len(payload)
        if total > max_total_size:
            _fail("BGI stored size budget", "stored_budget")
        table.extend(encoded.ljust(name_size, b"\0")
                     + struct.pack("<II", len(body), len(payload)) + extra)
        body.extend(payload)
    # Offsets are stored relative to the end of the index, exactly as the
    # reader computes them.
    archive = signature + struct.pack("<I", len(rows)) + bytes(table) + bytes(body)
    if verify:
        _verify(archive, rows, name_encoding)
    return archive


def _verify(archive: bytes, rows, name_encoding: str) -> None:
    """Re-read the produced bytes through the reader and compare everything."""
    stream = io.BytesIO(archive)
    index = read_index(stream, name_encoding=name_encoding, max_entries=max(len(rows), 1),
                       max_index_size=max(len(archive), 1))
    if [entry.name for entry in index.entries] != [name for name, _, _ in rows]:
        _fail("writer verification failed: member order/name mismatch", "write_mismatch")
    for entry, (name, payload, _) in zip(index.entries, rows):
        stored = read_member(stream, index, entry,
                             max_stored_size=max(len(payload), 1))
        if stored.stored_data != payload:
            _fail("writer verification failed: member bytes mismatch", "write_mismatch",
                  entry.offset)


def pack_member(data: bytes, *, compress: bool = True, allow_plain: bool = True,
                **options) -> bytes:
    """Return the stored form of one member: DSC when asked, else plain bytes.

    `allow_plain` refuses to silently store uncompressed bytes, because a game
    that expects the DSC wrapper will not load them.
    """
    if not isinstance(data, bytes):
        _fail("BGI member payload must be bytes", "input_type")
    if not compress:
        if not allow_plain:
            _fail("plain BGI members are not accepted for this archive", "unsupported_codec")
        return data
    return bgi_dsc.encode(data, **options)
