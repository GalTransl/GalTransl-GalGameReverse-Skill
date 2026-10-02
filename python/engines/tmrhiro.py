"""TmrHiro text file codec: repeated signed-i16 byte length + CP932 bytes.

Adapted from VNTextPatch-net8 (MIT), commit
d9c0fab7b72fdcf87d674ef12a84d3829c9188be,
VNTextPatch.Shared/Scripts/TmrHiroAdvSystem/TmrHiroAdvSystemTextScript.cs,
GetStrings and WritePatched. This is NOT the separate CodeScript format.
"""
from collections.abc import Iterable, Mapping
import struct


def read_text(data: bytes, *, encoding: str = "cp932") -> tuple[str, ...]:
    result = []
    pos = 0
    while pos < len(data):
        if pos + 2 > len(data):
            raise ValueError("truncated signed-i16 length")
        size = struct.unpack_from("<h", data, pos)[0]
        pos += 2
        if size < 0 or pos + size > len(data):
            raise ValueError("negative or out-of-bounds text length")
        result.append(data[pos:pos + size].decode(encoding, "strict"))
        pos += size
    return tuple(result)


def write_text(strings: Iterable[str], *, encoding: str = "cp932") -> bytes:
    out = bytearray()
    for text in strings:
        raw = text.encode(encoding, "strict")
        if len(raw) > 32767:
            raise ValueError("encoded text exceeds signed-i16 byte length")
        out.extend(struct.pack("<h", len(raw)))
        out.extend(raw)
    return bytes(out)


def patch_text(data: bytes, replacements: Mapping[int, str], *,
               encoding: str = "cp932") -> bytes:
    """Keep unchanged record bytes exactly, including CP932 alias codepoints."""
    strings = read_text(data, encoding=encoding)
    if any(type(i) is not int or not 0 <= i < len(strings) for i in replacements):
        raise ValueError("unknown text record index")
    pos = 0
    out = bytearray()
    for i in range(len(strings)):
        size = struct.unpack_from("<h", data, pos)[0]
        end = pos + 2 + size
        out.extend(write_text([replacements[i]], encoding=encoding)
                   if i in replacements else data[pos:end])
        pos = end
    return bytes(out)
