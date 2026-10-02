# Provenance group: tools-a; sources (repository-relative):
#   SExtractor/tools/DigitalWorks/文本工具(反编译与写回)/tak_text.py
# Symbols: disassemble, encode_text, lzs_decompress
# Validation: tests/test_engines_tools_a.py, synthetic fixtures only.
# Rewritten standard-library bytes API; scope: text-instruction-codec.
# SPDX-License-Identifier: GPL-3.0-only
# SExtractor tools/DigitalWorks/文本工具(反编译与写回)/tak_text.py:
# lzs_decompress, disassemble. Commit 8d8d976fd04ae54e7c677705af937273d04a376a.
# Rewrite: no hardcoded EXE index; explicitly framed TAK text instructions only.
"""BunBun TAK A8/AA text-instruction codec, not whole TAK.BIN relocation."""
import struct


def encode_text_instruction(kind: str, identifier: int, text: str, *, encoding="cp932") -> bytes:
    if kind not in ("name", "message"):
        raise ValueError("unknown text opcode")
    raw = text.encode(encoding)
    if len(raw) % 2 or b"\0" in raw:
        raise ValueError("TAK text must contain even-length, non-NUL bytes")
    end = 0xA9 if kind == "name" else 0xAB
    if any(raw[i] == end for i in range(0, len(raw), 2)):
        raise ValueError("text collides with end-opcode at pair boundary")
    op = 0xA8 if kind == "name" else 0xAA
    pad = bytes((-len(raw)) % 4)
    return struct.pack("<BBH", op, 0, identifier) + raw + pad + bytes((end, 0, 0, 0))


def decode_text_instruction(data: bytes, *, encoding="cp932") -> tuple[str, int, str]:
    if len(data) < 8 or data[0] not in (0xA8, 0xAA) or data[1] != 0:
        raise ValueError("not a supported TAK text instruction")
    end = 0xA9 if data[0] == 0xA8 else 0xAB
    pos = 4
    while pos + 1 < len(data) and data[pos] not in (0, end):
        pos += 2
    text_end = pos
    while pos < len(data) and data[pos] == 0:
        pos += 1
    if pos % 4 or data[pos:] != bytes((end, 0, 0, 0)):
        raise ValueError("invalid TAK alignment/terminator")
    return ("name" if data[0] == 0xA8 else "message",
            struct.unpack_from("<H", data, 2)[0], data[4:text_end].decode(encoding))
