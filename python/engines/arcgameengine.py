"""AGE XOR-FF/aligned string-pool codec; no instruction/address relocator.

Adapted from VNTextPatch-net8 (MIT), commit
d9c0fab7b72fdcf87d674ef12a84d3829c9188be,
VNTextPatch.Shared/Scripts/ArcGameEngine/AgeStringPoolBuilder.cs, Add.
"""
from collections.abc import Iterable


def build_string_pool(strings: Iterable[str], *, encoding: str = "cp932") -> tuple[bytes, tuple[int, ...]]:
    """Return encrypted pool and per-input relative addresses in FOUR-BYTE units.

    Equal Unicode strings share an address. NUL and padding are XORed too.
    No tunnel encoding; strict encoding is a caller-visible deployment limit.
    """
    pool = bytearray()
    addresses = []
    seen = {}
    for text in strings:
        if not isinstance(text, str) or "\0" in text:
            raise ValueError("expected a NUL-free string")
        if text not in seen:
            seen[text] = len(pool) // 4
            raw = text.encode(encoding, "strict") + b"\0"
            raw += b"\0" * (-len(raw) % 4)
            pool.extend(b ^ 255 for b in raw)
        addresses.append(seen[text])
    return bytes(pool), tuple(addresses)


def read_pool_string(pool: bytes, word_address: int, *, encoding: str = "cp932") -> str:
    """Read a pool-relative word address, validating terminator and zero padding."""
    if len(pool) % 4 or type(word_address) is not int or word_address < 0:
        raise ValueError("unaligned pool or invalid word address")
    start = word_address * 4
    if start >= len(pool):
        raise ValueError("pool address out of bounds")
    stop = pool.find(b"\xff", start)
    if stop < 0:
        raise ValueError("unterminated AGE pool string")
    end = (stop + 4) & ~3
    if any(b != 255 for b in pool[stop:end]):
        raise ValueError("nonzero decoded alignment padding")
    return bytes(b ^ 255 for b in pool[start:stop]).decode(encoding, "strict")
