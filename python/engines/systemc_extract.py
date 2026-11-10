# SPDX-License-Identifier: GPL-3.0-only
"""SystemC FPK -> CP932 ACT dialogue JSON -> rebuilt FPK, never in place."""
import argparse
import json
from pathlib import Path
import re
import stat
import sys

from ..archives.systemc import read_fpk_index_stream, read_fpk_member, unpack_fpk, rebuild_fpk
from ..common.binary import FormatError
from ..common.contract import dump_rows, load_json, sha256
from ..common.jis_workflow import preflight_translations
from ..common.safety import write_new_tree, validate_new_tree_destination
from .systemc import MAX_BYTES, VARIANT, export_act, inject_act


def _json(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _read(path):
    path = Path(path)
    for part in (path, *path.parents):
        info = part.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise FormatError(f"refusing link/reparse input: {path}")
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise FormatError(f"SystemC input outside file budget: {path}")
    with path.open("rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise FormatError("SystemC input grew beyond budget")
    return data


def _acts(members):
    acts = sorted(n for n in members if re.fullmatch(r"ACT_[A-Z]\.txt", n))
    if not acts:
        raise FormatError("FPK has no supported SystemC ACT texts")
    return acts


SCRIPT_MEMBER = re.compile(r"(?:ACT_[A-Z]\.(?:txt|DAT)|.+\.spt|charaid\.tbl)", re.IGNORECASE)
MAX_SIBLING_PACKAGES = 256
MAX_COMPARE_BYTES = 256 << 20
MAX_REPLACE_LIST = 1 << 20


def _parse_replace_list(data):
    """``replace.txt`` in a patch FPK: ``!SECTION`` lines followed by member names."""
    if len(data) > MAX_REPLACE_LIST:
        raise FormatError("replace.txt exceeds budget")
    text = data.decode("cp932", errors="strict")
    sections, current = {}, ""
    for line in text.replace("\r\n", "\n").split("\n"):
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        if line.startswith("!"):
            current = line[1:]
            sections.setdefault(current, [])
        else:
            sections.setdefault(current, []).append(line)
    return sections


def _sibling_packages(game, selected, members):
    """Inventory other same-directory FPKs by index; never merge them.

    Reports members sharing a name with the selected package, whether their
    decoded content differs, and any ``replace.txt`` list. Payloads other than
    shared members and replace.txt are not read.
    """
    paths = sorted((p for p in Path(game).iterdir()
                    if p.suffix.lower() == ".fpk" and p.name.casefold() != selected.casefold()),
                   key=lambda p: p.name.casefold())
    if len(paths) > MAX_SIBLING_PACKAGES:
        raise FormatError("too many sibling FPK packages")
    packages, warnings, budget = [], [], MAX_COMPARE_BYTES
    for path in paths:
        info = path.lstat()
        entry = {"path": path.name, "size": info.st_size}
        packages.append(entry)
        if not stat.S_ISREG(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            entry.update(status="skipped", reason="not an ordinary file")
            continue
        try:
            with path.open("rb") as stream:
                index = read_fpk_index_stream(stream)
                shared = []
                for item in index.entries:
                    if item.name == "replace.txt":
                        try:
                            entry["replace_list"] = _parse_replace_list(read_fpk_member(stream, item))
                        except (FormatError, UnicodeError) as exc:
                            entry["replace_list_error"] = str(exc)
                    if item.name not in members:
                        continue
                    record = {"member": item.name, "script": bool(SCRIPT_MEMBER.fullmatch(item.name))}
                    if item.size > budget:
                        record["content"] = "not-compared-budget"
                    else:
                        payload = read_fpk_member(stream, item)
                        budget -= item.size
                        record["content"] = "identical" if payload == members[item.name] else "different"
                    shared.append(record)
        except FormatError as exc:
            entry.update(status="unsupported", reason=str(exc))
            continue
        entry.update(status="indexed", members=len(index.entries), same_name_members=shared)
        if "replace_list" in entry:
            listed = {n for names in entry["replace_list"].values() for n in names}
            entry["replace_list_overrides_selected"] = sorted(listed & members.keys())
        differing = [r["member"] for r in shared if r["script"] and r["content"] != "identical"]
        if differing:
            entry["differing_script_members"] = differing
            warnings.append(f"{path.name} contains {len(differing)} script member(s) that differ from "
                            f"{selected} ({', '.join(differing[:8])}{' ...' if len(differing) > 8 else ''}); "
                            "the game may load the patch version. Confirm the effective version before "
                            "translating or packing.")
    return packages, warnings


def _verify_archive(archive, expected):
    _, actual = unpack_fpk(archive)
    if actual != expected:
        raise FormatError("rebuilt FPK did not reproduce all expected members")


def extract(game, destination, *, verify_edits=False):
    game, destination = Path(game), Path(destination)
    validate_new_tree_destination(destination)
    raw = _read(game / "data.fpk")
    index, members = unpack_fpk(raw)
    outputs = [("original/data.fpk", raw)]
    outputs.extend((f"original/members/{n}", data) for n, data in members.items())
    rewritten, edited, used_spt = dict(members), dict(members), set()
    report = {"schema": "systemc-workspace/1", "variant": VARIANT,
              "source": {"path": "data.fpk", "size": len(raw), "sha256": sha256(raw)},
              "members": len(members), "decoded_bytes": sum(map(len, members.values())),
              "archive_index_offset": index.offset, "scripts": [], "json_files": 0,
              "json_rows": 0, "selection_rows": 0, "runtime_verified": False,
              "loose_data": {"matching": [], "differing": [], "missing": []},
              "source_selection": "data.fpk; loose data and sibling FPKs compared only, never merged",
              "encoding": "cp932", "name_policy": "context-only"}
    packages, warnings = _sibling_packages(game, "data.fpk", members)
    report["sibling_packages"] = packages
    report["overridden_script_members"] = sorted({m for p in packages for m in p.get("differing_script_members", [])})
    report["warnings"] = warnings
    for warning in warnings:
        # Shown before parsing so it is visible even if the base scripts fail.
        print(f"WARNING: {warning}", file=sys.stderr, flush=True)
    for name in _acts(members):
        rows, manifest = export_act(name, members)
        rebuilt = inject_act(name, members, rows, manifest, rows)
        if rebuilt != members[name]:
            raise FormatError(f"SystemC original-text roundtrip changed {name}")
        rewritten[name] = rebuilt
        stem = name[:-4]
        sections = manifest["settings"]["sections"]
        used_spt.update(s["spt"] for s in sections)
        selections = sum(s["rows"] for s in sections if s["kind"] == "SS")
        report["scripts"].append({"member": name, "rows": len(rows), "selection_rows": selections,
            "sections": sections, "status": "exported" if rows else "empty",
            "outputs": {"json": f"{stem}.json" if rows else None}, "byte_identical": True})
        report["json_rows"] += len(rows)
        report["selection_rows"] += selections
        if rows:
            report["json_files"] += 1
            outputs.extend([(f"gt_input/{stem}.json", dump_rows(rows)),
                            (f"metadata/{stem}.json", _json(manifest))])
        if verify_edits and rows:
            changed = [dict(row, message="検証" + row["message"]) for row in rows]
            edited[name] = inject_act(name, members, rows, manifest, changed)
    orphans = sorted(n for n in members if n.lower().endswith(".spt") and n not in used_spt)
    report["unreferenced_spt"] = orphans
    report["unreferenced_spt_policy"] = "preserved opaque; absent from ACT/DAT section tables; not exported"
    for name, payload in members.items():
        path = game / "data" / name
        if not path.exists():
            report["loose_data"]["missing"].append(name)
            continue
        loose = _read(path)
        key = "matching" if loose == payload else "differing"
        report["loose_data"][key].append(name)
    repacked = rebuild_fpk(raw, rewritten)
    _verify_archive(repacked, rewritten)
    if repacked != raw:
        raise FormatError("SystemC original FPK roundtrip changed bytes")
    outputs.append(("roundtrip/data.fpk", repacked))
    report["archive_roundtrip_byte_identical"] = True
    report["roundtrip_sha256"] = sha256(repacked)
    if verify_edits:
        smoke = rebuild_fpk(raw, edited)
        _verify_archive(smoke, edited)
        report["edit_verification"] = {"changed_rows": report["json_rows"], "changed_act_files": report["json_files"],
            "reparsed_exactly": True, "compiled_members_unchanged": True,
            "size": len(smoke), "sha256": sha256(smoke),
            "test": "prefix first message line with CP932 検証; preserve physical line count",
            "runtime_verified": False}
    if _read(game / "data.fpk") != raw:
        raise FormatError("SystemC source archive changed during extraction")
    outputs.append(("reports/extraction.json", _json(report)))
    write_new_tree(destination, outputs)
    (destination / "gt_output").mkdir()
    return report


def pack(workspace, destination=None, *, translations=None, jis_mode="auto", jis_preflight=False,
         base_confirmed=False):
    from python.common.jis_substitution import JisSubstitution

    if jis_mode not in ("auto", "off"):
        raise FormatError("unsupported JIS mode")
    if jis_preflight and jis_mode != "auto":
        raise FormatError("JIS preflight requires --jis-mode auto")
    workspace = Path(workspace)
    if not jis_preflight:
        if destination is None:
            raise FormatError("SystemC pack requires an output destination")
        destination = Path(destination)
        validate_new_tree_destination(destination)
    report = load_json(_read(workspace / "reports/extraction.json"), max_bytes=MAX_BYTES)
    if report.get("schema") != "systemc-workspace/1" or report.get("variant") != VARIANT:
        raise FormatError("unsupported SystemC workspace")
    overridden = report.get("overridden_script_members") or []
    if overridden and not base_confirmed:
        # A same-directory patch FPK ships different script members; writing
        # data.fpk may have no effect or desynchronise ACT/DAT/SPT at runtime.
        raise FormatError(f"sibling FPK overrides {len(overridden)} script member(s) of data.fpk "
                          f"(see reports/extraction.json sibling_packages); confirm the effective "
                          f"version, then pass --base-confirmed")
    raw = _read(workspace / "original/data.fpk")
    if report["source"] != {"path": "data.fpk", "size": len(raw), "sha256": sha256(raw)}:
        raise FormatError("SystemC source snapshot changed")
    _, members = unpack_fpk(raw)
    text_codec = JisSubstitution() if jis_mode == "auto" else None
    if text_codec is not None:
        # One fixed mapping across all files, including untranslated scripts.
        for name in [*_acts(members), "charaid.tbl"]:
            text_codec.reserve(members[name].decode("cp932"))
    for name, payload in members.items():
        if _read(workspace / "original/members" / name) != payload:
            raise FormatError(f"SystemC decoded source snapshot changed: {name}")
    translated_dir = Path(translations) if translations is not None else workspace / "gt_output"
    rewritten = dict(members)
    result = {"schema": "systemc-pack/1", "variant": VARIANT, "source_sha256": sha256(raw),
              "translations": [], "missing_translations": [], "changed_rows": 0,
              "runtime_verified": False, "compiled_members_unchanged": True}
    expected_json = set()
    originals, translated = {}, {}
    for name in _acts(members):
        rows, manifest = export_act(name, members)
        if not rows:
            continue
        json_name = name[:-4] + ".json"
        expected_json.add(json_name)
        original = load_json(_read(workspace / "gt_input" / json_name), max_bytes=MAX_BYTES)
        metadata = load_json(_read(workspace / "metadata" / json_name), max_bytes=MAX_BYTES)
        if original != rows or metadata != manifest:
            raise FormatError(f"SystemC JSON/metadata source identity changed: {name}")
        path = translated_dir / json_name
        provided = path.exists()
        after = load_json(_read(path), max_bytes=MAX_BYTES) if provided else original
        if jis_preflight:
            originals[json_name] = original
            if provided:
                translated[json_name] = after
        if not jis_preflight:
            rewritten[name] = inject_act(name, members, original, metadata, after, text_codec=text_codec)
        result["changed_rows"] += sum(a != b for a, b in zip(original, after))
        result["translations" if provided else "missing_translations"].append(json_name)
    result["unmatched_json"] = sorted(p.name for p in translated_dir.glob("*.json") if p.name not in expected_json)
    if jis_preflight:
        extra = {f"original/members/{name}": members[name].decode("cp932")
                 for name in [*_acts(members), "charaid.tbl"]}
        return dict(result, schema="systemc-jis-preflight/1", jis_preflight=preflight_translations(
            originals, translated, encoding="cp932", extra_texts=extra))
    repacked = rebuild_fpk(raw, rewritten)
    _verify_archive(repacked, rewritten)
    result.update(output_sha256=sha256(repacked), size=len(repacked), reparsed_exactly=True,
                  byte_identical=repacked == raw)
    result["text_encoding"] = text_codec.summary() if text_codec is not None else {"mode": "strict-cp932"}
    extras = text_codec.artifacts() if text_codec is not None else []
    result["jis_artifacts"] = [name for name, _ in extras]
    write_new_tree(destination, [("data.fpk", repacked), ("verification.json", _json(result)), *extras])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    ex = commands.add_parser("extract")
    ex.add_argument("game", type=Path)
    ex.add_argument("--output", type=Path, required=True)
    ex.add_argument("--verify-edits", action="store_true")
    pk = commands.add_parser("pack")
    pk.add_argument("workspace", type=Path)
    pk.add_argument("--output", type=Path)
    pk.add_argument("--translations", type=Path)
    pk.add_argument("--jis-mode", choices=("auto", "off"), default="auto")
    pk.add_argument("--jis-preflight", action="store_true", help="report JIS proxy conflicts without writing a package")
    pk.add_argument("--base-confirmed", action="store_true",
                    help="data.fpk scripts confirmed effective despite differing sibling FPK members")
    args = parser.parse_args()
    if args.command == "pack":
        if not args.jis_preflight and args.output is None:
            parser.error("pack requires --output unless --jis-preflight is selected")
        if args.jis_preflight and args.jis_mode != "auto":
            parser.error("--jis-preflight requires --jis-mode auto")
    try:
        result = (extract(args.game, args.output, verify_edits=args.verify_edits) if args.command == "extract"
                  else pack(args.workspace, args.output, translations=args.translations,
                            jis_mode=args.jis_mode, jis_preflight=args.jis_preflight,
                            base_confirmed=args.base_confirmed))
    except (FormatError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
    # Full per-member detail is saved in reports; keep console output compact.
    print(json.dumps({k: v for k, v in result.items() if k not in {"scripts", "loose_data", "sibling_packages"}},
                     ensure_ascii=True, indent=2))
    if args.command == "pack" and args.jis_preflight and not result["jis_preflight"]["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
