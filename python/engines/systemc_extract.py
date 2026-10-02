# SPDX-License-Identifier: GPL-3.0-only
"""Tomefure SystemC FPK -> ACT dialogue JSON -> rebuilt FPK, never in place."""
import argparse
import json
from pathlib import Path
import re
import stat

from ..archives.systemc import unpack_fpk, rebuild_fpk
from ..common.binary import FormatError
from ..common.contract import dump_rows, load_json, sha256
from ..common.safety import write_new_tree
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


def _verify_archive(archive, expected):
    _, actual = unpack_fpk(archive)
    if actual != expected:
        raise FormatError("rebuilt FPK did not reproduce all expected members")


def extract(game, destination, *, verify_edits=False):
    game, destination = Path(game), Path(destination)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"refusing existing output: {destination}")
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
              "source_selection": "data.fpk; loose data compared only, never merged",
              "encoding": "cp932", "name_policy": "context-only"}
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


def pack(workspace, destination, *, translations=None, jis_mode="auto"):
    from python.common.jis_substitution import JisSubstitution

    if jis_mode not in ("auto", "off"):
        raise FormatError("unsupported JIS mode")
    workspace, destination = Path(workspace), Path(destination)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"refusing existing output: {destination}")
    report = load_json(_read(workspace / "reports/extraction.json"), max_bytes=MAX_BYTES)
    if report.get("schema") != "systemc-workspace/1" or report.get("variant") != VARIANT:
        raise FormatError("unsupported SystemC workspace")
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
        rewritten[name] = inject_act(name, members, original, metadata, after, text_codec=text_codec)
        result["changed_rows"] += sum(a != b for a, b in zip(original, after))
        result["translations" if provided else "missing_translations"].append(json_name)
    result["unmatched_json"] = sorted(p.name for p in translated_dir.glob("*.json") if p.name not in expected_json)
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
    pk.add_argument("--output", type=Path, required=True)
    pk.add_argument("--translations", type=Path)
    pk.add_argument("--jis-mode", choices=("auto", "off"), default="auto")
    args = parser.parse_args()
    result = (extract(args.game, args.output, verify_edits=args.verify_edits) if args.command == "extract"
              else pack(args.workspace, args.output, translations=args.translations, jis_mode=args.jis_mode))
    # Full per-member detail is saved in reports; keep console output compact.
    print(json.dumps({k: v for k, v in result.items() if k not in {"scripts", "loose_data"}},
                     ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
