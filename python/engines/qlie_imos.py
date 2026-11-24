"""QLIE ImoScripter FormatType=1 / ReturnCode=[n], explicit text profile.

Line roles follow the ImoScripter system scripts shipped inside the PACK
(Imo_FormatModeMulti, Imo_FormatDeleteCode, Misc_NameDivide): a trimmed text
line whose first character is the FormatNameCode opener is a name line, one
leading full-width space is an indent, a blank line ends the sentence.
No game source/material is distributed. Not a QLIE VM or FormatType=0 reader.
Save-title semantics: msg-tool src/scripts/qlie/script.rs (GPL-3.0-or-later).
"""
from dataclasses import dataclass
import re
import unicodedata

REFERENCE = 'qlie-imos-multi/3'
# Scripts accepted by the previous parser parse to identical rows/locators.
COMPATIBLE_REFERENCES = ('qlie-imos-multi/2', REFERENCE)

# Inline message tags with established meaning. Ruby is a protected group the
# translation may keep, rewrite, add or delete; timing tags are kept verbatim
# and in order. Anything else in brackets is rejected, not exported.
RUBY = re.compile(r'\[rb,([^\[\],\r\n]+),([^\[\],\r\n]+)\]')
TIMING = re.compile(r'\[(?:w,\d+|spd,\d+|spd)\]')
PC_LINE = re.compile(r'(?:\[spd,0\])?\[pc,([^\[\]]*)\](?:\[spd\])?(.*)')
NAME_CLOSED = re.compile(r'【([^【】]*)】([ \t　]*)')
NAME_OPEN = re.compile(r'【([^【】]*?)([ \t　]*)')
LINE_ROLES = ('^', '@', '\\', '％', '【')
SEPARATORS = '\r\0\v\f\x85\u2028\u2029'


class ScriptError(ValueError):
    """Unsupported or unsafe script structure with its line and offending token."""

    def __init__(self, reason: str, line: int | None = None, token: str | None = None):
        self.reason, self.line, self.token = reason, line, token
        message = reason
        if line is not None:
            message = f'line {line}: {message}'
        if token is not None:
            message += f': {token[:80]!r}'
        super().__init__(message)


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    raw: str
    kind: str


@dataclass(frozen=True)
class Record:
    parts: tuple[Span, ...]
    speaker: Span | None

    def row(self) -> dict:
        row = {'message': '\n'.join(p.raw.replace('[n]', '\n') for p in self.parts)}
        if self.speaker:
            row['name'] = self.speaker.raw.split('＠')[-1]
        return row


def _text_residue(text: str, *, source: bool = True) -> str:
    """Text left after removing valid ruby groups, timing tags and, in source
    lines only, [n] (translations write display breaks as JSON newlines)."""
    return TIMING.sub('', RUBY.sub('', text.replace('[n]', '') if source else text))


def _first_tag(text: str, *, source: bool = True) -> str:
    match = re.search(r'\[[^\[\]]*\]?|\]', _text_residue(text, source=source))
    return match[0] if match else text


def scan(script: str) -> tuple[Record, ...]:
    """Group a blank-line-delimited sentence; voices and commands stay inert.

    A name applies only within its sentence, so the following narration never
    inherits it. Standalone name-only sentences are rejected as ambiguous.
    Errors are ScriptError with a 1-based line number and the offending token.
    """
    for char in '\0\v\f\x85\u2028\u2029':
        if char in script:
            line = script.count('\n', 0, script.index(char)) + 1
            raise ScriptError('unsupported ImoScripter line separator', line, char)
    records, parts, speaker = [], [], None
    speaker_line = first_line = 0

    def flush():
        nonlocal speaker
        if parts:
            if len(parts) > 1 and any('[n]' in p.raw for p in parts):
                raise ScriptError('mixed physical/inline multiline sentence needs explicit mapping', first_line)
            records.append(Record(tuple(parts), speaker))
            parts.clear()
        elif speaker:
            raise ScriptError('name without message in ImoScripter sentence', speaker_line, speaker.raw)
        speaker = None

    offset = 0
    for number, line in enumerate(script.splitlines(keepends=True), 1):
        body = line.rstrip('\r\n')
        trimmed = body.strip(' \t')
        start = offset + len(body) - len(body.lstrip(' \t'))
        end = start + len(trimmed)
        if not trimmed:
            flush()
        elif trimmed.startswith('^select,'):
            flush()
            at = start + 8
            for option in trimmed[8:].split(','):
                records.append(Record((Span(at, at + len(option), option, 'choice'),), None))
                at += len(option) + 1
        elif trimmed.startswith('^savetext,'):
            caption = trimmed[10:].split(',', 1)[0]
            if '[' in caption or ']' in caption:
                raise ScriptError('unsupported savetext parameter layout', number, caption)
            records.append(Record((Span(start + 10, start + 10 + len(caption),
                                        caption, 'save-title'),), None))
        elif trimmed.startswith(('^', '％')):
            pass
        elif trimmed.startswith('\\cal,'):
            pass  # variable assignment: no text, jump or sentence event
        elif trimmed.startswith(('@', '\\')):
            if speaker or parts:
                raise ScriptError('control flow inside an unfinished ImoScripter sentence',
                                  number, trimmed.split(',', 1)[0])
        elif trimmed.startswith('【'):
            # The engine deletes the first opener and closer of the whole
            # trimmed line; text after the closer would join the name.
            if speaker or parts:
                raise ScriptError('ambiguous ImoScripter name placement', number, trimmed)
            match = NAME_CLOSED.fullmatch(trimmed) or NAME_OPEN.fullmatch(trimmed)
            if not match or (match.re is NAME_OPEN and not match[1]):
                raise ScriptError('unsupported ImoScripter name form', number, trimmed)
            raw = match[1]
            if raw.count('＠') > 1:
                raise ScriptError('unsupported ImoScripter name form', number, trimmed)
            speaker = Span(start + 1, start + 1 + len(raw), raw, 'name')
            speaker_line = number
        else:
            # The engine removes one leading full-width indent before display.
            if trimmed.startswith('　'):
                trimmed, start = trimmed[1:], start + 1
            if not trimmed:
                offset += len(line)
                continue  # display spacer, not a translation row
            if not parts:
                first_line = number
            pc = PC_LINE.fullmatch(trimmed)
            if pc and all(unicodedata.category(c).startswith('P') for c in pc[2]):
                # Only punctuation may follow the pc parameter; it stays verbatim.
                parts.append(Span(start + pc.start(1), start + pc.end(1), pc[1], 'pc'))
            elif '[pc,' in trimmed:
                raise ScriptError('unsupported mixed pc text layout', number, trimmed)
            else:
                residue = _text_residue(trimmed)
                if '[' in residue or ']' in residue:
                    raise ScriptError('unrecognized ImoScripter text tag', number, _first_tag(trimmed))
                parts.append(Span(start, end, trimmed, 'message'))
        offset += len(line)
    flush()
    # A save-title command does not end the surrounding dialogue sentence.
    return tuple(sorted(records, key=lambda record: record.parts[0].start))


def rows(script: str) -> list[dict]:
    return [record.row() for record in scan(script)]


def _whole_line(script: str, span: Span) -> tuple[int, int]:
    """Return the full physical line containing ``span``."""
    start = script.rfind('\n', 0, span.start) + 1
    end = script.find('\n', span.end)
    return start, len(script) if end < 0 else end + 1


def _check_message(script: str, span: Span, text: str, position: int):
    residue = _text_residue(text, source=False)
    if '[' in residue or ']' in residue:
        raise ScriptError(f'row {position}: malformed ruby/control brackets; keep [rb,base,reading] '
                          'with two non-empty fields and the original [w]/[spd] tags only',
                          token=_first_tag(text, source=False))
    # A span after a stripped full-width indent keeps its text role whatever it
    # starts with; an unindented span must not turn into a name/command/indent.
    indented = script[span.start - 1:span.start] == '　'
    if (not text.strip(' \t') or text != text.rstrip(' \t')
            or (not indented and (text != text.lstrip(' \t') or text.startswith(LINE_ROLES + ('　',))))):
        raise ScriptError(f'row {position}: translation changes ImoScripter line role/whitespace', token=text)


def patch(script: str, translated: list[dict]) -> str:
    """Reparse source, patch spans, and compare semantic rows and structure.

    Names keep the internal voice identity: translating 【Alice】 to 艾丽丝
    produces 【Alice＠艾丽丝】. A physical multiline sentence may use fewer
    lines: surplus trailing message lines are removed from the script. A single
    physical line may use [n] for translated display breaks. Line breaks may
    not be added, and [pc] parameter lines are never removed. Ruby groups may
    change; [w]/[spd] timing tags keep their sequence within the record.
    Byte encoding and manifest validation belong to the caller.
    """
    records = scan(script)
    if not isinstance(translated, list) or len(records) != len(translated):
        raise ValueError('ImoScripter translation count mismatch')
    edits, expected = [], []
    for position, (record, row) in enumerate(zip(records, translated)):
        source = record.row()
        if not isinstance(row, dict) or set(row) != set(source) or not all(isinstance(v, str) for v in row.values()):
            raise ScriptError(f'row {position}: ImoScripter row fields changed')
        message = row['message']
        bad = next((c for c in message if c in SEPARATORS), None)
        if bad:
            raise ScriptError(f'row {position}: unsupported ImoScripter text/control injection', token=bad)
        pieces = message.split('\n') if len(record.parts) > 1 else [message]
        if len(pieces) > len(record.parts):
            raise ScriptError(f'row {position}: ImoScripter translation adds physical lines')
        dropped = record.parts[len(pieces):]
        if any(span.kind != 'message' for span in dropped):
            raise ScriptError(f'row {position}: ImoScripter can only drop trailing message lines')
        before = [t for p in record.parts if p.kind == 'message' for t in TIMING.findall(p.raw)]
        after = [t for p, text in zip(record.parts, pieces) if p.kind == 'message' for t in TIMING.findall(text)]
        if before != after:
            raise ScriptError(f'row {position}: [w]/[spd] timing tags must stay unchanged and in order',
                              token=' '.join(before))
        for span, text in zip(record.parts, pieces):
            if span.kind in ('pc', 'choice', 'save-title'):
                bad = next((c for c in text if c in ',\n[]'), None)
                if bad:
                    raise ScriptError(f'row {position}: ImoScripter parameter delimiter injection', token=bad)
            else:
                _check_message(script, span, text, position)
            edits.append((span.start, span.end, text.replace('\n', '[n]')))
        for span in dropped:
            start, end = _whole_line(script, span)
            edits.append((start, end, ''))
        expected.append([p.kind for p in record.parts[:len(pieces)]])
        if record.speaker:
            name = row['name']
            raw_name = record.speaker.raw
            if name != source['name']:
                if raw_name.startswith('$') or not name or any(c in name for c in '＠,【】\n\r\0[]'):
                    raise ScriptError(f'row {position}: invalid ImoScripter display name', token=name)
                # Preserve the original identity, including an existing alias.
                edits.append((record.speaker.start, record.speaker.end, raw_name.split('＠')[0] + '＠' + name))
    result = script
    for start, end, text in sorted(edits, reverse=True):
        result = result[:start] + text + result[end:]
    rebuilt = scan(result)
    if [r.row() for r in rebuilt] != translated:
        raise ValueError('ImoScripter reparse differs from requested rows')
    if expected != [[p.kind for p in r.parts] for r in rebuilt]:
        raise ValueError('ImoScripter record structure changed')
    return result
