# SPDX-License-Identifier: GPL-3.0-only
# Adapted from SExtractor tools/StudioMiris/skm_to_txt.py and txt_to_skm.py
# Source commit: 8d8d976fd04ae54e7c677705af937273d04a376a
# Upstream attribution: Coroz; SExtractor contributors.
"""SKMSd string table; explicit pool-offset override replaces upstream game constant."""
import struct


def parse_skm(data, *, pool_offset=None):
    if len(data) < 10 or data[:6] != b"SKMSd\x00":
        raise ValueError("not SKMSd")
    count = struct.unpack_from("<I", data, 6)[0]
    end = 10 + count * 8
    base = end if pool_offset is None else pool_offset
    if count > 100_000 or not end <= base <= len(data):
        raise ValueError("invalid SKM index/pool boundary")
    result, cursor = [], 0
    for i in range(count):
        offset, size = struct.unpack_from("<II", data, 10 + i * 8)
        if offset != cursor or size > len(data) - base - offset:
            raise ValueError("only contiguous SKM string tables supported")
        result.append(bytes(b ^ 255 for b in data[base + offset:base + offset + size]))
        cursor += size
    return {"strings": result, "gap": data[end:base], "tail": data[base + cursor:]}


def extract_skm(data, *, pool_offset=None, encoding="cp932"):
    """Return indexed strings; caller must review name/message role separately."""
    return [{"index": i, "text": raw.decode(encoding), "role": "unclassified"}
            for i, raw in enumerate(parse_skm(data, pool_offset=pool_offset)["strings"])]


def rewrite_skm(data, replacements, *, pool_offset=None, encoding="cp932"):
    obj = parse_skm(data, pool_offset=pool_offset)
    strings = obj["strings"]
    if any(type(i) is not int or not 0 <= i < len(strings) for i in replacements):
        raise ValueError("unknown SKM string index")
    for i, text in replacements.items():
        raw = text.encode(encoding)
        if bytes(b for b in raw if b < 32) != bytes(b for b in strings[i] if b < 32):
            raise ValueError("SKM control-byte sequence changed")
        strings[i] = raw
    index, body = bytearray(), bytearray()
    for raw in strings:
        index.extend(struct.pack("<II", len(body), len(raw)))
        body.extend(b ^ 255 for b in raw)
    return (b"SKMSd\x00" + struct.pack("<I", len(strings)) + index + obj["gap"]
            + body + obj["tail"])
