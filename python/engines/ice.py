# Provenance group: tools-a; sources (repository-relative):
#   SExtractor/tools/ICE/ice_op.py
# Symbols: Charset.encode_idx, tokenize, seg_to_str, str_to_bytes
# Validation: tests/test_engines_tools_a.py, synthetic fixtures only.
# Rewritten standard-library bytes API; scope: message-token-codec.
# SPDX-License-Identifier: GPL-3.0-only
# SExtractor tools/ICE/ice_op.py: Charset.encode_idx, tokenize; commit
# 8d8d976fd04ae54e7c677705af937273d04a376a. Rewrite: baseline 0xF7 threshold,
# typed tokens preserve controls; no EXE patch/expanded charset or filesystem IO.
"""ICE baseline message token stream. Character IDs require caller's charset."""


def encode_index(index: int) -> bytes:
    if 0 <= index < 0xE7 or index == 0xE9:
        return bytes((index,))
    if 256 <= index <= 2559:
        return bytes((256 - (index >> 8), index & 255))
    raise ValueError("character index unavailable without a different VM/patch")


def tokenize(data: bytes) -> list[tuple]:
    pos, out = 0, []
    while pos < len(data):
        b = data[pos]
        pos += 1
        if b == 0xEC:
            if pos != len(data):
                raise ValueError("trailing bytes after text terminator")
            return out + [("end",)]
        if b in (0xEA, 0xEB) or b >= 0xF7:
            if pos == len(data):
                raise ValueError("truncated two-byte token")
            value = data[pos]
            pos += 1
            out.append(("break", b, value) if b < 0xF7 else ("char", value + ((256 - b) << 8)))
        elif b == 0xED and pos < len(data) and data[pos] == 0xED:
            pos += 1
            out.append(("reset",))
        elif 0xED <= b <= 0xF6:
            out.append(("color", b))
        elif b in (0xE7, 0xE8):
            out.append(("insert", b))
        else:
            out.append(("char", b))
    raise ValueError("missing ICE EC terminator")


def encode_tokens(tokens: list[tuple]) -> bytes:
    out = bytearray()
    for token in tokens:
        kind = token[0]
        if kind == "char":
            out += encode_index(token[1])
        elif kind == "break" and token[1] in (0xEA, 0xEB):
            out += bytes(token[1:])
        elif kind == "color" and 0xED <= token[1] <= 0xF6:
            out.append(token[1])
        elif kind == "insert" and token[1] in (0xE7, 0xE8):
            out.append(token[1])
        elif token == ("reset",):
            out += b"\xED\xED"
        elif token == ("end",):
            out.append(0xEC)
        else:
            raise ValueError("invalid token")
    raw = bytes(out)
    if tokenize(raw) != tokens:
        raise ValueError("ambiguous/unterminated token sequence")
    return raw
