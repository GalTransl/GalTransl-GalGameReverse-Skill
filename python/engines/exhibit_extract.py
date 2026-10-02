"""Extract/rebuild loose ExHibit v3 RLDs into a new, self-contained workspace."""
import argparse
from collections import Counter
import json
from pathlib import Path
import stat

from ..common.contract import dump_rows, load_json, sha256
from ..common.jis_substitution import JisSubstitution
from ..common.safety import _check_existing_ancestors, validate_names, write_new_tree
from .exhibit_keys import PE, recover_def_seed, scenario_seed
from .exhibit_rld import MAX_FILE, PROFILE, crypt, export_rld, parse, rebuild_rld


def json_bytes(obj):
    return (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def read_bounded(path, limit=MAX_FILE):
    path = Path(path)
    _check_existing_ancestors(path.parent)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or getattr(info, "st_file_attributes", 0) & 0x400:
        raise ValueError(f"not an ordinary, unlinked input file: {path}")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError(f"input exceeds budget: {path}")
    return raw


def flat_names(names):
    if validate_names(names) != names or any("/" in name or "\\" in name for name in names):
        raise ValueError("RLD workspace requires unique flat filenames")


def _kwargs(name, sources, seeds):
    definitions = next((key for key in sources if key.casefold() == "defchara.rld"), None)
    kw = {"filename": name}
    if definitions and name != definitions:
        kw.update(definitions=sources[definitions], definition_seed=seeds[definitions])
    return kw


def extract(source, output, *, exe=None, ini=None, resident=None, scripts_dir=None,
            seed=None, def_seed=None, smoke_test=False):
    source, output = Path(source), Path(output)
    if output.exists():
        raise FileExistsError(output)
    directory = Path(scripts_dir) if scripts_dir else source / "rld"
    _check_existing_ancestors(directory)
    paths = sorted((p for p in directory.iterdir() if p.suffix.lower() == ".rld"), key=lambda p: p.name.casefold())
    if not 1 <= len(paths) <= 4096:
        raise ValueError("RLD member count outside budget")
    flat_names([p.name for p in paths])
    sources, total = {}, 0
    for path in paths:
        raw = read_bounded(path)
        total += len(raw)
        if total > 64 << 20:
            raise ValueError("RLD source total exceeds 64 MiB budget")
        sources[path.name] = raw
    recovery = {"scenario": {"method": "explicit-seed"}, "machine": None}
    evidence = {}
    if exe is not None:
        exe_raw = read_bounded(exe, 128 << 20)
        recovery["machine"] = PE(exe_raw).machine
        evidence["exe"] = {"path": str(exe), "sha256": sha256(exe_raw)}
    if seed is None:
        try:
            for name, raw in sources.items():
                if name.casefold() != "def.rld":
                    parse(raw)
            seed = 0
            recovery["scenario"] = {"method": "plaintext-full-parse"}
        except ValueError:
            if exe is None:
                raise ValueError("encrypted RLD: provide --exe for bitmap/INI recovery or --seed") from None
            ini_path = Path(ini) if ini else source / "ExHIBIT.ini"
            ini_raw = read_bounded(ini_path, 1 << 20)
            seed, detail = scenario_seed(exe_raw, ini_raw)
            recovery["scenario"] = detail
            evidence["ini"] = {"path": str(ini_path), "sha256": sha256(ini_raw)}
    definition = next((name for name in sources if name.casefold() == "def.rld"), None)
    if definition and def_seed is None:
        try:
            parse(sources[definition])
            def_seed = 0
            recovery["def"] = {"method": "plaintext-full-parse"}
        except ValueError:
            resident_path = Path(resident) if resident else source / "resident.dll"
            resident_raw = read_bounded(resident_path, 128 << 20)
            def_seed, detail = recover_def_seed(resident_raw, sources[definition])
            recovery["def"] = detail
            evidence["resident"] = {"path": str(resident_path), "sha256": sha256(resident_raw)}
    elif definition:
        recovery["def"] = {"method": "explicit-seed"}
    seeds = {name: def_seed if name == definition else seed for name in sources}
    flat_names([Path(name).stem + ".json" for name in sources])
    files = {"gt_output/.keep": b""}
    if "ini_raw" in locals():
        files["original/ExHIBIT.ini"] = ini_raw
    entries, row_count, json_count, growth = [], 0, 0, []
    unknown_names = Counter()
    for name, raw in sources.items():
        try:
            kw = _kwargs(name, sources, seeds)
            rows, manifest = export_rld(raw, seeds[name], **kw)
            rebuilt = rebuild_rld(raw, seeds[name], rows, manifest, **kw)
            if rebuilt != raw:
                raise ValueError("no-edit encrypted bytes differ")
            plain = crypt(raw, seeds[name])
            script = parse(plain)
            filename = Path(name).stem + ".json"
            choices = sum(r["locator"]["kind"] == "choice" for r in manifest["records"])
            entry = {"name": name, "seed": seeds[name], "sha256": sha256(raw), "size": len(raw),
                     "commands": len(script.ops), "opcodes": dict(Counter(str(op.opcode) for op in script.ops)),
                     "count": len(rows), "choices": choices, "status": "exported" if rows else "empty",
                     "outputs": {"json": filename} if rows else {}}
            entries.append(entry)
            files[f"original/encrypted/{name}"] = raw
            files[f"original/rld/{name}"] = plain
            files[f"rebuilt/roundtrip/rld/{name}"] = rebuilt
            for row, record in zip(rows, manifest["records"]):
                if record["locator"].get("name_id") is not None and "name" not in row:
                    unknown_names[str(record["locator"]["name_id"])] += 1
            if rows:
                files[f"gt_input/{filename}"] = dump_rows(rows)
                files[f"metadata/{filename}"] = json_bytes(manifest)
                row_count += len(rows)
                json_count += 1
                if smoke_test:
                    changed = [dict(r) for r in rows]
                    changed[0]["message"] += " ABC"
                    modified = rebuild_rld(raw, seeds[name], changed, manifest, **kw)
                    files[f"rebuilt/growth-test/rld/{name}"] = modified
                    growth.append({"name": name, "row": 0, "suffix": " ABC", "size_delta": len(modified) - len(raw)})
        except (ValueError, UnicodeError) as exc:
            raise ValueError(f"RLD {name}: {exc}") from exc
    report = {"engine": "exhibit", "profile": PROFILE, "source_directory": str(directory),
              "script_encoding": "cp932", "json_encoding": "utf-8", "members": entries,
              "rows": row_count, "json_files": json_count, "choices": sum(e["choices"] for e in entries),
              "unresolved_name_ids": dict(unknown_names), "identity_verified": len(entries),
              "growth_tests": growth, "keys": recovery, "key_evidence": evidence,
              "runtime_verified": False, "text_scope": "op28 dialogue; op21 TAB/1010 choices; other strings preserved"}
    files["reports/extraction.json"] = json_bytes(report)
    files["README.txt"] = ("ExHibit RLD 提取结果\n\n"
        "gt_input：UTF-8 翻译输入，保留全部行与顺序；姓名位于正文上方。\n"
        "gt_output：译文按同名文件放回后告诉 agent，由 agent 校验、回写到新目录。\n"
        "metadata：间接姓名为只读上下文，不翻译 name；未解析姓名 ID 保留在元数据。\n"
        "original/encrypted：原始加密脚本；original/rld：完整解密脚本。均不要修改。\n"
        "rebuilt/roundtrip：经过完整读写并逐字节一致的脚本。\n"
        "rebuilt/growth-test：若存在，仅为增加 ABC 的离线增长测试，不能当正式译文。\n"
        "reports/extraction.json：范围、哈希、密钥恢复方式、未解析姓名与验证状态。\n"
        "部署时按原 rld/ 路径替换选中的副本；本工具不会修改游戏或执行游戏。\n"
        "CP932 中文回注默认优先使用 JIS 替换，生成匹配配置与兼容时的 x86 hook；\n"
        "先试注少量中文，确认加载、字体和显示后再批量翻译。\n").encode("utf-8")
    write_new_tree(output, list(files.items()))
    return report


def rebuild(workspace, output, *, jis_mode="auto"):
    workspace = Path(workspace)
    report = load_json(read_bounded(workspace / "reports/extraction.json"))
    if report["engine"] != "exhibit" or report["profile"] != PROFILE:
        raise ValueError("unsupported ExHibit workspace profile")
    members = report["members"]
    flat_names([e["name"] for e in members])
    if not 1 <= len(members) <= 4096:
        raise ValueError("RLD workspace count outside budget")
    sources, seeds, total = {}, {}, 0
    for entry in members:
        name = entry["name"]
        raw = read_bounded(workspace / "original/encrypted" / name)
        total += len(raw)
        if total > 64 << 20 or len(raw) != entry["size"] or sha256(raw) != entry["sha256"]:
            raise ValueError("RLD source hash/size/budget mismatch")
        sources[name], seeds[name] = raw, entry["seed"]
    if jis_mode not in ("auto", "off"):
        raise ValueError("unsupported JIS mode")
    codec = JisSubstitution() if jis_mode == "auto" else None
    if codec is not None:
        # Conservative collision reservation includes all parsed strings, even
        # unclassified UI text. Resource paths are never encoded/substituted.
        for name, raw in sources.items():
            for op in parse(crypt(raw, seeds[name])).ops:
                for text in op.strings:
                    codec.reserve(text)
    _check_existing_ancestors(workspace / "gt_output")
    available = {p.name for p in (workspace / "gt_output").iterdir() if p.suffix.lower() == ".json"}
    expected_files = {Path(e["name"]).stem + ".json" for e in members if e["count"]}
    if available - expected_files:
        raise ValueError("unmatched translation filenames")
    files, changed = {}, []
    for name, raw in sources.items():
        kw = _kwargs(name, sources, seeds)
        rows, manifest = export_rld(raw, seeds[name], **kw)
        filename = Path(name).stem + ".json"
        if rows:
            if (load_json(read_bounded(workspace / "gt_input" / filename)) != rows
                    or load_json(read_bounded(workspace / "metadata" / filename)) != manifest):
                raise ValueError(f"original JSON or manifest changed: {filename}")
        if filename in available:
            translated = load_json(read_bounded(workspace / "gt_output" / filename))
            modified = rebuild_rld(raw, seeds[name], translated, manifest, codec=codec, **kw)
            if modified != raw:
                files["rld/" + name] = modified
                changed.append(name)
    result = {"engine": "exhibit", "profile": PROFILE, "translated_json_files": sorted(available),
              "changed_members": changed, "unchanged_members": len(sources) - len(changed),
              "sha256": {name: sha256(raw) for name, raw in files.items()}, "runtime_verified": False}
    if codec is not None:
        result["jis_substitution"] = codec.summary()
        # An explicit seed without an EXE is enough to write scripts, but not
        # enough evidence to choose a DLL architecture.
        files.update(codec.artifacts(include_hook=report["keys"].get("machine") == 0x14C))
    files["reports/rebuild.json"] = json_bytes(result)
    files["README.txt"] = ("ExHibit 回注结果：只包含有变化的 rld/ 文件。\n"
        "先备份游戏原文件，再按原相对路径部署；不得把 original/rld 的明文当回注文件。\n"
        "本目录已通过重新解密、完整解析与文本核对；未验证游戏运行和字形显示。\n"
        "如果附带 JIS 配置/hook，请按 JIS-部署说明.txt 测试。保留原 ExHIBIT.ini 的受保护字段。\n"
        "把显示结果告诉 agent，再决定批量翻译或调整字体/编码策略。\n").encode("utf-8")
    write_new_tree(Path(output), list(files.items()))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    command = sub.add_parser("extract")
    command.add_argument("source", help="game root containing loose rld/")
    command.add_argument("output", help="new extraction directory")
    for name in ("exe", "ini", "resident", "scripts-dir"):
        command.add_argument("--" + name)
    for name in ("seed", "def-seed"):
        command.add_argument("--" + name, type=lambda s: int(s, 0))
    command.add_argument("--smoke-test", action="store_true")
    command = sub.add_parser("rebuild", aliases=["pack"])
    command.add_argument("workspace")
    command.add_argument("output", help="new result directory; only changed RLDs")
    command.add_argument("--jis-mode", choices=("auto", "off"), default="auto")
    args = vars(parser.parse_args())
    action = args.pop("command")
    result = extract(**args) if action == "extract" else rebuild(**args)
    summary = {k: result[k] for k in ("rows", "json_files", "identity_verified", "changed_members") if k in result}
    print(json.dumps(summary, ensure_ascii=True))


if __name__ == "__main__":
    main()
