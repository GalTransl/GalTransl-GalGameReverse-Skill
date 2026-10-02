# SPDX-License-Identifier: GPL-3.0-only
"""BlackRainbow's 0x4c-header segment script, not its DAT/PAK container."""
from dataclasses import dataclass
import struct

DEFAULT_KEY = b"\x2b\xc5\x2a\x3d"


def xor_text(data: bytes, key: bytes = DEFAULT_KEY) -> bytes:
    if not key:
        raise ValueError("empty XOR key")
    return bytes(value ^ key[i % len(key)] for i, value in enumerate(data))


@dataclass(frozen=True)
class Segment:
    kind: int
    prefix: bytes
    role_bytes: bytes
    text: bytes | None
    offset: int


def parse_script(data: bytes, *, key: bytes = DEFAULT_KEY) -> tuple[bytes, tuple[Segment, ...]]:
    """Validate every segment length, preserve opaque commands and raw role bytes."""
    if len(data) < 0x4C:
        raise ValueError("truncated BlackRainbow header")
    declared = struct.unpack_from("<I", data, 0x48)[0]
    if declared != len(data) - 0x4C:
        raise ValueError("script total length mismatch")
    pos = 0x4C
    result = []
    while pos < len(data):
        if pos + 8 > len(data):
            raise ValueError("truncated segment header")
        kind, size = struct.unpack_from("<II", data, pos)
        end = pos + 8 + size
        if end > len(data):
            raise ValueError("segment outside file")
        body = data[pos + 8:end]
        prefix, role, text = body, b"", None
        if kind == 8:
            if len(body) < 20:
                raise ValueError("truncated dialogue")
            role_len, text_len = struct.unpack_from("<II", body, 12)
            if 20 + role_len + text_len != len(body):
                raise ValueError("dialogue inner lengths disagree")
            prefix = body[:12]
            role = body[20:20 + role_len]
            text = xor_text(body[20 + role_len:], key)
        elif kind in (0x0E, 0x1D, 0x1E):
            prefix_len = 8 if kind == 0x0E else 0
            if len(body) < prefix_len + 4:
                raise ValueError("truncated choice/title")
            text_len = struct.unpack_from("<I", body, prefix_len)[0]
            if prefix_len + 4 + text_len != len(body):
                raise ValueError("choice/title length mismatch")
            prefix, text = body[:prefix_len], body[prefix_len + 4:]
        result.append(Segment(kind, prefix, role, text, pos))
        pos = end
    return data[:0x4C], tuple(result)


def replace_texts(data: bytes, replacements: dict[int, bytes], *, key: bytes = DEFAULT_KEY) -> bytes:
    """Rebuild known segment lengths and total size; keys are segment ordinals.

    Implements the source's local segment layout, not any external archive offsets.
    """
    header, segments = parse_script(data, key=key)
    if any(type(i) is not int or not 0 <= i < len(segments) or segments[i].text is None for i in replacements):
        raise ValueError("replacement is not a text segment")
    bodies = []
    for i, segment in enumerate(segments):
        text = replacements.get(i, segment.text)
        if text is not None and not isinstance(text, bytes):
            raise TypeError("replacement must be encoded bytes")
        if segment.kind == 8:
            body = segment.prefix + struct.pack("<II", len(segment.role_bytes), len(text))
            body += segment.role_bytes + xor_text(text, key)
        elif segment.kind in (0x0E, 0x1D, 0x1E):
            body = segment.prefix + struct.pack("<I", len(text)) + text
        else:
            body = segment.prefix
        bodies.append(struct.pack("<II", segment.kind, len(body)) + body)
    body = b"".join(bodies)
    return header[:0x48] + struct.pack("<I", len(body)) + body
