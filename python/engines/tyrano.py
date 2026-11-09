"""TyranoScript scenario (.ks) dialogue: export rows and write them back in place.

New implementation for this skill. Line handling mirrors TyranoScript's
``parseScenario``/``makeTag`` (ShikemokuMK/tyranoscript, MIT): each line is
split on LF and JavaScript-trimmed, then dispatched on its first character
(``;`` comment, ``#`` speaker, ``*`` label, ``@`` command, ``_`` keeps leading
blanks, otherwise text with ``[tag]`` runs). Whole-line ``/*`` ... ``*/`` is a
block comment; after ``iscript`` brackets are literal until a line mentions
``endscript``. Text inside ``[iscript]``, ``[html]`` and ``[macro]`` blocks is
code, markup or a template and is never exported.

A row is the text between message breaks (``[p]``, ``[cm]``, ``[er]``, flow
tags, speaker and label lines). Tags between its text pieces (``[l]``,
``[r]``, ``[ruby ...]`` ...) stay in the message as protected literals; the
engine concatenates text lines without inserting a break. Speaker names come
from ``#name[:face]``; when the name is a ``[chara_new]`` key the display name
is its ``jname``. A translated name is written to every ``#`` line using it
and to matching ``jname`` attributes so the engine's jname -> character lookup
keeps working. ``[glink text=...]`` choices are exported as unnamed rows.
"""

from dataclasses import dataclass, field
import re

from python.common.contract import make_manifest, validate_translation

PROFILE = "tyrano-kag/1"
ENCODING = "utf-8"
# String.prototype.trim whitespace (ECMAScript WhiteSpace + LineTerminator).
JS_WS = ("\t\n\v\f\r \u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006"
         "\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff")
# Tags that end the current message; anything else between text pieces is
# kept inside the message as a protected literal.
BREAK_TAGS = frozenset({"p", "cm", "er", "ct", "s", "jump", "call", "return", "glink", "button",
                        "iscript", "endscript", "html", "endhtml", "macro", "endmacro"})
LINE_SPECIAL = "#*@;_"
# makeTag drops ASCII spaces inside quotes and turns '#' into '='.
ATTR_FORBIDDEN = set(" \t\r\n\"'[]#=")
NAME_FORBIDDEN = ATTR_FORBIDDEN | {":"}


class TyranoError(ValueError):
    pass


def js_trim(text: str) -> str:
    return text.strip(JS_WS)


@dataclass
class Piece:
    start: int              # absolute character offset in the script
    end: int
    line_start: bool        # first visible text of its line (no '_' prefix)
    line_end: bool          # nothing but blanks follows on its line


@dataclass
class Tag:
    start: int
    end: int
    name: str
    literal: str


@dataclass
class Message:
    name_key: str | None    # raw '#' value, None for narration
    items: list = field(default_factory=list)   # Piece | Tag in order


@dataclass
class Choice:
    tag: Tag
    value_start: int
    value_end: int
    quote: str


@dataclass
class NameLine:
    start: int
    end: int
    value: str
    face: str | None


@dataclass
class Script:
    text: str
    messages: list
    choices: list
    name_lines: list
    chara_defs: list        # (key, jname, jname_start, jname_end)
    structure: list         # non-text signature for verification
    order: list             # ('m', i) / ('c', i) in document order
    skipped_block_text: int


def _tag_name(tag_str: str) -> str:
    stripped = tag_str.strip()
    return stripped.split()[0] if stripped else ""


_ATTR_RE = re.compile(r"""(?:^|\s)([A-Za-z_][\w-]*)\s*=\s*("[^"]*"|'[^']*'|[^\s"'\]]+)""")


def _attributes(tag: Tag):
    """name -> (value, value_start, value_end, quote) with absolute offsets."""
    inner = tag.literal[1:-1] if tag.literal.startswith("[") else tag.literal[1:]
    result = {}
    for match in _ATTR_RE.finditer(inner):
        raw = match.group(2)
        quote = raw[0] if raw[0] in "\"'" else ""
        start = tag.start + 1 + match.start(2) + (1 if quote else 0)
        value = raw[1:-1] if quote else raw
        result[match.group(1)] = (value, start, start + len(value), quote)
    return result


def _scan_line(content: str, base: int, in_script: bool):
    """Tyrano text-line scan.

    Returns ([('text', start, end, scripted) | Tag], in_script). While a script
    block is open, brackets are literal text, exactly like the engine.
    """
    items = []
    flag_tag, depth, text_start, tag_start = False, 0, 0, 0
    for j, c in enumerate(content):
        if flag_tag:
            if c == "]" and not in_script:
                depth -= 1
                if depth == 0:
                    flag_tag = False
                    literal = content[tag_start:j + 1]
                    tag = Tag(base + tag_start, base + j + 1, _tag_name(literal[1:-1]), literal)
                    items.append(tag)
                    if tag.name == "iscript":
                        in_script = True
                    elif tag.name == "endscript":
                        in_script = False
                    text_start = j + 1
            elif c == "[" and not in_script:
                depth += 1
        elif c == "[" and not in_script:
            depth = 1
            if j > text_start:
                items.append(("text", base + text_start, base + j, in_script))
            flag_tag, tag_start = True, j
    if flag_tag:
        raise TyranoError(f"unclosed tag at offset {base + tag_start}")
    if len(content) > text_start:
        items.append(("text", base + text_start, base + len(content), in_script))
    return items, in_script


def parse(data: bytes) -> Script:
    try:
        text = data.decode(ENCODING)
    except UnicodeError as exc:
        raise TyranoError(f"scenario is not strict UTF-8: {exc}") from exc
    messages, choices, name_lines, chara_defs, structure, order = [], [], [], [], [], []
    current, name_key = None, None
    flag_comment = in_script = False
    block = None            # 'html' / 'macro' while inside such a block
    skipped = 0

    def finish():
        nonlocal current
        if current is not None:
            while current.items and isinstance(current.items[-1], Tag):
                current.items.pop()
            if any(isinstance(item, Piece) for item in current.items):
                order.append(("m", len(messages)))
                messages.append(current)
        current = None

    def handle_tag(tag: Tag, *, in_text_line: bool):
        nonlocal block
        attrs = _attributes(tag)
        signature = tag.literal
        writable = {"chara_new": "jname", "glink": "text"}.get(tag.name)
        if writable in attrs:
            value, start, end, _ = attrs[writable]
            if tag.name == "chara_new" and "name" in attrs:
                chara_defs.append((attrs["name"][0], value, start, end))
            # Translatable attribute values are not part of the structure.
            signature = tag.literal[:start - tag.start] + "\0" + tag.literal[end - tag.start:]
        structure.append(("tag", signature))
        if tag.name in ("html", "macro"):
            finish()
            block = tag.name
            return
        if tag.name in ("endhtml", "endmacro"):
            block = None
            return
        if block:
            return
        if tag.name == "glink" and "text" in attrs:
            finish()
            value, start, end, quote = attrs["text"]
            if value:
                order.append(("c", len(choices)))
                choices.append(Choice(tag, start, end, quote))
            return
        if tag.name in BREAK_TAGS or not in_text_line:
            finish()
        elif current is not None:
            current.items.append(tag)

    pos = 0
    for raw in text.split("\n"):
        line_offset = pos
        pos += len(raw) + 1
        line = js_trim(raw)
        base = line_offset + len(raw) - len(raw.lstrip(JS_WS))
        if "endscript" in line:
            in_script = False
        if flag_comment and line == "*/":
            flag_comment = False
            continue
        if line == "/*":
            flag_comment = True
            continue
        if flag_comment or not line or line.startswith(";"):
            continue
        if line.startswith("#"):
            finish()
            value = js_trim(line[1:])
            key, face = (value.split(":")[0], value.split(":")[1]) if ":" in value else (value, None)
            key = js_trim(key)
            name_key = key or None
            structure.append(("name", face))
            if key and not block and not in_script:
                start = text.index(key, base + 1)
                name_lines.append(NameLine(start, start + len(key), key, face))
            continue
        if line.startswith("*"):
            finish()
            structure.append(("label", line))
            continue
        if line.startswith("@"):
            tag = Tag(base, base + len(line), _tag_name(line[1:]), line)
            handle_tag(tag, in_text_line=False)
            if tag.name == "iscript":
                in_script = True
            elif tag.name == "endscript":
                in_script = False
            continue
        prefixed = line.startswith("_")
        items, in_script = _scan_line(line[1:] if prefixed else line, base + prefixed, in_script)
        for item in items:
            if isinstance(item, Tag):
                handle_tag(item, in_text_line=True)
                continue
            _, start, end, scripted = item
            if block or scripted:
                skipped += 1
                continue
            if current is None:
                current = Message(name_key)
            current.items.append(Piece(start, end, start == base and not prefixed, end == base + len(line)))
    finish()
    if flag_comment:
        raise TyranoError("unterminated /* block comment")
    if in_script:
        raise TyranoError("unterminated [iscript] block")
    if block:
        raise TyranoError(f"unterminated [{block}] block")
    return Script(text, messages, choices, name_lines, chara_defs, structure, order, skipped)


def _message_text(script: Script, message: Message) -> str:
    return "".join(script.text[i.start:i.end] if isinstance(i, Piece) else i.literal for i in message.items)


def display_names(scripts: list[Script]) -> dict[str, str]:
    """chara key -> jname, from every [chara_new] across the given scripts."""
    result = {}
    for script in scripts:
        for key, jname, _, _ in script.chara_defs:
            if result.get(key, jname) != jname:
                raise TyranoError(f"chara key {key!r} has conflicting jname values")
            result[key] = jname
    return result


def export_rows(script: Script, charas: dict[str, str]):
    rows, locators = [], []
    for kind, index in script.order:
        if kind == "m":
            message = script.messages[index]
            row = {}
            if message.name_key:
                row["name"] = charas.get(message.name_key, message.name_key)
            row["message"] = _message_text(script, message)
            tags = [i.literal for i in message.items if isinstance(i, Tag)]
            rows.append(row)
            locators.append({"kind": "message", "index": index, "tags": len(tags)})
        else:
            choice = script.choices[index]
            rows.append({"message": script.text[choice.value_start:choice.value_end]})
            locators.append({"kind": "choice", "index": index, "tag": "glink"})
    return rows, locators


def manifest(path: str, raw: bytes, rows, locators, script: Script) -> dict:
    tokens = []
    for (kind, index), row in zip(script.order, rows):
        if kind == "m":
            literals = [i.literal for i in script.messages[index].items if isinstance(i, Tag)]
            tokens.append(list(dict.fromkeys(literals)))
        else:
            tokens.append([])
    return make_manifest(engine="tyrano", variant=PROFILE, reference="TyranoScript parseScenario (MIT)",
                         sources={path: raw}, rows=rows, locators=locators, encoding=ENCODING,
                         name_policies=["writable" if "name" in r else "absent" for r in rows],
                         protected_tokens=tokens, settings={"profile": PROFILE})


def _split_translation(message: str):
    """Scan a translated message like a non-script text line -> (gaps, tag literals)."""
    gaps, tags, buf, j = [], [], [], 0
    while j < len(message):
        c = message[j]
        if c == "[":
            depth, k = 1, j + 1
            while k < len(message) and depth:
                depth += {"[": 1, "]": -1}.get(message[k], 0)
                k += 1
            if depth:
                raise TyranoError("translation has an unclosed '['")
            gaps.append("".join(buf))
            buf = []
            tags.append(message[j:k])
            j = k
            continue
        buf.append(c)
        j += 1
    gaps.append("".join(buf))
    return gaps, tags


def _check_text(value: str, where: str):
    if "\n" in value or "\r" in value:
        raise TyranoError(f"{where}: translation must not contain line breaks; use the existing [r] tags")
    if "\0" in value:
        raise TyranoError(f"{where}: NUL in translation")


def _escape_line_start(value: str) -> str:
    if value and (value[0] in LINE_SPECIAL or value[0] in JS_WS):
        return "_" + value
    return value


def message_edits(script: Script, message: Message, translated: str, where: str):
    _check_text(translated, where)
    gaps, tags = _split_translation(translated)
    original_tags = [i.literal for i in message.items if isinstance(i, Tag)]
    if tags != original_tags:
        raise TyranoError(f"{where}: inline tags must stay identical and in the same order: {original_tags}")
    if not gaps[0] or not gaps[-1]:
        raise TyranoError(f"{where}: message must start and end with text (tags cannot lead or trail)")
    groups, last_tag = [[]], [None]
    for item in message.items:
        if isinstance(item, Tag):
            groups.append([])
            last_tag.append(item)
        else:
            groups[-1].append(item)
    edits = []
    for gap, pieces, tag in zip(gaps, groups, last_tag):
        stripped = js_trim(gap)
        if stripped in ("/*", "*/"):
            raise TyranoError(f"{where}: translation would form a block-comment line")
        if pieces:
            first = pieces[0]
            value = _escape_line_start(gap) if first.line_start else gap
            if first.line_end and value != value.rstrip(JS_WS):
                raise TyranoError(f"{where}: trailing blanks at line end are trimmed by Tyrano")
            edits.append((first.start, first.end, value))
            edits.extend((p.start, p.end, "") for p in pieces[1:])
        elif gap:
            if script.text[tag.end:tag.end + 1] in ("\n", "\r", "") and gap != gap.rstrip(JS_WS):
                raise TyranoError(f"{where}: trailing blanks at line end are trimmed by Tyrano")
            edits.append((tag.end, tag.end, gap))
    return edits


def _check_name(value: str, where: str):
    if not value or set(value) & NAME_FORBIDDEN or value != js_trim(value):
        raise TyranoError(f"{where}: speaker name must be nonempty without spaces or any of :#=\"'[]")


def name_map(pairs) -> dict[str, str]:
    """Consistent original display name -> translated name over all rows."""
    mapping = {}
    for where, before, after in pairs:
        if mapping.setdefault(before, after) != after:
            raise TyranoError(f"{where}: name {before!r} is translated inconsistently "
                              f"({mapping[before]!r} vs {after!r})")
    return {k: v for k, v in mapping.items() if k != v}


def rebuild(raw: bytes, script: Script, translated_rows, names: dict[str, str],
            charas: dict[str, str], *, label: str) -> bytes:
    """Apply message/choice translations and the global name map to one script."""
    edits = []
    for row_index, ((kind, index), row) in enumerate(zip(script.order, translated_rows)):
        where = f"{label} row {row_index}"
        if kind == "m":
            message = script.messages[index]
            if _message_text(script, message) != row["message"]:
                edits.extend(message_edits(script, message, row["message"], where))
        else:
            choice = script.choices[index]
            value = row["message"]
            if value != script.text[choice.value_start:choice.value_end]:
                if not value or set(value) & ATTR_FORBIDDEN:
                    raise TyranoError(f"{where}: choice text must be nonempty without spaces or any of #=\"'[]")
                edits.append((choice.value_start, choice.value_end, value))
    for line in script.name_lines:
        if line.value in names and line.value not in charas:
            edits.append((line.start, line.end, names[line.value]))
    for _, jname, start, end in script.chara_defs:
        if jname in names:
            edits.append((start, end, names[jname]))
    for after in names.values():
        _check_name(after, label)
    text = script.text
    edits.sort(key=lambda e: (e[0], e[1]))
    for (a_start, a_end, _), (b_start, _, _) in zip(edits, edits[1:]):
        if b_start < a_end:
            raise TyranoError(f"{label}: overlapping edits at offset {b_start}")
    out, cursor = [], 0
    for start, end, value in edits:
        out.append(text[cursor:start])
        out.append(value)
        cursor = end
    out.append(text[cursor:])
    return "".join(out).encode(ENCODING)


def verify(rebuilt: bytes, original: Script, translated_rows, names: dict[str, str],
           charas: dict[str, str], *, label: str) -> None:
    """Re-parse the rebuilt script; rows and non-text structure must match."""
    script = parse(rebuilt)
    renamed = {key: names.get(value, value) for key, value in charas.items()}
    rows, _ = export_rows(script, renamed)
    expected = []
    for row in translated_rows:
        row = dict(row)
        if "name" in row:
            row["name"] = names.get(row["name"], row["name"])
        expected.append(row)
    if rows != expected:
        for i, (a, b) in enumerate(zip(rows, expected)):
            if a != b:
                raise TyranoError(f"{label}: re-parsed row {i} differs from the translation")
        raise TyranoError(f"{label}: re-parsed row count {len(rows)} != {len(expected)}")
    if script.structure != original.structure:
        raise TyranoError(f"{label}: non-text structure changed after writeback")


def validate_rows(manifest_data, sources, original_rows, translated_rows):
    return validate_translation(manifest_data, sources, original_rows, translated_rows)
