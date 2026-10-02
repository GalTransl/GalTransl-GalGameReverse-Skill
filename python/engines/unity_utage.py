# SPDX-License-Identifier: GPL-3.0-only
"""Utage serialized AdvImportBook/StringGrid profile; no runtime execution.

Only the importVersion=0 layout with empty entity tables is supported. String
lengths are UTF-8 bytes; StringGrid.textLength counts UTF-16 code units.
"""
from dataclasses import dataclass
from collections import Counter
import copy
import re
import struct

from ..archives.unity_serialized import Reader, MAX_OBJECT
from ..common.binary import FormatError

PROFILE = "utage-book-v0-empty-entities"


class Writer:
    def __init__(self, prefix=b""):
        self.data = bytearray(prefix)

    def number(self, value, fmt="i"):
        self.data.extend(struct.pack("<" + fmt, value))

    def align(self):
        self.data.extend(bytes(-len(self.data) % 4))

    def string(self, value):
        raw = value.encode("utf-8", "strict")
        if len(raw) > 1 << 20:
            raise FormatError("Utage string exceeds budget")
        self.number(len(raw))
        self.data.extend(raw)
        self.align()


@dataclass
class Row:
    index: int
    strings: list
    empty: bool
    comment: bool


@dataclass
class Grid:
    rows: list
    name: str
    kind: int
    text_length: int
    header: int


@dataclass
class Book:
    prefix: bytes
    name: str
    grids: list


@dataclass
class Chapter:
    prefix: bytes
    name: str
    chapter_name: str
    books: list
    settings: list


def behaviour(r):
    start = r.pos
    r.take(12)  # GameObject PPtr
    enabled = r.number("B")
    r.align()
    if enabled not in (0, 1):
        raise FormatError("invalid MonoBehaviour enabled flag")
    script = r.number(), r.number("q")
    name = r.string()
    return r.data[start:r.pos], name, script


def mono_script(data):
    r = Reader(data)
    name = r.string()
    r.take(20)  # execution order + properties hash
    class_name, namespace, assembly = r.string(), r.string(), r.string()
    if r.pos != len(data):
        raise FormatError("unsupported MonoScript layout")
    return {"name": name, "class": class_name, "namespace": namespace, "assembly": assembly}


def units(grids):
    return sum(len(s.encode("utf-16-le")) // 2 for row in grids.rows for s in row.strings)


def read_grid(r, *, check_total=True):
    rows = []
    for _ in range(r.count(100000)):
        index = r.number()
        count = r.count(256)
        r.string_items = getattr(r, "string_items", 0) + count
        if r.string_items > 2000000:
            raise FormatError("Utage cell count exceeds object budget")
        cells = [r.string() for _ in range(count)]
        flags = []
        for _ in range(2):
            flag = r.number("B")
            r.align()
            if flag not in (0, 1):
                raise FormatError("invalid Utage row flag")
            flags.append(bool(flag))
        rows.append(Row(index, cells, *flags))
    grid = Grid(rows, r.string(), r.number(), r.number(), r.number())
    if not 0 <= grid.header < max(1, len(rows)):
        raise FormatError("Utage header row outside grid")
    if check_total and grid.text_length != units(grid):
        raise FormatError("Utage cached textLength differs from UTF-16 unit count")
    return grid


def write_grid(w, grid):
    w.number(len(grid.rows))
    for row in grid.rows:
        w.number(row.index)
        w.number(len(row.strings))
        for value in row.strings:
            w.string(value)
        for flag in (row.empty, row.comment):
            w.number(int(flag), "B")
            w.align()
    w.string(grid.name)
    w.number(grid.kind)
    w.number(units(grid))
    w.number(grid.header)


def reader(data):
    if not isinstance(data, bytes) or len(data) > MAX_OBJECT:
        raise FormatError("Utage object exceeds budget")
    return Reader(data)


def read_book(data):
    r = reader(data)
    prefix, name, _ = behaviour(r)
    if r.number() != 0:
        raise FormatError("unsupported Utage importVersion")
    grids = []
    for _ in range(r.count(4096)):
        grids.append(read_grid(r))
        if r.count() or r.count():
            raise FormatError("Utage nonempty entity tables require another profile")
    if r.pos != len(data):
        raise FormatError("unparsed Utage book tail")
    return Book(prefix, name, grids)


def write_book(book):
    w = Writer(book.prefix)
    w.number(0)
    w.number(len(book.grids))
    for grid in book.grids:
        write_grid(w, grid)
        w.number(0)
        w.number(0)
        if len(w.data) > MAX_OBJECT:
            raise FormatError("rebuilt Utage book exceeds budget")
    data = bytes(w.data)
    read_book(data)
    return data


def read_chapter(data):
    r = reader(data)
    prefix, name, _ = behaviour(r)
    chapter_name = r.string()
    books = [(r.number(), r.number("q")) for _ in range(r.count(4096))]
    # Chapter settings are read-only context, and may retain stale import caches.
    settings = [read_grid(r, check_total=False) for _ in range(r.count(4096))]
    if r.pos != len(data):
        raise FormatError("unparsed Utage chapter tail")
    return Chapter(prefix, name, chapter_name, books, settings)


def columns(grid):
    if not grid.rows:
        return {}
    names = grid.rows[grid.header].strings
    present = [name for name in names if name]
    if len(set(present)) != len(present):
        raise FormatError(f"duplicate Utage header column: {grid.name}")
    return {name: i for i, name in enumerate(names) if name}


def cell(row, header, name):
    index = header.get(name)
    return row.strings[index] if index is not None and index < len(row.strings) else ""


def character_names(chapters):
    """Context only: never modify CharacterName keys or chapter settings."""
    names = {}
    for chapter in chapters:
        for grid in chapter.settings:
            h = columns(grid)
            if not {"CharacterName", "NameText"} <= h.keys():
                continue
            for row in grid.rows[grid.header + 1:]:
                if row.empty or row.comment:
                    continue
                key, name = cell(row, h, "CharacterName"), cell(row, h, "NameText")
                if key:
                    if key in names and names[key] != name:
                        raise FormatError(f"conflicting Utage Character NameText: {key}")
                    names[key] = name
    return names


# Only established standard commands whose Text column is not a display field.
# Unknown commands with Text stop export; extend this set only with evidence.
NON_TEXT = frozenset({"Wait", "Bg", "Bgm", "BgEvent", "Jump", "Se", "StopSe", "CharacterOff"})
TEXT_COMMANDS = frozenset({"", "Text", "Character", "Selection"})
TOKEN = re.compile(r'<[^<>\r\n]+>|\{[^{}\r\n]+\}|\[[^\[\]\r\n]+\]|\\(?:[A-Za-z]+|.)|\r\n|[\r\n\t<>{}\[\]\\]')


def controls(text):
    if not isinstance(text, str) or any(ord(c) < 32 and c not in "\r\n\t" for c in text):
        raise FormatError("invalid Utage display string")
    text.encode("utf-8", "strict")
    return TOKEN.findall(text)


def export_book(book, names=None):
    names = names or {}
    result = []
    for gi, grid in enumerate(book.grids):
        h = columns(grid)
        rows, locations, excluded = [], [], Counter()
        if "Text" in h and not {"Command", "Arg1"} <= h.keys():
            raise FormatError(f"Utage scenario header lacks Command/Arg1: {grid.name}")
        for ri, row in enumerate(grid.rows[grid.header + 1:], grid.header + 1):
            text = cell(row, h, "Text")
            if not text:
                continue
            cmd = cell(row, h, "Command")
            if row.empty or row.comment or cmd.startswith("//"):
                excluded["comment-or-empty"] += 1
                continue
            if cmd.startswith("*") or cmd in NON_TEXT:
                excluded["label" if cmd.startswith("*") else cmd] += 1
                continue
            if cmd not in TEXT_COMMANDS:
                raise FormatError(f"unclassified Utage Text command {cmd!r}: {grid.name} row {ri}")
            controls(text)
            value = {}
            speaker = cell(row, h, "Arg1") if cmd in ("", "Character") else ""
            # Arg2 can contain character-pattern/name overrides. Do not invent
            # a display name from it; keep the raw context explicit in metadata.
            arg2 = cell(row, h, "Arg2")
            if speaker:
                value["name"] = names.get(speaker, speaker) or speaker
            value["message"] = text
            rows.append(value)
            locations.append({"row": ri, "row_index": row.index, "column": h["Text"],
                              "role": "selection" if cmd == "Selection" else "message",
                              "speaker_key": speaker, "arg2": arg2, "name_policy": "context-only"})
        result.append({"grid": gi, "name": grid.name, "rows": rows,
                       "locations": locations, "excluded_text_cells": dict(excluded)})
    return result


def patch_book(data, translations, names=None):
    """Patch selected grids by ordinal; validate every field against fresh parse."""
    original = read_book(data)
    exports = export_book(original, names)
    if set(translations) - set(range(len(exports))):
        raise FormatError("unknown Utage grid translation")
    modified = copy.deepcopy(original)
    projected = len(data)
    for item in exports:
        targets = translations.get(item["grid"], item["rows"])
        if not isinstance(targets, list) or len(targets) != len(item["rows"]):
            raise FormatError("Utage translation row count differs")
        for source, target, loc in zip(item["rows"], targets, item["locations"]):
            if not isinstance(target, dict) or set(target) != set(source):
                raise FormatError("Utage translation fields differ")
            if target.get("name") != source.get("name"):
                raise FormatError("Utage name is read-only context; do not translate resource keys")
            message = target["message"]
            if (not isinstance(message, str) or (not message.strip() and message != source["message"])
                    or controls(message) != controls(source["message"])):
                raise FormatError(f"Utage translation is empty or changes controls/newlines: {item['name']} row {loc['row']}")
            if len(message.encode("utf-8")) > 1 << 20:
                raise FormatError("Utage translation string exceeds budget")
            footprint = lambda s: (len(s.encode("utf-8")) + 3) // 4 * 4
            projected += footprint(message) - footprint(source["message"])
            if projected > MAX_OBJECT:
                raise FormatError("rebuilt Utage object exceeds budget")
            modified.grids[item["grid"]].rows[loc["row"]].strings[loc["column"]] = message
    for grid in modified.grids:
        grid.text_length = units(grid)
    result = write_book(modified)
    if read_book(result) != modified:
        raise FormatError("Utage reparse changed text or non-text structure")
    # Reversing just allowed text edits must recover every original byte.
    restored = read_book(result)
    for item in exports:
        for source, loc in zip(item["rows"], item["locations"]):
            restored.grids[item["grid"]].rows[loc["row"]].strings[loc["column"]] = source["message"]
    if write_book(restored) != data:
        raise FormatError("Utage non-text bytes changed during rebuild")
    return result
