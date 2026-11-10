# SPDX-License-Identifier: GPL-3.0-only
"""EAGLS source-text spans with strict storage-encoding round trips.

Message/name/choice syntax informed by SExtractor's Engine_EAGLS preset;
new bounded integration, not a general EAGLS command compiler.
"""
import re
from dataclasses import dataclass
from .eagls import apply_edits_with_labels, crypt_script, read_labels, verify_label_offsets
from ..common.contract import make_manifest, validate_translation


@dataclass(frozen=True)
class Profile:
    text_offset: int = 3600
    version: int = 2
    key: bytes = b"EAGLS_SYSTEM"
    label_size: int = 36
    encoding: str = "cp932"

    def display(self, text):
        return text

    def encode(self, text):
        raw = text.encode(self.encoding, "strict")
        if raw.decode(self.encoding, "strict") != text:
            raise ValueError("translation does not round-trip in the storage encoding")
        return raw

    def settings(self):
        return {"text_offset": self.text_offset, "version": self.version,
                "key_hex": self.key.hex(), "label_size": self.label_size,
                "storage_encoding": self.encoding}


def parse_script(encrypted: bytes, profile: Profile):
    """Return plain bytes, rows and byte locators; name applies to next message.

    Scan outside quoted operands. One &ID literal is one message; name commands
    may precede it on another line or follow the previous message on the same
    line. All other operands remain opaque and byte-preserved.
    """
    plain = crypt_script(encrypted, text_offset=profile.text_offset, key=profile.key, version=profile.version)
    read_labels(plain, text_offset=profile.text_offset, label_size=profile.label_size)
    # Stored offsets are authoritative; they only have to land on their token.
    verify_label_offsets(plain, text_offset=profile.text_offset, version=profile.version,
                         label_size=profile.label_size)
    body = plain[profile.text_offset:-profile.version]
    text = body.decode(profile.encoding, "strict")
    offsets = [0]
    for char in text:
        offsets.append(offsets[-1] + len(char.encode(profile.encoding, "strict")))
    if offsets[-1] != len(body):
        raise ValueError("encoding does not support byte-span reconstruction")
    rows, locators, pending = [], [], None
    pos = 0

    def span(start, end):
        return [profile.text_offset + offsets[start], profile.text_offset + offsets[end]]

    while pos < len(text):
        message = re.match(r'&([0-9]+)"([^"\r\n]*)"', text[pos:]) if text[pos] == '&' else None
        choice = re.match(r'52\("_SelStr([0-9]+)","([^"\r\n]*)"\)', text[pos:]) if text.startswith('52(', pos) else None
        if message or choice:
            match = message or choice
            # Empty choice slots are inactive, not translation placeholders.
            if message or match[2]:
                row = {"message": profile.display(match[2])}
                loc = {"kind": "message" if message else "choice", "id": match[1],
                       "message": span(pos + match.start(2), pos + match.end(2))}
                if message and pending is not None:
                    row["name"], loc["name"] = pending
                rows.append(row)
                locators.append(loc)
            if message:
                pending = None
            pos += match.end()
        elif text[pos] == '#':
            match = re.match(r'#([^,&=\r\n0-9]+)(?:,[0-9]+(?:=[A-Za-z0-9_]+)?)?', text[pos:])
            if not match or pending is not None:
                raise ValueError("unsupported or unconsumed name command")
            pending = (profile.display(match[1]), span(pos + match.start(1), pos + match.end(1)))
            pos += match.end()
        elif text[pos] == '"':
            end = text.find('"', pos + 1)
            if end == -1 or '\n' in text[pos:end]:
                raise ValueError("unterminated or multiline quoted operand")
            pos = end + 1
        elif text[pos] == '&' and re.match(r'&[0-9]+"', text[pos:]):
            raise ValueError("unsupported message literal")
        else:
            pos += 1
    if pending is not None:
        raise ValueError("name command has no following message")
    return plain, rows, locators


def export_script(encrypted: bytes, profile: Profile):
    _, rows, locators = parse_script(encrypted, profile)
    manifest = make_manifest(engine="eagls", variant="source-text-1", reference="eagls_text/1",
                             sources={"member.dat": encrypted}, rows=rows, locators=locators,
                             encoding="utf-8", settings=profile.settings(),
                             name_policies=["writable" if "name" in r else "absent" for r in rows])
    return rows, manifest


def rebuild_script(encrypted: bytes, rows: list, manifest: dict, profile: Profile) -> bytes:
    plain, original, locators = parse_script(encrypted, profile)
    _, expected = export_script(encrypted, profile)
    if manifest != expected:
        raise ValueError("manifest differs from reparsed original/profile")
    rows = validate_translation(manifest, {"member.dat": encrypted}, original, rows)
    edits = []
    for before, after, loc in zip(original, rows, locators):
        for field in before:
            value = after[field]
            if any(c in value for c in '"\r\n\0') or any(ord(c) < 32 for c in value):
                raise ValueError("control character or quote in translation")
            if field == "name" and (not value or re.search(r'[,&#=0-9]', value)):
                raise ValueError("name contains command delimiters")
            # No inferred escape syntax: preserve existing control-like literals.
            if field == "message" and re.findall(r'[\\%{}\[\]#&$]', before[field]) != re.findall(r'[\\%{}\[\]#&$]', value):
                raise ValueError("changed control-like literal sequence")
            if value != before[field]:
                start, end = loc[field]
                edits.append((start, end, profile.encode(value)))
    # Shift original offsets by the size change of preceding edits; no search.
    result = apply_edits_with_labels(plain, edits, text_offset=profile.text_offset,
                                     version=profile.version, label_size=profile.label_size)
    result = crypt_script(result, text_offset=profile.text_offset, key=profile.key, version=profile.version)
    _, reparsed, _ = parse_script(result, profile)
    if reparsed != rows:
        raise ValueError("reparsed rows differ from translation")
    return result
