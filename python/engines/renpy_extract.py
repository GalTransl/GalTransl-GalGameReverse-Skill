"""Bounded RPA/ARC3 + RPYC2 workspace extraction and archive rebuilding.

Never imports game modules, runs a game, or unpickles executable objects.
CLI writes only new directories. Source .rpy lexing remains in renpy.py.
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import stat

from ..archives import rpa
from ..common.contract import dump_rows, load_json, sha256
from ..common.safety import _check_existing_ancestors, validate_names, write_new_tree
from . import renpy_rpyc as rpyc
from .renpy_pickle import attributes, class_name, scalar

MAX_ARCHIVE = 64 << 20
MAX_TOTAL = 128 << 20


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def read_bounded(path, limit=MAX_ARCHIVE):
    path = Path(path)
    _check_existing_ancestors(path.parent)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or getattr(info, "st_file_attributes", 0) & 0x400:
        raise ValueError(f"not an ordinary, unlinked input file: {path}")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError(f"Ren'Py input exceeds budget: {path}")
    return raw


def flat_names(names):
    if validate_names(names) != names or any("/" in n or "\\" in n for n in names):
        raise ValueError("expected unique flat Ren'Py filenames")


def scan(directory):
    """Read archive headers/indexes only; never load media payloads."""
    directory = Path(directory)
    _check_existing_ancestors(directory)
    result = []
    paths = sorted(p for p in directory.iterdir() if p.suffix.lower() in (".rpa", ".arc"))
    if len(paths) > 256:
        raise ValueError("Ren'Py archive count exceeds budget")
    for path in paths:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError(f"unsafe archive path: {path}")
        try:
            with path.open("rb") as stream:
                index = rpa.read_index(stream, max_file_size=2 << 30, max_total_size=16 << 30, max_archive_size=16 << 30)
            validate_names([e.name for e in index.entries])
            result.append({"archive": path.name, "size": index.size, "magic": index.header[:7].decode("ascii"),
                           "members": len(index.entries), "scripts": [{"name": e.name, "size": e.length}
                            for e in index.entries if e.name.lower().endswith((".rpyc", ".rpy", ".rpymc", ".rpym"))]})
        except ValueError as exc:
            result.append({"archive": path.name, "status": "unsupported", "error": str(exc)})
    return result


def load_archives(directory, names):
    flat_names(names)
    if not 1 <= len(names) <= 64:
        raise ValueError("Ren'Py selected archive count outside budget")
    archives, entries, total = {}, [], 0
    for name in names:
        raw = read_bounded(Path(directory) / name)
        total += len(raw)
        if total > MAX_TOTAL:
            raise ValueError("Ren'Py selected archive total exceeds budget")
        archives[name] = raw
        members = rpa.extract(raw, max_archive_size=MAX_ARCHIVE, max_total_size=MAX_ARCHIVE)
        validate_names([e.name for e in members])
        entries.extend((name, e) for e in members)
    # Avoid silently combining competing archive overrides or .rpy sources.
    compiled = [e.name for _, e in entries if e.name.lower().endswith(".rpyc")]
    if not compiled or len(compiled) > 4096:
        raise ValueError("Ren'Py compiled script count outside budget")
    validate_names(compiled)
    lowered = {e.name.casefold() for _, e in entries}
    if any(n[:-1].casefold() in lowered for n in compiled):
        raise ValueError("matching .rpy source may override RPYC: select the source-text workflow")
    return archives, entries


def context(entries):
    candidates, translations = defaultdict(set), defaultdict(lambda: defaultdict(set))
    for archive, entry in entries:
        if not entry.name.lower().endswith(".rpyc"):
            continue
        try:
            script = rpyc.parse(entry.data)
            for key, name in rpyc.character_names(script.slots[1]).items():
                candidates[key].add(name)
            for value in script.slots[1].objects:
                if class_name(value) == ("renpy.ast", "TranslateString"):
                    attrs = attributes(value)
                    lang, old, new = (scalar(attrs.get(k)) for k in ("language", "old", "new"))
                    if isinstance(lang, str) and isinstance(old, str) and isinstance(new, str):
                        translations[lang][old].add(new)
        except ValueError as exc:
            raise ValueError(f"RPYC {archive}:{entry.name}: {exc}") from exc
    names = {key: next(iter(values)) for key, values in candidates.items() if len(values) == 1}
    return {"base": names, "languages": {lang: {key: next(iter(values)) for key, values in strings.items() if len(values) == 1}
                                          for lang, strings in translations.items()},
            "ambiguous_characters": sorted(key for key, values in candidates.items() if len(values) != 1)}


def language(name):
    parts = name.split("/")
    return parts[1] if len(parts) > 2 and parts[0] == "tl" else "original"


def names_for(name, ctx):
    strings = ctx["languages"].get(language(name), {})
    return {key: strings.get(value, value) for key, value in ctx["base"].items()}


def json_names(entries):
    scripts = [(a, e.name) for a, e in entries if e.name.lower().endswith(".rpyc")]
    stems = Counter(Path(n).stem.casefold() for _, n in scripts)
    counts, result = Counter(), {}
    for archive, name in scripts:
        stem = Path(name).stem
        if stems[stem.casefold()] > 1:
            stem += "__" + Path(archive).stem
        counts[stem.casefold()] += 1
        suffix = "" if counts[stem.casefold()] == 1 else f"_{counts[stem.casefold()]}"
        result[archive, name] = stem + suffix + ".json"
    flat_names(list(result.values()))
    return result


def extract(directory, output, *, archives, smoke_test=False):
    directory, output = Path(directory), Path(output)
    if output.exists():
        raise FileExistsError(output)
    sources, entries = load_archives(directory, list(archives))
    print(f"Reading character/translation context from {sum(e.name.endswith('.rpyc') for _, e in entries)} RPYC files", flush=True)
    ctx = context(entries)
    mapping = json_names(entries)
    files = {"gt_output/.keep": b"", "metadata/context.json": json_bytes(ctx)}
    report = {"engine": "renpy", "profile": rpyc.PROFILE, "source_directory": str(directory),
              "script_encoding": "Unicode strings serialized as UTF-8 in Pickle", "json_encoding": "utf-8",
              "archives": [], "members": [], "rows": 0, "json_files": 0, "scripts": 0,
              "runtime_verified": False, "growth_tests": [], "name_policy": "context-only",
              "scope": "Say/TranslateSay.what, Menu.items labels, TranslateString.new; Python/screen/ATL strings excluded"}
    growth_members = defaultdict(dict)
    for archive, raw in sources.items():
        files[f"original/archives/{archive}"] = raw
        original = rpa.rebuild(raw, {})
        if original != raw:
            raise ValueError(f"RPA identity roundtrip differs: {archive}")
        files[f"rebuilt/roundtrip/game/{archive}"] = original
        report["archives"].append({"name": archive, "size": len(raw), "sha256": sha256(raw),
                                   "magic": raw[:7].decode("ascii"), "identity_verified": True})
    for archive, entry in entries:
        detail = {"archive": archive, "name": entry.name, "size": len(entry.data), "sha256": sha256(entry.data)}
        report["members"].append(detail)
        if not entry.name.lower().endswith(".rpyc"):
            detail["status"] = "preserved-non-rpyc"
            continue
        try:
            script = rpyc.parse(entry.data)
            names = names_for(entry.name, ctx)
            rows, manifest = rpyc.export(script, filename=entry.name, names=names)
            original = rpyc.patch(script, rows, manifest, filename=entry.name, names=names)
            if original != entry.data:
                raise ValueError("RPYC identity bytes differ")
            files[f"original/scripts/{archive}/{entry.name}"] = entry.data
            detail.update(status="exported" if rows else "empty", count=len(rows), language=language(entry.name),
                          roles=dict(Counter(r["locator"]["role"] for r in manifest["records"])),
                          identity_verified=True, slots=sorted(script.slots))
            report["scripts"] += 1
            if rows:
                filename = mapping[archive, entry.name]
                files[f"gt_input/{filename}"] = dump_rows(rows)
                files[f"metadata/{filename}"] = json_bytes(manifest)
                detail["outputs"] = {"json": filename}
                report["rows"] += len(rows)
                report["json_files"] += 1
                if smoke_test:
                    changed = [dict(row) for row in rows]
                    changed[0]["message"] += " 这是中文显示与长度增长测试。"
                    modified = rpyc.patch(script, changed, manifest, filename=entry.name, names=names)
                    growth_members[archive][entry.name] = modified
                    report["growth_tests"].append({"archive": archive, "name": entry.name, "json": filename,
                        "row": 0, "suffix": " 这是中文显示与长度增长测试。", "compressed_delta": len(modified) - len(entry.data),
                        "slots_verified": sorted(script.slots), "nontext_graph_verified": True})
            print(f"Verified {report['scripts']} RPYC: {archive}:{entry.name}, {len(rows)} rows", flush=True)
        except ValueError as exc:
            raise ValueError(f"RPYC {archive}:{entry.name}: {exc}") from exc
    for archive, replacements in growth_members.items():
        files[f"rebuilt/growth-test/game/{archive}"] = rpa.rebuild(sources[archive], replacements)
    report["identity_verified"] = report["scripts"]
    report["empty_scripts"] = sum(m["status"] == "empty" for m in report["members"])
    files["reports/extraction.json"] = json_bytes(report)
    files["README.txt"] = ("Ren'Py RPYC2 提取结果\n\n"
        "gt_input：平铺 UTF-8 JSON；同名跨语言脚本以归档名后缀区分，映射见 reports/extraction.json。\n"
        "gt_output：译文按同名文件放回后告诉 agent，由 agent 校验并回包，无需手动执行命令。\n"
        "name 仅是只读人物上下文；不要翻译变量 ID，也不要改动它。保留行数、顺序和文本控制码。\n"
        "提取对白、菜单、翻译表 new；不扫描 Python、screen、ATL 中的任意字符串。\n"
        "原始语言和 tl/<语言> 是不同套文本；要测试哪种语言，就编辑对应 JSON 并在游戏选择该语言。\n"
        "original、metadata 不要修改；rebuilt/roundtrip 为经过读写且逐字节一致的归档。\n"
        "rebuilt/growth-test 若存在，是每个非空文件首行追加中文的离线测试，不是正式译文。\n"
        "pack 会输出 changed-archives/game 下同名完整归档及 loose/game 下对应编译脚本两种部署备选。\n"
        "优先在游戏副本备份后替换对应 game/ 同名归档；不要将其改名成未经证实会加载的 patch.rpa。\n"
        "松散脚本仅在确认该版本优先读取 loose 文件时使用，保留包内目录，避免旧 .rpy 覆盖。\n"
        "文字以 UTF-8 编码的 Unicode 存储，无需 JIS；缺字时检查游戏字体覆盖。\n"
        "所有验证均为离线读写，未启动游戏、未覆盖原游戏文件，实际加载与显示仍需用户确认。\n").encode("utf-8")
    write_new_tree(output, list(files.items()))
    return report


def pack(workspace, output):
    workspace, output = Path(workspace), Path(output)
    if output.exists():
        raise FileExistsError(output)
    report = load_json(read_bounded(workspace / "reports/extraction.json"))
    if report["engine"] != "renpy" or report["profile"] != rpyc.PROFILE:
        raise ValueError("unsupported Ren'Py workspace profile")
    archive_names = [a["name"] for a in report["archives"]]
    sources, entries = load_archives(workspace / "original/archives", archive_names)
    for a in report["archives"]:
        raw = sources[a["name"]]
        if len(raw) != a["size"] or sha256(raw) != a["sha256"]:
            raise ValueError("Ren'Py source archive hash/size changed")
    ctx = context(entries)
    if load_json(read_bounded(workspace / "metadata/context.json")) != ctx:
        raise ValueError("Ren'Py character context changed")
    mapping = json_names(entries)
    expected = {m["outputs"]["json"] for m in report["members"] if m["status"] == "exported"}
    flat_names(list(expected))
    _check_existing_ancestors(workspace / "gt_output")
    available = {p.name for p in (workspace / "gt_output").iterdir() if p.suffix.lower() == ".json"}
    if available - expected:
        raise ValueError(f"unmatched Ren'Py translation files: {sorted(available - expected)}")
    files, replacements, verified, changed = {}, defaultdict(dict), 0, []
    actual_expected = set()
    for archive, entry in entries:
        if not entry.name.lower().endswith(".rpyc"):
            continue
        script = rpyc.parse(entry.data)
        names = names_for(entry.name, ctx)
        original, manifest = rpyc.export(script, filename=entry.name, names=names)
        if not original:
            continue
        filename = mapping[archive, entry.name]
        actual_expected.add(filename)
        if load_json(read_bounded(workspace / "gt_input" / filename)) != original:
            raise ValueError(f"gt_input changed: {filename}; preserve edits in gt_output then restore from original archive")
        if load_json(read_bounded(workspace / "metadata" / filename)) != manifest:
            raise ValueError(f"Ren'Py member manifest changed: {filename}")
        if filename not in available:
            continue
        rows = load_json(read_bounded(workspace / "gt_output" / filename))
        modified = rpyc.patch(script, rows, manifest, filename=entry.name, names=names)
        verified += 1
        if modified != entry.data:
            replacements[archive][entry.name] = modified
            files[f"loose/game/{entry.name}"] = modified
            changed.append({"archive": archive, "name": entry.name, "json": filename,
                            "source_sha256": sha256(entry.data), "output_sha256": sha256(modified),
                            "changed_rows": sum(a != b for a, b in zip(original, rows))})
    if actual_expected != expected:
        raise ValueError("Ren'Py workspace export set differs from source")
    for archive, members in replacements.items():
        files[f"changed-archives/game/{archive}"] = rpa.rebuild(sources[archive], members)
    result = {"engine": "renpy", "profile": rpyc.PROFILE, "verified_json": verified,
              "changed": changed, "archives": list(replacements), "runtime_verified": False,
              "deployment": "Use same-name archives under game/ in a backed-up game copy; loose files require confirmed loader priority"}
    files["reports/pack.json"] = json_bytes(result)
    files["README.txt"] = ("Ren'Py 回包结果\n\n"
        "changed-archives/game：已重建的同名完整归档，包含未修改的其他成员。\n"
        "loose/game：只含改动的 RPYC，保留原路径；仅供已确认松散覆盖规则的版本使用。\n"
        "两种方式择一。先在游戏副本备份原文件，再按 game/ 对应位置部署。不要擅自改名为 patch.rpa。\n"
        "确保游戏语言与编辑的 original/tl 语言一致，检查同名 .rpy/旧补丁是否覆盖。\n"
        "已完成双槽文本、非文本对象图与归档重新解析验证；未执行游戏。\n"
        "UTF-8 无需 JIS。先检查少量中文、菜单与存读档；缺字时检查实际使用字体。\n").encode("utf-8")
    write_new_tree(output, list(files.items()))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    scan_parser = commands.add_parser("scan")
    scan_parser.add_argument("directory")
    extract_parser = commands.add_parser("extract")
    extract_parser.add_argument("directory")
    extract_parser.add_argument("output")
    extract_parser.add_argument("--archives", nargs="+", required=True)
    extract_parser.add_argument("--smoke-test", action="store_true")
    pack_parser = commands.add_parser("pack")
    pack_parser.add_argument("workspace")
    pack_parser.add_argument("output")
    args = parser.parse_args()
    if args.command == "scan":
        result = scan(args.directory)
    elif args.command == "extract":
        result = extract(args.directory, args.output, archives=args.archives, smoke_test=args.smoke_test)
        result = {k: result[k] for k in ("scripts", "json_files", "rows", "empty_scripts", "identity_verified", "runtime_verified")}
    else:
        result = pack(args.workspace, args.output)
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
