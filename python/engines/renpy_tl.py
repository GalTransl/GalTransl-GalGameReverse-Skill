"""New Ren'Py translation language (game/tl/<lang>/*.rpy) from inert RPYC2 ASTs.

Dialogue identifiers are read only from compiled ``Translate`` /
``TranslateSay`` nodes of the default (None) language; they are never
recomputed from hashes. A Say without such a node is refused. Menu captions
become ``translate <lang> strings`` old/new pairs. The written layout follows
Ren'Py 8 translation/generation.py (MIT, Copyright Tom Rothamel): UTF-8 BOM,
``translate <lang> <identifier with '.'->'_'>:`` blocks, say code
``who attrs @ temp "what" [nointeract] [with expr]``, strings old/new as
Python literals. ``parse`` reads such files back without executing anything.
"""
import re

from . import renpy as source
from . import renpy_rpyc as rpyc
from .renpy_pickle import attributes, class_name, scalar

PROFILE = "renpy-tl-new-v1"
BOM = chr(0xFEFF)
_IDENT = re.compile(r"\w+")
_IMAGE_WORD = re.compile(r"-?[-0-9a-zA-Z_\u00a0-\ufffd]+")


class MissingIdentifier(ValueError):
    """A dialogue node has no compiled translation identifier."""


def _strings(ref, where):
    if ref is None or ref.value.kind == "scalar" and ref.value.data is None:
        return None
    if ref.value.kind not in ("tuple", "list"):
        raise ValueError(f"{where}: unsupported say attribute container")
    values = [scalar(v) for v in ref.value.data]
    if not all(isinstance(v, str) and _IMAGE_WORD.fullmatch(v) for v in values):
        raise ValueError(f"{where}: unsupported say attribute {values!r}")
    return values


def speaker_ok(who):
    """A variable name or one plain string literal (``"Name" "what"`` form)."""
    if not isinstance(who, str):
        return False
    if source._WORD.fullmatch(who):
        return who not in source._RESERVED or who in source.BUILTIN_SPEAKERS
    try:
        tokens = source._lex(who)
        return (len(tokens) == 1 and tokens[0].quote in "'\"" and tokens[0].start == 0 and tokens[0].end == len(who)
                and isinstance(source.python_value(tokens[0]), str))
    except ValueError:
        return False


def literal_speaker(who):
    return source.python_value(source._lex(who)[0]) if who and who[0] in "'\"" else None


def say_fields(value, where):
    """Inert Say/TranslateSay fields needed to restate the statement."""
    attrs = attributes(value)
    arguments = attrs.get("arguments")
    if arguments is not None and not (arguments.value.kind == "scalar" and arguments.value.data is None):
        raise ValueError(f"{where}: say arguments are not supported by the tl writer")
    who = rpyc.expression(attrs.get("who"))
    what = scalar(attrs.get("what"))
    with_ = rpyc.expression(attrs.get("with_"))
    interact = scalar(attrs.get("interact")) if "interact" in attrs else True
    if who is not None and not speaker_ok(who):
        raise ValueError(f"{where}: speaker expression {who!r} is not a simple variable or string literal")
    if not isinstance(what, str):
        raise ValueError(f"{where}: say text is not a Unicode string")
    if with_ is not None and (not isinstance(with_, str) or not with_.strip() or "\n" in with_ or "#" in with_):
        raise ValueError(f"{where}: unsupported with clause {with_!r}")
    if type(interact) is not bool:
        raise ValueError(f"{where}: unsupported interact flag")
    return {"who": who, "attributes": _strings(attrs.get("attributes"), where),
            "temporary_attributes": _strings(attrs.get("temporary_attributes"), where),
            "what": what, "with": with_.strip() if with_ else None, "interact": interact}


def say_code(fields, what):
    parts = []
    if fields["who"]:
        parts.append(fields["who"])
    parts.extend(fields["attributes"] or ())
    if fields["temporary_attributes"]:
        parts.append("@")
        parts.extend(fields["temporary_attributes"])
    parts.append('"' + source.encode_say(what) + '"')
    if not fields["interact"]:
        parts.append("nointeract")
    if fields["with"]:
        parts.extend(("with", fields["with"]))
    return " ".join(parts)


def plan(script, *, filename):
    """Ordered translate blocks and menu strings of the default language.

    Raises MissingIdentifier when any Say lacks a compiled identifier.
    """
    rpyc.text_records(script)  # Both slots must agree before generating.
    program = script.slots[max(script.slots)]
    wrapped, blocks, strings = set(), [], []
    for value in program.objects:
        cls = class_name(value)
        if cls == ("renpy.ast", "Translate"):
            attrs = attributes(value)
            block = attrs["block"].value
            if block.kind != "list":
                raise ValueError(f"{filename}: unsupported Translate block")
            wrapped.update(id(child.value) for child in block.data)
    for value in program.objects:
        cls = class_name(value)
        if cls is None or cls[0] != "renpy.ast":
            continue
        attrs = attributes(value)
        line = scalar(attrs.get("linenumber"))
        origin = scalar(attrs.get("filename"))
        where = f"{filename}:{line}"
        if cls[1] in ("Translate", "TranslateSay"):
            if scalar(attrs.get("language")) is not None:
                continue
            identifier = scalar(attrs.get("identifier"))
            if not isinstance(identifier, str) or not _IDENT.fullmatch(identifier.replace(".", "_")):
                raise MissingIdentifier(f"{where}: missing/unsupported translation identifier {identifier!r}")
            if cls[1] == "TranslateSay":
                items = [{"kind": "say", **say_fields(value, where)}]
            else:
                items = []
                for child in attrs["block"].value.data:
                    kind = class_name(child.value)
                    cattrs = attributes(child.value)
                    if kind == ("renpy.ast", "Say"):
                        items.append({"kind": "say", **say_fields(child.value, where)})
                    elif kind == ("renpy.ast", "UserStatement"):
                        code = scalar(cattrs.get("line"))
                        if not isinstance(code, str) or not code.strip() or "\n" in code:
                            raise ValueError(f"{where}: unsupported statement in translate block")
                        items.append({"kind": "line", "code": code.strip()})
                    elif kind == ("renpy.ast", "Pass"):
                        items.append({"kind": "line", "code": "pass"})
                    else:
                        raise ValueError(f"{where}: unsupported {kind} in translate block")
            says = [i for i in items if i["kind"] == "say"]
            if not says or all(not i["what"] for i in says):
                continue  # Nothing displayable; the default block keeps running.
            blocks.append({"type": "block", "identifier": identifier, "source": origin, "line": line, "items": items})
        elif cls[1] == "Say" and id(value) not in wrapped:
            raise MissingIdentifier(f"{where}: Say has no compiled Translate identifier; "
                                    "this RPYC cannot produce identifier-based tl blocks")
        elif cls[1] == "Menu":
            items = attrs["items"].value
            for item in items.data:
                label = scalar(item.value.data[0])
                if isinstance(label, str) and label:
                    strings.append({"type": "string", "old": label, "source": origin, "line": line})
    entries = sorted(blocks + strings, key=lambda e: (e["line"], e["type"] == "string"))
    return entries


def rows(entries, names, seen_strings):
    """GalTransl rows and locators; strings already used elsewhere are skipped.

    Ren'Py rejects a second translation of the same ``old`` in one language,
    so a menu caption is exported once, at its first occurrence.
    """
    out, locators, kept = [], [], []
    for entry in entries:
        if entry["type"] == "string":
            if entry["old"] in seen_strings:
                continue
            seen_strings.add(entry["old"])
            entry = dict(entry, row=len(out))
            out.append({"message": entry["old"]})
            locators.append({"kind": "string", "source": entry["source"], "line": entry["line"]})
            kept.append(entry)
            continue
        items = []
        for index, item in enumerate(entry["items"]):
            if item["kind"] == "say" and item["what"]:
                item = dict(item, row=len(out))
                name = (names.get(item["who"]) or literal_speaker(item["who"])) if item["who"] else None
                out.append({"name": name, "message": item["what"]} if isinstance(name, str) else {"message": item["what"]})
                locators.append({"kind": "say", "identifier": entry["identifier"], "item": index,
                                 "source": entry["source"], "line": entry["line"], "speaker": item["who"]})
            items.append(item)
        kept.append(dict(entry, items=items))
    return out, locators, kept


def render(language, entries, messages):
    """tl/<language> file text (with BOM) for planned entries and row texts."""
    if not source._WORD.fullmatch(language) or language == "None":
        raise ValueError("translation language must be a Ren'Py name other than None")
    lines = [BOM + "# Generated from compiled Ren'Py script; identifiers copied from Translate nodes.", ""]
    strings = []
    for entry in entries:
        if entry["type"] == "string":
            strings.append(entry)
            continue
        lines.append(f"# {entry['source']}:{entry['line']}")
        lines.append(f"translate {language} {entry['identifier'].replace('.', '_')}:")
        lines.append("")
        for item in entry["items"]:
            lines.append("    # " + (say_code(item, item["what"]) if item["kind"] == "say" else item["code"]))
        for item in entry["items"]:
            if item["kind"] == "say":
                lines.append("    " + say_code(item, messages[item["row"]] if "row" in item else item["what"]))
            else:
                lines.append("    " + item["code"])
        lines.append("")
    if strings:
        lines.extend((f"translate {language} strings:", ""))
        for entry in strings:
            lines.append(f"    # {entry['source']}:{entry['line']}")
            lines.append('    old "' + source.encode_python(entry["old"]) + '"')
            lines.append('    new "' + source.encode_python(messages[entry["row"]]) + '"')
            lines.append("")
    return "\n".join(lines) + "\n"


def parse(text):
    """Read a generated-style tl file: blocks, says, verbatim lines and strings.

    Bounded line grammar; Python/style translate blocks are kept opaque.
    """
    if text.startswith(BOM):
        text = text[1:]
    result, current = [], None
    for number, raw in enumerate(text.split("\n"), 1):
        line = raw.rstrip("\r")
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not line[0].isspace():
            tokens = source._lex(line)
            words = [t.value for t in tokens]
            if len(words) != 4 or words[0] != "translate" or words[3] != ":" or any(t.quote for t in tokens):
                raise ValueError(f"tl line {number}: expected a translate statement")
            if words[2] == "strings":
                current = {"type": "strings", "language": words[1], "pairs": [], "pending": None}
            elif words[2] in ("python", "style"):
                current = {"type": words[2], "language": words[1], "lines": []}
            elif _IDENT.fullmatch(words[2]):
                current = {"type": "block", "language": words[1], "identifier": words[2], "items": []}
            else:
                raise ValueError(f"tl line {number}: bad translate identifier")
            result.append(current)
            continue
        if current is None or not line.startswith("    "):
            raise ValueError(f"tl line {number}: statement outside a translate block")
        if current["type"] in ("python", "style"):
            current["lines"].append(line[4:])
            continue
        tokens = source._lex(stripped)
        if current["type"] == "strings":
            if len(tokens) != 2 or tokens[0].value not in ("old", "new") or not tokens[1].quote:
                raise ValueError(f"tl line {number}: expected old/new string")
            value = source.python_value(tokens[1])
            if tokens[0].value == "old":
                if current["pending"] is not None:
                    raise ValueError(f"tl line {number}: old without new")
                current["pending"] = value
            else:
                if current["pending"] is None:
                    raise ValueError(f"tl line {number}: new without old")
                current["pairs"].append((current["pending"], value))
                current["pending"] = None
            continue
        say = source._say(tokens)
        if say is not None and (not say[0] or say[0][0].value not in source._RESERVED
                                or say[0][0].value in source.BUILTIN_SPEAKERS):
            prefix, what = say
            if what.unknown_escape:
                raise ValueError(f"tl line {number}: unknown escape in say string")
            literal = prefix[0].quote + prefix[0].raw + prefix[0].quote if prefix and prefix[0].quote else None
            head = ([literal] + stripped[prefix[0].end:what.start].split()) if literal else stripped[:what.start].split()
            temporary = None
            if "@" in head:
                at = head.index("@")
                head, temporary = head[:at], head[at + 1:]
            who = head[0] if head else None
            rest = stripped[what.end:].split(None, 1)
            interact = True
            if rest and rest[0] == "nointeract":
                interact = False
                rest = rest[1].split(None, 1) if len(rest) > 1 else []
            with_ = None
            if rest:
                if rest[0] != "with" or len(rest) != 2:
                    raise ValueError(f"tl line {number}: unsupported say clause")
                with_ = rest[1].strip()
            current["items"].append({"kind": "say", "who": who, "attributes": head[1:] or None,
                                     "temporary_attributes": temporary, "what": what.value,
                                     "with": with_, "interact": interact})
        else:
            current["items"].append({"kind": "line", "code": stripped})
    for block in result:
        if block["type"] == "strings" and block.pop("pending") is not None:
            raise ValueError("tl strings block ends with old without new")
    return result


def expected(language, entries, messages):
    """The parse() result that render() must produce."""
    out, pairs = [], []
    for entry in entries:
        if entry["type"] == "string":
            pairs.append((entry["old"], messages[entry["row"]]))
            continue
        items = []
        for item in entry["items"]:
            if item["kind"] == "say":
                items.append({"kind": "say", "who": item["who"] or None, "attributes": item["attributes"] or None,
                              "temporary_attributes": item["temporary_attributes"] or None,
                              "what": messages[item["row"]] if "row" in item else item["what"],
                              "with": item["with"], "interact": item["interact"]})
            else:
                items.append({"kind": "line", "code": item["code"]})
        out.append({"type": "block", "language": language,
                    "identifier": entry["identifier"].replace(".", "_"), "items": items})
    if pairs:
        out.append({"type": "strings", "language": language, "pairs": pairs})
    return out


def verify(text, language, entries, messages, *, filename):
    """Read back with this module and with the generic .rpy lexer."""
    if parse(text) != expected(language, entries, messages):
        raise ValueError(f"{filename}: tl read-back differs")
    speakers = sorted({i["who"] for e in entries if e["type"] == "block" for i in e["items"]
                       if i["kind"] == "say" and i["who"] and i["who"] not in source.BUILTIN_SPEAKERS
                       and source._WORD.fullmatch(i["who"])})
    found = [t.text for t in source.extract(text[1:] if text.startswith(BOM) else text,
                                            filename=filename, speakers=speakers)]
    want = [i["what"] for b in expected(language, entries, messages) if b["type"] == "block"
            for i in b["items"] if i["kind"] == "say"]
    want += [new for b in expected(language, entries, messages) if b["type"] == "strings" for _, new in b["pairs"]]
    if found != want:
        raise ValueError(f"{filename}: generic rpy lexer read-back differs")


def font_script(language, font):
    """Optional ``translate <lang> python`` block assigning GUI fonts."""
    if (not isinstance(font, str) or not re.fullmatch(r"[^\"'\\\x00-\x1f]+\.(?:ttf|otf|ttc)", font, re.I)
            or font.startswith("/") or ".." in font.split("/")):
        raise ValueError("font must be a relative game path to .ttf/.otf/.ttc without quotes")
    body = "\n".join(f'    gui.{name} = "{font}"' for name in ("text_font", "name_text_font", "interface_text_font"))
    return f"{BOM}# GUI fonts for this language; requires a gui-based project.\ntranslate {language} python:\n{body}\n"
