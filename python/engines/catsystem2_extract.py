"""Bounded CatSystem2 INT/CST extraction into the GalTransl exchange layout.

``pack`` / ``readback`` subcommands live in catsystem2_pack (new updateNN.int).
Exit status of the extract command: 0 complete, 1 partial (some members
failed), 2 failed (nothing exported) or a usage/format error.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import re
import sys

from python.common.contract import dump_rows, make_manifest
from python.common.binary import FormatError
from python.common.handoff import STATE_FILE, handoff, source_language_note
from python.common.safety import Limits, logical_path, write_new_tree, validate_new_tree_destination
from python.engines.catsystem2 import cst_text_encodings, export_cst, patch_dialogue, read_cst
from python.archives.catsystem2_int import (extract_exe_password, probe_member, read_int,
                                            read_member, write_int)

_UPDATE = re.compile(r"^update(\d+)\.int$", re.IGNORECASE)
_KIF = b"KIF\0"
_DEFAULT_MAX_ARCHIVES = 128
_DEFAULT_MAX_MEMBERS = 100_000
_DEFAULT_MAX_TOTAL_CST = 512 * 1024 * 1024
_DEFAULT_MAX_OUTPUT = 512 * 1024 * 1024
_ENCODING_SAMPLE = 64
_EDIT_MARK = "ABC"
_NOTES = (
    "姓名形如 ID＠表示名 时只导出 ＠ 后的显示名，译名不得为空或增删 ＠；$ 开头的动态姓名只作上下文，不可改",
    "\\@、\\p 等控制符数量须保持；换行可以比原文少但不能多，以换行开头的续行须保留开头的换行数",
    "振假名 [底字/注音] 可保留、改写或整组删除，保留时两侧都不能为空，不得留下多余方括号",
    "选项文字不得含换行；命令编号与标识符不导出，不必处理",
)


def _archive_order(path: Path):
    match = _UPDATE.fullmatch(path.name)
    if match:
        return 1, int(match.group(1)), path.name.casefold()
    return 0, 0, path.name.casefold()


def _next_destination(root: Path) -> Path:
    destination = root / f"{root.name}_extract"
    suffix = 2
    while os.path.lexists(destination):
        try:
            validate_new_tree_destination(destination)
        except (FileExistsError, FormatError):
            destination = root / f"{root.name}_extract_{suffix}"
            suffix += 1
            continue
        return destination
    return destination


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _output_name(member_name: str, archive_name: str, ordinal: int,
                 used: set[str]) -> str:
    safe_member = logical_path(member_name)
    base = safe_member.rsplit("/", 1)[-1]
    stem = base[:-4] if base.casefold().endswith(".cst") else base
    candidate = f"{stem}.json"
    if candidate.casefold() in used:
        candidate = f"{stem}__{Path(archive_name).stem}_m{ordinal:08d}.json"
    suffix = 2
    original = candidate
    while candidate.casefold() in used:
        candidate = f"{Path(original).stem}_{suffix}.json"
        suffix += 1
    used.add(candidate.casefold())
    return candidate


def _discover_archives(game_root: Path, archive_paths) -> list[Path]:
    if archive_paths is None:
        paths = list(game_root.glob("*.int"))
    else:
        paths = []
        for value in archive_paths:
            path = Path(value)
            if not path.is_absolute():
                path = game_root / path
            paths.append(path)
    paths = sorted(paths, key=_archive_order)
    if not paths:
        raise ValueError("no CatSystem2 INT archives found")
    if len(paths) > _DEFAULT_MAX_ARCHIVES:
        raise ValueError("CatSystem2 archive count exceeds limit")
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise ValueError(f"CatSystem2 archive path is not a file: {missing[0]}")
    names = [path.name.casefold() for path in paths]
    if len(names) != len(set(names)):
        raise ValueError("CatSystem2 archive basenames must be unique")
    return paths


def _archive_encoding(counts: Counter) -> str | None:
    """Archive-level evidence: members that decode under exactly one encoding."""
    cp932, utf8 = counts["cp932"], counts["utf-8"]
    if cp932 and utf8:
        return "mixed"
    if cp932:
        return "cp932"
    if utf8:
        return "utf-8"
    return None


def _classification_key(found) -> str:
    if found is None:
        return "ascii"
    if len(found) == 1:
        return found[0]
    return "both" if found else "none"


def _sample_encoding(path: Path, archive, entries, max_member: int) -> str | None:
    """Encoding evidence from a bounded sample of shadowed copies (warnings only)."""
    counts = Counter()
    with path.open("rb") as stream:
        for entry in sorted(entries, key=lambda e: e.index)[:_ENCODING_SAMPLE]:
            try:
                found = cst_text_encodings(read_member(stream, entry, archive.cipher,
                                                       max_member=max_member))
            except (OSError, UnicodeError, ValueError):
                continue
            counts[_classification_key(found)] += 1
    return _archive_encoding(counts)


def _overlay_warnings(groups, archive_info, sample) -> list[str]:
    """Explain shadowing that is not plain official update overlay."""
    warnings = []
    for (base, effective), members in sorted(groups.items()):
        base_info, effective_info = archive_info[base], archive_info[effective]
        order_unproven = _UPDATE.fullmatch(base) is None and _UPDATE.fullmatch(effective) is None
        patch_side = None
        if effective_info["encrypted"] is False and base_info["encrypted"] is True:
            patch_side = effective
        elif effective_info["encrypted"] is True and base_info["encrypted"] is False:
            patch_side = base
        effective_encoding = effective_info.get("script_encoding")
        base_encoding = base_info.get("script_encoding") or sample(base, members)
        differ = (effective_encoding in ("cp932", "utf-8") and base_encoding in ("cp932", "utf-8")
                  and effective_encoding != base_encoding)
        if patch_side is None and not differ and not order_unproven:
            continue
        parts = [f"{effective} overrides {len(members)} CST member(s) of {base}"]
        if order_unproven:
            parts.append("neither is an updateNN.int, so this order comes from file names only "
                         "and is not proven")
        if differ:
            parts.append(f"text encodings differ ({effective}: {effective_encoding}, "
                         f"{base}: {base_encoding})")
        if patch_side == effective:
            parts.append(f"{effective} is unencrypted while {base} is encrypted, so the exported "
                         f"copies look like an existing translation patch; the originals are in "
                         f"{base}: extract them with --archive {base}")
        elif patch_side == base:
            parts.append(f"{base} is unencrypted while {effective} is encrypted, so {base} looks "
                         f"like a translation patch and the exported copies from {effective} "
                         f"look original; check which pack the game actually loads")
        elif differ:
            parts.append("one of them is probably a translation patch; check which holds the "
                         "original and select it with --archive")
        else:
            parts.append("select the intended pack with --archive")
        warnings.append("; ".join(parts))
    return warnings


def _verify_edit(entry, raw, exported, encoding, archive_encrypted, password) -> dict:
    """Write one changed row through the CST writer and an INT writer, then re-read it."""
    rows = [dict(row) for row in exported.rows]
    rows[0]["message"] += _EDIT_MARK
    patched = patch_dialogue(raw, exported, rows, encoding)
    encrypted = bool(archive_encrypted and password is not None)
    options = {"password": password} if encrypted else {}
    packed = write_int([(entry.name, patched)], encrypted=encrypted, **options)
    archive = read_int(packed, **options)
    data = read_member(packed, archive.entries[0], archive.cipher)
    if data != patched or list(export_cst(data, encoding).rows) != rows:
        raise ValueError("edited CST differs after INT write and re-read")
    return {"member": entry.name, "row": 0, "size_delta": len(patched) - len(raw),
            "int_rewritten": "encrypted" if encrypted else "plain",
            "reparsed": True, "runtime_verified": False}


def extract_game(game_root, *, output=None, exe=None, password: str | None = None,
                 archive_paths=None, max_members: int = _DEFAULT_MAX_MEMBERS,
                 max_member: int = 64 * 1024 * 1024,
                 max_decoded_member: int = 64 * 1024 * 1024,
                 max_total_cst: int = _DEFAULT_MAX_TOTAL_CST,
                 max_output: int = _DEFAULT_MAX_OUTPUT, verify_edits: bool = False) -> dict:
    """Extract effective CatSystem2 dialogue without modifying any input file.

    Named members are overlaid in archive order, with numeric ``updateNN.int`` packages
    after base packages. If no password can be recovered, content probing still works,
    but names are ordinal and cross-archive overlays cannot be inferred. Each CST's
    text encoding (CP932 or UTF-8) is determined strictly per member, with the
    archive's other members as evidence when both decode; it is never guessed.
    """
    root = Path(os.path.abspath(game_root))
    if not root.is_dir():
        raise ValueError("CatSystem2 game root is not a directory")
    for value, label in ((max_members, "member"), (max_member, "member-size"),
                         (max_decoded_member, "decoded-member"),
                         (max_total_cst, "decoded-total"), (max_output, "output")):
        if type(value) is not int or value < 1:
            raise ValueError(f"invalid CatSystem2 {label} limit")
    archives = _discover_archives(root, archive_paths)
    warnings = []
    resolved_password = password
    if resolved_password is None:
        exe_path = Path(exe) if exe is not None else root / "cs2.exe"
        if not exe_path.is_absolute():
            exe_path = root / exe_path
        if exe_path.is_file():
            try:
                resolved_password = extract_exe_password(exe_path)
            except ValueError as error:
                warnings.append(f"password recovery failed: {error}")
        else:
            warnings.append("no CatSystem2 executable was available for filename recovery")

    archive_reports = []
    archive_info = {}
    candidates = []
    failures = []
    skipped = []
    total_members = 0
    for path in archives:
        report = {"archive": path.name, "size": path.stat().st_size,
                  "encrypted": None, "names_recovered": False,
                  "entries": 0, "cst_members": 0, "status": "blocked"}
        archive_info[path.name] = report
        try:
            with path.open("rb") as stream:
                if stream.read(len(_KIF)) != _KIF:
                    report["status"] = "skipped-not-kif"
                    skipped.append({"archive": path.name, "reason": "no KIF header; not a CatSystem2 INT"})
                    if archive_paths is not None:
                        warnings.append(f"{path.name} was requested but is not a KIF archive; skipped")
                    archive_reports.append(report)
                    continue
                archive = read_int(stream, password=resolved_password, max_entries=max_members)
                report["encrypted"] = archive.encrypted
                report["names_recovered"] = archive.names_recovered
                report["entries"] = len(archive.entries)
                if len(archive.entries) > max_members - total_members:
                    raise ValueError("CatSystem2 cumulative member count exceeds limit")
                total_members += len(archive.entries)
                cst_entries = []
                for entry in archive.entries:
                    try:
                        suffix_match = entry.name_known and entry.name.casefold().endswith(".cst")
                        if suffix_match or probe_member(stream, entry, archive.cipher,
                                                        max_bytes=8) == b"CatScene":
                            cst_entries.append(entry)
                            candidates.append((path, archive, entry))
                    except (OSError, UnicodeError, ValueError) as error:
                        failures.append({
                            "phase": "probe",
                            "archive": path.name,
                            "member": entry.name,
                            "member_index": entry.index,
                            "error": f"{type(error).__name__}: {error}",
                        })
                report["cst_members"] = len(cst_entries)
                report["status"] = "indexed"
        except (OSError, UnicodeError, ValueError) as error:
            report["error"] = f"{type(error).__name__}: {error}"
            failures.append({"phase": "index", "archive": path.name,
                             "error": report["error"]})
        archive_reports.append(report)

    selected = {}
    overrides = []
    shadowed = defaultdict(list)
    for path, archive, entry in candidates:
        if entry.name_known:
            identity = entry.name.replace("\\", "/").casefold()
        else:
            identity = f"{path.name.casefold()}#{entry.index}"
        if identity in selected:
            previous = selected[identity]
            overrides.append({
                "member": entry.name,
                "replaced_archive": previous[0].name,
                "effective_archive": path.name,
            })
            shadowed[identity].append(previous)
        selected[identity] = (path, archive, entry)

    output_entries = []
    output_records = []
    empty = []
    used_names = set()
    total_cst = 0
    total_rows = 0
    choices_excluded = 0
    roundtrip_passed = 0
    roundtrip_failed = 0
    orphan_names = 0
    name_command_crossings = 0
    scripts_by_archive = Counter()
    rows_by_archive = Counter()
    encodings_used = Counter()
    source_archives = set()
    texts = []
    first_json = None
    edit_check = None

    def member_failure(phase, path, entry, error, identity):
        record = {"phase": phase, "archive": path.name, "member": entry.name,
                  "member_index": entry.index, "error": error}
        older = [item[0].name for item in shadowed.get(identity, ())]
        if older:
            record["shadowed_copies_in"] = older
        failures.append(record)

    # Pass 1: read every effective member and classify its text encoding.
    ordered = sorted(selected.items(), key=lambda item: (_archive_order(item[1][0]),
                                                          item[1][2].name.casefold(),
                                                          item[1][2].index))
    loaded = []
    evidence = defaultdict(Counter)
    for identity, (path, archive, entry) in ordered:
        try:
            raw = read_member(path, entry, archive.cipher, max_member=max_member)
            if len(raw) >= 16 and raw[:8] == b"CatScene":
                declared_output = int.from_bytes(raw[12:16], "little")
                if declared_output > max_decoded_member:
                    raise ValueError("CST member expansion exceeds limit")
                if declared_output > max_total_cst - total_cst:
                    raise ValueError("CatSystem2 decoded CST total exceeds limit")
                total_cst += declared_output
            found = cst_text_encodings(raw, max_output=max_decoded_member)
        except (OSError, UnicodeError, ValueError) as error:
            member_failure("member", path, entry, f"{type(error).__name__}: {error}", identity)
            continue
        evidence[path.name][_classification_key(found)] += 1
        loaded.append((identity, path, archive, entry, raw, found))
    for name, counts in evidence.items():
        archive_info[name]["script_encoding"] = _archive_encoding(counts)
        archive_info[name]["script_encoding_evidence"] = dict(counts)

    # Pass 2: export with the determined encoding and prove the identity roundtrip.
    for identity, path, archive, entry, raw, found in loaded:
        archive_encoding = archive_info[path.name].get("script_encoding")
        if found is None:
            encoding = archive_encoding if archive_encoding in ("cp932", "utf-8") else "cp932"
            basis = "ascii-only"
        elif len(found) == 1:
            encoding, basis = found[0], "only strict decoding"
        elif found and archive_encoding in ("cp932", "utf-8"):
            encoding, basis = archive_encoding, f"archive evidence ({path.name})"
        elif found:
            member_failure("encoding", path, entry,
                           "text decodes as both strict CP932 and strict UTF-8 and "
                           f"{path.name} gives no single-encoding evidence; not guessed", identity)
            continue
        else:
            member_failure("encoding", path, entry,
                           "text decodes as neither strict CP932 nor strict UTF-8 "
                           "(mixed or other encoding); not exported", identity)
            continue
        try:
            scene = read_cst(raw, encoding, max_output=max_decoded_member)
            exported = export_cst(scene)
            try:
                if patch_dialogue(raw, exported, list(exported.rows), encoding) != raw:
                    raise ValueError("CatSystem2 identity dialogue roundtrip is not byte-identical")
            except ValueError:
                roundtrip_failed += 1
                raise
            roundtrip_passed += 1
            orphan_names += len(exported.orphan_names)
            name_command_crossings += len(exported.name_command_crossings)
            if not exported.rows:
                empty.append({"archive": path.name, "member": entry.name,
                              "member_index": entry.index})
                continue

            output_name = _output_name(entry.name, path.name, entry.index, used_names)
            if verify_edits and edit_check is None:
                edit_check = {"json": output_name,
                              **_verify_edit(entry, raw, exported, encoding,
                                             archive.encrypted, resolved_password)}
            archive_id = Path(path.name).stem
            original_name = f"original/{archive_id}/m{entry.index:08d}.cst"
            metadata_name = f"metadata/{archive_id}/m{entry.index:08d}.json"
            source_name = original_name
            locators = [{
                "archive": path.name,
                "member": entry.name,
                "member_index": entry.index,
                **locator,
            } for locator in exported.locators]
            rows = list(exported.rows)
            manifest = make_manifest(
                engine="catsystem2",
                variant="kif-int/catscene-cst",
                reference="python/archives/catsystem2_int.py + catsystem2.py",
                sources={source_name: raw},
                rows=rows,
                locators=locators,
                encoding=encoding,
                name_policies=list(exported.name_policies),
                protected_tokens=[list(tokens) for tokens in exported.protected_tokens],
                settings={
                    "archive_encrypted": archive.encrypted,
                    "names_recovered": archive.names_recovered,
                    "effective_overlay": entry.name_known,
                    "encoding_basis": basis,
                    "excluded_choice_records": list(exported.excluded_choices),
                    "orphan_name_records": list(exported.orphan_names),
                    "name_command_crossings": [
                        {"name_record": name_index, "command_records": list(commands)}
                        for name_index, commands in exported.name_command_crossings
                    ],
                },
            )
            output_entries.extend([
                (f"gt_input/{output_name}", dump_rows(rows)),
                (original_name, raw),
                (metadata_name,
                 (json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False)
                  + "\n").encode("utf-8")),
            ])
            output_records.append({
                "output": f"gt_input/{output_name}",
                "archive": path.name,
                "member": entry.name,
                "member_index": entry.index,
                "rows": len(rows),
                "encoding": encoding,
                "original": original_name,
                "metadata": metadata_name,
            })
            first_json = first_json or output_name
            texts.extend(row["message"] for row in rows)
            source_archives.add(path)
            total_rows += len(rows)
            choices_excluded += len(exported.excluded_choices)
            scripts_by_archive[path.name] += 1
            rows_by_archive[path.name] += len(rows)
            encodings_used[encoding] += 1
        except (OSError, UnicodeError, ValueError) as error:
            member_failure("member", path, entry, f"{type(error).__name__}: {error}", identity)
    if verify_edits and edit_check is None and output_records:
        raise ValueError("--verify-edits found no exported script to edit")

    groups = defaultdict(list)
    for item in overrides:
        groups[(item["replaced_archive"], item["effective_archive"])].append(item["member"])
    by_archive_member = {}
    for path, archive, entry in candidates:
        by_archive_member[(path.name, entry.name.replace("\\", "/").casefold())] = (path, archive, entry)

    def sample(base, members):
        hits = [by_archive_member.get((base, member.replace("\\", "/").casefold()))
                for member in members]
        hits = [hit for hit in hits if hit is not None]
        if not hits:
            return None
        return _sample_encoding(hits[0][0], hits[0][1], [hit[2] for hit in hits], max_member)

    warnings.extend(_overlay_warnings(groups, archive_info, sample))
    language_note = source_language_note(texts)
    if language_note:
        warnings.append(language_note)

    effective_failures = sum(1 for item in failures if item["phase"] in ("member", "encoding"))
    if not output_records:
        status = "failed"
    elif failures:
        status = "partial"
    else:
        status = "complete"
    not_reached = len(selected) - roundtrip_passed - roundtrip_failed

    for report, path in zip(archive_reports, archives):
        report["sha256"] = _sha256_file(path) if path in source_archives else None
    destination = _next_destination(root) if output is None else Path(output)
    if not destination.is_absolute():
        destination = root / destination
    summary = {
        "engine": "catsystem2",
        "status": status,
        "game_root": str(root),
        "output": str(destination),
        "password_recovered": resolved_password is not None,
        "password_disclosed": False,
        "archives_scanned": len(archives),
        "archives_skipped": len(skipped),
        "members_scanned": total_members,
        "raw_cst_members": len(candidates),
        "effective_cst_members": len(selected),
        "overridden_cst_members": len(overrides),
        "scripts_exported": len(output_records),
        "empty_scripts": len(empty),
        "parse_failures": len(failures),
        "member_failures": effective_failures,
        "dialogue_rows": total_rows,
        "decoded_cst_bytes": total_cst,
        "script_encodings": dict(encodings_used),
        "choice_commands_excluded": choices_excluded,
        "orphan_name_records": orphan_names,
        "name_command_crossings": name_command_crossings,
        "identity_roundtrip": {
            "status": ("complete" if roundtrip_failed == 0 and not_reached == 0
                       else "partial" if roundtrip_passed else "failed"),
            "passed": roundtrip_passed,
            "failed": roundtrip_failed,
            "not_reached": not_reached,
        },
        "scripts_by_archive": dict(scripts_by_archive),
        "rows_by_archive": dict(rows_by_archive),
        "skipped_archives": skipped,
        "failures_by_archive": dict(Counter(item["archive"] for item in failures)),
        "warnings": warnings,
    }
    if edit_check is not None:
        summary["edit_check"] = edit_check
    if output_records:
        notes = list(_NOTES)
        if "utf-8" in encodings_used:
            notes.append(f"{encodings_used['utf-8']} 个脚本以 UTF-8 存储（其余为 CP932），回写沿用各自 manifest 记录的编码")
        notes = [w for w in warnings if w != language_note][:3] + notes
        if language_note:
            notes.insert(0, language_note)
        if failures:
            notes.append(f"{len(failures)} 个成员或归档未导出，见 reports/outputs.json 的 failures")
        summary["delivery"], state = handoff(
            workspace=destination, engine="CatSystem2（KIF/INT 归档中的 CatScene CST）",
            json_files=len(output_records), rows=total_rows, notes=notes,
            verified="各 CST 经 patch_dialogue 原文回写后与原字节一致",
            edit_checked=edit_check is not None, first_json=first_json,
            first_json_basis="加载顺序与名称排序中第一个有文本的脚本，未确认是否开场",
            command="extract --verify-edits" if verify_edits else "extract",
            open_items="；".join(warnings[:3]) or "无", report="reports/summary.json")
        output_entries.append((STATE_FILE, state))
    output_entries.extend([
        ("reports/summary.json",
         (json.dumps(summary, ensure_ascii=False, indent=2) + "\n").encode("utf-8")),
        ("reports/outputs.json",
         (json.dumps({"outputs": output_records, "overrides": overrides,
                      "empty": empty, "skipped": skipped, "failures": failures},
                     ensure_ascii=False, indent=2) + "\n").encode("utf-8")),
        ("reports/archives.json",
         (json.dumps(archive_reports, ensure_ascii=False, indent=2) + "\n").encode("utf-8")),
    ])

    write_new_tree(destination, output_entries,
                   Limits(max_entries=max_members * 3 + 4, max_file_bytes=max_member,
                          max_total_bytes=max_output))
    (destination / "gt_output").mkdir()
    return summary


def _pack_main(argv) -> int:
    from python.engines.catsystem2_pack import pack, read_back
    parser = argparse.ArgumentParser(description="CatSystem2 update INT patch: pack / readback")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("pack", "readback"):
        command = commands.add_parser(name)
        command.add_argument("workspace", help="extraction workspace (or JIS prepared workspace/)")
        if name == "pack":
            command.add_argument("output", help="new directory for updateNN.int + reports")
            command.add_argument("--number", type=int, help="update number (default: highest + 1)")
            command.add_argument("--translations", help="translation JSON directory; default gt_output")
            command.add_argument("--readback", help="new directory for the overlay re-extraction")
        else:
            command.add_argument("rebuilt", help="pack output directory")
            command.add_argument("output", help="new readback directory")
        command.add_argument("--game", dest="game_root", help="game directory (default: from workspace)")
        command.add_argument("--exe")
        command.add_argument("--password")
    args = vars(parser.parse_args(argv))
    action = args.pop("command")
    try:
        result = pack(**args) if action == "pack" else read_back(**args)
    except (OSError, ValueError) as error:
        print(json.dumps({"ok": False, "error": f"{type(error).__name__}: {error}"},
                         ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("pack", "readback"):
        return _pack_main(argv)
    parser = argparse.ArgumentParser(
        description="Extract CatSystem2 INT/CST dialogue (subcommands: pack, readback). "
                    "Exit 0 complete, 1 partial, 2 failed.")
    parser.add_argument("game_root")
    parser.add_argument("--output", help="new workspace directory (default: <game>/<game>_extract)")
    parser.add_argument("--exe")
    parser.add_argument("--password")
    parser.add_argument("--archive", action="append", dest="archives",
                        help="INT to read instead of every *.int (repeatable); e.g. the original "
                             "scene.int when a translation patch overrides it")
    parser.add_argument("--verify-edits", action="store_true",
                        help="also write one edited row through the CST and INT writers and re-read it")
    args = parser.parse_args(argv)
    try:
        summary = extract_game(args.game_root, output=args.output, exe=args.exe,
                               password=args.password, archive_paths=args.archives,
                               verify_edits=args.verify_edits)
    except (OSError, ValueError) as error:
        print(f"error: {type(error).__name__}: {error}", file=sys.stderr)
        return 2
    for warning in summary["warnings"]:
        print(f"warning: {warning}", file=sys.stderr)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return {"complete": 0, "partial": 1}.get(summary["status"], 2)


if __name__ == "__main__":
    raise SystemExit(main())
