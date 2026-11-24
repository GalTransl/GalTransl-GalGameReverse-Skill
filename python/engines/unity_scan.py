# SPDX-License-Identifier: GPL-3.0-only
"""Read-only Unity text-location scan; prints or writes one JSON report.

Walks ``*_Data`` directories (StreamingAssets included) of a game folder and
reports, per container: UnityFS header and nodes, serialized version, class
statistics, TextAssets (name, size, encoding guess, entropy) and MonoBehaviour
script classes resolved through MonoScript objects. UnityFS bundles are also
recognised when foreign bytes precede the signature inside a bounded head
window (``prefix_length``). ``global-metadata.dat`` is only reported by size.
Bounded by file count and read/decompression budgets; containers that could
not be opened, bundle-like files that were not recognised and budget stops
mark the result ``partial`` and are listed, never silently dropped. Never
writes into the game folder and never executes game code.

    python -m python.engines.unity_scan <game dir> [--output <new dir>]
"""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import stat
import sys

from ..archives import unity_serialized as us
from ..archives import unityfs as fs
from ..common.binary import FormatError
from ..common.safety import write_new_tree
from .unity_textasset import TEXTASSET, entropy, guess_encoding, read_textasset

CLASS_NAMES = {
    1: "GameObject", 4: "Transform", 5: "TimeManager", 11: "AudioManager", 13: "InputManager",
    21: "Material", 28: "Texture2D", 43: "Mesh", 48: "Shader", 49: "TextAsset", 74: "AnimationClip",
    83: "AudioClip", 91: "AnimatorController", 95: "Animator", 114: "MonoBehaviour",
    115: "MonoScript", 128: "Font", 141: "BuildSettings", 142: "AssetBundle", 147: "ResourceManager",
    150: "PreloadData", 152: "MovieTexture", 213: "Sprite", 222: "CanvasRenderer", 223: "Canvas",
    224: "RectTransform", 329: "VideoClip", 687078895: "SpriteAtlas",
}
SKIP_SUFFIXES = {".dll", ".exe", ".pdb", ".so", ".mdb", ".resS", ".ress", ".resource"}
# Extensions Unity build pipelines commonly give AssetBundles; an unrecognised
# file with one of these (or with a sibling ``<name>.manifest``) is reported.
BUNDLE_SUFFIXES = {".bundle", ".unity3d", ".assetbundle", ".ab"}
# MonoBehaviour classes that have a route in engines/unity.md.
KNOWN_ROUTE_CLASSES = {"Utage.AdvImportBook": "utage-book", "Utage.AdvChapterData": "utage-chapter"}
# Leading magics of common media/archive formats: high entropy is expected there.
MAGICS = ((0, b"\x89PNG", "png"), (0, b"\xff\xd8\xff", "jpeg"), (0, b"OggS", "ogg"), (0, b"RIFF", "riff"),
          (4, b"ftyp", "mp4"), (0, b"ID3", "mp3"), (0, b"fLaC", "flac"), (0, b"PK\x03\x04", "zip"),
          (0, b"7z\xbc\xaf\x27\x1c", "7z"), (0, b"\x1f\x8b", "gzip"), (0, b"\x1a\x45\xdf\xa3", "matroska"),
          (0, b"CRID", "cri-usm"), (0, b"AFS2", "cri-awb"), (0, b"@UTF", "cri-utf"), (0, b"CPK ", "cri-cpk"),
          (0, b"BKHD", "wwise-bnk"), (0, b"AKPK", "wwise-pck"), (0, b"FSB5", "fmod-fsb5"),
          (0, b"SQLite format 3\0", "sqlite"))
MAX_DEPTH = 12
MAX_PREVIEW = 120
MAX_LISTED = 50
WHOLE_FILE = 4 << 20  # plain files up to this size are read whole
SAMPLES, SAMPLE_SIZE = 16, 64 << 10  # larger plain files: evenly spaced entropy samples
SUSPECT_ENTROPY = 7.5


class Budget:
    def __init__(self, files, read_bytes, per_container):
        self.files, self.read_bytes, self.per_container = files, read_bytes, per_container
        self.used_files = self.used_bytes = 0
        self.exhausted = []

    def charge(self, size):
        if self.used_bytes + size > self.read_bytes:
            raise FormatError("scan byte budget exhausted")
        self.used_bytes += size


def _class_name(class_id):
    return CLASS_NAMES.get(class_id, f"class_{class_id}")


def _preview(raw, encoding, limit):
    if not limit or encoding in ("binary", "empty"):
        return None
    codec = {"ascii": "utf-8", "utf-8": "utf-8", "utf-8-sig": "utf-8-sig"}.get(encoding, encoding)
    text = raw[:limit * 4].decode(codec, "replace")
    return " ".join(text.split())[:limit]


def _kana(raw):
    text = raw.decode("utf-8", "ignore")
    return sum(1 for c in text if "぀" <= c <= "ヿ" or "一" <= c <= "鿿")


def _magic(head):
    return next((name for at, sig, name in MAGICS if head[at:at + len(sig)] == sig), None)


def mono_script(index, obj, data):
    """Return ``(namespace, class)`` from a MonoScript; None if layout unknown."""
    t = index.types[obj.type_index]
    try:
        if t.nodes:
            values = {f.name: f.value for f in us.walk_object(t.nodes, data)}
            return (bytes(values["m_Namespace"]).decode("utf-8"), bytes(values["m_ClassName"]).decode("utf-8"))
        r = us.Reader(data)
        r.string()
        r.take(20)  # m_ExecutionOrder + m_PropertiesHash (Hash128)
        class_name, namespace = r.string(), r.string()
        r.string()
        if len(data) - r.pos in (1, 4) and data[r.pos] in (0, 1):
            r.number("B")  # m_IsEditorScript on older engines (object may end unaligned)
            if r.pos != len(data):
                r.align()
        if r.pos != len(data):
            return None
        return namespace, class_name
    except (FormatError, KeyError, UnicodeDecodeError):
        return None


def behaviour_header(data):
    """GameObject PPtr, enabled, script PPtr, m_Name (v14+ 64-bit PathIDs)."""
    r = us.Reader(data)
    r.take(12)
    if r.number("B") not in (0, 1):
        raise FormatError("invalid MonoBehaviour enabled flag")
    r.align()
    file_id, path_id = r.number("i"), r.number("q")
    return file_id, path_id, r.string(4096)


def scan_serialized(stream, label, budget, options):
    index = us.read_index(stream)
    counts = Counter(o.class_id for o in index.objects)
    report = {"serialized_version": index.version, "unity_version": index.unity_version,
              "platform": index.platform, "type_tree": index.type_tree,
              "object_count": len(index.objects), "externals": list(index.externals),
              "classes": {_class_name(c): n for c, n in counts.most_common()},
              "textassets": [], "monobehaviour_classes": {}, "partial": False}
    scripts, behaviours = {}, []

    def read(obj, prefix=None):
        size = obj.size if prefix is None else min(obj.size, prefix)
        budget.charge(size)
        return us.read_object(stream, obj, prefix=size)

    try:
        for obj in index.objects:
            if obj.class_id == TEXTASSET:
                if obj.size > us.MAX_OBJECT:
                    report["textassets"].append({"path_id": obj.path_id, "size": obj.size, "error": "over object budget"})
                    continue
                try:
                    ta = read_textasset(index, obj, read(obj))
                except FormatError as exc:
                    report["textassets"].append({"path_id": obj.path_id, "size": obj.size, "error": str(exc)})
                    continue
                encoding = guess_encoding(ta.script)
                ent = entropy(ta.script)
                item = {"path_id": obj.path_id, "name": ta.name, "size": len(ta.script), "encoding": encoding,
                        "entropy": ent, "layout": ta.layout}
                if encoding == "binary" and ent >= SUSPECT_ENTROPY and len(ta.script) >= 256:
                    item["suspected"] = "encrypted-or-compressed"
                preview = _preview(ta.script, encoding, options["preview"])
                if preview:
                    item["preview"] = preview
                report["textassets"].append(item)
            elif obj.class_id == 115 and obj.size <= 1 << 16:
                name = mono_script(index, obj, read(obj))
                if name:
                    scripts[obj.path_id] = name
            elif obj.class_id == 114:
                head = read(obj, 4096)
                try:
                    file_id, path_id, name = behaviour_header(head)
                except (FormatError, UnicodeDecodeError):
                    behaviours.append((None, None, "", obj, head))
                    continue
                behaviours.append((file_id, path_id, name, obj, head))
    except FormatError as exc:
        report["partial"] = True
        report["error"] = str(exc)
        budget.exhausted.append(label)
    return report, index, scripts, behaviours


def _container_key(name):
    """Case-folded last path component (``archive:/CAB-x/CAB-x`` -> ``cab-x``)."""
    return name.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1].casefold()


def _norm(path):
    return path.replace("\\", "/").casefold()


class ScriptTables:
    """MonoScript tables keyed by data directory and file name, never globally.

    ``fileID`` 0 resolves against the referencing file itself. An external
    reference resolves inside the same bundle first, then against the file at
    the exact relative path in the same ``*_Data`` directory, then against
    same-named files of that directory only when all of them agree; otherwise
    the behaviour is counted as ambiguous instead of guessed.
    """

    def __init__(self):
        self.by_dir, self.by_bundle = {}, {}

    def add(self, entry):
        name = _container_key(entry["name"])
        self.by_dir.setdefault((entry["data_dir"], name), []).append(entry)
        if entry["bundle"] is not None:
            self.by_bundle.setdefault((entry["bundle"], name), []).append(entry)

    def lookup(self, entry, file_id, path_id):
        """Return ``(class tuple or None, ambiguous)``."""
        if file_id == 0:
            return entry["scripts"].get(path_id), False
        if file_id is None or not 1 <= file_id <= len(entry["index"].externals):
            return None, False
        external = entry["index"].externals[file_id - 1]
        name = _container_key(external)
        if entry["bundle"] is not None:
            local = self.by_bundle.get((entry["bundle"], name), [])
            if len(local) == 1:
                return local[0]["scripts"].get(path_id), False
        candidates = self.by_dir.get((entry["data_dir"], name), [])
        exact = _norm(f"{entry['data_dir']}/{external}")
        for cand in candidates:
            if cand["bundle"] is None and _norm(cand["label"]) == exact:
                return cand["scripts"].get(path_id), False
        values = {cand["scripts"].get(path_id) for cand in candidates}
        if len(values) == 1:
            return values.pop(), False
        return None, len(values) > 1


def resolve(serialized, tables):
    """Resolve MonoBehaviour script PPtrs; never mixes different data dirs."""
    for entry in serialized:
        report, behaviours = entry["report"], entry["behaviours"]
        classes, largest, routes = Counter(), [], []
        unresolved = ambiguous = 0
        for file_id, path_id, name, obj, head in behaviours:
            cls, unclear = tables.lookup(entry, file_id, path_id)
            label = ".".join(p for p in cls if p) if cls else None
            if label:
                classes[label] += 1
                if label in KNOWN_ROUTE_CLASSES:
                    routes.append({"path_id": obj.path_id, "name": name, "class": label,
                                   "route": KNOWN_ROUTE_CLASSES[label], "size": obj.size})
            else:
                unresolved += 1
                ambiguous += unclear
            largest.append({"path_id": obj.path_id, "size": obj.size, "name": name, "class": label,
                            "cjk_chars_in_prefix": _kana(head)})
        largest.sort(key=lambda x: -x["size"])
        report["monobehaviour_classes"] = dict(classes.most_common())
        report["monobehaviour_unresolved"] = unresolved
        if ambiguous:
            report["monobehaviour_ambiguous"] = ambiguous
        report["largest_monobehaviours"] = largest[:20]
        if routes:
            report["known_route_objects"] = routes


def _plain_file(path, size, budget, options):
    """Encoding/entropy facts for a non-Unity file; large files are sampled."""
    item = {"size": size}
    if size <= WHOLE_FILE:
        budget.charge(size)
        raw = path.read_bytes()
        encoding = guess_encoding(raw)
        item.update(encoding=encoding, entropy=entropy(raw))
        preview = _preview(raw, encoding, options["preview"])
        if preview:
            item["preview"] = preview
        head = raw[:16]
    else:
        budget.charge(SAMPLES * SAMPLE_SIZE)
        chunks = []
        with path.open("rb") as f:
            for i in range(SAMPLES):
                f.seek(i * (size - SAMPLE_SIZE) // (SAMPLES - 1))
                chunks.append(f.read(SAMPLE_SIZE))
        head = chunks[0][:16]
        joined = b"".join(chunks)
        item.update(head=head.hex(), entropy=entropy(joined, limit=len(joined)),
                    entropy_samples={"count": SAMPLES, "bytes_each": SAMPLE_SIZE})
    magic = _magic(head)
    if magic:
        item["magic"] = magic
    if (item.get("encoding", "binary") == "binary" and item["entropy"] >= SUSPECT_ENTROPY
            and size >= 256 and not magic):
        item["suspected"] = "encrypted-or-compressed"
    return item


def _bundle_like(path):
    """Why an unrecognised file still looks like an AssetBundle, or None."""
    if path.suffix.lower() in BUNDLE_SUFFIXES:
        return f"{path.suffix.lower()} extension"
    if path.with_name(path.name + ".manifest").is_file():
        return "sibling .manifest file"
    return None


def _walk(root, budget):
    stack = [(root, 0)]
    while stack:
        directory, depth = stack.pop()
        try:
            entries = sorted(os.scandir(directory), key=lambda e: e.name)
        except OSError:
            continue
        for entry in entries:
            if entry.is_symlink():
                continue
            if entry.is_dir(follow_symlinks=False):
                if depth < MAX_DEPTH:
                    stack.append((Path(entry.path), depth + 1))
            elif entry.is_file(follow_symlinks=False):
                budget.used_files += 1
                if budget.used_files > budget.files:
                    raise FormatError("scan file budget exhausted")
                yield Path(entry.path)


def _detect(stream, size):
    """Return ``(kind, prefix_length)``; kind is None for non-Unity files."""
    head = stream.read(fs.MAX_PREFIX + 64)
    if head.startswith(fs.LEGACY_SIGNATURES):
        return "unityfs", 0
    at = fs.signature_offset(head)
    if at == 0:
        return "unityfs", 0
    try:
        us.read_header(head[:64], size)
        return "serialized", 0
    except FormatError:
        pass
    return ("unityfs", at) if at is not None else (None, 0)


def scan(game, *, max_files=20000, max_bytes=2 << 30, per_container=256 << 20, preview=60):
    game = Path(game)
    if not game.is_dir():
        raise FormatError("game path must be a directory")
    budget = Budget(max_files, max_bytes, per_container)
    options = {"preview": max(0, min(preview, MAX_PREVIEW))}
    data_dirs = []
    for top in sorted(game.iterdir()) + [p for d in sorted(game.iterdir()) if d.is_dir() and not d.is_symlink()
                                          for p in sorted(d.iterdir())]:
        if (top.is_dir() and not top.is_symlink() and top.name.endswith("_Data")
                and not any(d in top.parents for d in data_dirs)):
            data_dirs.append(top)
    result = {"game": str(game), "data_dirs": [d.relative_to(game).as_posix() for d in data_dirs],
              "il2cpp_metadata": [], "containers": [], "streaming_assets": [], "unrecognized_bundles": [],
              "other_files": {}, "budget": {}, "partial": False, "partial_reasons": []}
    serialized, tables = [], ScriptTables()

    def register(report, index, scripts, behaviours, label, name, data_dir, bundle):
        record = {"report": report, "index": index, "behaviours": behaviours, "scripts": scripts,
                  "label": label, "name": name, "data_dir": data_dir, "bundle": bundle}
        tables.add(record)
        serialized.append(record)

    try:
        for data_dir in data_dirs:
            dir_rel = data_dir.relative_to(game).as_posix()
            for path in _walk(data_dir, budget):
                rel = path.relative_to(game).as_posix()
                info = path.lstat()
                if not stat.S_ISREG(info.st_mode):
                    continue
                size = info.st_size
                if path.name == "global-metadata.dat":
                    result["il2cpp_metadata"].append({"path": rel, "size": size, "parsed": False})
                    continue
                in_streaming = "StreamingAssets" in path.relative_to(data_dir).parts
                key = path.suffix.lower() or "<none>"
                if path.suffix in SKIP_SUFFIXES or key in SKIP_SUFFIXES or (size < 48 and not in_streaming):
                    result["other_files"][key] = result["other_files"].get(key, 0) + 1
                    continue
                with path.open("rb") as stream:
                    kind, prefix = _detect(stream, size) if size >= 48 else (None, 0)
                    if kind is None:
                        reason = _bundle_like(path) if size >= 48 else None
                        if in_streaming or reason:
                            item = {"path": rel, **_plain_file(path, size, budget, options)}
                            if in_streaming:
                                result["streaming_assets"].append(item)
                            if reason:
                                result["unrecognized_bundles"].append(
                                    {"path": rel, "size": size, "reason": reason,
                                     **{k: item[k] for k in ("entropy", "magic", "suspected") if k in item}})
                        else:
                            result["other_files"][key] = result["other_files"].get(key, 0) + 1
                        continue
                    entry = {"path": rel, "data_dir": dir_rel, "size": size, "kind": kind}
                    if prefix:
                        entry["prefix_length"] = prefix
                    result["containers"].append(entry)
                    try:
                        if kind == "serialized":
                            report, index, scripts, behaviours = scan_serialized(stream, rel, budget, options)
                            entry.update(report)
                            register(entry, index, scripts, behaviours, rel, path.name, dir_rel, None)
                        else:
                            body = fs.SubStream(stream, prefix) if prefix else stream
                            bundle = fs.read_header(body)
                            entry.update(fs.describe(bundle))
                            reader = fs.BundleReader(body, bundle, budget=per_container)
                            for node in entry["nodes"]:
                                if not node["flags"] & 4:
                                    continue
                                n = next(x for x in bundle.nodes if x.path == node["path"])
                                label = f"{rel}:{n.path}"
                                try:
                                    report, index, scripts, behaviours = scan_serialized(
                                        us.NodeStream(reader, n), label, budget, options)
                                except FormatError as exc:
                                    node["error"] = str(exc)
                                    if "budget" in str(exc):
                                        node["partial"] = True
                                        budget.exhausted.append(label)
                                    continue
                                node.update(report)
                                register(node, index, scripts, behaviours, label, n.path, dir_rel, rel)
                            entry["decompressed_bytes"] = reader.used
                    except FormatError as exc:
                        entry["error"] = str(exc)
    except FormatError as exc:
        result["partial"] = True
        result["error"] = str(exc)
        result["partial_reasons"].append(str(exc))
    resolve(serialized, tables)
    result["budget"] = {"files_seen": budget.used_files, "max_files": max_files, "bytes_read": budget.used_bytes,
                        "max_bytes": max_bytes, "per_container_decompress": per_container,
                        "exhausted": budget.exhausted}
    result["summary"] = summarize(result)
    reasons = result["partial_reasons"]
    if budget.exhausted:
        reasons.append(f"budget exhausted in {len(budget.exhausted)} container(s)")
    if result["summary"]["unopened_containers"]:
        reasons.append(f"{result['summary']['unopened_container_count']} container(s) or node(s) not opened")
    if result["unrecognized_bundles"]:
        reasons.append(f"{len(result['unrecognized_bundles'])} bundle-like file(s) not recognised")
    result["partial"] = bool(reasons)
    return result


def _duplicates(result):
    """Same-named containers or bundle nodes at different places (live/backup/dummy copies)."""
    groups = {}
    for entry in result["containers"]:
        groups.setdefault(_container_key(entry["path"]), []).append(entry)
        for node in entry.get("nodes", []):
            if node["flags"] & 4:
                groups.setdefault(_container_key(node["path"]), []).append(
                    {"path": f"{entry['path']}:{node['path']}", "data_dir": entry["data_dir"], "size": node["size"]})
    out = []
    for name, items in groups.items():
        if len(items) > 1:
            out.append({"name": name, "same_data_dir": len({i["data_dir"] for i in items}) == 1,
                        "same_size": len({i["size"] for i in items}) == 1,
                        "paths": [{"path": i["path"], "data_dir": i["data_dir"], "size": i["size"]} for i in items]})
    out.sort(key=lambda g: (not g["same_data_dir"], g["name"]))
    return out


def summarize(result):
    text_assets, binary, suspect, classes = 0, 0, [], Counter()
    unopened, routes = [], []
    for entry in result["containers"]:
        if "error" in entry:
            unopened.append({"path": entry["path"], "error": entry["error"],
                             **({"prefix_length": entry["prefix_length"]} if "prefix_length" in entry else {})})
        for node in entry.get("nodes", []):
            if "error" in node:
                unopened.append({"path": f"{entry['path']}:{node['path']}", "error": node["error"]})
        for report in [entry, *entry.get("nodes", [])]:
            label = entry["path"] if report is entry else f"{entry['path']}:{report['path']}"
            for ta in report.get("textassets", []):
                if "encoding" not in ta:
                    continue
                if ta["encoding"] in ("binary", "empty"):
                    binary += 1
                else:
                    text_assets += 1
                if ta.get("suspected"):
                    suspect.append(ta["name"])
            classes.update(report.get("monobehaviour_classes", {}))
            routes.extend({"container": label, **obj} for obj in report.get("known_route_objects", []))
    files = [{"path": s["path"], "size": s["size"], "entropy": s["entropy"]}
             for s in result["streaming_assets"] if s.get("suspected")]
    files += [{"path": b["path"], "size": b["size"], "entropy": b["entropy"]}
              for b in result["unrecognized_bundles"]
              if b.get("suspected") and not any(f["path"] == b["path"] for f in files)]
    duplicates = _duplicates(result)
    return {"text_textassets": text_assets, "binary_textassets": binary,
            "suspected_encrypted_textassets": suspect[:MAX_LISTED],
            "suspected_encrypted_files": files[:MAX_LISTED],
            "streaming_text_files": sum(1 for s in result["streaming_assets"]
                                        if s.get("encoding") not in (None, "binary", "empty")),
            "top_monobehaviour_classes": dict(classes.most_common(30)),
            "known_route_objects": routes[:200], "known_route_object_count": len(routes),
            "unopened_containers": unopened[:MAX_LISTED], "unopened_container_count": len(unopened),
            "unrecognized_bundles": [b["path"] for b in result["unrecognized_bundles"][:MAX_LISTED]],
            "prefixed_bundles": sum(1 for e in result["containers"] if e.get("prefix_length")),
            "duplicate_container_names": duplicates[:MAX_LISTED],
            "duplicate_container_groups": len(duplicates),
            "il2cpp_metadata_present": bool(result["il2cpp_metadata"])}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("game")
    parser.add_argument("--output", help="new directory for scan.json (default: stdout)")
    parser.add_argument("--max-files", type=int, default=20000)
    parser.add_argument("--max-bytes", type=int, default=2 << 30, help="object/plain-file read budget")
    parser.add_argument("--per-container", type=int, default=256 << 20, help="decompression budget per bundle")
    parser.add_argument("--preview", type=int, default=60, help="characters of text preview (0 disables)")
    args = parser.parse_args(argv)
    try:
        result = scan(args.game, max_files=args.max_files, max_bytes=args.max_bytes,
                      per_container=args.per_container, preview=args.preview)
        payload = (json.dumps(result, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
        if args.output:
            write_new_tree(Path(args.output), [("scan.json", payload)])
            print(json.dumps({"output": str(Path(args.output) / "scan.json"), **result["summary"],
                              "partial": result["partial"], "partial_reasons": result["partial_reasons"]},
                             ensure_ascii=False))
        else:
            sys.stdout.buffer.write(payload)
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
