# SPDX-License-Identifier: GPL-3.0-only
"""Kaguya ``TBLSTR.ARC`` string records: three directory dialects, fixed slots.

Every record starts at an absolute address and holds ``i32 message id``,
``i32 length`` and XOR-0xFF text bytes. Three ways to find the addresses exist:

* companion ``.ari`` index: ``i32`` addresses from offset 4 to EOF; the text
  region is ``length - 2`` bytes, so the final two bytes of the record are kept;
* the archive itself starting with ``B8 33 25 00``: same address list, but the
  caller must supply the ``.ari`` because there is no embedded index;
* ``UF01``: ``u32 index offset`` at 4, then ``u32`` addresses to EOF; the text
  region is ``length`` bytes with no extra trailer.

Provenance: the three dialect rules and the ``length - 2`` distinction follow the
``KaguyaTblStr`` handlers in "翻译肋手 v4.9D". That tool decrypts and rewrites in
place with a fixed slot; this module keeps the same fixed-slot constraint but
validates every address before use, refuses overlapping records, and verifies
the rewritten bytes by re-reading the archive.
"""
from dataclasses import dataclass
import struct

EMBEDDED_MAGIC = b"\xb8\x33\x25\x00"
UF01_MAGIC = b"UF01"
MAX_FILE = 64 << 20
MAX_ENTRIES = 200_000
MAX_TEXT = 1 << 20


@dataclass(frozen=True)
class TblEntry:
    index: int
    address: int
    message_id: int
    length: int              # writable text bytes
    raw: bytes               # decrypted text bytes
    trailer: bytes           # bytes after the text region, kept verbatim


@dataclass(frozen=True)
class TblArchive:
    dialect: str             # "ari" / "embedded" / "uf01"
    ari: bytes | None
    addresses: tuple
    entries: tuple


def _xor(data):
    return bytes(value ^ 0xFF for value in data)


def _read_int32_list(blob, start, what):
    if start < 0 or start > len(blob) or (len(blob) - start) % 4:
        raise ValueError(f"{what} does not hold whole i32 addresses")
    count = (len(blob) - start) // 4
    if count > MAX_ENTRIES:
        raise ValueError(f"{what} address count exceeds the budget")
    return struct.unpack_from(f"<{count}i", blob, start)


def _read_u32_list(blob, start, what):
    if start < 0 or start > len(blob) or (len(blob) - start) % 4:
        raise ValueError(f"{what} does not hold whole u32 addresses")
    count = (len(blob) - start) // 4
    if count > MAX_ENTRIES:
        raise ValueError(f"{what} address count exceeds the budget")
    return struct.unpack_from(f"<{count}I", blob, start)


def _dialect(data, ari):
    if data[:4] == EMBEDDED_MAGIC:
        if ari is None:
            raise ValueError("this TBLSTR needs its .ari companion index")
        return "embedded", _read_int32_list(ari, 4, "ari index")
    if ari is not None:
        return "ari", _read_int32_list(ari, 4, "ari index")
    if data[:4] == UF01_MAGIC:
        if len(data) < 8:
            raise ValueError("UF01 header is truncated")
        offset = struct.unpack_from("<I", data, 4)[0]
        if not 4 <= offset < len(data):
            raise ValueError("UF01 index offset is outside the file")
        return "uf01", _read_u32_list(data, offset, "UF01 index")
    raise ValueError("not a Kaguya TBLSTR archive")


def open_tblstr(data, ari=None, *, encoding="cp932"):
    """Parse the address list and every record; text stays decrypted in memory."""
    if not isinstance(data, bytes) or not data or len(data) > MAX_FILE:
        raise ValueError("TBLSTR input is not a bounded bytes object")
    if ari is not None and (not isinstance(ari, bytes) or len(ari) > MAX_FILE):
        raise ValueError("TBLSTR .ari input is not a bounded bytes object")
    dialect, addresses = _dialect(data, ari)
    trailer_size = 0 if dialect == "uf01" else 2
    entries, seen = [], set()
    for index, address in enumerate(addresses):
        if address < 0 or address in seen:
            raise ValueError("TBLSTR address is negative or duplicated")
        seen.add(address)
        if address + 8 > len(data):
            raise ValueError("TBLSTR record header is outside the file")
        message_id, length = struct.unpack_from("<ii", data, address)
        text_size = length if dialect == "uf01" else length - 2
        if text_size < 0 or text_size > MAX_TEXT:
            raise ValueError("TBLSTR record length out of range")
        end = address + 8 + text_size
        if end > len(data):
            raise ValueError("TBLSTR record crosses the file")
        raw = _xor(data[address + 8:end])
        try:
            raw.decode(encoding)
        except UnicodeDecodeError as exc:
            raise ValueError(f"TBLSTR record {index} is not {encoding}") from exc
        entries.append(TblEntry(index, address, message_id, text_size, raw,
                                data[end:end + trailer_size]))
        if len(entries) > MAX_ENTRIES:
            raise ValueError("TBLSTR entry count exceeds the budget")
    return TblArchive(dialect, ari, tuple(addresses), tuple(entries))


def read_entry(archive, entry, *, encoding="cp932"):
    """Decode one already-decrypted record."""
    return entry.raw.decode(encoding)


def patch_tblstr(data, archive, replacements, *, encoding="gbk", fill=0x20):
    """Rewrite selected records at their fixed slot and re-read the result."""
    if not isinstance(archive, TblArchive) or not isinstance(replacements, dict):
        raise ValueError("TBLSTR patch needs a parsed archive and a mapping")
    if set(replacements) - set(range(len(archive.entries))):
        raise ValueError("unknown TBLSTR entry")
    if not 0 <= fill <= 0xFF:
        raise ValueError("invalid TBLSTR fill byte")
    buffer = bytearray(data)
    expected = {}
    for index, value in sorted(replacements.items()):
        entry = archive.entries[index]
        if not isinstance(value, str) or "\0" in value:
            raise ValueError("invalid TBLSTR text")
        try:
            encoded = value.encode(encoding, errors="strict")
        except UnicodeEncodeError as exc:
            raise ValueError(f"TBLSTR entry {index} is not encodable as {encoding}") from exc
        if len(encoded) > entry.length:
            raise ValueError(f"TBLSTR entry {index} does not fit {entry.length} bytes")
        plain = encoded + bytes([fill]) * (entry.length - len(encoded))
        start = entry.address + 8
        buffer[start:start + entry.length] = _xor(plain)
        expected[index] = plain
    result = bytes(buffer)
    again = open_tblstr(result, archive.ari, encoding="latin-1")
    if len(again.entries) != len(archive.entries):
        raise ValueError("TBLSTR entry count changed on write")
    for index, entry in enumerate(again.entries):
        if entry.address != archive.entries[index].address or entry.length != archive.entries[index].length:
            raise ValueError("TBLSTR slot identity changed on write")
        want = expected.get(index, archive.entries[index].raw)
        if entry.raw != want:
            raise ValueError(f"TBLSTR entry {index} round trip differs")
    return result
