"""Seekable index/member I/O shared by YPF, Will ARC and Softpal PAC.

New implementation for this skill. No format detection, codecs or disk writes.
Index snapshots are not authentication: callers must keep the archive unchanged.
"""

from contextlib import contextmanager

from ..common.binary import FormatError
from ..common.safety import Limits, validate_names


def limit(value: int, name: str) -> None:
    if type(value) is not int or value < 0:
        raise FormatError("invalid " + name)


@contextmanager
def preserve_position(stream):
    position = stream.tell()
    try:
        yield
    finally:
        stream.seek(position)


def stream_size(stream) -> int:
    stream.seek(0, 2)
    return stream.tell()


def check_range(offset: int, size: int, end: int, *, start: int = 0) -> None:
    if (type(offset) is not int or type(size) is not int or size < 0
            or offset < start or offset > end or size > end - offset):
        raise FormatError("archive range outside permitted region")


def read_at(stream, offset: int, size: int, end: int) -> bytes:
    check_range(offset, size, end)
    stream.seek(offset)
    result = bytearray()
    while len(result) < size:
        amount = min(size - len(result), 1 << 20)
        part = stream.read(amount)
        if not isinstance(part, bytes) or not part or len(part) > amount:
            raise FormatError("truncated archive or invalid binary stream")
        result.extend(part)
    return bytes(result)


def validate_entries(entries, index_end: int, archive_size: int, max_entries: int):
    validate_names([entry.name for entry in entries], Limits(max_entries=max_entries))
    for entry in entries:
        check_range(entry.offset, entry.size, archive_size, start=index_end)


def read_member_bytes(stream, index, entry, *, max_stored_size: int) -> bytes:
    limit(max_stored_size, "max_stored_size")
    if (type(entry.ordinal) is not int or not 0 <= entry.ordinal < len(index.entries)
            or index.entries[entry.ordinal] is not entry):
        raise FormatError("member does not belong to this index")
    if entry.size > max_stored_size:
        raise FormatError("stored member exceeds budget")
    with preserve_position(stream):
        size = stream_size(stream)
        if size != index.archive_size:
            raise FormatError("archive size changed since indexing")
        check_range(entry.offset, entry.size, size, start=index.index_end)
        return read_at(stream, entry.offset, entry.size, size)
