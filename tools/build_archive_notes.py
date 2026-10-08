"""Build portable archive algorithm notes from the pinned GARbro source.

Development only: uses the existing bounded C# lexer, never executes C# or
deserializes Formats.dat. The generated Markdown, not the source checkout,
is the artifact used by installed skills.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import textwrap

from build_source_catalog import Repository, TOKEN_RE, lex, pairs, parse_cs, require

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "engines" / "garbro"
SKIP_MEMBERS = {
    "Tag", "Description", "Signature", "Signatures", "Extensions", "CanWrite",
    "IsHierarchic", "Scheme", "GetDefaultOptions", "GetAccessWidget", "GetOptions",
    "ReadMetaData", "Dispose",
    "ToString", "GetEnumerator",
}
INFRASTRUCTURE = {
    "ArchiveFormat", "ArcFile", "Entry", "PackedEntry", "AutoEntry", "ArcView",
    "FormatCatalog", "VFS", "Binary", "Encodings", "IBinaryStream", "BinaryStream",
    "ResourceScheme", "ResourceOptions", "ResourceInstance", "ImageFormat",
    "AudioFormat", "ImageData", "ImageMetaData", "IImageDecoder", "ScriptFormat",
    "StreamRegion", "BinMemoryStream", "PrefixStream", "InputProxyStream",
    "StreamProxy", "SeekableStream", "ProxyStream", "ConcatStream", "LimitStream",
    "PackedStream", "Decompressor", "CowArray", "CowData", "PhysicalFileSystem",
    "FileSystem", "ImageFormatDecoder", "UnknownEncryptionScheme",
    "InvalidFormatException", "InvalidEncryptionScheme", "NotSupportedException",
    "NotImplementedException", "ResourceFormat", "Crc32", "Adler32",
    "arcStrings",
}


def strip_comments(value):
    return TOKEN_RE.sub(lambda m: "" if m.lastgroup == "comment" else m.group(), value)


def excerpt(cls, member):
    value = strip_comments(member.header + " " + member.raw)
    if re.search(r"\b(?:class|struct)\b", member.header):
        return ""
    if member.name in SKIP_MEMBERS:
        return ""
    if re.search(r"\b(?:ImageData|ImageMetaData|IImageDecoder|BitmapSource|SoundInput)\s+" +
                 re.escape(member.name) + r"\s*\(", member.header):
        return ""
    if member.name in {"Create", "Write"} and re.search(r"\boverride\s+void\b", member.header):
        return ""
    # Per-title databases are external parameters, not generic format rules.
    if member.name.startswith("Known"):
        references = any(other is not member and re.search(r"\b" + re.escape(member.name) + r"\b",
                         strip_comments(other.raw)) for other in cls.members)
        if not references or member.form == "property" or re.search(r"Dictionary\s*<\s*string\b", value):
            return ""
    if "GUI." in value or "System.Windows" in value or "BitmapSource" in value:
        return ""
    # Bundled per-title filename lists are external data, not format constants.
    value = re.sub(r'"[^"\r\n]+\.lst"', "name_list_parameter", value, flags=re.IGNORECASE)
    lines = value.splitlines()
    if len(lines) > 1:
        value = lines[0].strip() + "\n" + textwrap.dedent("\n".join(lines[1:]))
    value = re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", value).strip()
    return value


def is_algorithm(cls):
    return bool(cls.members)


def used_type(name, code):
    escaped = re.escape(name)
    return bool(re.search(r"\b(?:new|as|is|typeof)\s*\(?\s*" + escaped + r"\b|"
                          r"(?<![.\w])" + escaped + r"\s*(?:[.<\[]|\s+\w+\s*[;,(=)\[])|"
                          r"<\s*" + escaped + r"\s*>", code))


def enum_declarations(source):
    ts = lex(source)
    ps = pairs(ts)
    result = []
    for i, token in enumerate(ts[:-1]):
        if token.value != "enum":
            continue
        start = next(j for j in range(i + 1, len(ts)) if ts[j].value == "{")
        result.append((ts[i + 1].value,
                       strip_comments(source[token.pos:ts[ps[start]].pos + 1])))
    return result


def type_aliases(source):
    return re.findall(r"\busing\s+(\w+)\s*=\s*([^;]+);", strip_comments(source))


def key(cls):
    return cls.assembly, cls.qualified


def document_path(source):
    p = PurePosixPath(source)
    return "engines/garbro/" + str(p.with_suffix(".md"))


def relative_link(source, target):
    import posixpath
    return posixpath.relpath(target, str(PurePosixPath(source).parent))


def markdown(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def metadata_value(field):
    if field.get("status") != "known":
        return "未解析（不据此猜测）"
    value = field["value"]
    if isinstance(value, list):
        return ", ".join(f"`{markdown(v)}`" for v in value) or "无固定值"
    return f"`{markdown(value)}`"


def render_source(source, classes, formats, dependencies, enums, aliases):
    doc = document_path(source)
    label = PurePosixPath(source).stem
    family = PurePosixPath(source).parent.name
    out = [f"# {family} / {label}：归档读取与解码", "",
           "算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](" +
           relative_link(doc, "engines/garbro/reading.md") + ")。", "",
           "## 格式入口", "", "| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |", "|---|---|---|---|"]
    for fmt in formats:
        magic = fmt["magic"]["nonzero_uint32_le_hex"]
        out.append("| `" + str(fmt["tag"]["value"]).split()[0] + "` / `" + fmt["qualified_class"] + "` | " + metadata_value(fmt["extensions"]) + " | " +
                   (", ".join(f"`{m}`" for m in magic) or "无固定签名或来源表达式未解析") + " | " +
                   metadata_value(fmt["capabilities"]["can_write"]) + " |")
        if fmt["registration_configurations"] == ["Debug"]:
            out.extend(["", "该入口只在来源 Debug 配置注册，不能当作 Release 工具的可用格式保证。"])
    if not formats:
        out.append("| 辅助算法 | 由调用入口决定 | 不单独识别容器 | 不作支持声明 |")
    if aliases:
        out.extend(["", "## 类型别名", "", "| 摘录中的名称 | 来源类型 |", "|---|---|"])
        out.extend(f"| `{alias}` | `{markdown(target.strip())}` |" for alias, target in aliases)

    chunks = [(cls, member, excerpt(cls, member)) for cls in classes for member in cls.members]
    chunks = [(cls, member, code) for cls, member, code in chunks if code]
    out.extend(["", "## 字段与结构读取", "",
                "以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。", "",
                "| 算法位置 | 读取表达式 |", "|---|---|"])
    facts = set()
    for cls, member, code in chunks:
        for line in code.splitlines():
            if re.search(r"\b(?:Read(?:U?Int\d+|Bytes|String|CString|Byte|Header)|To(?:U?Int\d+)|AsciiEqual)\s*\(", line):
                fact = (cls.name + "." + member.name, line.strip())
                if fact not in facts:
                    facts.add(fact)
                    out.append("| `" + fact[0] + "` | `" + markdown(fact[1]).replace("`", "'") + "` |")
    if not facts:
        out.append("| 辅助算法 | 不独立读取索引；见调用入口和下面的变换步骤 |")

    out.extend(["", "## 读取、解密与解压步骤", "",
                "按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。", ""])
    if enums:
        out.extend(["### 枚举值", "", "```csharp", "\n\n".join(code for _, code in enums), "```", ""])
    for cls in classes:
        selected = [(member, code) for owner, member, code in chunks if owner is cls]
        if not selected:
            continue
        out.extend([f"### {cls.qualified}", ""])
        if cls.bases:
            out.extend(["继承/接口：" + ", ".join(f"`{markdown(base)}`" for base in cls.bases) + "。", ""])
        state = [code for member, code in selected if member.form in {"field", "property"}]
        if state:
            out.extend(["#### 状态与常量", "", "```csharp", "\n\n".join(state), "```", ""])
        for member, code in selected:
            if member.form in {"field", "property"}:
                continue
            if re.fullmatch(r"[\s\S]*\{\s*\}", code):
                continue
            out.extend([f"#### {member.name}", "", "```csharp", code, "```", ""])

    out.extend(["## 配套算法与外部条件", ""])
    for other in sorted(dependencies):
        out.append(f"- [{other}]({relative_link(doc, document_path(other))})：本页引用的随包算法资料。")
    if not dependencies:
        out.append("本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。")
    out.extend(["", "## 出处与许可", "",
                f"来源文件标识 `{source}`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](" +
                relative_link(doc, "provenance/garbro-archive-excerpts.json") + ")和 [原通知](" +
                relative_link(doc, "provenance/garbro-archive-notices.md") + ")。路径是出处，不是使用时需要访问的外部文件。", ""])
    return "\n".join(out)


def build(source_root):
    repo = Repository("garbro", source_root)
    catalog = json.loads((ROOT / "catalog/formats.json").read_text(encoding="utf-8"))
    require(catalog["source_commit"] == repo.commit, "Catalog/source version mismatch")
    formats = [fmt for fmt in catalog["formats"] if fmt["kind"] == "archive"]
    projects = catalog["projects"]
    all_classes, by_path = [], defaultdict(list)
    for project in projects:
        repo.preload(project["compiled_sources"])
        for path in project["compiled_sources"]:
            values = parse_cs(repo.text(path), project["assembly"], path,
                              frozenset(project["debug_defines"]))
            all_classes.extend(values)
            by_path[path].extend(values)
    by_name, by_qualified = defaultdict(list), defaultdict(list)
    for cls in all_classes:
        by_name[cls.name].append(cls)
        by_qualified[key(cls)].append(cls)
    selected_classes = {}
    for fmt in formats:
        owners = by_qualified[(fmt["assembly"], fmt["qualified_class"])]
        require(any(cls.path == fmt["source"]["path"] for cls in owners), "Missing registered source owner")
        for cls in owners:
            selected_classes[(cls.path, cls.qualified)] = cls
    dependencies = defaultdict(set)
    pending = list(selected_classes.values())
    while pending:
        cls = pending.pop()
        path = cls.path
        codes = "\n".join(excerpt(cls, member) for member in cls.members)
        aliases = type_aliases(repo.text(path))
        for alias, target in aliases:
            codes = re.sub(r"\b" + re.escape(alias) + r"\b", target.strip(), codes)
        tokens = {token.value for token in lex(codes)} | set(cls.bases)
        for name in sorted(tokens):
            if name in INFRASTRUCTURE or name not in by_name:
                continue
            candidates = [other for other in by_name[name] if is_algorithm(other)]
            qualified = [other for other in candidates if other.qualified in codes
                         or any(target.strip().endswith("." + other.name) and
                                other.qualified.endswith("." + target.strip())
                                for _, target in aliases)]
            if not used_type(name, codes) and name not in cls.bases and not qualified:
                continue
            local = [other for other in candidates if other.namespace == cls.namespace]
            parents = [other for other in candidates if cls.namespace.startswith(other.namespace + ".")]
            if parents:
                nearest = max(len(other.namespace) for other in parents)
                parents = [other for other in parents if len(other.namespace) == nearest]
            imported = [other for other in candidates if other.namespace in cls.usings]
            choices = local or parents or imported or qualified
            for other in choices:
                if other.path.startswith("GameRes/"):
                    continue
                if other.path != path:
                    dependencies[path].add(other.path)
                identity = (other.path, other.qualified)
                if identity not in selected_classes:
                    selected_classes[identity] = other
                    pending.append(other)
    format_paths = defaultdict(list)
    for fmt in formats:
        owner = next(cls for cls in by_qualified[(fmt["assembly"], fmt["qualified_class"])]
                     if cls.path == fmt["source"]["path"])
        require(any(member.name == "TryOpen" for member in owner.members) or fmt["inheritance"],
                f"No parser evidence for {fmt['qualified_class']}")
        format_paths[fmt["source"]["path"]].append(fmt)

    selected_paths = {cls.path for cls in selected_classes.values()}
    by_selected_path = defaultdict(list)
    for cls in selected_classes.values():
        by_selected_path[cls.path].append(cls)
    artifacts, notices, source_records = {}, [], []
    for path in sorted(selected_paths):
        classes = sorted(by_selected_path[path], key=lambda cls: cls.pos)
        require(classes, f"No algorithm classes: {path}")
        source = repo.text(path)
        artifacts[document_path(path)] = render_source(path, classes, format_paths[path], dependencies[path],
                                                      enum_declarations(source), type_aliases(source))
        header = source[:next((t.pos for t in lex(source)), len(source))].strip()
        # Preserve notices, not dated descriptions or per-game examples.
        notice_lines = [line for line in header.splitlines()
                        if not re.match(r"\s*//!|\s*//\s*\[\d", line)]
        notice = "\n".join(notice_lines).strip()
        if notice:
            notices.extend([f"## {path}", "", "```text", notice, "```", ""])
        source_records.append({"path": path, "decoded_utf8_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
                               "document": document_path(path), "classes": [cls.qualified for cls in classes]})
    records = [{"assembly": fmt["assembly"], "class": fmt["qualified_class"],
                "document": document_path(fmt["source"]["path"]),
                "source": fmt["source"], "kind": "algorithm-reference; not tested runtime support"}
               for fmt in formats]
    artifacts["catalog/archive-notes.json"] = json.dumps({
        "schema": "garbro-archive-algorithm-index/1", "count": len(records),
        "formats": records}, ensure_ascii=False, indent=2) + "\n"
    artifacts["provenance/garbro-archive-excerpts.json"] = json.dumps({
        "repository": "https://github.com/nanami5270/GARbro-Mod", "commit": repo.commit,
        "purpose": "Algorithm excerpts in Markdown; no C# runtime dependency",
        "changes": "Comments and UI/registration/writer/cleanup members omitted; fixed filename-list resource literals replaced with name_list_parameter; trailing line whitespace removed; original reading and decoding expressions otherwise retained",
        "license": "Per-file original notices in garbro-archive-notices.md; root MIT is not a blanket license",
        "sources": source_records}, ensure_ascii=False, indent=2) + "\n"
    artifacts["provenance/garbro-archive-notices.md"] = "# 归档算法摘录的原版权与许可通知\n\n" + \
        "源文件头通知按原文保留；没有单独文件通知的组件仍须核对根许可与来源记录，不能据此推断无条件授权。\n\n" + "\n".join(notices)
    families = defaultdict(list)
    for fmt in formats:
        p = PurePosixPath(fmt["source"]["path"])
        family = str(p.parent)
        families[family].append(fmt)
    index = ["# GARbro 归档算法资料索引", "",
             "本索引覆盖固定来源版本的全部 681 个归档注册入口。每项链接包含字段读取表达式、读取/解密/解压算法及专用辅助算法；这些是源码证据，不是随包运行能力或商业游戏验收。", "",
             "先读 [读取约定](../engines/garbro/reading.md)。常见格式的中文说明见 [归档资料入口](archive-notes.md)。", ""]
    for family, items in sorted(families.items()):
        index.extend([f"## {family}", "", "| 格式/API 标识 | 算法资料 |", "|---|---|"])
        for fmt in items:
            tag = str(fmt["tag"]["value"]).split()[0]
            index.append(f"| `{tag}` / `{fmt['qualified_class']}` | [{PurePosixPath(fmt['source']['path']).stem}](../{document_path(fmt['source']['path'])}) |")
        index.append("")
    artifacts["catalog/garbro-archive-index.md"] = "\n".join(index)
    for relative in artifacts:
        if relative.endswith(".md"):
            artifacts[relative] = "\n".join(line.rstrip() for line in artifacts[relative].split("\n"))
    return artifacts, len(formats), len(selected_paths)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--garbro", required=True)
    parser.add_argument("--check", action="store_true", help="Compare generated contents without writing")
    args = parser.parse_args()
    artifacts, count, sources = build(args.garbro)
    if not args.check:
        # Only remove stale files previously owned by this generator.
        previous = ROOT / "provenance/garbro-archive-excerpts.json"
        if previous.is_file():
            old = json.loads(previous.read_text(encoding="utf-8"))
            for record in old["sources"]:
                relative = record["document"]
                target = (ROOT / relative).resolve()
                require(target.is_relative_to(DEST.resolve()), "Stale document outside generated directory")
                if relative not in artifacts and target.is_file():
                    target.unlink()
    mismatches = []
    for relative, content in artifacts.items():
        target = ROOT / relative
        if args.check:
            if not target.is_file() or target.read_text(encoding="utf-8") != content:
                mismatches.append(relative)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8", newline="\n")
    if mismatches:
        raise SystemExit("Generated artifacts differ: " + ", ".join(mismatches))
    print(f"Archive entries: {count}; algorithm source documents: {sources}; checked: {args.check}")


if __name__ == "__main__":
    main()
