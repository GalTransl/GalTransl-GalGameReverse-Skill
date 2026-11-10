# SPDX-License-Identifier: GPL-3.0-only
"""SCPACK extraction/rebuild CLI. Writes a new tree; never installs a patch."""
import argparse
from dataclasses import asdict
import json
import stat
import sys
from pathlib import Path

from ..archives.eagls import DEFAULT_INDEX_KEY, pack_archive, read_index
from ..common.contract import dump_rows, load_json, sha256
from ..common.safety import Limits, validate_names, write_new_tree, _check_existing_ancestors, validate_new_tree_destination
from .eagls_text import Profile, export_script, parse_script, rebuild_script


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def read_bounded(path, limit=128 * 1024 * 1024):
    path = Path(path)
    _check_existing_ancestors(path.parent)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or getattr(info, "st_file_attributes", 0) & 0x400:
        raise ValueError("input is not an ordinary, unlinked file")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"input exceeds budget: {path}")
    return data


def load_profile(config=None, **kwargs):
    if config is not None:
        obj = load_json(config)
        if obj.get("tunnel_decoder", {}).get("enable"):
            raise ValueError("UIF tunnel decoding is not supported")
        mapping = obj.get("character_substitution", {})
        if mapping.get("enable"):
            kwargs.update(source_characters=mapping["source_characters"],
                          target_characters=mapping["target_characters"])
    return Profile(**kwargs)


def extract(source, output, *, profile=Profile(), key=DEFAULT_INDEX_KEY,
            long_offsets=True, config=None, smoke_test=False):
    source, output = Path(source), Path(output)
    validate_new_tree_destination(output)
    index = read_bounded(source / "SCPACK.idx")
    # Validate the bounded index against PAK size before reading PAK.
    _, entries = read_index(index, (source / "SCPACK.pak").stat().st_size,
                            key=key, long_offsets=long_offsets)
    pak = read_bounded(source / "SCPACK.pak", Limits().max_total_bytes)
    files = {"original/SCPACK.idx": index, "original/SCPACK.pak": pak,
             "gt_output/.keep": b""}
    if config is not None:
        files["original/uif_config.json"] = config
    names = [Path(e.name).stem + ".json" for e in entries]
    validate_names(names)
    replacements, records, total = {}, [], 0
    smoke = None
    for entry, filename in zip(entries, names):
        raw = pak[entry.offset:entry.offset + entry.size]
        try:
            rows, manifest = export_script(raw, profile)
            rebuilt = rebuild_script(raw, rows, manifest, profile)
            if rebuilt != raw:
                raise ValueError("no-edit roundtrip differs")
        except (ValueError, UnicodeError) as exc:
            # One unsupported member must not hide the others. It publishes no
            # JSON and is not passed to the writer, so every rebuilt archive
            # carries its original encrypted bytes. Label errors already name
            # the label and its stored offset.
            records.append({**asdict(entry), "sha256": sha256(raw), "status": "blocked",
                            "reason": f"pak offset {entry.offset}, size {entry.size}: {exc}", "outputs": {}})
            continue
        replacements[entry.name] = rebuilt
        plain, _, _ = parse_script(raw, profile)
        files[f"original/scripts/{entry.name}"] = plain
        records.append({**asdict(entry), "sha256": sha256(raw), "count": len(rows),
                        "status": "exported" if rows else "empty",
                        "outputs": {"json": filename} if rows else {}})
        if rows:
            files[f"gt_input/{filename}"] = dump_rows(rows)
            files[f"metadata/{filename}"] = json_bytes(manifest)
            total += len(rows)
            if smoke_test and smoke is None and entry.name.lower().startswith("sc"):
                changed = [dict(r) for r in rows]
                changed[0]["message"] += " (EAGLS roundtrip ABC)"
                modified = rebuild_script(raw, changed, manifest, profile)
                smoke = (entry.name, modified, filename, changed)
    # Every parsed member went through parser/writer above; blocked members are
    # absent from replacements and copied byte-for-byte by the archive writer.
    new_idx, new_pak = pack_archive(index, pak, replacements, key=key, long_offsets=long_offsets)
    if new_idx != index or new_pak != pak:
        raise ValueError("whole archive no-edit roundtrip differs")
    files["rebuilt/roundtrip/script/SCPACK.idx"] = new_idx
    files["rebuilt/roundtrip/script/SCPACK.pak"] = new_pak
    blocked = [{"name": r["name"], "reason": r["reason"]} for r in records if r["status"] == "blocked"]
    report = {"engine": "eagls", "status": "partial" if blocked else "complete",
              "profile": profile.settings(), "index_key_hex": key.hex(),
              "long_offsets": long_offsets, "members": records, "rows": total, "blocked": blocked,
              "source_hashes": {"SCPACK.idx": sha256(index), "SCPACK.pak": sha256(pak)},
              "no_edit_members_identical": len(replacements), "blocked_members_copied_verbatim": len(blocked),
              "no_edit_archives_identical": True, "runtime_verified": False}
    if config is not None:
        report["source_hashes"]["uif_config.json"] = sha256(config)
    if smoke_test:
        if smoke is None:
            raise ValueError("no scenario member available for smoke test")
        name, changed, filename, rows = smoke
        a, b = pack_archive(index, pak, {name: changed}, key=key, long_offsets=long_offsets)
        _, rebuilt_entries = read_index(a, len(b), key=key, long_offsets=long_offsets)
        for original_entry, rebuilt_entry in zip(entries, rebuilt_entries):
            actual = b[rebuilt_entry.offset:rebuilt_entry.offset + rebuilt_entry.size]
            expected = changed if original_entry.name == name else pak[original_entry.offset:original_entry.offset + original_entry.size]
            if actual != expected:
                raise ValueError("changed archive re-extraction differs")
        files["rebuilt/smoke-test/script/SCPACK.idx"] = a
        files["rebuilt/smoke-test/script/SCPACK.pak"] = b
        files[f"reports/smoke-translation/{filename}"] = dump_rows(rows)
        report["smoke_test"] = {"member": name, "size_delta": len(changed) - next(e.size for e in entries if e.name == name),
                                "all_members_reextracted": True, "runtime_verified": False}
    files["reports/extraction.json"] = json_bytes(report)
    write_new_tree(output, list(files.items()))
    return report


def rebuild(workspace, output):
    workspace = Path(workspace)
    report = load_json(read_bounded(workspace / "reports/extraction.json"))
    for name, expected in report["source_hashes"].items():
        if name not in {"SCPACK.idx", "SCPACK.pak", "uif_config.json"}:
            raise ValueError("unexpected source filename")
        if sha256(read_bounded(workspace / "original" / name, Limits().max_total_bytes)) != expected:
            raise ValueError("source hash changed")
    settings = dict(report["profile"])
    settings["key"] = bytes.fromhex(settings.pop("key_hex"))
    settings["encoding"] = settings.pop("storage_encoding")
    profile = Profile(**settings)
    index = read_bounded(workspace / "original/SCPACK.idx")
    pak = read_bounded(workspace / "original/SCPACK.pak", Limits().max_total_bytes)
    key, long_offsets = bytes.fromhex(report["index_key_hex"]), report["long_offsets"]
    _, entries = read_index(index, len(pak), key=key, long_offsets=long_offsets)
    filenames = [Path(e.name).stem + ".json" for e in entries]
    validate_names(filenames)
    _check_existing_ancestors(workspace / "gt_output")
    available = {p.name for p in (workspace / "gt_output").iterdir() if p.suffix.lower() == ".json"}
    if available - set(filenames):
        raise ValueError("unmatched translation filenames")
    # Blocked at extraction: no JSON was published, so a translation for one
    # is refused and the member stays byte-identical in the rebuilt archive.
    blocked = {r["name"]: r["reason"] for r in report["members"] if r.get("status") == "blocked"}
    refused = sorted(f"{f} ({name}: {blocked[name]})" for name, f in
                     ((e.name, f) for e, f in zip(entries, filenames)) if name in blocked and f in available)
    if refused:
        raise ValueError("translation supplied for blocked member(s): " + "; ".join(refused))
    replacements, changed = {}, []
    for entry, filename in zip(entries, filenames):
        if entry.name in blocked:
            continue
        raw = pak[entry.offset:entry.offset + entry.size]
        rows, expected_manifest = export_script(raw, profile)
        if not rows:
            if filename in available:
                raise ValueError("translation supplied for empty member")
            continue
        manifest = load_json(read_bounded(workspace / "metadata" / filename))
        original = load_json(read_bounded(workspace / "gt_input" / filename))
        if original != rows or manifest != expected_manifest:
            raise ValueError("original JSON or manifest changed")
        if filename in available:
            translated = load_json(read_bounded(workspace / "gt_output" / filename))
            try:
                replacements[entry.name] = rebuild_script(raw, translated, manifest, profile)
            except (ValueError, UnicodeError) as exc:
                raise ValueError(f"member {entry.name} ({filename}): {exc}") from exc
            changed.append(entry.name)
    new_idx, new_pak = pack_archive(index, pak, replacements, key=key, long_offsets=long_offsets)
    result = {"translated_members": changed, "copied_members": len(entries) - len(changed),
              "copied_blocked_members": sorted(blocked),
              "runtime_verified": False, "sha256": {"SCPACK.idx": sha256(new_idx), "SCPACK.pak": sha256(new_pak)}}
    write_new_tree(Path(output), [("script/SCPACK.idx", new_idx), ("script/SCPACK.pak", new_pak),
                                 ("reports/rebuild.json", json_bytes(result))])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("extract")
    export.add_argument("source", help="directory containing SCPACK.idx and SCPACK.pak")
    export.add_argument("output", help="new output directory")
    export.add_argument("--uif-config")
    export.add_argument("--short-offsets", action="store_true")
    export.add_argument("--text-offset", type=int, default=3600)
    export.add_argument("--version", type=int, choices=(1, 2), default=2)
    export.add_argument("--label-size", type=int, choices=(36, 136), default=36)
    export.add_argument("--encoding", default="cp932")
    export.add_argument("--index-key", default=DEFAULT_INDEX_KEY.decode("ascii"))
    export.add_argument("--script-key", default="EAGLS_SYSTEM")
    export.add_argument("--smoke-test", action="store_true")
    pack = commands.add_parser("rebuild")
    pack.add_argument("workspace")
    pack.add_argument("output", help="new output directory")
    args = parser.parse_args()
    try:
        if args.command == "extract":
            config = read_bounded(args.uif_config) if args.uif_config else None
            profile = load_profile(config, text_offset=args.text_offset, version=args.version,
                                   label_size=args.label_size, encoding=args.encoding,
                                   key=args.script_key.encode("ascii"))
            result = extract(args.source, args.output, profile=profile, key=args.index_key.encode("ascii"),
                             long_offsets=not args.short_offsets, config=config, smoke_test=args.smoke_test)
            print(json.dumps({"status": result["status"], "members": len(result["members"]), "rows": result["rows"],
                              "blocked": result["blocked"], "gt_input": str(Path(args.output) / "gt_input")},
                             ensure_ascii=True))
            # Same convention as the YU-RIS workflow: partial output exits 1.
            raise SystemExit(result["status"] != "complete")
        print(json.dumps(rebuild(args.workspace, args.output), ensure_ascii=True))
    except (ValueError, UnicodeError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
