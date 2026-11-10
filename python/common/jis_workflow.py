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
import os
from pathlib import Path
import re
import stat
import struct
import sys

from .binary import FormatError
from .codepage_probe import MAX_SITES, probe_codepage
from .contract import dump_rows, load_json, sha256, validate_rows
from .jis_substitution import (CIALLOHOOK_NAMES, HOOKS, JisSubstitution, batch_mapping_sha256,
                               format_reserved_codepoints, is_cp932, parse_reserved_codepoints)
from .safety import Limits, _check_existing_ancestors, validate_names, write_new_tree, validate_new_tree_destination

SCHEMA = "jis-json-workflow/1"
ROOTS = ("original", "metadata", "reports", "gt_input")
# CLI --hook value -> bundled hook. "auto" (default) picks CialloHook by the
# --exe PE machine. Plain "x86" stays the legacy UIF alias (UIF is the manual
# fallback); there is no x64 UIF, so "x64" means CialloHook x64.
HOOK_CHOICES = {"none": None, "x86": "uif", "uif-x86": "uif", "ciallohook-x86": "ciallohook",
                "x64": "ciallohook-x64", "ciallohook-x64": "ciallohook-x64"}
AUTO_HOOKS = {0x14C: "ciallohook", 0x8664: "ciallohook-x64"}
FORCE_CP932_MODES = ("auto", "on", "off")
# Probe verdicts for which ACP=932 is forced in auto mode: only a confirmed
# fixed-CP932 decoder is left alone.
NEEDS_CP932 = ("acp-following", "mixed", "undetermined")
CIALLOHOOK_INI_NAMES = {"ciallohook.ini", "version.ini", "winmm.ini"}
RESERVE_SCOPES = ("untranslated", "all")
# Engine manifests (metadata/*.json, top-level "settings") may declare
# codepoints the engine/game already uses; 'unused' never allocates them.
RESERVED_CODEPOINTS_KEY = "reserved_codepoints"
MAX_LOCATIONS = 20
PE_MACHINES = {0x14C: "x86", 0x8664: "x64", 0xAA64: "arm64"}


class JisDiagnosticsError(FormatError):
    """Preparation refused; .report has the same shape as the preflight JSON."""

    def __init__(self, message, report):
        super().__init__(message)
        self.report = report


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


def _paired(original, translated):
    """Yield (gt_input location, original text, translated text or None)."""
    for name, rows in sorted(original.items()):
        after_rows = translated.get(name)
        for index, values in enumerate(rows):
            after = after_rows[index] if after_rows is not None else None
            for field, value in values.items():
                location = {"source": "gt_input", "file": name, "row": index + 1, "field": field}
                if field != "names":
                    yield location, value, after[field] if after is not None else None
                    continue
                for slot, text in enumerate(value):
                    yield (dict(location, slot=slot + 1), text,
                           after[field][slot] if after is not None else None)


@dataclass
class _Scope:
    reserved: list   # (location, text) still displayed; their characters are literal
    replaced: list   # original texts fully replaced by a translation (not reserved)
    outputs: list    # (location, text) changed translation fields


def _scope(original, translated, reserve_scope):
    """'untranslated': reserve every original text still displayed somewhere.

    A text is released only at locations whose translation differs; the same
    text at another untouched location is still reserved there. 'all' keeps
    the older conservative behaviour of reserving every original text.
    """
    if reserve_scope not in RESERVE_SCOPES:
        raise FormatError(f"unsupported JIS reserve scope: {reserve_scope}")
    scope = _Scope([], [], [])
    for location, before, after in _paired(original, translated):
        changed = after is not None and after != before
        if changed and reserve_scope == "untranslated":
            scope.replaced.append(before)
        else:
            scope.reserved.append((location, before))
        if changed:
            scope.outputs.append((dict(location, source="gt_output"), after))
    return scope


def _reserved_sources(reserved_codepoints):
    """{origin: spec list} or a plain spec list (origin 'api') -> {origin: ranges}."""
    if isinstance(reserved_codepoints, dict):
        sources = reserved_codepoints
    elif reserved_codepoints in ((), [], None, ""):
        sources = {}
    else:
        sources = {"api": reserved_codepoints}
    return {origin: parse_reserved_codepoints(spec) for origin, spec in sources.items()}


def _codec(encoding, scope, extra, reserved_sources):
    ranges = [item for ranges in reserved_sources.values() for item in ranges]
    codec = JisSubstitution(encoding, reserved_codepoints=[
        f"U+{a:04X}-U+{b:04X}" for a, b in ranges])
    for _, text in scope.reserved:
        codec.reserve(text)
    for text in extra.values():
        codec.reserve(text)
        codec.avoid_private(text)
    for text in scope.replaced:
        # A replaced line no longer reserves its characters, but its private
        # glyphs (EUDC/engine codepoints) stay out of the 'unused' pool.
        codec.avoid_private(text)
    return codec


def _next_steps(report, reserve_scope, proxy_policy):
    steps = []
    if report["missing_characters"]:
        steps.append("译文含固定表没有、也不能直接用 CP932 存储的字符（missing_characters）："
                     "在 gt_output 中改写为常用字或 CP932 可直接编码的字符后重试；unused 策略也不会为它们分配代理。")
    if report["conflicts"]:
        if proxy_policy != "unused":
            steps.append("固定表代理字与仍会显示的日文/UI 字冲突：试注阶段改用 `--proxy-policy unused`，"
                         "并用 `--exe 实际游戏EXE` 配 hook（默认 `--hook auto` 按位数选 CialloHook，"
                         "UIF `uif-x86` 只作 CialloHook 无法加载时的兜底）；全量翻译后可按固定表重新预检。")
        if reserve_scope == "all":
            steps.append("当前 `--reserve-scope all` 连已被译文替换的原文也预留；"
                         "没有证据表明这些原文仍会显示时，改用默认 `--reserve-scope untranslated`。")
        if any(item.get("reserved_codepoint") for item in report["conflicts"]):
            steps.append("部分固定代理字落在 reserved_codepoints 内，只能用 `--proxy-policy unused` 重新分配。")
    if not steps:
        steps.append("预检通过：可正式 prepare；固定映射可配 hook，或使用映射版本匹配的预设字体。")
    return steps


def _locate(report, scope, extra, reserved_sources, max_locations):
    """Attach capped literal/translation locations plus total counts."""
    limit = None if max_locations is None or max_locations <= 0 else max_locations
    literal = {item["proxy"]: [0, []] for item in report["conflicts"]}
    translation = {item["character"]: [0, []] for item in report["conflicts"]}

    def add(bucket, char, location):
        entry = bucket[char]
        entry[0] += 1
        if limit is None or len(entry[1]) < limit:
            entry[1].append(location)

    for location, text in scope.reserved:
        for char in sorted(set(text).intersection(literal)):
            add(literal, char, location)
    for location, text in scope.outputs:
        present = set(text)
        for char in sorted(present.intersection(literal)):
            add(literal, char, location)
        for char in sorted(present.intersection(translation)):
            add(translation, char, location)
    for name, text in extra.items():
        for line, value in enumerate(text.split("\n"), 1):
            for char in sorted(set(value).intersection(literal)):
                add(literal, char, {"source": "extra_texts", "file": name, "line": line})
    for origin, ranges in reserved_sources.items():
        for char in literal:
            if any(a <= ord(char) <= b for a, b in ranges):
                add(literal, char, {"source": "reserved_codepoints", "origin": origin})
    for item in report["conflicts"]:
        count, locations = literal[item["proxy"]]
        item.update(literal_locations=locations, literal_location_count=count)
        count, locations = translation[item["character"]]
        item.update(translation_locations=locations, translation_location_count=count)
    report["max_locations"] = limit


def _diagnose(codec, original, translated, scope, extra, reserved_sources, *, encoding,
              reserve_scope, proxy_policy, max_locations):
    report = codec.preflight(text for rows in translated.values() for text in _texts(rows))
    report.update(schema="jis-json-preflight/1", script_encoding=encoding, reserve_scope=reserve_scope,
                  reserved_codepoints={origin: format_reserved_codepoints(ranges)
                                       for origin, ranges in reserved_sources.items()},
                  original_files=sorted(original), translated_files=sorted(translated),
                  missing_translations=sorted(set(original) - set(translated)), runtime_verified=False)
    if report["conflicts"]:
        _locate(report, scope, extra, reserved_sources, max_locations)
    report["next_steps"] = _next_steps(report, reserve_scope, proxy_policy)
    return report


def prepare_translations(original, translated, *, encoding, extra_texts=(), proxy_policy="fixed",
                         reserve_scope="untranslated", reserved_codepoints=(), max_locations=MAX_LOCATIONS):
    """Pure shared API: one deterministic proxy plan for the whole package.

    reserve_scope="untranslated" (default) reserves original text only where it
    is still displayed (unchanged rows/fields/name slots and untranslated
    files); "all" also reserves fully replaced lines. Extra decoded UI/control/
    resource text is always reserved. reserved_codepoints (spec list or
    {origin: spec list}) are never used as proxies. A refusal raises
    JisDiagnosticsError whose .report matches preflight_translations().
    Only display fields are transformed; the engine writer still runs its own
    manifest, control, name and offset checks.
    """
    if proxy_policy not in ("fixed", "unused"):
        raise FormatError("unsupported JIS proxy policy")
    original, translated = _translation_inputs(original, translated, encoding)
    extra = _extra_texts(extra_texts)
    scope = _scope(original, translated, reserve_scope)
    reserved_sources = _reserved_sources(reserved_codepoints)
    codec = _codec(encoding, scope, extra, reserved_sources)
    report = _diagnose(codec, original, translated, scope, extra, reserved_sources, encoding=encoding,
                       reserve_scope=reserve_scope, proxy_policy=proxy_policy, max_locations=max_locations)
    if report["missing_characters"] or (report["conflicts"] and proxy_policy == "fixed"):
        report.update(ok=False, stage="prepare", proxy_policy=proxy_policy)
        if report["missing_characters"]:
            char = report["missing_characters"][0]
            message = f"missing JIS substitution: U+{ord(char):04X}"
        else:
            message = ("JIS proxy also occurs as literal display text or reserved codepoint: "
                       + " ".join(f"{c['character']}->{c['proxy']}" for c in report["conflicts"]))
        raise JisDiagnosticsError(message, report)
    # 'unused' is an explicit custom mapping, not SExtractor preset-font compatible.
    codec.plan((text for rows in translated.values() for text in _texts(rows)),
               remap_conflicts=proxy_policy == "unused")
    stored = {n: _map_rows(rows, lambda text: codec.encode(text).decode("cp932"))
              for n, rows in sorted(translated.items())}
    result = TranslationPlan(original, translated, stored, codec)
    result.verify({n: stored.get(n, rows) for n, rows in original.items()})
    return result


def _translation_inputs(original, translated, encoding):
    if not is_cp932(encoding):
        raise FormatError("JIS workflow requires proven CP932 script encoding")
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
    return original, translated


def _extra_texts(texts):
    named = texts if isinstance(texts, dict) else {f"extra-{i}.txt": text for i, text in enumerate(texts, 1)}
    validate_names(list(named))
    if any(not isinstance(text, str) for text in named.values()):
        raise FormatError("extra display text must be decoded strings")
    return named


def preflight_translations(original, translated, *, encoding, extra_texts=(), reserve_scope="untranslated",
                           reserved_codepoints=(), max_locations=MAX_LOCATIONS):
    """Read-only fixed-mapping diagnostics for any engine's display JSON.

    extra_texts accepts decoded strings or a relative source-name -> text dict.
    Engine parsers remain responsible for supplying unexported display text.
    Location lists are capped at max_locations (<= 0: unlimited); *_count
    fields always give the totals.
    """
    original, translated = _translation_inputs(original, translated, encoding)
    extra = _extra_texts(extra_texts)
    scope = _scope(original, translated, reserve_scope)
    reserved_sources = _reserved_sources(reserved_codepoints)
    codec = _codec(encoding, scope, extra, reserved_sources)
    return _diagnose(codec, original, translated, scope, extra, reserved_sources, encoding=encoding,
                     reserve_scope=reserve_scope, proxy_policy="fixed", max_locations=max_locations)


def _read(path, limit=128 << 20):
    path = Path(path)
    _check_existing_ancestors(path.parent)
    return _read_entry(path, path.lstat(), limit)


def _read_entry(path, info, limit):
    """Read a file whose ancestors were already checked; info is its lstat."""
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or getattr(info, "st_file_attributes", 0) & 0x400:
        raise FormatError(f"not an ordinary, unlinked file: {path}")
    if info.st_size > limit:
        raise FormatError(f"input exceeds budget: {path}")
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        if info.st_ino and opened.st_ino and (opened.st_ino, opened.st_dev) != (info.st_ino, info.st_dev):
            raise FormatError(f"input replaced while reading: {path}")
        # read(n) preallocates n bytes: size the first read from lstat, and only
        # continue (still bounded) if the file grew after lstat.
        want = min(info.st_size, limit) + 1
        data = stream.read(want)
        if len(data) == want and want <= limit:
            data += stream.read(limit + 1 - len(data))
    if len(data) > limit:
        raise FormatError("input grew beyond budget")
    return data


def _tree(root, limits=Limits()):
    """Bounded tree read. Ancestors of root are checked once; every entry below
    is lstat-checked before descent/read, so no per-file ancestor walk."""
    root = Path(root)
    _check_existing_ancestors(root)
    files, total, pending, visited = {}, 0, [root], 0
    while pending:
        directory = pending.pop()
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
                raw = _read_entry(path, info, limits.max_file_bytes)
                total += len(raw)
                if total > limits.max_total_bytes:
                    raise FormatError("workspace exceeds byte budget")
                files[path.relative_to(root).as_posix()] = raw
    validate_names(list(files), limits)
    return files


def _json_rows(files):
    selected = {n: raw for n, raw in files.items() if n.lower().endswith(".json")}
    _names(selected)
    return {n: validate_rows(load_json(raw)) for n, raw in selected.items()}


def _rows(directory):
    return _json_rows(_tree(directory))


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


def _reject_ciallohook_map(raw):
    """An enabled CialloHook glyph map already substitutes characters."""
    text = raw.decode("utf-8-sig", "replace")
    if re.search(r"^[ \t]*EnableCnJpMap[ \t]*=[ \t]*(true|1)\b", text, re.I | re.M):
        raise FormatError("existing CialloHook EnableCnJpMap cannot be stacked")


def pe_machine(path):
    """Return the PE header Machine of an EXE/DLL (bounded header read only)."""
    with Path(path).open("rb") as stream:
        head = stream.read(64)
        if len(head) < 64 or head[:2] != b"MZ":
            raise FormatError(f"not a PE file: {path}")
        offset = struct.unpack_from("<I", head, 0x3C)[0]
        if offset > 1 << 20:
            raise FormatError(f"PE header offset out of range: {path}")
        stream.seek(offset)
        header = stream.read(6)
    if len(header) != 6 or header[:4] != b"PE\0\0":
        raise FormatError(f"not a PE file: {path}")
    return struct.unpack_from("<H", header, 4)[0]


def _check_hook_machine(exe, hook):
    machine = pe_machine(exe)
    expected = HOOKS[hook]["machine"]
    if machine != expected:
        raise FormatError(f"hook {hook} is {HOOKS[hook]['architecture']} but EXE machine is "
                          f"0x{machine:04X} ({PE_MACHINES.get(machine, 'unknown')}); "
                          "a DLL of another bitness is never loaded")
    return machine


def resolve_hook(hook, exe, warnings):
    """'auto' -> CialloHook of the EXE's bitness; None without an EXE (warned)."""
    if hook != "auto":
        if hook not in HOOKS:
            raise FormatError(f"unknown JIS hook: {hook}")
        return hook
    if exe is None:
        warnings.append("--hook auto 未提供 --exe，无法判断位数，未附带 hook；"
                        "请用 --exe 指定实际绘制文本的游戏 EXE 重新准备")
        return None
    machine = pe_machine(exe)
    if machine not in AUTO_HOOKS:
        raise FormatError(f"no bundled hook for EXE machine 0x{machine:04X} "
                          f"({PE_MACHINES.get(machine, 'unknown')})")
    return AUTO_HOOKS[machine]


def _force_mode(value):
    if value is True or value is False:
        return "on" if value else "off"
    if value not in FORCE_CP932_MODES:
        raise FormatError(f"force_cp932 must be one of {FORCE_CP932_MODES}")
    return value


def runtime_codepage(exe, mode, hook, warnings):
    """Probe the EXE (if given) and decide whether to force ACP 932.

    hook is the bundled hook name or None. Only CialloHook can force 932
    (LE/LEP restart); 'on' without it is an error. Probe FormatErrors
    (unsupported PE, damaged headers) count as 'undetermined'.
    """
    mode = _force_mode(mode)
    record = {"exe": str(exe) if exe is not None else None, "verdict": None, "confidence": None,
              "probe_error": None, "force_cp932_mode": mode}
    if exe is not None:
        try:
            probe = probe_codepage(exe)
            record.update(verdict=probe["verdict"], confidence=probe["confidence"],
                          reasons=probe["reasons"])
        except FormatError as error:
            record.update(verdict="undetermined", probe_error=f"{type(error).__name__}: {error}")
    ciallo = hook in CIALLOHOOK_NAMES
    verdict = record["verdict"]
    if mode == "on":
        if not ciallo:
            raise FormatError("--force-cp932 on needs a CialloHook (ciallohook-x86/ciallohook-x64); "
                              "UIF cannot restart the game under another locale")
        enabled, reason = True, "manual --force-cp932 on"
    elif mode == "off":
        enabled, reason = False, "manual --force-cp932 off"
        if verdict in NEEDS_CP932:
            warnings.append(f"运行时码页探测为 {verdict}，但已手动关闭强制 932：用户须自行以日文区域"
                            "（ACP 932）运行，否则 JIS 代理在非 932 系统上会乱码")
    elif exe is None:
        enabled, reason = False, "no --exe: runtime code page not probed"
        warnings.append("未提供 --exe，未探测运行时码页，未开启强制 932；引擎若跟随系统 ACP，"
                        "JIS 代理在非 932 系统上会乱码。请提供 --exe 重新准备")
    elif verdict == "fixed-cp932":
        enabled, reason = False, "probe verdict fixed-cp932: engine decodes CP932 regardless of ACP"
    elif ciallo:
        enabled, reason = True, f"probe verdict {verdict}: fixed CP932 not confirmed, force ACP 932"
    else:
        enabled, reason = False, f"probe verdict {verdict} needs ACP 932, but no CialloHook is bundled"
        warnings.append(f"运行时码页探测为 {verdict}，需要强制 932，但当前 hook 不是 CialloHook："
                        "改用 --hook auto/ciallohook-*，或由用户手动以日文区域运行")
    record.update(force_cp932=enabled, decision_reason=reason)
    return record


def hook_artifacts(codec, *, hook="auto", exe=None, force_cp932="auto", machine=None):
    """Shared engine entry for JIS delivery files.

    Same policy as ``prepare``: ``hook`` is "auto", a CLI alias from
    HOOK_CHOICES or a bundled hook name; "auto" picks CialloHook by the EXE's
    PE machine (``machine`` is a fallback hint when an engine recorded it
    without an EXE). An explicit hook of another bitness is refused. Forced
    ACP 932 follows ``runtime_codepage``. Returns (files, record).
    """
    warnings = []
    hook = HOOK_CHOICES.get(hook, hook) if hook != "auto" else hook
    exe = Path(exe) if exe else None
    if exe is not None and not exe.is_file():
        raise FormatError(f"--exe is not a file: {exe}")
    if hook == "auto" and exe is None and machine in AUTO_HOOKS:
        name = AUTO_HOOKS[machine]
        warnings.append("未提供 --exe：按记录的 PE 位数选择 hook，未探测运行时码页")
    else:
        name = resolve_hook(hook, exe, warnings) if hook is not None else None
    if name is not None and exe is not None:
        _check_hook_machine(exe, name)
    record = runtime_codepage(exe, force_cp932, name, warnings)
    files = codec.artifacts(include_hook=name is not None, hook=name or "ciallohook",
                            force_cp932=record["force_cp932"])
    return files, {"hook": name, "force_cp932": record["force_cp932"],
                   "runtime_codepage": record, "warnings": warnings}


def add_hook_arguments(parser):
    """CLI options shared by engines that emit JIS delivery files."""
    parser.add_argument("--hook", choices=("auto", *HOOK_CHOICES), default="auto",
                        help="auto (default): CialloHook matching the --exe PE machine; "
                             "uif-x86/x86: UIF fallback; none: no DLL")
    parser.add_argument("--exe", help="game EXE that draws text: hook bitness and runtime code-page probe")
    parser.add_argument("--force-cp932", choices=FORCE_CP932_MODES, default="auto",
                        help="CialloHook LE/LEP restart under ACP 932; auto: on unless the --exe probe "
                             "verdict is fixed-cp932 (off without --exe)")


def prepare(workspace, output=None, *, encoding, extra_texts=(), include_hook=False,
            hook="auto", proxy_policy="fixed", jis_preflight=False, translations=None,
            reserve_scope="untranslated", reserved_codepoints=(), max_locations=MAX_LOCATIONS, exe=None,
            force_cp932="auto"):
    """Create a bounded private workspace; original gt_output stays real Chinese.

    Copy original/metadata/reports/gt_input byte-for-byte, not earlier rebuilt
    outputs. Artifacts stay private under support/ until finalize verifies an
    actual engine readback. No changes to engine files, profiles or manifests.
    reserved_codepoints adds to those declared by metadata manifests under
    settings.reserved_codepoints. hook="auto" picks CialloHook by the exe's PE
    machine (no exe: no hook, warned). force_cp932 "auto" probes exe and
    forces ACP 932 unless the verdict is fixed-cp932; "on"/"off" override.
    """
    workspace = Path(workspace)
    if hook != "auto" and hook not in HOOKS:
        raise FormatError(f"unknown JIS hook: {hook}")
    force_mode = _force_mode(force_cp932)
    if jis_preflight and proxy_policy != "fixed":
        raise FormatError("JIS preflight reports the fixed mapping; use --proxy-policy fixed")
    warnings = []
    if not jis_preflight:
        if output is None:
            raise FormatError("JIS prepare requires an output destination")
        output = Path(output)
        validate_new_tree_destination(output)
        hook = resolve_hook(hook, exe, warnings) if include_hook else None
    else:
        hook = None  # preflight writes no hook/config
    include_hook = hook is not None
    machine = _check_hook_machine(exe, hook) if exe is not None and include_hook else None
    codepage = None if jis_preflight else runtime_codepage(exe, force_mode, hook, warnings)
    force = bool(codepage and codepage["force_cp932"])
    translated_dir = Path(translations) if translations is not None else workspace / "gt_output"
    payloads, declared = _workspace_payloads(workspace)
    original = _json_rows({n[len("workspace/gt_input/"):]: raw for n, raw in payloads.items()
                           if n.startswith("workspace/gt_input/")})
    translated = _rows(translated_dir)
    reserved = dict(declared)
    if isinstance(reserved_codepoints, dict):
        reserved.update(reserved_codepoints)
    elif reserved_codepoints not in ((), [], None, ""):
        reserved["cli"] = reserved_codepoints
    options = dict(encoding=encoding, extra_texts=extra_texts, reserve_scope=reserve_scope,
                   reserved_codepoints=reserved, max_locations=max_locations)
    if jis_preflight:
        return preflight_translations(original, translated, **options)
    plan = prepare_translations(original, translated, proxy_policy=proxy_policy, **options)
    for name, rows in plan.stored.items():
        payloads["workspace/gt_output/" + name] = dump_rows(rows)
        payloads["chinese/" + name] = dump_rows(translated[name])
    payloads["workspace/gt_output/.keep"] = b""
    for name, raw in plan.codec.artifacts(include_hook=include_hook, hook=hook or "ciallohook",
                                          force_cp932=force):
        payloads["support/" + name] = raw
    # Retain the exact source rows in the immutable snapshot; verification never
    # trusts a generic transformation as proof the game writer worked.
    config = dict(plan.codec.summary(), schema=SCHEMA, files=sorted(original), translated_files=sorted(translated),
                  include_hook=include_hook, hook=hook,
                  hook_architecture=HOOKS[hook]["architecture"] if include_hook else None,
                  exe_machine=f"0x{machine:04X}" if machine is not None else None,
                  force_cp932=force, runtime_codepage=codepage, warnings=warnings,
                  proxy_policy=proxy_policy, reserve_scope=reserve_scope,
                  reserved_codepoint_sources={k: format_reserved_codepoints(parse_reserved_codepoints(v))
                                              for k, v in reserved.items()},
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
            "translated_files": len(translated), "proxy_policy": proxy_policy,
            "reserve_scope": reserve_scope, "hook": hook, "force_cp932": force,
            "runtime_codepage": {k: v for k, v in codepage.items() if k != "reasons"},
            "warnings": warnings, **plan.codec.summary()}


def _workspace_payloads(workspace):
    """Copy the four source roots once; also collect manifest-declared
    settings.reserved_codepoints as {"metadata/<path>": spec}."""
    payloads, declared, copied_bytes = {}, {}, 0
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
                value = load_json(raw)
                _reject_mapping(value)
                settings = value.get("settings") if isinstance(value, dict) else None
                if name == "metadata" and isinstance(settings, dict) and RESERVED_CODEPOINTS_KEY in settings:
                    spec = settings[RESERVED_CODEPOINTS_KEY]
                    parse_reserved_codepoints(spec)
                    declared[f"metadata/{relative}"] = spec
            if name == "original" and Path(relative).name.casefold() == "uif_config.json":
                _reject_mapping(load_json(raw))
            if name == "original" and Path(relative).name.casefold() in CIALLOHOOK_INI_NAMES:
                _reject_ciallohook_map(raw)
    return payloads, declared


def finalize(prepared, rebuilt, readback, output):
    """Verify re-extracted JSON, then publish rebuilt resources plus JIS artifacts.

    readback is the gt_input directory of a NEW engine extraction of rebuilt
    resources. Caller must actually run that parser; this layer does not infer
    archive formats or claim a generic checksum validates an engine.
    """
    prepared, rebuilt, readback, output = map(Path, (prepared, rebuilt, readback, output))
    validate_new_tree_destination(output)
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
    substitution, mapping = {}, {}
    if settings["used_count"]:
        config = load_json(_read(prepared / "support/uif_config.json"))["character_substitution"]
        a, b = config["source_characters"], config["target_characters"]
        if len(a) != len(b) or len(set(a)) != len(a) or len(set(b)) != len(b):
            raise FormatError("ambiguous prepared character mapping")
        substitution = str.maketrans(a, b)
        mapping = dict(zip(b, a))
    batch_hash = batch_mapping_sha256(mapping)
    if settings.get("batch_mapping_sha256", batch_hash) != batch_hash:
        raise FormatError("prepared uif_config.json differs from the planned batch mapping")
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
    result = {"schema": SCHEMA, "script_encoding": settings.get("script_encoding", "cp932"),
              "verified_files": len(actual),
              "verified_rows": sum(map(len, actual.values())), "translated_files": sorted(chinese),
              "used_count": settings["used_count"], "stored_rows_verified": True,
              "remapped_count": settings["remapped_count"],
              "mapping_sha256": settings.get("mapping_sha256"), "batch_mapping_sha256": batch_hash,
              "proxy_policy": settings.get("proxy_policy"), "reserve_scope": settings.get("reserve_scope"),
              "hook": settings.get("hook"), "hook_architecture": settings.get("hook_architecture"),
              "force_cp932": settings.get("force_cp932", False),
              "runtime_codepage": settings.get("runtime_codepage"), "warnings": settings.get("warnings", []),
              "preset_font_compatible": settings["preset_font_compatible"],
              "display_rows_verified": True, "runtime_verified": False,
              "artifacts": [n[8:] for n in settings["support"]],
              "sha256": {n: sha256(raw) for n, raw in files.items()}}
    files[report_name] = _json(result)
    write_new_tree(output, list(files.items()))
    return result


def _emit(value):
    """Machine-readable UTF-8 JSON on stdout (not ASCII-escaped)."""
    sys.stdout.flush()
    sys.stdout.buffer.write((json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    sys.stdout.buffer.flush()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("prepare")
    command.add_argument("workspace")
    command.add_argument("output", nargs="?")
    command.add_argument("--encoding", required=True, help="proven script storage codec, not JSON encoding")
    command.add_argument("--extra-text", action="append", default=[], help="UTF-8 file of additional decoded UI/source text")
    command.add_argument("--translations", help="translation JSON directory; default: workspace/gt_output")
    command.add_argument("--jis-preflight", action="store_true", help="report fixed JIS proxy conflicts without writing a workspace")
    command.add_argument("--hook", choices=("auto", *HOOK_CHOICES), default="auto",
                         help="auto (default): CialloHook matching the --exe PE machine, none without --exe; "
                              "ciallohook-x86 / x64 / ciallohook-x64: CialloHook version.dll+ini; "
                              "uif-x86 / x86: UIF winmm.dll, manual fallback when CialloHook does not load; "
                              "none: no DLL")
    command.add_argument("--exe", help="game EXE: selects the auto hook, refuses a hook of another bitness, "
                                       "and is probed for --force-cp932 auto")
    command.add_argument("--force-cp932", choices=FORCE_CP932_MODES, default="auto",
                         help="CialloHook [LocaleEmulator] restart under ACP 932 plus LE/LEP DLLs. "
                              "auto: on unless the --exe probe verdict is fixed-cp932 (off without --exe)")
    command.add_argument("--proxy-policy", choices=("fixed", "unused"), default="fixed",
                         help="unused: resolve preset collisions with private CP932 proxies; requires matching hook/custom font")
    command.add_argument("--reserve-scope", choices=RESERVE_SCOPES, default="untranslated",
                         help="untranslated: reserve original text only where it is still displayed; "
                              "all: also reserve lines replaced by translations. Extra text is always reserved")
    command.add_argument("--reserve-codepoints", action="append", default=[],
                         help="never use as proxies, e.g. U+E000 or U+E000-U+E0FF (comma list, repeatable); "
                              "added to manifest settings.reserved_codepoints")
    command.add_argument("--max-locations", type=int, default=MAX_LOCATIONS,
                         help="cap per-conflict location lists (totals are always reported); 0 = unlimited")
    command = commands.add_parser("finalize")
    for name in ("prepared", "rebuilt", "readback", "output"):
        command.add_argument(name)
    command = commands.add_parser("arch", help="print a game EXE's PE machine and matching --hook values")
    command.add_argument("exe")
    command = commands.add_parser("codepage", help="read-only static probe: fixed CP932 or system-ACP text "
                                                   "decoding, before choosing JIS or direct GBK re-injection")
    command.add_argument("exe", nargs="+")
    command.add_argument("--max-sites", type=int, default=MAX_SITES,
                         help="cap each listed call/compare site list (summary keeps totals); 0 = unlimited")
    args = vars(parser.parse_args())
    action = args.pop("command")
    if action == "codepage":
        results, failed = [], False
        for exe in args["exe"]:
            try:
                results.append(probe_codepage(exe, max_sites=args["max_sites"]))
            except (FormatError, OSError) as error:
                failed = True
                results.append({"ok": False, "file": exe, "error": f"{type(error).__name__}: {error}"})
        _emit(results[0] if len(results) == 1 else {"ok": not failed, "results": results})
        if failed:
            raise SystemExit(1)
        return
    try:
        if action == "arch":
            machine = pe_machine(args["exe"])
            arch = PE_MACHINES.get(machine, "unknown")
            choices = [k for k, v in HOOK_CHOICES.items() if v and HOOKS[v]["machine"] == machine]
            _emit({"machine": f"0x{machine:04X}", "architecture": arch, "hook_choices": choices,
                   "auto_hook": AUTO_HOOKS.get(machine)})
            return
        if action == "prepare":
            if not args["jis_preflight"] and args["output"] is None:
                parser.error("prepare requires output unless --jis-preflight is selected")
            if args["jis_preflight"] and args["proxy_policy"] != "fixed":
                parser.error("--jis-preflight requires --proxy-policy fixed")
            args["extra_texts"] = {f"{i}-{Path(p).name}": _read(p).decode("utf-8-sig", "strict")
                                   for i, p in enumerate(args.pop("extra_text"), 1)}
            args["reserved_codepoints"] = args.pop("reserve_codepoints")
            if args["hook"] != "auto":
                args["hook"] = HOOK_CHOICES[args["hook"]]
            args["include_hook"] = args["hook"] is not None
            args["hook"] = args["hook"] or "auto"
            result = prepare(**args)
        else:
            result = finalize(**args)
    except JisDiagnosticsError as error:
        _emit(error.report)
        raise SystemExit(1)
    except (FormatError, OSError) as error:
        _emit({"ok": False, "error": f"{type(error).__name__}: {error}"})
        raise SystemExit(1)
    _emit({k: v for k, v in result.items() if k != "sha256"})
    if action == "prepare" and args["jis_preflight"] and not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
