"""Non-executing symbolic Pickle reader for compiled Ren'Py ASTs.

GLOBAL, NEWOBJ, REDUCE and BUILD are represented as inert records, never
imported, instantiated or called. No pickle.loads, Unpickler or game modules.
Memo aliases/cycles are explicit graph edges. Editing a string preserves its
old memo value (old push, memo writes, POP, new push), so other uses survive.
"""
from dataclasses import dataclass, field
import hashlib
import io
import json
import pickletools
import struct


@dataclass(eq=False)
class Value:
    kind: str
    data: object


@dataclass(eq=False)
class Ref:
    value: Value
    site: int


@dataclass
class Program:
    raw: bytes
    root: Ref
    operations: list
    objects: list = field(default_factory=list)


def parse(raw, *, max_bytes=32 << 20, max_ops=2_000_000, max_stack=100_000, max_memo=500_000):
    if not isinstance(raw, bytes) or len(raw) > max_bytes:
        raise ValueError("RPYC pickle byte budget exceeded")
    if raw[:2] not in (b"\x80\x02", b"\x80\x03", b"\x80\x04", b"\x80\x05"):
        raise ValueError("expected RPYC pickle protocol 2..5")
    stream = io.BytesIO(raw)
    stack, memo, operations, objects, marks = [], {}, [], [], []
    frame_end = None

    def push(kind, data, site):
        result = Ref(Value(kind, data), site)
        stack.append(result)
        return result

    def pop():
        if not stack or (marks and len(stack) - 1 == marks[-1]):
            raise ValueError("RPYC pickle stack underflow")
        return stack.pop()

    def marked():
        if not marks:
            raise ValueError("RPYC pickle missing MARK")
        at = marks.pop()
        result = stack[at + 1:]
        del stack[at:]
        return result

    def pairs(target, values):
        if target.value.kind == "object":
            payload = target.value.data.setdefault("items", Ref(Value("dict", {}), target.site))
            return pairs(payload, values)
        if target.value.kind != "dict" or len(values) % 2:
            raise ValueError(f"RPYC pickle dictionary shape: {target.value.kind} {class_name(target.value)} at {stream.tell()}")
        for i in range(0, len(values), 2):
            key = scalar(values[i])
            if type(key) not in (str, int, bytes, type(None)) or key in target.value.data:
                raise ValueError("RPYC duplicate/unsupported dictionary key")
            target.value.data[key] = values[i + 1]

    allowed = {"PROTO", "FRAME", "STOP", "MARK", "NONE", "NEWTRUE", "NEWFALSE", "BININT", "BININT1", "BININT2",
               "LONG1", "LONG4", "BINFLOAT", "BINUNICODE", "SHORT_BINUNICODE", "BINUNICODE8", "BINBYTES",
               "SHORT_BINBYTES", "BINBYTES8", "EMPTY_DICT", "EMPTY_LIST", "EMPTY_TUPLE", "EMPTY_SET", "TUPLE",
               "TUPLE1", "TUPLE2", "TUPLE3", "LIST", "DICT", "FROZENSET", "SETITEM", "SETITEMS", "APPEND",
               "APPENDS", "ADDITEMS", "BINPUT", "LONG_BINPUT", "MEMOIZE", "BINGET", "LONG_BINGET", "GLOBAL",
               "STACK_GLOBAL", "NEWOBJ", "NEWOBJ_EX", "REDUCE", "BUILD", "POP", "DUP"}
    try:
        while stream.tell() < len(raw):
            at = stream.tell()
            code = stream.read(1)
            op = pickletools.code2op.get(chr(code[0]))
            if op is None or op.name not in allowed:
                raise ValueError(f"unsupported RPYC pickle opcode at {at}")
            name = op.name
            arg = op.arg.reader(stream) if op.arg is not None else None
            end = stream.tell()
            if frame_end == at:
                frame_end = None
            if name == "FRAME":
                if frame_end is not None or end + arg > len(raw):
                    raise ValueError("RPYC pickle frame outside bounds/nested")
                frame_end = end + arg
            elif frame_end is not None and (end > frame_end or (name == "STOP" and end != frame_end)):
                raise ValueError("RPYC pickle opcode crosses frame boundary")
            operations.append((at, end, name))
            if len(operations) > max_ops:
                raise ValueError("RPYC pickle opcode budget exceeded")
            if name == "PROTO":
                if at != 0 or arg not in (2, 3, 4, 5):
                    raise ValueError("unsupported RPYC pickle protocol")
            elif name == "FRAME":
                continue
            elif name == "STOP":
                if marks or len(stack) != 1 or end != len(raw):
                    raise ValueError("RPYC pickle trailing bytes/stack mismatch")
                return Program(raw, stack[0], operations, objects)
            elif name == "MARK":
                if len(marks) >= 256:
                    raise ValueError("RPYC pickle MARK nesting budget")
                marks.append(len(stack))
                stack.append(None)
            elif name in ("NONE", "NEWTRUE", "NEWFALSE"):
                push("scalar", {"NONE": None, "NEWTRUE": True, "NEWFALSE": False}[name], at)
            elif name in ("BININT", "BININT1", "BININT2", "LONG1", "LONG4", "BINFLOAT"):
                if isinstance(arg, int) and arg.bit_length() > 4096:
                    raise ValueError("RPYC integer budget")
                push("scalar", arg, at)
            elif name in ("BINUNICODE", "SHORT_BINUNICODE", "BINUNICODE8"):
                push("str", arg, at)
            elif name in ("BINBYTES", "SHORT_BINBYTES", "BINBYTES8"):
                push("bytes", arg, at)
            elif name.startswith("EMPTY_"):
                kind = name[6:].lower()
                push(kind, {} if kind == "dict" else [], at)
            elif name in ("TUPLE", "LIST", "DICT", "FROZENSET"):
                items = marked()
                result = push(name.lower(), {} if name == "DICT" else items, at)
                if name == "DICT":
                    pairs(result, items)
            elif name in ("TUPLE1", "TUPLE2", "TUPLE3"):
                items = [pop() for _ in range(int(name[-1]))][::-1]
                push("tuple", items, at)
            elif name in ("SETITEM", "SETITEMS"):
                values = marked() if name == "SETITEMS" else [pop(), pop()][::-1]
                if not stack or stack[-1] is None:
                    raise ValueError("RPYC dictionary target missing")
                pairs(stack[-1], values)
            elif name in ("APPEND", "APPENDS", "ADDITEMS"):
                values = [pop()] if name == "APPEND" else marked()
                expected = "set" if name == "ADDITEMS" else "list"
                if not stack or stack[-1] is None:
                    raise ValueError("RPYC list/set target missing")
                target = stack[-1]
                if target.value.kind == "object":
                    target = target.value.data.setdefault("items", Ref(Value(expected, []), target.site))
                if target.value.kind != expected:
                    raise ValueError("RPYC list/set target type mismatch")
                target.value.data.extend(values)
            elif name in ("BINPUT", "LONG_BINPUT", "MEMOIZE"):
                key = len(memo) if name == "MEMOIZE" else arg
                if not 0 <= key < max_memo or key in memo or not stack or stack[-1] is None:
                    raise ValueError("RPYC invalid memo write")
                memo[key] = stack[-1].value
            elif name in ("BINGET", "LONG_BINGET"):
                if arg not in memo:
                    raise ValueError("RPYC missing memo entry")
                stack.append(Ref(memo[arg], at))
            elif name in ("GLOBAL", "STACK_GLOBAL"):
                if name == "GLOBAL":
                    module, symbol = arg.split(" ", 1)
                else:
                    symbol, module = scalar(pop()), scalar(pop())
                if not isinstance(module, str) or not isinstance(symbol, str):
                    raise ValueError("RPYC global identifiers must be strings")
                push("global", (module, symbol), at)
            elif name in ("NEWOBJ", "NEWOBJ_EX", "REDUCE"):
                kwargs = pop() if name == "NEWOBJ_EX" else None
                args, cls = pop(), pop()
                if args.value.kind != "tuple":
                    raise ValueError("RPYC symbolic constructor args must be tuple")
                result = push("object", {"operation": name, "class": cls, "args": args, "kwargs": kwargs, "state": None}, at)
                objects.append(result.value)
            elif name == "BUILD":
                state = pop()
                if not stack or stack[-1] is None or stack[-1].value.kind != "object" or stack[-1].value.data["state"] is not None:
                    raise ValueError("RPYC invalid symbolic BUILD")
                stack[-1].value.data["state"] = state
            elif name == "POP":
                pop()
            elif name == "DUP":
                value = pop()
                stack.extend((value, Ref(value.value, at)))
            if len(stack) > max_stack:
                raise ValueError("RPYC stack budget exceeded")
    except (IndexError, KeyError, TypeError, struct.error, UnicodeError) as exc:
        raise ValueError(f"malformed symbolic RPYC pickle: {exc}") from exc
    raise ValueError("RPYC pickle has no STOP")


def scalar(ref):
    if ref is None:
        return None
    if ref.value.kind not in ("str", "bytes", "scalar"):
        raise ValueError("expected primitive RPYC value")
    return ref.value.data


def class_name(value):
    if value.kind != "object":
        return None
    cls = value.data["class"].value
    return cls.data if cls.kind == "global" else None


def attributes(value):
    """Return inert __dict__/slot state; never invoke game __setstate__."""
    state = value.data["state"] if value.kind == "object" else None
    if state is None:
        return {}
    if state.value.kind == "dict":
        return state.value.data
    if state.value.kind == "tuple" and len(state.value.data) == 2:
        out = {}
        for part in state.value.data:
            if part.value.kind == "dict":
                if out.keys() & part.value.data.keys():
                    raise ValueError("RPYC duplicate instance/slot attribute")
                out.update(part.value.data)
            elif scalar(part) is not None:
                raise ValueError("unsupported RPYC instance state")
        return out
    return {}  # e.g. PyCode has a separate positional state; never interpreted as attributes.


def graph_digest(program, replacements=None):
    """Canonical reachable graph, including opaque code and all non-text fields."""
    replacements = replacements or {}
    queue, ids = [], {}

    def edge(ref):
        if ref is None:
            return None
        value = ref.value
        if value.kind in ("str", "bytes", "scalar", "global"):
            data = replacements.get(ref.site, value.data) if value.kind == "str" else value.data
            if isinstance(data, bytes):
                data = data.hex()
            return [value.kind, data]
        key = id(value)
        if key not in ids:
            ids[key] = len(queue)
            queue.append(value)
        return ["ref", ids[key]]

    digest = hashlib.sha256()
    digest.update(json.dumps(edge(program.root), ensure_ascii=True).encode())
    at = 0
    while at < len(queue):
        value = queue[at]
        if value.kind == "dict":
            data = [[type(k).__name__, k.hex() if isinstance(k, bytes) else k, edge(v)] for k, v in value.data.items()]
        elif value.kind == "object":
            data = [value.data["operation"], *[edge(value.data.get(k)) for k in ("class", "args", "kwargs", "state", "items")]]
        else:
            data = [edge(v) for v in value.data]
        digest.update(json.dumps([value.kind, data], ensure_ascii=True, separators=(",", ":")).encode())
        at += 1
        if len(queue) > 500_000:
            raise ValueError("RPYC graph traversal budget exceeded")
    return digest.hexdigest()


def rewrite(program, replacements):
    """Edit known string push sites, preserving memo values and opaque operations."""
    if not replacements:
        # Identity still walks the opcode stream, preserving original frames.
        return b"".join(program.raw[a:b] for a, b, _ in program.operations)
    indices = {at: i for i, (at, _, _) in enumerate(program.operations)}
    insertions = {}
    for site, text in replacements.items():
        if site not in indices or not isinstance(text, str):
            raise ValueError("unknown RPYC string edit site")
        i = indices[site]
        if program.operations[i][2] not in ("BINUNICODE", "SHORT_BINUNICODE", "BINUNICODE8", "BINGET", "LONG_BINGET"):
            raise ValueError("RPYC edit is not a string push/reference")
        j = i + 1
        while j < len(program.operations) and program.operations[j][2] in ("MEMOIZE", "BINPUT", "LONG_BINPUT", "FRAME"):
            j += 1
        raw = text.encode("utf-8", "strict")
        # POP removes only the live value; previously memoized original stays.
        insertions[j - 1] = b"0X" + struct.pack("<I", len(raw)) + raw
    out = bytearray()
    for i, (a, b, name) in enumerate(program.operations):
        if name != "FRAME":
            out.extend(program.raw[a:b])
        if i in insertions:
            out.extend(insertions[i])
    result = bytes(out)
    check = parse(result)
    if graph_digest(program, replacements) != graph_digest(check):
        raise ValueError("RPYC rewritten object graph differs outside requested strings")
    return result
