"""RPA-3.0 single-chunk extractor with a non-executing pickle data interpreter.

Supports a data-only subset of pickle protocols 0..5; no GLOBAL/REDUCE/BUILD, persistent
IDs, object constructors, or container memo references. This purposely
rejects some legitimate archives rather than running pickle code. Multi-chunk
file lists are rejected, never silently truncated to the first chunk.
RPA2/RPA4, game-specific scrambling, and RPYC objects require separate profiles.
Returned names are untrusted; only the caller may safely materialize them.

Format reference: GARbro-Mod, ArcFormats/RenPy/ArcRPA.cs,
RpaOpener.TryOpen/OpenEntry/Create and Pickle, commit
bc26d991ef5cdc0e1ecb32122ee9a48c3375750c (MIT).
Copyright (C) 2014 by morkt

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
from dataclasses import dataclass
import codecs
import io
import pickle
import pickletools
import re
import zlib


@dataclass(frozen=True)
class Entry:
    name: str
    data: bytes
    offset: int
    prefix_size: int


@dataclass(frozen=True)
class IndexEntry:
    name: str
    raw_name: object
    offset: int
    length: int
    prefix: bytes
    chunk: tuple


@dataclass(frozen=True)
class Index:
    header: bytes
    offset: int
    key: int
    size: int
    entries: list[IndexEntry]


def _data_opcodes(data: bytes):
    """Parse allowed operands, preserving Python-2 protocol-0 STRING bytes.

    pickletools.genops decodes STRING as ASCII before yielding it. Reading that
    operand here avoids rejecting escaped high bytes without enabling pickle
    constructors or evaluating a Python expression. The enclosing index budget
    bounds line/operand allocation. All other operands use stdlib data readers.
    """
    allowed = {
        "PROTO", "STOP", "MARK", "BININT", "BININT1", "BININT2", "INT", "LONG",
        "LONG1", "LONG4", "STRING", "BINSTRING", "SHORT_BINSTRING", "BINUNICODE",
        "UNICODE", "BINBYTES", "SHORT_BINBYTES", "EMPTY_LIST", "EMPTY_DICT",
        "EMPTY_TUPLE", "TUPLE", "LIST", "DICT", "TUPLE1", "TUPLE2", "TUPLE3",
        "APPEND", "APPENDS", "SETITEM", "SETITEMS", "PUT", "BINPUT", "LONG_BINPUT",
        "GET", "BINGET", "LONG_BINGET", "FRAME", "MEMOIZE", "SHORT_BINUNICODE",
    }
    stream = io.BytesIO(data)
    frame_end = None
    while stream.tell() < len(data):
        pos = stream.tell()
        code = stream.read(1)
        opcode = pickletools.code2op.get(chr(code[0]))
        if opcode is None or opcode.name not in allowed:
            raise ValueError("unsupported/unsafe RPA pickle opcode")
        if opcode.name == "STRING":
            line = stream.readline(len(data) - stream.tell() + 1)
            if not line.endswith(b"\n"):
                raise ValueError("unterminated RPA pickle STRING")
            literal = line[:-1]
            if len(literal) < 2 or literal[:1] not in (b"'", b'"') or literal[-1:] != literal[:1]:
                raise ValueError("unquoted RPA pickle STRING")
            arg = codecs.escape_decode(literal[1:-1], "strict")[0]
        else:
            arg = opcode.arg.reader(stream) if opcode.arg is not None else None
        if frame_end is not None and pos == frame_end:
            frame_end = None
        if opcode.name == "FRAME":
            if frame_end is not None or arg > len(data) - stream.tell():
                raise ValueError("RPA pickle frame exceeds bounds or nests")
            frame_end = stream.tell() + arg
        elif frame_end is not None:
            if stream.tell() > frame_end or (opcode.name == "STOP" and stream.tell() != frame_end):
                raise ValueError("RPA pickle opcode crosses frame boundary")
        yield opcode, arg, pos
        if opcode.name == "STOP":
            return


def _data_pickle(data: bytes, *, max_ops: int = 500_000,
                 max_stack: int = 20_000, max_memo: int = 100_000,
                 max_depth: int = 32):
    """Interpret an allowlist, NOT pickle.loads or a restricted Unpickler.

    Memo writes are bounded. GET may retrieve only immutable scalars, ruling
    out cycles, shared mutable containers, and exponential tree aliasing.
    """
    marker = object()
    stack, memo, depths = [], {}, {}
    marks = 0

    def pop_values():
        nonlocal marks
        if not marks:
            raise ValueError("RPA pickle missing MARK")
        pos = len(stack) - 1
        while pos >= 0 and stack[pos] is not marker:
            pos -= 1
        values = stack[pos + 1:]
        del stack[pos:]
        marks -= 1
        return values

    def depth(value):
        return depths.get(id(value), 0) if isinstance(value, (list, dict, tuple)) else 0

    def register(container, children):
        level = max((depth(item) for item in children), default=0) + 1
        level = max(level, depths.get(id(container), 1))
        if level > max_depth:
            raise ValueError("RPA pickle depth limit")
        depths[id(container)] = level
        return container

    def add_dict(target, values):
        if type(target) is not dict or len(values) % 2:
            raise ValueError("RPA pickle invalid dictionary")
        for i in range(0, len(values), 2):
            key, value = values[i:i + 2]
            if type(key) not in (str, bytes, int) or key in target:
                raise ValueError("RPA pickle unsupported/duplicate key")
            target[key] = value
        register(target, values)

    try:
        for number, (opcode, arg, pos) in enumerate(_data_opcodes(data), 1):
            if number > max_ops:
                raise ValueError("RPA pickle opcode budget")
            op = opcode.name
            if op == "PROTO":
                if pos != 0 or arg > 5:
                    raise ValueError("unsupported RPA pickle protocol")
            elif op == "FRAME":
                pass  # _data_opcodes checked frame length before reading its data.
            elif op == "STOP":
                if marks or len(stack) != 1 or pos + 1 != len(data):
                    raise ValueError("RPA pickle stack/trailing-data mismatch")
                return stack[0]
            elif op == "MARK":
                marks += 1
                if marks > max_depth:
                    raise ValueError("RPA pickle MARK depth limit")
                stack.append(marker)
            elif op in ("BININT", "BININT1", "BININT2", "INT", "LONG", "LONG1", "LONG4"):
                if type(arg) is not int or arg.bit_length() > 64:
                    raise ValueError("RPA pickle unsupported integer")
                stack.append(arg)
            elif op == "STRING":
                stack.append(arg)
            elif op in ("BINSTRING", "SHORT_BINSTRING"):
                stack.append(arg.encode("latin-1"))
            elif op in ("BINUNICODE", "SHORT_BINUNICODE", "UNICODE", "BINBYTES", "SHORT_BINBYTES"):
                stack.append(arg)
            elif op in ("EMPTY_LIST", "EMPTY_DICT", "EMPTY_TUPLE"):
                value = [] if op == "EMPTY_LIST" else {} if op == "EMPTY_DICT" else ()
                stack.append(register(value, []))
            elif op in ("TUPLE", "LIST", "DICT"):
                values = pop_values()
                if op == "DICT":
                    value = {}
                    add_dict(value, values)
                else:
                    value = tuple(values) if op == "TUPLE" else values
                    register(value, values)
                stack.append(value)
            elif op in ("TUPLE1", "TUPLE2", "TUPLE3"):
                count = int(op[-1])
                if len(stack) < count or any(v is marker for v in stack[-count:]):
                    raise ValueError("RPA pickle tuple underflow")
                value = tuple(stack[-count:])
                del stack[-count:]
                stack.append(register(value, value))
            elif op in ("APPEND", "APPENDS"):
                values = pop_values() if op == "APPENDS" else [stack.pop()]
                if not stack or type(stack[-1]) is not list or any(v is marker for v in values):
                    raise ValueError("RPA pickle list underflow/type")
                register(stack[-1], values)
                stack[-1].extend(values)
            elif op in ("SETITEM", "SETITEMS"):
                if op == "SETITEMS":
                    values = pop_values()
                else:
                    if len(stack) < 3:
                        raise ValueError("RPA pickle dictionary underflow")
                    values = stack[-2:]
                    del stack[-2:]
                if not stack:
                    raise ValueError("RPA pickle dictionary underflow")
                add_dict(stack[-1], values)
            elif op in ("PUT", "BINPUT", "LONG_BINPUT", "MEMOIZE"):
                if op == "MEMOIZE":
                    arg = len(memo)
                if not stack or stack[-1] is marker or not 0 <= arg < max_memo or arg in memo:
                    raise ValueError("RPA pickle invalid memo write/limit")
                memo[arg] = stack[-1]
            elif op in ("GET", "BINGET", "LONG_BINGET"):
                if arg not in memo or type(memo[arg]) not in (int, bytes, str):
                    raise ValueError("RPA pickle missing/scalar-only memo reference")
                stack.append(memo[arg])
            else:
                raise ValueError("unsupported/unsafe RPA pickle opcode: " + op)
            if len(stack) > max_stack:
                raise ValueError("RPA pickle stack limit")
    except (IndexError, UnicodeError, OverflowError, TypeError) as exc:
        raise ValueError("malformed RPA pickle data") from exc
    raise ValueError("RPA pickle missing STOP")


def read_index(stream, *, max_entries: int = 100_000,
            max_file_size: int = 64 << 20, max_total_size: int = 256 << 20,
            max_index_size: int = 16 << 20, max_archive_size: int = 512 << 20,
            max_pickle_ops: int = 500_000, max_pickle_stack: int = 20_000,
            max_pickle_memo: int = 100_000, max_pickle_depth: int = 32) -> Index:
    """Read only the header/index; reject multi-chunk and ambiguous input.

    tuple[0] XOR key = offset; tuple[1] XOR key = TOTAL decoded length,
    including prefix. Read only (total length - prefix length) archive bytes.
    Python-2 byte strings are preserved; Unicode prefixes must fit Latin-1.
    """
    stream.seek(0, 2)
    size = stream.tell()
    stream.seek(0)
    header = stream.read(34)
    if size > max_archive_size:
        raise ValueError("RPA input type/size")
    if min(max_entries, max_file_size, max_total_size, max_index_size,
           max_archive_size, max_pickle_ops, max_pickle_stack,
           max_pickle_memo, max_pickle_depth) < 0:
        raise ValueError("negative RPA limit")
    if not re.fullmatch(rb"(?:RPA|ARC)-3\.0 [0-9a-fA-F]{16} [0-9a-fA-F]{8}\n", header):
        raise ValueError("not supported RPA/ARC-3.0 header")
    index_at, key = int(header[8:24], 16), int(header[25:33], 16)
    if not 34 <= index_at < size:
        raise ValueError("RPA index offset outside data")
    if size - index_at > max_index_size:
        raise ValueError("RPA compressed index budget")
    decoder = zlib.decompressobj()
    stream.seek(index_at)
    packed_index = stream.read(size - index_at)
    try:
        index = decoder.decompress(packed_index, max_index_size + 1)
    except zlib.error as exc:
        raise ValueError("invalid RPA index zlib stream") from exc
    if len(index) > max_index_size or not decoder.eof or decoder.unconsumed_tail or decoder.unused_data:
        raise ValueError("RPA index size/truncation/trailing-data mismatch")
    mapping = _data_pickle(index, max_ops=max_pickle_ops, max_stack=max_pickle_stack,
                           max_memo=max_pickle_memo, max_depth=max_pickle_depth)
    if type(mapping) is not dict or not 0 < len(mapping) <= max_entries:
        raise ValueError("invalid RPA dictionary/count")
    result, names, total = [], set(), 0
    for raw_name, chunks in mapping.items():
        if type(raw_name) is bytes:
            name = raw_name.decode("utf-8", errors="strict")
        elif type(raw_name) is str:
            name = raw_name
        else:
            raise ValueError("RPA filename must be bytes/Unicode")
        if not name or "\0" in name or len(name) > 4096 or name in names:
            raise ValueError("invalid/duplicate RPA filename")
        if type(chunks) is not list or len(chunks) != 1:
            raise ValueError("unsupported RPA multi-chunk/empty chunk list")
        chunk = chunks[0]
        if type(chunk) is not tuple or len(chunk) not in (2, 3):
            raise ValueError("invalid RPA chunk tuple")
        if any(type(v) is not int or not 0 <= v <= 0xffffffffffffffff for v in chunk[:2]):
            raise ValueError("invalid RPA offset/length integer")
        offset, length = chunk[0] ^ key, chunk[1] ^ key
        prefix = chunk[2] if len(chunk) == 3 else b""
        if type(prefix) is str:
            prefix = prefix.encode("latin-1", errors="strict")
        if type(prefix) is not bytes:
            raise ValueError("unsupported RPA prefix type")
        if len(prefix) > length or length > max_file_size or total + length > max_total_size:
            raise ValueError("RPA prefix/length/output budget")
        stored_length = length - len(prefix)
        if not 34 <= offset <= index_at or stored_length > index_at - offset:
            raise ValueError("RPA payload range overlaps header/index or exceeds input")
        result.append(IndexEntry(name, raw_name, offset, length, prefix, chunk))
        names.add(name)
        total += length
    end = 34
    for entry in sorted(result, key=lambda e: e.offset):
        if entry.offset < end:
            raise ValueError("overlapping RPA member ranges")
        end = entry.offset + entry.length - len(entry.prefix)
    return Index(header, index_at, key, size, result)


def read_entry(stream, entry: IndexEntry) -> bytes:
    stream.seek(entry.offset)
    size = entry.length - len(entry.prefix)
    data = stream.read(size)
    if len(data) != size:
        raise ValueError("truncated RPA member")
    return entry.prefix + data


def extract(data: bytes, **limits) -> list[Entry]:
    if not isinstance(data, bytes):
        raise ValueError("RPA input type/size")
    stream = io.BytesIO(data)
    index = read_index(stream, **limits)
    return [Entry(e.name, read_entry(stream, e), e.offset, len(e.prefix)) for e in index.entries]


def rebuild(data: bytes, replacements: dict[str, bytes]) -> bytes:
    """Rebuild bounded single-chunk RPA/ARC3, preserving gaps, magic and key.

    No edits still traverse all members and reconstruct the archive exactly.
    Only a newly constructed data dictionary is serialized; no unpickling.
    """
    stream = io.BytesIO(data)
    index = read_index(stream)
    if replacements.keys() - {e.name for e in index.entries}:
        raise ValueError("unknown RPA replacement member")
    if any(not isinstance(v, bytes) or len(v) > 64 << 20 for v in replacements.values()):
        raise ValueError("RPA replacement type/size")
    output_size = sum(len(replacements[e.name]) if e.name in replacements else e.length for e in index.entries)
    if output_size > 256 << 20 or index.offset + output_size > 512 << 20:
        raise ValueError("RPA rebuilt output budget exceeded")
    out, cursor, chunks = bytearray(index.header), 34, {}
    changed = False
    for e in sorted(index.entries, key=lambda e: e.offset):
        payload = read_entry(stream, e)
        new = replacements.get(e.name, payload)
        changed |= new != payload
        out.extend(data[cursor:e.offset])
        prefix = new[:min(len(e.prefix), len(new))]
        chunk = (len(out) ^ index.key, len(new) ^ index.key)
        if len(e.chunk) == 3:
            chunk += (prefix.decode("latin-1") if isinstance(e.chunk[2], str) else prefix,)
        chunks[e.name] = chunk
        out.extend(new[len(prefix):])
        cursor = e.offset + e.length - len(e.prefix)
    out.extend(data[cursor:index.offset])
    if changed:
        offset = len(out)
        mapping = {e.raw_name: [chunks[e.name]] for e in index.entries}
        out.extend(zlib.compress(pickle.dumps(mapping, protocol=3)))
        out[8:24] = f"{offset:016x}".encode("ascii")
    else:
        out.extend(data[index.offset:])
    result = bytes(out)
    check = extract(result)
    if {e.name: e.data for e in check} != {e.name: replacements.get(e.name, read_entry(stream, e)) for e in index.entries}:
        raise ValueError("RPA rebuilt members differ")
    return result
