# SPDX-License-Identifier: GPL-3.0-only
# Adapted from SExtractor tools/ScenePlayer/pmx_pack.py
# Source commit: 8d8d976fd04ae54e7c677705af937273d04a376a
# Upstream attribution: Steins;Gate; SExtractor contributors.
"""ScenePlayer PMX script archive (zlib then XOR 0x21), not a text VM writer."""
import struct
import zlib


def _name(name, encoding):
    if not name or any(c in name for c in "\x00\\:") or any(p in ("", ".", "..") for p in name.split("/")):
        raise ValueError("invalid PMX relative name")
    raw = name.encode(encoding)
    if len(raw) > 31:
        raise ValueError("PMX name exceeds 31 encoded bytes")
    return raw


def pack_pmx(members, *, name_encoding="utf-8"):
    members = list(members)
    if not 0 < len(members) <= 100_000:
        raise ValueError("invalid PMX count")
    index, bodies, seen = bytearray(), [], set()
    for name, raw in members:
        encoded = _name(name, name_encoding)
        if name in seen:
            raise ValueError("duplicate PMX name")
        seen.add(name)
        index.extend(encoded.ljust(32, b"\x00") + struct.pack("<I", len(raw)))
        bodies.append(raw)
    plain = struct.pack("<I", len(members)) + index + b"".join(bodies)
    return bytes(b ^ 0x21 for b in zlib.compress(plain))


def unpack_pmx(data, *, name_encoding="utf-8", max_output=64 * 1024 * 1024):
    if not data or data[0] != (0x78 ^ 0x21) or max_output < 4:
        raise ValueError("not a supported PMX stream")
    dec = zlib.decompressobj()
    plain = dec.decompress(bytes(b ^ 0x21 for b in data), max_output + 1)
    if len(plain) > max_output or not dec.eof or dec.unused_data or dec.unconsumed_tail or len(plain) < 4:
        raise ValueError("invalid/budget-exceeding PMX zlib stream")
    count = struct.unpack_from("<I", plain)[0]
    cursor = 4 + count * 36
    if not 0 < count <= 100_000 or cursor > len(plain):
        raise ValueError("invalid PMX index")
    result, seen = [], set()
    for i in range(count):
        pos = 4 + 36 * i
        field = plain[pos:pos + 32]
        if b"\x00" not in field:
            raise ValueError("unterminated PMX name")
        name = field.split(b"\x00", 1)[0].decode(name_encoding)
        _name(name, name_encoding)
        size = struct.unpack_from("<I", plain, pos + 32)[0]
        if name in seen or size > len(plain) - cursor:
            raise ValueError("invalid PMX member")
        seen.add(name)
        result.append((name, plain[cursor:cursor + size]))
        cursor += size
    if cursor != len(plain):
        raise ValueError("unindexed PMX bytes")
    return result
