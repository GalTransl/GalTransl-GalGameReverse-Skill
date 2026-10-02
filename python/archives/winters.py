# SPDX-License-Identifier: GPL-3.0-only
# Adapted from SExtractor tools/Winters/ifp_pack.py and bytes_pad.py
# Source commit: 8d8d976fd04ae54e7c677705af937273d04a376a
# Upstream attribution: Steins;Gate; SExtractor contributors.
"""Winters IFP unmasked-member container subset; ISD text semantics are external."""
# Layer split: archives; format algorithms and original notices retained.
# Companion module: python/engines/winters.py
import struct


def pack_ifp(members):
    """Ordered (type_u16, bytes) members; explicit types, no guessed name sorting."""
    members = list(members)
    if not members or 0x660 + len(members) * 16 > 0x8010:
        raise ValueError("IFP fixed index region cannot hold these members")
    out = bytearray(0x8010)
    out[:16] = b"IAGS_IFP_01     "
    struct.pack_into("<4I", out, 0x10, 1, 0x10, 0x8000, 0)
    for i, (kind, raw) in enumerate(members):
        if not 1 <= kind <= 0xFFFF:
            raise ValueError("zero type is reserved for IFP end marker")
        pos = 0x20 if i == 0 else 0x660 + (i - 1) * 16
        struct.pack_into("<HHIII", out, pos, kind, 0, len(out), len(raw), 0)
        out.extend(raw)
    return bytes(out)


def unpack_ifp(data, *, max_output=64 * 1024 * 1024):
    if len(data) < 0x8010 or data[:16] != b"IAGS_IFP_01     ":
        raise ValueError("not the supported IFP layout")
    if struct.unpack_from("<4I", data, 0x10) != (1, 0x10, 0x8000, 0):
        raise ValueError("unsupported IFP header version")
    entries, cursor, pos, used = [], 0x8010, 0x20, 0
    while True:
        if pos + 16 > 0x8010:
            raise ValueError("unterminated IFP index")
        kind, mask_kind, offset, size, mask_size = struct.unpack_from("<HHIII", data, pos)
        if not kind:
            if (mask_kind, offset, size, mask_size) != (0, 0, 0, 0):
                raise ValueError("invalid IFP end marker")
            break
        if mask_kind or mask_size or offset != cursor or size > len(data) - offset or size > max_output - used:
            raise ValueError("unsupported masked/noncontiguous IFP member")
        entries.append((kind, data[offset:offset + size]))
        cursor, used = offset + size, used + size
        pos = 0x660 if pos == 0x20 else pos + 16
    if not entries or cursor != len(data):
        raise ValueError("invalid IFP data tail")
    return entries
