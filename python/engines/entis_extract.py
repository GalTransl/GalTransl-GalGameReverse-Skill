# SPDX-License-Identifier: GPL-3.0-or-later
"""Entis GLS workflow: NOA -> SRCXML -> GalTransl JSON, and back to a patch NOA.

Subcommands (all read-only on the game directory; outputs go to new directories):
  mounts   print the startup script and archive search order from the EXE's
           IDR_COTOMI resource (ERISA-N compressed XML; read as data, not run)
  extract  export msg/menu/open_line_msg text of the effective .srcxml members
           (exit 0 complete, 1 partial, 2 failed or error)
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
from python.archives.entis_noa import (NoaMember, build_noa, is_noa, member_from_entry,
                                       read_index, read_member)
from python.common.binary import FormatError
from python.common.contract import dump_rows, load_json, make_manifest, validate_translation
from python.common.handoff import STATE_FILE, handoff, source_language_note
from python.common.safety import Limits, write_new_tree
from python.engines import entis_srcxml as srcxml

ENGINE = "entis-gls"
VARIANT = "noa/srcxml-attribute-dialect"
REFERENCE = "python/archives/entis_noa.py + python/engines/entis_srcxml.py"
MAX_MEMBER = 64 * 1024 * 1024
MAX_EXE = 256 * 1024 * 1024
_ARCHIVE = re.compile(r"""<archive\s+path\s*=\s*"([^"]+)"\s*/>""")
_SCRIPT = re.compile(r"""<script\s+src\s*=\s*"([^"]+)\"""")
_EDIT_MARK = "ABC"
_NOTES = (
    "%name、%fp、%fname、%nck、%nick 等引擎变量和反斜杠序列（注音 \\r;漢字;かな:、换行 \\n 等）须原样保留、数量不变",
    "译文不得含真实换行，换行用脚本自己的 \\n；姓名为 %name 等变量的条目只作上下文，不可改",
    "SRCXML 为 UTF-8，不需要 JIS 替换；预渲染位图字体（.bmf）是否含简体字形须试注确认",
)


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
    """The one startup configuration in ``root``: (exe, config), or (None, None).

    Several EXEs with different mount tables (typically an original launcher
    and one shipped by a translation patch that mounts extra archives first)
    are ambiguous: the caller must choose with ``--exe``.
    """
    exes = sorted(p for p in root.iterdir() if p.is_file() and p.suffix.lower() == ".exe")
    found = []
    for exe in exes:
        try:
            found.append((exe, read_cotomi_config(exe)))
        except (OSError, FormatError, ValueError):
            continue
    if not found:
        return None, None
    tables = [(exe, mount_order(config)) for exe, config in found]
    distinct = {(tuple(n.casefold() for n in order), (script or "").casefold())
                for _, (order, script) in tables}
    if len(distinct) == 1:
        return found[0]
    common = set.intersection(*({n.casefold() for n in order} for _, (order, _) in tables))
    described = []
    for exe, (order, script) in tables:
        extra = [n for n in order if n.casefold() not in common]
        described.append(f"{exe.name}: mounts {', '.join(order)}"
                         + (f" (only this one: {', '.join(extra)})" if extra else "")
                         + (f", script {script}" if script else ""))
    raise FormatError(
        "several EXEs carry an IDR_COTOMI startup table and their mount tables differ; "
        "pass --exe for the launcher whose text you want (an EXE that mounts extra archives "
        "first usually belongs to a translation patch): " + " | ".join(described))


def _archives(root, archive_names, exe):
    """Return (ordered archive paths, order source, script image name, exe name)."""
    if archive_names:
        paths = [root / name for name in archive_names]
        return paths, "explicit", None, None
    config = None
    if exe:
        exe = Path(exe)
        config = read_cotomi_config(exe)
    else:
        exe, config = _find_exe(root)
    if config:
        order, script = mount_order(config)
        paths = [root / name for name in order if (root / name).is_file()]
        return paths, "IDR_COTOMI", script, exe.name
    paths = sorted((p for p in root.iterdir() if p.is_file() and p.suffix.lower() == ".noa"),
                   key=lambda p: p.name.casefold())
    return paths, "directory listing (no search order evidence)", None, None


def _noa_signature(path):
    with open(path, "rb") as stream:
        return is_noa(stream.read(0x40))


def _language(texts):
    """Single language suffix shared by the members ('' = unsuffixed text)."""
    found = set()
    for text in texts:
        try:
            found |= set(srcxml.languages(text))
        except ValueError:
            continue  # reported when the member itself is processed
    if len(found) > 1:
        raise FormatError(f"SRCXML members carry several languages {sorted(found)}; "
                          f"pass --language with one of them")
    return next(iter(found), "")


def _verify_edit(member, text, records, language):
    """Patch one record, store it in a new NOA, read it back and re-parse it."""
    record = records[0]
    expected = record.message + _EDIT_MARK
    patched = srcxml.patch_records(text, {record.index: {"message": expected}}, language)
    data = build_noa([NoaMember.raw(member, patched.encode("utf-8"))])
    stream = io.BytesIO(data)
    index = read_index(stream)
    back = srcxml.extract_records(read_member(stream, index, index.entries[0]).decode("utf-8"),
                                  language)
    if len(back) != len(records) or back[0].message != expected or \
            [r.message for r in back[1:]] != [r.message for r in records[1:]]:
        raise FormatError("edited SRCXML differs after NOA write and re-read")
    return {"member": member, "record": record.index,
            "size_delta": len(patched.encode("utf-8")) - len(text.encode("utf-8")),
            "noa_rewritten": "raw", "reparsed": True, "runtime_verified": False}


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


def extract(game_root, output, *, language=None, archives=None, exe=None, verify_edits=False):
    """Export the effective SRCXML members; ``language=None`` detects the suffix.

    Returns the summary; ``status`` is complete, partial (some members or
    archives failed) or failed (nothing exported).
    """
    root = Path(os.path.abspath(game_root))
    paths, order_source, script, exe_name = _archives(root, archives, exe)
    if not paths:
        raise FormatError("no NOA archives found")
    effective, overrides, reports, skipped, archive_failures = {}, [], [], [], []
    for path in paths:
        try:
            if not _noa_signature(path):
                if order_source.startswith("directory"):
                    skipped.append({"archive": path.name,
                                    "reason": "no Entis ERISA-Archive signature; not a NOA"})
                    continue
                raise FormatError("not an Entis ERISA-Archive file (NOA)")
            with open(path, "rb") as stream:
                index = read_index(stream)
        except (OSError, ValueError) as exc:
            archive_failures.append({"archive": path.name,
                                     "error": f"{type(exc).__name__}: {path.name}: {exc}"})
            continue
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
    if not reports:
        raise FormatError("no readable NOA archive: " + "; ".join(
            f["error"] for f in archive_failures) if archive_failures else "no NOA archives found")
    entries, outputs, empty, failures = [], [], [], []
    # Pass 1: decode every effective member (the language is chosen across all of them).
    decoded = []
    for key in sorted(effective):
        path, index, entry = effective[key]
        try:
            with open(path, "rb") as stream:
                raw = read_member(stream, index, entry, max_output=MAX_MEMBER)
            decoded.append((path, entry, raw, raw.decode("utf-8")))
        except (OSError, UnicodeError, ValueError) as exc:
            failures.append({"archive": path.name, "member": entry.path,
                             "error": f"{type(exc).__name__}: {exc}"})
    language_source = "explicit"
    if language is None:
        language, language_source = _language(text for _, _, _, text in decoded), "auto"
    used = set()
    total_rows = 0
    literal_space_total = 0
    by_archive = {}
    texts, first_json, edit_check = [], None, None
    for path, entry, raw, text in decoded:
        try:
            records = srcxml.extract_records(text, language)
            identity = {r.index: {"message": r.message, **({"name": r.name} if r.name else {})}
                        for r in records}
            if srcxml.patch_records(text, identity, language) != text:
                raise FormatError("identity patch is not byte-identical")
            literal_spaces = []
            mismatches = srcxml.escape_convention_mismatches(text, language,
                                                             literal_spaces=literal_spaces)
            if mismatches:
                shown = ", ".join(f"record {i} {key}" for i, key in mismatches[:5])
                raise FormatError(f"{len(mismatches)} attribute(s) use an escape spelling other "
                                  f"than the engine's (&#N; for U+0020 and below, &amp;, &quot;) "
                                  f"and are not proven safe to rewrite: {shown}")
            if not records:
                empty.append({"archive": path.name, "member": entry.path})
                continue
            stem = entry.path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
            name = stem + ".json"
            n = 2
            while name.casefold() in used:
                name = f"{stem}__{Path(path.name).stem}_{n}.json"
                n += 1
            if verify_edits and edit_check is None:
                edit_check = {"json": name, **_verify_edit(entry.path, text, records, language)}
            used.add(name.casefold())
            original = f"original/{Path(path.name).stem}/{entry.path}"
            metadata = f"metadata/{Path(path.name).stem}/{entry.path}.json"
            rows, policies, tokens = _rows(records)
            locators = [{"archive": path.name, "member": entry.path, "record": r.index,
                         "kind": r.kind, "element": r.element, "line": r.line,
                         "text_attribute": r.text_attribute,
                         "name_attribute": r.name_attribute} for r in records]
            settings = {"language": language, "archive": path.name, "member": entry.path,
                        "member_encoding": entry.encoding_name}
            if literal_spaces:
                settings["literal_space_attributes"] = [list(item) for item in literal_spaces]
            manifest = make_manifest(
                engine=ENGINE, variant=VARIANT, reference=REFERENCE,
                sources={original: raw}, rows=rows, locators=locators, encoding="utf-8",
                name_policies=policies, protected_tokens=tokens, settings=settings)
            entries += [(f"gt_input/{name}", dump_rows(rows)), (original, raw),
                        (metadata, _json(manifest))]
            outputs.append({"output": f"gt_input/{name}", "archive": path.name,
                            "member": entry.path, "rows": len(rows), "original": original,
                            "metadata": metadata})
            total_rows += len(rows)
            literal_space_total += len(literal_spaces)
            by_archive[path.name] = by_archive.get(path.name, 0) + 1
            first_json = first_json or name
            texts.extend(row["message"] for row in rows)
        except (OSError, UnicodeError, ValueError) as exc:
            failures.append({"archive": path.name, "member": entry.path,
                             "error": f"{type(exc).__name__}: {exc}"})
    for report in reports:
        if report["archive"] in by_archive:
            report["sha256"] = _sha256_file(root / report["archive"])
    failed_total = len(failures) + len(archive_failures)
    status = "failed" if not outputs else "partial" if failed_total else "complete"
    warnings = []
    summary = {"engine": ENGINE, "status": status, "language": language,
               "language_source": language_source, "exe": exe_name,
               "archive_order": [p.name for p in paths],
               "order_source": order_source, "script_image": script,
               "srcxml_effective": len(effective), "scripts_exported": len(outputs),
               "empty_scripts": len(empty), "failures": len(failures), "rows": total_rows,
               "identity_roundtrip": "byte-identical" if not failures else "partial",
               "scripts_by_archive": by_archive, "skipped_archives": skipped,
               "archive_failures": archive_failures,
               "literal_space_attributes": literal_space_total}
    listed = {p.name.casefold() for p in paths} - {s["archive"].casefold() for s in skipped}
    summary["unlisted_archives"] = sorted(
        p.name for p in root.iterdir()
        if p.is_file() and p.suffix.lower() == ".noa" and p.name.casefold() not in listed)
    loose = root / "script"
    if loose.is_dir() and any(p.suffix.lower() == ".srcxml" for p in loose.iterdir()):
        summary["warning"] = "loose script/*.srcxml exists; check which copy the game loads"
        warnings.append(summary["warning"])
    if literal_space_total:
        warnings.append(f"{literal_space_total} exported attribute(s) hold literal spaces where the "
                        "engine writes &#32;: those files were not written by the engine's own "
                        "tool (likely an existing translation patch); check that the exported "
                        "archive holds the original text")
    language_note = source_language_note(texts)
    if language_note:
        warnings.append(language_note)
    if failures:
        common = {}
        for item in failures:
            common[item["error"]] = common.get(item["error"], 0) + 1
        top, count = max(common.items(), key=lambda kv: kv[1])
        warnings.append(f"{len(failures)} SRCXML member(s) failed; most common ({count}): {top}")
    for item in archive_failures:
        warnings.append(f"archive not read: {item['error']}")
    summary["warnings"] = warnings
    if edit_check is not None:
        summary["edit_check"] = edit_check
    if outputs:
        slot = f"text_{language}/name_{language}" if language else "无后缀 text/name"
        notes = [f"导出的是 {slot} 槽位；rebuild 默认写回同一槽位，--target-language 可写入其他语言槽位",
                 *_NOTES]
        notes = warnings[:3] + notes
        if failed_total:
            notes.append(f"{failed_total} 个成员或归档未导出，见 reports/outputs.json 与 summary.json")
        summary["delivery"], state = handoff(
            workspace=Path(output), engine="Entis GLS（NOA 归档中的 SRCXML 多语言脚本）",
            json_files=len(outputs), rows=total_rows, notes=notes,
            verified="各 SRCXML 恒等回写逐字节一致",
            edit_checked=edit_check is not None, first_json=first_json,
            first_json_basis="成员名排序中第一个有文本的脚本，未确认是否开场",
            command="extract --verify-edits" if verify_edits else "extract",
            open_items="；".join(warnings[:3]) or "无", report="reports/summary.json")
        entries.append((STATE_FILE, state))
    entries += [("reports/summary.json", _json(summary)),
                ("reports/outputs.json", _json({"outputs": outputs, "overrides": overrides,
                                                "empty": empty, "failures": failures,
                                                "archive_failures": archive_failures,
                                                "skipped_archives": skipped})),
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
    e.add_argument("--language", help="attribute suffix such as JA; '' selects unsuffixed "
                                      "text/name; default: detected when the members agree")
    e.add_argument("--archive", action="append", help="archive file name, highest priority first")
    e.add_argument("--exe", help="launcher whose IDR_COTOMI mount table is used "
                                 "(required when several EXEs carry different tables)")
    e.add_argument("--verify-edits", action="store_true",
                   help="also write one edited record through the SRCXML and NOA writers and "
                        "re-read it")
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
    try:
        if args.command == "mounts":
            config = read_cotomi_config(args.exe)
            order, script = mount_order(config)
            result = {"script": script, "archives": order}
        elif args.command == "extract":
            result = extract(args.game, args.output, language=args.language,
                             archives=args.archive, exe=args.exe,
                             verify_edits=args.verify_edits)
        elif args.command == "rebuild":
            result = rebuild(args.workspace, args.output, target_language=args.target_language,
                             base=args.base, name=args.name)
        else:
            result = {"files": readback(args.workspace, args.archive, args.output,
                                        language=args.language)}
    except (OSError, ValueError) as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    for warning in result.get("warnings", []) if isinstance(result, dict) else []:
        print(f"warning: {warning}", file=sys.stderr)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.command == "extract":
        return {"complete": 0, "partial": 1}.get(result["status"], 2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
