# SPDX-License-Identifier: GPL-3.0-only
# Adapted from SExtractor tools/Yatagarasu/pkg_pack_v1.py
# Source commit: 8d8d976fd04ae54e7c677705af937273d04a376a
# Upstream attribution: Steins;Gate; SExtractor contributors.
"""Yatagarasu PKG v1 index/member encryption; explicit key, no plaintext text guessing."""
import struct


def _xor(data, key):
    return bytes(b ^ key[i % 4] for i, b in enumerate(data))


def _key(value):
    if not 0 <= value <= 0xFFFFFFFF:
        raise ValueError("PKG key must be uint32")
    return struct.pack("<I", value)


def _name(name):
    if not name or any(c in name for c in "\x00/:") or any(p in ("", ".", "..") for p in name.split("\\")):
        raise ValueError("invalid PKG relative name; use backslashes")
    raw = name.encode("utf-8")
    if len(raw) > 123:
        raise ValueError("PKG name would collide with reserved key bytes")
    return raw


def pack_pkg(members, *, key):
    kb, members = _key(key), list(members)
    if not 0 < len(members) <= 100_000:
        raise ValueError("invalid PKG count")
    index, payload, seen = bytearray(), bytearray(), set()
    base = 8 + len(members) * 136
    for name, raw in members:
        nb = _name(name)
        if name in seen:
            raise ValueError("duplicate PKG name")
        seen.add(name)
        index.extend(nb.ljust(128, b"\x00") + struct.pack("<II", len(raw), base + len(payload)))
        payload.extend(_xor(raw, kb))  # restart key phase at EACH member
    encrypted = bytearray(_xor(index, kb))
    for i in range(min(2, len(members))):
        encrypted[i * 136 + 124:i * 136 + 128] = kb
    total = base + len(payload)
    return struct.pack("<I", total ^ key) + _xor(struct.pack("<I", len(members)), kb) + encrypted + payload


def unpack_pkg(data, *, key, max_output=64 * 1024 * 1024):
    kb = _key(key)
    if len(data) < 144 or struct.unpack_from("<I", data)[0] != len(data) ^ key:
        raise ValueError("PKG size/key signature mismatch")
    count = struct.unpack("<I", _xor(data[4:8], kb))[0]
    base = 8 + count * 136
    if not 0 < count <= 100_000 or base > len(data):
        raise ValueError("invalid PKG index")
    for i in range(min(2, count)):
        if data[8 + i * 136 + 124:8 + i * 136 + 128] != kb:
            raise ValueError("PKG embedded key disagrees with explicit key")
    index = _xor(data[8:base], kb)
    result, cursor, used, seen = [], base, 0, set()
    for i in range(count):
        pos = i * 136
        field = index[pos:pos + 128]
        if b"\x00" not in field:
            raise ValueError("unterminated PKG name")
        name = field.split(b"\x00", 1)[0].decode("utf-8")
        _name(name)
        size, offset = struct.unpack_from("<II", index, pos + 128)
        if name in seen or offset != cursor or size > len(data) - offset or size > max_output - used:
            raise ValueError("invalid PKG placement/output budget")
        seen.add(name)
        result.append((name, _xor(data[offset:offset + size], kb)))
        cursor, used = offset + size, used + size
    if cursor != len(data):
        raise ValueError("unindexed PKG tail")
    return result
