"""Bounded Ren'Py workspaces: RPA/ARC3 + loose RPYC2, new tl languages, .rpy source.

Never imports game modules, runs a game, or unpickles executable objects.
CLI writes only new directories. Source .rpy lexing remains in renpy.py; the
.rpy workspace is renpy_source.py and tl generation is renpy_tl.py.

Loading rules used here (verified against Ren'Py 8 renpy/loader.py and
renpy/script.py, read as text): loose files under game/ are scanned before
archives and opened before archives unless ``config.force_archives``; a
``.rpy`` inside an archive is never loaded; a loose ``.rpy`` replaces its
``.rpyc`` unless the source MD5 equals the 16-byte digest at the RPYC end.
"""
import argparse
from collections import Counter, defaultdict
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

from ..archives import rpa
from ..common.contract import dump_rows, load_json, make_manifest, sha256, validate_translation
from ..common.safety import _check_existing_ancestors, validate_names, write_new_tree, validate_new_tree_destination
from . import renpy_rpyc as rpyc
from . import renpy_tl as tl
from .renpy_pickle import attributes, class_name, scalar

MAX_ARCHIVE = 64 << 20
MAX_TOTAL = 128 << 20
MAX_LOOSE_FILES = 4096
MAX_WALK = 200_000
LOOSE = "loose"
SCRIPT_SUFFIXES = (".rpyc", ".rpy", ".rpymc", ".rpym")
# Speakers predefined by the Ren'Py runtime itself, never in game archives.
BUILTIN_SPEAKERS = frozenset({"extend", "narrator", "centered", "vcentered", "nvl"})
CONFIG_HINT = re.compile(r"\bconfig\.(archives|force_archives|file_open_callback|searchpath|language|default_language)\b")


@lru_cache(maxsize=256)
def parsed(data):
    """Parse each RPYC once per run; Script objects are only read, never mutated."""
    return rpyc.parse(data)


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _ordinary(info):
    return stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and not getattr(info, "st_file_attributes", 0) & 0x400


def read_bounded(path, limit=MAX_ARCHIVE):
    path = Path(path)
    _check_existing_ancestors(path.parent)
    if not _ordinary(path.lstat()):
        raise ValueError(f"not an ordinary, unlinked input file: {path}")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError(f"Ren'Py input exceeds budget: {path}")
    return raw


def flat_names(names):
    if validate_names(names) != names or any("/" in n or "\\" in n for n in names):
        raise ValueError("expected unique flat Ren'Py filenames")


def discover_loose(directory, suffixes=SCRIPT_SUFFIXES):
    """Loose script paths under game/, as Ren'Py's walkdir sees them.

    Skips dot entries and the top-level cache/ and saves/ that the loader
    ignores; never follows links/junctions. Returns sorted slash paths.
    """
    directory = Path(directory)
    _check_existing_ancestors(directory)
    if (directory / "renpy").is_dir() or (directory / "game").is_dir():
        raise ValueError("pass the game/ directory itself, not the project root")
    found, seen, pending = [], 0, [(directory, "")]
    while pending:
        folder, prefix = pending.pop()
        if prefix.count("/") > 16:
            raise ValueError("loose directory nesting exceeds budget")
        for item in os.scandir(folder):
            seen += 1
            if seen > MAX_WALK:
                raise ValueError("loose directory entry count exceeds budget")
            if item.name.startswith("."):
                continue
            rel = prefix + item.name
            info = item.stat(follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400:
                if prefix or item.name not in ("cache", "saves"):
                    pending.append((Path(item.path), rel + "/"))
            elif stat.S_ISREG(info.st_mode) and item.name.lower().endswith(suffixes):
                found.append(rel)
    if len(found) > MAX_LOOSE_FILES * 2:
        raise ValueError("loose script count exceeds budget")
    found.sort()
    validate_names(found)
    return found


def loader_hints(directory):
    """Text-only evidence from ../renpy/loader.py (never imported or executed)."""
    path = Path(directory).parent / "renpy" / "loader.py"
    try:
        raw = read_bounded(path, 1 << 20)
    except (ValueError, OSError):
        return None
    text = raw.decode("utf-8", "replace")
    def returns(name):
        return sorted({v for block in re.findall(rf"def {name}\(\):\s*return \[([^\]]*)\]", text)
                       for v in re.findall(r"""b?["']([^"']+)["']""", block)})
    return {"path": "renpy/loader.py", "sha256": sha256(raw), "extensions": returns("get_supported_extensions"),
            "headers": returns("get_supported_headers"),
            "loose_before_archives": "load_from_filesystem" in text and "force_archives" in text}


def scan(directory):
    """Read archive headers/indexes and loose script names; never load media."""
    directory = Path(directory)
    _check_existing_ancestors(directory)
    result = []
    paths = sorted(p for p in directory.iterdir() if p.suffix.lower() in (".rpa", ".arc"))
    if len(paths) > 256:
        raise ValueError("Ren'Py archive count exceeds budget")
    for path in paths:
        if not _ordinary(path.lstat()):
            raise ValueError(f"unsafe archive path: {path}")
        try:
            with path.open("rb") as stream:
                index = rpa.read_index(stream, max_file_size=2 << 30, max_total_size=16 << 30, max_archive_size=16 << 30)
            validate_names([e.name for e in index.entries])
            result.append({"archive": path.name, "size": index.size, "magic": index.header[:7].decode("ascii"),
                           "members": len(index.entries), "scripts": [{"name": e.name, "size": e.length}
                            for e in index.entries if e.name.lower().endswith(SCRIPT_SUFFIXES)]})
        except ValueError as exc:
            result.append({"archive": path.name, "status": "unsupported", "error": str(exc)})
    loose = [{"name": n, "size": (directory / n).lstat().st_size} for n in discover_loose(directory)]
    return {"archives": result, "loose": loose, "loader": loader_hints(directory)}


def load_archives(directory, names):
    flat_names(names)
    if not len(names) <= 64:
        raise ValueError("Ren'Py selected archive count outside budget")
    if any(n.casefold() == LOOSE for n in names):
        raise ValueError("archive name is reserved for loose files")
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
    compiled = [e.name for _, e in entries if e.name.lower().endswith(".rpyc")]
    if len(compiled) > 4096:
        raise ValueError("Ren'Py compiled script count outside budget")
    try:
        validate_names(compiled)
    except ValueError as exc:
        raise ValueError(f"same script in several selected archives ({exc}); Ren'Py picks the first archive in "
                         "config.archives (default: archive names sorted in reverse) - select only the effective one") from exc
    return archives, entries


def load_loose(directory, names, total=0):
    data = {}
    for name in names:
        raw = read_bounded(Path(directory).joinpath(*name.split("/")), rpyc.MAX_FILE)
        total += len(raw)
        if total > MAX_TOTAL:
            raise ValueError("Ren'Py selected loose script total exceeds budget")
        data[name] = raw
    return data


def resolve(entries, loose, rpy_digests, loose_names, *, include_loose=True, rpy_mode=False):
    """Apply Ren'Py's loose-vs-archive and .rpy-vs-.rpyc rules.

    entries: selected (archive, Entry); loose: {name: raw RPYC};
    rpy_digests: {loose .rpy name: md5 hex}; loose_names: every loose script.
    Returns (effective entries, overrides, notes, source_only).
    """
    folded = {}
    for name in loose_names:
        folded.setdefault(name.casefold(), set()).add(name)
    overrides, notes, effective, source_only = [], [], [], []
    for archive, entry in entries:
        lower = entry.name.lower()
        if lower.endswith((".rpy", ".rpym")):
            notes.append({"archive": archive, "name": entry.name, "note": "archived source is never loaded by Ren'Py"})
        same = folded.get(entry.name.casefold(), set())
        if same and entry.name not in same:
            raise ValueError(f"loose {sorted(same)} differs only in case from {archive}:{entry.name}; resolve first")
        if entry.name in same and lower.endswith(".rpyc"):
            if not include_loose:
                raise ValueError(f"loose game/{entry.name} overrides {archive}:{entry.name}; add --loose")
            overrides.append({"name": entry.name, "effective": LOOSE, "shadowed": archive})
            continue
        if lower.endswith(".rpyc") and entry.name[:-1] in rpy_digests:
            raise ValueError(f"loose game/{entry.name[:-1]} and archived {archive}:{entry.name} would both load; "
                             "remove one before translating")
        effective.append((archive, entry))
    for name, raw in loose.items():
        effective.append((LOOSE, rpa.Entry(name, raw, 0, 0)))
        digest = rpy_digests.get(name[:-1])
        if digest is not None:
            if raw[-16:].hex() != digest:
                raise ValueError(f"loose game/{name[:-1]} differs from the source digest in {name}; Ren'Py "
                                 "recompiles the .rpy, so use the --rpy source workspace")
            notes.append({"archive": LOOSE, "name": name, "note": ".rpy present; its MD5 equals the RPYC digest, so "
                          "the RPYC is loaded while the .rpy stays unchanged"})
    compiled = {e.name for _, e in effective if e.name.lower().endswith(".rpyc")}
    for name in sorted(rpy_digests):
        if name + "c" not in compiled and not any(e.name == name + "c" for _, e in entries):
            source_only.append(name)
    if not rpy_mode and not compiled:
        raise ValueError("no Ren'Py compiled scripts selected")
    return effective, overrides, notes, source_only


def gather(directory, archives, *, include_loose):
    """Read selected archives and (optionally) loose RPYC with override rules."""
    directory = Path(directory)
    sources, entries = load_archives(directory, list(archives)) if archives else ({}, [])
    names = discover_loose(directory)
    rpyc_names = [n for n in names if n.lower().endswith(".rpyc")]
    if include_loose and len(rpyc_names) > MAX_LOOSE_FILES:
        raise ValueError("loose RPYC count exceeds budget")
    loose = load_loose(directory, rpyc_names if include_loose else [], sum(map(len, sources.values())))
    rpy_digests, total = {}, 0
    for n in names:
        if n.lower().endswith(".rpy"):
            raw = read_bounded(directory.joinpath(*n.split("/")))
            total += len(raw)
            if total > 2 * MAX_TOTAL:
                raise ValueError("loose .rpy total exceeds budget")
            rpy_digests[n] = hashlib.md5(raw).hexdigest()
    effective, overrides, notes, source_only = resolve(entries, loose, rpy_digests, names, include_loose=include_loose)
    return sources, loose, rpy_digests, effective, overrides, notes, source_only


def context(entries):
    candidates, translations = defaultdict(set), defaultdict(lambda: defaultdict(set))
    for archive, entry in entries:
        if not entry.name.lower().endswith(".rpyc"):
            continue
        try:
            script = parsed(entry.data)
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


def config_hints(entries):
    """Statements that may change loading/language, from inert PyCode text only."""
    hits = set()
    for archive, entry in entries:
        if not entry.name.lower().endswith(".rpyc"):
            continue
        for value in parsed(entry.data).slots[1].objects:
            if class_name(value) == ("renpy.ast", "PyCode"):
                state = value.data["state"]
                if state is None or state.value.kind != "tuple" or len(state.value.data) < 2:
                    continue
                try:
                    code = rpyc.expression(state.value.data[1])
                except ValueError:
                    continue
                if isinstance(code, str):
                    hits.update((archive, entry.name, m) for m in CONFIG_HINT.findall(code))
    return [{"archive": a, "name": n, "setting": f"config.{s}"} for a, n, s in sorted(hits)]


def languages(entries, loose_names):
    found = {language(e.name) for _, e in entries} | {language(n) for n in loose_names}
    for archive, entry in entries:
        if entry.name.lower().endswith(".rpyc"):
            script = parsed(entry.data)
            for value in script.slots[max(script.slots)].objects:
                if class_name(value) in (("renpy.ast", "TranslateString"), ("renpy.ast", "Translate"),
                                         ("renpy.ast", "TranslateSay")):
                    lang = scalar(attributes(value).get("language"))
                    if isinstance(lang, str):
                        found.add(lang)
    return found - {"original"}


def language(name):
    parts = name.split("/")
    return parts[1] if len(parts) > 2 and parts[0] == "tl" else "original"


def names_for(name, ctx):
    strings = ctx["languages"].get(language(name), {})
    return {key: strings.get(value, value) for key, value in ctx["base"].items()}


def json_names(entries, suffix=".rpyc"):
    scripts = [(a, e.name) for a, e in entries if e.name.lower().endswith(suffix)]
    stems = Counter(Path(n).stem.casefold() for _, n in scripts)
    counts, result = Counter(), {}
    for archive, name in scripts:
        stem = Path(name).stem
        if stems[stem.casefold()] > 1:
            if archive == LOOSE:
                parent = "_".join(Path(name).parent.parts)
                stem += "__" + (parent or LOOSE)
            else:
                stem += "__" + Path(archive).stem
        counts[stem.casefold()] += 1
        extra = "" if counts[stem.casefold()] == 1 else f"_{counts[stem.casefold()]}"
        result[archive, name] = stem + extra + ".json"
    flat_names(list(result.values()))
    return result


def original_path(archive, name):
    return f"original/loose/{name}" if archive == LOOSE else f"original/scripts/{archive}/{name}"


def tl_path(language_name, name):
    return f"tl/{language_name}/{name[:-1] if name.lower().endswith('.rpyc') else name}"


def _source_report(directory, sources, loose, rpy_digests, overrides, notes, source_only, effective, files):
    report = {"engine": "renpy", "source_directory": str(directory), "archives": [], "members": [],
              "loose": {"files": [], "rpy_md5": rpy_digests}, "overrides": overrides, "loader_notes": notes,
              "source_only_scripts": source_only, "loader": loader_hints(directory),
              "config_hints": config_hints(effective)}
    for archive, raw in sources.items():
        files[f"original/archives/{archive}"] = raw
        original = rpa.rebuild(raw, {})
        if original != raw:
            raise ValueError(f"RPA identity roundtrip differs: {archive}")
        files[f"rebuilt/roundtrip/game/{archive}"] = original
        report["archives"].append({"name": archive, "size": len(raw), "sha256": sha256(raw),
                                   "magic": raw[:7].decode("ascii"), "identity_verified": True})
    for name, raw in loose.items():
        files[f"original/loose/{name}"] = raw
        report["loose"]["files"].append({"name": name, "size": len(raw), "sha256": sha256(raw)})
    return report


def _warn_unresolved(report, unresolved):
    report["unresolved_speaker_rows"] = sum(unresolved.values())
    report["unresolved_speakers"] = dict(unresolved.most_common())
    warnings = report.setdefault("warnings", [])
    if unresolved:
        sample = ", ".join(f"{k}×{v}" for k, v in unresolved.most_common(8))
        warnings.append(f"{report['unresolved_speaker_rows']} row(s) have a speaker `who` without a resolved "
                        f"Character name ({len(unresolved)} speaker(s): {sample}). Select the archive holding the "
                        "Character definitions (often the rpy/script archive) together with the tl archives.")
    if report.get("source_only_scripts"):
        warnings.append(f"{len(report['source_only_scripts'])} loose .rpy script(s) have no RPYC and are not in this "
                        "workspace; use --rpy for them.")
    for w in warnings:
        print(f"WARNING: {w}", file=sys.stderr, flush=True)
    if not warnings:
        del report["warnings"]


def extract(directory, output, *, archives=(), loose=False, smoke_test=False, tl_language=None):
    directory, output = Path(directory), Path(output)
    validate_new_tree_destination(output)
    if not archives and not loose:
        raise ValueError("select --archives and/or --loose (loose RPYC under game/)")
    files = {"gt_output/.keep": b""}
    sources, loose_raw, rpy_digests, entries, overrides, notes, source_only = gather(directory, archives, include_loose=loose)
    print(f"Reading character/translation context from {sum(e.name.endswith('.rpyc') for _, e in entries)} RPYC files", flush=True)
    ctx = context(entries)
    files["metadata/context.json"] = json_bytes(ctx)
    report = _source_report(directory, sources, loose_raw, rpy_digests, overrides, notes, source_only, entries, files)
    for item in overrides:
        print(f"Override: loose game/{item['name']} replaces {item['shadowed']}:{item['name']}", flush=True)
    if tl_language is not None:
        report.update(mode="tl-new", profile=tl.PROFILE, language=tl_language)
        _extract_tl(report, files, entries, ctx, tl_language, smoke_test, discover_loose(directory))
    else:
        report.update(mode="rpyc", profile=rpyc.PROFILE)
        _extract_rpyc(report, files, sources, entries, ctx, smoke_test)
    files["reports/extraction.json"] = json_bytes(report)
    files["README.txt"] = readme(report).encode("utf-8")
    write_new_tree(output, list(files.items()))
    return report


def _common_report(report):
    report.update({"script_encoding": "Unicode strings serialized as UTF-8 in Pickle", "json_encoding": "utf-8",
                   "rows": 0, "json_files": 0, "scripts": 0, "runtime_verified": False, "growth_tests": [],
                   "name_policy": "context-only", "unresolved_speaker_rows": 0, "unresolved_speakers": {}})


def _extract_rpyc(report, files, sources, entries, ctx, smoke_test):
    _common_report(report)
    report["scope"] = "Say/TranslateSay.what, Menu.items labels, TranslateString.new; Python/screen/ATL strings excluded"
    mapping = json_names(entries)
    growth_members = defaultdict(dict)
    unresolved = Counter()
    for archive, entry in entries:
        detail = {"archive": archive, "name": entry.name, "size": len(entry.data), "sha256": sha256(entry.data)}
        report["members"].append(detail)
        if not entry.name.lower().endswith(".rpyc"):
            detail["status"] = "preserved-non-rpyc"
            continue
        try:
            script = parsed(entry.data)
            names = names_for(entry.name, ctx)
            rows, manifest = rpyc.export(script, filename=entry.name, names=names)
            original = rpyc.patch(script, rows, manifest, filename=entry.name, names=names)
            if original != entry.data:
                raise ValueError("RPYC identity bytes differ")
            files[original_path(archive, entry.name)] = entry.data
            detail.update(status="exported" if rows else "empty", count=len(rows), language=language(entry.name),
                          roles=dict(Counter(r["locator"]["role"] for r in manifest["records"])),
                          identity_verified=True, slots=sorted(script.slots))
            report["scripts"] += 1
            missing = Counter(r["locator"]["speaker"] for row, r in zip(rows, manifest["records"])
                              if isinstance(r["locator"]["speaker"], str) and "name" not in row
                              and r["locator"]["speaker"] not in BUILTIN_SPEAKERS)
            if missing:
                detail["unresolved_speaker_rows"] = sum(missing.values())
                unresolved.update(missing)
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
                    if archive == LOOSE:
                        files[f"rebuilt/growth-test/game/{entry.name}"] = modified
                    else:
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
    _warn_unresolved(report, unresolved)


def tl_plan(entries, ctx):
    """Per original-language script: (archive, entry, rows, locators, kept plan)."""
    seen_strings, identifiers, result = set(), {}, []
    for archive, entry in entries:
        if not entry.name.lower().endswith(".rpyc") or language(entry.name) != "original":
            continue
        try:
            script = parsed(entry.data)
            planned = tl.plan(script, filename=entry.name)
            rows, locators, kept = tl.rows(planned, names_for(entry.name, ctx), seen_strings)
        except ValueError as exc:
            raise type(exc)(f"RPYC {archive}:{entry.name}: {exc}") from exc
        for item in kept:
            if item["type"] == "block":
                key = item["identifier"].replace(".", "_")
                if key in identifiers:
                    raise ValueError(f"duplicate translation identifier {key} in {identifiers[key]} and {entry.name}")
                identifiers[key] = entry.name
        result.append((archive, entry, rows, locators, kept))
    if not result:
        raise ValueError("no original-language RPYC selected for a new tl language")
    return result


def tl_manifest(entry, rows, locators, language_name, ctx):
    return make_manifest(engine="renpy", variant=tl.PROFILE, reference="python/engines/renpy_tl.py",
                         sources={entry.name: entry.data}, rows=rows, locators=locators, encoding="utf-8",
                         settings={"language": language_name, "names": names_for(entry.name, ctx),
                                   "output": tl_path(language_name, entry.name)})


def _extract_tl(report, files, entries, ctx, language_name, smoke_test, loose_names):
    _common_report(report)
    report["scope"] = ("Default-language Translate/TranslateSay dialogue with compiled identifiers, and menu "
                       "captions as translate strings; Character names, screens and Python strings excluded")
    if not tl.source._WORD.fullmatch(language_name) or language_name == "None":
        raise ValueError("tl language must be a Ren'Py name such as schinese")
    existing = languages(entries, loose_names)
    if language_name in existing:
        raise ValueError(f"translation language {language_name!r} already exists; edit it with the RPYC workspace "
                         "instead of generating a second copy")
    report["existing_languages"] = sorted(existing)
    mapping = json_names([(a, e) for a, e in entries if language(e.name) == "original"])
    unresolved = Counter()
    for archive, entry, rows, locators, kept in tl_plan(entries, ctx):
        detail = {"archive": archive, "name": entry.name, "size": len(entry.data), "sha256": sha256(entry.data),
                  "count": len(rows), "blocks": sum(k["type"] == "block" for k in kept),
                  "strings": sum(k["type"] == "string" for k in kept), "output": tl_path(language_name, entry.name)}
        report["members"].append(detail)
        report["scripts"] += 1
        files[original_path(archive, entry.name)] = entry.data
        messages = [r["message"] for r in rows]
        text = tl.render(language_name, kept, messages)
        tl.verify(text, language_name, kept, messages, filename=detail["output"])
        unresolved.update(loc["speaker"] for row, loc in zip(rows, locators) if loc["kind"] == "say"
                          and loc["speaker"] and "name" not in row and loc["speaker"] not in BUILTIN_SPEAKERS)
        if not rows:
            detail["status"] = "empty"
            continue
        filename = mapping[archive, entry.name]
        manifest = tl_manifest(entry, rows, locators, language_name, ctx)
        files[f"gt_input/{filename}"] = dump_rows(rows)
        files[f"metadata/{filename}"] = json_bytes(manifest)
        detail.update(status="exported", outputs={"json": filename}, identity_verified=True)
        report["rows"] += len(rows)
        report["json_files"] += 1
        if smoke_test:
            changed = list(messages)
            changed[0] += " 这是中文显示与长度增长测试。"
            text = tl.render(language_name, kept, changed)
            tl.verify(text, language_name, kept, changed, filename=detail["output"])
            files[f"rebuilt/growth-test/game/{detail['output']}"] = text.encode("utf-8")
            report["growth_tests"].append({"name": entry.name, "json": filename, "row": 0, "output": detail["output"]})
        print(f"Planned tl/{language_name}: {archive}:{entry.name}, {len(rows)} rows", flush=True)
    report["identity_verified"] = report["json_files"]
    report["empty_scripts"] = sum(m.get("status") == "empty" for m in report["members"])
    _warn_unresolved(report, unresolved)


def readme(report):
    head = {"rpyc": "Ren'Py RPYC2 提取结果（原位改写）", "tl-new": f"Ren'Py 新建 tl/{report.get('language')} 翻译语言"}
    text = [head.get(report.get("mode"), "Ren'Py 提取结果"), "",
            "gt_input：平铺 UTF-8 JSON；同名脚本以来源后缀区分，映射见 reports/extraction.json。",
            "gt_output：译文按同名文件放回后告诉 agent，由 agent 校验并回包，无需手动执行命令。",
            "name 仅是只读人物上下文；不要翻译变量 ID，也不要改动它。保留顺序和文本控制码；显示换行可自行增删。"]
    if report.get("mode") == "tl-new":
        text += ["对白按编译脚本中的 translate identifier 生成 translate 块；菜单选项写入 translate strings，",
                 "同一选项文本在一种语言里只能有一个译文，因此只在首次出现处导出。",
                 "原文与原有 tl 语言不被修改；回包输出 new-language/game/tl/<语言>/，部署后需在游戏中选择该语言。"]
    else:
        text += ["提取对白、菜单、翻译表 new；不扫描 Python、screen、ATL 中的任意字符串。",
                 "原始语言和 tl/<语言> 是不同套文本；要测试哪种语言，就编辑对应 JSON 并在游戏选择该语言。",
                 "rebuilt/roundtrip 为经过读写且逐字节一致的归档；rebuilt/growth-test 若存在，是离线测试，不是正式译文。",
                 "pack 输出 changed-archives/game 下同名完整归档及 loose/game 下对应编译脚本。",
                 "松散 game/ 文件在 Ren'Py 中先于归档加载（除非 config.force_archives）；覆盖关系见 reports 的 overrides。"]
    text += ["original、metadata 不要修改。文字以 UTF-8 存储，无需 JIS；缺字时检查游戏字体覆盖。",
             "所有验证均为离线读写，未启动游戏、未覆盖原游戏文件，实际加载与显示仍需用户确认。"]
    return "\n".join(text) + "\n"


def _load_workspace(workspace):
    report = load_json(read_bounded(workspace / "reports/extraction.json"))
    if report.get("engine") != "renpy":
        raise ValueError("unsupported Ren'Py workspace profile")
    archive_names = [a["name"] for a in report["archives"]]
    sources, entries = load_archives(workspace / "original/archives", archive_names) if archive_names else ({}, [])
    for a in report["archives"]:
        raw = sources[a["name"]]
        if len(raw) != a["size"] or sha256(raw) != a["sha256"]:
            raise ValueError("Ren'Py source archive hash/size changed")
    loose_info = report.get("loose", {"files": [], "rpy_md5": {}})
    loose = load_loose(workspace / "original/loose", [f["name"] for f in loose_info["files"]])
    for f in loose_info["files"]:
        if len(loose[f["name"]]) != f["size"] or sha256(loose[f["name"]]) != f["sha256"]:
            raise ValueError("Ren'Py source loose script hash/size changed")
    shadowed = {(o["shadowed"], o["name"]) for o in report.get("overrides", [])}
    selected = [(a, e) for a, e in entries if (a, e.name) not in shadowed]
    effective = selected + [(LOOSE, rpa.Entry(n, raw, 0, 0)) for n, raw in loose.items()]
    ctx = context(effective)
    if load_json(read_bounded(workspace / "metadata/context.json")) != ctx:
        raise ValueError("Ren'Py character context changed")
    return report, sources, effective, ctx


def _gt_output(workspace, expected):
    flat_names(list(expected))
    _check_existing_ancestors(workspace / "gt_output")
    available = {p.name for p in (workspace / "gt_output").iterdir() if p.suffix.lower() == ".json"}
    if available - expected:
        raise ValueError(f"unmatched Ren'Py translation files: {sorted(available - expected)}")
    return available


def pack(workspace, output, *, font=None):
    workspace, output = Path(workspace), Path(output)
    validate_new_tree_destination(output)
    report = load_json(read_bounded(workspace / "reports/extraction.json"))
    mode = report.get("mode", "rpyc")
    if mode == "rpy":
        from . import renpy_source
        return renpy_source.pack(workspace, output)
    if mode == "tl-new":
        return _pack_tl(workspace, output, font)
    if font is not None:
        raise ValueError("--font applies only to a new tl language workspace")
    if report.get("profile") != rpyc.PROFILE:
        raise ValueError("unsupported Ren'Py workspace profile")
    report, sources, entries, ctx = _load_workspace(workspace)
    mapping = json_names(entries)
    expected = {m["outputs"]["json"] for m in report["members"] if m["status"] == "exported"}
    available = _gt_output(workspace, expected)
    files, replacements, verified, changed = {}, defaultdict(dict), 0, []
    actual_expected, errors = set(), []
    for archive, entry in entries:
        if not entry.name.lower().endswith(".rpyc"):
            continue
        script = parsed(entry.data)
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
        try:
            modified = rpyc.patch(script, rows, manifest, filename=entry.name, names=names, label=filename)
        except rpyc.TranslationErrors as exc:
            # Keep checking other files so every problem is listed at once.
            errors.extend(exc.errors)
            continue
        verified += 1
        if modified != entry.data:
            if archive != LOOSE:
                replacements[archive][entry.name] = modified
            files[f"loose/game/{entry.name}"] = modified
            changed.append({"archive": archive, "name": entry.name, "json": filename,
                            "source_sha256": sha256(entry.data), "output_sha256": sha256(modified),
                            "changed_rows": sum(a != b for a, b in zip(original, rows))})
    if actual_expected != expected:
        raise ValueError("Ren'Py workspace export set differs from source")
    if errors:
        raise rpyc.TranslationErrors(errors)
    for archive, members in replacements.items():
        rebuilt = rpa.rebuild(sources[archive], members)
        check = {e.name: e.data for e in rpa.extract(rebuilt, max_archive_size=MAX_ARCHIVE, max_total_size=MAX_ARCHIVE)}
        if any(check[name] != data for name, data in members.items()):
            raise ValueError(f"rebuilt archive read-back differs: {archive}")
        files[f"changed-archives/game/{archive}"] = rebuilt
    for name, data in files.items():
        if name.startswith("loose/game/"):
            rpyc.parse(data)
    result = {"engine": "renpy", "profile": rpyc.PROFILE, "verified_json": verified,
              "changed": changed, "archives": list(replacements), "runtime_verified": False,
              "overrides": report.get("overrides", []),
              "deployment": ("Archive members: same-name archives under game/ in a backed-up game copy, or loose/game "
                             "files (loose wins unless config.force_archives). Loose-source scripts: loose/game only.")}
    files["reports/pack.json"] = json_bytes(result)
    files["README.txt"] = ("Ren'Py 回包结果\n\n"
        "changed-archives/game：已重建的同名完整归档，包含未修改的其他成员（仅来自归档的脚本）。\n"
        "loose/game：改动的 RPYC，保留 game/ 下相对路径；原本就是松散文件的脚本只有这一种输出。\n"
        "同一脚本两种方式择一。松散文件先于归档加载（config.force_archives 为真时除外）。\n"
        "先在游戏副本备份原文件，再按 game/ 对应位置部署。不要擅自改名为 patch.rpa。\n"
        "确保游戏语言与编辑的 original/tl 语言一致；同名松散 .rpy 的 MD5 与 RPYC 末尾摘要不符时 Ren'Py 会改用 .rpy。\n"
        "已完成双槽文本、非文本对象图与归档重新解析验证；未执行游戏。\n"
        "UTF-8 无需 JIS。先检查少量中文、菜单与存读档；缺字时检查实际使用字体。\n").encode("utf-8")
    write_new_tree(output, list(files.items()))
    return result


def _pack_tl(workspace, output, font):
    report, sources, entries, ctx = _load_workspace(workspace)
    if report.get("profile") != tl.PROFILE:
        raise ValueError("unsupported Ren'Py tl workspace profile")
    language_name = report["language"]
    mapping = json_names([(a, e) for a, e in entries if language(e.name) == "original"])
    expected = {m["outputs"]["json"] for m in report["members"] if m.get("status") == "exported"}
    available = _gt_output(workspace, expected)
    files, errors, written, actual = {}, [], [], set()
    for archive, entry, rows, locators, kept in tl_plan(entries, ctx):
        if not rows:
            continue
        filename = mapping[archive, entry.name]
        actual.add(filename)
        manifest = tl_manifest(entry, rows, locators, language_name, ctx)
        if load_json(read_bounded(workspace / "gt_input" / filename)) != rows:
            raise ValueError(f"gt_input changed: {filename}; preserve edits in gt_output then restore from original data")
        if load_json(read_bounded(workspace / "metadata" / filename)) != manifest:
            raise ValueError(f"Ren'Py member manifest changed: {filename}")
        if filename not in available:
            continue
        translated = load_json(read_bounded(workspace / "gt_output" / filename))
        try:
            translated = validate_translation(manifest, {entry.name: entry.data}, rows, translated)
        except ValueError as exc:
            detail = re.sub(r"^row (\d+): ", r"#\1: ", str(exc))
            errors.append(f"{filename} {detail}" if detail.startswith("#") else f"{filename}: {detail}")
            continue
        bad = False
        for index, (before, after) in enumerate(zip(rows, translated)):
            if before["message"] == after["message"]:
                continue
            reason = rpyc.row_error(before["message"], after["message"])
            if reason is None:
                try:
                    tl.source.encode_say(after["message"])
                except ValueError as exc:
                    reason = str(exc)
            if reason:
                errors.append(f"{filename} #{index}: {reason}")
                bad = True
        if bad:
            continue
        messages = [r["message"] for r in translated]
        path = tl_path(language_name, entry.name)
        text = tl.render(language_name, kept, messages)
        tl.verify(text, language_name, kept, messages, filename=path)
        files[f"new-language/game/{path}"] = text.encode("utf-8")
        written.append({"name": entry.name, "json": filename, "output": path, "rows": len(rows),
                        "changed_rows": sum(a["message"] != b["message"] for a, b in zip(rows, translated)),
                        "identifiers": sum(k["type"] == "block" for k in kept),
                        "strings": sum(k["type"] == "string" for k in kept)})
    if actual != expected:
        raise ValueError("Ren'Py workspace export set differs from source")
    if errors:
        raise rpyc.TranslationErrors(errors)
    if font is not None:
        script = tl.font_script(language_name, font)
        parsed = tl.parse(script)
        if [b["type"] for b in parsed] != ["python"] or tl.source.extract(script[1:], filename="font.rpy"):
            raise ValueError("font stub read-back differs")
        files[f"new-language/game/tl/{language_name}/gt_font.rpy"] = script.encode("utf-8")
    result = {"engine": "renpy", "profile": tl.PROFILE, "language": language_name, "verified_json": len(written),
              "written": written, "font_stub": font, "runtime_verified": False,
              "deployment": f"Copy new-language/game/tl/{language_name} into game/tl/ of a backed-up game copy, "
                            "then select the language (Language action, config.language or RENPY_LANGUAGE)."}
    files["reports/pack.json"] = json_bytes(result)
    files["README.txt"] = (f"Ren'Py 新语言 tl/{language_name}\n\n"
        f"new-language/game/tl/{language_name}：新增的 .rpy 翻译文件，不修改原文和原有语言；复制到游戏 game/tl/ 下。\n"
        "Ren'Py 首次启动会编译这些 .rpy（需要 game/ 可写）。\n"
        f"启用：游戏自带语言菜单（Language(\"{language_name}\") 动作），或在新增脚本中设置 config.language，\n"
        f"或启动前设置环境变量 RENPY_LANGUAGE={language_name}。优先级：环境变量 > config.language > 玩家设置。\n"
        "字体：原字体缺中文时需提供中文字体；--font 生成的 gt_font.rpy 在 translate python 中设置 gui 字体，\n"
        "只适用于使用 gui 变量的工程。未提供 identifier 的句子不会生成。\n"
        "已完成 tl 文件重解析与 identifier、译文核对；未启动游戏，语言切换与显示仍需确认。\n").encode("utf-8")
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
    extract_parser.add_argument("--archives", nargs="+", default=[])
    extract_parser.add_argument("--loose", action="store_true", help="include loose game/**/*.rpyc")
    extract_parser.add_argument("--tl-language", help="generate a new game/tl/<language> from compiled identifiers")
    extract_parser.add_argument("--rpy", action="store_true", help="loose .rpy source workspace")
    extract_parser.add_argument("--speakers", nargs="+", default=[], help="extra Character variables for --rpy")
    extract_parser.add_argument("--smoke-test", action="store_true")
    pack_parser = commands.add_parser("pack")
    pack_parser.add_argument("workspace")
    pack_parser.add_argument("output")
    pack_parser.add_argument("--font", help="tl only: relative game font path for translate python gui fonts")
    args = parser.parse_args()
    try:
        if args.command == "scan":
            result = scan(args.directory)
        elif args.command == "extract":
            if args.rpy:
                if args.archives or args.loose or args.tl_language or args.smoke_test:
                    raise ValueError("--rpy cannot be combined with --archives/--loose/--tl-language/--smoke-test")
                from . import renpy_source
                result = renpy_source.extract(args.directory, args.output, speakers=args.speakers)
            else:
                if args.speakers:
                    raise ValueError("--speakers applies only to --rpy")
                result = extract(args.directory, args.output, archives=args.archives, loose=args.loose,
                                 smoke_test=args.smoke_test, tl_language=args.tl_language)
            result = {k: result[k] for k in ("mode", "scripts", "json_files", "rows", "empty_scripts", "identity_verified",
                                              "unresolved_speaker_rows", "overrides", "runtime_verified") if k in result}
        else:
            result = pack(args.workspace, args.output, font=args.font)
    except (ValueError, OSError) as exc:
        # Readable diagnostics instead of a traceback; nothing was written.
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
