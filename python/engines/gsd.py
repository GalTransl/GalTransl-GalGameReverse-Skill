# SPDX-License-Identifier: GPL-3.0-only
"""Decoded GSD v2-family SPT dialogue records and global.dat names.

profile=1/2 means SExtractor command layout, not GSD engine generation.
GSD v3 and profile 3 are intentionally outside this reference.
"""
from dataclasses import dataclass
import struct


@dataclass(frozen=True)
class Cell:
    offset: int
    opcode: int
    raw: bytes
    character: bytes | None


@dataclass(frozen=True)
class Dialogue:
    start: int
    end: int
    name_id: int | None
    cells: tuple[Cell, ...]
    end_cell: bytes

    def text_runs(self, encoding: str = "cp932") -> tuple[str | Cell, ...]:
        """Decode runs strictly; control cells remain typed objects, never fake text."""
        result = []
        pending = bytearray()
        for cell in self.cells:
            if cell.character is not None:
                pending.extend(cell.character)
            else:
                if pending:
                    result.append(bytes(pending).decode(encoding))
                    pending.clear()
                result.append(cell)
        if pending:
            result.append(bytes(pending).decode(encoding))
        return tuple(result)


def _u32(data: bytes, pos: int) -> int:
    if pos < 0 or pos + 4 > len(data):
        raise ValueError("truncated GSD word")
    return struct.unpack_from("<I", data, pos)[0]


def read_dialogue(decoded_spt: bytes, offset: int, *, profile: int) -> Dialogue:
    """0x40-byte header then count*12-byte cells; last cell is end opcode."""
    if profile not in (1, 2):
        raise NotImplementedError("only decoded GSD v2-family source profiles 1 and 2")
    signature = struct.pack("<IIII", 1, 0, 0, 0xFFFFFFFF if profile == 1 else 0)
    if offset < 0 or decoded_spt[offset:offset + 16] != signature:
        raise ValueError("dialogue signature mismatch")
    name_id = _u32(decoded_spt, offset + 0x28)
    count = _u32(decoded_spt, offset + 0x34)
    if not 2 <= count <= 0x300:
        raise ValueError("invalid GSD character-cell count")
    pos = offset + 0x40
    end = pos + count * 12
    if end > len(decoded_spt):
        raise ValueError("truncated cells")
    end_opcode = 8 if profile == 1 else 0x0A
    controls = set() if profile == 1 else {5, 7, 8, 9}
    cells = []
    for i in range(count - 1):
        start = pos + i * 12
        raw = decoded_spt[start:start + 12]
        opcode = _u32(raw, 0)
        if opcode != 7 and opcode not in controls:
            raise ValueError("unexpected text/control opcode")
        character = None
        if opcode == 7:
            character = raw[8:12].split(b"\0", 1)[0]
            if not character:
                raise ValueError("empty character cell")
        cells.append(Cell(start, opcode, raw, character))
    end_cell = decoded_spt[end - 12:end]
    if _u32(end_cell, 0) != end_opcode:
        raise ValueError("wrong end opcode for selected profile")
    return Dialogue(offset, end, None if name_id == 0xFFFFFFFF else name_id, tuple(cells), end_cell)


def read_global_names(data: bytes, *, skip_sections: int, encoding: str = "cp932") -> tuple[str, ...]:
    """Explicit section count avoids the upstream heuristic for locating name records."""
    if not 0 <= skip_sections <= 256 or len(data) < 12:
        raise ValueError("invalid section count/header")
    pos = 8
    for _ in range(skip_sections):
        count = _u32(data, pos)
        pos += 4
        if count > (len(data) - pos) // (8 + 0x8C):
            raise ValueError("section command count exceeds file")
        for _ in range(count):
            for _ in range(2):
                size = _u32(data, pos)
                pos += 4 + size
                if pos > len(data):
                    raise ValueError("truncated section string")
            pos += 0x8C
    count = _u32(data, pos)
    pos += 4
    if count > (len(data) - pos) // 0x104:
        raise ValueError("name table outside global.dat")
    names = []
    for index in range(count):
        raw = data[pos + index * 0x104:pos + (index + 1) * 0x104]
        end = raw.find(b"\0")
        if end < 0:
            raise ValueError("unterminated fixed name record")
        names.append(raw[:end].decode(encoding))
    return tuple(names)


def write_spt(*args, **kwargs) -> bytes:
    raise NotImplementedError("no GSD cell-count/selection relocation or SPT encode stage")
