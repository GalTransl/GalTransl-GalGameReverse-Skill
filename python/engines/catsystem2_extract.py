"""Bounded CatSystem2 INT/CST extraction into the GalTransl exchange layout."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re

from python.common.contract import dump_rows, make_manifest
from python.common.safety import Limits, logical_path, write_new_tree
from python.engines.catsystem2 import export_cst, patch_dialogue, read_cst
from python.archives.catsystem2_int import extract_exe_password, probe_member, read_int, read_member

_UPDATE = re.compile(r"^update(\d+)\.int$", re.IGNORECASE)
_DEFAULT_MAX_ARCHIVES = 128
_DEFAULT_MAX_MEMBERS = 100_000
_DEFAULT_MAX_TOTAL_CST = 512 * 1024 * 1024
_DEFAULT_MAX_OUTPUT = 512 * 1024 * 1024


def _archive_order(path: Path):
    match = _UPDATE.fullmatch(path.name)
    if match:
        return 1, int(match.group(1)), path.name.casefold()
    return 0, 0, path.name.casefold()


def _next_destination(root: Path) -> Path:
    destination = root / f"{root.name}_extract"
    suffix = 2
    while os.path.lexists(destination):
        destination = root / f"{root.name}_extract_{suffix}"
        suffix += 1
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
    if any(not path.is_file() for path in paths):
        raise ValueError("CatSystem2 archive path is not a file")
    names = [path.name.casefold() for path in paths]
    if len(names) != len(set(names)):
        raise ValueError("CatSystem2 archive basenames must be unique")
    return paths


def extract_game(game_root, *, output=None, exe=None, password: str | None = None,
                 archive_paths=None, max_members: int = _DEFAULT_MAX_MEMBERS,
                 max_member: int = 64 * 1024 * 1024,
                 max_decoded_member: int = 64 * 1024 * 1024,
                 max_total_cst: int = _DEFAULT_MAX_TOTAL_CST,
                 max_output: int = _DEFAULT_MAX_OUTPUT) -> dict:
    """Extract effective CatSystem2 dialogue without modifying any input file.

    Named members are overlaid in archive order, with numeric ``updateNN.int`` packages
    after base packages. If no password can be recovered, content probing still works,
    but names are ordinal and cross-archive overlays cannot be inferred.
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
    candidates = []
    failures = []
    total_members = 0
    for path in archives:
        report = {"archive": path.name, "size": path.stat().st_size,
                  "encrypted": None, "names_recovered": False,
                  "entries": 0, "cst_members": 0, "status": "blocked"}
        try:
            with path.open("rb") as stream:
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
    source_archives = set()

    ordered = sorted(selected.values(), key=lambda item: (_archive_order(item[0]),
                                                           item[2].name.casefold(),
                                                           item[2].index))
    for path, archive, entry in ordered:
        try:
            raw = read_member(path, entry, archive.cipher, max_member=max_member)
            if len(raw) >= 16 and raw[:8] == b"CatScene":
                declared_output = int.from_bytes(raw[12:16], "little")
                if declared_output > max_decoded_member:
                    raise ValueError("CST member expansion exceeds limit")
                if declared_output > max_total_cst - total_cst:
                    raise ValueError("CatSystem2 decoded CST total exceeds limit")
            scene = read_cst(raw, max_output=max_decoded_member)
            total_cst += len(scene.payload)
            exported = export_cst(scene)
            try:
                if patch_dialogue(raw, exported, list(exported.rows)) != raw:
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
                encoding="cp932",
                name_policies=list(exported.name_policies),
                protected_tokens=[list(tokens) for tokens in exported.protected_tokens],
                settings={
                    "archive_encrypted": archive.encrypted,
                    "names_recovered": archive.names_recovered,
                    "effective_overlay": entry.name_known,
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
                "original": original_name,
                "metadata": metadata_name,
            })
            source_archives.add(path)
            total_rows += len(rows)
            choices_excluded += len(exported.excluded_choices)
            scripts_by_archive[path.name] += 1
            rows_by_archive[path.name] += len(rows)
        except (OSError, UnicodeError, ValueError) as error:
            failures.append({
                "phase": "member",
                "archive": path.name,
                "member": entry.name,
                "member_index": entry.index,
                "error": f"{type(error).__name__}: {error}",
            })

    for report, path in zip(archive_reports, archives):
        report["sha256"] = _sha256_file(path) if path in source_archives else None
    destination = _next_destination(root) if output is None else Path(output)
    if not destination.is_absolute():
        destination = root / destination
    summary = {
        "engine": "catsystem2",
        "game_root": str(root),
        "output": str(destination),
        "password_recovered": resolved_password is not None,
        "password_disclosed": False,
        "archives_scanned": len(archives),
        "members_scanned": total_members,
        "raw_cst_members": len(candidates),
        "effective_cst_members": len(selected),
        "overridden_cst_members": len(overrides),
        "scripts_exported": len(output_records),
        "empty_scripts": len(empty),
        "parse_failures": len(failures),
        "dialogue_rows": total_rows,
        "decoded_cst_bytes": total_cst,
        "choice_commands_excluded": choices_excluded,
        "orphan_name_records": orphan_names,
        "name_command_crossings": name_command_crossings,
        "identity_roundtrip": {
            "status": "complete" if roundtrip_failed == 0 else "partial",
            "passed": roundtrip_passed,
            "failed": roundtrip_failed,
        },
        "scripts_by_archive": dict(scripts_by_archive),
        "rows_by_archive": dict(rows_by_archive),
        "warnings": warnings,
    }
    output_entries.extend([
        ("reports/summary.json",
         (json.dumps(summary, ensure_ascii=False, indent=2) + "\n").encode("utf-8")),
        ("reports/outputs.json",
         (json.dumps({"outputs": output_records, "overrides": overrides,
                      "empty": empty, "failures": failures},
                     ensure_ascii=False, indent=2) + "\n").encode("utf-8")),
        ("reports/archives.json",
         (json.dumps(archive_reports, ensure_ascii=False, indent=2) + "\n").encode("utf-8")),
    ])

    write_new_tree(destination, output_entries,
                   Limits(max_entries=max_members * 3 + 3, max_file_bytes=max_member,
                          max_total_bytes=max_output))
    (destination / "gt_output").mkdir()
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Extract CatSystem2 INT/CST dialogue")
    parser.add_argument("game_root")
    parser.add_argument("--output")
    parser.add_argument("--exe")
    parser.add_argument("--password")
    parser.add_argument("--archive", action="append", dest="archives")
    args = parser.parse_args(argv)
    summary = extract_game(args.game_root, output=args.output, exe=args.exe,
                           password=args.password, archive_paths=args.archives)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
