# SPDX-License-Identifier: GPL-3.0-only
# Adapted from SExtractor tools/Overflow/MISS EACH OTHER/script_xml_text.py
# Source commit: 8d8d976fd04ae54e7c677705af937273d04a376a
# Upstream attribution: 瑜瑜 & Steins;Gate; SExtractor contributors.
"""Overflow TextRes/Log XML dialect only; no archive or OBJ support."""
import xml.etree.ElementTree as ET


def _document(xml):
    if not isinstance(xml, str) or len(xml) > 8_000_000:
        raise ValueError("expected bounded decoded XML text")
    if "<!DOCTYPE" in xml.upper() or "<!ENTITY" in xml.upper():
        raise ValueError("DTD/entity declarations are not supported")
    root = ET.fromstring(xml)
    if root.tag != "Script":
        raise ValueError("not the Script/TextRes/Log dialect")
    resources = {}
    for node in root.findall(".//TextRes"):
        key = node.get("NO")
        if key is None or key in resources or len(node):
            raise ValueError("missing/duplicate resource ID or mixed content")
        resources[key] = node
    logs = []
    for log in root.findall(".//Log"):
        mid, nid = log.get("MESS", ""), log.get("NAME", "")
        if not mid:
            continue
        if mid not in resources or (nid and nid not in resources):
            raise ValueError("dangling Log resource reference")
        logs.append((nid, mid))
    return root, resources, logs


def extract_xml(xml):
    """Return each Log occurrence, retaining shared resource IDs (no text guessing)."""
    _, resources, logs = _document(xml)
    return [{"id": i, "name_id": nid, "message_id": mid,
             "name": resources[nid].text or "" if nid else "",
             "message": resources[mid].text or ""}
            for i, (nid, mid) in enumerate(logs)]


def rewrite_xml(xml, replacements):
    """Map TextRes NO -> text; only Log-referenced IDs may be changed.

    One shared ID has one translation. XML formatting can change; callers choose
    output encoding and must verify the external binary/XML conversion stage.
    """
    root, resources, logs = _document(xml)
    allowed = {key for pair in logs for key in pair if key}
    if set(replacements) - allowed:
        raise ValueError("replacement is not a Log name/message resource")
    for key, text in replacements.items():
        if not isinstance(text, str) or any(ord(c) < 32 and c not in "\t\r\n" for c in text):
            raise ValueError("invalid XML text")
        resources[key].text = text
    if not replacements:
        return xml
    return ET.tostring(root, encoding="unicode")
