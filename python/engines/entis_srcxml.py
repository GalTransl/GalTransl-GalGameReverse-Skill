# SPDX-License-Identifier: GPL-3.0-or-later
"""Entis GLS SRCXML engine dialect: lexical reader and span-preserving attribute writer.

Runtime SRCXML is not strict XML: attribute names may start with ``@`` (``@l`` is a
source line number) and numeric references such as ``&#8;`` that XML 1.0 forbids
occur in text. The ElementTree route in ``entis_gls`` rejects such files, so this
module tokenizes tags itself, keeps every byte outside edited attribute values, and
re-escapes edited values in the convention observed in engine-written files:
characters up to U+0020 become ``&#N;`` (spaces are ``&#32;``), ``&`` is ``&amp;``,
``"`` is ``&quot;``, ``<``/``>`` become ``&#60;``/``&#62;``.

Records follow ``entis_gls`` (msg-tool ``SrcXmlScript``, GPL-3.0-or-later):
``xscript/code/msg`` name/text, ``xscript/code/select/menu`` text, plus
``xscript/code/open_line_msg`` title (chat window title, a display string).
Language suffixes (``text_JA``) are selected explicitly when several exist.
New implementation for this skill; no DTD, entity expansion or code execution.
"""

from dataclasses import dataclass
import re

MAX_CHARS = 32 * 1024 * 1024
MAX_ELEMENTS = 1_000_000
MAX_DEPTH = 256
CONTROL = re.compile(r"%(?:fname|fp|name|nck|nick)|\\[^\s]")
VARIABLE_NAME = re.compile(r"%(?:fname|fp|name|nck|nick)")
_NAME = re.compile(r"[A-Za-z_@][\w.\-:@]*")
_ATTR = re.compile(r"[^\s=/>\"'<]+")
_REF = re.compile(r"&(#[0-9]+|#x[0-9A-Fa-f]+|amp|lt|gt|quot|apos);")
_NAMED = {"amp": "&", "lt": "<", "gt": ">", "quot": '"', "apos": "'"}
_DECL_ENCODING = re.compile(r"""encoding\s*=\s*["']([^"']+)["']""")


@dataclass(frozen=True)
class Attribute:
    name: str
    start: int          # value span inside the document (quotes excluded)
    end: int
    value: str          # decoded


class Element:
    __slots__ = ("name", "attrs", "children", "start")

    def __init__(self, name, attrs, start):
        self.name = name
        self.attrs = attrs
        self.children = []
        self.start = start


@dataclass(frozen=True)
class Record:
    index: int
    kind: str           # message | choice | title
    element: str
    line: str | None    # @l source line, when present
    name: str | None
    message: str
    name_attribute: str | None
    text_attribute: str


def _fail(message, pos):
    raise ValueError(f"SRCXML {message} at offset {pos}")


def decode_value(raw, pos=0):
    out = []
    last = 0
    for match in re.finditer(r"&", raw):
        ref = _REF.match(raw, match.start())
        if not ref:
            _fail("unsupported entity or bare '&'", pos + match.start())
        if match.start() < last:
            continue
        out.append(raw[last:match.start()])
        body = ref.group(1)
        if body.startswith("#"):
            code = int(body[2:], 16) if body[1:2] in "xX" else int(body[1:])
            if code == 0 or code > 0x10FFFF or 0xD800 <= code <= 0xDFFF:
                _fail("invalid character reference", pos + match.start())
            out.append(chr(code))
        else:
            out.append(_NAMED[body])
        last = ref.end()
    out.append(raw[last:])
    return "".join(out)


def encode_value(text):
    if not isinstance(text, str):
        raise ValueError("SRCXML value must be str")
    out = []
    for ch in text:
        code = ord(ch)
        if code == 0 or 0xD800 <= code <= 0xDFFF or code in (0xFFFE, 0xFFFF):
            raise ValueError("SRCXML value contains an invalid character")
        if ch in "\r\n":
            raise ValueError("literal line breaks are not allowed; keep the script's own "
                             "line-break sequence")
        if code <= 0x20:
            out.append(f"&#{code};")
        elif ch == "&":
            out.append("&amp;")
        elif ch == '"':
            out.append("&quot;")
        elif ch == "<":
            out.append("&#60;")
        elif ch == ">":
            out.append("&#62;")
        else:
            out.append(ch)
    return "".join(out)


def parse_document(text):
    """Tokenize the whole document and return the single root element."""
    if not isinstance(text, str):
        raise ValueError("SRCXML input must be str")
    if len(text) > MAX_CHARS:
        raise ValueError("SRCXML exceeds size limit")
    pos = 1 if text.startswith("\ufeff") else 0
    n = len(text)
    stack, root, count = [], None, 0
    while pos < n:
        lt = text.find("<", pos)
        segment = text[pos:n if lt < 0 else lt]
        if (not stack and segment.strip()) or ">" in segment:
            _fail("unexpected character data", pos)
        if "&" in segment:
            decode_value(segment, pos)
        if lt < 0:
            break
        pos = lt
        if text.startswith("<?", pos):
            end = text.find("?>", pos + 2)
            if end < 0:
                _fail("unterminated processing instruction", pos)
            body = text[pos + 2:end]
            if body.startswith("xml"):
                if root is not None or stack or text[:pos].strip("\ufeff \t\r\n"):
                    _fail("misplaced XML declaration", pos)
                enc = _DECL_ENCODING.search(body)
                if enc and enc.group(1).lower().replace("_", "-") not in ("utf-8", "utf8"):
                    _fail("declares a non-UTF-8 encoding", pos)
            pos = end + 2
            continue
        if text.startswith("<!--", pos):
            end = text.find("-->", pos + 4)
            if end < 0:
                _fail("unterminated comment", pos)
            pos = end + 3
            continue
        if text.startswith("<!", pos):
            _fail("DTD, entity or CDATA declarations are not accepted", pos)
        if text.startswith("</", pos):
            match = _NAME.match(text, pos + 2)
            if not match:
                _fail("bad closing tag", pos)
            end = match.end()
            while end < n and text[end] in " \t\r\n":
                end += 1
            if end >= n or text[end] != ">":
                _fail("bad closing tag", pos)
            if not stack or stack[-1].name != match.group():
                _fail(f"mismatched closing tag </{match.group()}>", pos)
            stack.pop()
            pos = end + 1
            continue
        match = _NAME.match(text, pos + 1)
        if not match:
            _fail("bad element name", pos)
        element = Element(match.group(), {}, pos)
        count += 1
        if count > MAX_ELEMENTS:
            _fail("element count exceeds limit", pos)
        p = match.end()
        closed = False
        while True:
            q = p
            while q < n and text[q] in " \t\r\n":
                q += 1
            if q >= n:
                _fail("unterminated tag", pos)
            if text.startswith("/>", q):
                closed, p = True, q + 2
                break
            if text[q] == ">":
                p = q + 1
                break
            if q == p:
                _fail("attributes must be separated by whitespace", q)
            name = _ATTR.match(text, q)
            if not name:
                _fail("bad attribute name", q)
            r = name.end()
            while r < n and text[r] in " \t\r\n":
                r += 1
            if r >= n or text[r] != "=":
                _fail("attribute without value", q)
            r += 1
            while r < n and text[r] in " \t\r\n":
                r += 1
            if r >= n or text[r] not in "\"'":
                _fail("unquoted attribute value", r)
            quote = text[r]
            close = text.find(quote, r + 1)
            if close < 0:
                _fail("unterminated attribute value", r)
            raw = text[r + 1:close]
            if "<" in raw:
                _fail("'<' inside attribute value", r)
            if name.group() in element.attrs:
                _fail(f"duplicate attribute {name.group()}", q)
            element.attrs[name.group()] = Attribute(name.group(), r + 1, close,
                                                    decode_value(raw, r + 1))
            p = close + 1
        if stack:
            stack[-1].children.append(element)
        elif root is None:
            root = element
        else:
            _fail("more than one root element", pos)
        if not closed:
            stack.append(element)
            if len(stack) > MAX_DEPTH:
                _fail("nesting exceeds limit", pos)
        pos = p
    if stack:
        _fail(f"unclosed element <{stack[-1].name}>", n)
    if root is None:
        raise ValueError("SRCXML has no root element")
    return root


def _candidates(root):
    if root.name != "xscript":
        raise ValueError("expected xscript root")
    nodes = []
    for code in root.children:
        if code.name != "code":
            continue
        for node in code.children:
            if node.name == "msg":
                nodes.append((node, "message"))
            elif node.name == "select":
                nodes.extend((menu, "choice") for menu in node.children if menu.name == "menu")
            elif node.name == "open_line_msg":
                nodes.append((node, "title"))
    return nodes


def languages(text):
    """Language suffixes present on candidate text attributes ('' = unsuffixed only)."""
    found = set()
    for node, kind in _candidates(parse_document(text)):
        base = "title_" if kind == "title" else "text_"
        found |= {key[len(base):] for key in node.attrs if key.startswith(base)}
    return sorted(found)


def _records(root, language):
    nodes = _candidates(root)
    if language is None:
        langs = set()
        for node, kind in nodes:
            base = "title_" if kind == "title" else "text_"
            langs |= {key[len(base):] for key in node.attrs if key.startswith(base)}
            if kind == "message":
                langs |= {key[5:] for key in node.attrs if key.startswith("name_")}
        if len(langs) > 1:
            raise ValueError(f"multiple languages {sorted(langs)}: select one explicitly")
        language = next(iter(langs), "")
    if not isinstance(language, str) or (language and not re.fullmatch(r"[\w-]+", language)):
        raise ValueError("invalid language suffix")
    suffix = "_" + language if language else ""
    records = []
    for index, (node, kind) in enumerate(nodes):
        text_key = ("title" if kind == "title" else "text") + suffix
        if text_key not in node.attrs:
            raise ValueError(f"missing {text_key} at record {index} (<{node.name}>)")
        name_key = "name" + suffix if kind == "message" and "name" + suffix in node.attrs else None
        line = node.attrs.get("@l")
        records.append((Record(index, kind, node.name, line.value if line else None,
                               node.attrs[name_key].value if name_key else None,
                               node.attrs[text_key].value, name_key, text_key), node))
    return records


def extract_records(text, language=None):
    return tuple(record for record, _ in _records(parse_document(text), language))


def name_policy(record):
    """'writable' for real names, 'context' for engine variables, 'absent' when empty."""
    if record.name_attribute is None or not record.name:
        return "absent"
    return "context" if VARIABLE_NAME.fullmatch(record.name) else "writable"


def protected_tokens(message):
    seen = []
    for token in CONTROL.findall(message):
        if token not in seen:
            seen.append(token)
    return seen


def escape_convention_mismatches(text, language=None):
    """Record attributes whose original spelling differs from ``encode_value``."""
    bad = []
    for record, node in _records(parse_document(text), language):
        for key in (record.text_attribute, record.name_attribute):
            if key is None:
                continue
            attr = node.attrs[key]
            try:
                same = encode_value(attr.value) == text[attr.start:attr.end]
            except ValueError:
                same = False
            if not same:
                bad.append((record.index, key))
    return bad


def patch_records(text, replacements, language=None):
    """Replace message/name values by record index; untouched bytes stay identical.

    ``replacements``: {index: {"message": str, "name": str}}. A value equal to the
    decoded original keeps the original spelling. Names can only be written where
    the attribute exists and is not empty.
    """
    pairs = _records(parse_document(text), language)
    if not isinstance(replacements, dict):
        raise ValueError("replacements must be a dict")
    edits = []
    expected = {}
    for index, change in replacements.items():
        if type(index) is not int or not 0 <= index < len(pairs):
            raise ValueError(f"unknown SRCXML record {index!r}")
        if not isinstance(change, dict) or set(change) - {"message", "name"}:
            raise ValueError("unknown translation field")
        record, node = pairs[index]
        for field, value in change.items():
            if field == "name":
                if record.name_attribute is None or not record.name:
                    raise ValueError(f"record {index} has no writable name")
                key, old = record.name_attribute, record.name
            else:
                key, old = record.text_attribute, record.message
            if value == old:
                continue
            attr = node.attrs[key]
            edits.append((attr.start, attr.end, encode_value(value)))
            expected[(index, field)] = value
    if not edits:
        return text
    edits.sort()
    out, last = [], 0
    for start, end, value in edits:
        out.append(text[last:start])
        out.append(value)
        last = end
    out.append(text[last:])
    result = "".join(out)
    check = extract_records(result, language)
    before = [record for record, _ in pairs]
    if len(check) != len(before):
        raise ValueError("record count changed after patch")
    for old, new in zip(before, check):
        want_message = expected.get((old.index, "message"), old.message)
        want_name = expected.get((old.index, "name"), old.name)
        if (new.kind, new.element, new.message, new.name) != (old.kind, old.element,
                                                              want_message, want_name):
            raise ValueError(f"record {old.index} differs after patch")
    return result
