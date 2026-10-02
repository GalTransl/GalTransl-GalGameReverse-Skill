"""Cyberworks a0 S/T framed blocks; bytes-only text payloads.

Adapted from SExtractor (GPL-3.0), commit
8d8d976fd04ae54e7c677705af937273d04a376a,
src/extract_Cyberworks.py, readFileDataImp and replaceEndImp.
Reject encrypted S lengths >=256 instead of guessing the source's None key.
"""
from dataclasses import dataclass
from collections.abc import Mapping
import struct


@dataclass(frozen=True)
class Block:
    kind: str
    prefix: bytes
    text: bytes
    suffix: bytes


def _xor(raw: bytes, key: bytes) -> bytes:
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(raw))


def read_blocks(data: bytes, *, encrypted: bool = True,
                s_has_length: bool = True) -> tuple[tuple[Block, ...], bytes]:
    """Parse length-prefixed blocks; return blocks and explicit zero-sentinel tail.

    Unknown nonzero tags are opaque M blocks. Truncation is never a tail.
    S length counts bytes; T length counts UTF-16 code units (two bytes).
    """
    if encrypted and not s_has_length:
        raise ValueError("S noTextLen variant must be explicitly unencrypted")
    blocks = []
    pos = 0
    while pos < len(data):
        if pos + 4 > len(data):
            raise ValueError("truncated a0 block length")
        size = struct.unpack_from("<I", data, pos)[0]
        if size == 0:
            return tuple(blocks), data[pos:]
        if size > 65535 or pos + 4 + size > len(data):
            raise ValueError("a0 block exceeds bounds or supported 0xffff limit")
        body = data[pos + 4:pos + 4 + size]
        tag = body[:1]
        if tag == b"S":
            start = 5 if s_has_length else 1
            if len(body) < start:
                raise ValueError("truncated S header")
            count = struct.unpack_from("<I", body, 1)[0] if s_has_length else size - 1
            if start + count > len(body):
                raise ValueError("S text exceeds its block")
            if encrypted and count >= 256:
                raise ValueError("encrypted S length >=256 is not supported")
            raw = body[start:start + count]
            text = _xor(raw, bytes([count])) if encrypted else raw
            blocks.append(Block("S", b"S", text, body[start + count:]))
        elif tag == b"T":
            if len(body) < 9:
                raise ValueError("truncated T header")
            count = struct.unpack_from("<I", body, 5)[0]
            end = 9 + count * 2
            if end > len(body):
                raise ValueError("T text exceeds its block")
            raw = body[9:end]
            text = _xor(raw, body[5:7]) if encrypted else raw
            blocks.append(Block("T", body[:5], text, body[end:]))
        else:
            blocks.append(Block("M", b"", b"", body))
        pos += 4 + size
    return tuple(blocks), b""


def write_blocks(blocks: tuple[Block, ...], tail: bytes = b"", *,
                 encrypted: bool = True, s_has_length: bool = True) -> bytes:
    """Recalculate both lengths, preserve opaque prefixes/suffixes and sentinel."""
    if encrypted and not s_has_length:
        raise ValueError("S noTextLen variant must be explicitly unencrypted")
    if tail and not tail.startswith(b"\0\0\0\0"):
        raise ValueError("tail must begin with the zero block-length sentinel")
    out = bytearray()
    for block in blocks:
        if block.kind == "S":
            if block.prefix != b"S":
                raise ValueError("invalid S prefix")
            count = len(block.text)
            if encrypted and count >= 256:
                raise ValueError("encrypted S length >=256 is not supported")
            if not s_has_length and block.suffix:
                raise ValueError("noTextLen S cannot distinguish text and suffix")
            raw = _xor(block.text, bytes([count])) if encrypted else block.text
            body = b"S" + (struct.pack("<I", count) if s_has_length else b"") + raw + block.suffix
        elif block.kind == "T":
            if len(block.prefix) != 5 or block.prefix[:1] != b"T" or len(block.text) % 2:
                raise ValueError("invalid T prefix or odd UTF-16 payload length")
            count = struct.pack("<I", len(block.text) // 2)
            raw = _xor(block.text, count[:2]) if encrypted else block.text
            body = block.prefix + count + raw + block.suffix
        elif block.kind == "M":
            if block.prefix or block.text or block.suffix[:1] in (b"S", b"T"):
                raise ValueError("M must be a nontext opaque block")
            body = block.suffix
        else:
            raise ValueError("unknown block kind")
        if not 1 <= len(body) <= 65535:
            raise ValueError("a0 block length must be 1..65535")
        out.extend(struct.pack("<I", len(body)) + body)
    return bytes(out) + tail


def patch_blocks(data: bytes, replacements: Mapping[int, bytes], *,
                 encrypted: bool = True, s_has_length: bool = True) -> bytes:
    """Replace text by BLOCK index (M indexes remain in the sequence)."""
    blocks, tail = read_blocks(data, encrypted=encrypted, s_has_length=s_has_length)
    result = list(blocks)
    for i, text in replacements.items():
        if type(i) is not int or not 0 <= i < len(blocks) or blocks[i].kind == "M":
            raise ValueError("replacement must target an S/T block index")
        if not isinstance(text, bytes):
            raise TypeError("text payload must be explicitly encoded bytes")
        old = blocks[i]
        result[i] = Block(old.kind, old.prefix, text, old.suffix)
    return write_blocks(tuple(result), tail, encrypted=encrypted, s_has_length=s_has_length)
