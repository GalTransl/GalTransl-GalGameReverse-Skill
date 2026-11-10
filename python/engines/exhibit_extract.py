"""Extract/rebuild/readback loose ExHibit v3 RLDs; every result goes to a new directory."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path, PureWindowsPath
import re
import stat
import struct

from ..common.contract import dump_rows, load_json, sha256
from ..common.jis_substitution import JisSubstitution
from ..common.jis_workflow import add_hook_arguments, hook_artifacts
from ..common.safety import _check_existing_ancestors, validate_names, write_new_tree, validate_new_tree_destination
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


PUA_FIRST, PUA_LAST = 0xE000, 0xF8FF
MAX_FONT = 32 << 20
# Files that ``rebuild`` writes besides rld/*.rld (JIS ones only in legacy auto mode).
REBUILD_SIDECARS = frozenset({"reports/rebuild.json", "README.txt", "uif_config.json", "jis-mapping.json",
                              "JIS-部署说明.txt", "winmm.dll", "version.dll", "version.ini"})


def eudc_fonts(ini_raw):
    """Return EUDC= values from ExHIBIT.ini bytes (any section, comments ignored)."""
    values = []
    for match in re.finditer(rb"^[ \t]*EUDC[ \t]*=[ \t]*([^\r\n;]*)", ini_raw, re.I | re.M):
        value = match.group(1).strip().strip(b'"').decode("cp932", "strict").strip()
        if value and value not in values:
            values.append(value)
    return values


def tte_codepoints(data):
    """Private-use code points with a non-zero glyph in a TrueType (.tte) cmap.

    Bounded sfnt reader for Unicode format 4/12 subtables only; anything else
    raises ValueError so the caller falls back to the whole private-use area.
    """
    if len(data) < 12 or len(data) > MAX_FONT:
        raise ValueError("EUDC font size outside budget")
    version, count = struct.unpack_from(">IH", data, 0)
    if version not in (0x00010000, 0x74727565) or not 1 <= count <= 512 or 12 + 16 * count > len(data):
        raise ValueError("not a TrueType sfnt table directory")
    cmap = None
    for i in range(count):
        tag, _, offset, length = struct.unpack_from(">4sIII", data, 12 + 16 * i)
        if tag == b"cmap":
            if offset + length > len(data) or length < 4:
                raise ValueError("cmap table outside font")
            cmap = data[offset:offset + length]
    if cmap is None:
        raise ValueError("font has no cmap table")
    _, tables = struct.unpack_from(">HH", cmap, 0)
    if tables > 64 or 4 + 8 * tables > len(cmap):
        raise ValueError("cmap subtable directory outside table")
    points, parsed = set(), False
    for i in range(tables):
        platform, encoding, offset = struct.unpack_from(">HHI", cmap, 4 + 8 * i)
        if not (platform == 0 or (platform == 3 and encoding in (1, 10))) or offset + 4 > len(cmap):
            continue
        fmt = struct.unpack_from(">H", cmap, offset)[0]
        if fmt == 4:
            length = struct.unpack_from(">H", cmap, offset + 2)[0]
            sub = cmap[offset:offset + length]
            if len(sub) != length or length < 16:
                raise ValueError("cmap format 4 outside table")
            segments = struct.unpack_from(">H", sub, 6)[0] // 2
            if 16 + 8 * segments > length:
                raise ValueError("cmap format 4 segments outside table")
            ends = struct.unpack_from(f">{segments}H", sub, 14)
            starts = struct.unpack_from(f">{segments}H", sub, 16 + 2 * segments)
            deltas = struct.unpack_from(f">{segments}h", sub, 16 + 4 * segments)
            range_at = 16 + 6 * segments
            for k, (start, end, delta) in enumerate(zip(starts, ends, deltas)):
                range_offset = struct.unpack_from(">H", sub, range_at + 2 * k)[0]
                for code in range(max(start, PUA_FIRST), min(end, PUA_LAST) + 1):
                    if range_offset:
                        at = range_at + 2 * k + range_offset + 2 * (code - start)
                        if at + 2 > length:
                            raise ValueError("cmap format 4 glyph index outside table")
                        glyph = struct.unpack_from(">H", sub, at)[0]
                        glyph = (glyph + delta) & 0xFFFF if glyph else 0
                    else:
                        glyph = (code + delta) & 0xFFFF
                    if glyph:
                        points.add(code)
            parsed = True
        elif fmt == 12:
            if offset + 16 > len(cmap):
                raise ValueError("cmap format 12 header outside table")
            length, _, groups = struct.unpack_from(">III", cmap, offset + 4)
            if offset + length > len(cmap) or 16 + 12 * groups > length:
                raise ValueError("cmap format 12 groups outside table")
            for k in range(groups):
                start, end, glyph = struct.unpack_from(">III", cmap, offset + 16 + 12 * k)
                if end < start:
                    raise ValueError("cmap format 12 group reversed")
                for code in range(max(start, PUA_FIRST), min(end, PUA_LAST) + 1):
                    if glyph + code - start:
                        points.add(code)
            parsed = True
    if not parsed:
        raise ValueError("no Unicode format 4/12 cmap subtable")
    return points


def eudc_reservation(ini_raw, base, sources, seeds):
    """Return (report, reserved_codepoints) when the INI declares EUDC, else (None, None).

    Reserve every private-use character in the parsed scripts plus the EUDC
    font's mapped private-use code points; without a safely parsed cmap,
    reserve the whole U+E000..U+F8FF block.
    """
    values = eudc_fonts(ini_raw) if ini_raw is not None else []
    if not values:
        return None, None
    text = set()
    for name, raw in sources.items():
        for op in parse(crypt(raw, seeds[name])).ops:
            text.update(ord(c) for s in op.strings for c in s if PUA_FIRST <= ord(c) <= PUA_LAST)
    fonts, font_points = [], set()
    for value in values:
        relative = PureWindowsPath(value)
        info = {"ini_value": value}
        if relative.is_absolute() or relative.drive or ".." in relative.parts:
            info["error"] = "font path is not inside the game directory"
        else:
            path = Path(base, *relative.parts)
            try:
                raw = read_bounded(path, MAX_FONT)
                info.update(path=str(path), sha256=sha256(raw))
                found = tte_codepoints(raw)
                if not found:
                    raise ValueError("cmap maps no private-use code points")
                info["cmap_private_use"] = len(found)
                font_points |= found
            except (OSError, ValueError) as exc:
                info["error"] = str(exc)
        fonts.append(info)
    if all("cmap_private_use" in f for f in fonts):
        method = "text-private-use+tte-cmap"
    else:
        method = "text-private-use+full-private-use-area"
        font_points = set(range(PUA_FIRST, PUA_LAST + 1))
    points = sorted(text | font_points)
    reserved = compact_codepoints(points)
    report = {"ini_values": values, "fonts": fonts, "method": method,
              "text_private_use": sorted(text), "reserved_count": len(points),
              "note": "JIS proxies must avoid reserved_codepoints; EUDC glyphs occupy them"}
    return report, reserved


def compact_codepoints(points):
    """Sorted code points as JSON items: int for a single point, "U+XXXX-U+YYYY" for a run."""
    items, run = [], []
    for code in sorted(set(points)) + [None]:
        if run and code == run[-1] + 1:
            run.append(code)
            continue
        if run:
            items.append(run[0] if len(run) == 1 else f"U+{run[0]:04X}-U+{run[-1]:04X}")
        run = [code] if code is not None else []
    return items


RESERVED_ITEM = re.compile(r"U\+[0-9A-F]{4,6}-U\+[0-9A-F]{4,6}")


def with_reserved(manifest, reserved):
    """Manifest as written to metadata/: settings.reserved_codepoints when EUDC is declared."""
    if reserved is None:
        return manifest
    if (not isinstance(reserved, list)
            or any(not ((type(c) is int and 0 <= c <= 0x10FFFF)
                        or (isinstance(c, str) and RESERVED_ITEM.fullmatch(c))) for c in reserved)):
        raise ValueError("invalid reserved_codepoints in workspace report")
    return dict(manifest, settings=dict(manifest["settings"], reserved_codepoints=reserved))


def _inside(path, root):
    path, root = os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.abspath(root))
    return os.path.commonpath([path, root]) == root


def _tree(directory, limit=8192):
    """Relative posix names of ordinary files below directory; links refused."""
    directory = Path(directory)
    _check_existing_ancestors(directory)
    found, pending = {}, [directory]
    while pending:
        for path in pending.pop().iterdir():
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ValueError(f"linked entry in rebuilt directory: {path}")
            if stat.S_ISDIR(info.st_mode):
                pending.append(path)
                continue
            if len(found) >= limit:
                raise ValueError("rebuilt directory has too many files")
            found[path.relative_to(directory).as_posix()] = path
    return found


def _export_members(sources, seeds, *, smoke_test=False, reserved=None):
    files, entries, row_count, json_count, growth = {}, [], 0, 0, []
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
                files[f"metadata/{filename}"] = json_bytes(with_reserved(manifest, reserved))
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
    return files, entries, row_count, json_count, growth, unknown_names


def _kwargs(name, sources, seeds):
    definitions = next((key for key in sources if key.casefold() == "defchara.rld"), None)
    kw = {"filename": name}
    if definitions and name != definitions:
        kw.update(definitions=sources[definitions], definition_seed=seeds[definitions])
    return kw


def extract(source, output, *, exe=None, ini=None, resident=None, scripts_dir=None,
            seed=None, def_seed=None, smoke_test=False):
    source, output = Path(source), Path(output)
    validate_new_tree_destination(output)
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
    # The INI is read whenever present: seed recovery needs it, and EUDC= marks
    # private-use code points that JIS proxies must not reuse.
    ini_path = Path(ini) if ini else source / "ExHIBIT.ini"
    ini_raw = read_bounded(ini_path, 1 << 20) if ini or ini_path.is_file() else None
    if ini_raw is not None:
        evidence["ini"] = {"path": str(ini_path), "sha256": sha256(ini_raw)}
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
            if ini_raw is None:
                ini_raw = read_bounded(ini_path, 1 << 20)  # reports the missing file
            seed, detail = scenario_seed(exe_raw, ini_raw)
            recovery["scenario"] = detail
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
    if ini_raw is not None:
        files["original/ExHIBIT.ini"] = ini_raw
    eudc, reserved = eudc_reservation(ini_raw, ini_path.parent, sources, seeds)
    member_files, entries, row_count, json_count, growth, unknown_names = _export_members(
        sources, seeds, smoke_test=smoke_test, reserved=reserved)
    files.update(member_files)
    report = {"engine": "exhibit", "profile": PROFILE, "source_directory": str(directory),
              "script_encoding": "cp932", "json_encoding": "utf-8", "members": entries,
              "rows": row_count, "json_files": json_count, "choices": sum(e["choices"] for e in entries),
              "unresolved_name_ids": dict(unknown_names), "identity_verified": len(entries),
              "growth_tests": growth, "keys": recovery, "key_evidence": evidence,
              "runtime_verified": False, "text_scope": "op28 dialogue; op21 TAB/1010 choices; other strings preserved"}
    if eudc is not None:
        report["eudc"] = eudc
        report["reserved_codepoints"] = reserved
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
        "CP932 中文回注默认优先使用 JIS 替换，按 EXE 位数生成 CialloHook 及配置（需要时强制 932）；\n"
        "先试注少量中文，确认加载、字体和显示后再批量翻译。\n").encode("utf-8")
    write_new_tree(output, list(files.items()))
    return report


def rebuild(workspace, output, *, jis_mode="auto", hook="auto", exe=None, force_cp932="auto"):
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
    reserved = report.get("reserved_codepoints")
    for name, raw in sources.items():
        kw = _kwargs(name, sources, seeds)
        rows, manifest = export_rld(raw, seeds[name], **kw)
        filename = Path(name).stem + ".json"
        if rows:
            if (load_json(read_bounded(workspace / "gt_input" / filename)) != rows
                    or load_json(read_bounded(workspace / "metadata" / filename))
                    != with_reserved(manifest, reserved)):
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
        # Shared policy: CialloHook by EXE bitness, forced ACP 932 unless the
        # probe proves fixed CP932. Without --exe the EXE recorded at extract
        # time is reused if still present, else only its PE machine; an
        # explicit seed alone is not enough evidence to choose a DLL.
        recorded = report.get("key_evidence", {}).get("exe", {}).get("path")
        if exe is None and recorded and Path(recorded).is_file():
            exe = recorded
        extras, delivery = hook_artifacts(codec, hook=hook, exe=exe, force_cp932=force_cp932,
                                          machine=report["keys"].get("machine"))
        result["jis_delivery"] = delivery
        files.update(extras)
    files["reports/rebuild.json"] = json_bytes(result)
    files["README.txt"] = ("ExHibit 回注结果：只包含有变化的 rld/ 文件。\n"
        "先备份游戏原文件，再按原相对路径部署；不得把 original/rld 的明文当回注文件。\n"
        "本目录已通过重新解密、完整解析与文本核对；未验证游戏运行和字形显示。\n"
        "如果附带 JIS 配置/hook，请按 JIS-部署说明.txt 测试。保留原 ExHIBIT.ini 的受保护字段。\n"
        "把显示结果告诉 agent，再决定批量翻译或调整字体/编码策略。\n").encode("utf-8")
    write_new_tree(Path(output), list(files.items()))
    return result


def readback(workspace, rebuilt, output):
    """Re-extract a ``rebuild`` result merged over the workspace originals.

    rebuilt/rld/<name> replaces that member; every other member comes from
    workspace original/encrypted after its recorded hash check. Seeds come from
    the workspace report, so no EXE/INI/resident.dll copy is needed. Unknown
    files in ``rebuilt`` are refused; nothing is written to either input.
    """
    workspace, rebuilt, output = Path(workspace), Path(rebuilt), Path(output)
    validate_new_tree_destination(output)
    for root in (workspace, rebuilt):
        if _inside(output, root) or _inside(root, output):
            raise ValueError(f"readback output must be outside {root}")
    report = load_json(read_bounded(workspace / "reports/extraction.json"))
    if report.get("engine") != "exhibit" or report.get("profile") != PROFILE:
        raise ValueError("unsupported ExHibit workspace profile")
    members = report["members"]
    flat_names([e["name"] for e in members])
    if not 1 <= len(members) <= 4096:
        raise ValueError("RLD workspace count outside budget")
    known = {e["name"] for e in members}
    replaced, unknown = {}, []
    for relative, path in sorted(_tree(rebuilt).items()):
        if relative.startswith("rld/") and relative[4:] in known:
            replaced[relative[4:]] = read_bounded(path)
        elif relative not in REBUILD_SIDECARS:
            unknown.append(relative)
    if unknown:
        raise ValueError(f"unknown files in rebuilt directory: {unknown}")
    if not replaced:
        raise ValueError("rebuilt directory contains no rld/ member of this workspace")
    sources, seeds, total = {}, {}, 0
    for entry in members:
        name = entry["name"]
        if name in replaced:
            raw = replaced[name]
        else:
            raw = read_bounded(workspace / "original/encrypted" / name)
            if len(raw) != entry["size"] or sha256(raw) != entry["sha256"]:
                raise ValueError(f"RLD source hash/size mismatch: {name}")
        total += len(raw)
        if total > 64 << 20:
            raise ValueError("RLD source total exceeds 64 MiB budget")
        sources[name], seeds[name] = raw, entry["seed"]
    member_files, entries, row_count, json_count, _, unknown_names = _export_members(
        sources, seeds, reserved=report.get("reserved_codepoints"))
    files = {name: raw for name, raw in member_files.items() if name.startswith(("gt_input/", "metadata/"))}
    result = {"engine": "exhibit", "profile": PROFILE, "mode": "readback", "members": entries,
              "rows": row_count, "json_files": json_count, "identity_verified": len(entries),
              "unresolved_name_ids": dict(unknown_names),
              "readback": {"workspace": str(workspace), "rebuilt": str(rebuilt),
                           "from_rebuilt": sorted(replaced),
                           "from_workspace": len(members) - len(replaced)},
              "runtime_verified": False}
    files["reports/readback.json"] = json_bytes(result)
    files["README.txt"] = ("ExHibit 回读结果：rebuilt 中的 rld 与工作区其余原件合并后重新解密、解析并导出。\n"
        "gt_input 是实际回注产物的提取结果，仅用于核对（如 JIS finalize），不是翻译输入。\n").encode("utf-8")
    write_new_tree(output, list(files.items()))
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
    add_hook_arguments(command)
    command = sub.add_parser("readback", help="re-extract a rebuild result merged over workspace originals")
    command.add_argument("workspace")
    command.add_argument("rebuilt", help="rebuild output directory (rld/*.rld)")
    command.add_argument("output", help="new readback directory")
    args = vars(parser.parse_args())
    action = args.pop("command")
    actions = {"extract": extract, "readback": readback}
    result = actions.get(action, rebuild)(**args)
    summary = {k: result[k] for k in ("rows", "json_files", "identity_verified", "changed_members", "readback")
               if k in result}
    print(json.dumps(summary, ensure_ascii=True))


if __name__ == "__main__":
    main()
