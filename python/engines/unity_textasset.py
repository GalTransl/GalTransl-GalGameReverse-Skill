# SPDX-License-Identifier: GPL-3.0-only
"""Unity TextAsset (class 49) whole-content extract and replace workspace.

Container chain: UnityFS bundle (optional) -> serialized file v17-v22 ->
TextAsset. With a TypeTree the object is read field by field; without one the
known layout (``m_Name`` string, ``m_Script`` bytes, and ``m_PathName`` on
engines before 2017) must consume the object exactly. Only the whole
``m_Script`` is replaced; no script dialect is parsed here.

Writes only to new directories. Bundles are rewritten with uncompressed data
blocks (see engines/unity.md for the runtime caveat).
"""
import argparse
from dataclasses import dataclass
import fnmatch
import io
import json
import math
from pathlib import Path
import re
import struct
import sys
import unicodedata

from ..archives import unity_serialized as us
from ..archives import unityfs as fs
from ..common.binary import FormatError
from ..common.contract import load_json, sha256
from ..common.safety import Limits, logical_path, validate_names, validate_new_tree_destination, write_new_tree

ENGINE = "unity-textasset"
PROFILE = "textasset-whole-v1"
TEXTASSET = 49
MAX_CONTAINER = 512 << 20
MAX_REPLACEMENT = 32 << 20
LIMITS = Limits(max_entries=100_000, max_file_bytes=MAX_CONTAINER, max_total_bytes=2 * MAX_CONTAINER)
_FIELDS = (("m_Name", "m_Script"), ("m_Name", "m_Script", "m_PathName"))


@dataclass(frozen=True)
class TextAsset:
    path_id: int
    name: str
    script: bytes
    start: int  # m_Script span inside the object, including alignment
    end: int
    aligned: bool
    layout: str


def _major(unity_version):
    m = re.match(r"(\d+)\.", unity_version)
    if not m:
        raise FormatError(f"unparseable Unity version {unity_version!r}")
    return int(m.group(1))


def read_textasset(index, obj, data):
    """Strictly parse one TextAsset object; raises on any unknown layout."""
    if obj.class_id != TEXTASSET:
        raise FormatError("object is not a TextAsset")
    t = index.types[obj.type_index]
    if t.nodes:
        if t.nodes[0].type != "TextAsset":
            raise FormatError("TypeTree root is not TextAsset")
        fields = us.walk_object(t.nodes, data)
        names = tuple(f.name for f in fields)
        if names not in _FIELDS or any(f.type != "string" for f in fields):
            raise FormatError(f"unsupported TextAsset fields {names}")
        name_field, script = fields[0], fields[1]
        at = next(i for i, n in enumerate(t.nodes) if n.level == 1 and n.name == "m_Script")
        aligned = bool((t.nodes[at].meta_flag | t.nodes[at + 1].meta_flag) & us.ALIGN_FLAG)
        size = len(script.value)
        if script.end - script.start != 4 + size + (-size % 4 if aligned else 0):
            raise FormatError("TextAsset m_Script span differs from its TypeTree alignment")
        try:
            name = bytes(name_field.value).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise FormatError("TextAsset m_Name is not UTF-8") from exc
        return TextAsset(obj.path_id, name, bytes(script.value), script.start, script.end, aligned, "typetree")
    r = us.Reader(data)
    name = r.string()
    start = r.pos
    script = r.take(r.count(len(data)))
    r.align()
    end = r.pos
    if _major(index.unity_version) < 2017:
        r.string()
    if r.pos != len(data):
        raise FormatError("stripped TextAsset does not match the known layout")
    return TextAsset(obj.path_id, name, script, start, end, True, "stripped")


def encode_script(payload, aligned):
    if len(payload) > MAX_REPLACEMENT:
        raise FormatError("TextAsset replacement exceeds budget")
    return struct.pack("<i", len(payload)) + payload + (bytes(-len(payload) % 4) if aligned else b"")


def patch_textasset(index, obj, data, payload):
    """Return the object with ``m_Script`` replaced; other bytes unchanged."""
    old = read_textasset(index, obj, data)
    if old.start % 4:
        raise FormatError("TextAsset m_Script is not four-byte aligned")
    new = data[:old.start] + encode_script(payload, old.aligned) + data[old.end:]
    check = read_textasset(index, obj, new)
    if (check.name, check.script, check.layout) != (old.name, payload, old.layout):
        raise FormatError("TextAsset readback differs after patch")
    return new


def guess_encoding(raw):
    """Classify bytes as ascii/utf-8/utf-8-sig/utf-16le/utf-16be/cp932/binary/empty."""
    if not raw:
        return "empty"
    for bom, name in ((b"\xef\xbb\xbf", "utf-8-sig"), (b"\xff\xfe", "utf-16le"), (b"\xfe\xff", "utf-16be")):
        if raw.startswith(bom):
            try:
                text = raw.decode(name if name != "utf-8-sig" else "utf-8-sig")
                return name if _texty(text) else "binary"
            except UnicodeDecodeError:
                return "binary"
    candidates = ["utf-8"]
    if len(raw) % 2 == 0 and raw[1::2].count(0) > len(raw) // 4:
        candidates.insert(0, "utf-16le")
    candidates.append("cp932")
    for name in candidates:
        try:
            text = raw.decode(name)
        except UnicodeDecodeError:
            continue
        if _texty(text):
            return "ascii" if name == "utf-8" and raw.isascii() else name
    return "binary"


def _texty(text):
    bad = sum(1 for c in text if unicodedata.category(c) in ("Cc", "Cs", "Co", "Cn") and c not in "\t\r\n")
    return bad <= len(text) // 100


def entropy(raw, limit=1 << 20):
    raw = raw[:limit]
    if not raw:
        return 0.0
    counts = [0] * 256
    for b in raw:
        counts[b] += 1
    n = len(raw)
    return round(-sum(c / n * math.log2(c / n) for c in counts if c), 3)


# --- containers ------------------------------------------------------------

@dataclass
class Container:
    kind: str  # "unityfs" or "serialized"
    raw: bytes
    bundle: object
    serialized: dict  # node path ("" for a bare serialized file) -> bytes


def open_container(raw):
    if fs.is_unityfs(raw[:16]):
        bundle, _, nodes = fs.read_bundle(raw, budget=MAX_CONTAINER)
        serialized = {}
        for node in bundle.nodes:
            if node.flags & 4:
                serialized[node.path] = nodes[node.path]
        return Container("unityfs", raw, bundle, serialized)
    us.read_index(io.BytesIO(raw))
    return Container("serialized", raw, None, {"": raw})


def text_assets(container):
    """Yield ``(node, index, object, TextAsset)`` in node/object order."""
    for node, data in container.serialized.items():
        index = us.read_index(io.BytesIO(data))
        for obj in index.objects:
            if obj.class_id == TEXTASSET:
                yield node, index, obj, read_textasset(index, obj, data[obj.offset:obj.offset + obj.size])


def rebuild_container(container, replacements):
    """``replacements``: {(node, path_id): new m_Script bytes}. Returns bytes."""
    by_node = {}
    for (node, path_id), payload in replacements.items():
        by_node.setdefault(node, {})[path_id] = payload
    new_nodes = {}
    for node, edits in by_node.items():
        data = container.serialized.get(node)
        if data is None:
            raise FormatError(f"unknown serialized node {node!r}")
        index = us.read_index(io.BytesIO(data))
        objects = {o.path_id: o for o in index.objects}
        objs = {}
        for path_id, payload in edits.items():
            obj = objects.get(path_id)
            if obj is None or obj.class_id != TEXTASSET:
                raise FormatError(f"TextAsset {path_id} not found in {node!r}")
            objs[path_id] = patch_textasset(index, obj, data[obj.offset:obj.offset + obj.size], payload)
        new_nodes[node] = us.rebuild(data, objs)
    if container.kind == "serialized":
        return new_nodes.get("", container.raw)
    return fs.rebuild(container.raw, new_nodes, budget=MAX_CONTAINER)


def verify_container(original, rebuilt, replacements):
    """Reread ``rebuilt``: every object byte-identical except replaced scripts."""
    after = open_container(rebuilt)
    if after.kind != original.kind or list(after.serialized) != list(original.serialized):
        raise FormatError("container kind or serialized node list changed")
    if original.kind == "unityfs":
        _, _, old_nodes = fs.read_bundle(original.raw, budget=MAX_CONTAINER)
        _, _, new_nodes = fs.read_bundle(rebuilt, budget=MAX_CONTAINER)
        for path, payload in old_nodes.items():
            if path not in after.serialized and new_nodes[path] != payload:
                raise FormatError(f"non-serialized node {path!r} changed")
    checked, changed = 0, []
    for node, data in original.serialized.items():
        new = after.serialized[node]
        a, b = us.read_index(io.BytesIO(data)), us.read_index(io.BytesIO(new))
        if [(o.path_id, o.class_id, o.type_index) for o in a.objects] != [(o.path_id, o.class_id, o.type_index) for o in b.objects]:
            raise FormatError(f"object table identity changed in {node!r}")
        if (a.types, a.externals, a.scripts, a.ref_types, a.unity_version) != (b.types, b.externals, b.scripts, b.ref_types, b.unity_version):
            raise FormatError(f"serialized metadata changed in {node!r}")
        if not any(k[0] == node for k in replacements) and data != new:
            raise FormatError(f"untouched serialized node {node!r} changed")
        for x, y in zip(a.objects, b.objects):
            old_obj, new_obj = data[x.offset:x.offset + x.size], new[y.offset:y.offset + y.size]
            key = (node, x.path_id)
            if key in replacements:
                ta_old = read_textasset(a, x, old_obj)
                ta_new = read_textasset(b, y, new_obj)
                if ta_new.script != replacements[key] or ta_new.name != ta_old.name:
                    raise FormatError(f"TextAsset {key} readback differs")
                if (old_obj[:ta_old.start] != new_obj[:ta_new.start]
                        or old_obj[ta_old.end:] != new_obj[ta_new.end:]):
                    raise FormatError(f"TextAsset {key} non-script bytes changed")
                if ta_new.script != ta_old.script:
                    changed.append(key)
            elif old_obj != new_obj:
                raise FormatError(f"object {key} changed unexpectedly")
            checked += 1
    return checked, changed


# --- workspace -------------------------------------------------------------

def _json(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _read_bounded(path, limit):
    path = Path(path)
    with us.open_checked(path) as stream:
        stream.seek(0, 2)
        size = stream.tell()
        if size > limit:
            raise FormatError(f"{path.name} exceeds the {limit >> 20} MiB budget")
        stream.seek(0)
        raw = stream.read(limit + 1)
    if len(raw) != size:
        raise FormatError(f"{path.name} changed while reading")
    return raw


def _flat_name(name, path_id, encoding, used):
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")[:120] or "textasset"
    ext = ".bytes" if encoding in ("binary", "empty") else ".txt"
    try:
        logical_path(stem + ext)
    except FormatError:
        stem = "_" + stem
    candidate = stem + ext
    key = lambda s: unicodedata.normalize("NFC", s).casefold()
    if key(candidate) in used:
        candidate = f"{stem}__p{path_id}{ext}"
    if key(candidate) in used:
        raise FormatError("ambiguous TextAsset output filename")
    used.add(key(candidate))
    return candidate


def _select(entries, names, path_ids, node):
    chosen = []
    for item in entries:
        n, _, obj, ta = item
        if node is not None and n != node:
            continue
        if path_ids and obj.path_id not in path_ids:
            continue
        if names and not any(fnmatch.fnmatchcase(ta.name, pattern) for pattern in names):
            continue
        chosen.append(item)
    return chosen


def extract(source, output, *, names=(), path_ids=(), node=None, target=None):
    source, output = Path(source), Path(output)
    validate_new_tree_destination(output)
    target = logical_path(target or source.name)
    raw = _read_bounded(source, MAX_CONTAINER)
    container = open_container(raw)
    entries = _select(list(text_assets(container)), names, set(path_ids), node)
    if not entries:
        raise FormatError("no TextAsset matched the selection")
    used, members, files = set(), [], {}
    for n, index, obj, ta in entries:
        encoding = guess_encoding(ta.script)
        name = _flat_name(ta.name, obj.path_id, encoding, used)
        members.append({"file": name, "node": n, "path_id": obj.path_id, "name": ta.name,
                        "size": len(ta.script), "sha256": sha256(ta.script), "encoding": encoding,
                        "entropy": entropy(ta.script), "layout": ta.layout,
                        "serialized_version": index.version, "unity_version": index.unity_version})
        files["original/textassets/" + name] = ta.script
    # Identity proof through the real writers: same scripts, rebuilt containers.
    identity = {(m["node"], m["path_id"]): ta.script for m, (_, _, _, ta) in zip(members, entries)}
    for n in {m["node"] for m in members}:
        data = container.serialized[n]
        index = us.read_index(io.BytesIO(data))
        objs = {o.path_id: data[o.offset:o.offset + o.size] for o in index.objects
                if (n, o.path_id) in identity}
        patched = {pid: patch_textasset(index, next(o for o in index.objects if o.path_id == pid), body,
                                        identity[(n, pid)]) for pid, body in objs.items()}
        if patched != objs or us.rebuild(data, patched) != data:
            raise FormatError(f"serialized writer is not byte-identical for {n!r}")
    rebuilt = rebuild_container(container, identity)
    checked, changed = verify_container(container, rebuilt, identity)
    if changed:
        raise FormatError("identity rebuild changed a TextAsset")
    files["original/" + source.name] = raw
    files["rebuilt/roundtrip/" + target] = rebuilt
    files["replace/.keep"] = b""
    files["metadata/manifest.json"] = _json({"engine": ENGINE, "profile": PROFILE, "members": members})
    report = {"engine": ENGINE, "profile": PROFILE, "source": str(source), "source_name": source.name,
              "source_size": len(raw), "source_sha256": sha256(raw), "target": target,
              "container": container.kind,
              "bundle": fs.describe(container.bundle) if container.bundle else None,
              "textassets": len(members), "verified_objects": checked,
              "identity_rebuild_sha256": sha256(rebuilt),
              "identity_serialized_byte_identical": True,
              "identity_bundle_byte_identical": rebuilt == raw,
              "runtime_verified": False}
    files["reports/extraction.json"] = _json(report)
    files["README.txt"] = (
        "Unity TextAsset 工作区（整段替换）\n\n"
        "original/textassets：选中 TextAsset 的 m_Script 原始字节；metadata/manifest.json 记录来源对象。\n"
        "替换时把改好的同名文件放入 replace/ 后告诉 agent；默认按原始字节写入，"
        "--text 则按 UTF-8 文本读入后编码回原编码。\n"
        "rebuilt/roundtrip 是经真实 writer 重建并逐对象读回核对的原文容器；"
        "UnityFS 会写成无压缩数据块，文件会变大。\n"
        "本工作区不解析剧本方言，不生成 gt_input；未覆盖游戏、未运行游戏。\n").encode("utf-8")
    write_new_tree(output, list(files.items()), LIMITS)
    return {k: v for k, v in report.items() if k != "bundle"}


def _encode_text(text_bytes, encoding, label):
    try:
        text = text_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise FormatError(f"{label}: replacement text is not UTF-8") from exc
    if encoding in ("ascii", "utf-8"):
        return text.encode("utf-8")
    if encoding == "utf-8-sig":
        return b"\xef\xbb\xbf" + text.encode("utf-8")
    if encoding in ("utf-16le", "utf-16be"):
        return (b"\xff\xfe" if encoding == "utf-16le" else b"\xfe\xff") + text.encode(encoding)
    if encoding == "cp932":
        try:
            return text.encode("cp932")
        except UnicodeEncodeError as exc:
            raise FormatError(f"{label}: {text[exc.start:exc.end]!r} is not encodable in CP932; "
                              "use the JIS substitution workflow or a raw replacement") from exc
    raise FormatError(f"{label}: text mode is not available for {encoding} TextAssets")


def pack(workspace, output, *, source_dir=None, text=False):
    workspace, output = Path(workspace), Path(output)
    validate_new_tree_destination(output)
    report = load_json(_read_bounded(workspace / "reports/extraction.json", 16 << 20))
    manifest = load_json(_read_bounded(workspace / "metadata/manifest.json", 16 << 20))
    if report.get("engine") != ENGINE or report.get("profile") != PROFILE or manifest.get("profile") != PROFILE:
        raise FormatError("not a Unity TextAsset workspace")
    source_name = report["source_name"]
    validate_names([source_name])
    target = logical_path(report["target"])
    raw = _read_bounded(workspace / "original" / source_name, MAX_CONTAINER)
    if len(raw) != report["source_size"] or sha256(raw) != report["source_sha256"]:
        raise FormatError("original container hash/size differs from the extraction report")
    container = open_container(raw)
    current = {(n, obj.path_id): ta for n, _, obj, ta in text_assets(container)}
    members = manifest["members"]
    if not isinstance(members, list) or not members:
        raise FormatError("empty TextAsset manifest")
    validate_names([m["file"] for m in members])
    source_dir = Path(source_dir) if source_dir else workspace / "replace"
    replacements, used, total = {}, [], 0
    for m in members:
        key = (m["node"], m["path_id"])
        ta = current.get(key)
        if ta is None or ta.name != m["name"] or sha256(ta.script) != m["sha256"]:
            raise FormatError(f"{m['file']}: original TextAsset differs from manifest")
        original = _read_bounded(workspace / "original/textassets" / m["file"], MAX_REPLACEMENT)
        if original != ta.script:
            raise FormatError(f"{m['file']}: original/textassets copy was modified")
        candidate = source_dir / m["file"]
        if not candidate.exists():
            continue
        payload = _read_bounded(candidate, MAX_REPLACEMENT)
        total += len(payload)
        if total > 4 * MAX_REPLACEMENT:
            raise FormatError("replacements exceed total budget")
        if text:
            payload = _encode_text(payload, m["encoding"], m["file"])
        replacements[key] = payload
        used.append(m["file"])
    known = {m["file"] for m in members} | {".keep"}
    unmatched = []
    if source_dir.is_dir():
        for i, path in enumerate(source_dir.iterdir()):
            if i > 100_000:
                raise FormatError("replacement directory exceeds budget")
            if path.name not in known:
                unmatched.append(path.name)
    if not replacements:
        raise FormatError(f"no replacement file found in {source_dir}")
    rebuilt = rebuild_container(container, replacements)
    checked, changed = verify_container(container, rebuilt, replacements)
    result = {"engine": ENGINE, "profile": PROFILE, "target": target, "source_sha256": report["source_sha256"],
              "size": len(rebuilt), "sha256": sha256(rebuilt), "container": container.kind,
              "replaced_files": used, "changed_objects": [{"node": n, "path_id": p} for n, p in changed],
              "unmatched_files": sorted(unmatched), "verified_objects": checked,
              "text_mode": text, "bundle_compression": "none" if container.kind == "unityfs" else None,
              "runtime_verified": False}
    files = {"files/" + target: rebuilt, "reports/rebuild.json": _json(result)}
    after = open_container(rebuilt)
    for n, _, obj, ta in text_assets(after):
        m = next((m for m in members if (m["node"], m["path_id"]) == (n, obj.path_id)), None)
        if m and m["file"] in used:
            files["readback/textassets/" + m["file"]] = ta.script
    files["README.txt"] = (
        "Unity TextAsset 回写结果\n"
        "files/ 内路径相对于游戏目录，是完整容器，不是增量补丁。\n"
        "已重新解析：目标 TextAsset 读回等于替换内容，其他对象与节点逐字节不变。\n"
        "UnityFS 以无压缩数据块写出，体积变大；游戏能否加载与显示尚未验证。\n"
        "部署前另存游戏中的原文件。\n").encode("utf-8")
    write_new_tree(output, list(files.items()), LIMITS)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("extract", help="copy selected TextAssets into a new workspace")
    p.add_argument("source", help="UnityFS bundle or serialized file")
    p.add_argument("output")
    p.add_argument("--name", action="append", default=[], dest="names", help="m_Name glob; repeatable")
    p.add_argument("--path-id", action="append", default=[], type=int, dest="path_ids")
    p.add_argument("--node", help="serialized node path inside a bundle")
    p.add_argument("--target", help="deployment path relative to the game root")
    p = commands.add_parser("pack", help="replace TextAssets and rebuild the container")
    p.add_argument("workspace")
    p.add_argument("output")
    p.add_argument("--source-dir", help="directory with replacement files (default: <workspace>/replace)")
    p.add_argument("--text", action="store_true", help="read replacements as UTF-8 text and re-encode")
    args = vars(parser.parse_args(argv))
    action = args.pop("command")
    try:
        result = extract(**args) if action == "extract" else pack(**args)
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
