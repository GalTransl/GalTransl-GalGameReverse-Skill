# SPDX-License-Identifier: GPL-3.0-only
# Adapted from SExtractor tools/PureMail/obj_processor.py and obj_processor_v2.py
# Source commit: 8d8d976fd04ae54e7c677705af937273d04a376a
# Upstream attribution: Steins;Gate; SExtractor contributors.
"""PureMail contiguous OBJ string tables, explicit V1/V2; not DAT archives."""
import struct


def parse_obj(data, *, version):
    if version not in (1, 2):
        raise ValueError("OBJ version must be 1 or 2, independent of DAT version")
    fmt = "<HH" if version == 1 else "<IH"
    stride = struct.calcsize(fmt)
    if len(data) < stride * 2:
        raise ValueError("truncated OBJ index")
    tail_offset, tail_length = struct.unpack_from(fmt, data)
    first, _ = struct.unpack_from(fmt, data, stride)
    if first % stride or not stride * 2 <= first <= tail_offset <= len(data):
        raise ValueError("invalid OBJ section boundaries")
    count = first // stride
    strings, cursor = [], first
    for i in range(1, count):
        offset, size = struct.unpack_from(fmt, data, i * stride)
        if offset != cursor or offset + size > tail_offset:
            raise ValueError("only contiguous, nonaliased OBJ pools are supported")
        strings.append(data[offset:offset + size])
        cursor += size
    if cursor != tail_offset or tail_length > len(data) - tail_offset:
        raise ValueError("invalid opaque tail")
    return {"strings": strings, "tail": data[tail_offset:], "tail_length": tail_length}


def extract_obj(data, *, version, encoding="cp932"):
    """Indexed strings, not automatically dialogue; NUL/control characters retained."""
    obj = parse_obj(data, version=version)
    return [{"index": i + 1, "text": raw.decode(encoding), "role": "unclassified"}
            for i, raw in enumerate(obj["strings"])]


def rewrite_obj(data, replacements, *, version, encoding="cp932"):
    """Map 1-based string index to text; rebuild address/length table and tail pointer."""
    obj = parse_obj(data, version=version)
    strings = obj["strings"]
    if any(type(i) is not int or not 1 <= i <= len(strings) for i in replacements):
        raise ValueError("unknown OBJ string index")
    for i, text in replacements.items():
        raw = text.encode(encoding)
        old = strings[i - 1]
        if bytes(b for b in raw if b < 32) != bytes(b for b in old if b < 32):
            raise ValueError("OBJ control-byte sequence changed")
        strings[i - 1] = raw
    fmt = "<HH" if version == 1 else "<IH"
    stride = struct.calcsize(fmt)
    cursor = (len(strings) + 1) * stride
    limit = 0xFFFF if version == 1 else 0xFFFFFFFF
    entries = []
    for raw in strings:
        if cursor > limit or len(raw) > 0xFFFF:
            raise ValueError("OBJ address or string length overflow")
        entries.append(struct.pack(fmt, cursor, len(raw)))
        cursor += len(raw)
    if cursor > limit:
        raise ValueError("OBJ tail address overflow")
    return (struct.pack(fmt, cursor, obj["tail_length"]) + b"".join(entries)
            + b"".join(strings) + obj["tail"])
