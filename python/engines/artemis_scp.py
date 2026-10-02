"""Artemis Engine SCP plain-text scenario reference (``.txt``/``.iet``).

Artemis releases ship two unrelated script shapes:

* compiled ``ASB`` trees (see ``python/engines/artemis.py``), and
* **SCP text scripts**: a line-oriented UTF-8 text format that carries the actual
  dialogue. ``.txt`` is not automatically text and ``.iet`` is not automatically
  ASB; the content decides.

Observed grammar (real release by *しろくまだんご*, tag schema from its
``tag.ini``; corroborated by msg-tool's Artemis TXT builders, GPL-3.0-or-later):

    //  or  ;        comment (``;`` also comments out tags/commands)
    *label           label
    [tag attr="v"]   command; only the tag name and quoted ``attr="value"`` pairs
                     are interpreted, anything after ``]`` is left untouched
    #name a,b        line tag injected by ``[&linetag prefix="#"]`` - never dialogue
    (blank)          message separator
    other            dialogue or narration text

A message is a maximal run of text lines. A run whose first line starts with an
opening quote (``「『（(``) is spoken; the speaker is the most recent speaker
command, which persists until another speaker command or an unknown-speaker tag
appears. A tag that is declared in ``tag.ini`` (for example ``var``, which also
takes ``name``) is always a command, never a speaker.

Speaker evidence, strongest first:

1. ``name="..."`` on the command - the display text itself (policy ``writable``).
2. a voice attribute (``file``/``voice``) and no other attribute keys - the tag
   name is the character key (policy ``context``); observed as
   ``[幸枝 file="sachie_t23"]``.
3. a bare non-ASCII tag that is no declared command - an **unknown** speaker: the
   record keeps no name (policy ``absent``) but the stale speaker is cleared, so a
   later line can never inherit the previous character's name. ``[主人公]`` is
   this case; pass it in ``speaker_tags`` to expose it as a context name.

Anything else is an ordinary command and does not touch the speaker, so a
``[背景 ...]`` between two lines does not steal the attribution.

Inline directives inside text lines (``[ルビ rb="漢/かん"]``, ``[恋人呼称
chara="..."]``) are reported as protected tokens and must survive translation
unchanged. The opening/closing quotes are structural: a translated line that no
longer starts with an opening quote silently becomes narration, so
:func:`patch_script` rejects it.

Name policies follow ``guides/roundtrip-contract.md``: ``writable`` when the
display name is the command's own ``name`` attribute, ``context`` when only the
tag name is available (the engine resolves it at runtime), ``absent`` for
narration. No discovery of dialogue beyond this grammar, and no game startup.
"""

from dataclasses import dataclass
import re

#: Line prefixes that are never text.
COMMENT_PREFIXES = ("//", ";")
LABEL_PREFIX = "*"
LINE_TAG_PREFIX = "#"
COMMAND_OPEN = "["
COMMAND_CLOSE = "]"
#: Characters that make a text run spoken.
OPEN_QUOTES = ("「", "『", "（", "(")
SPEAKER_ATTRIBUTE = "name"
#: Voice attributes that mark a character tag when they are the only keys.
VOICE_ATTRIBUTES = ("file", "voice")
#: Commands known to take ``name`` without being a speaker, used when no tag.ini
#: is supplied. tag.ini supersedes this list by naming the real command tags.
DEFAULT_COMMAND_TAGS = frozenset({"var", "macro"})
INLINE_RE = re.compile(r"\[[^\[\]\r\n]*\]")
_ATTR_RE = re.compile(r'([^\s=\]"]+)\s*=\s*"([^"]*)"')
_SECTION_RE = re.compile(r"^\[([^\]]*)\]")


class ScpError(ValueError):
    """Rejected script or translation, with a machine-readable code and stage."""

    def __init__(self, code: str, message: str, stage: str = "parse"):
        super().__init__(message)
        self.code = code
        self.stage = stage


@dataclass(frozen=True)
class TagSchema:
    """Tag names and attribute order declared by an Artemis ``tag.ini``."""

    tags: frozenset = frozenset()
    attributes: dict = None

    @classmethod
    def parse(cls, data: bytes, *, encoding: str = "utf-8"):
        try:
            text = data.decode(encoding, errors="strict")
        except (UnicodeDecodeError, LookupError) as exc:
            raise ScpError("tag_ini_encoding", "tag.ini is not decodable", "schema") from exc
        tags, attributes, current = set(), {}, None
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith(";"):
                continue
            section = _SECTION_RE.match(line)
            if section:
                current = section.group(1).strip()
                tags.add(current)
                attributes.setdefault(current, [])
                continue
            if current is not None and "=" in line:
                _, _, value = line.partition("=")
                value = value.strip()
                if value and value not in attributes[current]:
                    attributes[current].append(value)
        return cls(frozenset(tags), {key: tuple(value) for key, value in attributes.items()})


@dataclass(frozen=True)
class Record:
    ordinal: int
    kind: str                      # "dialogue" | "narration"
    line_start: int
    line_end: int                  # exclusive
    text: str
    name: str | None
    name_policy: str               # "absent" | "context" | "writable"
    speaker_tag: str | None
    speaker_line: int | None
    tokens: tuple = ()


@dataclass(frozen=True)
class Script:
    text: str
    encoding: str
    bom: bool
    newline: str
    lines: tuple
    records: tuple
    tag_schema: TagSchema | None = None
    #: Speaker policy this script was parsed with; `patch` reuses it so a rebuild
    #: can never silently disagree with the analysis.
    speaker_tags: frozenset = frozenset()
    command_tags: frozenset = frozenset()

    def rows(self):
        """Minimal GalTransl-compatible rows in document order."""
        result = []
        for record in self.records:
            row = {"message": record.text}
            if record.name is not None:
                row["name"] = record.name
            result.append(row)
        return result

    def locators(self):
        return [{"kind": record.kind, "line_start": record.line_start,
                 "line_end": record.line_end, "speaker_tag": record.speaker_tag,
                 "speaker_line": record.speaker_line,
                 "message_lines": record.line_end - record.line_start}
                for record in self.records]

    def name_policies(self):
        return [record.name_policy for record in self.records]

    def protected_tokens(self):
        return [list(record.tokens) for record in self.records]

    def patch(self, rows, *, max_output_size: int = 64 << 20) -> bytes:
        """Rebuild the source bytes from ``rows`` under this script's own policy.

        Prefer this over :func:`patch_script`: handing back the parsed object
        keeps `tag_schema`/`speaker_tags`/`command_tags` consistent, which is the
        one way a rebuild can disagree with the analysis while looking correct.
        """
        rebuilt = encode_script(self, render(self, rows), max_output_size=max_output_size)
        verified = read_script(rebuilt, encoding=self.encoding, tag_schema=self.tag_schema,
                               speaker_tags=self.speaker_tags, command_tags=self.command_tags)
        _verify_rebuild(self, verified, rows)
        return rebuilt


def _decode(data, encoding):
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise ScpError("input_type", "script input must be bytes", "input")
    data = bytes(data)
    if encoding is not None:
        candidates = (encoding,)
    else:
        candidates = ("utf-8", "cp932")
    failure = None
    for candidate in candidates:
        try:
            codec = "utf-8-sig" if candidate == "utf-8" and data[:3] == b"\xef\xbb\xbf" else candidate
            return data.decode(codec, errors="strict"), candidate, codec == "utf-8-sig"
        except (UnicodeDecodeError, LookupError) as exc:
            failure = exc
    raise ScpError("script_encoding", "script is not valid text in any candidate codec", "input") from failure


def line_kind(line: str) -> str:
    """Classify one raw line: blank/comment/label/tag/command/text."""
    stripped = line.strip()
    if not stripped:
        return "blank"
    if stripped.startswith(COMMENT_PREFIXES):
        return "comment"
    if stripped.startswith(LABEL_PREFIX):
        return "label"
    if stripped.startswith(LINE_TAG_PREFIX):
        return "linetag"
    if stripped.startswith(COMMAND_OPEN):
        return "command"
    return "text"


def _scan_command(text: str):
    """Return (tag, attributes) for a command line, or None when malformed.

    A ``]`` inside a quoted attribute value does not end the tag.
    """
    index = text.index(COMMAND_OPEN) + 1
    while index < len(text) and not text[index].isspace() and text[index] != COMMAND_CLOSE:
        index += 1
    tag = text[text.index(COMMAND_OPEN) + 1:index]
    if not tag:
        return None
    quoted = False
    while index < len(text):
        char = text[index]
        if char == '"':
            quoted = not quoted
        elif char == COMMAND_CLOSE and not quoted:
            break
        index += 1
    body = text[text.index(COMMAND_OPEN) + 1:index if index < len(text) else len(text)]
    return tag, dict(_ATTR_RE.findall(body))


def looks_like_script(data, *, encoding=None, max_lines: int = 40) -> bool:
    """Weak content probe: enough SCP structure to justify selecting this reader."""
    try:
        text, _encoding, _bom = _decode(data, encoding)
    except ScpError:
        return False
    if text[:5] == "ASB\x00\x00" or text[:4] == "ASB\x00":
        return False
    kinds = {}
    for line in text.splitlines()[:max_lines]:
        kinds[line_kind(line)] = kinds.get(line_kind(line), 0) + 1
    commands = kinds.get("command", 0)
    text_lines = kinds.get("text", 0)
    return commands + text_lines + kinds.get("comment", 0) + kinds.get("linetag", 0) >= 3 \
        and text_lines + commands >= 2 and kinds.get("label", 0) + kinds.get("command", 0) >= 1


def read_script(data, *, encoding=None, tag_schema=None, speaker_tags=frozenset(),
                command_tags=frozenset(), max_bytes: int = 64 << 20,
                max_lines: int = 2_000_000) -> Script:
    """Parse one SCP text script into ordered records; no filesystem access.

    ``speaker_tags`` forces the named tags to be speakers, which is how a bare
    character tag whose display name the engine resolves at runtime (``[主人公]``)
    becomes a context name; it also wins over the built-in command set.
    ``command_tags`` adds tags that must never be read as speakers.
    ``tag_schema`` supplies the archive's own tag.ini.
    """
    if len(bytes(data)) > max_bytes:
        raise ScpError("script_budget", "script exceeds the input byte budget", "input")
    text, used_encoding, bom = _decode(data, encoding)
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(newline)
    if len(lines) > max_lines:
        raise ScpError("script_budget", "script exceeds the line budget", "input")
    pinned = set(speaker_tags)
    excluded = set(DEFAULT_COMMAND_TAGS) | set(command_tags)
    if tag_schema is not None:
        excluded |= set(tag_schema.tags)
    excluded -= pinned

    records = []
    speaker = None      # (tag, display name or None, policy, line index or None)
    index, total = 0, len(lines)
    while index < total:
        kind = line_kind(lines[index])
        if kind == "command":
            parsed = _scan_command(lines[index])
            if parsed is not None:
                tag, attributes = parsed
                keys = set(attributes)
                if tag in pinned:
                    if SPEAKER_ATTRIBUTE in attributes:
                        speaker = (tag, attributes[SPEAKER_ATTRIBUTE], "writable", index)
                    else:
                        speaker = (tag, tag, "context", None)
                elif tag in excluded:
                    pass
                elif SPEAKER_ATTRIBUTE in attributes:
                    speaker = (tag, attributes[SPEAKER_ATTRIBUTE], "writable", index)
                elif keys and not tag.isascii() and keys <= set(VOICE_ATTRIBUTES):
                    speaker = (tag, tag, "context", None)
                elif not keys and not tag.isascii():
                    # A bare character tag we cannot name: clear the stale speaker
                    # so a later line never inherits the previous character.
                    speaker = (tag, None, "absent", None)
            index += 1
            continue
        if kind != "text":
            index += 1
            continue
        start = index
        while index < total and line_kind(lines[index]) == "text":
            index += 1
        body = lines[start:index]
        quoted = body[0].lstrip().startswith(OPEN_QUOTES)
        if quoted and speaker is not None:
            name, policy, speaker_line = speaker[1], speaker[2], speaker[3]
        else:
            name, policy, speaker_line = None, "absent", None
        tokens = tuple(dict.fromkeys(match.group(0) for line in body for match in INLINE_RE.finditer(line)))
        records.append(Record(
            ordinal=len(records),
            kind="dialogue" if quoted else "narration",
            line_start=start, line_end=index,
            text="\n".join(body), name=name, name_policy=policy,
            speaker_tag=speaker[0] if speaker is not None else None,
            speaker_line=speaker_line, tokens=tokens))
    return Script(text=text, encoding=used_encoding, bom=bom, newline=newline,
                  lines=tuple(lines), records=tuple(records), tag_schema=tag_schema,
                  speaker_tags=frozenset(pinned), command_tags=frozenset(command_tags))


def _replace_attribute(line: str, key: str, value: str) -> str:
    pattern = re.compile(r'(?<![\w"])' + re.escape(key) + r'\s*=\s*"([^"]*)"')
    match = pattern.search(line)
    if match is None:
        raise ScpError("missing_attribute", f"speaker command has no {key} attribute", "write")
    return line[:match.start(1)] + value + line[match.end(1):]


def render(script: Script, rows) -> str:
    """Apply ``message``/``name`` from rows to the parsed lines, then rejoin."""
    if len(rows) != len(script.records):
        raise ScpError("row_count", "row count differs from the parsed records", "write")
    edits = []
    speaker_names = {}
    for record, row in zip(script.records, rows):
        if not isinstance(row, dict) or not isinstance(row.get("message"), str):
            raise ScpError("bad_row", f"row {record.ordinal}: message must be a string", "write")
        message = row["message"]
        if message == "" or "\r" in message or "\0" in message or message.endswith("\n"):
            raise ScpError("bad_message",
                           f"row {record.ordinal}: empty message or embedded CR/NUL", "write")
        if record.kind == "dialogue" and not message.lstrip().startswith(OPEN_QUOTES):
            raise ScpError("structure_changed",
                           f"row {record.ordinal}: a spoken line must keep its opening quote", "write")
        for token in record.tokens:
            if message.count(token) != record.text.count(token):
                raise ScpError("token_changed",
                               f"row {record.ordinal}: protected token changed: {token!r}", "write")
        lines = message.split("\n")
        for line in lines:
            if line_kind(line) != "text":
                raise ScpError("line_kind_changed",
                               f"row {record.ordinal}: translated line is not text: {line!r}", "write")
        edits.append((record.line_start, record.line_end, lines))
        name = row.get("name")
        if record.name_policy == "absent":
            # The command has no name attribute, so a supplied name could only be
            # dropped silently. Refuse instead of pretending it was written.
            if name is not None:
                raise ScpError("name_not_writable",
                               f"row {record.ordinal}: this line has no writable name; if a name "
                               "came from the analysis, rebuild with the same tag_schema/"
                               "speaker_tags/command_tags (see Script.patch)", "write")
        elif record.name_policy == "context":
            if name != record.name:
                raise ScpError("context_name_changed",
                               f"row {record.ordinal}: a context-only name cannot be rewritten; "
                               "the tag name is not display text", "write")
        elif record.speaker_line is not None:
            if not isinstance(name, str) or not name:
                raise ScpError("missing_name",
                               f"row {record.ordinal}: writable speaker name is required", "write")
            if "\0" in name or '"' in name or "\n" in name or "\r" in name:
                raise ScpError("bad_name", f"row {record.ordinal}: name is not writable", "write")
            previous = speaker_names.get(record.speaker_line)
            if previous is not None and previous != name:
                raise ScpError("shared_name_conflict",
                               f"line {record.speaker_line}: one speaker command received two names",
                               "write")
            speaker_names[record.speaker_line] = name
    for line_index, name in speaker_names.items():
        edits.append((line_index, line_index + 1, [_replace_attribute(script.lines[line_index],
                                                                      SPEAKER_ATTRIBUTE, name)]))
    output = list(script.lines)
    for start, end, replacement in sorted(edits, key=lambda item: item[0], reverse=True):
        output[start:end] = replacement
    return script.newline.join(output)


def encode_script(script: Script, text: str, *, encoding=None, max_output_size: int = 64 << 20) -> bytes:
    codec = "utf-8-sig" if script.bom else (script.encoding if encoding is None else encoding)
    try:
        data = text.encode(codec, errors="strict")
    except (UnicodeEncodeError, LookupError) as exc:
        raise ScpError("bad_encoding", f"script is not encodable as {codec}", "write") from exc
    if len(data) > max_output_size:
        raise ScpError("output_budget", "rebuilt script exceeds the output budget", "write")
    return data


def _verify_rebuild(before: Script, after: Script, rows) -> None:
    """Independent re-parse comparison; a mismatch means the write is not trusted."""
    if len(after.records) != len(before.records):
        raise ScpError("verification_failed", "record count changed after rebuild", "verify")
    for original, rebuilt, row in zip(before.records, after.records, rows):
        if (original.kind, original.line_start, original.line_end) != \
                (rebuilt.kind, rebuilt.line_start, rebuilt.line_end):
            raise ScpError("verification_failed", "record boundaries shifted after rebuild", "verify")
        if rebuilt.text != row["message"]:
            raise ScpError("verification_failed", "rebuilt message differs from the translation", "verify")
        if original.name_policy == "writable" and rebuilt.name != row.get("name"):
            raise ScpError("verification_failed", "rebuilt speaker name differs from the translation", "verify")
        if original.name_policy == "context" and rebuilt.name != original.name:
            raise ScpError("verification_failed", "context-only speaker name changed", "verify")


def patch_script(data, rows, *, encoding=None, tag_schema=None, speaker_tags=frozenset(),
                 command_tags=frozenset(), max_output_size: int = 64 << 20) -> bytes:
    """Reinsert translations into one SCP text script.

    Equivalent to ``read_script(...).patch(rows)``. The keyword policy arguments
    must match the ones used for the analysis, otherwise a name slot can only be
    resolved differently; prefer ``Script.patch`` when the parsed object is still
    available.
    """
    script = read_script(data, encoding=encoding, tag_schema=tag_schema,
                         speaker_tags=speaker_tags, command_tags=command_tags)
    return script.patch(rows, max_output_size=max_output_size)
