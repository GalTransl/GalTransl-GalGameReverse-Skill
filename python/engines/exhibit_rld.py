"""ExHibit RLD v3/tag256: complete structural reader and raw-span text writer.

The legacy fragment API remains in exhibit.py. This profile uses the runtime's
offset+4 instruction origin and 0xFFD0 exclusive XOR endpoint. No opcode width
table is needed: operand counts are in each instruction. Only known display
fields are editable; opaque operands and CP932 byte aliases survive unchanged.
"""
from dataclasses import dataclass
from functools import lru_cache
import re
import struct

from ..common.contract import make_manifest, validate_translation
from .exhibit import Op, extract_dialogue, name_table

PROFILE = "rld-v3-tag256/1"
MAX_FILE = 32 << 20


@lru_cache(maxsize=16)
def mt_keys(seed):
    """First 256 outputs of MT19937 with the old 69069 packed-half initializer."""
    if type(seed) is not int or not 0 <= seed <= 0xFFFFFFFF:
        raise ValueError("RLD seed must be u32")
    state, value = [], seed
    for _ in range(624):
        high = value & 0xFFFF0000
        value = (69069 * value + 1) & 0xFFFFFFFF
        state.append(high | (value >> 16))
        value = (69069 * value + 1) & 0xFFFFFFFF
    for i in range(624):
        y = (state[i] & 0x80000000) | (state[(i + 1) % 624] & 0x7FFFFFFF)
        state[i] = state[(i + 397) % 624] ^ (y >> 1) ^ (0x9908B0DF if y & 1 else 0)
    result = []
    for y in state[:256]:
        y ^= y >> 11
        y ^= (y << 7) & 0x9D2C5680
        y ^= (y << 15) & 0xEFC60000
        y ^= y >> 18
        result.append(y)
    return tuple(result)


def crypt(data, seed):
    """Symmetric runtime v3 XOR; seed zero bypasses encryption."""
    if len(data) < 16 or len(data) > MAX_FILE or data[:4] != b"\0DLR":
        raise ValueError("invalid/oversized RLD")
    keys = mt_keys(seed)
    if seed == 0:
        return data
    result = bytearray(data)
    for i, at in enumerate(range(16, min(len(data) // 4 * 4, 0xFFD0), 4)):
        value, = struct.unpack_from("<I", data, at)
        struct.pack_into("<I", result, at, value ^ seed ^ keys[i & 255])
    return bytes(result)


@dataclass(frozen=True)
class Script:
    plain: bytes
    ops: tuple[Op, ...]
    spans: tuple[tuple[tuple[int, int], ...], ...]


def parse(plain):
    if not 276 <= len(plain) <= MAX_FILE or plain[:4] != b"\0DLR":
        raise ValueError("invalid/oversized RLD v3")
    version, offset, count, imports = struct.unpack_from("<4I", plain, 4)
    if version != 3 or offset != 272:
        raise ValueError("unsupported RLD header; expected v3/tag256 offset=272")
    if b"\0" not in plain[20:276]:
        raise ValueError("unterminated RLD tag")
    tag = plain[20:276].split(b"\0", 1)[0].decode("cp932", "strict")
    if imports != (len(tag.split(",")) if tag else 0):
        raise ValueError("RLD import count/tag mismatch (wrong seed or profile)")
    at = offset + 4
    if count > 1_000_000 or count > (len(plain) - at) // 4:
        raise ValueError("RLD command count exceeds bounds")
    ops, spans = [], []
    for index in range(count):
        if at + 4 > len(plain):
            raise ValueError(f"truncated RLD instruction {index}")
        opcode, n, flags = struct.unpack_from("<HBB", plain, at)
        at += 4
        if at + n * 4 > len(plain):
            raise ValueError(f"truncated RLD operands at instruction {index}")
        integers = struct.unpack_from(f"<{n}I", plain, at)
        at += n * 4
        strings, ranges = [], []
        for _ in range(flags & 15):
            end = plain.find(b"\0", at)
            if end < 0:
                raise ValueError(f"unterminated RLD string at instruction {index}")
            strings.append(plain[at:end].decode("cp932", "strict"))
            ranges.append((at, end))
            at = end + 1
        ops.append(Op(opcode, flags & 0xF0, integers, tuple(strings)))
        spans.append(tuple(ranges))
    if at != len(plain):
        raise ValueError(f"RLD has {len(plain) - at} unparsed bytes after declared instructions")
    return Script(plain, tuple(ops), tuple(spans))


def choice_fields(op):
    """Recognize TAB/1010 with 11 text slots; leave other op21 forms explicit."""
    if op.opcode != 21:
        return ()
    if op.integers or op.flags != 0x60 or len(op.strings) != 1:
        raise ValueError("unsupported RLD op21 choice shape")
    fields = op.strings[0].split("\t")
    numeric = list(range(14)) + list(range(25, 29))
    if (len(fields) != 30 or fields[0] != "1010" or fields[-1] != ""
            or any(not re.fullmatch(r"-?[0-9]+", fields[i]) for i in numeric)):
        raise ValueError("unsupported RLD op21 TAB/1010 layout")
    count = int(fields[4])
    if (not 1 <= count <= 11 or any(x != "*" for x in fields[14 + count:25])
            or any(x in ("", "*") for x in fields[14:14 + count])):
        raise ValueError("RLD choice count/slots disagree")
    return tuple(range(14, 14 + count))


def records(script, names=None):
    dialogues = {d.op_index: d for d in extract_dialogue(script.ops, names)}
    result = []
    for index, op in enumerate(script.ops):
        if index in dialogues:
            d = dialogues[index]
            row = {"name": d.names[0]} if d.names else {}
            row["message"] = d.message
            result.append((row, {"op": index, "string": 1, "kind": "dialogue", "name_id": d.name_id},
                           "writable" if d.name_writable and d.names else "context" if d.names else "absent"))
        for field in choice_fields(op):
            result.append(({"message": op.strings[0].split("\t")[field]},
                           {"op": index, "string": 0, "field": field, "kind": "choice"}, "absent"))
    return result


def _check_text(before, after):
    if before == after:
        return
    if "\0" in after:
        raise ValueError("RLD display text contains NUL")
    # This is the plain-display profile, not a guessed escape/markup grammar.
    if any(c in before + after for c in "\\[]{}<>$%"):
        raise ValueError("unclassified RLD display syntax; adapt controls before editing")
    controls = lambda s: tuple(c for c in s if ord(c) < 32)
    if controls(before) != controls(after):
        raise ValueError("RLD display control sequence changed")


def patch(script, recs, rows, codec=None):
    """Replace only display spans, then independently compare all instructions."""
    if len(recs) != len(rows):
        raise ValueError("RLD row count changed")
    changes = {}
    encode = codec.encode if codec is not None else lambda s: s.encode("cp932", "strict")
    for (before, loc, policy), after in zip(recs, rows):
        if set(before) != set(after) or any(not isinstance(v, str) for v in after.values()):
            raise ValueError("RLD row fields/types changed")
        i, j = loc["op"], loc["string"]
        _check_text(before["message"], after["message"])
        if before["message"] != after["message"]:
            if loc["kind"] == "choice":
                if "\t" in after["message"]:
                    raise ValueError("TAB in RLD choice text")
                fields = changes.get((i, j), script.ops[i].strings[j]).split("\t")
                fields[loc["field"]] = after["message"]
                changes[i, j] = "\t".join(fields)
            else:
                changes[i, j] = after["message"]
        if before.get("name") != after.get("name"):
            if policy != "writable":
                raise ValueError("RLD context-only name changed")
            _check_text(before["name"], after["name"])
            if after["name"] == "*" or after["name"].startswith("$"):
                raise ValueError("RLD translated name becomes a sentinel")
            changes[i, 0] = after["name"]
    edits = []
    expected = {}
    for (i, j), value in changes.items():
        if script.ops[i].opcode == 21:
            # Preserve even noncanonical byte aliases in untouched choice slots.
            raw_fields = script.plain[slice(*script.spans[i][j])].split(b"\t")
            old_fields = script.ops[i].strings[j].split("\t")
            raw = b"\t".join(encode(new) if new != old else old_raw
                             for new, old, old_raw in zip(value.split("\t"), old_fields, raw_fields))
        else:
            raw = encode(value)
        if b"\0" in raw:
            raise ValueError("encoded RLD string contains NUL")
        expected[i, j] = raw.decode("cp932", "strict")
        edits.append((*script.spans[i][j], raw))
    out, at = bytearray(), 0
    for start, end, raw in sorted(edits):
        out.extend(script.plain[at:start])
        out.extend(raw)
        at = end
    out.extend(script.plain[at:])
    rebuilt = bytes(out)
    check = parse(rebuilt)
    if rebuilt[:276] != script.plain[:276] or len(check.ops) != len(script.ops):
        raise ValueError("RLD header/count changed")
    for i, (old, new) in enumerate(zip(script.ops, check.ops)):
        if (old.opcode, old.flags, old.integers) != (new.opcode, new.flags, new.integers):
            raise ValueError("RLD non-text instruction data changed")
        if len(new.strings) != len(old.strings):
            raise ValueError("RLD string count changed")
        for j, text in enumerate(new.strings):
            if text != expected.get((i, j), old.strings[j]):
                raise ValueError("RLD stored text reparse mismatch")
            if (i, j) in changes and (codec.display(text) if codec else text) != changes[i, j]:
                raise ValueError("RLD displayed text reparse mismatch")
    return rebuilt


def export_rld(raw, seed, *, filename="script.rld", definitions=None, definition_seed=None):
    if "/" in filename or "\\" in filename:
        raise ValueError("RLD filename must be flat")
    script = parse(crypt(raw, seed))
    sources = {"rld/" + filename: raw}
    names = {}
    if definitions is not None:
        if filename.casefold() == "defchara.rld":
            raise ValueError("definition file cannot depend on itself")
        names = name_table(parse(crypt(definitions, definition_seed)).ops)
        sources["rld/defChara.rld"] = definitions
    recs = records(script, names)
    rows = [r[0] for r in recs]
    manifest = make_manifest(engine="exhibit", variant=PROFILE, reference="python/engines/exhibit_rld.py",
                             sources=sources, rows=rows, encoding="cp932", locators=[r[1] for r in recs],
                             name_policies=[r[2] for r in recs], settings={"seed": seed,
                             "definition_seed": definition_seed if definitions is not None else None},
                             protected_tokens=[list(dict.fromkeys(c for c in r[0]["message"] if ord(c) < 32))
                                               for r in recs])
    return rows, manifest


def rebuild_rld(raw, seed, rows, manifest, *, filename="script.rld", definitions=None,
                definition_seed=None, codec=None):
    original, expected = export_rld(raw, seed, filename=filename, definitions=definitions,
                                    definition_seed=definition_seed)
    if manifest != expected:
        raise ValueError("RLD manifest differs from rederived source metadata")
    sources = {"rld/" + filename: raw}
    names = {}
    if definitions is not None:
        sources["rld/defChara.rld"] = definitions
        names = name_table(parse(crypt(definitions, definition_seed)).ops)
    rows = validate_translation(manifest, sources, original, rows, text_codec=codec)
    script = parse(crypt(raw, seed))
    plain = patch(script, records(script, names), rows, codec)
    result = crypt(plain, seed)
    if crypt(result, seed) != plain:
        raise ValueError("RLD encryption recheck mismatch")
    parse(crypt(result, seed))
    return result
