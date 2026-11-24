# SPDX-License-Identifier: GPL-3.0-only
"""Explicit loose-YBN workspace and matching YPF template workflow (YSTB v482/v488)."""
import argparse
import io
import json
from pathlib import Path
import stat
import struct
import sys
from ..archives.yuris_482 import read_index, decode_member, pack_archive
from ..common.contract import load_json, dump_rows, sha256
from ..common.safety import logical_path, validate_names, write_new_tree, _check_existing_ancestors, validate_new_tree_destination
from ..common.handoff import STATE_FILE, handoff, source_language_note
from .yuris_names import LIST_NAME, json_names, read_script_list
from .yuris_text import (PARSE_VERSIONS, WRITE_VERSIONS, Profile, Scenario, commands_from,
                         export_script, rebuild_script, select_key, ystb_version)


def read_file(path, limit=64 << 20):
    path = Path(path)
    _check_existing_ancestors(path.parent)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or getattr(info, "st_file_attributes", 0) & 0x400:
        raise ValueError("input must be an ordinary file")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("input exceeds budget")
    return data


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _legacy_profile_settings(settings):
    """Drop the empty character-table fields of older workspaces.

    Original games never ship a UIF mapping; a non-empty table means earlier
    translation output was mixed into the source, so re-extract from the
    original game instead.
    """
    settings = dict(settings)
    source = settings.pop("source_characters", "")
    target = settings.pop("target_characters", "")
    if source or target:
        raise ValueError("workspace carries a character table from earlier translation output; "
                         "re-extract from the original game files")
    return settings


def archive_members(raw):
    _, entries, _ = read_index(io.BytesIO(raw))
    result, total = {}, 0
    for entry in entries:
        data = decode_member(raw[entry.offset:entry.offset + entry.size], entry, max_output=min(64 << 20, (256 << 20) - total))
        result[entry.name] = data
        total += len(data)
    return result


def baseline_from_archive(raw):
    """Use the template archive's own members as the text baseline."""
    members = archive_members(raw)
    data = {name.replace("\\", "/"): value for name, value in members.items()}
    dictionaries = [name for name in data if name.rsplit("/", 1)[-1].lower() == "ysc.ybn"]
    if len(dictionaries) != 1:
        raise ValueError("template archive needs exactly one ysc.ybn")
    loose = dictionaries[0].rsplit("/", 1)[0] if "/" in dictionaries[0] else ""
    if not loose or dictionaries[0] != f"{loose}/ysc.ybn" or any(
            name.rsplit("/", 1)[0] != loose for name in data):
        raise ValueError("template archive members must share the ysc.ybn directory")
    validate_names([name.rsplit("/", 1)[-1] for name in data])
    return loose, data


def _json_map(report):
    """Scenario member -> JSON name as published at extraction (older workspaces: stem)."""
    return {r["source"]: r.get("json", Path(r["source"]).stem + ".json") for r in report["members"]}


def extract(game, output, *, archive, loose=None, reference_archives=(), smoke_test=False, key=None):
    """``key`` overrides the YSTB section key; otherwise it is chosen by full parses."""
    game, output = Path(game), Path(output)
    validate_new_tree_destination(output)
    archive = logical_path(archive)
    if loose is None:
        # No trusted loose copy (absent or already patched): the template
        # archive itself is the original baseline.
        loose, loose_data = baseline_from_archive(read_file(game / archive, 256 << 20))
        baseline_kind = "template-archive-members"
    else:
        loose = logical_path(loose)
        baseline_kind = "explicit-loose-files"
        _check_existing_ancestors(game / loose)
        paths = sorted((game / loose).glob("*.ybn"))
        if not 0 < len(paths) <= 10000:
            raise ValueError("missing or excessive loose scripts")
        validate_names([p.name for p in paths])
        loose_data, total = {}, 0
        for path in paths:
            data = read_file(path)
            total += len(data)
            if total > 256 << 20:
                raise ValueError("loose input budget exceeded")
            loose_data[f"{loose}/{path.name}"] = data
    ysc = loose_data[f"{loose}/ysc.ybn"]
    commands = commands_from(ysc)
    writable = {name: raw for name, raw in loose_data.items()
                if raw[:4] == b"YSTB" and ystb_version(raw) in WRITE_VERSIONS}
    if writable:
        key, key_evidence = select_key(writable, commands, explicit=key)
    else:
        key_evidence = {"source": "explicit" if key is not None else "profile-default", "parsed": 0, "members": 0}
        key = Profile().key if key is None else key
    profile = Profile(key=key)
    # The compile list maps yst<NNNNN>.ybn back to the script's source path.
    listed = [name for name in loose_data if name.rsplit("/", 1)[-1].lower() == LIST_NAME]
    paths, list_status = None, "absent"
    if len(listed) == 1:
        try:
            paths, list_status = read_script_list(loose_data[listed[0]]), "used"
        except ValueError as exc:
            list_status = f"unused: {exc}"
    elif listed:
        list_status = "unused: several script lists"
    naming = json_names([name for name, raw in loose_data.items() if raw[:4] == b"YSTB"], paths)
    files, records, counts = {"gt_output/.keep": b""}, [], {"rows": 0, "named": 0, "exported": 0,
                                                              "empty": 0, "non_target": 0, "unsupported_version": 0,
                                                              "blocked": 0, "opaque_eval": 0}
    source_hashes = {}
    for name, data in loose_data.items():
        files[f"original/game/{name}"] = data
        source_hashes[name] = sha256(data)
    smoke, texts = None, []
    versions = set()
    for name, raw in loose_data.items():
        if raw[:4] != b"YSTB":
            # Ancillary files remain opaque, not submitted as dialogue.
            counts["non_target"] += 1
            records.append({"source": name, "status": "non_target", "signature_hex": raw[:4].hex()})
            files[f"rebuilt/roundtrip/{name}"] = raw
            continue
        version = ystb_version(raw)
        versions.add(version)
        if version not in WRITE_VERSIONS:
            # Text append is only verified for WRITE_VERSIONS. Reading a wider range
            # must not be reported as translatable: keep the member byte-identical
            # and state the reason instead of silently emitting JSON.
            counts["unsupported_version"] += 1
            records.append({"source": name, "status": "unsupported_version", "version": version,
                            "writer_versions": list(WRITE_VERSIONS)})
            files[f"rebuilt/roundtrip/{name}"] = raw
            continue
        stats = {}
        try:
            rows, manifest = export_script(raw, ysc, profile, stats)
            restored = rebuild_script(raw, ysc, rows, manifest, profile)
            if restored != raw:
                raise ValueError("original script roundtrip differs")
        except (ValueError, UnicodeError, struct.error) as exc:
            # One unsupported member must not hide the others. It publishes no
            # JSON, stays byte-identical in every rebuilt archive and is listed.
            counts["blocked"] += 1
            records.append({"source": name, "status": "blocked", "reason": str(exc)})
            files[f"rebuilt/roundtrip/{name}"] = raw
            continue
        files[f"rebuilt/roundtrip/{name}"] = restored
        filename = naming[name]["json"]
        record = {"source": name, "status": "exported" if rows else "empty", "count": len(rows),
                  "opaque_eval": stats["opaque_eval"], "naming": naming[name]["naming"],
                  "dialogue": sum(r["locator"]["role"] == "dialogue" for r in manifest["records"])}
        if naming[name]["original_path"]:
            record["original_path"] = naming[name]["original_path"]
        counts["opaque_eval"] += stats["opaque_eval"]
        counts[record["status"]] += 1
        counts["rows"] += len(rows)
        counts["named"] += sum("name" in r for r in rows)
        if rows:
            texts.extend(row["message"] for row in rows)
            files[f"gt_input/{filename}"] = dump_rows(rows)
            files[f"metadata/{filename}"] = json_bytes(manifest)
            record["json"] = filename
            if smoke_test and smoke is None:
                candidate = next((i for i, r in enumerate(manifest["records"]) if r["locator"]["role"] == "dialogue"), None)
                if candidate is not None:
                    changed = [dict(row) for row in rows]
                    changed[candidate]["message"] += " (YU-RIS test ABC)"
                    modified = rebuild_script(raw, ysc, changed, manifest, profile)
                    smoke = (name, modified)
                    files[f"reports/smoke-translation/{filename}"] = dump_rows(changed)
                    files[f"rebuilt/smoke-test/{name}"] = modified
                    record["smoke_size_delta"] = len(modified) - len(raw)
        records.append(record)
    archive_reports, baseline = [], None
    archive_paths = list(dict.fromkeys([archive, *[logical_path(p) for p in reference_archives]]))
    for relative in archive_paths:
        with (game / relative).open("rb") as stream:
            read_index(stream)  # index/name-hash validation precedes full read
        raw = read_file(game / relative, 256 << 20)
        files[f"original/game/{relative}"] = raw
        source_hashes[relative] = sha256(raw)
        members = archive_members(raw)
        rebuilt_members = {}
        dictionary = members.get(f"{loose}\\ysc.ybn", members.get(f"{loose}/ysc.ybn"))
        if dictionary != ysc:
            raise ValueError("archive and loose command dictionaries differ")
        differences, unparsed = [], []
        for member, data in members.items():
            if data[:4] == b"YSTB":
                if ystb_version(data) not in WRITE_VERSIONS:
                    rebuilt_members[member] = data
                    continue
                try:
                    scenario = Scenario(data, commands, profile.key)
                except (ValueError, struct.error):
                    # Kept opaque; the container round trip below still applies.
                    unparsed.append(member.replace("\\", "/"))
                    rebuilt_members[member] = data
                    continue
                rebuilt_members[member] = scenario.serialize({})
                if rebuilt_members[member] != data:
                    raise ValueError("archive scenario structural roundtrip differs")
            normalized = member.replace("\\", "/")
            if normalized in loose_data and loose_data[normalized] != data:
                differences.append(normalized)
        rebuilt = pack_archive(raw, rebuilt_members)
        if rebuilt != raw:
            raise ValueError("archive roundtrip differs")
        files[f"rebuilt/roundtrip/{relative}"] = rebuilt
        archive_reports.append({"source": relative, "members": len(members), "different_from_loose": differences,
                                "scenario_structure_unparsed": unparsed,
                                "roundtrip_identical": True, "name_and_stored_murmur2_verified": True})
        if relative == archive:
            baseline = raw
            canonical = {name.replace("\\", "/"): name for name in members}
            if set(loose_data) != set(canonical):
                raise ValueError("loose and archive member sets differ; explicit resolution needed")
    # Explicitly construct a complete archive of the selected loose baseline.
    replacements = {canonical[name]: data for name, data in loose_data.items()}
    current = pack_archive(baseline, replacements)
    if archive_members(current) != replacements:
        raise ValueError("current-state archive extraction mismatch")
    # Rebuilt archives keep the template's game-relative path and file name.
    files[f"rebuilt/current/{archive}"] = current
    if smoke_test:
        if smoke is None:
            raise ValueError("no dialogue for smoke test")
        name, modified = smoke
        changed = dict(replacements)
        changed[canonical[name]] = modified
        test = pack_archive(baseline, changed)
        if archive_members(test) != changed:
            raise ValueError("smoke archive extraction mismatch")
        files[f"rebuilt/smoke-test/{archive}"] = test
    report = {"engine": "yuris", "status": "partial" if counts["blocked"] else "complete",
              "version": next(iter(versions)) if len(versions) == 1 else None,
              "versions": sorted(versions), "writer_versions": list(WRITE_VERSIONS),
              "key_selection": {**key_evidence, "key": f"0x{key:08X}"},
              "script_list": list_status,
              "parse_versions": [PARSE_VERSIONS.start, PARSE_VERSIONS.stop - 1],
              "profile": profile.settings(), "archive": archive,
              # Directory of the baseline scripts (explicit --loose or the template's own).
              "loose": loose, "loose_option_given": baseline_kind == "explicit-loose-files",
              "source_hashes": source_hashes,
              "counts": counts, "members": records,
              "blocked": [{"source": r["source"], "reason": r["reason"]} for r in records if r["status"] == "blocked"],
              "archives": archive_reports,
              "selected_baseline": baseline_kind, "load_precedence_verified": False,
              "current_archive_matches_loose": True, "smoke_reextraction_verified": smoke is not None,
              "runtime_verified": False}
    notes = ["\\p、\\c、\\u 等控制码的数量与顺序保持不变；换行可以比原文少，不能新增或跨控制码移动",
             "姓名不要加【】，回填时自动恢复；同一角色的姓名定义行与对白姓名保持一致",
             "只能写入 CP932 可表示的字符，简体中文需走 JIS 替换流程"]
    warning = source_language_note(texts)
    if warning:
        notes.insert(0, warning)
        report["warnings"] = [warning]
    if counts["blocked"] or counts["unsupported_version"]:
        notes.append(f"{counts['blocked'] + counts['unsupported_version']} 个场景未导出（受阻或版本不可写），"
                     "见 reports/extraction.json")
    exported = [r for r in records if r["status"] == "exported"]
    # Name-definition tables come first in compile order; prefer a scene with dialogue.
    scenes = [r for r in exported if r["dialogue"]] or exported
    first = min(scenes, key=lambda r: r["source"])["json"] if scenes else None
    report["delivery"], state = handoff(
        workspace=output, engine=f"YU-RIS（YSTB v{'/'.join(map(str, sorted(versions)))}）",
        json_files=len(exported), rows=counts["rows"], notes=notes,
        verified="各场景经 writer 重建后与原字节一致，YPF 重封后逐成员一致", edit_checked=smoke is not None,
        first_json=first, first_json_basis=("编译序号最小的含对白场景，未确认是否开场" if first else ""),
        command="extract --verify-edits" if smoke_test else "extract")
    files["reports/extraction.json"] = json_bytes(report)
    files[STATE_FILE] = state
    write_new_tree(output, list(files.items()))
    return report


def rebuild(workspace, output):
    workspace = Path(workspace)
    report = load_json(read_file(workspace / "reports/extraction.json"))
    sources = {}
    for relative, digest in report["source_hashes"].items():
        relative = logical_path(relative)
        data = read_file(workspace / "original/game" / relative, 256 << 20)
        if sha256(data) != digest:
            raise ValueError("original source hash changed")
        sources[relative] = data
    profile = Profile(**_legacy_profile_settings(report["profile"]))
    loose = logical_path(report["loose"])
    ysc = sources[f"{loose}/ysc.ybn"]
    baseline = sources[logical_path(report["archive"])]
    replacements = archive_members(baseline)
    canonical = {name.replace("\\", "/"): name for name in replacements}
    # Members blocked or version-gated at extraction published no JSON; they
    # are copied byte-identically and any translation for them is unmatched.
    opaque = {r["source"] for r in report["members"] if r["status"] in ("blocked", "unsupported_version")}
    expected_json, changed, files = set(), [], []
    published = _json_map(report)
    for source, member in canonical.items():
        raw = sources[source]
        if raw[:4] == b"YSTB" and source not in opaque:
            rows, manifest = export_script(raw, ysc, profile)
            if rows:
                filename = published[source]
                expected_json.add(filename)
                if load_json(read_file(workspace / "gt_input" / filename)) != rows or load_json(read_file(workspace / "metadata" / filename)) != manifest:
                    raise ValueError("original JSON/manifest changed")
                translated = workspace / "gt_output" / filename
                if translated.exists():
                    raw = rebuild_script(raw, ysc, load_json(read_file(translated)), manifest, profile)
                    changed.append(source)
        replacements[member] = raw
        files.append((source, raw))
    _check_existing_ancestors(workspace / "gt_output")
    if {p.name for p in (workspace / "gt_output").glob("*.json")} - expected_json:
        raise ValueError("unmatched translation filenames")
    packed = pack_archive(baseline, replacements)
    if archive_members(packed) != replacements:
        raise ValueError("rebuilt archive differs from intended members")
    archive = logical_path(report["archive"])
    files.append((archive, packed))
    result = {"translated_members": changed, "members": len(replacements), "archive": archive,
              "copied_unsupported_members": sorted(opaque), "runtime_verified": False}
    files.append(("reports/rebuild.json", json_bytes(result)))
    write_new_tree(Path(output), files)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("extract")
    p.add_argument("game")
    p.add_argument("output")
    p.add_argument("--archive", required=True)
    p.add_argument("--loose", help="original loose YBN directory; omit to use --archive members")
    p.add_argument("--reference-archive", action="append", default=[])
    p.add_argument("--verify-edits", "--smoke-test", dest="smoke_test", action="store_true",
                   help="also write one edited row through the writer and re-extract the changed archive")
    p.add_argument("--key", type=lambda value: int(value, 0),
                   help="YSTB section key (e.g. 0x12345678); default: chosen by full parses of all scenarios")
    p = commands.add_parser("rebuild")
    p.add_argument("workspace")
    p.add_argument("output")
    args = parser.parse_args()
    try:
        if args.command == "extract":
            report = extract(args.game, args.output, archive=args.archive, loose=args.loose,
                             reference_archives=args.reference_archive, smoke_test=args.smoke_test, key=args.key)
            for warning in report.get("warnings", []):
                print(f"warning: {warning}", file=sys.stderr)
            print(json.dumps({"status": report["status"], "counts": report["counts"],
                              "key_selection": report["key_selection"], "blocked": report["blocked"],
                              "delivery": report["delivery"]}, ensure_ascii=False))
            raise SystemExit(report["status"] != "complete")
        print(json.dumps(rebuild(args.workspace, args.output), ensure_ascii=False))
    except (ValueError, UnicodeError, OSError, struct.error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
