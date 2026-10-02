"""Musica .sc finite message/select ranges and engine escape conversion.
Source: VNTextPatch-net8, VNTextPatch.Shared/Scripts/MusicaScript.cs,
GetMessageRanges/GetSelectRanges/GetTextForRead/GetTextForWrite.
Commit d9c0fab7b72fdcf87d674ef12a84d3829c9188be; source license MIT.
Unlike msg-tool's message-only parser, this includes .select captions.
"""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Field:
    start: int
    end: int
    kind: str
    text: str
    writable: bool = True


def decode_text(text: str, *, name: bool = False) -> str:
    """Decode Musica \\n and \\$HH; conservatively retain full-width name spaces."""
    if re.search(r"\\(?!n|\$[0-9a-fA-F]{2})", text):
        raise ValueError("unknown Musica escape")
    text = text if name else text.replace("　", " ")
    text = text.replace("\\n", "\n")
    return re.sub(r"\\\$([0-9a-fA-F]{2})", lambda m: chr(int(m[1], 16)), text)


def musica_fields(script: str) -> tuple[Field, ...]:
    """str -> .message name/body and .select caption fields, with stable spans."""
    fields = []
    offset = 0

    def add(start, end, kind):
        raw = script[start:end]
        fields.append(Field(start, end, kind, decode_text(raw, name=kind == "name"),
                            not (kind == "name" and raw.startswith("$"))))

    for raw in script.splitlines(keepends=True):
        line = raw.rstrip("\r\n")
        match = re.fullmatch(r"(\.\w+)((?:[ \t][^ \t]*)+)", line)
        if match and match[1] in (".message", ".select"):
            args = list(re.finditer(r"[ \t]([^ \t]*)", line[len(match[1]):]))
            base = offset + len(match[1])
            if match[1] == ".message":
                if len(args) < 4:
                    raise ValueError("short Musica .message")
                name = args[2]
                if name[1]:
                    skip = 1 if name[1].startswith("@") else 0
                    add(base + name.start(1) + skip, base + name.end(1), "name")
                add(base + args[3].start(1), base + args[-1].end(1), "message")
            else:
                for arg in args:
                    colon = arg[1].find(":")
                    if colon >= 0:
                        add(base + arg.start(1), base + arg.start(1) + colon, "choice")
        offset += len(raw)
    return tuple(fields)


def patch_musica(script: str, replacements: dict[int, str]) -> str:
    """Field ordinal -> text; preserve IDs, voices, @ prefixes, targets and spacing."""
    fields = musica_fields(script)
    if any(type(k) is not int or not 0 <= k < len(fields) for k in replacements):
        raise ValueError("unknown Musica field")
    out = script
    for index in sorted(replacements, reverse=True):
        field, text = fields[index], replacements[index]
        if not field.writable:
            raise ValueError("name variable is context-only")
        if not isinstance(text, str) or any(c in text for c in "\0\t\\"):
            raise ValueError("translation introduces Musica syntax")
        if field.kind == "choice" and ":" in text:
            raise ValueError("colon would alter choice target")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        if field.kind == "name" and "\n" in text:
            raise ValueError("newline in Musica name")
        text = text.replace(" ", "　").replace("\n", "\\n")
        out = out[:field.start] + text + out[field.end:]
    if [f.kind for f in musica_fields(out)] != [f.kind for f in fields]:
        raise ValueError("translation changes Musica field structure")
    return out
