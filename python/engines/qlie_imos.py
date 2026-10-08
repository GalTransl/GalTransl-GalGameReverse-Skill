"""QLIE ImoScripter FormatType=1 / ReturnCode=[n], explicit text profile.

New implementation verified against installed ImoScripter_Format.s,
Imo_ApplyMessageText and Misc_NameDivide in the 2012 Biman 2 sample.
No game source/material is distributed. Not a QLIE VM or FormatType=0 reader.
Save-title semantics: msg-tool src/scripts/qlie/script.rs (GPL-3.0-or-later).
"""
from dataclasses import dataclass
import re

REFERENCE = 'qlie-imos-multi/2'


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


def scan(script: str) -> tuple[Record, ...]:
    """Group a blank-line-delimited sentence; voices and commands stay inert.

    A name applies only within its sentence, so the following narration never
    inherits it. Standalone name-only sentences are rejected as ambiguous.
    """
    if '\0' in script or any(c in script for c in '\v\f\x85\u2028\u2029'):
        raise ValueError('unsupported ImoScripter line separator')
    records, parts, speaker = [], [], None

    def flush():
        nonlocal speaker
        if parts:
            if len(parts) > 1 and any('[n]' in p.raw for p in parts):
                raise ValueError('mixed physical/inline multiline sentence needs explicit mapping')
            records.append(Record(tuple(parts), speaker))
            parts.clear()
        elif speaker:
            raise ValueError('name without message in ImoScripter sentence')
        speaker = None

    offset = 0
    for line in script.splitlines(keepends=True):
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
                raise ValueError('unsupported savetext parameter layout')
            records.append(Record((Span(start + 10, start + 10 + len(caption),
                                        caption, 'save-title'),), None))
        elif trimmed.startswith(('^', '％')):
            pass
        elif trimmed.startswith(('@', '\\')):
            if speaker or parts:
                raise ValueError('control flow inside an unfinished ImoScripter sentence')
        elif trimmed.startswith('【'):
            if speaker or parts or not trimmed.endswith('】'):
                raise ValueError('ambiguous ImoScripter name placement')
            raw = trimmed[1:-1]
            if raw.count('＠') > 1 or any(c in raw for c in '【】'):
                raise ValueError('unsupported ImoScripter name form')
            speaker = Span(start + 1, end - 1, raw, 'name')
        else:
            # The engine removes one leading full-width indent before display.
            if trimmed.startswith('　'):
                trimmed, start = trimmed[1:], start + 1
            if not trimmed:
                offset += len(line)
                continue  # display spacer, not a translation row
            pc = re.fullmatch(r'(?:\[spd,0\])?\[pc,([^\[\]]*)\](?:\[spd\])?', trimmed)
            if pc:
                parts.append(Span(start + pc.start(1), start + pc.end(1), pc[1], 'pc'))
            elif '[pc,' in trimmed:
                raise ValueError('unsupported mixed pc text layout')
            else:
                # This observed profile has only [n] in ordinary text. Refuse
                # unknown tags instead of exporting potentially hidden strings.
                if '[' in trimmed.replace('[n]', '') or ']' in trimmed.replace('[n]', ''):
                    raise ValueError('unrecognized ImoScripter text tag')
                parts.append(Span(start, end, trimmed, 'message'))
        offset += len(line)
    flush()
    # A save-title command does not end the surrounding dialogue sentence.
    return tuple(sorted(records, key=lambda record: record.parts[0].start))


def rows(script: str) -> list[dict]:
    return [record.row() for record in scan(script)]


def patch(script: str, translated: list[dict]) -> str:
    """Reparse source, patch spans, and compare semantic rows and structure.

    Names keep the internal voice identity: translating 【Alice】 to 艾丽丝
    produces 【Alice＠艾丽丝】. Physical multiline sentences keep their line
    count; a single physical line may use [n] for translated display breaks.
    Byte encoding and manifest validation belong to the caller.
    """
    records = scan(script)
    if not isinstance(translated, list) or len(records) != len(translated):
        raise ValueError('ImoScripter translation count mismatch')
    edits = []
    for record, row in zip(records, translated):
        source = record.row()
        if not isinstance(row, dict) or set(row) != set(source) or not all(isinstance(v, str) for v in row.values()):
            raise ValueError('ImoScripter row fields changed')
        message = row['message']
        if any(c in message for c in '\r\0\v\f\x85\u2028\u2029[]'):
            raise ValueError('unsupported ImoScripter text/control injection')
        pieces = message.split('\n') if len(record.parts) > 1 else [message]
        if len(pieces) != len(record.parts):
            raise ValueError('physical multiline sentence requires the same line count')
        for span, text in zip(record.parts, pieces):
            if span.kind in ('pc', 'choice', 'save-title') and any(c in text for c in ',\n'):
                raise ValueError('ImoScripter parameter delimiter injection')
            if span.kind == 'message' and (not text.strip(' \t') or text != text.strip(' \t')
                    or text.startswith(('^', '@', '\\', '％', '【', '　'))):
                raise ValueError('translation changes ImoScripter line role/whitespace')
            edits.append((span.start, span.end, text.replace('\n', '[n]')))
        if record.speaker:
            name = row['name']
            raw_name = record.speaker.raw
            if name != source['name']:
                if raw_name.startswith('$') or not name or any(c in name for c in '＠,【】\n\r\0[]'):
                    raise ValueError('invalid ImoScripter display name')
                # Preserve the original identity, including an existing alias.
                edits.append((record.speaker.start, record.speaker.end, raw_name.split('＠')[0] + '＠' + name))
    result = script
    for start, end, text in sorted(edits, reverse=True):
        result = result[:start] + text + result[end:]
    rebuilt = scan(result)
    if [r.row() for r in rebuilt] != translated:
        raise ValueError('ImoScripter reparse differs from requested rows')
    if [[p.kind for p in r.parts] for r in records] != [[p.kind for p in r.parts] for r in rebuilt]:
        raise ValueError('ImoScripter record structure changed')
    return result
