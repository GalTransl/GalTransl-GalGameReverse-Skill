"""Escu:de mdb tables used by the @code/@mess Haison profile.

Original implementation, GPL-3.0-or-later, from independently checked binary
layout and the sample's db_set/NAME_T schema. No game data/source is bundled.
This is not Microsoft Access MDB. Only integer and string-offset columns are
supported; unknown types/sizes fail. There is no database writer.
"""
from dataclasses import dataclass
import struct


@dataclass(frozen=True)
class Column:
    name: str
    kind: int
    width: int


@dataclass(frozen=True)
class Table:
    name: str
    offset: int
    columns: tuple[Column, ...]
    rows: tuple[tuple[int | str, ...], ...]


def read_mdb(data: bytes, *, max_bytes: int = 16 << 20,
             max_tables: int = 128, max_rows: int = 100_000) -> tuple[Table, ...]:
    """Read sized headers/rows/pools until the exact u32 zero terminator."""
    if len(data) > max_bytes or data[:4] != b"mdb\0":
        raise ValueError("not bounded Escu:de mdb")
    pos = 4
    tables = []
    row_total = 0

    def u32() -> int:
        nonlocal pos
        if pos+4 > len(data):
            raise ValueError("truncated mdb word")
        value, = struct.unpack_from("<I", data, pos)
        pos += 4
        return value

    while True:
        start = pos
        header_size = u32()
        if header_size == 0:
            if pos != len(data):
                raise ValueError("unknown mdb trailing data")
            return tuple(tables)
        if len(tables) >= max_tables:
            raise ValueError("mdb table budget exceeded")
        name_offset, count = u32(), u32()
        if not 0 < count <= 256 or header_size != 8+8*count or pos+8*count > len(data):
            raise ValueError("invalid mdb column header")
        specs = [struct.unpack_from("<HHI", data, pos+i*8) for i in range(count)]
        pos += 8*count
        if any(not (kind == 1 and width in (1, 2, 4) or kind == 4 and width == 4)
               for kind, width, _ in specs):
            raise ValueError("unsupported mdb column kind/width")
        row_size = sum(spec[1] for spec in specs)
        raw_size = u32()
        if raw_size % row_size or pos+raw_size > len(data):
            raise ValueError("invalid mdb row section")
        row_total += raw_size // row_size
        if row_total > max_rows:
            raise ValueError("mdb row budget exceeded")
        raw = data[pos:pos+raw_size]
        pos += raw_size
        pool_size = u32()
        if pos+pool_size > len(data):
            raise ValueError("truncated mdb string pool")
        pool = data[pos:pos+pool_size]
        pos += pool_size

        def string(offset: int) -> str:
            if offset >= len(pool) or offset and pool[offset-1] != 0:
                raise ValueError("mdb string offset is not a string boundary")
            end = pool.find(b"\0", offset)
            if end < 0:
                raise ValueError("unterminated mdb string")
            return pool[offset:end].decode("cp932", errors="strict")

        name = string(name_offset)
        columns = tuple(Column(string(off), kind, width) for kind, width, off in specs)
        if any(t.name == name for t in tables) or len({c.name for c in columns}) != count:
            raise ValueError("duplicate mdb table/column name")
        rows = []
        for base in range(0, len(raw), row_size):
            values = []
            for kind, width, _ in specs:
                value = int.from_bytes(raw[base:base+width], "little")
                values.append(string(value) if kind == 4 else value)
                base += width
            rows.append(tuple(values))
        tables.append(Table(name, start, columns, tuple(rows)))


def read_names(data: bytes) -> tuple[str, ...]:
    """Display-name row indices are NAME operands; combined names stay one slot."""
    expected = (("名前", 4, 4), ("文字色", 1, 4), ("キャラID", 1, 4),
                ("音声グループ", 1, 4), ("顔画像", 4, 4))
    for table in read_mdb(data):
        if table.name == "登場人物":
            if tuple((c.name, c.kind, c.width) for c in table.columns) != expected:
                raise ValueError("unknown mdb speaker schema")
            names = tuple(row[0] for row in table.rows)
            if not names or names[0] != "":
                raise ValueError("mdb speaker zero must be empty")
            return names
    raise ValueError("missing mdb speaker table")
