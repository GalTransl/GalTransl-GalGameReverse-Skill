"""Entis GLS SRCXML attribute dialogue/choice traversal, semantic XML writer.
Source: msg-tool, src/scripts/entis_gls/srcxml.rs,
SrcXmlScript::extract_messages/import_messages.
Commit f72716cee88554d40c1cdface2812493b14ca653; GPL-3.0-or-later.
This adaptation uses strict stdlib XML, not xml5ever recovery. Auto-language
ambiguity is rejected, and menu attributes (not select) are inspected.
"""
from dataclasses import dataclass
import re
import xml.etree.ElementTree as ET


@dataclass(frozen=True)
class Message:
    index: int
    kind: str
    name: str | None
    message: str
    name_writable: bool
    text_attribute: str
    name_attribute: str | None


def _parse(xml: str, language: str | None):
    if not isinstance(xml, str) or re.search(r"<!\s*(DOCTYPE|ENTITY)\b", xml, re.I):
        raise ValueError("DTD/entities are not accepted")
    if len(xml) > 32 * 1024 * 1024:
        raise ValueError("SRCXML exceeds reference size limit")
    try:
        parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True, insert_pis=True))
        root = ET.fromstring(xml, parser=parser)
    except ET.ParseError as exc:
        raise ValueError("invalid SRCXML") from exc
    if root.tag != "xscript":
        raise ValueError("expected unqualified xscript root")
    nodes = []
    for code in root:
        if code.tag != "code":
            continue
        for instruction in code:
            if instruction.tag == "msg":
                nodes.append((instruction, "message"))
            elif instruction.tag == "select":
                nodes.extend((menu, "choice") for menu in instruction if menu.tag == "menu")
    if language is None:
        langs = {key[5:] for node, _ in nodes for key in node.attrib
                 if key.startswith(("name_", "text_"))}
        if len(langs) > 1:
            raise ValueError("multiple languages: select one explicitly")
        language = next(iter(langs), "")
    if not isinstance(language, str) or (language and not re.fullmatch(r"[\w-]+", language)):
        raise ValueError("invalid language suffix")
    suffix = "_" + language if language else ""
    text_key, name_key = "text" + suffix, "name" + suffix
    records = []
    for index, (node, kind) in enumerate(nodes):
        if text_key not in node.attrib:
            raise ValueError(f"missing {text_key} at record {index}")
        writable = kind == "message" and name_key in node.attrib
        records.append(Message(index, kind, node.get(name_key) or None if writable else None,
                               node.attrib[text_key], writable, text_key,
                               name_key if writable else None))
    return root, nodes, tuple(records)


def extract_srcxml(xml: str, language: str | None = None) -> tuple[Message, ...]:
    """Read xscript/code/msg plus select/menu; all empty records retain identity."""
    return _parse(xml, language)[2]


def patch_srcxml(xml: str, replacements: dict[int, dict[str, str]],
                 language: str | None = None) -> str:
    """Patch message/name attributes by record index; absent names cannot be invented.

    Returns XML text, not file bytes. Re-serialization can normalize entity spelling,
    quotes and empty tags; comments, other attributes, languages and child order stay.
    """
    root, nodes, records = _parse(xml, language)
    if any(type(k) is not int or not 0 <= k < len(records) for k in replacements):
        raise ValueError("unknown SRCXML record")
    for index, changes in replacements.items():
        if changes.keys() - {"name", "message"}:
            raise ValueError("unknown translation field")
        record = records[index]
        node = nodes[index][0]
        for key, value in changes.items():
            if not isinstance(value, str) or any(
                ord(c) < 32 and c not in "\t\r\n" or 0xD800 <= ord(c) <= 0xDFFF
                or ord(c) in (0xFFFE, 0xFFFF) for c in value
            ):
                raise ValueError("invalid XML text")
            if key == "name":
                if not record.name_writable:
                    raise ValueError("name is absent/context-only")
                node.set(record.name_attribute, value)
            else:
                node.set(record.text_attribute, value)
    if not replacements:
        return xml
    result = ET.tostring(root, encoding="unicode")
    _parse(result, language)  # Validate the serialized structure before returning.
    return result
