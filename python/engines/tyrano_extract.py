"""TyranoScript scenarios (Electron app.asar or loose data/) -> GalTransl workspace -> patch.

New implementation for this skill. Reads ``resources/app.asar`` (or a loose
``data/`` tree) without executing game code, exports dialogue from
``data/scenario`` scripts, and writes translations back with the shared
writer in ``tyrano.py``. Scripts that no other script or page names are
reported as unreferenced and left out of ``gt_input`` unless requested.

Packing never touches the game. ``--mode asar`` streams a rebuilt
``resources/app.asar`` (unchanged members copied verbatim) into a new
directory; ``--mode tpatch`` writes the engine's own ``<projectID>.tpatch``
zip with only changed scripts (the engine applies it by rewriting app.asar on
the next launch, see engines/tyrano.md). Loose sources produce only the
changed files at their original relative paths.
"""
import argparse
import fnmatch
import io
import os
from pathlib import Path
import re
import sys
import zipfile

from python.archives import asar
from python.common.contract import dump_rows, load_json, sha256
from python.common.safety import Limits, validate_names, validate_new_tree_destination, write_new_tree
from . import tyrano
from .kirikiri_extract import js, read_file, regular

PROFILE = "tyrano-workspace/1"
SCRIPT_BUDGET = 64 << 20
TEXT_SCAN_BUDGET = 32 << 20
DEFAULT_MEMBERS = ("data/scenario/*.ks",)
REFERENCE_SUFFIXES = (".ks", ".js", ".html", ".json", ".tjs")
# Tags whose storage= names a scenario file (others name images, audio ...).
SCENARIO_TAGS = frozenset({"jump", "call", "link", "glink", "button", "clickable", "sleepgame",
                           "set_resizecall", "showsave", "showload"})


class Source:
    """Read-only view of a Tyrano game: an Electron asar or a loose directory."""

    def __init__(self, game: Path, archive: str | None):
        self.game = Path(os.path.abspath(game))
        if not self.game.is_dir():
            raise ValueError("game path is not a directory")
        candidate = archive if archive is not None else "resources/app.asar"
        path = self.game.joinpath(*validate_names([candidate])[0].split("/"))
        self.kind = "asar" if path.is_file() else "loose"
        if archive is not None and self.kind != "asar":
            raise ValueError(f"asar archive not found: {archive}")
        self.archive = candidate if self.kind == "asar" else None
        if self.kind == "asar":
            self.path = regular(path)
            with self.path.open("rb") as stream:
                self.index = asar.read_index(stream)
                prefix, _ = asar.plan_rebuild(self.index, {})
            self.header_sha256 = sha256(prefix)
            self.names = [e.path for e in self.index.entries if not e.unpacked]
        else:
            if not (self.game / "data" / "scenario").is_dir():
                raise ValueError("no resources/app.asar and no loose data/scenario directory")
            self.path = self.game
            self.names = []
            for root, dirs, files in os.walk(self.game / "data"):
                dirs[:] = sorted(d for d in dirs if not os.path.islink(os.path.join(root, d)))
                for name in sorted(files):
                    self.names.append(Path(root, name).relative_to(self.game).as_posix())
                    if len(self.names) > 200_000:
                        raise ValueError("loose data tree exceeds entry budget")

    def size(self, name: str) -> int:
        if self.kind == "asar":
            return self.index.member(name).size
        return (self.game / name).stat().st_size

    def read(self, name: str, limit: int = 32 << 20) -> bytes:
        if self.kind == "asar":
            with self.path.open("rb") as stream:
                return asar.read_member(stream, self.index, self.index.member(name), max_bytes=limit)
        return read_file(self.game / name, limit)

    def describe(self) -> dict:
        if self.kind == "asar":
            return {"kind": "asar", "game": str(self.game), "archive": self.archive,
                    "size": self.index.file_size, "header_sha256": self.header_sha256}
        return {"kind": "loose", "game": str(self.game)}


def _project(source: Source) -> dict:
    result = {"projectID": None, "patch_apply_auto": None}
    if "data/system/Config.tjs" in source.names:
        text = source.read("data/system/Config.tjs", 4 << 20).decode("utf-8", errors="replace")
        for key in result:
            match = re.search(rf"^\s*;\s*{key}\s*=\s*(.*?)\s*$", text, re.MULTILINE)
            if match:
                result[key] = match.group(1)
    return result


def _references(source: Source, scripts: dict, parsed: dict) -> tuple[set, list]:
    """Basenames named by storage= attributes or literally by text resources."""
    referenced, dynamic = {"first.ks", "make.ks"}, []
    for name, script in parsed.items():
        for kind, literal in script.structure:
            if kind != "tag":
                continue
            tag = tyrano._tag_name(literal.lstrip("@[").rstrip("]"))
            for match in re.finditer(r"""storage\s*=\s*("[^"]*"|'[^']*'|[^\s"'\]]+)""", literal):
                value = match.group(1).strip("\"'")
                if value.startswith("&") and tag in SCENARIO_TAGS:
                    dynamic.append(f"{name}: {literal[:80]}")
                elif value.lower().endswith(".ks") or (value and tag in SCENARIO_TAGS):
                    referenced.add(Path(value).name.lower())
    total = 0
    candidates = {Path(n).name.lower() for n in scripts}
    for name in source.names:
        if not name.lower().endswith(REFERENCE_SUFFIXES) or name.startswith("node_modules/"):
            continue
        size = source.size(name)
        if size > (4 << 20):
            continue
        total += size
        if total > TEXT_SCAN_BUDGET:
            dynamic.append("reference scan budget exhausted")
            break
        text = source.read(name, 4 << 20).decode("utf-8", errors="replace").lower()
        own = Path(name).name.lower()
        referenced.update(c for c in candidates if c != own and c in text)
    return referenced, dynamic


def _flat_names(members: list[str]) -> list[str]:
    stems = [Path(m).stem for m in members]
    names = []
    for member, stem in zip(members, stems):
        if stems.count(stem) > 1:
            stem = member.removesuffix(".ks").replace("/", "__")
        names.append(stem + ".json")
    return validate_names(names)


def extract(game, output, *, archive=None, members=DEFAULT_MEMBERS, include_unreferenced=False):
    output = Path(output)
    validate_new_tree_destination(output)
    source = Source(Path(game), archive)
    scripts, total = {}, 0
    for name in source.names:
        if not (name.startswith("data/") and name.lower().endswith(".ks")):
            continue
        total += source.size(name)
        if total > SCRIPT_BUDGET:
            raise ValueError("Tyrano script selection exceeds budget")
        scripts[name] = source.read(name)
    selected = [n for n in scripts if any(fnmatch.fnmatchcase(n, p) for p in members)]
    if not selected:
        raise ValueError("no scenario scripts matched --members")
    parsed, diagnostics = {}, []
    for name, raw in scripts.items():
        try:
            parsed[name] = tyrano.parse(raw)
        except tyrano.TyranoError as exc:
            if name in selected:
                raise ValueError(f"{name}: {exc}") from exc
            diagnostics.append({"member": name, "error": str(exc), "role": "support script not parsed"})
    charas = tyrano.display_names(list(parsed.values()))
    referenced, dynamic = _references(source, scripts, parsed)
    flats = dict(zip(selected, _flat_names(selected)))
    payloads = [("gt_output/.keep", b"")]
    exports, counts = [], {"files": 0, "rows": 0, "named": 0, "choices": 0, "unreferenced_rows": 0}
    names_seen = {}
    for name, raw in scripts.items():
        payloads.append(("original/" + name, raw))
        entry = {"member": name, "sha256": sha256(raw), "exported": False}
        if name in parsed and name in selected:
            script = parsed[name]
            rows, locators = tyrano.export_rows(script, charas)
            if tyrano.rebuild(raw, script, rows, {}, charas, label=name) != raw:
                raise ValueError(f"{name}: identity rebuild differs")
            smoke = [dict(r, message="验证" + r["message"]) for r in rows]
            rebuilt = tyrano.rebuild(raw, script, smoke, {}, charas, label=name)
            tyrano.verify(rebuilt, script, smoke, {}, charas, label=name)
            reachable = Path(name).name.lower() in referenced
            entry.update(rows=len(rows), choices=len(script.choices), reachable=reachable,
                         skipped_block_text=script.skipped_block_text)
            if rows and (reachable or include_unreferenced):
                flat = flats[name]
                manifest = tyrano.manifest(name, raw, rows, locators, script)
                payloads += [("gt_input/" + flat, dump_rows(rows)), ("metadata/" + flat, js(manifest))]
                entry.update(json=flat, exported=True)
                counts["files"] += 1
                counts["rows"] += len(rows)
                counts["named"] += sum("name" in r for r in rows)
                counts["choices"] += len(script.choices)
                for row in rows:
                    if "name" in row:
                        names_seen[row["name"]] = names_seen.get(row["name"], 0) + 1
            elif rows:
                counts["unreferenced_rows"] += len(rows)
        exports.append(entry)
    if not counts["files"]:
        raise ValueError("no exportable dialogue; check --members, or pass --include-unreferenced "
                         "when scenarios are only reached through computed storage names")
    report = {
        "profile": PROFILE, "script_profile": tyrano.PROFILE, "source": source.describe(),
        "project": _project(source), "members": list(members), "exports": exports, "counts": counts,
        "speaker_names": dict(sorted(names_seen.items(), key=lambda kv: -kv[1])),
        "chara_jnames": charas, "diagnostics": diagnostics,
        "reachability": {"method": "basename named by a storage= value or literally by a .ks/.js/.html/"
                                   ".json/.tjs resource; first.ks and make.ks are engine entry points",
                         "dynamic_references": dynamic[:20],
                         "unreferenced": [e["member"] for e in exports if e.get("reachable") is False],
                         "unreferenced_included": include_unreferenced},
        "validation": {"original_scripts_identity_rebuild": True, "smoke_test_reparsed": True},
        "runtime_verified": False,
    }
    payloads.append(("reports/extraction.json", js(report)))
    write_new_tree(output, payloads, Limits(max_file_bytes=SCRIPT_BUDGET, max_total_bytes=SCRIPT_BUDGET * 3))
    return report


def _translations(workspace: Path, report: dict, parsed: dict, charas: dict):
    exported = {e["json"]: e for e in report["exports"] if e.get("exported")}
    for folder in ("gt_input", "metadata"):
        if {p.name for p in (workspace / folder).glob("*.json")} != set(exported):
            raise ValueError(f"{folder} JSON set changed")
    unknown = {p.name for p in (workspace / "gt_output").glob("*.json")} - set(exported)
    if unknown:
        raise ValueError(f"unknown translation filenames: {sorted(unknown)}")
    result, votes = {}, []
    for flat, entry in exported.items():
        name = entry["member"]
        script = parsed[name]
        rows, locators = tyrano.export_rows(script, charas)
        if load_json(read_file(workspace / "gt_input" / flat)) != rows:
            raise ValueError(f"{flat}: gt_input differs from the original export")
        manifest = load_json(read_file(workspace / "metadata" / flat))
        if manifest != tyrano.manifest(name, read_file(workspace / "original" / name, SCRIPT_BUDGET), rows,
                                       locators, script):
            raise ValueError(f"{flat}: metadata differs from the original export")
        path = workspace / "gt_output" / flat
        if not path.exists():
            continue
        translated = tyrano.validate_rows(manifest, {name: read_file(workspace / "original" / name, SCRIPT_BUDGET)},
                                          rows, load_json(read_file(path)))
        votes += [(f"{flat} row {i}", a["name"], b["name"])
                  for i, (a, b) in enumerate(zip(rows, translated)) if "name" in a]
        result[name] = [dict(b, name=a["name"]) if "name" in a else b for a, b in zip(rows, translated)]
    return result, tyrano.name_map(votes)


def pack(workspace, output, *, mode=None, game=None):
    workspace, output = Path(workspace), Path(output)
    validate_new_tree_destination(output)
    report = load_json(read_file(workspace / "reports/extraction.json"))
    if report.get("profile") != PROFILE:
        raise ValueError("unsupported Tyrano workspace")
    originals = {}
    for entry in report["exports"]:
        raw = read_file(workspace / "original" / entry["member"], SCRIPT_BUDGET)
        if sha256(raw) != entry["sha256"]:
            raise ValueError(f"original script changed: {entry['member']}")
        originals[entry["member"]] = raw
    parsed = {}
    for name, raw in originals.items():
        try:
            parsed[name] = tyrano.parse(raw)
        except tyrano.TyranoError:
            pass
    charas = tyrano.display_names(list(parsed.values()))
    translations, names = _translations(workspace, report, parsed, charas)
    changed = {}
    for name, script in parsed.items():
        rows, _ = tyrano.export_rows(script, charas)
        wanted = translations.get(name, rows)
        rebuilt = tyrano.rebuild(originals[name], script, wanted, names, charas, label=name)
        tyrano.verify(rebuilt, script, wanted, names, charas, label=name)
        if rebuilt != originals[name]:
            changed[name] = rebuilt
    src = report["source"]
    mode = mode or ("asar" if src["kind"] == "asar" else "loose")
    result = {"profile": PROFILE, "mode": mode, "changed_members": sorted(changed),
              "translated_files": sorted(translations), "name_map": names, "runtime_verified": False}
    if not changed:
        raise ValueError("no script changed; nothing to pack")
    if mode == "loose":
        files = [(name, data) for name, data in sorted(changed.items())]
        result["deployment"] = "Copy the changed files over the game's data/ tree after backing it up."
        write_new_tree(output, files + [("reports/pack.json", js(result))])
        return result
    if src["kind"] != "asar":
        raise ValueError(f"--mode {mode} needs an asar source")
    game = Path(os.path.abspath(game)) if game else Path(src["game"])
    source = Source(game, src["archive"])
    if source.header_sha256 != src["header_sha256"] or source.index.file_size != src["size"]:
        raise ValueError("app.asar differs from the extracted one; re-extract")
    for name, raw in originals.items():
        if source.read(name, SCRIPT_BUDGET) != raw:
            raise ValueError(f"app.asar member differs from workspace original: {name}")
    if mode == "tpatch":
        project = report["project"]
        project_id = project.get("projectID")
        if not project_id or not re.fullmatch(r"[A-Za-z0-9_.-]+", project_id):
            raise ValueError("projectID not found in data/system/Config.tjs; cannot name the .tpatch")
        if str(project.get("patch_apply_auto")).lower() == "false":
            raise ValueError("Config.tjs disables patch_apply_auto; the engine will not apply a .tpatch")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, data in sorted(changed.items()):
                archive.writestr(name, data)
        with zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as archive:
            if {i.filename: archive.read(i) for i in archive.infolist()} != changed:
                raise ValueError("tpatch readback differs")
        result["tpatch"] = project_id + ".tpatch"
        result["deployment"] = ("Place next to the game EXE. On next launch the engine extracts app.asar, overlays "
                                "these files, rewrites app.asar in place and deletes the .tpatch. Back up "
                                "resources/app.asar first and wait for the restart prompt before closing.")
        write_new_tree(output, [(result["tpatch"], buffer.getvalue()), ("reports/pack.json", js(result))])
        return result
    if mode != "asar":
        raise ValueError(f"unknown mode: {mode}")
    size = asar.rebuilt_size(source.index, changed)
    target = src["archive"]

    def writer(sink):
        with source.path.open("rb") as stream:
            asar.write_rebuilt(stream, source.index, changed, sink)

    write_new_tree(output, [], streams=[(target, writer, size)])
    with source.path.open("rb") as before, (output / target).open("rb") as after:
        result["verification"] = asar.verify_rebuilt(before, source.index, after, changed)
    result["archive"] = target
    result["bytes"] = size
    result["deployment"] = (f"Back up the game's {target}, then copy this {target} over it. "
                            "Electron builds that enforce asar header integrity will reject the new file.")
    write_new_tree(output / "reports", [("pack.json", js(result))])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    ex = sub.add_parser("extract")
    ex.add_argument("game")
    ex.add_argument("output")
    ex.add_argument("--asar", help="archive path relative to the game (default resources/app.asar)")
    ex.add_argument("--members", nargs="+", default=list(DEFAULT_MEMBERS))
    ex.add_argument("--include-unreferenced", action="store_true")
    pk = sub.add_parser("pack")
    pk.add_argument("workspace")
    pk.add_argument("output")
    pk.add_argument("--mode", choices=("asar", "tpatch", "loose"))
    pk.add_argument("--game", help="game directory if it moved since extraction")
    args = parser.parse_args()
    if args.command == "extract":
        result = extract(args.game, args.output, archive=args.asar, members=args.members,
                         include_unreferenced=args.include_unreferenced)
        out = {"counts": result["counts"], "unreferenced": result["reachability"]["unreferenced"],
               "dynamic_references": result["reachability"]["dynamic_references"]}
    else:
        out = pack(args.workspace, args.output, mode=args.mode, game=args.game)
    sys.stdout.buffer.write(js(out))


if __name__ == "__main__":
    main()
