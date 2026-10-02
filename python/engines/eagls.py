# SPDX-License-Identifier: GPL-3.0-only
"""EAGLS/ALIS script-tool algorithms, extracted into explicit byte transforms.

Keys/text offset/version must be supplied; no known-plaintext key guessing.
"""
# Layer split: engines; format algorithms and original notices retained.
# Companion module: python/archives/eagls.py
import re
import struct
from ..archives.eagls import MSVCRTRand


def crypt_script(data: bytes, *, text_offset: int, key: bytes, version: int) -> bytes:
    """v1 XORs entire tail; v2 XORs alternate bytes with a signed final-byte seed."""
    if version not in (1, 2) or not key or not 0 <= text_offset <= len(data) - version:
        raise ValueError("invalid EAGLS profile, offset, key or footer")
    out = bytearray(data)
    if version == 1:
        for pos in range(text_offset, len(data)):
            out[pos] ^= key[(pos - text_offset) % len(key)]
    else:
        seed = data[-1] if data[-1] < 128 else data[-1] - 256
        random = MSVCRTRand(seed)
        for pos in range(text_offset, len(data) - 1, 2):
            out[pos] ^= key[random.rand() % len(key)]
    return bytes(out)


def read_labels(plain: bytes, *, text_offset: int, label_size: int = 36) -> tuple[tuple[bytes, int], ...]:
    """Read label table (36 EAGLS / 136 ALIS); offsets are relative to text body."""
    if label_size not in (36, 136) or not 0 <= text_offset <= len(plain):
        raise ValueError("invalid label table")
    labels = []
    seen = set()
    for pos in range(0, text_offset - label_size + 1, label_size):
        entry = plain[pos:pos + label_size]
        if entry[0] == 0:
            return tuple(labels)
        label = entry[:-4].split(b"\0", 1)[0]
        if label in seen:
            raise ValueError("duplicate label")
        seen.add(label)
        offset = struct.unpack_from("<I", entry, label_size - 4)[0]
        if offset >= len(plain) - text_offset:
            raise ValueError("label offset outside text")
        labels.append((label, offset))
    raise ValueError("label table lacks empty sentinel")


def fix_label_offsets(plain: bytes, *, text_offset: int, version: int, label_size: int = 36) -> bytes:
    """Recompute existing labels after editing a decoded script, preserving header/footer.

    Match complete CR/LF line labels, not '$foo' inside '$foobar' or dialogue.
    Old offsets need not fit the newly shortened body.
    """
    if version not in (1, 2) or not 0 <= text_offset <= len(plain) - version:
        raise ValueError("invalid footer or text offset")
    if label_size not in (36, 136):
        raise ValueError("unsupported label record size")
    body = plain[text_offset:-version]
    out = bytearray(plain)
    seen = set()
    sentinel = False
    for pos in range(0, text_offset - label_size + 1, label_size):
        entry = plain[pos:pos + label_size]
        if entry[0] == 0:
            sentinel = True
            break
        label = entry[:-4].split(b"\0", 1)[0]
        if not label or label in seen:
            raise ValueError("empty/duplicate label")
        seen.add(label)
        pattern = rb"(?m)^\$" + re.escape(label) + rb"(?=[:(\r\n]|$)"
        matches = list(re.finditer(pattern, body))
        if len(matches) != 1:
            raise ValueError("missing or ambiguous line label")
        struct.pack_into("<I", out, pos + label_size - 4, matches[0].start())
    if not sentinel:
        raise ValueError("missing label-table sentinel")
    return bytes(out)


def dialogue_spans(line: str) -> tuple[tuple[str, int, int], ...]:
    """CRLF-decoded EAGLS text: &number\"text\", #name, and _SelStr choices."""
    if not line or line.startswith("_"):
        return ()
    result = []
    pattern = r'&\d+?"(?P<message>[^"]+?)"|#(?P<name>[^,&=\r\n0-9]+)|"_SelStr\d+","(?P<choice>[^"]+?)"'
    for match in re.finditer(pattern, line):
        role = match.lastgroup
        result.append((role, *match.span(role)))
    return tuple(result)
