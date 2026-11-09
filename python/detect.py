"""Read-only, bounded game-directory triage, NOT format validation.

Run from any directory: python /path/to/skill/python/detect.py GAME_DIRECTORY
Header facts derive from the format sources recorded in provenance/sources.json.
Only lists candidates: extensions, filenames and magic do not establish that a
specific parser, encryption scheme, script writer or patch loading route works.
Derived trees (this skill's *_extract workspaces, third-party *_Output dumps)
are skipped by default; pass --include-derived to scan them too.
"""

import argparse
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
    (b"YPF\0", "yuris", "YPF archive header; version/name scheme unknown"),
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
    (b"Entis\x1a\0\0", "entis-gls", "Entis CSX; distinguish VM versions"),
    (b"YKC001", "yuka", "YKC001 archive prefix"),
    (b"YKC002", "yuka", "YKC002 archive prefix; differs from writer v1"),
    (b"\xcd\x32\x6e\x59", "rugp", "rUGP RIO object signature; schema/key/script roles unverified"),
    (b"MDN0", "med", "MED MDN0 container; only plain MDN0 script archives (often md_scr.med) have a writer"),
    (b"MDE0", "med", "MED MDE0 container; encrypted members, no writer for this magic"),
    (b"UnityFS\0", "unity", "UnityFS/AssetBundle shell; not covered by the complete workspace route"),
)

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

# Derived trees: this skill's workspaces and common third-party dump folders.
DERIVED_NAME = re.compile(r"(?i)(?:_extract(?:[_-]?\d+)?|(?<!^gt)_output)$")
MAX_SKIPPED_REPORTED = 50

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
        return "derived output name (*_extract / *_Output)"
    try:
        children = {entry.name.lower() for entry in os.scandir(path) if entry.is_dir(follow_symlinks=False)}
    except OSError:
        return None
    if "gt_input" in children and ({"metadata", "reports"} & children):
        return "skill workspace (gt_input with metadata/reports)"
    return None


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
              "candidates": {}, "candidate_stats": {}, "evidence_capped": False,
              "volume_sets": [], "skipped_directories": [], "skipped_directory_count": 0,
              "catalog_hints": [],
              "catalog_hint_stats": {"total_hits": 0, "shown_hits": 0, "capped": False,
                                     "note": "catalog magic leads only; not engine-page support"},
              "warnings": []}
    started = time.monotonic()
    pending = [(root, 0)]
    matched_files: dict[str, set[str]] = {}
    # A PFS-family name is a set of independent volumes, not one archive.
    volume_families: dict[tuple, list] = {}

    def evidence(engine, file, kind, explanation):
        hits = result["candidates"].setdefault(engine, [])
        stats = result["candidate_stats"].setdefault(
            engine, {"total_hits": 0, "shown_hits": 0, "matched_files": 0, "capped": False})
        stats["total_hits"] += 1
        unique = matched_files.setdefault(engine, set())
        unique.add(file)
        stats["matched_files"] = len(unique)
        if len(hits) < max_evidence:
            hits.append({"file": file, "kind": kind, "evidence": explanation})
        stats["shown_hits"] = len(hits)
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
        if result["files_seen"] >= max_files or time.monotonic() - started > max_seconds:
            result["truncated"] = True
            break
        directory, depth = pending.pop()
        try:
            iterator = os.scandir(directory)
        except OSError as exc:
            result["warnings"].append({"file": directory.relative_to(root).as_posix(), "error": type(exc).__name__})
            continue
        with iterator:
            for entry in iterator:
                if result["files_seen"] >= max_files or time.monotonic() - started > max_seconds:
                    result["truncated"] = True
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
                        elif depth < max_depth:
                            pending.append((Path(entry.path), depth + 1))
                        else:
                            result["truncated"] = True
                        continue
                    if not stat.S_ISREG(info.st_mode):
                        continue
                    result["files_seen"] += 1
                    path = Path(entry.path)
                    suffix = path.suffix.lower()
                    for engine in EXTENSIONS.get(suffix, ()):
                        evidence(engine, relative, "weak-extension", EXTENSION_NOTES.get(suffix, path.suffix))
                    for engine in BASENAMES.get(path.name.lower(), ()):
                        evidence(engine, relative, "weak-layout", path.name)
                    name = path.name
                    head, _, tail = name.rpartition(".")
                    stem = head if (tail.isdigit() and head.lower().endswith(".pfs")) else name
                    if stem.lower().endswith(".pfs"):
                        volume_families.setdefault((relative.rsplit("/", 1)[0] if "/" in relative else "",
                                                    stem), []).append(relative)
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
                    header_hit = False
                    for magic, engine, explanation in MAGICS:
                        if header.startswith(magic):
                            evidence(engine, relative, "header-hint", explanation)
                            header_hit = True
                    if (header[:3] == b"MDN" and header[3:4].isdigit() and not header.startswith(b"MDN0")):
                        evidence("med", relative, "header-hint",
                                 f"MED {header[:4].decode('ascii')} container; only plain MDN0 scripts have a writer")
                        header_hit = True
                    if _nexas_head(header):
                        evidence("nexas", relative, "header-hint",
                                 "PAC head (count and compression type plausible); validate the tail index")
                        header_hit = True
                    asar = _asar_probe(path, header, info.st_size)
                    if asar:
                        evidence(asar[0], relative, "header-hint", asar[1])
                        header_hit = True
                    if b"FilePackVer" in footer:
                        evidence("qlie", relative, "footer-hint", "FilePackVer footer; validate version/key/layout")
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
    result["candidates"] = dict(sorted(result["candidates"].items()))
    result["candidate_stats"] = dict(sorted(result["candidate_stats"].items()))
    result["evidence_capped"] = any(stats["capped"] for stats in result["candidate_stats"].values())
    return result


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
    parser.add_argument("--max-evidence", type=int, default=12,
                        help="display cap per engine; counts are still collected (0: counts only)")
    parser.add_argument("--include-derived", action="store_true",
                        help="also scan *_extract workspaces and *_Output dump folders")
    args = parser.parse_args()
    try:
        result = detect_directory(args.directory, max_files=args.max_files, max_depth=args.max_depth,
                                  max_evidence=args.max_evidence, include_derived=args.include_derived)
    except (OSError, ValueError) as exc:
        _emit(sys.stderr, f"scan refused: {exc}\n")
        sys.exit(2)
    _emit(sys.stdout, json.dumps(result, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
