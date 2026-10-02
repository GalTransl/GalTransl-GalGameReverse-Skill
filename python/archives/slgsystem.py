# SPDX-License-Identifier: GPL-3.0-only
# Adapted from SExtractor tools/SLGSystem/szs_tool.py
# Source commit: 8d8d976fd04ae54e7c677705af937273d04a376a
# Upstream attribution: Steins;Gate & 多了芒果; SExtractor contributors.
"""SZS100__ archive stage. Seed and XOR/subtraction variant are always explicit."""
import struct


def crypt_member(data, *, seed, mode, decrypt):
    if mode not in ("xor", "sub") or not 0 <= seed <= 0xFFFFFFFF:
        raise ValueError("invalid SZS seed or cipher mode")
    out, state = bytearray(), seed
    for value in data:
        state = (state * 0x343FD + 0x269EC3) & 0xFFFFFFFF
        key = (state >> 16) & 255
        if decrypt:
            value ^= 0x90
            value = value ^ key if mode == "xor" else (value - key) & 255
        else:
            value = value ^ key if mode == "xor" else (value + key) & 255
            value ^= 0x90
        out.append(value)
    return bytes(out)


def _name(name):
    if not name or "\x00" in name or "\\" in name or ";" in name:
        raise ValueError("use relative slash-separated SZS names")
    if any(p in ("", ".", "..") or ":" in p for p in name.split("/")):
        raise ValueError("unsafe or ambiguous SZS member name")
    raw = name.replace("/", ";").encode("cp932")
    if len(raw) > 255:
        raise ValueError("SZS encoded name too long")
    return raw


def pack_szs(members, *, version, seed, mode):
    members = list(members)
    if not 0 < len(members) <= 100_000 or not 0 <= version <= 0xFFFFFFFF:
        raise ValueError("invalid SZS count/version")
    out = bytearray(b"SZS100__" + struct.pack("<II", version, len(members)) + bytes(272 * len(members)))
    seen = set()
    for i, (name, raw) in enumerate(members):
        encoded_name = _name(name)
        if name in seen:
            raise ValueError("duplicate SZS name")
        seen.add(name)
        pos = 16 + i * 272
        out[pos:pos + len(encoded_name)] = encoded_name
        encrypted = crypt_member(raw, seed=seed, mode=mode, decrypt=False)
        struct.pack_into("<QQ", out, pos + 256, len(out), len(encrypted))
        out.extend(encrypted)
    return bytes(out)


def unpack_szs(data, *, seed, mode, max_output=64 * 1024 * 1024):
    if len(data) < 16 or data[:8] != b"SZS100__":
        raise ValueError("not SZS100__")
    version, count = struct.unpack_from("<II", data, 8)
    if not 0 < count <= 100_000 or 16 + count * 272 > len(data):
        raise ValueError("invalid SZS index")
    result, cursor, used, seen = [], 16 + count * 272, 0, set()
    for i in range(count):
        pos = 16 + 272 * i
        field = data[pos:pos + 256]
        if b"\x00" not in field:
            raise ValueError("unterminated SZS name")
        name = field.split(b"\x00", 1)[0].decode("cp932").replace(";", "/")
        _name(name)
        offset, size = struct.unpack_from("<QQ", data, pos + 256)
        if name in seen or offset < cursor or size > len(data) - offset or size > max_output - used:
            raise ValueError("invalid SZS placement or output budget")
        seen.add(name)
        result.append((name, crypt_member(data[offset:offset + size], seed=seed, mode=mode, decrypt=True)))
        cursor, used = offset + size, used + size
    return version, result
