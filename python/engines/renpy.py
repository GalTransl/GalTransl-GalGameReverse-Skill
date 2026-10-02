"""A deliberately finite Ren'Py .rpy lexer and span-preserving patcher.

Design comparison (not wholesale quote scanning): VNTextPatch-net8 (MIT),
d9c0fab7b72fdcf87d674ef12a84d3829c9188be,
VNTextPatch.Shared/Scripts/RenpyScript.cs, GetRanges; SExtractor (GPL-3.0),
8d8d976fd04ae54e7c677705af937273d04a376a, src/extract_RenPy.py, parseImp.
This implementation is original; it never imports Ren'Py or unpickles rpyc.
"""
from dataclasses import dataclass
from collections.abc import Mapping, Collection
import re


@dataclass(frozen=True)
class Target:
    start: int
    end: int
    text: str
    role: str
    speaker: str | None
    quote: str


@dataclass(frozen=True)
class _Token:
    value: str
    start: int
    end: int
    quote: str = ""
    unknown_escape: bool = False


_RESERVED = frozenset("scene show hide image play queue stop voice sound music jump call return pause window camera with at on text textbutton add use default define python init screen transform style old new menu label translate if elif else while for pass nvl nvlextend".split())
_ESCAPES = {"n": "\n", "r": "\r", "t": "\t", "\\": "\\", "'": "'", '"': '"'}


def _lex(line):
    tokens = []
    pos = 0
    while pos < len(line):
        c = line[pos]
        if c.isspace():
            pos += 1
        elif c == "#":
            break
        elif c in "\"'":
            start, quote = pos, c
            if line.startswith(c * 3, pos):
                raise ValueError("multiline/triple-quoted rpy strings are outside this subset")
            pos += 1
            value = []
            unknown = False
            while pos < len(line) and line[pos] != quote:
                c = line[pos]
                if c == "\\":
                    pos += 1
                    if pos >= len(line):
                        raise ValueError("continued rpy string is unsupported")
                    esc = line[pos]
                    if esc not in _ESCAPES:
                        unknown = True
                    value.append(_ESCAPES.get(esc, "\\" + esc))
                else:
                    value.append(c)
                pos += 1
            if pos >= len(line):
                raise ValueError("unterminated rpy string")
            pos += 1
            tokens.append(_Token("".join(value), start, pos, quote, unknown))
        else:
            m = re.match(r"[A-Za-z_]\w*", line[pos:])
            end = pos + len(m[0]) if m else pos + 1
            tokens.append(_Token(line[pos:end], pos, end))
            pos = end
    return tokens


def _declaration(tokens):
    # Only exact define alias = Character("display name"); no executable args.
    return (len(tokens) == 7 and [t.value for t in tokens[:1]] == ["define"]
            and not tokens[1].quote and re.fullmatch(r"[A-Za-z_]\w*", tokens[1].value)
            and [t.value for t in tokens[2:5]] == ["=", "Character", "("]
            and bool(tokens[5].quote) and tokens[6].value == ")")


def extract(script: str, *, filename: str = "script.rpy",
            speakers: Collection[str] = ()) -> tuple[Target, ...]:
    """Recognize narration, whitelisted say, menu captions and translate/new.

    speakers contains known Character variable IDs from the project, NOT names
    to translate. Exact Character declarations in this file are auto-collected.
    Python/screen/unknown suites are skipped. All offsets are Unicode indices.
    Compiled-only rpyc is rejected, not fed to pickle or an external tool.
    """
    if not filename.lower().endswith(".rpy"):
        raise ValueError("only source .rpy is supported; .rpyc requires a separate authorized decompiler")
    if "\0" in script:
        raise ValueError("binary/NUL-containing input is not rpy source")
    if any(not re.fullmatch(r"[A-Za-z_]\w*", s) or s in _RESERVED for s in speakers):
        raise ValueError("speaker whitelist must contain variable identifiers")
    lines = []
    stack = []
    offset = 0
    aliases = set(speakers)
    for full in script.splitlines(keepends=True):
        line = full.rstrip("\r\n")
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
        words = [t.value for t in tokens]
        kind = None
        if not tokens[0].quote and words[-1] == ":":
            if words[0] == "translate" and len(words) == 4:
                kind = "strings" if words[2] == "strings" else "dialogue"
            elif words[0] == "label":
                kind = "dialogue"
            elif words[0] == "menu" and len(words) == 2:
                kind = "menu"
            elif words[0] in ("if", "elif", "else", "while") and context != "strings":
                kind = context
            else:
                kind = "blocked"
        elif tokens[0].quote and len(tokens) == 2 and words[1] == ":" and context == "menu":
            kind = "dialogue"
        if _declaration(tokens):
            aliases.add(tokens[1].value)
        lines.append((offset, context, tokens))
        if kind is not None:
            stack.append((indent, kind))
        offset += len(full)

    targets = []

    def add(token, offset, role="message", speaker=None):
        if token.unknown_escape:
            raise ValueError("unknown escape in a translatable rpy string")
        targets.append(Target(offset + token.start + 1, offset + token.end - 1,
                              token.value, role, speaker, token.quote))

    for offset, context, tokens in lines:
        words = [t.value for t in tokens]
        if _declaration(tokens):
            add(tokens[5], offset, "name", tokens[1].value)
        elif context == "strings":
            if len(tokens) == 2 and words[0] == "new" and tokens[1].quote:
                add(tokens[1], offset)
            # old is a lookup key, deliberately never a translation target.
        elif len(tokens) == 1 and tokens[0].quote:
            add(tokens[0], offset)
        elif len(tokens) == 2 and tokens[0].quote and tokens[1].value == ":" and context == "menu":
            add(tokens[0], offset)
        elif len(tokens) >= 2 and not tokens[0].quote and words[0] in aliases and words[0] not in _RESERVED and tokens[-1].quote:
            if all(not t.quote and re.fullmatch(r"[A-Za-z_]\w*", t.value) for t in tokens[:-1]):
                add(tokens[-1], offset, speaker=words[0])
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
        escaped = text.replace("\\", "\\\\").replace(target.quote, "\\" + target.quote)
        escaped = escaped.replace("\r", "\\r").replace("\n", "\\n").replace("\t", "\\t")
        edits.append((target.start, target.end, escaped))
    for start, end, text in sorted(edits, reverse=True):
        script = script[:start] + text + script[end:]
    return script
