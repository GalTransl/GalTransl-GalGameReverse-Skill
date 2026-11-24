"""Artemis AST text scripts: the Lua-table scenario dialect (``.ast``).

Artemis releases ship several unrelated script shapes: compiled ``ASB`` trees
(:mod:`python.engines.artemis`), line-oriented SCP text
(:mod:`python.engines.artemis_scp`), and this one - a **plain-text Lua table
dump**. Two topologies of the same dialect are read here.

Named-block layout (``label.top`` present)::

    astver = 2.0                    -- header; also seen: astname = "..." or
    astname = "chapter01"           -- neither, when the file starts at ``ast``
    ast = {
        block_00000 = {             -- quoted keys (["0001_00001"] = {) also occur
            {"savetitle", text="..."},
            {"text"},
            delay = { [1000] = { {"se", id=1, file="se0148"}, }, },
            text = {
                linemode = {},      -- attribute members are kept, never text
                vo = { {"vo", file="fem_shi_00004", ch="shi"}, },
                ja = {
                    {
                        name = {"<identity>", "<display>"},
                        "...", {"ruby", text="..."}, "...", {"/ruby"},
                        "...", {"heroname", mode="fn"}, "...",
                        {"rt2"},
                    },
                },
            },
            linknext = "block_00010",
            line = 150,
        },
        label = { top = { block = "block_00000", label=1 }, },
    }

Positional-block layout (no ``label.top``; blocks are positional tables and
the text lives in one top-level ``text`` table keyed ``[N]``)::

    ast = {
        { {"savetitle", text="..."}, {"text"}, crc="...", lang="...", line=23 },
        { {"select", file="...", text="..."}, ... },
        text = {
            [1] = { vo = {...}, name = { name="<identity>", en="<display>" },
                    ja = { {"...", {"rt2"}} }, en = { {...} } },
            [2] = { select = { ja = {"...", "..."}, en = {...} } },
            [3] = { ja = { name = {"name", name="<display>"}, {"..."} } },
        },
        label = {},
    }

Dialogue is one box per element of the selected language table. Values are
Lua: quoted strings, ``[[long strings]]``, numbers, ``nil``, ``true``/``false``
and tables. A bare identifier (a Lua global reference) is rejected because its
value only exists at run time.

Rendering model
---------------

The engine walks a box in order: strings are printed, tables are executed as
tags. ``{"rt2"}`` ends a rendered line, so a box's text is its literal
fragments joined by a line break; a shipped Chinese patch rewrote
``"A", {"rt2"}, "B", {"rt2"}`` as ``"A\\nB", {"rt2"}``, so ``\\n`` inside a
literal is an equivalent spelling. Every other inline command (``exfont``,
``txkey``, ``heroname``, ``gaiji``, ...) is exported **verbatim as a protected
token** - its exact Lua source - at its position in the message. A
translation must contain the same tokens in the same order; the writer puts
them back between the literals. ``ruby`` furigana cannot follow rewritten
characters: it is dropped on a rewrite and reported through the locator.

Names
-----

* In-box ``name = {"A", "B"}``: slot 0 is the fixed identity, the last slot
  the display name; a lone slot gains an appended display slot. In-box keyed
  ``name = {name="A", ja="B"}`` uses its last key; a lone keyed slot is context.
* Entry-level ``name = {name="A", en="B", ...}`` (positional layout): the
  engine shows ``name[language] or name.name``; ``name`` is the identity. The
  writer replaces the selected language's literal or appends that key.
* Language-level ``name = {"name", name="A"}`` (oldest positional variant,
  inside each language table): shown as ``text or name``; official
  localisations rewrite it per language, so the writer replaces that literal.

Known boundaries: no game startup, no font/glyph work, no container handling,
and no proof that the engine accepts a rewritten file. Escapes are written only
as ``\\n`` unless ``allow_lua_escapes`` is passed, because the shipped patch
proves ``\\n`` is accepted and proves nothing about ``\\\\`` or ``\\"``.
"""

from dataclasses import dataclass, field
import codecs
import dataclasses
import re

#: Header statements accepted before ``ast = {``.
HEADER_KEYS = ("astver", "astname")
#: ``astver`` values this module claims to handle.
SUPPORTED_VERSIONS = ("2.0",)
#: Tags that terminate a rendered line (msg-tool maps both to a newline).
LINE_BREAK_TAGS = frozenset({"rt2", "ret2"})
#: Inline commands kept verbatim as protected tokens. ``heroname`` prints the
#: player-entered name and ``gaiji`` prints its ``text`` in the gaiji font;
#: neither carries translatable text. Extend via ``extra_inline_tags``.
INLINE_TAGS = frozenset({"exfont", "txkey", "txruby", "heroname", "gaiji"})
#: ``text``/``select`` members that are never the language table.
NON_LANGUAGE_KEYS = re.compile(r"(?:vo|vl\d+|lv\d+)\Z")
#: Every protected token starts with this; plain text may not contain it.
TOKEN_MARK = '{"'
_SPACE = " \t\r\n"
_PUNCT = "{}()[],="
_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?\Z")
_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_DIGITS_RE = re.compile(r"\d{1,3}")
_HEX_RE = re.compile(r"u\{([0-9a-fA-F]{1,6})\}|u([0-9a-fA-F]{4})|x([0-9a-fA-F]{2})")
_SCALARS = ("str", "int", "float", "bool", "null")


class AstError(ValueError):
    """Rejected script or translation, with a machine-readable code and stage."""

    def __init__(self, code: str, message: str, stage: str = "parse"):
        super().__init__(message)
        self.code = code
        self.stage = stage


# --------------------------------------------------------------------- lexer


@dataclass(frozen=True)
class Token:
    kind: str          # "str" | "longstr" | "number" | "name" | "punct"
    raw: str
    start: int
    end: int


def tokenize(text: str) -> tuple:
    """Split decoded AST text into tokens that carry their source spans."""
    tokens = []
    index, size = 0, len(text)
    while index < size:
        char = text[index]
        if char in _SPACE:
            index += 1
            continue
        if char == '"':
            end = index + 1
            while end < size and text[end] != '"':
                end += 2 if text[end] == "\\" else 1
            if end >= size:
                raise AstError("unterminated_string", "unterminated string literal")
            tokens.append(Token("str", text[index:end + 1], index, end + 1))
            index = end + 1
            continue
        if char == "[" and text.startswith("[[", index):
            end = text.find("]]", index + 2)
            if end < 0:
                raise AstError("unterminated_long_string", "unterminated [[long string]]")
            tokens.append(Token("longstr", text[index:end + 2], index, end + 2))
            index = end + 2
            continue
        if char in _PUNCT:
            tokens.append(Token("punct", char, index, index + 1))
            index += 1
            continue
        end = index
        while end < size and text[end] not in _SPACE and text[end] not in _PUNCT \
                and text[end] != '"' and not text.startswith("[[", end):
            end += 1
        raw = text[index:end]
        if not raw:
            raise AstError("unexpected_character", f"unexpected character {char!r}")
        tokens.append(Token("number" if _NUMBER_RE.match(raw) else "name",
                            raw, index, end))
        index = end
    return tuple(tokens)


# ------------------------------------------------------------------- escapes

_SIMPLE_ESCAPES = {"n": "\n", "r": "\r", "t": "\t", "v": "\v", "b": "\b",
                   "f": "\f", "a": "\a", "'": "'", '"': '"', "\\": "\\"}


def unescape_lua(body: str, *, lenient: bool = False) -> str:
    """Decode a quoted literal with Lua escape rules.

    ``\\n \\r \\t \\v \\b \\f \\a \\' \\" \\\\ \\ddd \\xXX \\uXXXX \\u{...}`` are
    recognised. Anything else is an error unless ``lenient`` is set, in which
    case the backslash is kept - patched commercial releases really do contain
    such sequences, so accepting them has to be an explicit choice.
    """
    out, index = [], 0
    while index < len(body):
        char = body[index]
        if char != "\\":
            out.append(char)
            index += 1
            continue
        rest = body[index + 1:]
        digits = _DIGITS_RE.match(rest)
        if digits:
            out.append(chr(int(digits.group(0), 10) & 0xFF))
            index += 1 + len(digits.group(0))
            continue
        match = _HEX_RE.match(rest)
        if match:
            code = int(next(group for group in match.groups() if group), 16)
            out.append(chr(code))
            index += 1 + match.end()
            continue
        simple = _SIMPLE_ESCAPES.get(rest[:1]) if rest else None
        if simple is None:
            if not lenient:
                raise AstError("unknown_escape",
                               f"unknown escape sequence \\{rest[:1]} in a literal")
            out.append(char)
            index += 1
            continue
        out.append(simple)
        index += 2
    return "".join(out)


def escape_lua(value: str, *, allow_lua_escapes: bool = False) -> str:
    """Encode text for a quoted literal.

    Only a line break is escaped by default, because the shipped patch proves
    ``\\n`` is accepted and gives no evidence about the rest. With
    ``allow_lua_escapes`` the writer may also emit ``\\\\``/``\\"``/``\\t``/
    ``\\r`` and ``\\ddd``; characters Lua cannot represent inline are refused
    either way instead of being dropped.
    """
    out = []
    for char in value:
        if char == "\n":
            out.append("\\n")
        elif char == '"':
            if not allow_lua_escapes:
                raise AstError("unsafe_character",
                               "ASCII double quote needs allow_lua_escapes")
            out.append('\\"')
        elif char == "\\":
            if not allow_lua_escapes:
                raise AstError("unsafe_character", "backslash needs allow_lua_escapes")
            out.append("\\\\")
        elif char == "\r":
            if not allow_lua_escapes:
                raise AstError("unsafe_character",
                               "carriage return needs allow_lua_escapes")
            out.append("\\r")
        elif char == "\t":
            out.append("\\t" if allow_lua_escapes else "\t")
        elif ord(char) < 0x20 or ord(char) == 0x7F:
            if not allow_lua_escapes:
                raise AstError("unsafe_character",
                               f"U+{ord(char):04X} needs allow_lua_escapes")
            out.append("\\%03d" % ord(char))
        else:
            out.append(char)
    return "".join(out)


# -------------------------------------------------------------------- values


@dataclass(frozen=True)
class Value:
    """One Lua value; ``start``/``end`` span the node including its delimiters."""

    kind: str                      # "str" | "int" | "float" | "bool" | "null" | "pair" | "table"
    start: int
    end: int
    text: str | None = None        # decoded string, or the raw literal for numbers/booleans
    key: "Value | None" = None     # "pair": key node
    value: "Value | None" = None   # "pair": value node
    items: tuple = ()              # "table": ordered members

    def members(self):
        return () if self.kind != "table" else self.items

    def pairs(self):
        return tuple(item for item in self.items if item.kind == "pair")

    def get(self, key: str):
        """Last pair with this key, matching the engine's own last-wins lookup."""
        found = None
        for item in self.items:
            if item.kind == "pair" and item.key.kind == "str" and item.key.text == key:
                found = item.value
        return found

    def get_all(self, key: str):
        return tuple(item.value for item in self.items
                     if item.kind == "pair" and item.key.kind == "str"
                     and item.key.text == key)

    def is_str(self) -> bool:
        return self.kind == "str"

    def as_str(self):
        return self.text if self.kind == "str" else None

    def tag(self):
        """``{"tag", ...}`` command form: the tag when the first member is a string."""
        if self.kind != "table" or not self.items:
            return None
        first = self.items[0]
        return first.text if first.kind == "str" else None

    def find_tag(self, tag: str):
        for item in self.items:
            if item.kind == "table" and item.tag() == tag:
                return item
        return None


class _Parser:
    def __init__(self, text: str, *, lenient: bool = False):
        self.text = text
        self.lenient = lenient
        self.tokens = tokenize(text)
        self.pos = 0

    def peek(self, offset: int = 0):
        index = self.pos + offset
        return self.tokens[index] if index < len(self.tokens) else None

    def take(self):
        token = self.peek()
        if token is None:
            raise AstError("unexpected_end", "input ended early")
        self.pos += 1
        return token

    def expect_punct(self, char: str):
        token = self.take()
        if token.kind != "punct" or token.raw != char:
            raise AstError("unexpected_token", f"expected {char!r}, got {token.raw!r}")
        return token

    def string_literal(self, token: Token):
        if token.kind == "str":
            return unescape_lua(token.raw[1:-1], lenient=self.lenient)
        return token.raw[2:-2]

    def parse_value(self):
        token = self.peek()
        if token is None:
            raise AstError("unexpected_end", "input ended early")
        if token.kind in ("str", "longstr"):
            self.take()
            return Value("str", token.start, token.end, self.string_literal(token))
        if token.kind == "number":
            self.take()
            return Value("float" if "." in token.raw else "int",
                         token.start, token.end, token.raw)
        if token.kind == "name":
            self.take()
            if token.raw == "nil":
                return Value("null", token.start, token.end)
            if token.raw in ("true", "false"):
                return Value("bool", token.start, token.end, token.raw)
            # A Lua global reference: its value exists only at run time.
            raise AstError("bare_identifier",
                           f"bare identifier {token.raw!r} is a run-time variable "
                           "reference, not data")
        if token.raw == "{":
            return self.parse_table()
        raise AstError("unexpected_token", f"unexpected token {token.raw!r}")

    def parse_key(self):
        token = self.peek()
        if token is None:
            raise AstError("unexpected_end", "input ended early")
        if token.kind in ("str", "longstr"):
            self.take()
            return Value("str", token.start, token.end, self.string_literal(token))
        if token.kind == "number":
            self.take()
            return Value("int", token.start, token.end, token.raw)
        if token.kind == "name":
            self.take()
            return Value("str", token.start, token.end, token.raw)
        if token.kind == "punct" and token.raw == "[":
            opening = self.take()
            inner = self.parse_key()
            closing = self.expect_punct("]")
            return Value("str", opening.start, closing.end, inner.text)
        raise AstError("unexpected_token", f"unexpected key {token.raw!r}")

    def _starts_pair(self) -> bool:
        token = self.peek()
        if token is None:
            return False
        if token.kind in ("name", "number", "str", "longstr"):
            following = self.peek(1)
            return following is not None and following.kind == "punct" \
                and following.raw == "="
        return token.kind == "punct" and token.raw == "["

    def parse_table(self):
        opening = self.expect_punct("{")
        items = []
        while True:
            token = self.peek()
            if token is None:
                raise AstError("unexpected_end", "unterminated table")
            if token.kind == "punct" and token.raw == "}":
                self.take()
                return Value("table", opening.start, token.end, items=tuple(items))
            if token.kind == "punct" and token.raw == ",":
                self.take()
                continue
            if self._starts_pair():
                key = self.parse_key()
                self.expect_punct("=")
                value = self.parse_value()
                items.append(Value("pair", key.start, value.end, key=key, value=value))
                continue
            items.append(self.parse_value())

    def parse_file(self):
        version = name = None
        for _ in range(len(HEADER_KEYS)):
            token = self.peek()
            if token is None:
                raise AstError("unexpected_end", "input ended early")
            if not (token.kind == "name" and token.raw in HEADER_KEYS):
                break
            self.take()
            self.expect_punct("=")
            if token.raw == "astver":
                if version is not None:
                    raise AstError("duplicate_header", "two astver statements")
                version = self.parse_value()
            else:
                if name is not None:
                    raise AstError("duplicate_header", "two astname statements")
                name = self.parse_value()
        token = self.take()
        if token.kind != "name" or token.raw != "ast":
            raise AstError("bad_header", f"expected the ast table, got {token.raw!r}")
        self.expect_punct("=")
        ast = self.parse_value()
        if self.peek() is not None:
            raise AstError("trailing_data", f"unexpected trailing token {self.peek().raw!r}")
        return version, name, ast


# --------------------------------------------------------------------- units


@dataclass(frozen=True)
class Unit:
    """One translatable unit: a message box, a choice, a choice prompt or a title."""

    kind: str                   # "message" | "choice" | "prompt" | "title"
    block: str                  # block name, "#N" positional block, or "text[N]" entry
    index: int
    script_line: int | None
    span: tuple                 # (start, end) of the text a rewrite replaces
    message: str
    names: tuple = ()
    name_keys: tuple = ()       # per slot: the pair key when the name table is keyed
    furigana: tuple = ()
    inline: tuple = ()          # tag of every protected inline command, in order
    lines: int = 1
    # message boxes only
    indent: str = ""
    close_indent: str = ""
    trailing_break: bool = False
    break_tag: str = "rt2"
    blank_lines: bool = False   # the box separates statements with an empty line
    name_spans: tuple = ()      # per slot: (start, end) of the string literal
    tokens: tuple = ()          # protected inline command sources, in order
    language: str | None = None
    #: "slots" | "keyed" (in-box), "entry" (positional entry), "command"
    #: (language-level ``{"name", name=...}``); "" without a name.
    name_form: str = ""
    name_display: int = -1      # index of the display slot in ``names``
    name_append_key: str | None = None   # "entry" form: key a new display needs
    name_table: tuple | None = None      # (start, end) of the name table value
    name_pair: tuple | None = None       # in-box form: (start, end) of ``name = {...}``
    name_outer: bool = False    # the name table lives outside the box span
    name_sep: str = ", "        # separator used when appending a slot or key
    name_eq: str = "="          # ``key = value`` spelling used when appending a key
    boxless: bool = False       # entry with a name but no text box at all
    duplicate_entry: bool = False
    compact: bool = False       # box written on one line (no per-member lines)

    @property
    def display_name(self):
        """The text shown in the name box (``None`` for narration)."""
        return self.names[self.name_display] if self.names else None

    @property
    def identity_name(self):
        """The fixed character identity; read-only context."""
        if not self.names:
            return None
        if self.name_form in ("slots", "keyed"):
            return self.names[0]
        if self.name_form == "entry":
            return self.names[self.name_keys.index("name")]
        return None

    @property
    def name_policy(self) -> str:
        if not self.names:
            return "absent"
        if self.name_form == "keyed" and len(self.names) == 1:
            # A lone keyed slot has no key to give an appended display slot.
            return "context"
        if self.name_form == "entry" and self.name_append_key is None \
                and self.name_keys[self.name_display] == "name":
            # No language selected: a new display key cannot be named.
            return "context"
        return "writable"

    @property
    def owned_spans(self):
        spans = [self.span]
        if self.name_outer and self.name_table is not None and not self.boxless:
            spans.append(self.name_table)
        return spans


@dataclass(frozen=True)
class Document:
    """A parsed AST script plus the decoded source it was parsed from."""

    path: str
    encoding: str
    bom: bool
    newline: str
    astver: str | None
    astname: str | None
    ast: Value
    units: tuple
    text: str = field(default="", repr=False)
    #: Parse options; ``patch`` re-reads its own output with exactly these.
    language: str | None = None
    extra_inline_tags: frozenset = frozenset()
    lenient_escapes: bool = False
    #: "blocks" (``label.top`` named blocks) or "positional".
    layout: str = "blocks"
    #: Language keys seen in text/select tables, in document order.
    languages: tuple = ()
    #: The language the units were read from (explicit or first seen).
    selected_language: str | None = None
    #: Tables that hold other languages but not the selected one; not exported.
    skipped: tuple = ()

    def rows(self):
        """Minimal GalTransl rows in document order; ``name`` is the display slot."""
        result = []
        for unit in self.units:
            row = {}
            if unit.names:
                row["name"] = unit.display_name
            row["message"] = unit.message
            result.append(row)
        return result

    def locators(self):
        return [{"kind": unit.kind, "layout": self.layout, "block": unit.block,
                 "index": unit.index, "script_line": unit.script_line,
                 "span": [unit.span[0], unit.span[1]], "language": unit.language,
                 "source_lines": unit.lines, "name_slots": len(unit.names),
                 "name_form": unit.name_form or None,
                 "name_identity": unit.identity_name,
                 "furigana": list(unit.furigana), "inline_commands": list(unit.inline),
                 "tokens": list(unit.tokens), "boxless": unit.boxless,
                 "duplicate_entry": unit.duplicate_entry}
                for unit in self.units]

    def name_policies(self):
        return [unit.name_policy for unit in self.units]

    def protected_tokens(self):
        """Per row: distinct inline-command tokens, in first-appearance order."""
        return [list(dict.fromkeys(unit.tokens)) for unit in self.units]

    def patch(self, rows, *, allow_lua_escapes: bool = False,
              max_output_size: int = 64 << 20) -> bytes:
        """Rebuild the source bytes from ``rows`` and verify them by re-parsing.

        The output is read back with this document's own encoding, language,
        ``extra_inline_tags`` and ``lenient_escapes``, then compared unit by
        unit (text, tokens, name slots), byte for byte outside the rewritten
        spans, and against the non-text skeleton; any mismatch raises
        ``verification_failed`` instead of returning bytes.
        """
        text = render(self, rows, allow_lua_escapes=allow_lua_escapes)
        rebuilt = encode_ast(self, text, max_output_size=max_output_size)
        after = read_ast(rebuilt, encoding=self.encoding, path=self.path,
                         language=self.language,
                         extra_inline_tags=self.extra_inline_tags,
                         lenient_escapes=self.lenient_escapes,
                         max_bytes=max(max_output_size, len(rebuilt)))
        if after.bom != self.bom:
            raise AstError("verification_failed", "BOM state changed after rebuild",
                           "verify")
        _verify_rebuild(self, after, rows)
        return rebuilt


# ------------------------------------------------------------------- reading


_UTF8_BOM = b"\xef\xbb\xbf"


def _candidates(data: bytes, encoding):
    """Yield ``(codec, body, bom)``; the BOM is decided from the bytes, not the codec.

    ``utf-8-sig`` happily decodes BOM-less input, so trying it first would record
    a BOM the file never had and the writer would then add one.
    """
    bom = data[:3] == _UTF8_BOM
    if encoding is None:
        codecs_to_try = ("utf-8",) if bom else ("utf-8", "cp932")
    else:
        codecs_to_try = (encoding,)
    for codec in codecs_to_try:
        try:
            name = codecs.lookup(codec).name
        except LookupError:
            continue
        if name in ("utf-8", "utf-8-sig"):
            yield ("utf-8-sig", data[3:], True) if bom else ("utf-8", data, False)
        else:
            yield codec, data, False


def _decode(data, encoding):
    """Return ``(text, codec, bom)``; ``text`` never starts with the BOM."""
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise AstError("input_type", "script input must be bytes", "input")
    data = bytes(data)
    for codec, body, bom in _candidates(data, encoding):
        try:
            return body.decode(codec if not bom else "utf-8", errors="strict"), codec, bom
        except UnicodeDecodeError:
            continue
    raise AstError("bad_encoding", "script is not decodable with the given encodings",
                   "input")


def looks_like_ast(data, *, encoding=None, max_bytes: int = 4096) -> bool:
    """Weak probe: ``astver``/``astname``/``ast`` followed by ``=``.

    Enough to pick this reader over the ASB and SCP ones, not a support claim.
    Only a prefix is decoded; an incremental decoder holds back a multibyte
    character cut by the prefix boundary instead of failing on it.
    """
    try:
        prefix = bytes(data)[:max_bytes]
    except (TypeError, ValueError):
        return False
    text = None
    for codec, body, bom in _candidates(prefix, encoding):
        try:
            decoder = codecs.getincrementaldecoder("utf-8" if bom else codec)("strict")
            text = decoder.decode(body, final=False)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    if text is None:
        return False
    text = text.lstrip("\ufeff \t\r\n")
    for key in ("astver", "astname", "ast"):
        if text.startswith(key):
            rest = text[len(key):].lstrip(" \t\r\n")
            return rest.startswith("=")
    return False


def _indent_of(text: str, position: int) -> str:
    return text[text.rfind("\n", 0, position) + 1:position]


def _script_line(block: Value):
    value = block.get("line")
    if value is None or value.kind not in ("int", "float"):
        return None
    try:
        return int(value.text)
    except (TypeError, ValueError):
        return None


def _only_pair(block: Value, key: str):
    values = block.get_all(key)
    if len(values) > 1:
        raise AstError("duplicate_key", f"block declares {key!r} more than once")
    return values[0] if values else None


# ---------------------------------------------------------- table shapes


def _is_attribute(value: Value) -> bool:
    """Scalar, or a table of scalar ``key = value`` pairs (``linemode={...}``)."""
    if value.kind in _SCALARS:
        return True
    return value.kind == "table" and all(
        item.kind == "pair" and item.value.kind in _SCALARS for item in value.items)


def _is_box(value: Value) -> bool:
    if value.kind != "table":
        return False
    if any(item.kind != "pair" for item in value.items):
        return True                       # contents are validated by _read_box
    return all(item.key.text == "name" for item in value.items)


def _is_message_language(value: Value) -> bool:
    """A list of boxes, optionally with a language-level ``name`` pair."""
    if value.kind != "table":
        return False
    positional = [item for item in value.items if item.kind != "pair"]
    if not positional:
        return False
    if any(item.kind == "pair" and item.key.text != "name" for item in value.items):
        return False
    return all(_is_box(item) for item in positional)


def _is_choice_language(value: Value) -> bool:
    return value.kind == "table" and bool(value.items) and \
        all(item.kind == "str" for item in value.items)


def _text_languages(table: Value, where: str, language, reserved=("name",)):
    """``[(key, table)]`` for members shaped like a language box list.

    Voice layers, attribute members (``linemode={}``, ``hide=true``) and the
    reserved keys are skipped; anything else is rejected, never guessed at.
    """
    found = []
    for item in table.items:
        if item.kind != "pair" or item.key.kind != "str":
            raise AstError("unknown_text_member",
                           f"{where}: positional member inside a text table")
        key = item.key.text
        if key in reserved or NON_LANGUAGE_KEYS.match(key):
            continue
        if _is_message_language(item.value):
            found.append((key, item.value))
        elif language is not None and key == language:
            raise AstError("bad_structure",
                           f"{where}: text[{key}] is not a list of message boxes")
        elif not _is_attribute(item.value):
            raise AstError("unknown_text_member",
                           f"{where}: text member {key!r} is neither a language "
                           "box list nor a plain attribute")
    return found


def _select_languages(table: Value, where: str, language):
    """``([(key, options)], neutral)``; ``neutral`` is a language-free option list."""
    if table.kind != "table":
        raise AstError("bad_structure", f"{where}: select is not a table")
    if _is_choice_language(table):
        return [], table
    found = []
    for item in table.items:
        if item.kind != "pair" or item.key.kind != "str":
            raise AstError("bad_select", f"{where}: select option is not a string literal")
        key = item.key.text
        if NON_LANGUAGE_KEYS.match(key):
            continue
        if _is_choice_language(item.value):
            found.append((key, item.value))
        elif (language is not None and key == language) or item.value.kind == "table" \
                and any(member.kind != "pair" for member in item.value.items):
            raise AstError("bad_select",
                           f"{where}: select[{key}] option is not a string literal")
        elif not _is_attribute(item.value):
            raise AstError("bad_select", f"{where}: select member {key!r} is not text")
    return found, None


# ----------------------------------------------------------------- names


@dataclass(frozen=True)
class _Name:
    form: str
    names: tuple
    keys: tuple
    spans: tuple
    display: int
    append_key: str | None
    table: tuple
    pair: tuple | None
    sep: str
    eq: str


def _separator(text: str, table: Value, default: str = ", ") -> str:
    items = table.items
    if len(items) >= 2:
        between = text[items[-2].end:items[-1].start]
        if between.strip() == ",":
            return between
    return default


def _box_name(text: str, box: Value):
    """In-box ``name = {...}``: positional slots or keyed slots."""
    pairs = [item for item in box.items if item.kind == "pair"
             and item.key.kind == "str" and item.key.text == "name"]
    if len(pairs) > 1:
        raise AstError("duplicate_name", "message box declares name more than once")
    if not pairs:
        return None
    table = pairs[0].value
    if table.kind != "table":
        raise AstError("bad_name", "name is not a table")
    names, keys, spans = [], [], []
    for member in table.items:
        if member.kind == "str":
            names.append(member.text)
            keys.append(None)
            spans.append((member.start, member.end))
        elif member.kind == "pair" and member.value.kind == "str" \
                and member.key.kind == "str":
            names.append(member.value.text)
            keys.append(member.key.text)
            spans.append((member.value.start, member.value.end))
        else:
            raise AstError("bad_name_slot",
                           "name members must be string values or string pairs")
    if not names:
        raise AstError("bad_name_slot", "name table holds no string slot")
    form = "keyed" if keys[0] is not None else "slots"
    return _Name(form, tuple(names), tuple(keys), tuple(spans), len(names) - 1, None,
                 (table.start, table.end), (pairs[0].start, pairs[0].end),
                 _separator(text, table), "=")


def _entry_name(text: str, table: Value, language, where: str):
    """Entry-level ``name = {name="id", <lang>="display", ...}``."""
    if table.kind != "table" or not table.items:
        raise AstError("bad_name", f"{where}: name is not a keyed table")
    names, keys, spans = [], [], []
    for member in table.items:
        if member.kind != "pair" or member.key.kind != "str" or member.value.kind != "str":
            raise AstError("bad_name_slot",
                           f"{where}: entry name members must be key = \"string\"")
        if member.key.text in keys:
            raise AstError("duplicate_name", f"{where}: name key {member.key.text!r} repeats")
        names.append(member.value.text)
        keys.append(member.key.text)
        spans.append((member.value.start, member.value.end))
    if "name" not in keys:
        raise AstError("bad_name", f"{where}: entry name has no identity key 'name'")
    identity = table.items[keys.index("name")]
    if language is not None and language in keys and language != "name":
        display, append = keys.index(language), None
    else:
        display = keys.index("name")
        append = language if language not in (None, "name") else None
    return _Name("entry", tuple(names), tuple(keys), tuple(spans), display, append,
                 (table.start, table.end), None, _separator(text, table, ","),
                 text[identity.key.end:identity.value.start])


def _command_name(table: Value, where: str):
    """Language-level ``name = {"name", name="display"}`` (``text`` overrides)."""
    if table.kind != "table" or table.tag() != "name" or \
            any(item.kind != "pair" for item in table.items[1:]):
        raise AstError("bad_name", f"{where}: language name is not {{\"name\", name=...}}")
    names, keys, spans = [], [], []
    for member in table.items[1:]:
        if member.key.kind != "str" or member.value.kind != "str":
            raise AstError("bad_name_slot", f"{where}: name attributes must be strings")
        if member.key.text in keys:
            raise AstError("duplicate_name", f"{where}: name key {member.key.text!r} repeats")
        names.append(member.value.text)
        keys.append(member.key.text)
        spans.append((member.value.start, member.value.end))
    shown = "text" if "text" in keys else "name" if "name" in keys else None
    if shown is None:
        raise AstError("bad_name", f"{where}: language name has neither text nor name")
    return _Name("command", tuple(names), tuple(keys), tuple(spans), keys.index(shown),
                 None, (table.start, table.end), None, ", ", "=")


# ----------------------------------------------------------------- boxes


def _read_box(text, where, line, box, index, extra_inline, language, outer=None,
              entry_dup=False):
    inner = _box_name(text, box)
    if inner is not None and outer is not None:
        raise AstError("duplicate_name",
                       f"{where}: box declares a name and its entry declares one too")
    name = inner or outer
    furigana, inline, tokens, parts = [], [], [], []
    for element in box.items:
        if element.kind == "pair":
            if element.key.kind == "str" and element.key.text == "name":
                continue
            raise AstError("unknown_element",
                           f"{where}: unexpected key "
                           f"{element.key.text!r} inside a message box")
        if element.kind == "str":
            if TOKEN_MARK in element.text:
                raise AstError("ambiguous_token",
                               f"{where}: literal text contains {TOKEN_MARK!r}, the "
                               "protected-token prefix")
            parts.append(("text", element.text))
            continue
        if element.kind != "table":
            raise AstError("bad_message",
                           f"{where}: box member is not a string or a command")
        tag = element.tag()
        if tag is None:
            raise AstError("bad_message", f"{where}: box command has no tag")
        if tag in LINE_BREAK_TAGS:
            parts.append(("break", tag))
        elif tag == "ruby":
            reading = element.get("text")
            furigana.append(reading.text if reading is not None and reading.is_str() else "")
        elif tag == "/ruby":
            continue
        elif tag in INLINE_TAGS or tag in extra_inline:
            raw = text[element.start:element.end]
            if "\n" in raw or "\r" in raw:
                raise AstError("multiline_inline",
                               f"{where}: inline command {tag!r} spans several lines")
            inline.append(tag)
            tokens.append(raw)
            parts.append(("token", raw))
        else:
            raise AstError("unknown_inline",
                           f"{where}: unknown inline tag {tag!r}; pass it in "
                           "extra_inline_tags to keep it as a protected token")
    if not parts and name is None:
        raise AstError("empty_box", f"{where}: message box is empty")
    groups = [[]]
    for part in parts:
        if part[0] == "break":
            groups.append([])
        else:
            groups[-1].append(part[1])
    trailing = bool(parts) and parts[-1][0] == "break"
    content = groups[:-1] if trailing else groups
    breaks = [part[1] for part in parts if part[0] == "break"]
    head = text[box.start + 1:box.items[0].start]
    indent = _indent_of(text, box.items[0].start)
    close_indent = _indent_of(text, box.end - 1)
    # A box whose members do not each start a line (minified files) is
    # rewritten on one line, without inventing a line layout.
    compact = "\n" not in head or indent.strip(" \t") != "" or \
        close_indent.strip(" \t") != ""
    if compact:
        indent = close_indent = ""
    return Unit("message", where, index, line,
                (box.start + 1, box.end - 1), "\n".join("".join(g) for g in content),
                _field(name, "names", ()), _field(name, "keys", ()), tuple(furigana),
                tuple(inline), len(breaks), indent, close_indent,
                trailing, breaks[0] if breaks else "rt2",
                not compact and head.count("\n") > 1,
                _field(name, "spans", ()), tuple(tokens), language,
                **_name_fields(name, outer is not None), duplicate_entry=entry_dup,
                compact=compact)


def _field(name, attr, default):
    return getattr(name, attr) if name is not None else default


def _name_fields(name, outer):
    if name is None:
        return {}
    return {"name_form": name.form, "name_display": name.display,
            "name_append_key": name.append_key, "name_table": name.table,
            "name_pair": name.pair, "name_outer": outer, "name_sep": name.sep,
            "name_eq": name.eq}


def _boxless_unit(where, name, language, entry_dup):
    """An entry with a name and no text box: the name is still shown."""
    return Unit("message", where, 0, None, name.table, "", name.names, name.keys,
                (), (), 0, name_spans=name.spans, language=language, boxless=True,
                duplicate_entry=entry_dup, **_name_fields(name, True))


def _resolve_language(sites, language):
    """Explicit language, or the first language key in document order."""
    seen = []
    for site in sites:
        for key, _value in site:
            if key not in seen:
                seen.append(key)
    if language is None:
        return (seen[0] if seen else None), tuple(seen)
    if seen and language not in seen:
        raise AstError("no_language_table",
                       f"language {language!r} is not present; found {seen}")
    return language, tuple(seen)


def _pick(found, language):
    for key, value in found:
        if key == language:
            return value
    return None


def _command_text(command: Value, base: str, language, where: str):
    """``<base>_<lang>`` / ``<lang>`` override, else ``<base>`` (engine lookup)."""
    candidates = []
    if language is not None:
        candidates.append(f"{base}_{language}")
        if base == "text":
            candidates.append(language)
    present = [key for key in candidates if command.get(key) is not None]
    if len(present) > 1:
        raise AstError("ambiguous_attribute",
                       f"{where}: both {present[0]!r} and {present[1]!r} are set")
    key = present[0] if present else base
    values = command.get_all(key)
    if len(values) > 1:
        raise AstError("duplicate_key", f"{where}: {key!r} repeats in a command")
    return values[0] if values else None


# ------------------------------------------------------- named-block layout


def _read_block_layout(text, ast, extra_inline, language):
    seen_names = set()
    for entry in ast.items:
        if entry.kind != "pair" or entry.key.kind != "str":
            raise AstError("bad_structure", "the ast table may only hold named tables")
        if entry.key.text in seen_names:
            raise AstError("duplicate_key", f"top-level table {entry.key.text!r} repeats")
        seen_names.add(entry.key.text)
    # Any string key is a block; its name is whatever label.top.block /
    # linknext refer to. Bare ``block_00000`` and quoted ``["0001_00001"]``
    # keys both occur, so no name prefix is required.
    plan = []
    for entry in ast.items:
        name = entry.key.text
        if name == "label":
            continue
        block = entry.value
        if block.kind != "table":
            raise AstError("bad_structure", f"{name} is not a table")
        tables = {}
        for key in ("text", "select"):
            table = _only_pair(block, key)
            if table is None:
                continue
            if table.kind != "table":
                raise AstError("bad_structure", f"{name}: {key} is not a table")
            if key == "text":
                tables[key] = (_text_languages(table, name, language), None)
            else:
                tables[key] = _select_languages(table, name, language)
        plan.append((name, block, tables))
    sites = [found for _n, _b, tables in plan for found, _neutral in tables.values()]
    chosen, languages = _resolve_language(sites, language)
    units, skipped = [], []
    for name, block, tables in plan:
        line = _script_line(block)
        if "text" in tables:
            found = tables["text"][0]
            members = _pick(found, chosen)
            if members is None and found:
                skipped.append({"kind": "message", "block": name})
            elif members is not None:
                _language_boxes(text, name, line, members, extra_inline, chosen,
                                None, False, units)
        if "select" in tables:
            _choices(name, line, tables["select"], chosen, skipped, units)
        _title(name, line, block, chosen, units)
    return units, chosen, languages, skipped


def _language_boxes(text, where, line, members, extra_inline, language, outer,
                    duplicate, units):
    level = [item for item in members.items if item.kind == "pair"]
    boxes = [item for item in members.items if item.kind != "pair"]
    if level:
        if len(level) > 1:
            raise AstError("duplicate_name", f"{where}: language table repeats name")
        if outer is not None:
            raise AstError("duplicate_name",
                           f"{where}: entry and language table both declare a name")
        outer = _command_name(level[0].value, where)
    if outer is not None and len(boxes) != 1:
        raise AstError("ambiguous_name",
                       f"{where}: one name table cannot be tied to {len(boxes)} boxes")
    for index, box in enumerate(boxes):
        units.append(_read_box(text, where, line, box, index, extra_inline, language,
                               outer, duplicate))


def _choices(where, line, select, language, skipped, units):
    found, neutral = select
    options = neutral if neutral is not None else _pick(found, language)
    if options is None:
        if found:
            skipped.append({"kind": "choice", "block": where})
        return
    for index, member in enumerate(options.items):
        units.append(Unit("choice", where, index, line, (member.start, member.end),
                          member.text, language=None if neutral is not None else language))


def _title(where, line, block, language, units):
    title = block.find_tag("savetitle")
    if title is None:
        return
    value = _command_text(title, "text", language, where)
    if value is None or not value.is_str():
        raise AstError("bad_title", f"{where}: savetitle has no string text")
    units.append(Unit("title", where, 0, line, (value.start, value.end), value.text,
                      language=language))


# ------------------------------------------------------- positional layout


def _read_positional_layout(text, ast, extra_inline, language):
    blocks, tables, labels = [], [], 0
    for item in ast.items:
        if item.kind == "table":
            blocks.append(item)
        elif item.kind == "pair" and item.key.kind == "str" and item.key.text == "text":
            if item.value.kind != "table":
                raise AstError("bad_structure", "the top-level text member is not a table")
            tables.append(item.value)
        elif item.kind == "pair" and item.key.kind == "str" and item.key.text == "label":
            labels += 1
            if labels > 1:
                raise AstError("duplicate_key", "top-level label repeats")
        else:
            raise AstError("unknown_layout_member",
                           "positional layout holds a member that is neither a block "
                           "table, text nor label")
    entries = []
    for ordinal, table in enumerate(tables):
        prefix = "text" if len(tables) == 1 else f"text#{ordinal + 1}"
        keys = [item.key.text for item in table.items
                if item.kind == "pair" and item.key.kind == "str"]
        for item in table.items:
            if item.kind != "pair" or item.key.kind != "str":
                raise AstError("bad_structure", "text entries must be [N] = {...} pairs")
            where = f"{prefix}[{item.key.text}]"
            value = item.value
            if value.kind != "table":
                raise AstError("bad_structure", f"{where} is not a table")
            name = _only_pair(value, "name")
            select = _only_pair(value, "select")
            found = _text_languages(value, where, language, reserved=("name", "select"))
            choices = _select_languages(select, where, language) if select is not None \
                else None
            entries.append((where, value, name, found, choices,
                            keys.count(item.key.text) > 1))
    sites = [found for _w, _v, _n, found, _c, _d in entries] + \
        [choices[0] for _w, _v, _n, _f, choices, _d in entries if choices is not None]
    chosen, languages = _resolve_language(sites, language)
    units, skipped = [], []
    for where, value, name, found, choices, duplicate in entries:
        outer = _entry_name(text, name, chosen, where) if name is not None else None
        members = _pick(found, chosen)
        if members is not None:
            _language_boxes(text, where, None, members, extra_inline, chosen, outer,
                            duplicate, units)
        elif found:
            skipped.append({"kind": "message", "block": where})
        elif outer is not None:
            units.append(_boxless_unit(where, outer, chosen, duplicate))
        if choices is not None:
            before = len(units)
            _choices(where, None, choices, chosen, skipped, units)
            if duplicate:
                units[before:] = [_replace(unit, duplicate_entry=True)
                                  for unit in units[before:]]
    # Choice labels live in the block commands only when no text entry carries
    # a select table (the engine then reads ``text_<lang>`` or ``text``).
    block_choices = not any(choices is not None for *_r, choices, _d in entries)
    for number, block in enumerate(blocks, 1):
        where = f"#{number}"
        if block.get("text") is not None or block.get("select") is not None:
            raise AstError("unknown_layout_member",
                           f"{where}: a positional block carries its own text/select "
                           "table; mixed layouts are not implemented")
        line = _script_line(block)
        _title(where, line, block, chosen, units)
        if not block_choices:
            continue
        ordinal = 0
        for command in block.items:
            if command.kind != "table" or command.tag() != "select":
                continue
            for base, kind in (("text", "choice"), ("mw", "prompt")):
                value = _command_text(command, base, chosen, where)
                if value is None:
                    continue
                if not value.is_str():
                    raise AstError("bad_select", f"{where}: select {base} is not a string")
                units.append(Unit(kind, where, ordinal, line, (value.start, value.end),
                                  value.text, language=chosen))
            ordinal += 1
    return units, chosen, languages, skipped


def _replace(unit, **changes):
    return dataclasses.replace(unit, **changes)


def _read_units(text, ast, extra_inline, language):
    if ast.kind != "table":
        raise AstError("bad_structure", "the ast statement is not a table")
    label = ast.get("label")
    if label is not None and label.kind == "table" and label.get("top") is not None:
        layout = "blocks"
        units, chosen, languages, skipped = _read_block_layout(text, ast, extra_inline,
                                                               language)
    elif any(item.kind == "table" for item in ast.items) or ast.get("text") is not None:
        layout = "positional"
        units, chosen, languages, skipped = _read_positional_layout(
            text, ast, extra_inline, language)
    else:
        raise AstError("missing_label",
                       "the ast table has no label.top entry and no positional "
                       "blocks (unknown layout)")
    units.sort(key=lambda unit: (unit.span[0], unit.span[1]))
    owned = sorted(span for unit in units for span in unit.owned_spans)
    for (_s1, end), (start, _e2) in zip(owned, owned[1:]):
        if start < end:
            raise AstError("overlapping_units", "two units claim the same source range")
    return layout, tuple(units), chosen, languages, tuple(skipped)


def read_ast(data, *, encoding=None, path: str = "", language=None,
             extra_inline_tags=frozenset(), lenient_escapes: bool = False,
             max_bytes: int = 64 << 20) -> Document:
    """Parse one AST text script into ordered units; no filesystem access."""
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise AstError("input_type", "script input must be bytes", "input")
    if len(data) > max_bytes:
        raise AstError("too_large", "script exceeds the byte budget", "input")
    text, codec, bom = _decode(data, encoding)
    version, name, ast = _Parser(text, lenient=lenient_escapes).parse_file()
    astver = None
    if version is not None:
        if version.kind not in ("int", "float"):
            raise AstError("bad_header", "astver must be a number")
        astver = version.text
        if astver not in SUPPORTED_VERSIONS:
            raise AstError("unsupported_version", f"unsupported astver {astver}")
    astname = name.text if name is not None and name.is_str() else None
    extra = frozenset(extra_inline_tags)
    layout, units, chosen, languages, skipped = _read_units(text, ast, extra, language)
    return Document(path=path, encoding=codec, bom=bom,
                    newline="\r\n" if "\r\n" in text else "\n", astver=astver,
                    astname=astname, ast=ast, units=units, text=text,
                    language=language, extra_inline_tags=extra,
                    lenient_escapes=lenient_escapes, layout=layout,
                    languages=languages, selected_language=chosen, skipped=skipped)


# ------------------------------------------------------------------- writing


def _slot_literal(value, allow_lua_escapes):
    return '"' + escape_lua(value, allow_lua_escapes=allow_lua_escapes) + '"'


def _segments(unit: Unit, message: str):
    """Split ``message`` into text and the unit's tokens; same tokens, same order."""
    ordered = sorted(set(unit.tokens), key=len, reverse=True)
    segments, found, buffer, index = [], [], [], 0
    while index < len(message):
        token = next((t for t in ordered if message.startswith(t, index)), None)
        if token is None:
            buffer.append(message[index])
            index += 1
            continue
        if buffer:
            segments.append(("text", "".join(buffer)))
            buffer = []
        segments.append(("token", token))
        found.append(token)
        index += len(token)
    if buffer:
        segments.append(("text", "".join(buffer)))
    if found != list(unit.tokens):
        raise AstError("token_mismatch",
                       f"{unit.block}: inline-command tokens must appear exactly as in "
                       f"the source and in the same order ({len(unit.tokens)} expected, "
                       f"{len(found)} found)", "write")
    if any(kind == "text" and TOKEN_MARK in value for kind, value in segments):
        raise AstError("token_mismatch",
                       f"{unit.block}: text contains {TOKEN_MARK!r} that is not one of "
                       "this box's tokens", "write")
    return segments


def _render_box(unit: Unit, segments, name_source, newline: str,
                allow_lua_escapes: bool) -> str:
    gap = "" if unit.compact else newline * (2 if unit.blank_lines else 1)
    lead = gap + unit.indent
    body = ""
    if name_source is not None:
        body += lead + name_source + ","
    if not unit.tokens:
        message = "".join(value for _kind, value in segments)
        body += lead + _slot_literal(message, allow_lua_escapes) + ","
        if unit.trailing_break:
            body += lead + '{"' + unit.break_tag + '"},'
        return body + gap + unit.close_indent
    lines = [[]]
    for kind, value in segments:
        if kind == "token":
            lines[-1].append(value)
            continue
        for position, piece in enumerate(value.split("\n")):
            if position:
                lines.append([])
            if piece:
                lines[-1].append(_slot_literal(piece, allow_lua_escapes))
    if len(lines) > 1 and not lines[-1] and not unit.trailing_break:
        raise AstError("bad_message",
                       f"{unit.block}: a final empty line cannot be written without "
                       "a trailing line break", "write")
    for position, parts in enumerate(lines):
        for part in parts:
            body += lead + part + ","
        if unit.trailing_break or position < len(lines) - 1:
            body += lead + '{"' + unit.break_tag + '"},'
    return body + gap + unit.close_indent


def _names_for(unit: Unit, row):
    """``(names, keys)`` after applying ``row["name"]``, or ``None`` when unchanged.

    The identity is never rewritten. In-box slots: the last slot is the display
    and a lone slot gains an appended one. Entry-level keyed names: the selected
    language's key is replaced or appended. Language-level names: the shown
    attribute is replaced.
    """
    if "names" in row:
        raise AstError("bad_name",
                       "AST rows carry one display name in name; the identity slot "
                       "is not translatable", "write")
    name = row.get("name")
    if name is None:
        return None
    if not isinstance(name, str) or not name:
        raise AstError("bad_name", "name must be a nonempty string", "write")
    if not unit.names:
        raise AstError("name_not_writable", "this unit has no name slot", "write")
    if name == unit.display_name:
        return None
    if unit.name_policy != "writable":
        raise AstError("name_not_writable",
                       "this name slot is identity only; no display slot can be "
                       "added without inventing a key", "write")
    names, keys = list(unit.names), list(unit.name_keys)
    if unit.name_form == "slots" and len(names) == 1:
        return names + [name], keys + [None]
    if unit.name_form == "entry" and unit.name_append_key is not None:
        return names + [name], keys + [unit.name_append_key]
    names[unit.name_display] = name
    return names, keys


def _render_name_edit(unit: Unit, names, keys, allow_lua_escapes: bool):
    """Minimal edit: replace the display literal, or append one slot/key."""
    literal = _slot_literal(names[-1] if len(names) > len(unit.names)
                            else names[unit.name_display], allow_lua_escapes)
    if len(names) > len(unit.names):
        end = unit.name_spans[-1][1]
        if keys[-1] is None:
            return end, end, unit.name_sep + literal
        return end, end, unit.name_sep + keys[-1] + unit.name_eq + literal
    start, end = unit.name_spans[unit.name_display]
    return start, end, literal


def render(document: Document, rows, *, allow_lua_escapes: bool = False) -> str:
    """Apply ``message``/``name`` from ``rows``; every other byte is preserved.

    Only units whose text or names actually differ are rewritten, so an
    unchanged export reproduces the file byte for byte.
    """
    if len(rows) != len(document.units):
        raise AstError("row_count", "row count differs from the parsed units", "write")
    text = document.text
    edits = []
    for unit, row in zip(document.units, rows):
        if not isinstance(row, dict) or not isinstance(row.get("message"), str):
            raise AstError("bad_row", "every row needs a string message", "write")
        message = row["message"]
        if (message == "" and unit.message != "") or "\r" in message or "\0" in message:
            raise AstError("bad_message",
                           "empty message or embedded CR/NUL changes the record", "write")
        if unit.kind != "message":
            if "name" in row or "names" in row:
                raise AstError("name_not_writable",
                               f"{unit.kind} {unit.block}: this unit has no name slot",
                               "write")
            if message == unit.message:
                continue
            if TOKEN_MARK in message and TOKEN_MARK not in unit.message:
                raise AstError("token_mismatch",
                               f"{unit.block}: {TOKEN_MARK!r} is not allowed here",
                               "write")
            edits.append((unit.span[0], unit.span[1],
                          _slot_literal(message, allow_lua_escapes)))
            continue
        renamed = _names_for(unit, row)
        name_edit = _render_name_edit(unit, *renamed, allow_lua_escapes) \
            if renamed is not None else None
        if message == unit.message:
            if name_edit is not None:
                edits.append(name_edit)
            continue
        if unit.boxless:
            raise AstError("bad_message",
                           f"{unit.block}: this entry has a name but no text box",
                           "write")
        segments = _segments(unit, message)
        name_source = None
        if unit.names and not unit.name_outer:
            start, end = unit.name_pair
            name_source = text[start:end]
            if name_edit is not None:
                edit_start, edit_end, replacement = name_edit
                name_source = name_source[:edit_start - start] + replacement + \
                    name_source[edit_end - start:]
        elif name_edit is not None:
            edits.append(name_edit)
        edits.append((unit.span[0], unit.span[1],
                      _render_box(unit, segments, name_source, document.newline,
                                  allow_lua_escapes)))
    return _splice(text, edits)


def _splice(text: str, edits) -> str:
    if not edits:
        return text
    out, previous = [], 0
    for start, end, replacement in sorted(edits):
        if start < previous or end < start or end > len(text):
            raise AstError("overlapping_edit", "internal edit range is invalid", "write")
        out.append(text[previous:start])
        out.append(replacement)
        previous = end
    out.append(text[previous:])
    return "".join(out)


def _skeleton(ast: Value):
    """Block identity outside the text tables, for the post-write comparison."""
    out = []
    for entry in ast.pairs():
        if entry.key.kind != "str" or entry.key.text == "label":
            continue
        block = entry.value
        if block.kind != "table":
            out.append((entry.key.text, "not-a-table"))
            continue
        members = []
        for member in block.items:
            if member.kind == "pair" and member.key.kind == "str":
                key = member.key.text
                if key in ("text", "select"):
                    members.append((key,))
                elif member.value.kind == "table":
                    members.append((key, "table", len(member.value.items)))
                else:
                    members.append((key, member.value.kind, member.value.text))
            elif member.kind == "table":
                members.append((member.tag(), len(member.items)))
            else:
                members.append((member.kind,))
        out.append((entry.key.text, _script_line(block), tuple(members)))
    return tuple(out)


def _outside(document: Document):
    """Source text outside every unit's owned spans, as ordered chunks."""
    chunks, previous = [], 0
    for start, end in sorted(span for unit in document.units for span in unit.owned_spans):
        chunks.append(document.text[previous:start])
        previous = max(previous, end)
    chunks.append(document.text[previous:])
    return chunks


def _verify_rebuild(before: Document, after: Document, rows) -> None:
    """Independent re-parse comparison; a mismatch means the write is not trusted."""
    if len(after.units) != len(before.units):
        raise AstError("verification_failed", "unit count changed after rebuild", "verify")
    if (after.layout, after.selected_language, after.skipped) != \
            (before.layout, before.selected_language, before.skipped):
        raise AstError("verification_failed", "layout or language selection changed",
                       "verify")
    for original, rebuilt, row in zip(before.units, after.units, rows):
        if (rebuilt.kind, rebuilt.block, rebuilt.index) != \
                (original.kind, original.block, original.index):
            raise AstError("verification_failed",
                           f"{original.block}: unit identity changed", "verify")
        if rebuilt.message != row["message"]:
            raise AstError("verification_failed",
                           f"{original.block}: message did not survive the rebuild",
                           "verify")
        if rebuilt.tokens != original.tokens or rebuilt.inline != original.inline:
            raise AstError("verification_failed",
                           f"{original.block}: inline commands changed", "verify")
        expected = _names_for(original, row) if original.kind == "message" else None
        if expected is None:
            expected = (list(original.names), list(original.name_keys))
        if (list(rebuilt.names), list(rebuilt.name_keys)) != \
                (list(expected[0]), list(expected[1])) or \
                rebuilt.name_form != original.name_form:
            raise AstError("verification_failed",
                           f"{original.block}: name slots did not survive the rebuild",
                           "verify")
    if _outside(after) != _outside(before):
        raise AstError("verification_failed",
                       "bytes outside the rewritten units changed", "verify")
    if before.layout == "blocks" and _skeleton(after.ast) != _skeleton(before.ast):
        raise AstError("verification_failed",
                       "non-text structure changed outside the rewritten units", "verify")


def encode_ast(document: Document, text: str, *, encoding=None,
               max_output_size: int = 64 << 20) -> bytes:
    codec = "utf-8-sig" if document.bom else (document.encoding if encoding is None
                                              else encoding)
    try:
        data = text.encode(codec, errors="strict")
    except (UnicodeEncodeError, LookupError) as exc:
        raise AstError("bad_encoding", f"script is not encodable as {codec}",
                       "write") from exc
    if len(data) > max_output_size:
        raise AstError("too_large", "rebuilt script exceeds the byte budget", "write")
    return data


def patch_ast(data, rows, *, encoding=None, language=None,
              extra_inline_tags=frozenset(), lenient_escapes: bool = False,
              allow_lua_escapes: bool = False, max_bytes: int = 64 << 20,
              max_output_size: int = 64 << 20) -> bytes:
    """Reinsert translations into one AST text script.

    Equivalent to ``read_ast(...).patch(rows)``; both re-parse and verify.
    Prefer ``Document.patch`` when the parsed object is still around; the
    keyword arguments here must match the analysis or the units will resolve
    differently.
    """
    document = read_ast(data, encoding=encoding, language=language,
                        extra_inline_tags=extra_inline_tags,
                        lenient_escapes=lenient_escapes, max_bytes=max_bytes)
    return document.patch(rows, allow_lua_escapes=allow_lua_escapes,
                          max_output_size=max_output_size)
