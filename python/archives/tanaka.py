# SPDX-License-Identifier: GPL-3.0-only
# Adapted from SExtractor tools/Tanaka/SCB1_{unpack,pack}.py; src/reg.yaml:_BIN_Tanaka
# Source commit: 8d8d976fd04ae54e7c677705af937273d04a376a
# Upstream attribution: satan53x / SExtractor contributors.
"""Tanaka SCB1 template repacking and bounded, already-isolated text records."""
# Layer split: archives; format algorithms and original notices retained.
# Companion module: python/engines/tanaka.py
import struct


def parse_scb1(data):
    if len(data) < 32:
        raise ValueError("SCB1 template too short")
    pos = struct.unpack_from("<I", data, 0x1C)[0]
    if not 32 <= pos <= len(data) - 4:
        raise ValueError("invalid SCB1 index pointer")
    items = []
    while True:
        if pos + 4 > len(data) or len(items) >= 100_000:
            raise ValueError("unterminated SCB1 index")
        field = pos
        offset = struct.unpack_from("<I", data, pos)[0]
        pos += 4
        if not offset:
            break
        if pos >= len(data):
            raise ValueError("missing SCB1 name length")
        size = data[pos] - 1
        pos += 1
        if size < 1 or size > len(data) - pos:
            raise ValueError("invalid SCB1 name length")
        name = data[pos:pos + size].rstrip(b"\x00").decode("cp932")
        if not name or "\x00" in name:
            raise ValueError("invalid SCB1 name")
        pos += size
        items.append({"name": name, "offset": offset, "field": field})
    if not items or len({i["name"] for i in items}) != len(items):
        raise ValueError("empty/duplicate SCB1 index")
    offsets = [i["offset"] for i in items] + [len(data)]
    if offsets[0] < pos or any(a > b for a, b in zip(offsets, offsets[1:])):
        raise ValueError("out-of-order SCB1 members")
    for i, end in zip(items, offsets[1:]):
        if end > len(data):
            raise ValueError("SCB1 offset past EOF")
        i["data"] = data[i["offset"]:end]
    return items


def repack_scb1(data, replacements):
    """Map exact member name -> bytes; retain old header/index layout, fix offsets."""
    items = parse_scb1(data)
    if set(replacements) - {i["name"] for i in items}:
        raise ValueError("unknown SCB1 member")
    out = bytearray(data[:items[0]["offset"]])
    for item in items:
        struct.pack_into("<I", out, item["field"], len(out))
        out.extend(replacements.get(item["name"], item["data"]))
    return bytes(out)
