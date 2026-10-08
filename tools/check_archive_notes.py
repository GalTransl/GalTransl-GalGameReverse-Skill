"""Check archive documentation coverage against the independent source catalog."""
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def check():
    catalog = json.loads((ROOT / "catalog/formats.json").read_text(encoding="utf-8"))
    index = json.loads((ROOT / "catalog/archive-notes.json").read_text(encoding="utf-8"))
    source = json.loads((ROOT / "provenance/garbro-archive-excerpts.json").read_text(encoding="utf-8"))
    formats = [fmt for fmt in catalog["formats"] if fmt["kind"] == "archive"]
    expected = {(fmt["assembly"], fmt["qualified_class"], fmt["source"]["path"]) for fmt in formats}
    actual = {(fmt["assembly"], fmt["class"], fmt["source"]["path"]) for fmt in index["formats"]}
    errors = []
    if actual != expected or len(actual) != len(index["formats"]) or index["count"] != len(expected):
        errors.append("Archive entry inventory differs from source catalog")
    if source["commit"] != catalog["source_commit"]:
        errors.append("Source/catalog versions differ")
    documents = {record["path"]: record["document"] for record in source["sources"]}
    for fmt in formats:
        for method in ("TryOpen", "OpenEntry"):
            evidence = fmt["capabilities"]["methods"][method]
            if not evidence.get("declaration_found"):
                errors.append(f"Missing source method evidence: {fmt['qualified_class']}.{method}")
                continue
            path = evidence["source"]["path"]
            if path == "GameRes/ArchiveFormat.cs":
                # Default OpenEntry is documented as a bounded raw span.
                continue
            target = ROOT / documents.get(path, "missing-document")
            if not target.is_file():
                errors.append(f"Missing algorithm document: {path}")
                continue
            text = target.read_text(encoding="utf-8")
            owner = evidence["source"]["symbol"].rsplit(".", 1)[0]
            heading = "### " + owner + "\n"
            if heading not in text:
                errors.append(f"Missing method owner: {owner}")
                continue
            body = text.split(heading, 1)[1].split("\n### ", 1)[0]
            if f"#### {method}\n" not in body:
                errors.append(f"Missing algorithm: {owner}.{method}")
    referenced = {record["document"] for record in source["sources"]}
    shipped = {path.relative_to(ROOT).as_posix() for path in (ROOT / "engines/garbro").rglob("*.md")}
    if shipped != referenced | {"engines/garbro/reading.md"}:
        errors.append("Generated document inventory contains missing/stale files")
    for relative in sorted(referenced):
        path = ROOT / relative
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            if len(re.findall(r"^```", text, re.MULTILINE)) % 2:
                errors.append(f"Unbalanced code fences: {relative}")
    result = {"ok": not errors, "archive_entries": len(expected),
              "algorithm_documents": len(referenced), "errors": errors}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(check())
