# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2021 arcusmaximus (MIT-derived portions)
# SPDX-FileCopyrightText: msg-tool contributors (GPL-3.0-or-later-derived portions)
"""Artemis ASB typed item/attribute tree and conservative field edits.
Source: VNTextPatch-net8, VNTextPatch.Shared/Scripts/Artemis/ArtemisAsbScript.cs,
ReadFile/ReadItem/ReadString/WriteItem/WriteString/GetTextReferences.
Commit d9c0fab7b72fdcf87d674ef12a84d3829c9188be; source license MIT.
Preserves original line numbers (upstream writer zeroes them) and attribute order.
Display-name slots: msg-tool src/scripts/artemis/asb.rs (GPL-3.0-or-later).
"""
from dataclasses import dataclass, replace
import struct


@dataclass(frozen=True)
class Command:
    name: str
    line_number: int = 0
    attributes: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class Label:
    name: str


@dataclass(frozen=True)
class Field:
    item: int
    attribute: str
    kind: str
    text: str


def read_asb(data: bytes) -> tuple[Command | Label, ...]:
    """bytes -> ordered ASB tree; reject unknown item types, bad lengths/trailer."""
    if not data.startswith(b"ASB\0\0"):
        raise ValueError("not ASB")
    pos = 5

    def u32():
        nonlocal pos
        if pos + 4 > len(data):
            raise ValueError("truncated ASB integer")
        value, = struct.unpack_from("<I", data, pos)
        pos += 4
        return value

    def string():
        nonlocal pos
        size = u32()
        end = pos + size
        if end >= len(data) or data[end] != 0 or b"\0" in data[pos:end]:
            raise ValueError("invalid ASB string length/terminator")
        value = data[pos:end].decode("utf-8", errors="strict")
        pos = end + 1
        return value

    count = u32()
    if count > (len(data) - pos) // 9:
        raise ValueError("impossible ASB item count")
    items = []
    for _ in range(count):
        kind = u32()
        if kind == 1:
            items.append(Label(string()))
        elif kind == 0:
            name, line, count_attrs = string(), u32(), u32()
            if count_attrs > (len(data) - pos) // 10:
                raise ValueError("impossible ASB attribute count")
            attrs = tuple((string(), string()) for _ in range(count_attrs))
            if len({key for key, _ in attrs}) != len(attrs):
                raise ValueError("duplicate ASB attribute")
            items.append(Command(name, line, attrs))
        else:
            raise ValueError(f"unknown ASB item type {kind}")
    if pos != len(data):
        raise ValueError("uninterpreted ASB trailer")
    return tuple(items)


def write_asb(items: tuple[Command | Label, ...]) -> bytes:
    """ASB tree -> bytes; UTF-8 length excludes the trailing NUL."""
    out = bytearray(b"ASB\0\0")

    def u32(value):
        if type(value) is not int or not 0 <= value <= 0xFFFFFFFF:
            raise ValueError("ASB u32 overflow")
        out.extend(struct.pack("<I", value))

    def string(text):
        if not isinstance(text, str) or "\0" in text:
            raise ValueError("ASB string contains NUL")
        encoded = text.encode("utf-8", errors="strict")
        u32(len(encoded))
        out.extend(encoded + b"\0")

    u32(len(items))
    for item in items:
        if isinstance(item, Label):
            u32(1)
            string(item.name)
        elif isinstance(item, Command):
            u32(0)
            string(item.name)
            u32(item.line_number)
            u32(len(item.attributes))
            if len({key for key, _ in item.attributes}) != len(item.attributes):
                raise ValueError("duplicate ASB attribute")
            for key, value in item.attributes:
                string(key)
                string(value)
        else:
            raise ValueError("unknown ASB node")
    return bytes(out)


def text_fields(items: tuple[Command | Label, ...]) -> tuple[Field, ...]:
    """Stable leaf fields, not lossy merged dialogue; ruby readings remain separate."""
    schema = {"name": ("0", "name"), "print": ("data", "message"),
              "ruby": ("text", "ruby_reading"), "sel_text": ("text", "choice"),
              "RegisterTextToHistory": ("1", "history")}
    result = []
    for index, item in enumerate(items):
        if not isinstance(item, Command) or item.name not in schema:
            continue
        key, role = schema[item.name]
        attrs = dict(item.attributes)
        if item.name == "name":
            if not attrs or set(attrs) != {str(i) for i in range(len(attrs))}:
                raise ValueError("unsupported ASB name slot layout")
            key = str(len(attrs) - 1)
        if key not in attrs:
            raise ValueError(f"missing {item.name}.{key}")
        result.append(Field(index, key, role, attrs[key]))
    return tuple(result)


def patch_asb(data: bytes, replacements: dict[tuple[int, str], str]) -> bytes:
    """Edit only recognized text attributes without replacing commands/ruby ranges."""
    items = read_asb(data)
    allowed = {(field.item, field.attribute) for field in text_fields(items)}
    if replacements.keys() - allowed:
        raise ValueError("unknown/non-text ASB field")
    patched = []
    for index, item in enumerate(items):
        if isinstance(item, Command):
            attrs = item.attributes
            if item.name == "name" and len(attrs) == 1 and (index, "0") in replacements:
                name = replacements[(index, "0")]
                if name != attrs[0][1]:
                    attrs += (("1", name),)
            else:
                attrs = tuple((key, replacements.get((index, key), value))
                              for key, value in attrs)
            item = replace(item, attributes=attrs)
        patched.append(item)
    return write_asb(tuple(patched))
