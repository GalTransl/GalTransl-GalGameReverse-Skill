# SPDX-License-Identifier: GPL-3.0-only
"""Kaguya ver4 tables -> ordered GalTransl JSON -> independent message.dat.

The external message table is not a member of scr.arc. LINK6 is separately
roundtripped as supporting evidence; SCR bytecode is never guessed or edited.
"""
import argparse
from collections import Counter
from dataclasses import replace
import io
import json
from pathlib import Path
import stat

from ..archives import kaguya_link as link
from ..common.binary import FormatError
from ..common.contract import dump_rows, load_json, make_manifest, sha256, validate_translation
from ..common.safety import write_new_tree
from . import kaguya

VARIANT = "ver4-cp932-preserved-suffix"
MAX_BYTES = 64 << 20


def _json(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _read(path):
    path = Path(path)
    for part in (path, *path.parents):
        info = part.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise FormatError(f"refusing link/reparse input: {path}")
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise FormatError(f"input exceeds file budget: {path}")
    return path.read_bytes()


def _rows(doc):
    rows, locators = [], []
    for gi, group in enumerate(doc.groups):
        for occurrence, mi in enumerate(group.message_indexes):
            row = {"message": doc.messages[mi].text}
            if group.name_index >= 0:
                row["name"] = doc.names[group.name_index]
            rows.append(row)
            locators.append({"kind": "message", "group": gi, "occurrence": occurrence,
                             "message_index": mi, "name_index": group.name_index})
    for ci, choice in enumerate(doc.choices):
        rows.append({"message": choice})
        locators.append({"kind": "choice", "choice_index": ci})
    return rows, locators


def export(data: bytes) -> tuple[list[dict], dict]:
    doc = kaguya.read_message_dat(data, allow_trailer=True)
    rows, locators = _rows(doc)
    policies = ["absent" if "name" not in row else "context" if row["name"] == "％" else "writable"
                for row in rows]
    # Keep line structure and the engine's special F040/percent codepoint.
    tokens = [[t for t in ("\n", "％") if t in row["message"]] for row in rows]
    manifest = make_manifest(
        engine="kaguya", variant=VARIANT, reference="python/engines/kaguya_extract.py",
        sources={"message.dat": data}, rows=rows, locators=locators, encoding="cp932",
        name_policies=policies, protected_tokens=tokens,
        settings={"suffix": "preserve-exactly; not-interpreted", "suffix_sha256": sha256(doc.trailer),
                  "suffix_size": len(doc.trailer), "name_percent": "context-only"})
    return rows, manifest


def inject(data: bytes, original_rows: list[dict], manifest: dict, translated_rows: list[dict]) -> bytes:
    expected_rows, expected_manifest = export(data)
    if expected_rows != original_rows or expected_manifest != manifest:
        raise FormatError("Kaguya export/manifest no longer matches the source parser")
    translated = validate_translation(manifest, {"message.dat": data}, original_rows, translated_rows)
    doc = kaguya.read_message_dat(data, allow_trailer=True)
    names, choices, messages, groups = map(list, (doc.names, doc.choices, doc.messages, doc.groups))
    group_names = {}
    group_messages = {}
    for before, after, record in zip(original_rows, translated, manifest["records"]):
        for field in before:
            text = after[field]
            if text == before[field]:
                continue
            if any(ord(c) < 32 and c != "\n" for c in text):
                raise FormatError("unsupported Kaguya text control")
            if text.count("\n") != before[field].count("\n"):
                raise FormatError("Kaguya line count changed")
            if text.endswith("\n") != before[field].endswith("\n"):
                raise FormatError("Kaguya final newline changed")
            if text.count("％") != before[field].count("％"):
                raise FormatError("Kaguya special percent codepoint changed")
            encoded = kaguya._encode(text)
            if len(encoded) > MAX_BYTES or kaguya._decode(encoded) != text:
                raise FormatError("Kaguya text is not losslessly CP932 representable")
        loc = record["locator"]
        if loc["kind"] == "choice":
            choices[loc["choice_index"]] = after["message"]
            continue
        gi, mi = loc["group"], loc["message_index"]
        if "name" in after:
            if gi in group_names and group_names[gi] != after["name"]:
                raise FormatError("messages in one Kaguya group must use one consistent name")
            group_names[gi] = after["name"]
        if before["message"] != after["message"]:
            ids = group_messages.setdefault(gi, list(doc.groups[gi].message_indexes))
            ids[loc["occurrence"]] = len(messages)
            messages.append(replace(doc.messages[mi], text=after["message"]))
    # Clone changed references. Original slots, unused messages and voices survive.
    for gi, name in group_names.items():
        original = doc.groups[gi]
        if name != doc.names[original.name_index]:
            groups[gi] = replace(groups[gi], name_index=len(names))
            names.append(name)
    for gi, ids in group_messages.items():
        groups[gi] = replace(groups[gi], message_indexes=tuple(ids))
    rebuilt = replace(doc, names=tuple(names), choices=tuple(choices), messages=tuple(messages), groups=tuple(groups))
    result = kaguya.write_message_dat(rebuilt)
    parsed = kaguya.read_message_dat(result, allow_trailer=True)
    if _rows(parsed)[0] != translated or parsed.trailer != doc.trailer or parsed.header != doc.header:
        raise FormatError("Kaguya reparse verification failed")
    if parsed.raw_names[:len(doc.names)] != doc.raw_names or parsed.raw_messages[:len(doc.messages)] != doc.raw_messages:
        raise FormatError("Kaguya original shared string slots changed")
    for old, new in zip(doc.groups, parsed.groups):
        if len(old.message_indexes) != len(new.message_indexes):
            raise FormatError("Kaguya group shape changed")
        for oi, ni in zip(old.message_indexes, new.message_indexes):
            if doc.messages[oi].voices != parsed.messages[ni].voices:
                raise FormatError("Kaguya voice bindings changed")
    return result


def extract(game: Path, destination: Path, *, verify_edits: bool = False) -> dict:
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"refusing existing output: {destination}")
    data = _read(game / "message.dat")
    doc = kaguya.read_message_dat(data, allow_trailer=True)
    rows, manifest = export(data)
    rebuilt = inject(data, rows, manifest, rows)
    if rebuilt != data:
        raise FormatError("Kaguya original-text roundtrip changed bytes")
    refs = Counter(i for g in doc.groups for i in g.message_indexes)
    report = {"schema": "kaguya-workspace/1", "variant": VARIANT,
              "tables": {key: len(getattr(doc, key)) for key in ("names", "choices", "messages", "groups")},
              "message_rows": sum(len(g.message_indexes) for g in doc.groups), "choice_rows": len(doc.choices),
              "json_rows": len(rows), "json": "message.json" if rows else None,
              "unused_message_indexes": [i for i in range(len(doc.messages)) if i not in refs],
              "shared_message_slots": sum(n > 1 for n in refs.values()),
              "suffix": {"size": len(doc.trailer), "sha256": sha256(doc.trailer), "interpretation": "opaque"},
              "source_files": {"message.dat": sha256(data)}, "message_roundtrip_byte_identical": True,
              "runtime_verified": False, "alternate_message_files": []}
    outputs = [("original/message.dat", data), ("roundtrip/message.dat", rebuilt)]
    if rows:
        outputs.extend([("gt_input/message.json", dump_rows(rows)), ("metadata/message.json", _json(manifest))])
    archive_path = game / "scr.arc"
    if archive_path.exists():
        raw = _read(archive_path)
        stream = io.BytesIO(raw)
        index = link.read_index(stream)
        members = {entry.name: link.read_member(stream, index, entry) for entry in index.entries}
        archive = link.rebuild(stream, index, members)
        if archive != raw:
            raise FormatError("LINK6 roundtrip changed bytes")
        rebuilt_index = link.read_index(io.BytesIO(archive))
        for entry in rebuilt_index.entries:
            if link.read_member(io.BytesIO(archive), rebuilt_index, entry) != members[entry.name]:
                raise FormatError("rebuilt LINK6 member changed")
        outputs.extend([("original/scr.arc", raw), ("roundtrip/scr.arc", archive)])
        outputs.extend((f"original/scripts/{name}", payload) for name, payload in members.items())
        report["source_files"]["scr.arc"] = sha256(raw)
        report["link6"] = {"members": len(members), "byte_identical": True,
                           "scr_ver51_members": sum(p.startswith(b"[SCR-Ver5.1]") for p in members.values())}
    params = game / "params.dat"
    if params.exists():
        raw = _read(params)
        outputs.append(("original/params.dat", raw))
        report["source_files"]["params.dat"] = sha256(raw)
    # Known alternate directory is evidence only, never an automatic fallback.
    alternate = game / "%DEFAULT FOLDER%/message.dat"
    if alternate.exists():
        raw = _read(alternate)
        report["alternate_message_files"].append({"path": "%DEFAULT FOLDER%/message.dat",
            "size": len(raw), "sha256": sha256(raw), "selected": False})
    if verify_edits:
        edited = []
        for row, record in zip(rows, manifest["records"]):
            changed = dict(row)
            changed["message"] = "検証" + row["message"]
            if record["name_policy"] == "writable":
                changed["name"] += "試験"
            edited.append(changed)
        smoke = inject(data, rows, manifest, edited)
        report["edit_verification"] = {"changed_rows": len(edited), "reparsed_exactly": True,
                                        "size": len(smoke), "sha256": sha256(smoke)}
    for name, digest in report["source_files"].items():
        if sha256(_read(game / name)) != digest:
            raise FormatError("game input changed during extraction")
    outputs.append(("reports/extraction.json", _json(report)))
    write_new_tree(destination, outputs)
    (destination / "gt_output").mkdir()
    return report


def pack(workspace: Path, destination: Path, *, translations: Path | None = None) -> dict:
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"refusing existing output: {destination}")
    report = load_json(_read(workspace / "reports/extraction.json"), max_bytes=MAX_BYTES)
    if report.get("schema") != "kaguya-workspace/1" or report.get("variant") != VARIANT:
        raise FormatError("unsupported Kaguya workspace")
    if set(report["source_files"]) - {"message.dat", "scr.arc", "params.dat"}:
        raise FormatError("unexpected Kaguya source file")
    for name, digest in report["source_files"].items():
        if sha256(_read(workspace / "original" / name)) != digest:
            raise FormatError(f"Kaguya source snapshot changed: {name}")
    data = _read(workspace / "original/message.dat")
    rows = load_json(_read(workspace / "gt_input/message.json"), max_bytes=MAX_BYTES)
    manifest = load_json(_read(workspace / "metadata/message.json"), max_bytes=MAX_BYTES)
    directory = translations or workspace / "gt_output"
    path = directory / "message.json"
    provided = path.exists()
    translated = load_json(_read(path), max_bytes=MAX_BYTES) if provided else rows
    rewritten = inject(data, rows, manifest, translated)
    result = {"schema": "kaguya-pack/1", "source_sha256": sha256(data), "output_sha256": sha256(rewritten),
              "size": len(rewritten), "changed_rows": sum(a != b for a, b in zip(rows, translated)),
              "translation_provided": provided, "missing_translations": [] if provided else ["message.json"],
              "unmatched_json": sorted(p.name for p in directory.glob("*.json") if p.name != "message.json"),
              "reparsed_exactly": True, "runtime_verified": False}
    write_new_tree(destination, [("message.dat", rewritten), ("verification.json", _json(result))])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    ex = sub.add_parser("extract")
    ex.add_argument("game", type=Path)
    ex.add_argument("--output", required=True, type=Path)
    ex.add_argument("--verify-edits", action="store_true")
    pk = sub.add_parser("pack")
    pk.add_argument("workspace", type=Path)
    pk.add_argument("--output", required=True, type=Path)
    pk.add_argument("--translations", type=Path)
    args = parser.parse_args()
    result = (extract(args.game, args.output, verify_edits=args.verify_edits) if args.command == "extract"
              else pack(args.workspace, args.output, translations=args.translations))
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
