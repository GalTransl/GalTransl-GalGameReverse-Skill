# SPDX-License-Identifier: GPL-3.0-or-later
"""Entis GLS workflow: NOA -> SRCXML -> GalTransl JSON, and back to a patch NOA.

Subcommands (all read-only on the game directory; outputs go to new directories):
  mounts   print the startup script and archive search order from the EXE's
           IDR_COTOMI resource (ERISA-N compressed XML; read as data, not run)
  extract  export msg/menu/open_line_msg text of the effective .srcxml members
  rebuild  apply gt_output to the original .srcxml, write a NOA (only changed
           members stored raw, or merged into a copy of --base), read it back
  readback re-export JSON from a rebuilt NOA for comparison with gt_output
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys

from python.archives.entis_erisa import decode_nemesis
from python.archives.entis_noa import (NoaMember, build_noa, member_from_entry, read_index,
                                       read_member)
from python.common.binary import FormatError
from python.common.contract import dump_rows, load_json, make_manifest, validate_translation
from python.common.safety import Limits, write_new_tree
from python.engines import entis_srcxml as srcxml

ENGINE = "entis-gls"
VARIANT = "noa/srcxml-attribute-dialect"
REFERENCE = "python/archives/entis_noa.py + python/engines/entis_srcxml.py"
MAX_MEMBER = 64 * 1024 * 1024
MAX_EXE = 256 * 1024 * 1024
_ARCHIVE = re.compile(r"""<archive\s+path\s*=\s*"([^"]+)"\s*/>""")
_SCRIPT = re.compile(r"""<script\s+src\s*=\s*"([^"]+)\"""")


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_cotomi_config(exe_path, *, max_exe=MAX_EXE):
    """Return the startup XML text stored as RCDATA ``IDR_COTOMI`` in the EXE."""
    from python.archives.catsystem2_int import _find_named_resource, _pe_resource_tree
    size = os.path.getsize(exe_path)
    if size > max_exe:
        raise FormatError("executable exceeds size limit")
    data = Path(exe_path).read_bytes()
    tree = _pe_resource_tree(data)
    if not tree:
        raise FormatError("no PE resource tree")
    leaf = _find_named_resource(tree, (10, "IDR_COTOMI"))
    if leaf is None:
        raise FormatError("EXE has no IDR_COTOMI resource")
    offset, length = leaf
    raw = decode_nemesis(data[offset:offset + length], None, max_output=4 * 1024 * 1024)
    # Declared UTF-8, but captions may hold stray legacy bytes; this text is only
    # read for archive/script paths, so undecodable bytes become U+FFFD.
    return raw.decode("utf-8", errors="replace")


def mount_order(config_text):
    """Archive file names in declaration order (the engine's search order)."""
    names = []
    for path in _ARCHIVE.findall(config_text):
        name = path.replace("\\", "/").rsplit("/", 1)[-1]
        if name and name.casefold() not in {n.casefold() for n in names}:
            names.append(name)
    script = _SCRIPT.search(config_text)
    return names, script.group(1) if script else None


def _find_exe(root):
    exes = sorted(p for p in root.iterdir() if p.is_file() and p.suffix.lower() == ".exe")
    found = []
    for exe in exes:
        try:
            found.append((exe, read_cotomi_config(exe)))
        except (OSError, FormatError, ValueError):
            continue
    return found[0] if len(found) == 1 else (None, None)


def _archives(root, archive_names, exe):
    """Return (ordered archive paths, order source, script image name)."""
    if archive_names:
        paths = [root / name for name in archive_names]
        return paths, "explicit", None
    config = None
    if exe:
        config = read_cotomi_config(exe)
    else:
        _, config = _find_exe(root)
    if config:
        order, script = mount_order(config)
        paths = [root / name for name in order if (root / name).is_file()]
        return paths, "IDR_COTOMI", script
    paths = sorted((p for p in root.iterdir() if p.is_file() and p.suffix.lower() == ".noa"),
                   key=lambda p: p.name.casefold())
    return paths, "directory listing (no search order evidence)", None


def _rows(records):
    rows, policies, tokens = [], [], []
    for record in records:
        policy = srcxml.name_policy(record)
        row = {"name": record.name} if policy != "absent" else {}
        row["message"] = record.message
        rows.append(row)
        policies.append(policy)
        tokens.append(srcxml.protected_tokens(record.message))
    return rows, policies, tokens


def _json(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def extract(game_root, output, *, language, archives=None, exe=None):
    root = Path(os.path.abspath(game_root))
    paths, order_source, script = _archives(root, archives, exe)
    if not paths:
        raise FormatError("no NOA archives found")
    effective, overrides, reports = {}, [], []
    for path in paths:
        with open(path, "rb") as stream:
            index = read_index(stream)
        members = [e for e in index.entries if e.path.casefold().endswith(".srcxml")]
        reports.append({"archive": path.name, "size": path.stat().st_size,
                        "entries": len(index.entries), "srcxml": len(members),
                        "encodings": sorted({e.encoding_name for e in members})})
        for entry in members:
            key = entry.path.casefold()
            if key in effective:
                overrides.append({"member": entry.path, "shadowed_in": path.name,
                                  "effective": effective[key][0].name})
                continue
            effective[key] = (path, index, entry)
    entries, outputs, empty, failures = [], [], [], []
    used = set()
    total_rows = 0
    by_archive = {}
    for key in sorted(effective):
        path, index, entry = effective[key]
        try:
            with open(path, "rb") as stream:
                raw = read_member(stream, index, entry, max_output=MAX_MEMBER)
            text = raw.decode("utf-8")
            records = srcxml.extract_records(text, language)
            identity = {r.index: {"message": r.message, **({"name": r.name} if r.name else {})}
                        for r in records}
            if srcxml.patch_records(text, identity, language) != text:
                raise FormatError("identity patch is not byte-identical")
            mismatches = srcxml.escape_convention_mismatches(text, language)
            if mismatches:
                raise FormatError(f"{len(mismatches)} attributes use an unknown escape spelling")
            if not records:
                empty.append({"archive": path.name, "member": entry.path})
                continue
            stem = entry.path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
            name = stem + ".json"
            n = 2
            while name.casefold() in used:
                name = f"{stem}__{Path(path.name).stem}_{n}.json"
                n += 1
            used.add(name.casefold())
            original = f"original/{Path(path.name).stem}/{entry.path}"
            metadata = f"metadata/{Path(path.name).stem}/{entry.path}.json"
            rows, policies, tokens = _rows(records)
            locators = [{"archive": path.name, "member": entry.path, "record": r.index,
                         "kind": r.kind, "element": r.element, "line": r.line,
                         "text_attribute": r.text_attribute,
                         "name_attribute": r.name_attribute} for r in records]
            manifest = make_manifest(
                engine=ENGINE, variant=VARIANT, reference=REFERENCE,
                sources={original: raw}, rows=rows, locators=locators, encoding="utf-8",
                name_policies=policies, protected_tokens=tokens,
                settings={"language": language, "archive": path.name, "member": entry.path,
                          "member_encoding": entry.encoding_name})
            entries += [(f"gt_input/{name}", dump_rows(rows)), (original, raw),
                        (metadata, _json(manifest))]
            outputs.append({"output": f"gt_input/{name}", "archive": path.name,
                            "member": entry.path, "rows": len(rows), "original": original,
                            "metadata": metadata})
            total_rows += len(rows)
            by_archive[path.name] = by_archive.get(path.name, 0) + 1
        except (OSError, UnicodeError, ValueError) as exc:
            failures.append({"archive": path.name, "member": entry.path,
                             "error": f"{type(exc).__name__}: {exc}"})
    for report in reports:
        if report["archive"] in by_archive:
            report["sha256"] = _sha256_file(root / report["archive"])
    summary = {"engine": ENGINE, "language": language, "archive_order": [p.name for p in paths],
               "order_source": order_source, "script_image": script,
               "srcxml_effective": len(effective), "scripts_exported": len(outputs),
               "empty_scripts": len(empty), "failures": len(failures), "rows": total_rows,
               "identity_roundtrip": "byte-identical" if not failures else "partial",
               "scripts_by_archive": by_archive}
    listed = {p.name.casefold() for p in paths}
    summary["unlisted_archives"] = sorted(
        p.name for p in root.iterdir()
        if p.is_file() and p.suffix.lower() == ".noa" and p.name.casefold() not in listed)
    loose = root / "script"
    if loose.is_dir() and any(p.suffix.lower() == ".srcxml" for p in loose.iterdir()):
        summary["warning"] = "loose script/*.srcxml exists; check which copy the game loads"
    entries += [("reports/summary.json", _json(summary)),
                ("reports/outputs.json", _json({"outputs": outputs, "overrides": overrides,
                                                "empty": empty, "failures": failures})),
                ("reports/archives.json", _json(reports))]
    write_new_tree(Path(output), entries,
                   Limits(max_entries=len(entries) + 8, max_file_bytes=MAX_MEMBER,
                          max_total_bytes=2 << 30))
    (Path(output) / "gt_output").mkdir()
    return summary


def _load_workspace(workspace):
    workspace = Path(workspace)
    outputs = load_json((workspace / "reports/outputs.json").read_bytes())["outputs"]
    summary = load_json((workspace / "reports/summary.json").read_bytes())
    return workspace, outputs, summary


def _translations(workspace, outputs, target):
    """Validated patched SRCXML bytes keyed by member path, plus expectations."""
    changed, expected, skipped_names = {}, {}, 0
    for item in outputs:
        translated_path = workspace / "gt_output" / item["output"].split("/", 1)[1]
        if not translated_path.is_file():
            continue
        manifest = load_json((workspace / item["metadata"]).read_bytes())
        raw = (workspace / item["original"]).read_bytes()
        original_rows = load_json((workspace / item["output"]).read_bytes())
        translated = validate_translation(manifest, {item["original"]: raw}, original_rows,
                                          load_json(translated_path.read_bytes()))
        source_language = manifest["settings"]["language"]
        text = raw.decode("utf-8")
        target_records = srcxml.extract_records(text, target)
        if not len(translated) == len(original_rows) == len(target_records) == \
                len(manifest["records"]):
            raise FormatError(f"record count differs for {item['member']}")
        replacements = {}
        for row, before, record, meta in zip(translated, original_rows, target_records,
                                             manifest["records"]):
            change = {}
            if target != source_language or row["message"] != before["message"]:
                change["message"] = row["message"]
            if meta["name_policy"] == "writable" and (target != source_language
                                                      or row["name"] != before["name"]):
                if srcxml.name_policy(record) == "writable":
                    change["name"] = row["name"]
                else:
                    skipped_names += 1
            if change:
                replacements[record.index] = change
        if not replacements:
            continue
        patched = srcxml.patch_records(text, replacements, target)
        member = manifest["settings"]["member"]
        changed[member] = patched.encode("utf-8")
        expected[member] = (replacements, target_records)
    return changed, expected, skipped_names


def _readback(data, expected, target):
    stream = io.BytesIO(data)
    index = read_index(stream)
    by_path = {e.path.casefold(): e for e in index.entries}
    checked = 0
    for member, (replacements, before) in expected.items():
        entry = by_path[member.casefold()]
        records = srcxml.extract_records(read_member(stream, index, entry).decode("utf-8"), target)
        if len(records) != len(before):
            raise FormatError(f"readback record count differs for {member}")
        for old, new in zip(before, records):
            change = replacements.get(old.index, {})
            if new.message != change.get("message", old.message) or \
                    new.name != change.get("name", old.name):
                raise FormatError(f"readback differs for {member} record {old.index}")
            checked += 1
    return len(index.entries), checked


def rebuild(workspace, output, *, target_language=None, base=None, name=None):
    workspace, outputs, summary = _load_workspace(workspace)
    target = target_language or summary["language"]
    changed, expected, skipped_names = _translations(workspace, outputs, target)
    if not changed:
        raise FormatError("no translated gt_output file changes any record")
    members, replaced = [], 0
    if base:
        base = Path(base)
        with open(base, "rb") as stream:
            index = read_index(stream)
            seen = set()
            for entry in index.entries:
                key = entry.path.casefold()
                original = next((m for m in changed if m.casefold() == key), None)
                if original is not None:
                    members.append(NoaMember.raw(entry.path, changed[original], entry.filetime))
                    seen.add(original)
                    replaced += 1
                else:
                    members.append(member_from_entry(stream, index, entry))
        members += [NoaMember.raw(m, data) for m, data in changed.items() if m not in seen]
        archive_name = name or base.name
    else:
        if not name:
            raise FormatError("pass --base or --name for the output archive")
        members = [NoaMember.raw(m, data) for m, data in changed.items()]
        archive_name = name
    data = build_noa(members)
    total, checked = _readback(data, expected, target)
    report = {"archive": archive_name, "size": len(data), "sha256": _sha256(data),
              "target_language": target, "members": total, "changed_members": len(changed),
              "replaced_in_base": replaced, "base": base.name if base else None,
              "checked_records": checked, "skipped_name_writes": skipped_names,
              "changed_storage": "raw (encoding 0)", "runtime": "not verified"}
    write_new_tree(Path(output), [(archive_name, data), ("reports/rebuild.json", _json(report))],
                   Limits(max_entries=4, max_file_bytes=max(len(data), 1 << 20),
                          max_total_bytes=len(data) + (1 << 20)))
    return report


def readback(workspace, archive, output, *, language=None):
    workspace, outputs, summary = _load_workspace(workspace)
    language = language or summary["language"]
    entries = []
    with open(archive, "rb") as stream:
        index = read_index(stream)
        by_path = {e.path.casefold(): e for e in index.entries}
        for item in outputs:
            entry = by_path.get(item["member"].casefold())
            if entry is None:
                continue
            text = read_member(stream, index, entry, max_output=MAX_MEMBER).decode("utf-8")
            rows, _, _ = _rows(srcxml.extract_records(text, language))
            entries.append((item["output"], dump_rows(rows)))
    if not entries:
        raise FormatError("rebuilt archive holds none of the workspace members")
    write_new_tree(Path(output), entries,
                   Limits(max_entries=len(entries) + 1, max_file_bytes=MAX_MEMBER))
    return len(entries)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    m = sub.add_parser("mounts")
    m.add_argument("exe")
    e = sub.add_parser("extract")
    e.add_argument("game")
    e.add_argument("output")
    e.add_argument("--language", required=True, help="attribute suffix, e.g. JA")
    e.add_argument("--archive", action="append", help="archive file name, highest priority first")
    e.add_argument("--exe")
    r = sub.add_parser("rebuild")
    r.add_argument("workspace")
    r.add_argument("output")
    r.add_argument("--target-language")
    r.add_argument("--base", help="archive to copy and overlay (output keeps its name)")
    r.add_argument("--name", help="output archive file name")
    b = sub.add_parser("readback")
    b.add_argument("workspace")
    b.add_argument("archive")
    b.add_argument("output")
    b.add_argument("--language")
    args = parser.parse_args(argv)
    if args.command == "mounts":
        config = read_cotomi_config(args.exe)
        order, script = mount_order(config)
        result = {"script": script, "archives": order}
    elif args.command == "extract":
        result = extract(args.game, args.output, language=args.language,
                         archives=args.archive, exe=args.exe)
    elif args.command == "rebuild":
        result = rebuild(args.workspace, args.output, target_language=args.target_language,
                         base=args.base, name=args.name)
    else:
        result = {"files": readback(args.workspace, args.archive, args.output,
                                    language=args.language)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
