# Provenance group: tools-a; sources (repository-relative):
#   SExtractor/tools/Masys/meg_crypt.py
# Symbols: walk_and_crypt, xor_buf, EXPR_ATOM, EXPR_OPS
# Validation: tests/test_engines_tools_a.py, synthetic fixtures only.
# Rewritten standard-library bytes API; scope: expression-string-cipher.
# SPDX-License-Identifier: GPL-3.0-only
# SExtractor tools/Masys/meg_crypt.py: walk_and_crypt.walk_expr, xor_buf;
# commit 8d8d976fd04ae54e7c677705af937273d04a376a. Standalone expression parser.
# No opcodelist import/fallback or implicit title keys; see provenance/tools-a.json.
"""Masys expression atom 0x62 string XOR; caller supplies a delimited expression."""
import struct


def crypt_expression(data: bytes, key: bytes) -> bytes:
    """Transform string atoms only. Accept one complete nonempty expression."""
    if not key:
        raise ValueError("nonempty expression XOR key required")
    out, pos, first = bytearray(data), 0, True
    bare = {0x53, 0x54, 0x55, 0x57, 0x58, 0x59, 0x5A, 0x5B, 0x5C}
    operators = set(range(3, 12)) | set(range(13, 23))
    while pos < len(data):
        op = data[pos]
        pos += 1
        if op == 0:
            if first or pos != len(data):
                raise ValueError("empty expression or trailing bytes")
            return bytes(out)
        first = False
        if op == 0x62:
            if pos + 2 > len(data):
                raise ValueError("truncated STR length")
            n = struct.unpack_from("<H", data, pos)[0]
            pos += 2
            if pos + n > len(data):
                raise ValueError("truncated STR")
            for i in range(n):
                out[pos + i] ^= key[i % len(key)]
        elif op in (0x50, 0x51, 0x52):
            n = 2
        elif op in (0x60, 0x61):
            n = 4 if op == 0x60 else 10
        elif op in bare or op in operators:
            n = 0
        else:
            raise ValueError("unknown expression token")
        pos += n
        if pos > len(data):
            raise ValueError("truncated expression operand")
    raise ValueError("unterminated expression")
