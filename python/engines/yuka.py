# SPDX-License-Identifier: GPL-3.0-only
# Adapted from SExtractor tools/Yuka/yks_text_v2.py
# Source commit: 8d8d976fd04ae54e7c677705af937273d04a376a
# Upstream attribution: 瑜瑜 & Steins;Gate; SExtractor contributors.
"""YKS002 typed UTF-8 pool, verified GraphicTextOut/Select.Text routes only."""
import re
import struct

_SCHEMA = {1: ("T", "I"), 2: ("T", "-"), 3: ("T", "I"), 4: ("T", "I"),
           5: ("-", "B"), 6: ("-", "B"), 7: ("-", "T"), 8: ("T", "I"),
           9: ("-", "L"), 10: ("T", "-"), 11: ("T", "-")}
_NULL = 0xFFFFFFFF
_CONTROL = re.compile(r"@[a-zA-Z][+\-]?\([^)]*\)")


def parse_yks(data):
    if len(data) < 48 or len(data) > 64 * 1024 * 1024 or data[:8] != b"YKS002\x00\x00":
        raise ValueError("only YKS002 is supported")
    h = struct.unpack_from("<10I", data, 8)
    hdr, a, an, b, bn, c, cn, d, dn, flags = h
    if (hdr != 48 or a != 48 or b != a + an or c != b + bn or d != c + cn
            or d + dn != len(data) or an % 4 or bn % 4 or cn % 12
            or an // 4 > 100_000 or bn // 4 > 100_000 or cn // 12 > 100_000):
        raise ValueError("noncanonical/truncated YKS002 sections")
    nodes = [tuple(struct.unpack_from("<3I", data, c + i * 12)) for i in range(cn // 12)]
    operands = list(struct.unpack_from("<%dI" % (bn // 4), data, b))
    obj = {"nodes": nodes, "operands": operands, "pool": data[d:d + dn],
           "node_base": c, "pool_base": d, "flags": flags}
    for typ, f1, f2 in nodes:
        if typ not in _SCHEMA:
            raise ValueError("unknown YKS002 node type")
        for kind, value in zip(_SCHEMA[typ], (f1, f2)):
            if value == _NULL:
                continue
            if kind == "T":
                _string(obj, value)
            elif kind == "B" and value + 8 > dn:
                raise ValueError("YKS002 binary pool reference outside bounds")
    return obj


def _string(obj, offset):
    pool = obj["pool"]
    end = pool.find(b"\x00", offset)
    if offset >= len(pool) or end < 0:
        raise ValueError("invalid YKS002 UTF-8 pool reference")
    return pool[offset:end].decode("utf-8")


def _roles(obj):
    nodes, roles = obj["nodes"], {}
    for i, (typ, _, offset) in enumerate(nodes):
        if typ != 7 or offset == _NULL:
            continue
        for j in range(i + 1, min(i + 4, len(nodes))):
            nt, nf1, _ = nodes[j]
            if nt == 11 and nf1 != _NULL:
                if _string(obj, nf1).startswith("Select.Text"):
                    roles[i] = "choice"
                break
            if nt in (7, 3, 4):
                break
        if i in roles or i + 1 >= len(nodes):
            continue
        nt, nf1, _ = nodes[i + 1]
        if nt != 1 or nf1 == _NULL or _string(obj, nf1) != "GraphicTextOut":
            continue
        for j in range(i - 1, max(i - 4, -1), -1):
            pt, _, p2 = nodes[j]
            if pt == 7:
                break
            if pt != 8 or p2 == _NULL:
                continue
            if p2 >= len(obj["operands"]):
                raise ValueError("YKS002 PARAM operand-chain offset out of range")
            integers, terminated = [], False
            for chain_pos in range(p2, min(p2 + 1024, len(obj["operands"]))):
                value = obj["operands"][chain_pos]
                if value == _NULL:
                    terminated = True
                    break
                if value >= len(nodes):
                    raise ValueError("YKS002 PARAM references an invalid node")
                st, _, sf2 = nodes[value]
                if st == 5 and sf2 != _NULL:
                    integers.append(struct.unpack_from("<I", obj["pool"], sf2)[0])
            if not terminated:
                raise ValueError("unterminated YKS002 operand chain")
            if len(integers) >= 2:
                roles[i] = "name" if integers[1] == 1 else "message"
            break
    return roles


def extract_yks(data):
    """Return only semantically linked nodes; no 'any long/non-ASCII string' fallback."""
    obj = parse_yks(data)
    roles, entries = _roles(obj), []
    for i, role in roles.items():
        if role == "name":
            continue
        message = _string(obj, obj["nodes"][i][2])
        if not _CONTROL.sub("", message).strip():
            continue
        name, name_id = "", None
        if role == "message":
            for j in range(i - 1, max(i - 20, -1), -1):
                typ, f1, f2 = obj["nodes"][j]
                if typ == 1 and f1 != _NULL and _string(obj, f1) == "KeyWait":
                    break
                if roles.get(j) == "name":
                    name, name_id = _string(obj, f2), j
                    break
        entries.append({"id": i, "kind": role, "name": name, "name_id": name_id, "message": message})
    return entries


def rewrite_yks(data, replacements):
    """Map extracted S3 message/name IDs -> text; rebuild typed pool, fix T/B offsets.

    S1/S2 index values and 8-byte binary INT/FLOAT data are preserved, not mistaken
    for string offsets. Interior/suffix overlap and ambiguous shared roles fail.
    """
    obj = parse_yks(data)
    entries = extract_yks(data)
    allowed = {e["id"] for e in entries} | {e["name_id"] for e in entries if e["name_id"] is not None}
    if set(replacements) - allowed:
        raise ValueError("YKS002 replacement is not a verified message/name node")
    changes = {}
    for node_id, text in replacements.items():
        offset = obj["nodes"][node_id][2]
        old = _string(obj, offset)
        if "\x00" in text or _CONTROL.findall(old) != _CONTROL.findall(text):
            raise ValueError("YKS002 control-code sequence changed")
        raw = text.encode("utf-8")
        if offset in changes and changes[offset] != raw:
            raise ValueError("conflicting YKS002 shared-string translations")
        changes[offset] = raw
    refs = {}
    for node_id, (typ, f1, f2) in enumerate(obj["nodes"]):
        for field, (kind, offset) in enumerate(zip(_SCHEMA[typ], (f1, f2))):
            if kind not in ("T", "B") or offset == _NULL:
                continue
            if offset in refs and refs[offset] != kind:
                raise ValueError("YKS002 pool offset aliases binary and text")
            if offset in changes and (typ != 7 or field != 1 or node_id not in allowed):
                raise ValueError("translated pool string also has an unreviewed/non-dialogue role")
            refs[offset] = kind
    pool, remap, cursor = bytearray(), {}, 0
    for offset, kind in sorted(refs.items()):
        if offset < cursor:
            raise ValueError("overlapping YKS002 pool objects")
        pool.extend(obj["pool"][cursor:offset])
        remap[offset] = len(pool)
        end = offset + 8 if kind == "B" else obj["pool"].index(0, offset) + 1
        pool.extend(changes[offset] + b"\x00" if offset in changes else obj["pool"][offset:end])
        cursor = end
    pool.extend(obj["pool"][cursor:])
    out = bytearray(data[:obj["pool_base"]])
    for i, (typ, f1, f2) in enumerate(obj["nodes"]):
        for field, (kind, offset) in enumerate(zip(_SCHEMA[typ], (f1, f2))):
            if kind in ("T", "B") and offset != _NULL:
                struct.pack_into("<I", out, obj["node_base"] + 12 * i + 4 + field * 4, remap[offset])
    struct.pack_into("<I", out, 40, len(pool))
    out.extend(pool)
    parse_yks(out)
    return bytes(out)
