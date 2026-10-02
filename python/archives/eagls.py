# SPDX-License-Identifier: GPL-3.0-only
"""EAGLS/ALIS script-tool algorithms, extracted into explicit byte transforms.

Keys/text offset/version must be supplied; no known-plaintext key guessing.
"""
# Layer split: archives; format algorithms and original notices retained.
# Companion module: python/engines/eagls.py



class MSVCRTRand:
    def __init__(self, seed: int):
        self.seed = seed

    def rand(self) -> int:
        self.seed = (214013 * self.seed + 2531011) & 0x7FFFFFFF
        return self.seed >> 16


def crypt_index(index: bytes, key: bytes) -> bytes:
    """XOR all bytes except the final LE seed word (same operation both ways)."""
    if len(index) < 4 or not key:
        raise ValueError("index seed and nonempty key required")
    random = MSVCRTRand(int.from_bytes(index[-4:], "little"))
    body = bytes(b ^ key[random.rand() % len(key)] for b in index[:-4])
    return body + index[-4:]


from dataclasses import dataclass
import struct
from ..common.safety import Limits, validate_names


DEFAULT_INDEX_KEY = b"1qaz2wsx3edc4rfv5tgb6yhn7ujm8ik,9ol.0p;/-@:^[]"


@dataclass(frozen=True)
class Entry:
    name: str
    offset: int
    size: int


def read_index(index: bytes, pak_size: int, *, key: bytes, long_offsets: bool,
               limits: Limits = Limits()) -> tuple[bytes, tuple[Entry, ...]]:
    """Explicit SCPACK layout; enforce a contiguous, fully covered PAK.

    Index/packing layout adapted from Cosetto's EAGLS_script_tool/scpacker.py
    distributed by SExtractor (GPL-3.0-only). Unlike its sequential reader,
    validate every stored offset against the first entry's base address.
    """
    width, fmt = (24, "<QQ") if long_offsets else (20, "<II")
    stride = width + struct.calcsize(fmt)
    if len(index) > limits.max_file_bytes or len(index) < stride + 5:
        raise ValueError("invalid or oversized index")
    if not 0 <= pak_size <= limits.max_total_bytes:
        raise ValueError("PAK exceeds budget")
    plain = crypt_index(index, key)
    entries, base, end = [], None, 0
    for pos in range(0, len(plain) - 4, stride):
        if plain[pos] == 0:
            break
        if pos + stride > len(plain) - 4 or len(entries) >= limits.max_entries:
            raise ValueError("truncated index or entry limit exceeded")
        raw_name = plain[pos:pos + width]
        if b"\0" not in raw_name:
            raise ValueError("unterminated member name")
        name = raw_name.split(b"\0", 1)[0].decode("cp932", "strict")
        offset, size = struct.unpack_from(fmt, plain, pos + width)
        if base is None:
            base = offset
        offset -= base
        if offset != end or size == 0 or size > limits.max_file_bytes or offset + size > pak_size:
            raise ValueError("noncontiguous, overlapping or out-of-range member")
        entries.append(Entry(name, offset, size))
        end = offset + size
    else:
        raise ValueError("missing index sentinel")
    if not entries or end != pak_size:
        raise ValueError("empty index or unindexed PAK bytes")
    validate_names([e.name for e in entries], limits)
    return plain, tuple(entries)


def pack_archive(index: bytes, pak: bytes, replacements: dict[str, bytes], *,
                 key: bytes, long_offsets: bool, limits: Limits = Limits()) -> tuple[bytes, bytes]:
    """Return encrypted IDX and PAK, retaining base, names, padding and seed.

    Replacements are already encrypted complete members. Unspecified members
    are copied; no script encryption or text encoding is inferred here.
    """
    plain, entries = read_index(index, len(pak), key=key, long_offsets=long_offsets, limits=limits)
    if set(replacements) - {e.name for e in entries}:
        raise ValueError("unknown replacement member")
    width, fmt = (24, "<QQ") if long_offsets else (20, "<II")
    stride = width + struct.calcsize(fmt)
    base = struct.unpack_from(fmt, plain, width)[0]
    new_index, body = bytearray(plain), bytearray()
    for number, entry in enumerate(entries):
        data = replacements.get(entry.name, pak[entry.offset:entry.offset + entry.size])
        if not isinstance(data, bytes) or not 0 < len(data) <= limits.max_file_bytes:
            raise ValueError("invalid replacement size/type")
        if len(body) + len(data) > limits.max_total_bytes:
            raise ValueError("rebuilt PAK exceeds budget")
        struct.pack_into(fmt, new_index, number * stride + width, base + len(body), len(data))
        body.extend(data)
    encrypted = crypt_index(bytes(new_index), key)
    read_index(encrypted, len(body), key=key, long_offsets=long_offsets, limits=limits)
    return encrypted, bytes(body)
