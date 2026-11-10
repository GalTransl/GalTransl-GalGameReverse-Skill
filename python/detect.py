"""Read-only, bounded game-directory triage, NOT format validation.

Run from any directory: python /path/to/skill/python/detect.py GAME_DIRECTORY
Header facts derive from the format sources recorded in provenance/sources.json.
Only lists candidates: extensions, filenames and magic do not establish that a
specific parser, encryption scheme, script writer or patch loading route works.
Derived trees (this skill's *_extract workspaces, third-party *_Output dumps)
are skipped by default; pass --include-derived to scan them too.
Every read is capped (head/footer probes, PE headers, BGI indexes, duplicate
head hashes); nothing found in the game directory is executed or loaded.
"""

import argparse
import codecs
import hashlib
import heapq
import json
import os
from pathlib import Path
import re
import stat
import struct
import sys
import time

# Support an explicit absolute-path CLI invocation without an installation.
# Importing python.detect does not modify the module search path.
if __name__ == "__main__" and __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from python.engines.artemis_scp import looks_like_script

# (full known prefix or explicitly partial hint, engine id, explanation)
MAGICS = (
    (b"XP3\r\n \n\x1a\x8bg\x01", "kirikiri", "XP3 header; encryption/filter not determined"),
    (b"RPA-3.0 ", "renpy", "RPA-3.0 header; validate index and chunk layout"),
    (b"ARC-3.0 ", "renpy", "ARC-3.0 header: renamed RPA-3.0; validate index, XOR key and chunk layout"),
    (b"RPA-3.2 ", "renpy", "RPA-3.2 header; bundled reader accepts only RPA-3.0/ARC-3.0"),
    (b"RPA-2.0 ", "renpy", "RPA-2.0 header (no XOR key); bundled reader accepts only RPA-3.0/ARC-3.0"),
    (b"pf8", "artemis", "PFS pf8 prefix; validate index before using SHA-1 XOR"),
    (b"pf6", "artemis", "PFS pf6 prefix; validate table and filename encoding"),
    (b"pf2", "artemis", "PFS pf2 prefix; distinct table layout"),
    (b"pf0", "artemis", "PFS pf0 prefix; distinct table layout"),
    (b"ASB\0\0", "artemis", "Artemis ASB prefix; not AZSystem solely from .asb"),
    (b"MajiroArcV", "majiro", "Majiro archive family prefix; version not validated"),
    (b"MajiroObjV1.000", "majiro", "Majiro plaintext object signature"),
    (b"MajiroObjX1.000", "majiro", "Majiro encrypted object signature"),
    (b"PackFile    ", "bgi", "BGI archive v1 signature"),
    (b"BURIKO ARC20", "bgi", "BGI archive v2 signature"),
    (b"BurikoCompiledScriptVer1.00\0", "bgi", "BGI compiled scenario header"),
    (b"DSC FORMAT 1.00\0", "bgi", "BGI DSC compressed wrapper; payload may be script, animation, or another resource"),
    (b"CatScene", "catsystem2", "CST scene header; verify compression and offsets"),
    (b"CSTL", "catsystem2", "CSTL language table prefix"),
    (b"KIF\0", "catsystem2", "INT archive prefix; encryption unknown"),
    (b"TJS2100\0", "kirikiri", "compiled TJS2, not source-text TJS"),
    (b"TJS/ns0\0", "kirikiri", "NS0 compiled structure, not dialogue JSON"),
    (b"TJS/4s0\0", "kirikiri", "4S0 compiled structure, not dialogue JSON"),
    (b"YSTB", "yuris", "YU-RIS scenario; command metadata may be required"),
    (b"YSCF", "yuris", "YU-RIS configuration table, not necessarily dialogue"),
    (b"YSCM", "yuris", "YU-RIS command table"),
    (b"ESCR1_00", "escude", "Escu:de script header"),
    (b"ESC-ARC2", "escude", "Escu:de archive header"),
    (b"\0DLR", "exhibit", "RLD script header; check key and defChara.rld"),
    (b"NORI", "hexenhaus", "NORI wrapper; fixed slots are not resizable"),
    (b"Sv20", "softpal", "Softpal SRC; TEXT.DAT and POINT.DAT may be needed"),
    (b"SHSysSC\0", "shsystem", "ShSystem; source reference has no whole-file writer"),
    (b"[SCR-MESSAGE]ver4.0", "kaguya", "KaGuYa message.dat v4 signature"),
    (b"YKC001", "yuka", "YKC001 archive prefix"),
    (b"YKC002", "yuka", "YKC002 archive prefix; differs from writer v1"),
    (b"\xcd\x32\x6e\x59", "rugp", "rUGP RIO object signature; schema/key/script roles unverified"),
    (b"MDN0", "med", "MED MDN0 container; only plain MDN0 script archives (often md_scr.med) have a writer"),
    (b"MDE0", "med", "MED MDE0 container; encrypted members, no writer for this magic"),
)
# Version-bearing heads handled by dedicated probes below: YPF\0, Entis, UnityFS,
# Unity serialized files and the QLIE FilePackVer footer.

EXTENSIONS = {
    ".xp3": ("kirikiri",), ".ks": ("kirikiri", "tyrano"), ".tjs": ("kirikiri",),
    ".rpa": ("renpy",), ".rpy": ("renpy",), ".rpyc": ("renpy",),
    ".pfs": ("artemis",), ".ast": ("artemis",), ".asb": ("artemis", "azsystem"),
    ".iet": ("artemis", "artemis-scp"),
    ".mjo": ("majiro",), ".ws2": ("willplus",), ".cst": ("catsystem2",),
    ".ybn": ("yuris",), ".ypf": ("yuris",), ".hcb": ("favorite",),
    ".rld": ("exhibit",), ".hst": ("shsystem",), ".srcxml": ("entis-gls",),
    ".nnn": ("systemnnn",), ".srp": ("tmrhiro",), ".mwb": ("gxengine",),
    ".rvdata2": ("rpgmaker",), ".rvdata": ("rpgmaker",),
    ".ykc": ("yuka",), ".yks": ("yuka",),
    ".rio": ("rugp",), ".ici": ("rugp",),
    ".fpk": ("systemc",),
}
EXTENSION_NOTES = {
    ".fpk": ".fpk; other engines also use FPK, check the encrypted tail index",
}

# Content probes for extensions that are ambiguous on their own.
AMBIGUOUS_TEXT_SUFFIXES = (".txt", ".iet")
#: Largest head read for a probe; never the whole file.
PROBE_BYTES = 2048
#: Largest Electron asar header JSON read; member data is never read.
ASAR_HEADER_LIMIT = 32 << 20

BASENAMES = {
    "nscript.dat": ("nscripter",), "0.txt": ("nscripter",),
    "scene.pck": ("siglus",), "seen.txt": ("reallive",),
    "script.src": ("softpal",), "ysc.ybn": ("yuris",),
    "rpg_core.js": ("rpgmaker",), "rmmz_core.js": ("rpgmaker",),
    "systemc.ini": ("systemc",),
    "eagls.ini": ("eagls",), "eagls.dll": ("eagls",),
    "scpack.idx": ("eagls",), "scpack.pak": ("eagls",),
    "unityplayer.dll": ("unity",), "gameassembly.dll": ("unity",),
    "globalgamemanagers": ("unity",), "globalgamemanagers.assets": ("unity",),
    "kag.parser.js": ("tyrano",),
}

# Evidence strength: header/footer/content/layout probes beat characteristic
# filenames, which beat bare extensions. Display ranks by this, not by name.
STRENGTH_OF_KIND = {
    "header-hint": "probe", "footer-hint": "probe", "content-probe": "probe",
    "layout-probe": "probe", "volume-set": "probe",
    "weak-layout": "filename", "weak-extension": "extension",
}
STRENGTH_ORDER = ("probe", "filename", "extension")
STRENGTH_RANK = {name: rank for rank, name in enumerate(STRENGTH_ORDER)}

# Breadth-first scan; at each depth these folder names are visited first so
# deep third-party plugin trees cannot spend the file budget before them.
PRIORITY_DIRS = frozenset(("game", "data", "archive", "archives", "pac", "pack", "packs",
                           "resources", "streamingassets"))

# Derived trees: this skill's workspaces and common third-party dump folders.
# "_output" alone is too common (media plugin folders such as audio_output),
# so only extractor dump folders like "KrkrExtract_Output" match by name.
DERIVED_NAME = re.compile(r"(?i)(?:_extract(?:[_-][\w-]*)?|extract\w*_output)$")
MAX_SKIPPED_REPORTED = 50

# Existing patch / earlier experiment leads. None of them is proof of anything.
PATCH_NOTE = "可能是已有补丁或旧实验产物，确认原版来源后再提取"
HOOK_DLL_NAMES = frozenset((
    "winmm.dll", "version.dll", "d3d8.dll", "d3d9.dll", "d3d10.dll", "d3d11.dll", "dxgi.dll",
    "ddraw.dll", "dinput.dll", "dinput8.dll", "dsound.dll", "opengl32.dll", "msimg32.dll",
    "winhttp.dll", "xinput1_3.dll",
))
PATCH_CONFIG_NAMES = frozenset((
    "uif_config.json", "ciallohook.ini", "version.ini", "winmm.ini",
    "jis-mapping.json", "jis_mapping.json", "doorstop_config.ini",
))
BACKUP_SUFFIXES = (".bak", ".org", ".orig")
COPY_DIR_NAME = re.compile(r"(?i)副本|備份|备份|コピー|バックアップ|-\s*copy\b|backup")
MAX_PATCH_HINTS = 100
# Duplicate archives: only same-name or same-size groups are hashed, and only
# over a bounded head, within a total byte/file budget.
ARCHIVE_SUFFIXES = frozenset((
    ".xp3", ".arc", ".pac", ".pak", ".pfs", ".ypf", ".rpa", ".int", ".pack", ".noa", ".fpk",
    ".cpk", ".med", ".ykc", ".dat", ".gxp", ".afs", ".unity3d", ".pck", ".bundle",
))
PFS_VOLUME = re.compile(r"(?i)\.pfs\.\d+$")
DUPLICATE_MIN_SIZE = 64 << 10
DUPLICATE_HEAD_BYTES = 4 << 20
DUPLICATE_MAX_FILES = 64
DUPLICATE_MAX_BYTES = 128 << 20
# BGI loose override: index-only reads, bounded, plus bounded encoding probes.
BGI_MAX_ARCHIVES = 64
BGI_INDEX_LIMIT = 8 << 20
BGI_LOOSE_PROBE_BYTES = 256 << 10
BGI_MAX_PROBED = 50
BGI_FILES_SHOWN = 20

PE_MACHINES = {0x14C: "x86", 0x8664: "x64", 0xAA64: "arm64", 0x1C0: "arm", 0x200: "ia64"}
PE_HEADER_LIMIT = 1 << 20
MAX_EXECUTABLES = 50
#: Executables (and hook DLLs beside them) are reported down to this depth;
#: some releases keep the real game EXE one or two folders below a launcher.
EXECUTABLE_MAX_DEPTH = 2

# Catalog fallback: generic media/container heads carry no engine signal.
GENERIC_PREFIXES = (
    b"\x89PNG", b"OggS", b"RIFF", b"MZ", b"PK\x03\x04", b"ID3", b"\xff\xd8\xff",
    b"\x1aE\xdf\xa3", b"GIF8", b"%PDF", b"\x00\x00\x01\xba", b"\x00\x00\x01\xb3",
    b"0&\xb2u", b"fLaC", b"\x7fELF", b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff", b"MSCF",
)
# Catalog "magics" below this little-endian value are version/count words
# (e.g. Chromium .pak heads 05 00 00 00), not signatures.
MIN_CATALOG_MAGIC = 0x10000
MAX_CATALOG_HINTS = 50
_CATALOG_INDEX = None


def _catalog_index() -> dict:
    """Four file-order header bytes (hex) -> catalog tags; loaded once, lazily."""
    global _CATALOG_INDEX
    if _CATALOG_INDEX is None:
        from python.common.source_catalog import load_formats
        index: dict[str, list[str]] = {}
        try:
            document = load_formats(Path(__file__).resolve().parents[1] / "catalog" / "formats.json")
        except (OSError, ValueError):
            document = {"formats": []}
        for entry in document["formats"]:
            tag = entry.get("tag", {}).get("value")
            for magic in entry.get("magic", {}).get("nonzero_uint32_le_hex", []) or []:
                if int.from_bytes(bytes.fromhex(magic), "little") < MIN_CATALOG_MAGIC:
                    continue
                tags = index.setdefault(magic, [])
                if tag and tag not in tags:
                    tags.append(tag)
        _CATALOG_INDEX = index
    return _CATALOG_INDEX


def _generic_head(header: bytes) -> bool:
    return header.startswith(GENERIC_PREFIXES) or header[4:8] == b"ftyp"


def _nexas_head(header: bytes) -> bool:
    if len(header) < 12 or header[:3] != b"PAC":
        return False
    count, pack_type = struct.unpack_from("<II", header, 4)
    return 1 <= count <= 100_000 and pack_type in (0, 2, 3, 4, 5, 6, 7)


def _cstring(data: bytes, offset: int, limit: int = 64):
    """Printable ASCII C string at offset, or None."""
    raw = data[offset:offset + limit]
    end = raw.find(b"\0")
    if end <= 0 or not all(0x20 <= byte < 0x7F for byte in raw[:end]):
        return None
    return raw[:end].decode("ascii")


def _ypf_probe(header: bytes):
    """(version, explanation) for a YPF head, else None."""
    if len(header) < 16 or header[:4] != b"YPF\0":
        return None
    version, count = struct.unpack_from("<II", header, 4)
    if not 0 < version < 0x1000:
        return None, "YPF header with an implausible version word; validate before any reader"
    route = ("v482 has the bundled extraction/writer route" if version == 0x1E2
             else "only v482 (0x1E2) has the full route; swap table/name key unproven")
    return version, f"YPF archive version {version} (0x{version:X}), {count} entries declared; {route}"


ENTIS_SUBTYPES = (
    (b"ERISA-Archive file", "noa",
     "Entis NOA archive (ERISA-Archive file at 0x10); read with python/archives/entis_noa.py (ERISA-N decoded; raw writer)"),
    (b"Cotopha Image file", "csx",
     "Entis CSX script image (Cotopha Image file at 0x10); distinguish VM versions"),
)


def _entis_probe(header: bytes):
    """(subtype, explanation) for an Entis head, else None."""
    if not header.startswith(b"Entis") or len(header) < 0x22:
        return None
    signature = header[0x10:0x40]
    for prefix, subtype, explanation in ENTIS_SUBTYPES:
        if signature.startswith(prefix):
            return subtype, explanation
    if header[5:6] != b"\x1a":
        return None
    name = _cstring(header, 0x10, 0x30)
    return "other", (f"Entis container, sub-signature {name!r} at 0x10; neither NOA nor CSX"
                     if name else "Entis container without a readable sub-signature at 0x10")


def _unityfs_probe(header: bytes):
    """(format version, engine version) for a UnityFS bundle head, else None."""
    if not header.startswith(b"UnityFS\0") or len(header) < 12:
        return None
    version = struct.unpack_from(">I", header, 8)[0]
    player = _cstring(header, 12, 32)
    engine = _cstring(header, 13 + len(player), 32) if player is not None else None
    return version, engine


def _unity_serialized_probe(header: bytes, size: int):
    """(serialized version, unity version) from a serialized-file head, else None.

    Big-endian legacy header; version >= 22 moves sizes to 64-bit fields at 0x14.
    The declared file size must equal the real size.
    """
    if len(header) < 48:
        return None
    version = struct.unpack_from(">I", header, 8)[0]
    if 22 <= version <= 64:
        _metadata, file_size, data_offset = struct.unpack_from(">IQQ", header, 20)
        position = 48
    elif 9 <= version < 22:
        _metadata, file_size, _version, data_offset = struct.unpack_from(">4I", header, 0)
        position = 20
    else:
        return None
    if file_size != size or not 0 < data_offset <= size or header[16] not in (0, 1):
        return None
    unity = _cstring(header, position, 32)
    if unity is not None and not re.fullmatch(r"\d+\.\d+\.\d+\w*", unity):
        unity = None
    return version, unity


def _pe_machine(stream, size: int):
    """PE Machine word name from a bounded header read, else None."""
    stream.seek(0)
    head = stream.read(64)
    if len(head) < 64 or head[:2] != b"MZ":
        return None
    offset = struct.unpack_from("<I", head, 0x3C)[0]
    if not 0x40 <= offset <= min(PE_HEADER_LIMIT, size - 6):
        return None
    stream.seek(offset)
    signature = stream.read(6)
    if len(signature) < 6 or signature[:4] != b"PE\0\0":
        return None
    machine = struct.unpack_from("<H", signature, 4)[0]
    return PE_MACHINES.get(machine, f"unknown(0x{machine:04X})")


def _guess_encoding(data: bytes, partial: bool) -> str:
    """Encoding lead for a bounded slice: whole-file UTF-8 first, then NUL-split strings."""
    try:
        text = codecs.getincrementaldecoder("utf-8")("strict").decode(data, final=not partial)
    except UnicodeDecodeError:
        text = None
    if text is not None:
        return "utf-8" if any(ord(char) > 0x7F for char in text) else "ascii"
    utf8 = legacy = 0
    for segment in data.split(b"\0"):
        if len(segment) < 4 or max(segment) < 0x80:
            continue
        try:
            segment.decode("utf-8")
            utf8 += 1
            continue
        except UnicodeDecodeError:
            pass
        try:
            segment.decode("cp932")
            legacy += 1
        except UnicodeDecodeError:
            pass
    if utf8 >= 3 and utf8 > legacy:
        return "utf-8-strings"
    if legacy >= 3 and legacy > utf8:
        return "cp932-compatible-strings"
    return "undetermined"


def _asar_probe(path: Path, header: bytes, size: int):
    """Return (engine, explanation) for an Electron asar head, else None.

    Reads only the bounded header JSON; member payloads are never touched.
    """
    if len(header) < 25 or struct.unpack_from("<I", header, 0)[0] != 4 or header[16:25] != b'{"files":':
        return None
    length = struct.unpack_from("<I", header, 12)[0]
    if not 0 < length <= ASAR_HEADER_LIMIT or 16 + length > size:
        return ("tyrano", "Electron asar head with an out-of-range header length; only Electron asar")
    try:
        with path.open("rb") as stream:
            stream.seek(16)
            tree = json.loads(stream.read(length).decode("utf-8"))
        files = tree["files"]
        scenario = files.get("data", {}).get("files", {}).get("scenario", {}).get("files", {})
        tyrano = "files" in files.get("tyrano", {})
        has_ks = any(name.lower().endswith(".ks") and "files" not in node for name, node in scenario.items())
    except (OSError, ValueError, KeyError, AttributeError, TypeError):
        return ("tyrano", "Electron asar head; header JSON unreadable; only Electron asar")
    if tyrano and has_ks:
        return ("tyrano", "Electron asar with tyrano/ and data/scenario/*.ks; TyranoScript layout, "
                          "dialect still needs parsing")
    return ("tyrano", "only Electron asar; no TyranoScript layout (tyrano/ + data/scenario/*.ks) seen")


def _derived_reason(path: Path, name: str):
    if DERIVED_NAME.search(name):
        return "derived output name (*_extract* / *Extract*_Output)"
    try:
        entries = list(os.scandir(path))
    except OSError:
        return None
    children = {entry.name.lower() for entry in entries if entry.is_dir(follow_symlinks=False)}
    files = {entry.name.lower() for entry in entries if entry.is_file(follow_symlinks=False)}
    if "gt_input" in children and ({"metadata", "reports"} & children):
        return "skill workspace (gt_input with metadata/reports)"
    if "verification.json" in files:
        return "skill pack output (verification.json)"
    return None


def _is_priority_dir(name: str) -> bool:
    lowered = name.lower()
    return lowered in PRIORITY_DIRS or lowered.endswith("_data")


def _select_evidence(hits: list, limit: int) -> list:
    """Strongest first, discovery order within a strength; >=1 per present strength."""
    if limit == 0:
        return []
    ranked = sorted(range(len(hits)), key=lambda i: (STRENGTH_RANK[hits[i]["strength"]], i))
    chosen, seen = [], set()
    for strength in STRENGTH_ORDER:
        first = next((i for i in ranked if hits[i]["strength"] == strength), None)
        if first is not None:
            chosen.append(first)
            seen.add(first)
    for i in ranked:
        if len(chosen) >= limit:
            break
        if i not in seen:
            chosen.append(i)
            seen.add(i)
    chosen.sort(key=lambda i: (STRENGTH_RANK[hits[i]["strength"]], i))
    return [hits[i] for i in chosen]


def detect_directory(root: Path, *, max_files: int = 2000, max_depth: int = 5,
                     max_seconds: float = 15.0, max_evidence: int = 12,
                     include_derived: bool = False) -> dict:
    root = Path(os.path.abspath(root))
    if max_files < 1 or max_depth < 0 or max_seconds <= 0:
        raise ValueError("invalid scan limits")
    if type(max_evidence) is not int or max_evidence < 0:
        raise ValueError("max_evidence must be a nonnegative integer")
    info = root.lstat()
    if root.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400 or not stat.S_ISDIR(info.st_mode):
        raise ValueError("choose an ordinary directory, not a link or junction")
    result = {"kind": "candidate-evidence-only", "files_seen": 0, "truncated": False,
              "truncated_reason": [],
              "candidates": {}, "candidate_stats": {}, "evidence_capped": False,
              "format_versions": {}, "executables": [], "unity": None,
              "existing_patch_hints": [],
              "existing_patch_hint_stats": {"total_hits": 0, "shown_hits": 0, "capped": False},
              "volume_sets": [], "skipped_directories": [], "skipped_directory_count": 0,
              "catalog_hints": [],
              "catalog_hint_stats": {"total_hits": 0, "shown_hits": 0, "capped": False,
                                     "note": "catalog magic leads only; not engine-page support"},
              "warnings": []}
    started = time.monotonic()
    # (depth, non-priority flag, sequence): breadth first, priority folders first per level.
    pending = [(0, 0, 0, root)]
    sequence = 1
    all_hits: dict[str, list] = {}
    matched_files: dict[str, set[str]] = {}
    # A PFS-family name is a set of independent volumes, not one archive.
    volume_families: dict[tuple, list] = {}
    directory_files: dict[str, dict[str, tuple]] = {}
    bgi_archives: list[tuple] = []
    archive_files: list[tuple] = []
    unity_backend = {"mono": [], "il2cpp": []}
    exe_directories: set[str] = set()
    hook_dlls: list[tuple] = []

    def truncate(reason):
        result["truncated"] = True
        if reason not in result["truncated_reason"]:
            result["truncated_reason"].append(reason)

    def out_of_budget():
        if result["files_seen"] >= max_files:
            truncate("max_files")
            return True
        if time.monotonic() - started > max_seconds:
            truncate("max_seconds")
            return True
        return False

    def evidence(engine, file, kind, explanation, **extra):
        hit = {"file": file, "kind": kind, "strength": STRENGTH_OF_KIND[kind], "evidence": explanation}
        hit.update(extra)
        all_hits.setdefault(engine, []).append(hit)
        matched_files.setdefault(engine, set()).add(file)

    def version_seen(family, version):
        counts = result["format_versions"].setdefault(family, {})
        key = str(version)
        counts[key] = counts.get(key, 0) + 1

    def patch_hint(kind, **fields):
        stats = result["existing_patch_hint_stats"]
        stats["total_hits"] += 1
        if len(result["existing_patch_hints"]) < MAX_PATCH_HINTS:
            result["existing_patch_hints"].append({"kind": kind, **fields, "note": PATCH_NOTE})
        stats["shown_hits"] = len(result["existing_patch_hints"])
        stats["capped"] = stats["total_hits"] > stats["shown_hits"]

    def catalog_hint(file, header):
        tags = _catalog_index().get(header[:4].hex())
        if not tags:
            return
        stats = result["catalog_hint_stats"]
        stats["total_hits"] += 1
        if len(result["catalog_hints"]) < MAX_CATALOG_HINTS:
            result["catalog_hints"].append({"file": file, "tags": tags[:5], "kind": "catalog-magic"})
        stats["shown_hits"] = len(result["catalog_hints"])
        stats["capped"] = stats["total_hits"] > stats["shown_hits"]

    while pending:
        if out_of_budget():
            break
        depth, _, _, directory = heapq.heappop(pending)
        directory_relative = "" if directory == root else directory.relative_to(root).as_posix()
        try:
            iterator = os.scandir(directory)
        except OSError as exc:
            result["warnings"].append({"file": directory_relative, "error": type(exc).__name__})
            continue
        with iterator:
            for entry in iterator:
                if out_of_budget():
                    break
                relative = Path(entry.path).relative_to(root).as_posix()
                try:
                    info = entry.stat(follow_symlinks=False)
                    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                        continue
                    if stat.S_ISDIR(info.st_mode):
                        reason = None if include_derived else _derived_reason(Path(entry.path), entry.name)
                        if reason:
                            result["skipped_directory_count"] += 1
                            if len(result["skipped_directories"]) < MAX_SKIPPED_REPORTED:
                                result["skipped_directories"].append({"directory": relative, "reason": reason})
                            continue
                        if COPY_DIR_NAME.search(entry.name):
                            patch_hint("copy-named-directory", directory=relative)
                        if entry.name.lower() == "il2cpp_data":
                            unity_backend["il2cpp"].append(relative)
                            evidence("unity", relative, "layout-probe",
                                     "il2cpp_data folder; IL2CPP scripting backend")
                        if depth < max_depth:
                            heapq.heappush(pending, (depth + 1, 0 if _is_priority_dir(entry.name) else 1,
                                                     sequence, Path(entry.path)))
                            sequence += 1
                        else:
                            truncate("max_depth")
                        continue
                    if not stat.S_ISREG(info.st_mode):
                        continue
                    result["files_seen"] += 1
                    path = Path(entry.path)
                    name = path.name
                    lowered = name.lower()
                    suffix = path.suffix.lower()
                    directory_files.setdefault(directory_relative, {})[lowered] = (relative, info.st_size, path)
                    for engine in EXTENSIONS.get(suffix, ()):
                        evidence(engine, relative, "weak-extension", EXTENSION_NOTES.get(suffix, path.suffix))
                    for engine in BASENAMES.get(lowered, ()):
                        evidence(engine, relative, "weak-layout", name)
                    if lowered == "gameassembly.dll":
                        unity_backend["il2cpp"].append(relative)
                        evidence("unity", relative, "layout-probe", "GameAssembly.dll; IL2CPP scripting backend")
                    if (lowered == "assembly-csharp.dll"
                            and re.search(r"(?i)(?:^|/)[^/]+_data/managed$", directory_relative)):
                        unity_backend["mono"].append(relative)
                        evidence("unity", relative, "layout-probe",
                                 "*_Data/Managed/Assembly-CSharp.dll; Mono scripting backend")
                    if lowered in PATCH_CONFIG_NAMES:
                        patch_hint("patch-config", file=relative)
                    if lowered.endswith(BACKUP_SUFFIXES):
                        patch_hint("backup-file", file=relative)
                    elif ((suffix in (".exe", ".dll") or suffix in ARCHIVE_SUFFIXES)
                          and COPY_DIR_NAME.search(path.stem)):
                        patch_hint("copy-named-file", file=relative)
                    head, _, tail = name.rpartition(".")
                    stem = head if (tail.isdigit() and head.lower().endswith(".pfs")) else name
                    if stem.lower().endswith(".pfs"):
                        volume_families.setdefault((directory_relative, stem), []).append(relative)
                    if ((suffix in ARCHIVE_SUFFIXES or PFS_VOLUME.search(name))
                            and info.st_size >= DUPLICATE_MIN_SIZE):
                        archive_files.append((relative, lowered, info.st_size, path))
                    with path.open("rb") as stream:
                        header = stream.read(PROBE_BYTES)
                        # QLIE's signature is in a footer, not a file header.
                        footer = b""
                        if suffix == ".pack":
                            if info.st_size <= 256:
                                footer = header[:256]
                            else:
                                stream.seek(max(0, info.st_size - 256))
                                footer = stream.read(256)
                        machine = None
                        if depth <= EXECUTABLE_MAX_DEPTH and (suffix == ".exe" or lowered in HOOK_DLL_NAMES):
                            machine = _pe_machine(stream, info.st_size) or "not-pe"
                    if depth <= EXECUTABLE_MAX_DEPTH and suffix == ".exe":
                        exe_directories.add(directory_relative)
                        if len(result["executables"]) < MAX_EXECUTABLES:
                            result["executables"].append({"file": relative, "machine": machine})
                    if depth <= EXECUTABLE_MAX_DEPTH and lowered in HOOK_DLL_NAMES:
                        hook_dlls.append((directory_relative, relative, machine))
                    header_hit = False
                    for magic, engine, explanation in MAGICS:
                        if header.startswith(magic):
                            evidence(engine, relative, "header-hint", explanation)
                            header_hit = True
                            if engine == "renpy":
                                version_seen("renpy-rpa", magic.decode("ascii").strip())
                    if header.startswith((b"PackFile    ", b"BURIKO ARC20")):
                        bgi_archives.append((directory_relative, relative, path))
                    if (header[:3] == b"MDN" and header[3:4].isdigit() and not header.startswith(b"MDN0")):
                        evidence("med", relative, "header-hint",
                                 f"MED {header[:4].decode('ascii')} container; only plain MDN0 scripts have a writer")
                        header_hit = True
                    ypf = _ypf_probe(header)
                    if ypf:
                        extra = {} if ypf[0] is None else {"version": ypf[0]}
                        evidence("yuris", relative, "header-hint", ypf[1], **extra)
                        version_seen("yuris-ypf", ypf[0] if ypf[0] is not None else "implausible")
                        header_hit = True
                    entis = _entis_probe(header)
                    if entis:
                        evidence("entis-gls", relative, "header-hint", entis[1], subtype=entis[0])
                        version_seen("entis", entis[0])
                        header_hit = True
                    bundle = _unityfs_probe(header)
                    if bundle:
                        evidence("unity", relative, "header-hint",
                                 f"UnityFS bundle format {bundle[0]}, engine {bundle[1] or 'unreadable'}; "
                                 "not covered by the complete workspace route",
                                 version=bundle[0], unity_version=bundle[1])
                        version_seen("unityfs", bundle[0])
                        header_hit = True
                    if suffix == ".assets" or lowered == "globalgamemanagers":
                        serialized = _unity_serialized_probe(header, info.st_size)
                        if serialized:
                            evidence("unity", relative, "header-hint",
                                     f"Unity serialized file v{serialized[0]}, engine "
                                     f"{serialized[1] or 'unreadable'}; the workspace route covers only "
                                     "v20 with stripped TypeTrees",
                                     version=serialized[0], unity_version=serialized[1])
                            version_seen("unity-serialized", serialized[0])
                            header_hit = True
                    if _nexas_head(header):
                        evidence("nexas", relative, "header-hint",
                                 "PAC head (count and compression type plausible); validate the tail index")
                        header_hit = True
                    asar = _asar_probe(path, header, info.st_size)
                    if asar:
                        evidence(asar[0], relative, "header-hint", asar[1])
                        header_hit = True
                    pack = re.search(rb"FilePackVer(\d+\.\d+)", footer)
                    if pack:
                        version = pack.group(1).decode("ascii")
                        evidence("qlie", relative, "footer-hint",
                                 f"FilePackVer{version} footer; bundled reader/writer cover only 3.0; "
                                 "validate key/layout", version=version)
                        version_seen("qlie-filepack", version)
                        header_hit = True
                    if suffix in AMBIGUOUS_TEXT_SUFFIXES and len(header) == PROBE_BYTES:
                        # The suffix does not decide: .iet is text in some releases and ASB
                        # in others, and .txt may be binary. Look at the content.
                        if header.startswith(b"ASB\0\0"):
                            evidence("artemis", relative, "content-probe",
                                     "ASB tree inside a .txt/.iet file; not the SCP text dialect")
                        elif looks_like_script(header, max_lines=12):
                            evidence("artemis-scp", relative, "content-probe",
                                     "line-oriented SCP text (// or ; comments, [tag ...], *label)")
                    if not header_hit and len(header) >= 4 and not _generic_head(header):
                        catalog_hint(relative, header)
                except OSError as exc:
                    if len(result["warnings"]) < 50:
                        result["warnings"].append({"file": relative, "error": type(exc).__name__})
    for (directory, stem), files in sorted(volume_families.items()):
        if len(files) < 2:
            continue
        result["volume_sets"].append({"directory": directory, "base": stem,
                                      "count": len(files), "volumes": sorted(files)})
        evidence("artemis", sorted(files)[0], "volume-set",
                 f"{stem} plus {len(files) - 1} numbered siblings; each volume is a "
                 "separate archive and the engine merges their namespaces")

    # Proxy DLLs only matter beside a game executable (or in the scanned root).
    for directory, file, machine in hook_dlls:
        if directory in exe_directories or directory == "":
            patch_hint("hook-dll", file=file, machine=machine)
    _bgi_loose_overrides(bgi_archives, directory_files, patch_hint, result["warnings"])
    _duplicate_archives(archive_files, patch_hint, started, max_seconds)

    if unity_backend["mono"] or unity_backend["il2cpp"] or "unity" in all_hits:
        backends = [name for name in ("mono", "il2cpp") if unity_backend[name]]
        result["unity"] = {
            "scripting_backend": "+".join(backends) if backends else "undetermined",
            "evidence": (unity_backend["mono"] + unity_backend["il2cpp"])[:10],
            "note": "runtime backend only; does not decide the asset/story serialization layout",
        }

    for engine in sorted(all_hits):
        hits = all_hits[engine]
        shown = _select_evidence(hits, max_evidence)
        by_strength = {strength: sum(1 for hit in hits if hit["strength"] == strength)
                       for strength in STRENGTH_ORDER}
        result["candidates"][engine] = shown
        result["candidate_stats"][engine] = {
            "total_hits": len(hits), "shown_hits": len(shown),
            "matched_files": len(matched_files[engine]), "capped": len(hits) > len(shown),
            "by_strength": {key: value for key, value in by_strength.items() if value},
        }
    result["evidence_capped"] = any(stats["capped"] for stats in result["candidate_stats"].values())
    return result


def _bgi_loose_overrides(archives, directory_files, patch_hint, warnings) -> None:
    """Loose files beside (or at the root above) a BGI .arc whose name matches a member."""
    from python.archives.bgi import BgiArchiveError, read_index
    for directory, relative, path in archives[:BGI_MAX_ARCHIVES]:
        try:
            with path.open("rb") as stream:
                index = read_index(stream, max_index_size=BGI_INDEX_LIMIT, max_archive_size=None)
        except (OSError, BgiArchiveError, ValueError) as exc:
            if len(warnings) < 50:
                warnings.append({"file": relative, "error": f"BGI index unreadable: {exc}"})
            continue
        loose = {}
        for folder in dict.fromkeys((directory, "")):
            for lowered, item in directory_files.get(folder, {}).items():
                loose.setdefault(lowered, item)
        matches = []
        for member in index.entries:
            found = loose.get(member.name.lower())
            if found and found[0] != relative:
                matches.append((member.name, found))
        if not matches:
            continue
        encodings: dict[str, int] = {}
        files = []
        for number, (member, (file, size, loose_path)) in enumerate(matches):
            if number < BGI_MAX_PROBED:
                try:
                    with loose_path.open("rb") as stream:
                        data = stream.read(BGI_LOOSE_PROBE_BYTES)
                    guess = _guess_encoding(data, size > len(data))
                except OSError:
                    guess = "unreadable"
            else:
                guess = "not-probed"
            encodings[guess] = encodings.get(guess, 0) + 1
            if len(files) < BGI_FILES_SHOWN:
                files.append({"file": file, "member": member, "encoding": guess})
        utf8 = encodings.get("utf-8", 0) + encodings.get("utf-8-strings", 0)
        summary = ("疑似 UTF-8 汉化覆盖" if utf8 else
                   "松散文件与归档成员同名，BGI 可能优先读取松散文件")
        patch_hint("bgi-loose-override", archive=relative, count=len(matches), files=files,
                   encodings=encodings, summary=summary)


def _duplicate_archives(archives, patch_hint, started, max_seconds) -> None:
    """Same-name or same-size archive groups whose size and bounded head hash agree."""
    by_name: dict[str, list] = {}
    by_size: dict[int, list] = {}
    for item in archives:
        by_name.setdefault(item[1], []).append(item)
        by_size.setdefault(item[2], []).append(item)
    candidates = {}
    for group in list(by_name.values()) + list(by_size.values()):
        if len(group) > 1:
            for item in group:
                candidates.setdefault(item[0], item)
    digests: dict[tuple, list] = {}
    spent = hashed = 0
    capped = False
    for relative, _, size, path in sorted(candidates.values()):
        amount = min(size, DUPLICATE_HEAD_BYTES)
        if (hashed >= DUPLICATE_MAX_FILES or spent + amount > DUPLICATE_MAX_BYTES
                or time.monotonic() - started > max_seconds):
            capped = True
            break
        digest = hashlib.sha256()
        try:
            with path.open("rb") as stream:
                remaining = amount
                while remaining:
                    chunk = stream.read(min(remaining, 1 << 20))
                    if not chunk:
                        break
                    digest.update(chunk)
                    remaining -= len(chunk)
        except OSError:
            continue
        spent += amount
        hashed += 1
        digests.setdefault((size, digest.hexdigest()), []).append(relative)
    for (size, _), files in sorted(digests.items(), key=lambda item: item[1][0]):
        if len(files) > 1:
            patch_hint("duplicate-archive", files=files, size=size,
                       compared=f"size and SHA-256 of the first {min(size, DUPLICATE_HEAD_BYTES)} bytes")
    if capped:
        patch_hint("duplicate-check-capped", candidates=len(candidates), hashed=hashed,
                   compared=f"limits: {DUPLICATE_MAX_FILES} files, {DUPLICATE_MAX_BYTES} bytes, "
                            "scan time budget")


def _emit(stream, text: str) -> None:
    """Write UTF-8 regardless of the console code page or -I/-X utf8 mode."""
    data = text.encode("utf-8")
    buffer = getattr(stream, "buffer", None)
    if buffer is not None:
        stream.flush()
        buffer.write(data)
        buffer.flush()
    else:
        stream.write(text)
        stream.flush()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--max-files", type=int, default=2000)
    parser.add_argument("--max-depth", type=int, default=5)
    parser.add_argument("--max-seconds", type=float, default=15.0)
    parser.add_argument("--max-evidence", type=int, default=12,
                        help="display cap per engine; counts are still collected (0: counts only)")
    parser.add_argument("--include-derived", action="store_true",
                        help="also scan *_extract workspaces and *_Output dump folders")
    args = parser.parse_args()
    try:
        result = detect_directory(args.directory, max_files=args.max_files, max_depth=args.max_depth,
                                  max_seconds=args.max_seconds, max_evidence=args.max_evidence,
                                  include_derived=args.include_derived)
    except (OSError, ValueError) as exc:
        _emit(sys.stderr, f"scan refused: {exc}\n")
        sys.exit(2)
    _emit(sys.stdout, json.dumps(result, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
