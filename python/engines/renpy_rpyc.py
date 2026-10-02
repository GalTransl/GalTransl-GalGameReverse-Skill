"""RPYC2 text edits through inert ASTs, without loading Ren'Py or executing Pickle.

Both source and transformed slots must agree on semantic text identities.
Opaque Python, labels, translation lookup keys, and the source MD5 survive.
"""
import ast
from dataclasses import dataclass
import json
import re
import struct
import zlib

from ..common.contract import make_manifest, validate_translation
from . import renpy_pickle as symbolic

PROFILE = "rpyc2-symbolic-v1"
MAGIC = b"RENPY RPC2"
MAX_FILE = 32 << 20


@dataclass
class Script:
    raw: bytes
    slots: dict
    ranges: dict
    table_end: int


def parse(raw):
    if not isinstance(raw, bytes) or len(raw) > MAX_FILE or not raw.startswith(MAGIC):
        raise ValueError("expected bounded RPYC2 script")
    ranges, at = {}, len(MAGIC)
    for _ in range(3):
        if at + 12 > len(raw):
            raise ValueError("truncated RPYC2 slot table")
        slot, offset, size = struct.unpack_from("<III", raw, at)
        table_at = at
        at += 12
        if slot == 0:
            if offset or size:
                raise ValueError("invalid RPYC2 slot terminator")
            break
        if slot not in (1, 2) or slot in ranges or not size:
            raise ValueError("unsupported/duplicate RPYC2 slot")
        ranges[slot] = (offset, size, table_at)
    else:
        raise ValueError("missing RPYC2 slot terminator")
    if 1 not in ranges:
        raise ValueError("RPYC2 source slot missing")
    cursor, slots, total = at, {}, 0
    for slot, (offset, size, _) in sorted(ranges.items(), key=lambda x: x[1][0]):
        if offset < cursor or offset + size > len(raw):
            raise ValueError("RPYC2 slot range overlaps/outside file")
        decoder = zlib.decompressobj()
        try:
            data = decoder.decompress(raw[offset:offset + size], MAX_FILE + 1)
        except zlib.error as exc:
            raise ValueError("invalid RPYC2 zlib slot") from exc
        total += len(data)
        if total > MAX_FILE or not decoder.eof or decoder.unconsumed_tail or decoder.unused_data:
            raise ValueError("RPYC2 zlib budget/truncation/trailing data")
        slots[slot] = symbolic.parse(data)
        root = slots[slot].root.value
        if root.kind != "tuple" or len(root.data) != 2 or root.data[0].value.kind != "dict" or root.data[1].value.kind != "list":
            raise ValueError("unsupported RPYC2 root schema")
        meta = root.data[0].value.data
        if type(symbolic.scalar(meta.get("version"))) is not int or not isinstance(symbolic.scalar(meta.get("key")), str):
            raise ValueError("missing RPYC2 version/key metadata")
        cursor = offset + size
    if len(raw) - cursor != 16:
        raise ValueError("expected RPYC2 source digest suffix")
    return Script(raw, slots, ranges, at)


def rebuild(script, edits):
    if edits.keys() - script.slots.keys():
        raise ValueError("unknown RPYC2 edit slot")
    out, cursor = bytearray(script.raw[:script.table_end]), script.table_end
    for slot, (offset, size, table_at) in sorted(script.ranges.items(), key=lambda x: x[1][0]):
        program = script.slots[slot]
        payload = symbolic.rewrite(program, edits.get(slot, {}))
        # Identity preserves the exact compressor output; the reader/writer has
        # still traversed and reconstructed the complete opcode stream.
        packed = script.raw[offset:offset + size] if payload == program.raw else zlib.compress(payload)
        out.extend(script.raw[cursor:offset])
        struct.pack_into("<III", out, table_at, slot, len(out), len(packed))
        out.extend(packed)
        cursor = offset + size
    out.extend(script.raw[cursor:])
    return bytes(out)


def primitive(ref, depth=0):
    if depth > 16:
        raise ValueError("RPYC node identity nesting/cycle budget exceeded")
    if ref is None:
        return None
    if ref.value.kind == "tuple":
        return [primitive(v, depth + 1) for v in ref.value.data]
    return symbolic.scalar(ref)


def expression(ref):
    if ref is not None and symbolic.class_name(ref.value) == ("renpy.ast", "PyExpr"):
        args = ref.value.data["args"].value
        if args.kind == "tuple" and args.data:
            return symbolic.scalar(args.data[0])
    return symbolic.scalar(ref)


def literal(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (str, type(None))):
        return node.value
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_" and len(node.args) == 1 and not node.keywords:
        return literal(node.args[0])
    raise ValueError("dynamic character name")


def character_names(program):
    """Only statically proven Character declarations; names are read-only context."""
    found = {}
    for value in program.objects:
        if symbolic.class_name(value) != ("renpy.ast", "Define"):
            continue
        attrs = symbolic.attributes(value)
        if symbolic.scalar(attrs.get("store")) != "store" or symbolic.scalar(attrs.get("operator")) != "=":
            continue
        try:
            code = attrs["code"].value
            if symbolic.class_name(code) != ("renpy.ast", "PyCode"):
                continue
            source = expression(code.data["state"].value.data[1])
            if len(source) > 65536:
                continue
            node = ast.parse(source, mode="eval").body
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != "Character" or not node.args:
                continue
            if any(k.arg in (None, "dynamic") for k in node.keywords):
                continue
            name = literal(node.args[0])
            key = symbolic.scalar(attrs["varname"])
            found.setdefault(key, set()).add(name)
        except (ValueError, SyntaxError, KeyError, IndexError, TypeError):
            continue
    return {key: next(iter(values)) for key, values in found.items() if len(values) == 1}


def controls(text):
    """Protect complete tags/interpolations and escapes, including nested indexes.

    This is a conservative delimiter scanner, never an expression evaluator.
    Unknown or unterminated constructs stop changed-text validation.
    """
    tokens, i = [], 0
    while i < len(text):
        ch = text[i]
        if ch == "%":
            match = re.match(r"%(?:%|(?:\([^)]+\))?[#0 +\-]*(?:\d+|\*)?(?:\.(?:\d+|\*))?[hlL]?[diouxXeEfFgGcrsa])", text[i:])
            if match:
                tokens.append(match.group())
                i += len(match.group())
                continue
        if ch not in "{[":
            i += 1
            continue
        start = i
        if text[i:i + 2] in ("{{", "[["):
            tokens.append(text[i:i + 2]); i += 2
            continue
        close = "}" if ch == "{" else "]"
        depth, quote = 1, None
        i += 1
        while i < len(text):
            c = text[i]
            if ch == "[" and quote:
                if c == "\\":
                    i += 2
                    continue
                if text.startswith(quote, i):
                    i += len(quote); quote = None
                    continue
            elif ch == "[" and c in "\"'":
                quote = c * 3 if text.startswith(c * 3, i) else c
                i += len(quote)
                continue
            elif c == ch:
                depth += 1
            elif c == close:
                depth -= 1
                if not depth:
                    i += 1
                    break
            i += 1
        if depth or quote:
            raise ValueError(f"unterminated Ren'Py text control at {start}")
        tokens.append(text[start:i])
    return tokens


def records(program):
    result = {}
    for value in program.objects:
        cls = symbolic.class_name(value)
        if cls not in (("renpy.ast", "Say"), ("renpy.ast", "TranslateSay"), ("renpy.ast", "Menu"), ("renpy.ast", "TranslateString")):
            continue
        attrs = symbolic.attributes(value)
        location = {"filename": symbolic.scalar(attrs.get("filename")),
                    "line": symbolic.scalar(attrs.get("linenumber")), "node": primitive(attrs.get("name"))}
        if not isinstance(location["filename"], str) or type(location["line"]) is not int:
            raise ValueError("RPYC text node has no source location")
        if cls[1] in ("Say", "TranslateSay"):
            targets = [("say", 0, attrs["what"])]
            who = expression(attrs.get("who"))
        elif cls[1] == "TranslateString":
            targets = [("translation-new", 0, attrs["new"])]
            who = None
        else:
            items = attrs["items"].value
            if items.kind != "list":
                raise ValueError("unsupported RPYC menu items")
            targets, who = [], None
            for i, item in enumerate(items.data):
                if item.value.kind != "tuple" or len(item.value.data) != 3:
                    raise ValueError("unsupported RPYC menu item")
                targets.append(("choice", i, item.value.data[0]))
        for role, index, target in targets:
            message = symbolic.scalar(target)
            if not isinstance(message, str):
                raise ValueError("RPYC text must be a Unicode string")
            if not message:
                continue
            locator = dict(location, role=role, item=index, speaker=who)
            key = json.dumps(locator, ensure_ascii=True, sort_keys=True)
            if key in result:
                raise ValueError("ambiguous RPYC text identity")
            result[key] = {"locator": locator, "site": target.site, "message": message}
    return dict(sorted(result.items(), key=lambda kv: (kv[1]["locator"]["filename"], kv[1]["locator"]["line"], kv[1]["locator"]["item"], kv[0])))


def text_records(script):
    slots = {slot: records(program) for slot, program in script.slots.items()}
    base = slots[1]
    for slot, current in slots.items():
        if current.keys() != base.keys() or any(r["message"] != current[k]["message"] for k, r in base.items()):
            raise ValueError(f"RPYC slot {slot} text identities/content differ")
    return base, slots


def export(script, *, filename="script.rpyc", names=None):
    names = names or {}
    base, slots = text_records(script)
    rows, locators = [], []
    for key, rec in base.items():
        who = rec["locator"]["speaker"]
        name = names.get(who)
        if name is None and isinstance(who, str):
            try:
                name = literal(ast.parse(who, mode="eval").body)
            except (SyntaxError, ValueError):
                pass
        row = {"name": name, "message": rec["message"]} if isinstance(name, str) else {"message": rec["message"]}
        rows.append(row)
        locators.append(dict(rec["locator"], sites={str(s): rs[key]["site"] for s, rs in slots.items()}))
    manifest = make_manifest(engine="renpy", variant=PROFILE, reference="python/engines/renpy_rpyc.py",
                             sources={filename: script.raw}, rows=rows, locators=locators, encoding="utf-8",
                             settings={"names": names, "name_policy": "context", "text_scope": "Say/Menu/TranslateString.new"})
    return rows, manifest


def patch(script, rows, manifest, *, filename="script.rpyc", names=None):
    original, expected = export(script, filename=filename, names=names)
    if manifest != expected:
        raise ValueError("RPYC manifest differs from freshly parsed source")
    rows = validate_translation(manifest, {filename: script.raw}, original, rows)
    edits = {slot: {} for slot in script.slots}
    for before, after, record in zip(original, rows, manifest["records"]):
        if before["message"] == after["message"]:
            continue
        if not after["message"] or "\0" in after["message"] or controls(before["message"]) != controls(after["message"]):
            raise ValueError(f"Ren'Py row {record['position']}: empty/NUL text or changed controls")
        for slot, site in record["locator"]["sites"].items():
            if site in edits[int(slot)] and edits[int(slot)][site] != after["message"]:
                raise ValueError("conflicting edits at shared RPYC site")
            edits[int(slot)][site] = after["message"]
    raw = rebuild(script, edits)
    checked = parse(raw)
    if export(checked, filename=filename, names=names)[0] != rows:
        raise ValueError("RPYC read-back text differs")
    return raw
