# SPDX-License-Identifier: GPL-3.0-only
"""NekoSDK NEKOPACK4 archive: 14-byte header, XOR-named index, zlib members.

Header: ``NEKOPACK4`` (9), mode byte ``A`` (0x41), u32 index size at 10; the
index starts at 14 and the payload area follows ``14 + index_size``.

Index entry: u32 name length (includes one trailing NUL, 0 terminates the
index), CP932 name bytes, then u32 offset and u32 size, both XORed with
``checksum = sum(signed byte of the name bytes incl. NUL)``.

Member: ``stored[0:4]`` is XORed with a rolling key ``size // 8 + 34`` (shifted
left by 3 after each byte), followed by a zlib stream, then a u32 uncompressed
size. Stored size counts the 4-byte tail, not only the compressed stream.

Provenance: layout, checksum and member transform follow ``GameRes.NEKOSDK.
ArcPAK`` in the GARbro-derived code bundled with "翻译肋手 v4.9D". Independent
rewrite with bounded parsing; only mode ``A`` is accepted because the ``S``
variant was not exercised by the reference packer.
"""
from dataclasses import dataclass
import struct
import zlib

MAGIC = b"NEKOPACK4"
HEADER_SIZE = 14
MODE_A = 0x41
MODE_S = 0x53
MAX_ENTRIES = 100_000
MAX_NAME = 256
MAX_MEMBER = 256 << 20


@dataclass(frozen=True)
class PakEntry:
    name: str
    offset: int
    size: int


@dataclass(frozen=True)
class PakArchive:
    mode: str
    data_offset: int
    entries: tuple


def name_checksum(raw_name):
    """Signed-byte sum of the stored name bytes, including its NUL."""
    return sum(b - 256 if b > 127 else b for b in raw_name)


def xor_head(stored, size):
    """XOR the first four stored bytes with the rolling member key."""
    key = size // 8 + 34
    out = bytearray(stored[:4])
    for i in range(len(out)):
        out[i] ^= key & 0xFF
        key = (key << 3) & 0xFFFFFFFF
    return bytes(out)


def open_pak(data):
    if not isinstance(data, bytes) or len(data) < HEADER_SIZE:
        raise ValueError("NEKOPACK too small")
    if data[:9] != MAGIC or data[9] not in (MODE_A, MODE_S):
        raise ValueError("not a NEKOPACK4 archive (mode A/S)")
    mode = chr(data[9])
    index_size, = struct.unpack_from("<I", data, 10)
    start = 14 if mode == "A" else 10
    end = start + index_size + (0 if mode == "A" else 12)
    if end > len(data):
        raise ValueError("NEKOPACK index exceeds the file")
    entries, pos = [], start
    while pos < end:
        if pos + 4 > len(data):
            raise ValueError("truncated NEKOPACK index")
        name_len, = struct.unpack_from("<I", data, pos)
        pos += 4
        if name_len == 0:
            break
        if name_len > MAX_NAME or pos + name_len + 8 > len(data):
            raise ValueError("NEKOPACK name length out of range")
        raw_name = data[pos:pos + name_len]
        if raw_name[-1] != 0:
            raise ValueError("NEKOPACK name is not NUL terminated")
        try:
            name = raw_name[:-1].decode("cp932")
        except UnicodeDecodeError as exc:
            raise ValueError("NEKOPACK name is not CP932") from exc
        pos += name_len
        checksum = name_checksum(raw_name)
        offset, size = struct.unpack_from("<II", data, pos)
        offset ^= checksum & 0xFFFFFFFF
        size ^= checksum & 0xFFFFFFFF
        pos += 8
        if not name or offset + size > len(data) or size > MAX_MEMBER:
            raise ValueError(f"NEKOPACK member {name!r} exceeds the file")
        entries.append(PakEntry(name, offset, size))
        if len(entries) > MAX_ENTRIES:
            raise ValueError("NEKOPACK entry count exceeds limit")
    if not entries:
        raise ValueError("NEKOPACK archive has no entries")
    return PakArchive(mode, end, tuple(entries))


def read_member(data, entry):
    if entry.size < 8:
        raise ValueError("NEKOPACK member is too small for its header and size")
    head = xor_head(data[entry.offset:entry.offset + 4], entry.size)
    body = data[entry.offset + 4:entry.offset + entry.size - 4]
    unpacked, = struct.unpack_from("<i", data, entry.offset + entry.size - 4)
    if not 0 <= unpacked <= MAX_MEMBER:
        raise ValueError("NEKOPACK stored size field out of range")
    stream = zlib.decompressobj()
    raw = stream.decompress(head + body, unpacked + 1)
    if len(raw) != unpacked or not stream.eof or stream.unused_data or stream.unconsumed_tail:
        raise ValueError("NEKOPACK zlib stream mismatch")
    return raw


def build_pak(members):
    """Write a mode-A archive from ``name -> bytes``; index precedes payloads."""
    if not isinstance(members, dict) or not members:
        raise ValueError("NEKOPACK needs at least one member")
    index = bytearray()
    encoded = []
    for name, payload in members.items():
        if not isinstance(name, str) or not name or not isinstance(payload, bytes):
            raise ValueError("invalid NEKOPACK member")
        raw_name = name.encode("cp932", errors="strict") + b"\x00"
        if len(raw_name) > MAX_NAME:
            raise ValueError(f"NEKOPACK name too long: {name!r}")
        stored = zlib.compress(payload, 9)
        size = len(stored) + 4
        head = xor_head(stored, size)
        encoded.append((raw_name, head + stored[4:] + struct.pack("<I", len(payload)), size))
    offset = HEADER_SIZE + sum(4 + len(n) + 8 for n, _, _ in encoded)
    body = bytearray()
    for raw_name, stored, size in encoded:
        checksum = name_checksum(raw_name)
        index += struct.pack("<I", len(raw_name)) + raw_name
        index += struct.pack("<II", (offset + len(body)) ^ (checksum & 0xFFFFFFFF),
                             size ^ (checksum & 0xFFFFFFFF))
        body += stored
    header = MAGIC + b"A" + struct.pack("<I", len(index))
    result = header + bytes(index) + bytes(body)
    archive = open_pak(result)
    if len(archive.entries) != len(members):
        raise ValueError("NEKOPACK entry count changed on build")
    for entry in archive.entries:
        if read_member(result, entry) != members[entry.name]:
            raise ValueError(f"NEKOPACK member {entry.name!r} does not round trip")
    return result
