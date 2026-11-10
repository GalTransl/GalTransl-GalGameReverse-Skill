"""Artemis AST text scripts: the Lua-table scenario dialect (``.ast``).

Artemis releases ship at least four unrelated script shapes: compiled ``ASB``
trees (:mod:`python.engines.artemis`), line-oriented SCP text
(:mod:`python.engines.artemis_scp`), and this one - a **plain-text Lua table
dump** whose first statement is a version header. A fifth shape (the same file
family, different top-level topology) is detected and rejected on purpose; see
`Old layout`_ below.

Observed grammar (a real multi-volume release; the whole corpus re-serialises
byte for byte)::

    astver = 2.0                    -- header; also seen: astname = "..." or
    astname = "chapter01"           -- neither, when the file starts at ``ast``
    ast = {
        block_00000 = {             -- quoted keys (["0001_00001"] = {) also occur
            {"savetitle", text="第Ⅰ章"},
            {"text"},
            delay = { [1000] = { {"se", id=1, file="se0148"}, }, },
            text = {
                vo = { {"vo", file="fem_shi_00004", ch="shi"}, },
                ja = {
                    {
                        name = {"静流"},
                        "「そうですか。",
                        {"ruby", text="つぶらぎ"},
                        "円木",
                        {"/ruby"},
                        "ちゃんが店長してた時からの常連さんですか？」",
                        {"rt2"},
                    },
                },
            },
            linkback = "block_00008",
            linknext = "block_00010",
            line = 150,
        },
        label = { top = { block = "block_00000", label=1 }, },
    }

Dialogue lives in ``text.<language>``; one element is one message box. Values
are Lua: quoted strings, ``[[long strings]]``, integers/floats, ``nil``, and
tables whose members are values or ``key = value`` pairs (bare ``name`` keys and
bracketed ``[1] = ...`` keys both occur). The ``label`` table maps labels to
blocks and carries no text.

Rendering model, and why it matters
-----------------------------------

``{"rt2"}`` terminates one rendered line, so a box's text is its literal
fragments joined by a line break. A shipped Chinese patch confirms the
equivalence: it rewrote ``"A", {"rt2"}, "B", {"rt2"}`` as the single literal
``"A\nB", {"rt2"}`` - the separator count is unchanged, only its spelling is.
This module writes exactly that normalised spelling (keeping whichever
line-break tag the box already used), and re-emits inline commands at their
original per-line position when the translation keeps the line count.

``{"ruby", ...}``/``{"/ruby"}`` carry furigana for the following fragment and
own no literal. So do ``{"exfont" ...}``/``{"txkey"}``/``{"txruby"}``. A
rewritten box cannot move a furigana annotation onto different characters, so
furigana is dropped and reported through the locator; inline commands are
preserved where the line count allows and reported either way. Nothing is
dropped silently.

Name slots
----------

``name = {"A", "B"}`` follows the ASB ``name`` command: slot 0 is the fixed
character identity (official multi-language data keeps it untranslated while
the last slot changes per language), and the **last slot is the display name**.
Rows export only the display slot as ``name``; the identity is reported in the
locator as ``name_identity`` and never rewritten. A lone slot gains an appended
display slot (``{"A"} -> {"A", "译名"}``) instead of being overwritten. The
language-keyed form ``name = { name="...", ja="..." }`` uses the same rule with
its keys preserved; a lone keyed slot is ``context`` because an appended slot
would need an invented key.

Old layout
----------

Some releases keep the text tables outside the blocks: the ``ast`` table holds
numeric-keyed blocks plus one top-level ``text`` table indexed ``[1]..[n]``,
with ``select`` nested inside it. That topology is detected (no
``label.top.block``, but a top-level ``text`` table) and rejected with
``old_layout`` instead of being guessed at; this module was never validated
against it.

Known boundaries: no game startup, no font/glyph work, no container handling,
and no proof that the engine accepts a rewritten file. Escapes are written only
as ``\\n`` unless ``allow_lua_escapes`` is passed, because the shipped patch
proves ``\\n`` is accepted and proves nothing about ``\\\\`` or ``\\"``.
"""

from dataclasses import dataclass, field
import codecs
import re

#: Header statements accepted before ``ast = {``.
HEADER_KEYS = ("astver", "astname")
#: ``astver`` values this module claims to handle.
SUPPORTED_VERSIONS = ("2.0",)
#: Tags that terminate a rendered line (msg-tool maps both to a newline).
LINE_BREAK_TAGS = frozenset({"rt2", "ret2"})
#: Inline commands that own no literal; extend per game via ``extra_inline_tags``.
INLINE_TAGS = frozenset({"exfont", "txkey", "txruby"})
#: ``text``/``select`` members that are never the language table.
NON_LANGUAGE_KEYS = re.compile(r"(?:vo|vl\d+|lv\d+)\Z")
_SPACE = " \t\r\n"
_PUNCT = "{}()[],="
_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?\Z")
_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_DIGITS_RE = re.compile(r"\d{1,3}")
_HEX_RE = re.compile(r"u\{([0-9a-fA-F]{1,6})\}|u([0-9a-fA-F]{4})|x([0-9a-fA-F]{2})")


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

    kind: str                      # "str" | "int" | "float" | "null" | "pair" | "table"
    start: int
    end: int
    text: str | None = None        # decoded string, or the raw literal for numbers
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
            if token.raw != "nil":
                raise AstError("unexpected_token", f"unexpected bare token {token.raw!r}")
            self.take()
            return Value("null", token.start, token.end)
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
    """One translatable unit: a message box, a choice option or a chapter title."""

    kind: str                   # "message" | "choice" | "title"
    block: str
    index: int
    script_line: int | None
    span: tuple                 # (start, end) of the text a rewrite replaces
    message: str
    names: tuple = ()
    name_keys: tuple = ()       # per slot: the pair key when the name table is keyed
    furigana: tuple = ()
    inline: tuple = ()
    lines: int = 1
    # message boxes only
    indent: str = ""
    close_indent: str = ""
    trailing_break: bool = False
    break_tag: str = "rt2"
    blank_lines: bool = False   # the box separates statements with an empty line
    line_lead: tuple = ()       # per rendered line: inline command source slices
    line_tail: tuple = ()
    line_has_text: tuple = ()
    name_spans: tuple = ()      # per slot: (start, end) of the string literal

    @property
    def display_name(self):
        """Last slot: the text shown in the name box (``None`` for narration)."""
        return self.names[-1] if self.names else None

    @property
    def identity_name(self):
        """Slot 0: the fixed character identity; read-only context."""
        return self.names[0] if self.names else None

    @property
    def name_policy(self) -> str:
        if not self.names:
            return "absent"
        # A lone keyed slot has no key to give an appended display slot.
        if len(self.names) == 1 and self.name_keys[0] is not None:
            return "context"
        return "writable"


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
        return [{"kind": unit.kind, "block": unit.block, "index": unit.index,
                 "script_line": unit.script_line, "span": [unit.span[0], unit.span[1]],
                 "source_lines": unit.lines, "name_slots": len(unit.names),
                 "name_identity": unit.identity_name,
                 "furigana": list(unit.furigana), "inline_commands": list(unit.inline)}
                for unit in self.units]

    def name_policies(self):
        return [unit.name_policy for unit in self.units]

    def protected_tokens(self):
        return [[] for _ in self.units]

    def patch(self, rows, *, allow_lua_escapes: bool = False,
              max_output_size: int = 64 << 20) -> bytes:
        """Rebuild the source bytes from ``rows`` and verify them by re-parsing.

        The output is read back with this document's own encoding, language,
        ``extra_inline_tags`` and ``lenient_escapes``, then compared unit by unit
        and against the non-text skeleton; any mismatch raises
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


def _pick_language(table: Value, language=None):
    """First table member that is not a voice table, in declared order.

    Same rule as msg-tool: ``vo`` and the ``vlNN``/``lvN`` voice layers are not
    text. ``language`` overrides the search when a caller already knows the key.
    """
    for item in table.items:
        if item.kind != "pair" or item.key.kind != "str":
            continue
        key = item.key.text
        if not isinstance(key, str) or key == "name" or NON_LANGUAGE_KEYS.match(key):
            continue
        if language is not None and key != language:
            continue
        return key, item.value
    return None, None


def _name_slots(box: Value):
    pairs = [item for item in box.items if item.kind == "pair"
             and item.key.kind == "str" and item.key.text == "name"]
    if len(pairs) > 1:
        raise AstError("duplicate_name", "message box declares name more than once")
    if not pairs:
        return (), (), ()
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
    return tuple(names), tuple(keys), tuple(spans)


def _read_box(text, block_name, block, box, index, extra_inline):
    names, name_keys, name_spans = _name_slots(box)
    furigana, inline, parts = [], [], []
    for element in box.items:
        if element.kind == "pair":
            if element.key.kind == "str" and element.key.text == "name":
                continue
            raise AstError("unknown_element",
                           f"{block_name}: unexpected key "
                           f"{element.key.text!r} inside a message box")
        if element.kind == "str":
            parts.append(("text", element.text, ""))
            continue
        if element.kind != "table":
            raise AstError("bad_message",
                           f"{block_name}: box member is not a string or a command")
        tag = element.tag()
        if tag is None:
            raise AstError("bad_message", f"{block_name}: box command has no tag")
        if tag in LINE_BREAK_TAGS:
            parts.append(("break", tag, ""))
        elif tag == "ruby":
            reading = element.get("text")
            furigana.append(reading.text if reading is not None and reading.is_str() else "")
        elif tag == "/ruby":
            continue
        elif tag in INLINE_TAGS or tag in extra_inline:
            inline.append(tag)
            parts.append(("inline", tag, text[element.start:element.end]))
        else:
            raise AstError("unknown_inline",
                           f"{block_name}: unknown inline tag {tag!r}; pass it in "
                           "extra_inline_tags when it owns no literal")
    if not parts and not names:
        raise AstError("empty_box", f"{block_name}: message box is empty")
    groups = [[]]
    for part in parts:
        if part[0] == "break":
            groups.append([])
        else:
            groups[-1].append(part)
    trailing = bool(parts) and parts[-1][0] == "break"
    content = groups[:-1] if trailing else groups
    lead, tail, has_text, line_texts = [], [], [], []
    for group in content:
        at = [position for position, part in enumerate(group) if part[0] == "text"]
        lead.append(tuple(part[2] for part in group[:at[0]] if part[0] == "inline")
                    if at else tuple(part[2] for part in group if part[0] == "inline"))
        tail.append(tuple(part[2] for part in group[at[-1] + 1:] if part[0] == "inline")
                    if at else ())
        has_text.append(bool(at))
        line_texts.append("".join(part[1] for part in group if part[0] == "text"))
    breaks = [part[1] for part in parts if part[0] == "break"]
    head = text[box.start + 1:box.items[0].start]
    return Unit("message", block_name, index, _script_line(block),
                (box.start + 1, box.end - 1), "\n".join(line_texts),
                names, name_keys, tuple(furigana), tuple(inline), len(breaks),
                _indent_of(text, box.items[0].start), _indent_of(text, box.end - 1),
                trailing, breaks[0] if breaks else "rt2", head.count("\n") > 1,
                tuple(lead), tuple(tail), tuple(has_text), name_spans)


def _read_units(text, ast, extra_inline, language):
    if ast.kind != "table":
        raise AstError("bad_structure", "the ast statement is not a table")
    label = ast.get("label")
    if label is None or label.kind != "table" or label.get("top") is None:
        if ast.get("text") is not None:
            raise AstError("old_layout",
                           "text tables live outside the blocks here; the old "
                           "top-level layout is not implemented")
        raise AstError("missing_label",
                       "the ast table has no label.top entry (unknown layout)")
    names = set()
    for entry in ast.items:
        if entry.kind != "pair" or entry.key.kind != "str":
            raise AstError("bad_structure", "the ast table may only hold named tables")
        if entry.key.text in names:
            raise AstError("duplicate_key", f"top-level table {entry.key.text!r} repeats")
        names.add(entry.key.text)
    # Any string key is a block; its name is whatever label.top.block /
    # linknext refer to. Bare ``block_00000`` and quoted ``["0001_00001"]``
    # keys both occur, so no name prefix is required.
    units = []
    for entry in ast.items:
        name = entry.key.text
        if name == "label":
            continue
        block = entry.value
        if block.kind != "table":
            raise AstError("bad_structure", f"{name} is not a table")
        line = _script_line(block)
        for key, kind in (("text", "message"), ("select", "choice")):
            table = _only_pair(block, key)
            if table is None:
                continue
            if table.kind != "table":
                raise AstError("bad_structure", f"{name}: {key} is not a table")
            chosen, members = _pick_language(table, language)
            if members is None:
                raise AstError("no_language_table",
                               f"{name}: {key} declares no language table")
            if members.kind != "table":
                raise AstError("bad_structure", f"{name}: {key}[{chosen}] is not a table")
            for index, member in enumerate(members.items):
                if kind == "message":
                    if member.kind != "table":
                        raise AstError("bad_message",
                                       f"{name}: text[{chosen}] member is not a box")
                    units.append(_read_box(text, name, block, member, index, extra_inline))
                else:
                    if member.kind != "str":
                        raise AstError("bad_select",
                                       f"{name}: select option is not a string literal")
                    units.append(Unit("choice", name, index, line,
                                      (member.start, member.end), member.text))
        title = block.find_tag("savetitle")
        if title is not None:
            value = title.get("text")
            if value is None or not value.is_str():
                raise AstError("bad_title", f"{name}: savetitle has no string text")
            units.append(Unit("title", name, 0, line, (value.start, value.end), value.text))
    units.sort(key=lambda unit: unit.span[0])
    return tuple(units)


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
    units = _read_units(text, ast, frozenset(extra_inline_tags), language)
    return Document(path=path, encoding=codec, bom=bom,
                    newline="\r\n" if "\r\n" in text else "\n", astver=astver,
                    astname=astname, ast=ast, units=units, text=text,
                    language=language, extra_inline_tags=frozenset(extra_inline_tags),
                    lenient_escapes=lenient_escapes)


# ------------------------------------------------------------------- writing


def _slot_literal(value, allow_lua_escapes):
    return '"' + escape_lua(value, allow_lua_escapes=allow_lua_escapes) + '"'


def _render_box(unit: Unit, message: str, names, newline: str,
                allow_lua_escapes: bool) -> str:
    gap = newline * (2 if unit.blank_lines else 1)
    body = ""
    if names is not None:
        rendered = []
        for position, slot in enumerate(names):
            key = unit.name_keys[position] if position < len(unit.name_keys) else None
            literal = _slot_literal(slot, allow_lua_escapes)
            rendered.append(f"{key} = {literal}" if key else literal)
        body += gap + unit.indent + "name = {" + ", ".join(rendered) + "},"
    lines = message.split("\n")
    structured = bool(unit.inline) and len(lines) == len(unit.line_lead)
    if structured:
        for position, line_text in enumerate(lines):
            for raw in unit.line_lead[position]:
                body += gap + unit.indent + raw + ","
            if line_text or unit.line_has_text[position]:
                body += gap + unit.indent + _slot_literal(line_text,
                                                          allow_lua_escapes) + ","
            for raw in unit.line_tail[position]:
                body += gap + unit.indent + raw + ","
            if unit.trailing_break or position < len(lines) - 1:
                body += gap + unit.indent + '{"' + unit.break_tag + '"},'
    else:
        body += gap + unit.indent + _slot_literal(message, allow_lua_escapes) + ","
        if unit.trailing_break:
            body += gap + unit.indent + '{"' + unit.break_tag + '"},'
    return body + gap + unit.close_indent


def _names_for(unit: Unit, row):
    """Full slot list after applying ``row["name"]``, or ``None`` when unchanged.

    Slot 0 is the character identity and is never rewritten; the last slot is
    the display name. A lone slot gains an appended display slot instead of
    being overwritten - the same rule as the ASB ``name`` command.
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
                       "a lone keyed name slot is identity only; no display slot "
                       "can be added without inventing a key", "write")
    if len(unit.names) == 1:
        return [unit.names[0], name]
    return list(unit.names[:-1]) + [name]


def _render_name_edit(unit: Unit, names, allow_lua_escapes: bool):
    """Minimal edit: replace the display literal, or append one after slot 0."""
    literal = _slot_literal(names[-1], allow_lua_escapes)
    if len(names) > len(unit.names):
        end = unit.name_spans[-1][1]
        return end, end, ", " + literal
    start, end = unit.name_spans[-1]
    return start, end, literal


def render(document: Document, rows, *, allow_lua_escapes: bool = False) -> str:
    """Apply ``message``/``name`` from ``rows``; every other byte is preserved.

    Only units whose text or names actually differ are rewritten, so an
    unchanged export reproduces the file byte for byte.
    """
    if len(rows) != len(document.units):
        raise AstError("row_count", "row count differs from the parsed units", "write")
    edits = []
    for unit, row in zip(document.units, rows):
        if not isinstance(row, dict) or not isinstance(row.get("message"), str):
            raise AstError("bad_row", "every row needs a string message", "write")
        message = row["message"]
        if (message == "" and unit.message != "") or "\r" in message or "\0" in message:
            raise AstError("bad_message",
                           "empty message or embedded CR/NUL changes the record", "write")
        if unit.kind == "message":
            names = _names_for(unit, row)
            if message == unit.message:
                if names is not None:
                    edits.append(_render_name_edit(unit, names, allow_lua_escapes))
                continue
            if not message and not unit.line_has_text:
                raise AstError("bad_message", f"{unit.block}: refusing to blank a box",
                               "write")
            effective = names if names is not None else (
                list(unit.names) if unit.names else None)
            replacement = _render_box(unit, message, effective,
                                      document.newline, allow_lua_escapes)
        else:
            if "name" in row or "names" in row:
                raise AstError("name_not_writable",
                               f"{unit.kind} {unit.block}: this unit has no name slot",
                               "write")
            if message == unit.message:
                continue
            replacement = _slot_literal(message, allow_lua_escapes)
        edits.append((unit.span[0], unit.span[1], replacement))
    return _splice(document.text, edits)


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


def _verify_rebuild(before: Document, after: Document, rows) -> None:
    """Independent re-parse comparison; a mismatch means the write is not trusted."""
    if len(after.units) != len(before.units):
        raise AstError("verification_failed", "unit count changed after rebuild", "verify")
    for original, rebuilt, row in zip(before.units, after.units, rows):
        if rebuilt.message != row["message"]:
            raise AstError("verification_failed",
                           f"{original.block}: message did not survive the rebuild",
                           "verify")
        expected = _names_for(original, row) if original.kind == "message" else None
        if expected is None:
            expected = list(original.names)
        if list(rebuilt.names) != list(expected) or \
                list(rebuilt.name_keys[:len(original.name_keys)]) != list(original.name_keys):
            raise AstError("verification_failed",
                           f"{original.block}: name slots did not survive the rebuild",
                           "verify")
        if (rebuilt.kind, rebuilt.block, rebuilt.index) != \
                (original.kind, original.block, original.index):
            raise AstError("verification_failed",
                           f"{original.block}: unit identity changed", "verify")
    if _skeleton(after.ast) != _skeleton(before.ast):
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
