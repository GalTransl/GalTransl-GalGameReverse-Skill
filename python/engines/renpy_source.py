"""Loose Ren'Py .rpy source workspace: gt_input, manifest, pack and read-back.

Uses the finite lexer in renpy.py; never imports Ren'Py or runs game code.
Only loose files under game/ are read: Ren'Py never loads .rpy from archives.
A rewritten .rpy no longer matches the MD5 stored at the end of its .rpyc,
so Ren'Py recompiles the source at the next start (renpy/script.py).
"""
from collections import Counter
import hashlib
from pathlib import Path
import sys

from ..archives import rpa
from ..common.contract import dump_rows, load_json, make_manifest, sha256, validate_translation
from ..common.safety import validate_new_tree_destination, write_new_tree
from . import renpy
from . import renpy_extract as workspace_io
from . import renpy_rpyc as rpyc

PROFILE = "renpy-rpy-source-v1"
UTF8_BOM = b"\xef\xbb\xbf"


def decode(raw):
    bom = raw.startswith(UTF8_BOM)
    try:
        return raw[len(UTF8_BOM) if bom else 0:].decode("utf-8"), bom
    except UnicodeDecodeError as exc:
        raise ValueError(f"Ren'Py .rpy must be UTF-8: {exc}") from exc


def encode(text, bom):
    return (UTF8_BOM if bom else b"") + text.encode("utf-8")


def collect(sources, extra):
    """Character aliases (whitelist) and literal display names over all files."""
    aliases, names = set(extra), {}
    for name, raw in sources.items():
        for alias, display in renpy.characters(decode(raw)[0]).items():
            if alias in renpy._RESERVED:
                continue
            aliases.add(alias)
            names[alias] = display if alias not in names or names[alias] == display else None
    return sorted(aliases), {k: v for k, v in names.items() if isinstance(v, str)}


def export(name, raw, speakers, names):
    text, bom = decode(raw)
    diagnostics = []
    targets = renpy.extract(text, filename=name, speakers=speakers, diagnostics=diagnostics)
    if renpy.patch(text, {}, filename=name, speakers=speakers) != text or encode(text, bom) != raw:
        raise ValueError(f"{name}: rpy identity round trip differs")
    rows, locators = [], []
    for index, target in enumerate(targets):
        if target.role == "name" or not target.text:
            continue  # Character names stay context; empty strings carry no text.
        display = speaker_name(target.speaker, names)
        rows.append({"name": display, "message": target.text} if display else {"message": target.text})
        locators.append({"target": index, "line": text.count("\n", 0, target.start) + 1,
                         "speaker": target.speaker, "syntax": target.syntax})
    manifest = make_manifest(engine="renpy", variant=PROFILE, reference="python/engines/renpy.py",
                             sources={name: raw}, rows=rows, locators=locators, encoding="utf-8",
                             settings={"speakers": speakers, "bom": bom})
    return rows, manifest, diagnostics, text, bom


def load(directory):
    names = [n for n in workspace_io.discover_loose(directory) if n.lower().endswith(".rpy")]
    if not names or len(names) > workspace_io.MAX_LOOSE_FILES:
        raise ValueError("loose .rpy count outside budget (Ren'Py loads .rpy only from game/, never archives)")
    sources, total = {}, 0
    for name in names:
        raw = workspace_io.read_bounded(Path(directory).joinpath(*name.split("/")), rpyc.MAX_FILE)
        total += len(raw)
        if total > workspace_io.MAX_TOTAL:
            raise ValueError("loose .rpy total exceeds budget")
        sources[name] = raw
    return sources


def compiled_state(directory, name, raw):
    """How Ren'Py treats the sibling .rpyc of a loose .rpy (MD5 digest rule)."""
    path = Path(directory).joinpath(*(name + "c").split("/"))
    try:
        compiled = workspace_io.read_bounded(path, rpyc.MAX_FILE)
    except (ValueError, OSError):
        return "no-loose-rpyc"
    return "rpyc-matches-source" if compiled[-16:] == hashlib.md5(raw).digest() else "source-newer-than-rpyc"


def extract(directory, output, *, speakers=()):
    directory, output = Path(directory), Path(output)
    validate_new_tree_destination(output)
    sources = load(directory)
    aliases, names = collect(sources, speakers)
    entries = [(workspace_io.LOOSE, rpa.Entry(n, raw, 0, 0)) for n, raw in sources.items()]
    mapping = workspace_io.json_names(entries, ".rpy")
    files = {"gt_output/.keep": b""}
    report = {"engine": "renpy", "mode": "rpy", "profile": PROFILE, "source_directory": str(directory),
              "script_encoding": "UTF-8 .rpy source", "json_encoding": "utf-8", "speakers": aliases,
              "extra_speakers": sorted(speakers), "names": names, "members": [], "rows": 0, "json_files": 0,
              "scripts": 0, "runtime_verified": False, "name_policy": "context-only",
              "scope": "say/narration, menu captions, translate strings new; Character names, Python, screens excluded",
              "loader": workspace_io.loader_hints(directory)}
    unknown = Counter()
    for name, raw in sources.items():
        rows, manifest, diagnostics, _, bom = export(name, raw, aliases, names)
        files[f"original/rpy/{name}"] = raw
        detail = {"name": name, "size": len(raw), "sha256": sha256(raw), "bom": bom, "count": len(rows),
                  "language": workspace_io.language(name), "identity_verified": True,
                  "compiled": compiled_state(directory, name, raw), "status": "exported" if rows else "empty"}
        if diagnostics:
            detail["skipped_say_like_lines"] = [{"line": n, "kind": k, "word": w} for n, k, w in diagnostics[:50]]
            unknown.update(w for _, _, w in diagnostics)
        if rows:
            filename = mapping[workspace_io.LOOSE, name]
            files[f"gt_input/{filename}"] = dump_rows(rows)
            files[f"metadata/{filename}"] = workspace_io.json_bytes(manifest)
            detail["outputs"] = {"json": filename}
            report["rows"] += len(rows)
            report["json_files"] += 1
        report["members"].append(detail)
        report["scripts"] += 1
    report["identity_verified"] = report["scripts"]
    report["empty_scripts"] = sum(m["status"] == "empty" for m in report["members"])
    if unknown:
        sample = ", ".join(f"{k}×{v}" for k, v in unknown.most_common(8))
        report["warnings"] = [f"say-like lines skipped for undeclared speakers or say arguments: {sample}. "
                              "Verify they are Character variables, then rerun with --speakers."]
        print(f"WARNING: {report['warnings'][0]}", file=sys.stderr, flush=True)
    files["reports/extraction.json"] = workspace_io.json_bytes(report)
    files["README.txt"] = ("Ren'Py .rpy 源码工作区\n\n"
        "gt_input：平铺 UTF-8 JSON；译文按同名文件放回 gt_output 后告诉 agent，由 agent 回写。\n"
        "name 是只读人物上下文；Character 名称、Python、screen 字符串不在本工作区。\n"
        "回写输出 loose/game/<相对路径>.rpy。改写后的 .rpy 与旧 .rpyc 末尾 MD5 不符，Ren'Py 下次启动会重新编译源码；\n"
        "改写原文同时会改变对白的 translate identifier，已有 tl/<语言> 中对应句会失配。\n"
        "未启动游戏、未覆盖原游戏文件。\n").encode("utf-8")
    write_new_tree(output, list(files.items()))
    return report


def pack(workspace, output):
    workspace, output = Path(workspace), Path(output)
    validate_new_tree_destination(output)
    report = load_json(workspace_io.read_bounded(workspace / "reports/extraction.json"))
    if report.get("engine") != "renpy" or report.get("profile") != PROFILE:
        raise ValueError("unsupported Ren'Py .rpy workspace profile")
    sources = {}
    for member in report["members"]:
        raw = workspace_io.read_bounded(workspace.joinpath("original", "rpy", *member["name"].split("/")), rpyc.MAX_FILE)
        if len(raw) != member["size"] or sha256(raw) != member["sha256"]:
            raise ValueError(f"Ren'Py source .rpy hash/size changed: {member['name']}")
        sources[member["name"]] = raw
    aliases, names = collect(sources, report["extra_speakers"])
    if aliases != report["speakers"] or names != report["names"]:
        raise ValueError("Ren'Py speaker context changed")
    entries = [(workspace_io.LOOSE, rpa.Entry(n, raw, 0, 0)) for n, raw in sources.items()]
    mapping = workspace_io.json_names(entries, ".rpy")
    expected = {m["outputs"]["json"] for m in report["members"] if m["status"] == "exported"}
    available = workspace_io._gt_output(workspace, expected)
    files, errors, changed, verified = {}, [], [], 0
    for name, raw in sources.items():
        rows, manifest, _, text, bom = export(name, raw, aliases, names)
        if not rows:
            continue
        filename = mapping[workspace_io.LOOSE, name]
        if load_json(workspace_io.read_bounded(workspace / "gt_input" / filename)) != rows:
            raise ValueError(f"gt_input changed: {filename}; preserve edits in gt_output then restore from original")
        if load_json(workspace_io.read_bounded(workspace / "metadata" / filename)) != manifest:
            raise ValueError(f"Ren'Py member manifest changed: {filename}")
        if filename not in available:
            continue
        translated = load_json(workspace_io.read_bounded(workspace / "gt_output" / filename))
        try:
            translated = validate_translation(manifest, {name: raw}, rows, translated)
        except ValueError as exc:
            errors.append(f"{filename}: {exc}")
            continue
        replacements, bad = {}, False
        for index, (before, after, record) in enumerate(zip(rows, translated, manifest["records"])):
            if before["message"] == after["message"]:
                continue
            reason = rpyc.row_error(before["message"], after["message"])
            if reason is None:
                try:
                    (renpy.encode_python if record["locator"]["syntax"] == "python" else renpy.encode_say)(after["message"])
                except ValueError as exc:
                    reason = str(exc)
            if reason:
                errors.append(f"{filename} #{index}: {reason}")
                bad = True
            replacements[record["locator"]["target"]] = after["message"]
        if bad:
            continue
        verified += 1
        patched = renpy.patch(text, replacements, filename=name, speakers=aliases)
        data = encode(patched, bom)
        check_rows = export_rows_only(name, data, aliases, names)
        if check_rows != translated:
            raise ValueError(f"{filename}: rpy read-back differs")
        if data != raw:
            files[f"loose/game/{name}"] = data
            changed.append({"name": name, "json": filename, "source_sha256": sha256(raw), "output_sha256": sha256(data),
                            "changed_rows": len(replacements)})
    if errors:
        raise rpyc.TranslationErrors(errors)
    result = {"engine": "renpy", "profile": PROFILE, "verified_json": verified, "changed": changed,
              "runtime_verified": False,
              "deployment": "Replace game/<path>.rpy in a backed-up game copy; Ren'Py recompiles it because the "
                            "old .rpyc digest no longer matches. Keep the game directory writable."}
    files["reports/pack.json"] = workspace_io.json_bytes(result)
    files["README.txt"] = ("Ren'Py .rpy 回写结果\n\n"
        "loose/game：改写后的 .rpy，保留 game/ 下相对路径。在游戏副本备份后覆盖同名文件。\n"
        "旧 .rpyc 不必删除：其末尾 MD5 与新源码不符，Ren'Py 会改用 .rpy 并在可写时重新生成 .rpyc。\n"
        "若同一脚本的 .rpyc 在归档内，松散 .rpy 与归档 .rpyc 会同时加载，部署前须先确认只有一份。\n"
        "已重新解析校验；未启动游戏。\n").encode("utf-8")
    write_new_tree(output, list(files.items()))
    return result


def export_rows_only(name, raw, speakers, names):
    text, _ = decode(raw)
    rows = []
    for target in renpy.extract(text, filename=name, speakers=speakers):
        if target.role == "name" or not target.text:
            continue
        display = speaker_name(target.speaker, names)
        rows.append({"name": display, "message": target.text} if display else {"message": target.text})
    return rows


def speaker_name(speaker, names):
    if speaker and speaker[0] in "\"'":
        return renpy.python_value(renpy._lex(speaker)[0])
    return names.get(speaker)
