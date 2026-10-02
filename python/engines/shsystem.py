"""SHSysSC header and locally bounded scriptcall 0x33 extraction only.

Adapted from VNTextPatch-net8 (MIT), commit
d9c0fab7b72fdcf87d674ef12a84d3829c9188be,
VNTextPatch.Shared/Scripts/ShSystem/ShSystemDisassembler.cs,
TryReadLiteralExpression/SkipExpression/SkipString/SkipList; ShSystemScript.cs,
HandleScriptCall/GetStrings. Upstream WritePatched throws NotImplementedException.
No writer is supplied here either.
"""


class _Reader:
    def __init__(self, data, pos):
        self.data, self.pos = data, pos

    def take(self, n):
        if n < 0 or self.pos < 0 or self.pos + n > len(self.data):
            raise ValueError("truncated SH operand")
        raw = self.data[self.pos:self.pos + n]
        self.pos += n
        return raw

    def byte(self):
        return self.take(1)[0]

    def cstring(self):
        end = self.data.find(b"\0", self.pos)
        if end < 0:
            raise ValueError("unterminated SH string")
        raw = self.take(end - self.pos)
        self.take(1)
        return raw.decode("cp932", "strict")

    def expression(self):
        start = self.pos
        while True:
            tag = self.byte()
            if tag == 255:
                break
            operation, index = tag >> 4, tag & 15
            n = 0
            if operation == 0 and index >= 13:
                n = (1, 2, 4)[index - 13]
            elif operation in (1, 2, 3) and index >= 14:
                n = index - 13
            self.take(n)
        raw = self.data[start:self.pos]
        value = None
        if raw[0] in (13, 14, 15):
            n = (1, 2, 4)[raw[0] - 13]
            if len(raw) == n + 2:
                value = int.from_bytes(raw[1:-1], "big", signed=n == 4)
        return {"kind": "expression", "offset": start, "end": self.pos, "value": value}

    def string(self):
        start = self.pos
        tag = self.byte()
        value = None
        if tag >= 32:
            self.pos -= 1
            value = self.cstring()
            kind = "literal"
        elif tag == 0:
            kind = "empty"
        elif tag < 12:
            self.take(1 if tag < 6 else 2)
            kind = "variable"
        else:
            self.expression()
            kind = "string_expression"
        return {"kind": kind, "offset": start, "end": self.pos, "value": value}


def read_header(data: bytes) -> dict:
    r = _Reader(data, 0)
    if r.take(8) != b"SHSysSC\0":
        raise ValueError("invalid SHSysSC signature")
    size = int.from_bytes(r.take(3), "big")
    if size != len(data):
        raise ValueError("SH 24-bit file size mismatch")
    has_source = r.byte() != 0
    reserved = r.take(4)
    source = r.cstring() if has_source else None
    return {"code_offset": r.pos, "has_source_info": has_source,
            "source": source, "reserved": reserved}


def read_scriptcall(data: bytes, opcode_offset: int) -> dict:
    """Parse one known opcode 0x03 boundary, excluding optional source line u16.

    Returns all argument ranges and a record ONLY for literal script ID 0x33
    with exactly five arguments and a literal string at argument 4.
    Does not discover calls by scanning for bytes 03/33 in arbitrary data.
    """
    r = _Reader(data, opcode_offset)
    if r.byte() != 3:
        raise ValueError("expected SH scriptcall opcode 0x03")
    expr = r.expression()
    args = []
    while True:
        tag = r.byte()
        if tag == 0:
            break
        args.append(r.string() if tag == 1 else r.expression())
    record = None
    if expr["value"] == 0x33 and len(args) == 5 and args[4]["kind"] == "literal":
        text = args[4]["value"].replace("\\n", "\r\n")
        i = text.find("\r\n")
        name = text[:i] if i > 0 else None
        message = text[i + 2:] if i > 0 else text
        record = {"name": name, "message": message.strip(), "offset": args[4]["offset"]}
    return {"script_id": expr["value"], "arguments": tuple(args), "record": record,
            "end": r.pos}
