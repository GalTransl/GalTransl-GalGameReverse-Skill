"""Engine-independent JIS preparation and verified delivery at the JSON boundary.

Keep the engine parser/writer unmodified: give it CP932-representable proxy
JSON in a private workspace, re-extract its output normally, then verify both
stored rows and restored Chinese here. No codec monkey-patching or engine
registry. Callers remain responsible for choosing the proven script encoding
and using an actual engine re-extraction as readback evidence.
"""
import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import stat

from .binary import FormatError
from .contract import dump_rows, load_json, sha256, validate_rows
from .jis_substitution import JisSubstitution, is_cp932
from .safety import Limits, _check_existing_ancestors, validate_names, write_new_tree

SCHEMA = "jis-json-workflow/1"
ROOTS = ("original", "metadata", "reports", "gt_input")


def _json(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _names(names):
    names = list(names)
    if validate_names(names) != names or any("/" in n or "\\" in n or not n.endswith(".json") for n in names):
        raise FormatError("JIS translation filenames must be unique, flat .json names")


def _texts(rows):
    for row in rows:
        for key, value in row.items():
            yield from value if key == "names" else (value,)


def _map_rows(rows, function):
    return [{key: [function(s) for s in value] if key == "names" else function(value)
             for key, value in row.items()} for row in rows]


@dataclass
class TranslationPlan:
    original: dict
    translated: dict
    stored: dict
    codec: JisSubstitution

    def verify(self, readback):
        """Require ALL exported files; check proxies first, then real display text."""
        if set(readback) != set(self.original):
            raise FormatError("JIS readback file set differs (include untranslated files)")
        for name, original in self.original.items():
            actual = validate_rows(readback[name])
            if actual != self.stored.get(name, original):
                raise FormatError(f"JIS stored rows differ after engine re-extraction: {name}")
            if _map_rows(actual, self.codec.display) != self.translated.get(name, original):
                raise FormatError(f"JIS restored Chinese differs: {name}")
        return {"verified_files": len(readback), "verified_rows": sum(map(len, readback.values())),
                "stored_rows_verified": True, "display_rows_verified": True, "runtime_verified": False}


def prepare_translations(original, translated, *, encoding, extra_texts=(), proxy_policy="fixed"):
    """Pure shared API. All source text is conservatively reserved before encoding.

    Only the minimal JSON display fields are transformed. The original manifest
    and engine control/name/offset checks still run in the ordinary writer.
    Extra decoded UI/control/resource text can reserve additional literal
    characters. Existing runtime mappings must be handled before this function.
    """
    if not is_cp932(encoding):
        raise FormatError("JIS preparation requires proven CP932 script encoding")
    if proxy_policy not in ("fixed", "unused"):
        raise FormatError("unsupported JIS proxy policy")
    _names(original)
    _names(translated)
    if not original or set(translated) - set(original):
        raise FormatError("empty original set or unmatched translation filenames")
    original = {n: validate_rows(r) for n, r in original.items()}
    translated = {n: validate_rows(r) for n, r in translated.items()}
    for name, rows in translated.items():
        before = original[name]
        if len(rows) != len(before):
            raise FormatError(f"JIS row count changed: {name}")
        for a, b in zip(before, rows):
            if set(a) != set(b) or ("names" in a and len(a["names"]) != len(b["names"])):
                raise FormatError(f"JIS fields/name slots changed: {name}")
    codec = JisSubstitution(encoding)
    for rows in original.values():
        for text in _texts(rows):
            codec.reserve(text)
    for text in extra_texts:
        if not isinstance(text, str):
            raise FormatError("extra display text must be decoded strings")
        codec.reserve(text)
    # One deterministic plan for the entire package. 'unused' is an explicit
    # custom mapping, not a claim of compatibility with SExtractor preset fonts.
    codec.plan((text for rows in translated.values() for text in _texts(rows)),
               remap_conflicts=proxy_policy == "unused")
    stored = {n: _map_rows(rows, lambda text: codec.encode(text).decode("cp932"))
              for n, rows in sorted(translated.items())}
    result = TranslationPlan(original, translated, stored, codec)
    result.verify({n: stored.get(n, rows) for n, rows in original.items()})
    return result


def _read(path, limit=128 << 20):
    path = Path(path)
    _check_existing_ancestors(path.parent)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or getattr(info, "st_file_attributes", 0) & 0x400:
        raise FormatError(f"not an ordinary, unlinked file: {path}")
    if info.st_size > limit:
        raise FormatError(f"input exceeds budget: {path}")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise FormatError("input grew beyond budget")
    return data


def _tree(root, limits=Limits()):
    root = Path(root)
    _check_existing_ancestors(root)
    files, total, pending, visited = {}, 0, [root], 0
    while pending:
        directory = pending.pop()
        _check_existing_ancestors(directory)
        for path in directory.iterdir():
            visited += 1
            if visited > limits.max_entries:
                raise FormatError("workspace entry count exceeds budget")
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise FormatError("workspace link/reparse point refused")
            if stat.S_ISDIR(info.st_mode):
                pending.append(path)
            else:
                raw = _read(path, limits.max_file_bytes)
                total += len(raw)
                if total > limits.max_total_bytes:
                    raise FormatError("workspace exceeds byte budget")
                files[path.relative_to(root).as_posix()] = raw
    validate_names(list(files), limits)
    return files


def _rows(directory):
    files = _tree(directory)
    selected = {n: raw for n, raw in files.items() if n.lower().endswith(".json")}
    _names(selected)
    return {n: validate_rows(load_json(raw)) for n, raw in selected.items()}


def _reject_mapping(value):
    """Reject declared source mappings; do not stack an existing display codec."""
    if isinstance(value, dict):
        if value.get("source_characters") or value.get("target_characters"):
            raise FormatError("existing character mapping requires a separate merge plan")
        for key in ("character_substitution", "tunnel_decoder"):
            if isinstance(value.get(key), dict) and value[key].get("enable"):
                raise FormatError("existing substitution/tunneling cannot be stacked")
        for child in value.values():
            _reject_mapping(child)
    elif isinstance(value, list):
        for child in value:
            _reject_mapping(child)


def prepare(workspace, output, *, encoding, extra_texts=(), include_hook=False, proxy_policy="fixed"):
    """Create a bounded private workspace; original gt_output stays real Chinese.

    Copy original/metadata/reports/gt_input byte-for-byte, not earlier rebuilt
    outputs. Artifacts stay private under support/ until finalize verifies an
    actual engine readback. No changes to engine files, profiles or manifests.
    """
    workspace, output = Path(workspace), Path(output)
    if output.exists():
        raise FileExistsError(output)
    original, translated = _rows(workspace / "gt_input"), _rows(workspace / "gt_output")
    payloads, copied_bytes = {}, 0
    for name in ROOTS:
        directory = workspace / name
        if not directory.exists():
            if name in ("original", "metadata", "gt_input"):
                raise FormatError(f"workspace missing {name}")
            continue
        for relative, raw in _tree(directory).items():
            copied_bytes += len(raw)
            if copied_bytes > Limits().max_total_bytes:
                raise FormatError("workspace copy exceeds budget")
            payloads[f"workspace/{name}/{relative}"] = raw
            if relative.lower().endswith(".json") and name in ("metadata", "reports"):
                _reject_mapping(load_json(raw))
            if name == "original" and Path(relative).name.casefold() == "uif_config.json":
                _reject_mapping(load_json(raw))
    plan = prepare_translations(original, translated, encoding=encoding, extra_texts=extra_texts,
                                proxy_policy=proxy_policy)
    for name, rows in plan.stored.items():
        payloads["workspace/gt_output/" + name] = dump_rows(rows)
        payloads["chinese/" + name] = dump_rows(translated[name])
    payloads["workspace/gt_output/.keep"] = b""
    for name, raw in plan.codec.artifacts(include_hook=include_hook):
        payloads["support/" + name] = raw
    # Retain the exact source rows in the immutable snapshot; verification never
    # trusts a generic transformation as proof the game writer worked.
    config = dict(plan.codec.summary(), schema=SCHEMA, files=sorted(original), translated_files=sorted(translated),
                  include_hook=include_hook, proxy_policy=proxy_policy,
                  snapshot={n: sha256(raw) for n, raw in payloads.items()},
                  support=[n for n in payloads if n.startswith("support/")],
                  status="prepared-only; engine rebuild and re-extraction still required")
    payloads["jis-plan.json"] = _json(config)
    payloads["README.txt"] = ("JIS 公共准备目录（不是可部署补丁）\n"
        "用原有引擎打包器读取 workspace/，输出到新的目录；无需修改引擎代码。\n"
        "用原有提取器重新提取实际生成的包，再交给公共 finalize 核对并交付。\n"
        "chinese/ 保留真实中文；workspace/gt_output/ 才是代理文本；原工作区完全不变。\n"
        "原本带 JIS 自动处理的打包器请关闭该模式，避免重复处理。\n"
        "不要用 workspace/gt_output/ 冒充实际资源回读结果。\n").encode("utf-8")
    write_new_tree(output, list(payloads.items()))
    return {"prepared_workspace": str(output / "workspace"), "json_files": len(original),
            "translated_files": len(translated), **plan.codec.summary()}


def finalize(prepared, rebuilt, readback, output):
    """Verify re-extracted JSON, then publish rebuilt resources plus JIS artifacts.

    readback is the gt_input directory of a NEW engine extraction of rebuilt
    resources. Caller must actually run that parser; this layer does not infer
    archive formats or claim a generic checksum validates an engine.
    """
    prepared, rebuilt, readback, output = map(Path, (prepared, rebuilt, readback, output))
    if output.exists():
        raise FileExistsError(output)
    settings = load_json(_read(prepared / "jis-plan.json"))
    if settings.get("schema") != SCHEMA:
        raise FormatError("unsupported JIS workflow")
    validate_names(list(settings["snapshot"]))
    for name, digest in settings["snapshot"].items():
        if sha256(_read(prepared / name)) != digest:
            raise FormatError(f"prepared JIS snapshot changed: {name}")
    _names(settings["files"])
    _names(settings["translated_files"])
    originals = _rows(prepared / "workspace/gt_input")
    proxies = _rows(prepared / "workspace/gt_output")
    chinese = {name: validate_rows(load_json(_read(prepared / "chinese" / name))) for name in settings["translated_files"]}
    if set(originals) != set(settings["files"]) or set(proxies) != set(chinese):
        raise FormatError("prepared JSON file set changed")
    substitution = {}
    if settings["used_count"]:
        config = load_json(_read(prepared / "support/uif_config.json"))["character_substitution"]
        a, b = config["source_characters"], config["target_characters"]
        if len(a) != len(b) or len(set(a)) != len(a) or len(set(b)) != len(b):
            raise FormatError("ambiguous prepared character mapping")
        substitution = str.maketrans(a, b)
    actual = _rows(readback)
    if set(actual) != set(originals):
        raise FormatError("JIS readback must contain exactly the full exported file set")
    for name, source in originals.items():
        if actual[name] != proxies.get(name, source):
            raise FormatError(f"stored rows differ after engine readback: {name}")
        if _map_rows(actual[name], lambda s: s.translate(substitution)) != chinese.get(name, source):
            raise FormatError(f"restored Chinese differs after engine readback: {name}")
    files = _tree(rebuilt)
    if not files:
        raise FormatError("rebuilt resource tree is empty")
    for name in settings["support"]:
        if not name.startswith("support/") or "/" in name[8:]:
            raise FormatError("invalid JIS support path")
        target = name[8:]
        if target in files:
            raise FormatError(f"existing output config/hook cannot be overwritten: {target}")
        files[target] = _read(prepared / name)
    report_name = "reports/jis-workflow.json"
    if report_name in files:
        raise FormatError("rebuild output already contains JIS workflow report")
    result = {"schema": SCHEMA, "script_encoding": "cp932", "verified_files": len(actual),
              "verified_rows": sum(map(len, actual.values())), "translated_files": sorted(chinese),
              "used_count": settings["used_count"], "stored_rows_verified": True,
              "remapped_count": settings["remapped_count"],
              "preset_font_compatible": settings["preset_font_compatible"],
              "display_rows_verified": True, "runtime_verified": False,
              "artifacts": [n[8:] for n in settings["support"]],
              "sha256": {n: sha256(raw) for n, raw in files.items()}}
    files[report_name] = _json(result)
    write_new_tree(output, list(files.items()))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("prepare")
    command.add_argument("workspace")
    command.add_argument("output")
    command.add_argument("--encoding", required=True, help="proven script storage codec, not JSON encoding")
    command.add_argument("--extra-text", action="append", default=[], help="UTF-8 file of additional decoded UI/source text")
    command.add_argument("--hook", choices=("none", "x86"), default="none", help="x86 only after verifying the game EXE architecture")
    command.add_argument("--proxy-policy", choices=("fixed", "unused"), default="fixed",
                         help="unused: resolve preset collisions with private CP932 proxies; requires matching hook/custom font")
    command = commands.add_parser("finalize")
    for name in ("prepared", "rebuilt", "readback", "output"):
        command.add_argument(name)
    args = vars(parser.parse_args())
    action = args.pop("command")
    if action == "prepare":
        args["extra_texts"] = [_read(p).decode("utf-8-sig", "strict") for p in args.pop("extra_text")]
        args["include_hook"] = args.pop("hook") == "x86"
        result = prepare(**args)
    else:
        result = finalize(**args)
    print(json.dumps({k: v for k, v in result.items() if k != "sha256"}, ensure_ascii=True))


if __name__ == "__main__":
    main()
