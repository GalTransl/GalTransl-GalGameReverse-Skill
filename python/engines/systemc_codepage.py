# SPDX-License-Identifier: GPL-3.0-only
"""SystemC whole-package CP932 -> GBK transcoding for ACP-following executables.

When the executable decodes script text with ``MultiByteToWideChar(CP_ACP)``,
every runtime text member must use the system ANSI code page. A GBK package is
only consistent if untranslated lines, name tables, labels and DAT scene titles
are converted too; this module never leaves CP932 bytes beside GBK text unless
the caller explicitly keeps a member, which is then reported.

Characters without a GBK mapping are never replaced silently: the caller must
provide an explicit ``source=target`` replacement table, and every use is
counted for the report.
"""
import json
import re
import struct
import unicodedata

from ..common.binary import FormatError

SOURCE = "cp932"
TARGET = "gbk"
ACT = re.compile(r"ACT_[A-Z]\.txt")
DAT = re.compile(r"ACT_[A-Z]\.DAT")
# Fixed-record compiled/media members: never decoded as text.
BINARY_SUFFIXES = (".spt", ".hmp", ".kg", ".bmp", ".png", ".jpg", ".ogg", ".wav", ".fpn", ".ttf", ".otf")
DAT_RECORD = 156
DAT_TITLE = 80
# Replacement targets must not create SystemC controls, commands or comments.
UNSAFE_ASCII = set("$&\\<>[]{}@#%^|~/*_") | set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")
MAX_REPLACEMENTS = 4096
MAX_LISTED_FAILURES = 40


def parse_replacements(pairs=(), table=None):
    """Merge ``"src=dst"`` CLI pairs and a JSON object; reject unsafe targets."""
    mapping = {}
    items = []
    if table is not None:
        if not isinstance(table, dict):
            raise FormatError("GBK replacement table must be a JSON object {\"source\": \"target\"}")
        items.extend(table.items())
    for pair in pairs:
        if not isinstance(pair, str) or "=" not in pair[1:]:
            raise FormatError(f"GBK replacement must be 'source=target': {pair!r}")
        items.append(tuple(pair.split("=", 1)))
    if len(items) > MAX_REPLACEMENTS:
        raise FormatError("too many GBK replacements")
    for source, target in items:
        if not isinstance(source, str) or not isinstance(target, str):
            raise FormatError("GBK replacement keys and values must be strings")
        if len(source) != 1 or source.isascii():
            raise FormatError(f"GBK replacement source must be one non-ASCII character: {source!r}")
        if not target or len(target) > 8:
            raise FormatError(f"GBK replacement target must be 1..8 characters: {source}={target!r}")
        for char in target:
            if ord(char) < 32 or char in UNSAFE_ASCII or char == "\x7f":
                raise FormatError(f"GBK replacement target contains control/command syntax: {source}={target!r}")
            try:
                char.encode(TARGET, errors="strict")
            except UnicodeError:
                raise FormatError(f"GBK replacement target is not GBK-encodable: {source}={target!r}") from None
        if source in mapping and mapping[source] != target:
            raise FormatError(f"conflicting GBK replacements for {source!r}")
        mapping[source] = target
    return mapping


def load_replacement_table(data):
    try:
        return json.loads(data.decode("utf-8-sig"))
    except (UnicodeError, ValueError) as exc:
        raise FormatError(f"invalid GBK replacement table: {exc}") from exc


def apply(text, mapping):
    return "".join(mapping.get(c, c) for c in text) if mapping else text


def map_rows(rows, mapping):
    return [{k: apply(v, mapping) if isinstance(v, str) else v for k, v in row.items()} for row in rows]


def classify(members, keep=()):
    """Return ``{member: kind}``; fail closed on undecidable non-ASCII members.

    Kinds: ``act`` / ``text`` (whole CP932 file), ``dat-titles`` (CP932 scene
    title in each record's first 80 bytes), ``ascii`` (identical in both code
    pages), ``binary`` (fixed records/media/NUL data) and ``kept`` (explicit).
    """
    kinds = {}
    unknown = set(keep) - members.keys()
    if unknown:
        raise FormatError(f"--gbk-keep-member names unknown members: {', '.join(sorted(unknown))}")
    for name, data in members.items():
        if name in keep:
            kinds[name] = "kept"
        elif ACT.fullmatch(name):
            kinds[name] = "act"
        elif DAT.fullmatch(name) and name[:-4] + ".txt" in members:
            kinds[name] = "dat-titles"
        elif name.lower().endswith(BINARY_SUFFIXES) or b"\0" in data:
            kinds[name] = "binary"
        elif data.isascii():
            kinds[name] = "ascii"
        else:
            try:
                text = data.decode(SOURCE, errors="strict")
            except UnicodeDecodeError as exc:
                raise FormatError(f"{name}: non-ASCII member is neither binary nor strict CP932 text "
                                  f"(byte {exc.start}); inspect it, then pass --gbk-keep-member {name} "
                                  "only if the runtime does not decode it with the ANSI code page") from None
            if any(ord(c) < 32 and c not in "\t\r\n" for c in text):
                raise FormatError(f"{name}: CP932-decodable member contains control bytes; classify it "
                                  f"explicitly with --gbk-keep-member {name} after inspection")
            kinds[name] = "text"
    return kinds


def _dat_titles(name, data):
    if len(data) < 4:
        raise FormatError(f"{name}: SystemC DAT too short")
    count = struct.unpack_from("<I", data)[0]
    if count > 100000 or len(data) != 4 + count * DAT_RECORD:
        raise FormatError(f"{name}: SystemC DAT record count/size mismatch")
    titles = []
    for index in range(count):
        field = data[4 + index * DAT_RECORD:4 + index * DAT_RECORD + DAT_TITLE]
        raw = field.split(b"\0", 1)[0]
        try:
            titles.append(raw.decode(SOURCE, errors="strict"))
        except UnicodeDecodeError:
            raise FormatError(f"{name}: record {index + 1} title is not strict CP932") from None
    return count, titles


def _code(char):
    return f"U+{ord(char):04X}"


def _scan(text, location, mapping, failures):
    for char in dict.fromkeys(text):
        if char in mapping:
            continue
        try:
            char.encode(TARGET, errors="strict")
        except UnicodeError:
            failures.append({"location": location, "char": char, "codepoint": _code(char),
                             "name": unicodedata.name(char, "?"), "count": text.count(char)})


def scan(members, kinds, mapping, translations=()):
    """Every GBK-unencodable character, located per member line / DAT record / JSON row.

    ``translations`` holds ``(json_name, translated_rows, original_rows)``.
    """
    failures = []
    for name, data in members.items():
        kind = kinds[name]
        if kind in ("act", "text"):
            for number, line in enumerate(data.decode(SOURCE).split("\r\n" if b"\r\n" in data else "\n"), 1):
                _scan(line, f"{name}:{number}", mapping, failures)
        elif kind == "dat-titles":
            for index, title in enumerate(_dat_titles(name, data)[1], 1):
                _scan(title, f"{name}:record {index}", mapping, failures)
    # Unchanged rows are already covered by the source member scan.
    for json_name, rows, originals in translations:
        for index, (row, old) in enumerate(zip(rows, originals), 1):
            if not isinstance(row, dict) or not isinstance(old, dict):
                continue  # Shape errors are reported by translation validation.
            for key, value in row.items():
                if isinstance(value, str) and value != old.get(key):
                    _scan(value, f"gt_output/{json_name}:{index}:{key}", mapping, failures)
    return failures


def summarize(failures):
    chars = {}
    for item in failures:
        entry = chars.setdefault(item["char"], {"char": item["char"], "codepoint": item["codepoint"],
                                                "name": item["name"], "occurrences": 0, "members": {}})
        entry["occurrences"] += item["count"]
        member = item["location"].split(":", 1)[0] if not item["location"].startswith("gt_output/") \
            else item["location"].rsplit(":", 2)[0]
        entry["members"][member] = entry["members"].get(member, 0) + item["count"]
    return sorted(chars.values(), key=lambda e: (-e["occurrences"], e["codepoint"]))


def failure_message(failures):
    lines = [f"{len(failures)} location(s) contain characters GBK cannot encode; nothing was written."]
    for item in failures[:MAX_LISTED_FAILURES]:
        lines.append(f"  {item['location']}: {item['char']!r} {item['codepoint']} {item['name']}")
    if len(failures) > MAX_LISTED_FAILURES:
        lines.append(f"  ... {len(failures) - MAX_LISTED_FAILURES} more; run pack --output-encoding gbk "
                     "--gbk-preflight for the full JSON list")
    lines.append("Distinct characters: " + ", ".join(f"{e['char']} {e['codepoint']}×{e['occurrences']}"
                                                     for e in summarize(failures)))
    lines.append('Choose explicit replacements, e.g. --gbk-replace "・=·" (repeatable) or '
                 "--gbk-replace-table table.json; every replacement is recorded in verification.json.")
    return "\n".join(lines)


def transcode(members, kinds, mapping):
    """Return ``(members, replacement_counts)`` with every text member in GBK."""
    out, counts = dict(members), {}

    def convert(text, name):
        for char in mapping:
            found = text.count(char)
            if found:
                counts.setdefault(char, {}).setdefault(name, 0)
                counts[char][name] += found
        return apply(text, mapping).encode(TARGET, errors="strict")

    for name, data in members.items():
        kind = kinds[name]
        if kind in ("act", "text"):
            out[name] = convert(data.decode(SOURCE, errors="strict"), name)
        elif kind == "dat-titles":
            count, titles = _dat_titles(name, data)
            buffer = bytearray(data)
            for index, title in enumerate(titles):
                at = 4 + index * DAT_RECORD
                old = data[at:at + DAT_TITLE]
                new = convert(title, name)
                used = len(old.split(b"\0", 1)[0])
                tail = old[used:]
                if len(new) == used:
                    field = new + tail
                elif any(tail) or len(new) >= DAT_TITLE:
                    raise FormatError(f"{name}: record {index + 1} GBK title does not fit the "
                                      f"{DAT_TITLE}-byte NUL-terminated field")
                else:
                    field = new.ljust(DAT_TITLE, b"\0")
                buffer[at:at + DAT_TITLE] = field
            out[name] = bytes(buffer)
    return out, counts


def replacement_report(mapping, counts):
    return [{"source": source, "source_codepoint": _code(source), "target": target,
             "target_codepoints": [_code(c) for c in target],
             "occurrences": sum(counts.get(source, {}).values()), "members": counts.get(source, {})}
            for source, target in mapping.items()]


def verify_readback(original, packed, kinds, mapping, expected_acts):
    """Independently decode the rebuilt package as GBK and compare in Unicode.

    ``expected_acts`` maps ACT name to the expected Unicode line list (mapped
    source lines with translated slots substituted). Non-text members must be
    byte-identical; DAT records may differ only in their title field.
    """
    checked = {"text_members": 0, "act_members": 0, "dat_members": 0, "binary_or_ascii_identical": 0,
               "kept_identical": 0}
    if packed.keys() != original.keys():
        raise FormatError("GBK readback member list changed")
    for name, data in original.items():
        kind, new = kinds[name], packed[name]
        if kind in ("binary", "ascii", "kept"):
            if new != data:
                raise FormatError(f"GBK readback changed non-text member {name}")
            checked["kept_identical" if kind == "kept" else "binary_or_ascii_identical"] += 1
        elif kind == "text":
            if new.decode(TARGET, errors="strict") != apply(data.decode(SOURCE), mapping):
                raise FormatError(f"GBK readback text differs: {name}")
            checked["text_members"] += 1
        elif kind == "act":
            lines = new.decode(TARGET, errors="strict").split("\r\n")
            if lines != expected_acts[name]:
                bad = next(i for i, (a, b) in enumerate(zip(lines + [None], expected_acts[name] + [None])) if a != b)
                raise FormatError(f"GBK readback ACT differs: {name}:{bad + 1}")
            checked["act_members"] += 1
        elif kind == "dat-titles":
            count, titles = _dat_titles(name, data)
            new_titles = []
            if len(new) != len(data) or new[:4] != data[:4]:
                raise FormatError(f"GBK readback DAT size changed: {name}")
            for index in range(count):
                at = 4 + index * DAT_RECORD
                if new[at + DAT_TITLE:at + DAT_RECORD] != data[at + DAT_TITLE:at + DAT_RECORD]:
                    raise FormatError(f"GBK readback DAT compiled fields changed: {name}:record {index + 1}")
                new_titles.append(new[at:at + DAT_TITLE].split(b"\0", 1)[0].decode(TARGET, errors="strict"))
            if new_titles != [apply(t, mapping) for t in titles]:
                raise FormatError(f"GBK readback DAT titles differ: {name}")
            checked["dat_members"] += 1
    return checked


RUNTIME_REQUIREMENT = {
    "system_acp": 936,
    "summary": "System ANSI code page must be 936 (Simplified Chinese Windows). Do not run through "
               "Locale Emulator or a Japanese system locale: the executable decodes these members with CP_ACP.",
    "hook": "If a hook such as CialloHook is used, disable EnableCnJpMap and [CodePage] remapping and keep "
            "Charset=0; the engine selects the font charset from GetACP() itself.",
    "font": "Only replace the font if the configured face lacks Chinese glyphs.",
    "evidence": "Choose this route only with ACP-following evidence for the executable, e.g. "
                "python -m python.common.jis_workflow codepage <exe>.",
}
