# SPDX-License-Identifier: GPL-3.0-only
# Adapted from SExtractor tools/U-GOS/o_tool.py
# Source commit: 8d8d976fd04ae54e7c677705af937273d04a376a
# Upstream attribution: 朝比奈真冬 (batch additions); SExtractor contributors.
"""U-GOS .o pointer/string blocks. A independently established code_end is mandatory."""
import struct
import re

_WIDTHS = {0: 0, 1: 0, 3: 0, 7: 0, 8: 0, 192: 0, 193: 0, 194: 0, 195: 0,
           208: 0, 209: 0, 210: 0, 211: 0, 212: 0,
           2: 4, 5: 4, 6: 4, 16: 2, 19: 2, 23: 2, 18: 2, 21: 2, 22: 2,
           32: 1, 35: 1, 39: 1, 34: 1, 37: 1, 38: 1}
_CONTROL = frozenset((0, 7, 8, 9, 10))


def parse_references(data, *, code_end):
    if not 0 < code_end <= len(data) or len(data) > 64 * 1024 * 1024:
        raise ValueError("invalid independently verified code boundary")
    refs, pos = [], 0
    while pos < code_end:
        op = data[pos]
        pos += 1
        if op not in _WIDTHS or pos + _WIDTHS[op] > code_end:
            raise ValueError("unknown/truncated U-GOS instruction")
        width = _WIDTHS[op]
        if op in (2, 18, 34):
            target = int.from_bytes(data[pos:pos + width], "little")
            if target < code_end or target + 2 > len(data):
                raise ValueError("string pointer not in bounded data section")
            size = struct.unpack_from("<H", data, target)[0]
            if not size or target + 2 + size > len(data):
                raise ValueError("invalid U-GOS string block")
            refs.append({"field": pos, "width": width, "target": target,
                         "raw": data[target + 2:target + 2 + size]})
        pos += width
    return refs


def _text_parts(raw):
    a, b = 0, len(raw)
    while a < b and raw[a] in _CONTROL:
        a += 1
    while b > a and raw[b - 1] in _CONTROL:
        b -= 1
    if any(c in _CONTROL for c in raw[a:b]):
        raise ValueError("interior controls need a richer text segmentation model")
    return raw[:a], raw[a:b], raw[b:]


def extract_o(data, *, code_end, encoding="cp932"):
    """Return pointer-backed candidates, not proof of a complete VM semantic analysis."""
    entries, seen = [], set()
    for ref in parse_references(data, code_end=code_end):
        if ref["target"] in seen:
            continue
        seen.add(ref["target"])
        _, text, _ = _text_parts(ref["raw"])
        text = text.decode(encoding)
        if (not text or re.match(r"^(●|//|'|!|◎|○|sys_|[a-z]+\\)", text)
                or any(ext in text for ext in (".dat", ".bmp", ".png", ".ogg", ".wav", ".txt"))
                or not any(ord(c) > 126 for c in text)):
            continue
        name, message = "", text
        if "「" in text:
            name, message = text.split("「", 1)
            name, message = name.replace("　", "").strip(), "「" + message
        entries.append({"target": ref["target"], "name": name, "message": message,
                        "text": text, "status": "candidate"})
    return entries


def rewrite_o(data, replacements, *, code_end, encoding="cp932"):
    """Map reviewed candidate block offsets -> complete text (name included).

    Changed blocks append at EOF; ALL known aliases are repointed. Width overflow
    fails before returning bytes; original pool and code layout remain untouched.
    """
    refs = parse_references(data, code_end=code_end)
    allowed = {e["target"] for e in extract_o(data, code_end=code_end, encoding=encoding)}
    if set(replacements) - allowed:
        raise ValueError("replacement target was not an extracted candidate")
    unique = {r["target"]: r for r in refs}
    out, remap = bytearray(data), {}
    for target, text in replacements.items():
        prefix, old, suffix = _text_parts(unique[target]["raw"])
        raw = text.encode(encoding)
        if not raw or any(b in _CONTROL for b in raw):
            raise ValueError("replacement introduces a U-GOS control byte")
        if raw == old:
            continue
        block = prefix + raw + suffix
        if len(block) > 65535:
            raise ValueError("U-GOS block length overflow")
        remap[target] = len(out)
        out.extend(struct.pack("<H", len(block)) + block)
    for ref in refs:
        if ref["target"] in remap:
            offset = remap[ref["target"]]
            if offset >= 1 << (8 * ref["width"]):
                raise ValueError("U-GOS pointer width overflow")
            out[ref["field"]:ref["field"] + ref["width"]] = offset.to_bytes(ref["width"], "little")
    return bytes(out)
