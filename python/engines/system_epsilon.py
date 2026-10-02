# SPDX-License-Identifier: GPL-3.0-only
# Adapted from SExtractor src/reg.yaml:_BIN_SYSTEM-ε and src/extract_BIN.py
# Source commit: 8d8d976fd04ae54e7c677705af937273d04a376a
# Upstream attribution: satan53x / SExtractor contributors.
"""SYSTEM-epsilon isolated preset segments and candidate pointer patterns."""
import re

_PRIMARY = re.compile(rb"\x1d\x08[^\x00][\s\S]([\s\S]{3}\x00)|\x30\x08\x00\x00([\s\S]{3}\x00)[^\x00]|\x2e\x0c[\s\S]{6}([\s\S]{3}\x00)|\x2f\x08\x00\x00([\s\S]{3}\x00)\x1c")
_SECONDARY = re.compile(rb"(?<!\x0c\x08\x00\x00)\x0d\x08[\s\S]{2}([\s\S]{3}\x00)|\x00\x00([\s\S]{3}\x00)\x24\x08")


def parse_segment(segment, *, encoding="cp932"):
    """After 00 04 00 separator; exactly length byte + optional 8194 + text + NUL."""
    if len(segment) < 3 or not segment[0] or segment[-1] != 0:
        raise ValueError("invalid SYSTEM-epsilon text segment")
    begin = 3 if segment[1:3] == b"\x81\x94" else 1
    raw = segment[begin:-1]
    if not raw or b"\x00" in raw:
        raise ValueError("empty or unterminated SYSTEM-epsilon field")
    return {"role": "name" if begin == 3 else "message", "text": raw.decode(encoding), "begin": begin}


def rewrite_segment(segment, text, *, encoding="cp932"):
    """Update the original length byte by encoded-byte delta; do not infer its base.

    Returns an isolated segment only. Known pointer-pattern matches alone do not
    prove that every enclosing VM address has been found, so no whole-file writer.
    """
    item = parse_segment(segment, encoding=encoding)
    raw = text.encode(encoding)
    old = segment[item["begin"]:-1]
    if bytes(b for b in old if b < 32) != bytes(b for b in raw if b < 32):
        raise ValueError("SYSTEM-epsilon control-byte sequence changed")
    length = segment[0] + len(raw) - len(old)
    if not 1 <= length <= 255:
        raise ValueError("SYSTEM-epsilon one-byte length overflow")
    result = bytes([length]) + segment[1:item["begin"]] + raw + b"\x00"
    parsed = parse_segment(result, encoding=encoding)
    if parsed["role"] != item["role"]:
        raise ValueError("message prefix would become a name marker")
    return result


def pointer_candidates(data, *, include_secondary=False):
    """Return preset-pattern (field offset, stored u32) evidence, not verified jumps."""
    if len(data) > 64 * 1024 * 1024:
        raise ValueError("SYSTEM-epsilon scan budget exceeded")
    fields = {}
    for pattern in (_PRIMARY, _SECONDARY) if include_secondary else (_PRIMARY,):
        for match in pattern.finditer(data):
            for group in range(1, len(match.groups()) + 1):
                if match[group] is not None:
                    field = match.start(group)
                    fields[field] = int.from_bytes(match[group], "little")
    return sorted(fields.items())
