# SPDX-License-Identifier: GPL-3.0-only
# Adapted from SExtractor tools/Unison/lazy_common.py and val_extract.py
# Source commit: 8d8d976fd04ae54e7c677705af937273d04a376a
# Upstream attribution: Steins;Gate; SExtractor contributors.
"""Unison/Softpal Lazy VAL pool relocation; reviewed DISPLAY_TEXT sites required."""
import struct


def parse_val(data):
    if len(data) < 9:
        raise ValueError("truncated VAL u24 header")
    code_size = int.from_bytes(data[:3], "little")
    count = int.from_bytes(data[3:6], "little")
    base = 9 + code_size + count * 4
    if count > 100_000 or base > len(data):
        raise ValueError("invalid VAL code/index size")
    code = data[9:9 + code_size]
    offsets = list(struct.unpack_from("<%dI" % count, data, 9 + code_size))
    pool = data[base:]
    strings = []
    for offset in offsets:
        end = pool.find(b"\x00", offset)
        if offset >= len(pool) or end < 0:
            raise ValueError("invalid VAL pool offset/terminator")
        strings.append(pool[offset:end])
    return {"code": code, "extra": data[6:9], "offsets": offsets, "pool": pool, "strings": strings}


def extract_val(data, *, sites, encoding="cp932"):
    """Only caller-reviewed instruction starts with dd 00 00 00 [u16 index]."""
    obj, out, seen = parse_val(data), [], set()
    for site in sites:
        code = obj["code"]
        if type(site) is not int or site < 0 or site + 6 > len(code) or code[site:site + 4] != b"\xDD\x00\x00\x00":
            raise ValueError("not a reviewed DISPLAY_TEXT type-zero instruction")
        index = struct.unpack_from("<H", code, site + 4)[0]
        if index >= len(obj["strings"]):
            raise ValueError("DISPLAY_TEXT references nonexistent string")
        if index not in seen:
            seen.add(index)
            out.append({"site": site, "index": index, "name": "", "message": obj["strings"][index].decode(encoding)})
    return out


def rewrite_val(data, replacements, *, sites, encoding="cp932"):
    """Map reviewed string indices -> message. seg_A and extra u24 remain byte-exact."""
    obj = parse_val(data)
    allowed = {e["index"] for e in extract_val(data, sites=sites, encoding=encoding)}
    if set(replacements) - allowed:
        raise ValueError("replacement does not have a reviewed text reference")
    changes = {}
    for index, text in replacements.items():
        raw = text.encode(encoding)
        if b"\x00" in raw:
            raise ValueError("VAL string contains embedded NUL")
        old = obj["strings"][index]
        if bytes(b for b in raw if b < 32) != bytes(b for b in old if b < 32):
            raise ValueError("VAL control-byte sequence changed")
        offset = obj["offsets"][index]
        if offset in changes and changes[offset] != raw:
            raise ValueError("conflicting translations for aliased VAL strings")
        changes[offset] = raw
    for index, offset in enumerate(obj["offsets"]):
        if offset in changes and changes[offset] != obj["strings"][index] and index not in allowed:
            raise ValueError("translated VAL object also has an unreviewed alias index")
    out, cursor, remap = bytearray(), 0, {}
    for offset in sorted(set(obj["offsets"])):
        if offset < cursor:
            raise ValueError("suffix-overlapping VAL strings require a different writer")
        end = obj["pool"].index(0, offset)
        out.extend(obj["pool"][cursor:offset])
        remap[offset] = len(out)
        out.extend(changes.get(offset, obj["pool"][offset:end]) + b"\x00")
        cursor = end + 1
    out.extend(obj["pool"][cursor:])
    index = b"".join(struct.pack("<I", remap[o]) for o in obj["offsets"])
    header = len(obj["code"]).to_bytes(3, "little") + len(obj["offsets"]).to_bytes(3, "little") + obj["extra"]
    return header + obj["code"] + index + bytes(out)
