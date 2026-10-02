# SPDX-License-Identifier: GPL-3.0-only
"""ANIM rolling-key codec, adapted from SExtractor extract_ANIM.py.

Pure byte transforms, not a container or script relocator. See provenance.
"""
from dataclasses import dataclass


def switch_key(key: bytes, last_plain: int) -> bytes:
    """Update the 16-byte key in source order (assignments are dependent)."""
    if len(key) != 16 or not 0 <= last_plain <= 255:
        raise ValueError("16-byte key and byte-valued plaintext required")
    k = bytearray(key)
    t = last_plain
    mode = t & 7
    if mode == 0:
        k[0] = (k[0] + t) & 255
        k[3] = (k[3] + t + 2) & 255
        k[4] = (k[2] + t + 11) & 255
        k[8] = (k[6] + 7) & 255
    elif mode == 1:
        for dst, a, b in ((2, 9, 10), (6, 7, 15), (8, 8, 1), (15, 5, 3)):
            k[dst] = (k[a] + k[b]) & 255
    elif mode == 2:
        for a, b in ((1, 2), (5, 6), (7, 8), (10, 11)):
            k[a] = (k[a] + k[b]) & 255
    elif mode == 3:
        for dst, a, b in ((9, 2, 1), (11, 6, 5), (12, 8, 7), (13, 11, 10)):
            k[dst] = (k[a] + k[b]) & 255
    elif mode == 4:
        for dst, src, add in ((0, 1, 111), (3, 4, 71), (4, 5, 17), (14, 15, 64)):
            k[dst] = (k[src] + add) & 255
    elif mode == 5:
        for dst, a, b in ((2, 2, 10), (4, 5, 12), (6, 8, 14), (8, 11, 0)):
            k[dst] = (k[a] + k[b]) & 255
    elif mode == 6:
        for dst, a, b in ((9, 11, 1), (11, 13, 3), (13, 15, 5), (15, 9, 7),
                          (1, 9, 5), (2, 10, 6), (3, 11, 7), (4, 12, 8)):
            k[dst] = (k[a] + k[b]) & 255
    else:
        for dst, a, b in ((1, 9, 5), (2, 10, 6), (3, 11, 7), (4, 12, 8)):
            k[dst] = (k[a] + k[b]) & 255
    return bytes(k)


def crypt(data: bytes, *, decrypt: bool) -> bytes:
    """Keep header [0, 0x14); XOR using last *plaintext* at each 16-byte boundary."""
    if len(data) < 0x14:
        raise ValueError("truncated ANIM header")
    out = bytearray(data)
    key = data[4:0x14]
    for i in range(0x14, len(data)):
        slot = (i - 0x14) % 16
        out[i] = data[i] ^ key[slot]
        if slot == 15:
            key = switch_key(key, out[i] if decrypt else data[i])
    return bytes(out)


def text_start(plain: bytes, *, sce: bool = False) -> int:
    """Offset is 0x14 for dat; sce stores relative start at 0x18."""
    if len(plain) < (0x1C if sce else 0x14):
        raise ValueError("truncated header")
    start = 0x14 + int.from_bytes(plain[0x18:0x1C], "little") if sce else 0x14
    if start < (0x1C if sce else 0x14) or start > len(plain):
        raise ValueError("text start outside file/header")
    return start


@dataclass(frozen=True)
class Token:
    start: int
    end: int
    raw: bytes


def nul_tokens(plain: bytes, *, sce: bool = False) -> tuple[Token, ...]:
    """Return nonempty byte spans; no guessed variable-to-person-name mutation."""
    pos = text_start(plain, sce=sce)
    tokens = []
    while pos < len(plain):
        end = plain.find(b"\0", pos)
        if end < 0:
            end = len(plain)
        if end > pos:
            tokens.append(Token(pos, end, plain[pos:end]))
        pos = end + 1
    return tuple(tokens)


def replace_token(plain: bytes, token: Token, replacement: bytes) -> bytes:
    """Equal-byte-length only; unknown ANIM offsets are never silently shifted."""
    if not 0x14 <= token.start <= token.end <= len(plain) or plain[token.start:token.end] != token.raw:
        raise ValueError("stale token")
    if b"\0" in replacement:
        raise ValueError("embedded terminator")
    if len(replacement) != len(token.raw):
        raise NotImplementedError("ANIM script relocation is not implemented")
    return plain[:token.start] + replacement + plain[token.end:]
