# SPDX-License-Identifier: GPL-3.0-only
"""NeXAS PAC -> GalTransl JSON -> verified PAC copies. See engines/nexas.md."""
import argparse
from collections import Counter
import io
import json
from pathlib import Path
import stat

from ..archives import nexas as pac
from ..common.binary import FormatError
from ..common.contract import dump_rows, load_json, sha256
from ..common.safety import Limits, logical_path, validate_names, write_new_tree
from . import nexas_bin as script

LIMITS = Limits()
SCHEMA = "nexas-workspace/1"


def _json(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _file(path: Path, limit=LIMITS.max_file_bytes):
    for part in (path, *path.parents):
        info = part.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise FormatError(f"refusing reparse/symlink path: {path}")
    if not path.is_file() or path.stat().st_size > limit:
        raise FormatError(f"not a bounded regular file: {path}")
    return path.read_bytes()


def verify_archive(original: bytes, rebuilt: bytes, replacements: dict[str, bytes]) -> dict:
    a, b = io.BytesIO(original), io.BytesIO(rebuilt)
    ia, ib = pac.read_index(a), pac.read_index(b)
    if (ia.marker, ia.pack_type, [e.name_raw for e in ia.entries]) != (
            ib.marker, ib.pack_type, [e.name_raw for e in ib.entries]):
        raise FormatError("rebuilt PAC identity changed")
    checked = copied = 0
    for old, new in zip(ia.entries, ib.entries):
        if old.name in replacements:
            if pac.read_member(b, ib, new) != replacements[old.name]:
                raise FormatError(f"rebuilt PAC member mismatch: {old.name}")
            checked += 1
        else:
            a.seek(old.offset)
            b.seek(new.offset)
            if (old.unpacked_size != new.unpacked_size or old.packed_size != new.packed_size
                    or a.read(old.packed_size) != b.read(new.packed_size)):
                raise FormatError(f"untouched PAC payload changed: {old.name}")
            copied += 1
    return {"decoded_replacements_verified": checked, "untouched_packed_members_verified": copied,
            "size": len(rebuilt), "sha256": sha256(rebuilt)}


def extract(game: Path, destination: Path, archives: list[str]) -> dict:
    """archives is an explicit low-to-high priority list, not a filename guess."""
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"refusing to replace output: {destination}")
    validate_names(archives)
    if not archives or any(Path(name).name != name for name in archives):
        raise FormatError("provide archive basenames in low-to-high priority order")
    outputs, archive_reports, decoded = [], [], {}
    owners, inventory = {}, []
    total = 0
    for name in archives:
        raw = _file(game / name)
        total += len(raw)
        if total > LIMITS.max_total_bytes:
            raise FormatError("archive inputs exceed total budget")
        stream = io.BytesIO(raw)
        index = pac.read_index(stream)
        bins = [entry for entry in index.entries if entry.name.lower().endswith(".bin")]
        if sum(entry.unpacked_size for entry in bins) + total > LIMITS.max_total_bytes:
            raise FormatError("script outputs exceed total budget")
        rewritten = {}
        for entry in bins:
            data = pac.read_member(stream, index, entry)
            total += len(data)
            rows, manifest = script.export(data, source_name=entry.name)
            result = script.inject(data, rows, manifest, rows, source_name=entry.name)
            if result != data:
                raise FormatError(f"original-text BIN roundtrip differs: {entry.name}")
            rewritten[entry.name] = result
            key = entry.name.casefold()
            owners[key] = (name, entry.name)
            decoded[(name, entry.name)] = (data, rows, manifest)
        rebuilt = pac.rebuild(stream, index, rewritten)
        verification = verify_archive(raw, rebuilt, rewritten)
        archive_reports.append({"name": name, "sha256": sha256(raw), "size": len(raw),
                                "bin_count": len(bins), "member_count": len(index.entries),
                                "marker": index.marker, "pack_type": index.pack_type,
                                "roundtrip": verification})
        outputs.extend([(f"original/archives/{name}", raw), (f"roundtrip/{name}", rebuilt)])
        for entry in index.entries:
            inventory.append({"archive": name, "name": entry.name, "unpacked_size": entry.unpacked_size,
                              "packed_size": entry.packed_size, "offset": entry.offset})
    members = []
    kinds = Counter()
    filenames = []
    for archive, member in owners.values():
        data, rows, manifest = decoded[(archive, member)]
        filename = Path(member).stem + ".json"
        filenames.append(filename)
        record = {"archive": archive, "member": member, "status": "exported" if rows else "empty",
                  "rows": len(rows), "source_sha256": sha256(data)}
        outputs.append((f"original/scripts/{member}", data))
        if rows:
            record["json"] = filename
            outputs.extend([(f"gt_input/{filename}", dump_rows(rows)),
                            (f"metadata/{filename}", _json(manifest))])
            kinds.update(r["locator"]["kind"] for r in manifest["records"])
        members.append(record)
    validate_names(filenames)
    # Keep configuration evidence without interpreting it as deployment approval.
    for name in ["Config.pac", *[n for n in archives if n != "Config.pac"]]:
        path = game / name
        if not path.is_file():
            continue
        with path.open("rb") as stream:
            idx = pac.read_index(stream)
            for entry in idx.entries:
                if entry.name.casefold() == "packlist.dat":
                    outputs.append((f"reports/{Path(name).stem}-packlist.dat", pac.read_member(stream, idx, entry)))
    report = {"schema": SCHEMA, "profile": script.PROFILE,
              "archive_priority": "explicit-low-to-high; runtime-not-tested",
              "archives": archive_reports, "members": members,
              "summary": {"effective_scripts": len(members),
                          "exported_files": sum(m["status"] == "exported" for m in members),
                          "empty_scripts": sum(m["status"] == "empty" for m in members),
                          "rows": sum(kinds.values()), "kinds": dict(kinds),
                          "original_bin_roundtrips": len(decoded)},
              "runtime_verified": False, "encoding": "cp932"}
    outputs.extend([("reports/extraction.json", _json(report)), ("reports/archive-index.json", _json(inventory))])
    write_new_tree(destination, outputs)
    (destination / "gt_output").mkdir()
    return report["summary"]


def pack(workspace: Path, destination: Path, translations: Path | None = None) -> dict:
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"refusing to replace output: {destination}")
    translations = translations or workspace / "gt_output"
    report = load_json(_file(workspace / "reports/extraction.json"))
    if report.get("schema") != SCHEMA or report.get("profile") != script.PROFILE:
        raise FormatError("unsupported NeXAS workspace")
    names = [item["name"] for item in report["archives"]]
    validate_names(names)
    if any(Path(name).name != name for name in names):
        raise FormatError("archive names must be basenames")
    snapshots = {}
    total = 0
    for item in report["archives"]:
        raw = _file(workspace / "original/archives" / item["name"])
        total += len(raw)
        if total > LIMITS.max_total_bytes or sha256(raw) != item["sha256"] or len(raw) != item["size"]:
            raise FormatError("archive source changed or budget exceeded")
        snapshots[item["name"]] = raw
    replacements = {name: {} for name in names}
    used, missing, changed = [], [], 0
    effective = {}
    indexes = {}
    for name, raw in snapshots.items():
        index = pac.read_index(io.BytesIO(raw))
        indexes[name] = index
        for entry in index.entries:
            if entry.name.lower().endswith(".bin"):
                effective[entry.name.casefold()] = (name, entry.name)
    identities = [(m["archive"], m["member"]) for m in report["members"]]
    if set(identities) != set(effective.values()) or len(identities) != len(effective):
        raise FormatError("workspace members do not match archive priority")
    export_names = []
    for member in report["members"]:
        archive, name = member["archive"], member["member"]
        logical_path(name)
        idx = indexes[archive]
        entry = next(e for e in idx.entries if e.name == name)
        data = pac.read_member(io.BytesIO(snapshots[archive]), idx, entry)
        rows, manifest = script.export(data, source_name=name)
        if sha256(data) != member["source_sha256"]:
            raise FormatError("member source changed")
        if not rows:
            if member["status"] != "empty":
                raise FormatError("workspace empty member status changed")
            continue
        filename = logical_path(member["json"])
        if Path(filename).name != filename or filename != Path(name).stem + ".json":
            raise FormatError("workspace JSON mapping changed")
        export_names.append(filename)
        source_rows = load_json(_file(workspace / "gt_input" / filename))
        saved_manifest = load_json(_file(workspace / "metadata" / filename))
        if source_rows != rows or saved_manifest != manifest:
            raise FormatError("saved export or manifest changed")
        path = translations / filename
        if not path.exists():
            missing.append(filename)
            continue
        translated = load_json(_file(path))
        rewritten = script.inject(data, rows, manifest, translated, source_name=name)
        replacements[archive][name] = rewritten
        used.append(filename)
        changed += rewritten != data
    validate_names(export_names)
    extras = sorted(p.name for p in translations.glob("*.json") if p.name not in export_names)
    outputs, verification = [], {}
    for name, raw in snapshots.items():
        rebuilt = pac.rebuild(io.BytesIO(raw), indexes[name], replacements[name])
        verification[name] = verify_archive(raw, rebuilt, replacements[name])
        outputs.append((name, rebuilt))
    result = {"schema": "nexas-pack/1", "translated_files": used, "missing_translations": missing,
              "unmatched_json": extras, "changed_scripts": changed, "archives": verification,
              "runtime_verified": False}
    outputs.append(("verification.json", _json(result)))
    write_new_tree(destination, outputs)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    extract_args = commands.add_parser("extract")
    extract_args.add_argument("game", type=Path)
    extract_args.add_argument("--output", required=True, type=Path)
    extract_args.add_argument("--archives", required=True, nargs="+", help="low-to-high priority basenames")
    pack_args = commands.add_parser("pack")
    pack_args.add_argument("workspace", type=Path)
    pack_args.add_argument("--output", required=True, type=Path)
    pack_args.add_argument("--translations", type=Path)
    args = parser.parse_args()
    if args.action == "extract":
        result = extract(args.game, args.output, args.archives)
    else:
        result = pack(args.workspace, args.output, args.translations)
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
