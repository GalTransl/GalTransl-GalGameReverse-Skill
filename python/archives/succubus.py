# SPDX-License-Identifier: GPL-3.0-only
# Adapted from SExtractor tools/Succubus/VFA包处理工具/{extract,repack}.py
# Source commit: 8d8d976fd04ae54e7c677705af937273d04a376a
# Upstream attribution: 这位同学; SExtractor contributors.
"""Succubus VFA1 RIFF variant; source dialect has no generic RIFF word padding."""
import struct


def _chunk(tag, payload):
    return tag + struct.pack("<I", len(payload)) + payload


def parse_vfa(data):
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"VFA1":
        raise ValueError("not RIFF/VFA1")
    if struct.unpack_from("<I", data, 4)[0] != len(data) - 8:
        raise ValueError("VFA RIFF length mismatch")
    pos, chunks = 12, []
    for expected in (b"hdri", b"data", b"dent"):
        if pos + 8 > len(data) or data[pos:pos + 4] != expected:
            raise ValueError("unsupported VFA chunk sequence")
        size = struct.unpack_from("<I", data, pos + 4)[0]
        pos += 8
        if size > len(data) - pos:
            raise ValueError("truncated VFA chunk")
        chunks.append(data[pos:pos + size])
        pos += size
    if pos != len(data) or len(chunks[0]) != 16 or chunks[0][8:] != b"dentdata":
        raise ValueError("unsupported VFA header/tail")
    header, body, index = chunks
    entries, pos, cursor = [], 0, 0
    while pos < len(index):
        if len(entries) >= 100_000 or pos + 8 > len(index):
            raise ValueError("invalid VFA entry count/boundary")
        tag = index[pos:pos + 4]
        size = struct.unpack_from("<I", index, pos + 4)[0]
        pos += 8
        if size > len(index) - pos or size % 2:
            raise ValueError("invalid VFA entry size")
        payload = index[pos:pos + size]
        pos += size
        nul = next((i for i in range(0, len(payload) - 1, 2) if payload[i:i + 2] == b"\x00\x00"), -1)
        if nul < 0:
            raise ValueError("unterminated UTF-16 VFA name")
        name = payload[:nul].decode("utf-16le")
        if tag == b"dir " and nul + 2 == len(payload):
            entries.append({"type": "dir", "name": name})
        elif tag == b"file" and nul + 18 == len(payload):
            offset, size, stamp, flags = struct.unpack_from("<4I", payload, nul + 2)
            if offset != cursor or size > len(body) - offset:
                raise ValueError("noncontiguous or out-of-bounds VFA file")
            entries.append({"type": "file", "name": name, "data": body[offset:offset + size],
                            "stamp": stamp, "flags": flags})
            cursor += size
        else:
            raise ValueError("unsupported VFA directory-entry type")
    if cursor != len(body):
        raise ValueError("unindexed VFA data tail")
    return {"header": header, "entries": entries}


def build_vfa(entries, *, header):
    """Preserve directory events, timestamps and flags; rebuild all chunk sizes/offsets."""
    if len(header) != 16 or header[8:] != b"dentdata":
        raise ValueError("unsupported VFA header")
    body, index = bytearray(), bytearray()
    for i, entry in enumerate(entries):
        if i >= 100_000 or "\x00" in entry["name"]:
            raise ValueError("VFA count/name limit")
        name = entry["name"].encode("utf-16le") + b"\x00\x00"
        if entry["type"] == "dir":
            index.extend(_chunk(b"dir ", name))
        elif entry["type"] == "file":
            raw = entry["data"]
            meta = struct.pack("<4I", len(body), len(raw), entry["stamp"], entry["flags"])
            index.extend(_chunk(b"file", name + meta))
            body.extend(raw)
        else:
            raise ValueError("unknown VFA event")
    content = b"VFA1" + _chunk(b"hdri", header) + _chunk(b"data", body) + _chunk(b"dent", index)
    return b"RIFF" + struct.pack("<I", len(content)) + content
