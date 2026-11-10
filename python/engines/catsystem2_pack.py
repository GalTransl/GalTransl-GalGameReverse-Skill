"""CatSystem2 workspace -> new ``updateNN.int`` patch archive, and its readback.

``pack`` validates gt_output against the extraction workspace, patches only the
CST members whose bytes change, writes them under their real member names into
one new update archive (encryption mirrored from the archive that currently
provides those members), re-reads that archive and reparses every CST.
``read_back`` overlays the new archive on the workspace originals and exports
the full gt_input set into a separate new directory (JIS finalize step 3).
Game files are only read; nothing is executed or overwritten.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat

from python.archives.catsystem2_int import (detect_int_layout, encode_passphrase,
                                            extract_exe_password, read_int, read_member,
                                            verify_int, write_int)
from python.common.binary import FormatError
from python.common.contract import dump_rows, load_json, sha256, validate_translation
from python.common.safety import (Limits, _check_existing_ancestors, validate_names,
                                  validate_new_tree_destination, write_new_tree)
from python.engines.catsystem2 import export_cst, patch_dialogue

UPDATE_NAME = re.compile(r"^update(\d+)\.int$", re.IGNORECASE)
REBUILD_SIDECARS = frozenset({"reports/verification.json", "README.txt"})
_MAX_JSON = 64 * 1024 * 1024
_MAX_CST = 64 * 1024 * 1024
_MAX_PACK = 512 * 1024 * 1024
_MAX_TRANSLATIONS = 100_000


def _json(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


_CHECKED_PARENTS: set[str] = set()


def _read(path: Path, limit: int = _MAX_JSON) -> bytes:
    path = Path(path)
    parent = os.path.normcase(os.path.abspath(path.parent))
    if parent not in _CHECKED_PARENTS:
        _check_existing_ancestors(path.parent)
        _CHECKED_PARENTS.add(parent)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise FormatError(f"CatSystem2 input must be an ordinary file: {path}")
    if info.st_size > limit:
        raise FormatError(f"CatSystem2 input exceeds budget: {path}")
    with path.open("rb") as stream:
        # read(n) preallocates n bytes: size it from lstat, still bounded.
        data = stream.read(info.st_size + 1)
    if len(data) != info.st_size:
        raise FormatError(f"CatSystem2 input changed size: {path}")
    return data


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _inside(path, root) -> bool:
    path, root = os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.abspath(root))
    try:
        return os.path.commonpath([path, root]) == root
    except ValueError:
        return False


def _identity(member: str) -> str:
    return member.replace("\\", "/").casefold()


def update_number(name: str) -> int | None:
    match = UPDATE_NAME.fullmatch(name)
    return int(match.group(1)) if match else None


def overlay_order(name: str):
    """Extraction overlay order: base archives, then numeric updateNN (later wins)."""
    number = update_number(name)
    return (1, number, name.casefold()) if number is not None else (0, 0, name.casefold())


class _Workspace:
    """Extraction workspace reports, validated once."""

    def __init__(self, root):
        self.root = Path(root)
        self.summary = load_json(_read(self.root / "reports/summary.json"))
        if not isinstance(self.summary, dict) or self.summary.get("engine") != "catsystem2":
            raise FormatError("not a CatSystem2 extraction workspace")
        outputs = load_json(_read(self.root / "reports/outputs.json"))
        self.archives = load_json(_read(self.root / "reports/archives.json"))
        self.outputs = {}
        self.by_member = {}
        for record in outputs.get("outputs", []):
            name = record["output"].rsplit("/", 1)[-1]
            validate_names([record["output"], record["original"], record["metadata"]])
            if name in self.outputs or not record["output"].startswith("gt_input/"):
                raise FormatError(f"ambiguous workspace output: {record['output']}")
            self.outputs[name] = record
            identity = _identity(record["member"])
            if identity in self.by_member:
                raise FormatError(f"duplicate effective member in workspace: {record['member']}")
            self.by_member[identity] = record
        self.archive_reports = {r["archive"].casefold(): r for r in self.archives}

    def source(self, record) -> tuple[dict, bytes, list]:
        manifest = load_json(_read(self.root / record["metadata"]))
        raw = _read(self.root / record["original"], _MAX_CST)
        rows = load_json(_read(self.root / record["output"]))
        source = manifest["sources"][0]
        if len(manifest["sources"]) != 1 or source["path"] != record["original"] \
                or source["sha256"] != sha256(raw):
            raise FormatError(f"workspace original CST changed: {record['original']}")
        if list(export_cst(raw).rows) != rows:
            raise FormatError(f"{record['output']}: gt_input differs from the current CatSystem2 "
                              "export (older extractor format); re-extract into a new workspace")
        return manifest, raw, rows


def _game_root(workspace: _Workspace, game_root) -> Path:
    root = Path(game_root if game_root is not None else workspace.summary.get("game_root", ""))
    if not root.is_dir():
        raise FormatError("CatSystem2 game root is not a directory; pass --game")
    return root


def _key(game_root: Path, *, exe=None, password=None, key=None) -> int:
    if key is not None:
        return key
    if password is not None:
        return encode_passphrase(password)
    exe_path = Path(exe) if exe is not None else game_root / "cs2.exe"
    if not exe_path.is_absolute():
        exe_path = game_root / exe_path
    if not exe_path.is_file():
        raise FormatError("encrypted CatSystem2 INT needs --password or a readable --exe")
    return encode_passphrase(extract_exe_password(exe_path))


def _existing_updates(game_root: Path, workspace: _Workspace) -> tuple[dict[int, str], list[str]]:
    """All update numbers (game + workspace) and game updates the workspace never scanned."""
    found, unscanned = {}, []
    for path in game_root.iterdir():
        number = update_number(path.name)
        if number is not None and path.is_file():
            found[number] = path.name
            report = workspace.archive_reports.get(path.name.casefold())
            if report is None:
                unscanned.append(path.name)
            elif report.get("size") != path.stat().st_size:
                raise FormatError(f"{path.name} in the game differs from the extraction workspace; "
                                  "re-extract before packing so overlays stay correct")
    for report in workspace.archives:
        number = update_number(report["archive"])
        if number is not None:
            found.setdefault(number, report["archive"])
    return found, sorted(unscanned, key=overlay_order)


def choose_update_name(existing: dict[int, str], number: int | None = None) -> str:
    """Next ``updateNN.int`` above every existing one (two digits, as ``update??.INT``)."""
    highest = max(existing, default=0)
    if number is None:
        number = highest + 1
    if type(number) is not int or not 0 <= number <= 99:
        raise FormatError("CatSystem2 update number must be 0..99 (update??.int)")
    if number in existing:
        raise FormatError(f"update{number:02d}.int already exists; choose a new number")
    if number <= highest:
        raise FormatError(f"update{number:02d}.int would load before {existing[highest]}; "
                          "use a number above every existing update archive")
    return f"update{number:02d}.int"


def _translation_files(directory: Path) -> dict[str, Path]:
    _check_existing_ancestors(directory)
    files = {}
    for path in directory.iterdir():
        if len(files) > _MAX_TRANSLATIONS:
            raise FormatError("too many translation files")
        if path.suffix.lower() == ".json":
            files[path.name] = path
    validate_names(list(files))
    return files


def pack(workspace, output, *, game_root=None, exe=None, password=None, number=None,
         translations=None, readback=None) -> dict:
    """Write ``output/updateNN.int`` + ``reports/verification.json`` (new directory)."""
    _CHECKED_PARENTS.clear()
    workspace_root, output = Path(workspace), Path(output)
    validate_new_tree_destination(output)
    if _inside(output, workspace_root) or _inside(workspace_root, output):
        raise FormatError("pack output must be outside the workspace")
    if readback is not None:
        readback = Path(readback)
        validate_new_tree_destination(readback)
        for root in (workspace_root, output):
            if _inside(readback, root) or _inside(root, readback):
                raise FormatError(f"readback output must be outside {root}")
    ws = _Workspace(workspace_root)
    game = _game_root(ws, game_root)
    if _inside(output, game) or (readback is not None and _inside(readback, game)):
        raise FormatError("never write CatSystem2 outputs into the game directory")
    source_dir = Path(translations) if translations is not None else workspace_root / "gt_output"
    available = _translation_files(source_dir)
    unknown = sorted(set(available) - set(ws.outputs))
    if unknown:
        raise FormatError(f"translation files without a workspace script: {unknown[:10]}")

    changed, unchanged = [], []
    for filename in sorted(available):
        record = ws.outputs[filename]
        manifest, raw, rows = ws.source(record)
        translated = load_json(_read(available[filename]))
        try:
            checked = validate_translation(manifest, {record["original"]: raw}, rows, translated)
            patched = patch_dialogue(raw, export_cst(raw), checked)
        except ValueError as error:
            raise FormatError(f"{filename}: {error}") from error
        if patched == raw:
            unchanged.append(filename)
            continue
        if not manifest["settings"].get("effective_overlay", True):
            raise FormatError(f"{filename}: member name was not recovered; cannot overlay")
        changed.append((record, patched, checked))
    if not changed:
        raise FormatError("no CST changed; nothing to pack")

    sources = sorted({r["archive"] for r, _, _ in changed}, key=overlay_order)
    template_name = sources[-1]
    template_path = game / template_name
    report = ws.archive_reports.get(template_name.casefold())
    if report is None or not template_path.is_file() or report.get("sha256") is None \
            or _sha256_file(template_path) != report["sha256"]:
        raise FormatError(f"{template_name} in the game differs from the extraction workspace")
    existing, unscanned = _existing_updates(game, ws)
    archive_name = choose_update_name(existing, number)
    cached = []

    def name_key():
        if not cached:
            cached.append(_key(game, exe=exe, password=password))
        return cached[0]

    with template_path.open("rb") as stream:
        probe = read_int(stream)
        key = name_key() if probe.encrypted else None
        template = read_int(stream, key=key)
        layout = detect_int_layout(stream, template)
    by_index = {e.index: e for e in template.entries}
    for record, _, _ in changed:
        if record["archive"] != template_name:
            continue
        entry = by_index.get(record["member_index"])
        if entry is None or entry.name != record["member"]:
            raise FormatError("INT password does not recover the workspace member names")
    changed_ids = {_identity(r["member"]) for r, _, _ in changed}
    for name in unscanned:
        # An update the workspace never scanned must not hold a newer copy of a
        # member we are about to replace with a patch of an older one.
        with (game / name).open("rb") as stream:
            other = read_int(stream, key=name_key() if read_int(stream).encrypted else None)
        if not other.names_recovered:
            raise FormatError(f"{name}: member names unknown; re-extract including it")
        overlap = sorted(e.name for e in other.entries if _identity(e.name) in changed_ids)
        if overlap:
            raise FormatError(f"{name} (not in the workspace) also provides {overlap[:5]}; "
                              "re-extract including it")

    members = sorted(((r["member"], data) for r, data, _ in changed), key=lambda m: m[0].casefold())
    options = dict(encrypted=layout.encrypted, record_prefix=layout.record_prefix,
                   name_size=layout.name_size)
    if layout.encrypted:
        options.update(key=key, seed=layout.seed, key_slot=layout.key_slot)
    packed = write_int(members, max_total=_MAX_PACK, **options)

    # Independent readback of the bytes that will be written.
    expected = {_identity(r["member"]): (r, data, rows) for r, data, rows in changed}
    stream = io.BytesIO(packed)
    archive = verify_int(stream, members, key=key, record_prefix=layout.record_prefix)
    verified = []
    for entry in archive.entries:
        record, data, rows = expected[_identity(entry.name)]
        payload = read_member(stream, entry, archive.cipher, max_member=_MAX_CST)
        if payload != data or list(export_cst(payload).rows) != list(rows):
            raise FormatError(f"packed CST readback differs: {entry.name}")
        verified.append({"member": entry.name, "json": record["output"].rsplit("/", 1)[-1],
                         "replaces_archive": record["archive"], "rows": len(rows),
                         "sha256": sha256(payload)})
    result = {
        "engine": "catsystem2", "mode": "pack", "archive": archive_name,
        "sha256": sha256(packed), "size": len(packed), "encrypted": layout.encrypted,
        "layout_template": template_name, "record_prefix": layout.record_prefix,
        "name_size": layout.name_size,
        "seed_and_key_slot": "copied from template" if layout.encrypted else None,
        "existing_updates": [existing[n] for n in sorted(existing)],
        "unscanned_updates_checked": unscanned,
        "overlay_rule": "numeric updateNN.int after base archives; later number wins "
                        "(cs2.exe enumerates update??.INT); not verified in game",
        "changed_members": verified, "translated_files": sorted(available),
        "unchanged_translation_files": unchanged,
        "int_readback_verified": True, "cst_reparse_verified": True,
        "runtime_verified": False, "script_encoding": "cp932",
    }
    readme = ("CatSystem2 补丁包\n"
              f"{archive_name} 只含有改动的 CST，成员使用原名；放到游戏 EXE 同目录即可按 update 编号覆盖同名成员。\n"
              "已用 reader 读回并重新解析 CST；未运行游戏，加载顺序与显示仍需游戏内确认。\n"
              "不要覆盖已有 update*.int；部署前备份。使用 JIS 流程时请部署 finalize 交付目录。\n")
    write_new_tree(output, [(archive_name, packed), ("reports/verification.json", _json(result)),
                            ("README.txt", readme.encode("utf-8"))],
                   Limits(max_entries=8, max_file_bytes=_MAX_PACK, max_total_bytes=_MAX_PACK + _MAX_JSON))
    if readback is not None:
        result["readback"] = read_back(workspace_root, output, readback, game_root=game,
                                       exe=exe, password=password, key=key)["readback"]
    return result


def _rebuilt_archive(rebuilt: Path) -> Path:
    _check_existing_ancestors(rebuilt)
    found, pending = [], [rebuilt]
    while pending:
        for path in pending.pop().iterdir():
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise FormatError(f"linked entry in rebuilt directory: {path}")
            if stat.S_ISDIR(info.st_mode):
                pending.append(path)
            else:
                found.append(path.relative_to(rebuilt).as_posix())
            if len(found) > 16:
                raise FormatError("CatSystem2 rebuilt directory has too many files")
    archives = [n for n in found if "/" not in n and update_number(n) is not None]
    unknown = sorted(set(found) - set(archives) - REBUILD_SIDECARS)
    if unknown or len(archives) != 1:
        raise FormatError(f"rebuilt directory must hold one updateNN.int (unknown: {unknown})")
    return rebuilt / archives[0]


def read_back(workspace, rebuilt, output, *, game_root=None, exe=None, password=None,
              key=None) -> dict:
    """Overlay the rebuilt update archive on workspace originals; export all JSON."""
    _CHECKED_PARENTS.clear()
    workspace_root, rebuilt, output = Path(workspace), Path(rebuilt), Path(output)
    validate_new_tree_destination(output)
    for root in (workspace_root, rebuilt):
        if _inside(output, root) or _inside(root, output):
            raise FormatError(f"readback output must be outside {root}")
    ws = _Workspace(workspace_root)
    path = _rebuilt_archive(rebuilt)
    later_than = [r["archive"] for r in ws.archives if overlay_order(r["archive"]) >= overlay_order(path.name)]
    if later_than:
        raise FormatError(f"{path.name} does not load after {later_than}; overlay would not apply")
    if path.stat().st_size > _MAX_PACK:
        raise FormatError("rebuilt INT exceeds budget")
    replaced = {}
    with path.open("rb") as stream:
        archive = read_int(stream)
        if archive.encrypted:
            if key is None:
                key = _key(_game_root(ws, game_root), exe=exe, password=password)
            archive = read_int(stream, key=key)
        for entry in archive.entries:
            identity = _identity(entry.name)
            if identity not in ws.by_member:
                raise FormatError(f"rebuilt member is not an exported workspace script: {entry.name}")
            if identity in replaced:
                raise FormatError(f"duplicate member in rebuilt INT: {entry.name}")
            replaced[identity] = read_member(stream, entry, archive.cipher, max_member=_MAX_CST)
    files, rows_total = {}, 0
    for filename, record in sorted(ws.outputs.items()):
        raw = replaced.get(_identity(record["member"]))
        if raw is None:
            _, raw, _ = ws.source(record)
        rows = list(export_cst(raw).rows)
        files["gt_input/" + filename] = dump_rows(rows)
        rows_total += len(rows)
    result = {"engine": "catsystem2", "mode": "readback", "archive": path.name,
              "sha256": _sha256_file(path), "replaced_members": len(replaced), "rows": rows_total,
              "readback": {"workspace": str(workspace_root), "rebuilt": str(path),
                           "output": str(output), "json_files": len(files)},
              "runtime_verified": False}
    files["reports/readback.json"] = _json(result)
    files["README.txt"] = ("CatSystem2 回读：工作区原 CST 叠加新 update 包后重新导出。\n"
                           "gt_input 仅供核对（如 JIS finalize），不是翻译输入，也不随补丁发布。\n").encode("utf-8")
    write_new_tree(output, list(files.items()))
    return result
