# SPDX-License-Identifier: GPL-3.0-only
"""Read-only Unity text-location scan; prints or writes one JSON report.

Walks ``*_Data`` directories (StreamingAssets included) of a game folder and
reports, per container: UnityFS header and nodes, serialized version, class
statistics, TextAssets (name, size, encoding guess, entropy) and MonoBehaviour
script classes resolved through MonoScript objects of any scanned file.
``global-metadata.dat`` is only reported by size. Bounded by file count and
read/decompression budgets; partial results are marked, never silently
dropped. Never writes into the game folder and never executes game code.

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
MAX_DEPTH = 12
MAX_PREVIEW = 120


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
                if encoding == "binary" and ent >= 7.5 and len(ta.script) >= 256:
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
    return name.replace("\\", "/").rsplit("/", 1)[-1].casefold()


def resolve(serialized, script_tables):
    """Resolve MonoBehaviour script PPtrs across every scanned serialized file."""
    for entry in serialized:
        report, index, behaviours = entry["report"], entry["index"], entry["behaviours"]
        classes, largest = Counter(), []
        unresolved = 0
        for file_id, path_id, name, obj, head in behaviours:
            cls = None
            if file_id == 0:
                cls = script_tables.get(entry["key"], {}).get(path_id)
            elif file_id is not None and 1 <= file_id <= len(index.externals):
                cls = script_tables.get(_container_key(index.externals[file_id - 1]), {}).get(path_id)
            label = ".".join(p for p in cls if p) if cls else None
            if label:
                classes[label] += 1
            else:
                unresolved += 1
            largest.append({"path_id": obj.path_id, "size": obj.size, "name": name, "class": label,
                            "cjk_chars_in_prefix": _kana(head)})
        largest.sort(key=lambda x: -x["size"])
        report["monobehaviour_classes"] = dict(classes.most_common())
        report["monobehaviour_unresolved"] = unresolved
        report["largest_monobehaviours"] = largest[:20]


def _plain_file(path, size, budget, options):
    item = {"size": size}
    if size <= 4 << 20:
        budget.charge(size)
        raw = path.read_bytes()
        encoding = guess_encoding(raw)
        item.update(encoding=encoding, entropy=entropy(raw))
        preview = _preview(raw, encoding, options["preview"])
        if preview:
            item["preview"] = preview
    else:
        with path.open("rb") as f:
            item["head"] = f.read(16).hex()
    return item


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


def scan(game, *, max_files=20000, max_bytes=2 << 30, per_container=256 << 20, preview=60):
    game = Path(game)
    if not game.is_dir():
        raise FormatError("game path must be a directory")
    budget = Budget(max_files, max_bytes, per_container)
    options = {"preview": max(0, min(preview, MAX_PREVIEW))}
    data_dirs = []
    for top in sorted(game.iterdir()) + [p for d in sorted(game.iterdir()) if d.is_dir() and not d.is_symlink()
                                          for p in sorted(d.iterdir())]:
        if top.is_dir() and not top.is_symlink() and top.name.endswith("_Data"):
            data_dirs.append(top)
    result = {"game": str(game), "data_dirs": [d.relative_to(game).as_posix() for d in data_dirs],
              "il2cpp_metadata": [], "containers": [], "streaming_assets": [], "other_files": {},
              "budget": {}, "partial": False}
    serialized, tables = [], {}
    try:
        for data_dir in data_dirs:
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
                if size < 48:
                    result["streaming_assets"].append({"path": rel, **_plain_file(path, size, budget, options)})
                    continue
                with path.open("rb") as stream:
                    head = stream.read(64)
                    kind = None
                    if fs.is_unityfs(head) or head.startswith(fs.LEGACY_SIGNATURES):
                        kind = "unityfs"
                    else:
                        try:
                            us.read_header(head, size)
                            kind = "serialized"
                        except FormatError:
                            pass
                    if kind is None:
                        if in_streaming:
                            item = {"path": rel, **_plain_file(path, size, budget, options)}
                            result["streaming_assets"].append(item)
                        else:
                            result["other_files"][key] = result["other_files"].get(key, 0) + 1
                        continue
                    entry = {"path": rel, "size": size, "kind": kind}
                    result["containers"].append(entry)
                    try:
                        if kind == "serialized":
                            report, index, scripts, behaviours = scan_serialized(stream, rel, budget, options)
                            entry.update(report)
                            key = _container_key(path.name)
                            tables.setdefault(key, {}).update(scripts)
                            serialized.append({"report": entry, "index": index, "behaviours": behaviours, "key": key})
                        else:
                            bundle = fs.read_header(stream)
                            entry.update(fs.describe(bundle))
                            reader = fs.BundleReader(stream, bundle, budget=per_container)
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
                                key = _container_key(n.path)
                                tables.setdefault(key, {}).update(scripts)
                                serialized.append({"report": node, "index": index, "behaviours": behaviours, "key": key})
                            entry["decompressed_bytes"] = reader.used
                    except FormatError as exc:
                        entry["error"] = str(exc)
    except FormatError as exc:
        result["partial"] = True
        result["error"] = str(exc)
    resolve(serialized, tables)
    result["partial"] = result["partial"] or bool(budget.exhausted)
    result["budget"] = {"files_seen": budget.used_files, "max_files": max_files, "bytes_read": budget.used_bytes,
                        "max_bytes": max_bytes, "per_container_decompress": per_container,
                        "exhausted": budget.exhausted}
    result["summary"] = summarize(result)
    return result


def summarize(result):
    text_assets, binary, suspect, classes = 0, 0, [], Counter()
    for entry in result["containers"]:
        for report in [entry, *entry.get("nodes", [])]:
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
    return {"text_textassets": text_assets, "binary_textassets": binary,
            "suspected_encrypted_textassets": suspect[:50],
            "streaming_text_files": sum(1 for s in result["streaming_assets"]
                                        if s.get("encoding") not in (None, "binary", "empty")),
            "top_monobehaviour_classes": dict(classes.most_common(30)),
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
                              "partial": result["partial"]}, ensure_ascii=False))
        else:
            sys.stdout.buffer.write(payload)
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
