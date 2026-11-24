# SPDX-License-Identifier: GPL-3.0-only
"""NeXAS PAC -> GalTransl JSON -> verified PAC copies. See engines/nexas.md."""
import argparse
from collections import Counter
import io
import json
from pathlib import Path
import re
import stat
import struct
import sys

from ..archives import nexas as pac
from ..common.binary import FormatError
from ..common.contract import dump_rows, load_json, sha256
from ..common.handoff import STATE_FILE, handoff, source_language_note
from ..common.safety import Limits, logical_path, validate_names, write_new_tree, validate_new_tree_destination
from . import nexas_bin as script

LIMITS = Limits()
SCHEMA = "nexas-workspace/1"
PACKLIST = "packlist.dat"
PACK_NAME = re.compile(rb"[A-Za-z0-9_]{1,64}")


def _json(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _check_path(path: Path):
    for part in (path, *path.parents):
        info = part.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise FormatError(f"refusing reparse/symlink path: {path}")
    if not path.is_file():
        raise FormatError(f"not a regular file: {path}")


def _file(path: Path, limit=LIMITS.max_file_bytes):
    _check_path(path)
    if path.stat().st_size > limit:
        raise FormatError(f"not a bounded regular file: {path}")
    return path.read_bytes()


def parse_packlist(raw: bytes) -> list[str]:
    """Pack base names of packlist.dat, in file order.

    Layout: 12-byte header (three u32, kept opaque), then repeated
    NUL-terminated ASCII name + u32 group until the exact end of the file.
    Patch packs are listed before the base packs they override (UpdateN ...
    Update, then Config/System/Script ...), so file order is high-to-low
    priority. Anything else is refused instead of guessed.
    """
    if len(raw) < 12 or len(raw) > 1 << 16:
        raise FormatError("packlist.dat size outside the known layout")
    pos, names = 12, []
    while pos < len(raw):
        end = raw.find(b"\0", pos, pos + 65)
        if end < 0 or not PACK_NAME.fullmatch(raw[pos:end]) or end + 5 > len(raw):
            raise FormatError(f"packlist.dat entry at byte {pos} does not match the known layout")
        names.append(raw[pos:end].decode("ascii"))
        pos = end + 5
    if not names or len({n.casefold() for n in names}) != len(names):
        raise FormatError("packlist.dat has no entries or repeats a pack name")
    return names


def _disk_names(game: Path) -> dict[str, str]:
    return {p.name.casefold(): p.name for p in game.iterdir() if p.is_file()}


def _packlist_of(path: Path) -> bytes | None:
    _check_path(path)
    with path.open("rb") as stream:
        index = pac.read_index(stream)
        for entry in index.entries:
            if entry.name.casefold() == PACKLIST:
                return pac.read_member(stream, index, entry)
    return None


def default_archives(game: Path) -> tuple[list[str], dict]:
    """Low-to-high priority PACs holding .bin scripts, derived from packlist.dat.

    Only packs that packlist.dat names and that exist on disk are used; absent
    packs are reported, never assumed. All packlist copies must agree.
    """
    disk = _disk_names(game)
    config = disk.get("config.pac")
    if config is None:
        raise FormatError("Config.pac not found; pass --archives explicitly (low-to-high priority)")
    raw = _packlist_of(game / config)
    if raw is None:
        raise FormatError("Config.pac has no packlist.dat; pass --archives explicitly")
    names = parse_packlist(raw)
    present, absent, chosen = [], [], []
    for name in names:
        actual = disk.get(f"{name}.pac".casefold())
        (present if actual else absent).append(actual or f"{name}.pac")
    for actual in present:
        copy = _packlist_of(game / actual)
        if copy is not None and copy != raw:
            raise FormatError(f"{actual} carries a packlist.dat that differs from Config.pac; "
                              "pass --archives explicitly")
    for actual in reversed(present):
        with (game / actual).open("rb") as stream:
            if any(e.name.lower().endswith(".bin") for e in pac.read_index(stream).entries):
                chosen.append(actual)
    if not chosen:
        raise FormatError("no pack named by packlist.dat holds .bin scripts; pass --archives explicitly")
    return chosen, {"source": "Config.pac/packlist.dat", "listed_high_to_low": names,
                    "absent_on_disk": absent, "selected_low_to_high": chosen}


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


def edit_rows(rows: list[dict]) -> list[dict]:
    """Deterministic variable-length test edit that keeps every control token."""
    edited = []
    for i, row in enumerate(rows):
        row = dict(row, message=row["message"] + "試" * (1 + i % 3))
        if "name" in row:
            row["name"] += "名"
        edited.append(row)
    return edited


def _notes(dialect: script.Dialect) -> list[str]:
    notes = ["@n 是换行，可删减但不得新增或移到其他控制码之前",
             "其余 @ 控制码须原样保留、顺序不变、不得增删：@v 语音号、@t 四位延时、"
             "@h 资源名（可为空，紧随的正文不能并入）、@k、@d、@m 两位参数"]
    if dialect.ruby:
        notes.append("@s 四位参数原样保留；注音写作 @r底字@读音@，可翻译底字和读音，但须保留 @r 与两个 @ 分隔")
    else:
        notes.append("@i 两位参数原样保留")
    notes.append("special-text 与 custom-message 可能引用同一句原文，未去重，译文须保持一致")
    return notes


def extract(game: Path, destination: Path, archives: list[str] | None = None, *,
            verify_edits: bool = False) -> dict:
    """archives is an explicit low-to-high priority list; None derives it from packlist.dat."""
    validate_new_tree_destination(destination)
    selection = None
    if archives is None:
        archives, selection = default_archives(game)
    validate_names(archives)
    if not archives or any(Path(name).name != name for name in archives):
        raise FormatError("provide archive basenames in low-to-high priority order")
    loaded, total = [], 0
    for name in archives:
        raw = _file(game / name)
        total += len(raw)
        if total > LIMITS.max_total_bytes:
            raise FormatError("archive inputs exceed total budget")
        stream = io.BytesIO(raw)
        try:
            index = pac.read_index(stream)
        except FormatError as exc:
            raise FormatError(f"{name}: {exc}") from None
        bins = [entry for entry in index.entries if entry.name.lower().endswith(".bin")]
        if sum(entry.unpacked_size for entry in bins) + total > LIMITS.max_total_bytes:
            raise FormatError("script outputs exceed total budget")
        members = {}
        for entry in bins:
            try:
                data = pac.read_member(stream, index, entry)
            except FormatError as exc:
                raise FormatError(f"{name}:{entry.name}: {exc}") from None
            total += len(data)
            try:
                members[entry.name] = (data, script.parse(data), None)
            except FormatError as exc:
                members[entry.name] = (data, None, f"BIN layout: {exc}")
        loaded.append((name, raw, stream, index, members))
    # One FUNC table per workspace, chosen from message call-site evidence.
    dialect = script.select_dialect(parsed for *_, members in loaded
                                    for _, parsed, _ in members.values() if parsed is not None)
    evidence = {profile: sum(script.message_sites(parsed, d) for *_, members in loaded
                             for _, parsed, _ in members.values() if parsed is not None)
                for profile, d in script.DIALECTS.items()}
    outputs, archive_reports, decoded = [], [], {}
    owners, inventory = {}, []
    for name, raw, stream, index, members in loaded:
        rewritten, blocked = {}, []
        for member, (data, parsed, reason) in members.items():
            rows = manifest = None
            if reason is None:
                try:
                    rows, manifest = script.export(data, source_name=member, dialect=dialect)
                    result = script.inject(data, rows, manifest, rows, source_name=member)
                    if result != data:
                        raise FormatError("original-text BIN roundtrip differs")
                    rewritten[member] = result
                except (FormatError, UnicodeError) as exc:
                    reason = str(exc)
            if reason is not None:
                # Publishes no JSON; the PAC writer copies its packed bytes verbatim.
                blocked.append({"member": member, "reason": reason})
            owners[member.casefold()] = (name, member)
            decoded[(name, member)] = (data, rows, manifest, reason)
        rebuilt = pac.rebuild(stream, index, rewritten)
        verification = verify_archive(raw, rebuilt, rewritten)
        archive_reports.append({"name": name, "sha256": sha256(raw), "size": len(raw),
                                "bin_count": len(members), "member_count": len(index.entries),
                                "marker": index.marker, "pack_type": index.pack_type,
                                "blocked": blocked, "roundtrip": verification})
        outputs.extend([(f"original/archives/{name}", raw), (f"roundtrip/{name}", rebuilt)])
        for entry in index.entries:
            inventory.append({"archive": name, "name": entry.name, "unpacked_size": entry.unpacked_size,
                              "packed_size": entry.packed_size, "offset": entry.offset})
    members, kinds, filenames, texts = [], Counter(), [], []
    first_json = None
    for archive, member in owners.values():
        data, rows, manifest, reason = decoded[(archive, member)]
        filename = Path(member).stem + ".json"
        filenames.append(filename)
        outputs.append((f"original/scripts/{member}", data))
        if reason is not None:
            members.append({"archive": archive, "member": member, "status": "blocked", "rows": 0,
                            "reason": f"{archive}:{member}: {reason}", "source_sha256": sha256(data)})
            continue
        record = {"archive": archive, "member": member, "status": "exported" if rows else "empty",
                  "rows": len(rows), "source_sha256": sha256(data)}
        if rows:
            record["json"] = filename
            first_json = first_json or filename
            outputs.extend([(f"gt_input/{filename}", dump_rows(rows)),
                            (f"metadata/{filename}", _json(manifest))])
            kinds.update(r["locator"]["kind"] for r in manifest["records"])
            texts.extend(row["message"] for row in rows)
        members.append(record)
    validate_names(filenames)
    blocked = [{"member": m["member"], "reason": m["reason"]} for m in members if m["status"] == "blocked"]
    if not any(m["status"] == "exported" for m in members):
        detail = "; ".join(b["reason"] for b in blocked[:3])
        raise FormatError(f"no NeXAS script could be exported{': ' + detail if detail else ''}")
    edit_check = _verify_edits(loaded, decoded, owners) if verify_edits else None
    # Keep configuration evidence without interpreting it as deployment approval.
    for name in ["Config.pac", *[n for n in archives if n != "Config.pac"]]:
        path = game / name
        if not path.is_file():
            continue
        with path.open("rb") as stream:
            idx = pac.read_index(stream)
            for entry in idx.entries:
                if entry.name.casefold() == PACKLIST:
                    outputs.append((f"reports/{Path(name).stem}-packlist.dat", pac.read_member(stream, idx, entry)))
    summary = {"effective_scripts": len(members),
               "exported_files": sum(m["status"] == "exported" for m in members),
               "empty_scripts": sum(m["status"] == "empty" for m in members),
               "blocked_scripts": len(blocked),
               "rows": sum(kinds.values()), "kinds": dict(kinds),
               "original_bin_roundtrips": sum(1 for v in decoded.values() if v[3] is None)}
    report = {"schema": SCHEMA, "profile": dialect.profile, "status": "partial" if blocked else "complete",
              "dialect_evidence": {"message_call_sites": evidence},
              "archive_priority": ("packlist-default-low-to-high" if selection else "explicit-low-to-high")
              + "; runtime-not-tested",
              "archives": archive_reports, "members": members, "blocked": blocked, "summary": summary,
              "runtime_verified": False, "encoding": "cp932"}
    if selection:
        report["archive_selection"] = selection
    if edit_check:
        report["edit_check"] = edit_check
    notes = _notes(dialect)
    warning = source_language_note(texts)
    if warning:
        notes.insert(0, warning)
        report["warnings"] = [warning]
    if blocked:
        notes.append(f"{len(blocked)} 个脚本解析受阻未导出（原样保留在重封包中），见 reports/extraction.json 的 blocked")
    report["delivery"], state = handoff(
        workspace=destination, engine=f"NeXAS（PAC + BIN 字符串池，方言 {dialect.profile}）",
        json_files=summary["exported_files"], rows=summary["rows"], notes=notes,
        verified="各脚本 BIN 经 writer 原文回写逐字节一致，每个 PAC 重建后逐成员核对",
        edit_checked=bool(edit_check), first_json=first_json,
        first_json_basis="覆盖顺序中第一个有文本的脚本，未确认是否开场",
        command="extract --verify-edits" if verify_edits else "extract")
    outputs.extend([("reports/extraction.json", _json(report)), ("reports/archive-index.json", _json(inventory)),
                    (STATE_FILE, state)])
    write_new_tree(destination, outputs)
    (destination / "gt_output").mkdir()
    return report


def _verify_edits(loaded, decoded, owners) -> dict:
    """Edit every row of every exported script, rebuild each PAC, re-read and re-parse."""
    effective = set(owners.values())
    rows_edited = members_edited = 0
    for name, raw, stream, index, _ in loaded:
        edited = {}
        expected = {}
        for (archive, member), (data, rows, manifest, reason) in decoded.items():
            if archive != name or reason is not None or not rows or (archive, member) not in effective:
                continue
            changed = edit_rows(rows)
            try:
                edited[member] = script.inject(data, rows, manifest, changed, source_name=member)
            except (FormatError, UnicodeError) as exc:
                raise FormatError(f"edit check {archive}:{member}: {exc}") from None
            expected[member] = (changed, manifest)
            rows_edited += len(rows)
        if not edited:
            continue
        rebuilt = pac.rebuild(stream, index, edited)
        verify_archive(raw, rebuilt, edited)
        new = io.BytesIO(rebuilt)
        new_index = pac.read_index(new)
        dialect = None
        for entry in new_index.entries:
            if entry.name not in expected:
                continue
            changed, manifest = expected[entry.name]
            dialect = dialect or script.dialect_of(manifest)
            reread, _ = script.records(script.parse(pac.read_member(new, new_index, entry)), dialect)
            if reread != changed:
                raise FormatError(f"edit check {name}:{entry.name}: re-extracted rows differ")
            members_edited += 1
    return {"members": members_edited, "rows": rows_edited, "pac_reread": True,
            "nontext_structure_checked": True, "runtime_verified": False}


def pack(workspace: Path, destination: Path, translations: Path | None = None) -> dict:
    validate_new_tree_destination(destination)
    translations = translations or workspace / "gt_output"
    report = load_json(_file(workspace / "reports/extraction.json"))
    if report.get("schema") != SCHEMA or report.get("profile") not in script.DIALECTS:
        raise FormatError("unsupported NeXAS workspace")
    dialect = script.DIALECTS[report["profile"]]
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
    available = {p.name for p in translations.glob("*.json")} if translations.is_dir() else set()
    blocked = {Path(m["member"]).stem + ".json": m for m in report["members"] if m["status"] == "blocked"}
    refused = sorted(f"{f} ({blocked[f]['reason']})" for f in available if f in blocked)
    if refused:
        raise FormatError("translation supplied for blocked script(s): " + "; ".join(refused))
    export_names = []
    for member in report["members"]:
        archive, name = member["archive"], member["member"]
        logical_path(name)
        idx = indexes[archive]
        entry = next(e for e in idx.entries if e.name == name)
        data = pac.read_member(io.BytesIO(snapshots[archive]), idx, entry)
        if sha256(data) != member["source_sha256"]:
            raise FormatError("member source changed")
        if member["status"] == "blocked":
            continue
        try:
            rows, manifest = script.export(data, source_name=name, dialect=dialect)
        except FormatError as exc:
            raise FormatError(f"{archive}:{name}: {exc}") from None
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
        try:
            rewritten = script.inject(data, rows, manifest, translated, source_name=name)
        except (FormatError, UnicodeError) as exc:
            raise FormatError(f"{filename} ({archive}:{name}): {exc}") from None
        replacements[archive][name] = rewritten
        used.append(filename)
        changed += rewritten != data
    validate_names(export_names)
    extras = sorted(f for f in available if f not in export_names)
    outputs, verification = [], {}
    for name, raw in snapshots.items():
        rebuilt = pac.rebuild(io.BytesIO(raw), indexes[name], replacements[name])
        verification[name] = verify_archive(raw, rebuilt, replacements[name])
        outputs.append((name, rebuilt))
    result = {"schema": "nexas-pack/1", "translated_files": used, "missing_translations": missing,
              "unmatched_json": extras, "changed_scripts": changed,
              "copied_blocked_scripts": sorted(m["member"] for m in blocked.values()),
              "archives": verification, "runtime_verified": False}
    outputs.append(("verification.json", _json(result)))
    write_new_tree(destination, outputs)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    extract_args = commands.add_parser("extract")
    extract_args.add_argument("game", type=Path)
    extract_args.add_argument("--output", required=True, type=Path)
    extract_args.add_argument("--archives", nargs="+",
                              help="low-to-high priority basenames (default: packs named by "
                                   "Config.pac/packlist.dat that exist and hold .bin scripts)")
    extract_args.add_argument("--verify-edits", action="store_true",
                              help="also edit every row, rebuild each PAC, re-read and re-parse it")
    pack_args = commands.add_parser("pack")
    pack_args.add_argument("workspace", type=Path)
    pack_args.add_argument("--output", required=True, type=Path)
    pack_args.add_argument("--translations", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "extract":
            report = extract(args.game, args.output, args.archives, verify_edits=args.verify_edits)
            for warning in report.get("warnings", []):
                print(f"warning: {warning}", file=sys.stderr)
            print(json.dumps({"status": report["status"], "profile": report["profile"],
                              "summary": report["summary"], "blocked": report["blocked"],
                              "edit_check": report.get("edit_check"), "delivery": report["delivery"]},
                             ensure_ascii=True, indent=2))
            # Same convention as the other workspace extractors: partial output exits 1.
            raise SystemExit(report["status"] != "complete")
        print(json.dumps(pack(args.workspace, args.output, args.translations), ensure_ascii=True, indent=2))
    except (FormatError, ValueError, UnicodeError, OSError, struct.error) as exc:
        print(f"error: {args.action}: {exc}", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
