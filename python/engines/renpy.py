"""A deliberately finite Ren'Py .rpy lexer and span-preserving patcher.

Design comparison (not wholesale quote scanning): VNTextPatch-net8 (MIT),
d9c0fab7b72fdcf87d674ef12a84d3829c9188be,
VNTextPatch.Shared/Scripts/RenpyScript.cs, GetRanges; SExtractor (GPL-3.0),
8d8d976fd04ae54e7c677705af937273d04a376a, src/extract_RenPy.py, parseImp.
String semantics follow the Ren'Py 8 script lexer (MIT): say/menu strings
collapse runs of spaces and expand only the Ren'Py escapes; ``translate
strings`` old/new and ``define`` arguments are Python literals. This
implementation is original; it never imports Ren'Py or unpickles rpyc.
"""
import ast
from dataclasses import dataclass
from collections.abc import Mapping, Collection
import re

# Ren'Py's word_regexp: ASCII word characters plus U+00A0..U+FFFD.
WORD = r"[a-zA-Z_\u00a0-\ufffd][0-9a-zA-Z_\u00a0-\ufffd]*"
_WORD = re.compile(WORD)
_NAME_RUN = re.compile(r"[0-9a-zA-Z_\u00a0-\ufffd]+")
_ATTRIBUTE = re.compile(r"[-@0-9a-zA-Z_\u00a0-\ufffd]+")


@dataclass(frozen=True)
class Target:
    start: int
    end: int
    text: str
    role: str
    speaker: str | None
    quote: str
    syntax: str = "say"  # "say": Ren'Py say string; "python": Python literal


@dataclass(frozen=True)
class _Token:
    value: str
    start: int
    end: int
    quote: str = ""
    unknown_escape: bool = False
    raw: str = ""


_RESERVED = frozenset("scene show hide image play queue stop voice sound music jump call return pause window camera with at on text textbutton add use default define python init screen transform style old new menu label translate if elif else while for pass nvl nvlextend".split())
# Speakers predefined by the Ren'Py runtime, valid without a game declaration.
BUILTIN_SPEAKERS = frozenset({"extend", "narrator", "centered", "vcentered", "nvl"})
_CHARACTER_CLASSES = frozenset({"Character", "ADVCharacter", "NVLCharacter", "DynamicCharacter"})
_OPEN, _CLOSE = "([{", ")]}"


def say_value(raw):
    """Value of a non-raw Ren'Py say/menu string body (lexer.string semantics).

    Returns (value, unknown_escape). Escapes other than \\\\ \\" \\' \\space \\n
    \\{ \\[ \\% and \\uXXXX are marked unknown (Ren'Py would drop the backslash).
    """
    unknown = False

    def dequote(m):
        nonlocal unknown
        c = m.group(1)
        if c == "{":
            return "{{"
        if c == "[":
            return "[["
        if c == "%":
            return "%%"
        if c == "n":
            return "\n"
        if c[0] == "u" and m.group(2):
            return chr(int(m.group(2), 16))
        if c not in "\\\"' ":
            unknown = True
        return c

    value = re.sub(r"[ \n]+", " ", raw)
    value = re.sub(r"\\(u([0-9a-fA-F]{1,4})|.)", dequote, value)
    return value, unknown


def encode_say(text, quote='"'):
    """Body for a say/menu string whose say_value() equals ``text``."""
    if "\r" in text or "\0" in text or any(ord(c) < 32 and c not in "\n\t" for c in text):
        raise ValueError("control character cannot be written into a Ren'Py say string")
    body = text.replace("\\", "\\\\").replace("\n", "\\n").replace(quote, "\\" + quote)
    return re.sub(r"(?<= ) ", "\\\\ ", body)


def encode_python(text, quote='"'):
    """Body for a Python string literal (Ren'Py quote_unicode plus quote)."""
    if "\0" in text:
        raise ValueError("NUL cannot be written into a Ren'Py string literal")
    body = text.replace("\\", "\\\\").replace(quote, "\\" + quote)
    for raw, escaped in (("\a", "\\a"), ("\b", "\\b"), ("\f", "\\f"), ("\n", "\\n"),
                         ("\r", "\\r"), ("\t", "\\t"), ("\v", "\\v")):
        body = body.replace(raw, escaped)
    return body


def python_value(token):
    """Python literal value of a lexed string token (literal_eval only)."""
    try:
        value = ast.literal_eval(token.quote + token.raw + token.quote)
    except (ValueError, SyntaxError) as exc:
        raise ValueError("invalid Python string literal in rpy") from exc
    if not isinstance(value, str):
        raise ValueError("expected a text literal")
    return value


def _lex(line):
    tokens = []
    pos = 0
    while pos < len(line):
        c = line[pos]
        if c.isspace():
            pos += 1
        elif c == "#":
            break
        elif c in "\"'`":
            start, quote = pos, c
            if line.startswith(c * 3, pos):
                raise ValueError("multiline/triple-quoted rpy strings are outside this subset")
            pos += 1
            while pos < len(line) and line[pos] != quote:
                if line[pos] == "\\":
                    pos += 1
                    if pos >= len(line):
                        raise ValueError("continued rpy string is unsupported")
                pos += 1
            if pos >= len(line):
                raise ValueError("unterminated rpy string")
            raw = line[start + 1:pos]
            pos += 1
            value, unknown = say_value(raw)
            tokens.append(_Token(value, start, pos, quote, unknown, raw))
        else:
            m = _NAME_RUN.match(line, pos)
            end = m.end() if m else pos + 1
            tokens.append(_Token(line[pos:end], pos, end))
            pos = end
    return tokens


def _depth(tokens, depth):
    for t in tokens:
        if not t.quote and len(t.value) == 1:
            if t.value in _OPEN:
                depth += 1
            elif t.value in _CLOSE:
                depth -= 1
    return depth


def _declaration(tokens):
    """``define alias = Character(...)``: returns (alias, name token or None)."""
    words = [t.value for t in tokens]
    if (len(tokens) < 5 or words[0] != "define" or tokens[1].quote or not _WORD.fullmatch(words[1])
            or words[2] != "=" or words[3] not in _CHARACTER_CLASSES or words[4] != "("):
        return None
    name = None
    if words[3] != "DynamicCharacter":
        rest = tokens[5:]
        if len(rest) >= 2 and rest[0].quote and rest[1].value in (",", ")"):
            name = rest[0]
        elif (len(rest) >= 5 and [t.value for t in rest[:2]] == ["_", "("] and rest[2].quote
              and rest[3].value == ")" and rest[4].value in (",", ")")):
            name = rest[2]
    return tokens[1].value, name


def _say(tokens):
    """Split ``[who attrs] "what" [nointeract] [id x] [with expr]``.

    Returns (prefix tokens, what token) or None when the line is not say-shaped.
    """
    k = next((i for i, t in enumerate(tokens) if t.quote), None)
    if k is None:
        return None
    if k == 0 and len(tokens) > 1 and tokens[1].quote:
        # ``"Display Name" "what"``: a string-literal speaker expression.
        prefix, k = tokens[:1], 1
    else:
        prefix = tokens[:k]
    suffix = tokens[k + 1:]
    if prefix and not prefix[0].quote:
        if not _WORD.fullmatch(prefix[0].value) or prefix[0].quote:
            return None
        if any(t.quote or not _ATTRIBUTE.fullmatch(t.value) for t in prefix[1:]):
            return None
    words = [t.value for t in suffix]
    i = 0
    if i < len(words) and words[i] == "nointeract":
        i += 1
    if i + 1 < len(words) and words[i] == "id" and _WORD.fullmatch(words[i + 1]):
        i += 2
    if i < len(words) and words[i] == "with":
        if i + 1 >= len(words):
            return None
        i = len(words)
    if i != len(words):
        return None
    return prefix, tokens[k]


def characters(script: str) -> dict:
    """Character aliases declared by ``define``: alias -> literal name or None."""
    found = {}
    for full in script.splitlines():
        line = full.strip()
        if not line.startswith("define "):
            continue
        try:
            decl = _declaration(_lex(line))
        except ValueError:
            continue
        if decl:
            alias, token = decl
            name = None
            if token is not None:
                try:
                    name = python_value(token)
                except ValueError:
                    name = None
            found[alias] = name if alias not in found or found[alias] == name else None
    return found


def extract(script: str, *, filename: str = "script.rpy",
            speakers: Collection[str] = (), diagnostics: list | None = None) -> tuple[Target, ...]:
    """Recognize narration, whitelisted say, menu captions and translate/new.

    speakers contains known Character variable IDs from the project, NOT names
    to translate. Character declarations in this file are auto-collected, as
    are the runtime speakers extend/narrator/centered/vcentered/nvl.
    Python/screen/unknown suites and bracket continuation lines are skipped.
    All offsets are Unicode indices. Compiled-only rpyc is rejected, not fed to
    pickle or an external tool. ``diagnostics`` (a list) receives
    ``(line_number, kind, word)`` for say-shaped lines that were NOT exported
    (unknown speaker or say arguments), so callers can extend ``speakers``.
    """
    if not filename.lower().endswith(".rpy"):
        raise ValueError("only source .rpy is supported; .rpyc requires a separate authorized decompiler")
    if "\0" in script:
        raise ValueError("binary/NUL-containing input is not rpy source")
    if script.startswith("\ufeff"):
        raise ValueError("strip the UTF-8 BOM before lexing and restore it on write")
    if any(not _WORD.fullmatch(s) or s in _RESERVED for s in speakers):
        raise ValueError("speaker whitelist must contain variable identifiers")
    lines = []
    stack = []
    offset = 0
    depth = 0
    aliases = set(speakers) | BUILTIN_SPEAKERS
    for number, full in enumerate(script.splitlines(keepends=True), 1):
        line = full.rstrip("\r\n")
        if depth > 0:
            # Continuation of a bracketed logical line: never a text target.
            depth = _depth(_lex(line), depth)
            offset += len(full)
            continue
        indent_text = line[:len(line) - len(line.lstrip(" \t"))]
        if "\t" in indent_text:
            raise ValueError("tab indentation is outside this conservative subset")
        indent = len(indent_text)
        if not line.strip() or line.lstrip().startswith("#"):
            offset += len(full)
            continue
        while stack and indent <= stack[-1][0]:
            stack.pop()
        context = stack[-1][1] if stack else "dialogue"
        if context == "blocked":
            offset += len(full)
            continue
        tokens = _lex(line)
        if not tokens:
            offset += len(full)
            continue
        depth = _depth(tokens, 0)
        if depth < 0:
            raise ValueError(f"unbalanced closing bracket at line {number}")
        words = [t.value for t in tokens]
        kind = None
        if not tokens[0].quote and words[-1] == ":":
            if words[0] == "translate" and len(words) == 4:
                kind = {"strings": "strings", "python": "blocked", "style": "blocked"}.get(words[2], "dialogue")
            elif words[0] == "label":
                kind = "dialogue"
            elif words[0] == "menu" and (len(words) == 2 or (len(words) == 3 and _WORD.fullmatch(words[1]))):
                kind = "menu"
            elif words[0] in ("if", "elif", "else", "while") and context != "strings":
                kind = context
            else:
                kind = "blocked"
        elif tokens[0].quote and words[-1] == ":" and context == "menu" and (len(tokens) == 2 or words[1] == "if"):
            kind = "dialogue"
        decl = _declaration(tokens)
        if decl:
            aliases.add(decl[0])
        lines.append((offset, number, context, tokens, decl))
        if kind is not None:
            stack.append((indent, kind))
        offset += len(full)

    targets = []

    def add(token, offset, role="message", speaker=None, syntax="say"):
        if syntax == "python":
            text = python_value(token)
        else:
            if token.unknown_escape:
                raise ValueError("unknown escape in a translatable rpy string")
            text = token.value
        targets.append(Target(offset + token.start + 1, offset + token.end - 1,
                              text, role, speaker, token.quote, syntax))

    for offset, number, context, tokens, decl in lines:
        words = [t.value for t in tokens]
        if decl:
            if decl[1] is not None:
                add(decl[1], offset, "name", decl[0], "python")
        elif context == "strings":
            if len(tokens) == 2 and words[0] == "new" and tokens[1].quote:
                add(tokens[1], offset, syntax="python")
            # old is a lookup key, deliberately never a translation target.
        elif tokens[0].quote and words[-1] == ":" and context == "menu" and (len(tokens) == 2 or words[1] == "if"):
            add(tokens[0], offset)
        else:
            say = _say(tokens)
            if say is None:
                if (diagnostics is not None and context in ("dialogue", "menu") and not tokens[0].quote
                        and words[0] in aliases and words[0] not in _RESERVED and any(t.quote for t in tokens)):
                    diagnostics.append((number, "unsupported-say-clause", words[0]))
                continue
            prefix, what = say
            if not prefix:
                add(what, offset)
            elif prefix[0].quote:
                python_value(prefix[0])
                add(what, offset, speaker=prefix[0].quote + prefix[0].raw + prefix[0].quote)
            elif prefix[0].value in aliases and (prefix[0].value in BUILTIN_SPEAKERS or prefix[0].value not in _RESERVED):
                add(what, offset, speaker=prefix[0].value)
            elif diagnostics is not None and prefix[0].value not in _RESERVED and context in ("dialogue", "menu"):
                diagnostics.append((number, "unknown-speaker", prefix[0].value))
    return tuple(targets)


def patch(script: str, replacements: Mapping[int, str], *, filename: str = "script.rpy",
          speakers: Collection[str] = ()) -> str:
    """Patch only lexer-proven literal interiors, leaving quotes/comments/EOLs."""
    targets = extract(script, filename=filename, speakers=speakers)
    if any(type(i) is not int or not 0 <= i < len(targets) for i in replacements):
        raise ValueError("unknown rpy target index")
    edits = []
    for i, text in replacements.items():
        if "\0" in text:
            raise ValueError("NUL in translation")
        target = targets[i]
        if target.syntax == "python":
            escaped = encode_python(text, target.quote)
        else:
            escaped = encode_say(text, target.quote)
        edits.append((target.start, target.end, escaped))
    for start, end, text in sorted(edits, reverse=True):
        script = script[:start] + text + script[end:]
    checked = extract(script, filename=filename, speakers=speakers)
    expected = [replacements.get(i, t.text) for i, t in enumerate(targets)]
    if [t.text for t in checked] != expected:
        raise ValueError("rpy read-back differs after patch")
    return script
