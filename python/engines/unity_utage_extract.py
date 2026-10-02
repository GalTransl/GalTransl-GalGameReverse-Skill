# SPDX-License-Identifier: GPL-3.0-only
"""Extract/repack Utage books in stripped Unity serialized v20 assets.

Dependencies are explicit serialized assets containing MonoScript metadata,
never assemblies. All output is published to a new directory only.
"""
import argparse
from collections import Counter
import io
import json
from pathlib import Path
import re
import unicodedata

from ..archives import unity_serialized as archive
from ..common.binary import FormatError
from ..common.contract import dump_rows, load_json, sha256
from ..common.safety import _check_existing_ancestors, logical_path, validate_names, write_new_tree
from . import unity_utage as script


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def bounded(path, limit=32 << 20):
    with archive.open_checked(path) as stream:
        stream.seek(0, 2)
        size = stream.tell()
        if size > limit:
            raise FormatError("Unity workspace input exceeds budget")
        stream.seek(0)
        raw = stream.read(limit + 1)
    if len(raw) != size:
        raise FormatError("Unity workspace input changed size")
    return raw


def flat(name):
    if logical_path(name) != name or "/" in name:
        raise FormatError("expected a flat Unity asset filename")
    return name


def filename(name, path_id, grid, used):
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name.rsplit(":", 1)[-1]).strip(" .")[:140] or "sheet"
    try:
        logical_path(stem + ".json")
    except FormatError:
        stem = "_" + stem
    candidate = stem + ".json"
    key = lambda s: unicodedata.normalize("NFC", s).casefold()
    if key(candidate) in used:
        candidate = f"{stem}__p{path_id}_g{grid}.json"
    if key(candidate) in used:
        raise FormatError("ambiguous Utage output filename")
    used.add(key(candidate))
    return candidate


def inventory(data, dependencies):
    index = archive.read_index(io.BytesIO(data))
    if len(dependencies) > 16 or sum(map(len, dependencies.values())) + len(data) > 192 << 20:
        raise FormatError("Unity dependency budget exceeded")
    scripts = {}
    for name, raw in [("", data), *dependencies.items()]:
        ix = archive.read_index(io.BytesIO(raw))
        scripts[name] = {o.path_id: script.mono_script(raw[o.offset:o.offset + o.size])
                         for o in ix.objects if o.class_id == 115 and o.size <= archive.MAX_OBJECT}
    books, chapters, diagnostics = {}, [], Counter()
    for obj in index.objects:
        if obj.class_id != 114:
            continue
        prefix = data[obj.offset:obj.offset + min(obj.size, 8192)]
        _, name, (file_id, path_id) = script.behaviour(script.Reader(prefix))
        if file_id == 0:
            dependency = ""
        elif 1 <= file_id <= len(index.externals):
            # Only explicit metadata inputs can be resolved; never open a path
            # supplied by untrusted serialized metadata.
            dependency = index.externals[file_id - 1].replace("\\", "/").rsplit("/", 1)[-1]
        else:
            raise FormatError("MonoBehaviour script file ID outside external table")
        cls = scripts.get(dependency, {}).get(path_id)
        if cls is None:
            diagnostics["unresolved_monoscripts"] += 1
            if name.endswith((".book", ".chapter")):
                raise FormatError(f"missing explicit MonoScript metadata for Utage candidate {name!r}")
            continue
        if cls["namespace"] != "Utage" or cls["class"] not in ("AdvImportBook", "AdvChapterData"):
            continue
        raw = archive.read_object(io.BytesIO(data), obj)
        if cls["class"] == "AdvImportBook":
            books[obj.path_id] = (raw, script.read_book(raw))
        else:
            chapters.append(script.read_chapter(raw))
    if not books:
        raise FormatError("no class-verified Utage AdvImportBook in source asset")
    names = script.character_names(chapters)
    members, exports, used = [], {}, set()
    for path_id, (_, book) in books.items():
        for item in script.export_book(book, names):
            name = filename(item["name"], path_id, item["grid"], used) if item["rows"] else None
            info = {"path_id": path_id, "book": book.name, "grid": item["grid"], "name": item["name"],
                    "json": name, "rows": len(item["rows"]), "locations": item["locations"],
                    "excluded_text_cells": item["excluded_text_cells"],
                    "status": "exported" if name else "no-display-text"}
            members.append(info)
            if name:
                exports[name] = item["rows"]
    diagnostics["chapter_objects"] = len(chapters)
    diagnostics["character_keys"] = len(names)
    diagnostics["readonly_setting_cache_mismatches"] = sum(g.text_length != script.units(g)
        for chapter in chapters for g in chapter.settings)
    return index, books, names, members, exports, dict(diagnostics)


def extract(source, output, *, dependencies=(), target=None):
    source, output = Path(source), Path(output)
    if output.exists():
        raise FileExistsError(output)
    flat(source.name)
    target = logical_path(target or source.name)
    data, _ = archive.read_file(source)
    dep = {}
    for path in dependencies:
        path = Path(path)
        flat(path.name)
        validate_names([*dep, path.name])
        if len(dep) >= 16:
            raise FormatError("too many Unity metadata dependencies")
        if len(data) + sum(map(len, dep.values())) + path.stat().st_size > 192 << 20:
            raise FormatError("Unity dependency budget exceeded")
        dep[path.name] = archive.read_file(path)[0]
    index, books, names, members, exports, diagnostics = inventory(data, dep)
    files = {"original/" + source.name: data, "gt_output/.keep": b""}
    files.update({"original/dependencies/" + name: raw for name, raw in dep.items()})
    replacements = {}
    for path_id, (raw, book) in books.items():
        rewritten = script.write_book(book)
        if rewritten != raw:
            raise FormatError("Utage original book writer is not byte-identical")
        replacements[path_id] = rewritten
    rebuilt = archive.rebuild(data, replacements)
    if rebuilt != data:
        raise FormatError("Unity original serialized writer is not byte-identical")
    files["rebuilt/roundtrip/" + target] = rebuilt
    for member in members:
        if member["json"]:
            name = member["json"]
            files["gt_input/" + name] = dump_rows(exports[name])
            files["metadata/" + name] = json_bytes(member)
    report = {"engine": "unity-utage", "profile": script.PROFILE,
              "source": str(source), "source_name": source.name, "source_sha256": sha256(data),
              "source_size": len(data), "target": target, "unity_version": index.unity_version,
              "dependencies": [{"name": name, "sha256": sha256(raw)} for name, raw in dep.items()],
              "encoding": "utf-8", "serialized_version": 20, "object_count": len(index.objects),
              "book_count": len(books), "grid_count": len(members), "json_files": len(exports),
              "rows": sum(len(rows) for rows in exports.values()),
              "roles": dict(Counter(loc["role"] for m in members for loc in m["locations"])),
              "members": members, "diagnostics": diagnostics,
              "name_policy": "context-only", "identity_verified": True, "runtime_verified": False}
    files["reports/extraction.json"] = json_bytes(report)
    files["README.txt"] = (
        "Unity / Utage 剧情工作区\n\n"
        "gt_input：平铺 UTF-8 JSON；只含有文本的剧本表。\n"
        "gt_output：译文按同名放回后告诉 agent，由 agent 校验、回写和打包。\n"
        "当前只回写 message；name 是只读上下文，保留原样，避免改坏角色资源键。\n"
        "保留条数、顺序、换行、富文本标签和变量（包括 ruby 标签的参数）。\n"
        "original 与 metadata 不要修改；误改 gt_input 先让 agent 保存修改再恢复。\n"
        "rebuilt/roundtrip 是经实际 writer 重建并逐字节核对的原文归档。\n"
        "源文件名与实际部署文件名可以不同，目标相对路径见 extraction.json 的 target。\n"
        "未提取任意 UI 或设置表，未保证所有剧情表都在游戏中可达。\n"
        "正文为 UTF-8，不使用 CP932/JIS 替换；缺字时检查 Unity 字体及回退字体。\n"
        "未覆盖游戏、未运行游戏；先用少量中文测试加载与显示。\n").encode("utf-8")
    write_new_tree(output, list(files.items()))
    return report


def pack(workspace, output):
    workspace, output = Path(workspace), Path(output)
    if output.exists():
        raise FileExistsError(output)
    report = load_json(bounded(workspace / "reports/extraction.json"))
    if report.get("engine") != "unity-utage" or report.get("profile") != script.PROFILE:
        raise FormatError("unsupported Unity workspace")
    source_name, target = flat(report["source_name"]), logical_path(report["target"])
    raw, _ = archive.read_file(workspace / "original" / source_name)
    if len(raw) != report["source_size"] or sha256(raw) != report["source_sha256"]:
        raise FormatError("Unity original asset hash/size differs")
    dependencies = report["dependencies"]
    if not isinstance(dependencies, list) or len(dependencies) > 16:
        raise FormatError("Unity dependencies exceed budget")
    validate_names([flat(d["name"]) for d in dependencies])
    dep = {}
    for d in dependencies:
        path = workspace / "original/dependencies" / d["name"]
        if len(raw) + sum(map(len, dep.values())) + path.stat().st_size > 192 << 20:
            raise FormatError("Unity dependency budget exceeded")
        dep[d["name"]] = archive.read_file(path)[0]
        if sha256(dep[d["name"]]) != d["sha256"]:
            raise FormatError("Unity metadata dependency hash differs")
    index, books, names, members, exports, _ = inventory(raw, dep)
    if members != report["members"]:
        raise FormatError("Unity workspace inventory differs from original")
    _check_existing_ancestors(workspace / "gt_output")
    available = set()
    for n, path in enumerate((workspace / "gt_output").iterdir()):
        if n >= 100000:
            raise FormatError("Unity translation directory exceeds budget")
        if path.suffix.lower() == ".json":
            available.add(path.name)
    validate_names(list(available))
    by_book = {pid: {} for pid in books}
    expected_rows, translated = {}, []
    total = 0
    for member in members:
        name = member["json"]
        if not name:
            continue
        rows = exports[name]
        if (load_json(bounded(workspace / "gt_input" / name)) != rows
                or load_json(bounded(workspace / "metadata" / name)) != member):
            raise FormatError(f"Unity original JSON/manifest changed: {name}")
        if name in available:
            translation = bounded(workspace / "gt_output" / name)
            total += len(translation)
            if total > 128 << 20:
                raise FormatError("Unity translations exceed total budget")
            rows = load_json(translation)
            translated.append(name)
        by_book[member["path_id"]][member["grid"]] = rows
        expected_rows[name] = rows
    replacements = {pid: script.patch_book(data, by_book[pid], names) for pid, (data, _) in books.items()}
    rebuilt = archive.rebuild(raw, replacements)
    # Read actual file offsets, then compare semantic exports to submitted rows.
    _, _, _, after_members, after_rows, _ = inventory(rebuilt, dep)
    if after_members != members or after_rows != expected_rows:
        raise FormatError("Unity repacked text/locators differ from expected rows")
    changed = [pid for pid, (data, _) in books.items() if replacements[pid] != data]
    result = {"engine": "unity-utage", "profile": script.PROFILE, "target": target,
              "sha256": sha256(rebuilt), "source_sha256": sha256(raw), "size": len(rebuilt),
              "changed_objects": changed, "translated_files": translated,
              "unmatched_translation_files": sorted(available - exports.keys()),
              "verified_objects": len(index.objects), "verified_json_files": len(after_rows),
              "encoding": "utf-8", "runtime_verified": False}
    files = {"files/" + target: rebuilt, "reports/rebuild.json": json_bytes(result)}
    files.update({"readback/gt_input/" + name: dump_rows(rows) for name, rows in after_rows.items()})
    files["README.txt"] = (
        "Unity / Utage 回写结果\n"
        "files/ 内路径相对于游戏目录；这是完整 serialized asset，不是增量 patch 包。\n"
        "已重新解析核对文本、所有对象、非文本结构和偏移。游戏加载与字体显示尚未验证。\n"
        "手动部署前另存游戏中当前文件；不要覆盖日文备份。配套 resS/resource 保持原样。\n"
        "UTF-8 直接回写，缺字需检查 Unity 字体/回退字体或图集覆盖，不需 JIS hook。\n").encode("utf-8")
    write_new_tree(output, list(files.items()))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("extract")
    p.add_argument("source")
    p.add_argument("output")
    p.add_argument("--dependency", action="append", default=[], dest="dependencies")
    p.add_argument("--target", help="deployment path relative to game root; source filename may differ")
    p = commands.add_parser("pack")
    p.add_argument("workspace")
    p.add_argument("output")
    args = vars(parser.parse_args())
    action = args.pop("command")
    result = extract(**args) if action == "extract" else pack(**args)
    print(json.dumps({k: v for k, v in result.items() if k != "members"}, ensure_ascii=True))


if __name__ == "__main__":
    main()
