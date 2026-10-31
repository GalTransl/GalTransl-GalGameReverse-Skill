"""Lossless, deterministic storage for the bundled source-format inventory.

Schema 2 shares repeated objects and source identities; callers receive the
original schema-1 metadata, including unknown expressions and source claims.
"""
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def compact_formats(document):
    if document.get("schema_version") != 1:
        raise ValueError("Expected expanded source catalog schema 1")
    repository, commit = "garbro", document["source_commit"]

    def encode(value, context=None):
        if isinstance(value, dict):
            if "$ref" in value or "$source" in value:
                raise ValueError("Reserved catalog marker in input")
            if (set(value) in ({"repository", "commit", "path", "line"},
                               {"repository", "commit", "path", "line", "symbol"})
                    and value["repository"] == repository and value["commit"] == commit):
                path = value["path"]
                if context and value is not context["source"] and path == context["source"]["path"]:
                    path = None
                source = [path, value["line"]]
                if "symbol" in value:
                    symbol = value["symbol"]
                    if context and isinstance(symbol, str):
                        owner = context["qualified_class"]
                        if symbol == owner or symbol.startswith(owner + "."):
                            symbol = symbol[len(owner):]
                    source.append(symbol)
                return {"$source": source}
            return {key: encode(item, context) for key, item in value.items()}
        if isinstance(value, list):
            return [encode(item, context) for item in value]
        return value

    encoded = {key: encode(value) for key, value in document.items() if key != "formats"}
    encoded["formats"] = [encode(entry, entry) for entry in document["formats"]]
    counts = Counter()

    def count(value):
        if isinstance(value, dict):
            counts[_json(value)] += 1
            for item in value.values():
                count(item)
        elif isinstance(value, list):
            for item in value:
                count(item)

    count(encoded)
    shared, references = [], {}

    def pool(value):
        if isinstance(value, dict):
            key = _json(value)
            if counts[key] > 1 and len(key) > 80:
                if key not in references:
                    index = len(shared)
                    references[key] = index
                    shared.append(None)
                    shared[index] = {name: pool(item) for name, item in value.items()}
                return {"$ref": references[key]}
            return {name: pool(item) for name, item in value.items()}
        if isinstance(value, list):
            return [pool(item) for item in value]
        return value

    result = pool(encoded)
    result["schema_version"] = 2
    result["source_repository"] = repository
    result["shared"] = shared
    return result


def expand_formats(document, *, max_nodes=1_000_000, max_depth=64):
    version = document.get("schema_version")
    if version == 1:
        return deepcopy(document)
    if version != 2:
        raise ValueError("Unsupported source catalog schema")
    shared = document["shared"]
    if not isinstance(shared, list):
        raise ValueError("Catalog shared table must be an array")
    remaining = max_nodes

    def resolve(value, active=(), depth=0):
        nonlocal remaining
        remaining -= 1
        if remaining < 0 or depth > max_depth:
            raise ValueError("Catalog expansion budget exceeded")
        if isinstance(value, dict):
            if "$ref" in value:
                index = value["$ref"]
                if (len(value) != 1 or type(index) is not int or not 0 <= index < len(shared)
                        or index in active):
                    raise ValueError("Invalid or cyclic catalog reference")
                return resolve(shared[index], active + (index,), depth + 1)
            return {key: resolve(item, active, depth + 1) for key, item in value.items()}
        if isinstance(value, list):
            return [resolve(item, active, depth + 1) for item in value]
        return value

    result = resolve({key: value for key, value in document.items() if key != "shared"})
    repository = result.pop("source_repository")
    commit = result["source_commit"]

    def sources(value, context=None):
        if isinstance(value, dict):
            if "$source" in value:
                source = value["$source"]
                if (len(value) != 1 or not isinstance(source, list) or len(source) not in (2, 3)
                        or type(source[1]) is not int or source[1] < 1):
                    raise ValueError("Invalid catalog source marker")
                path = source[0]
                if path is None and context:
                    path = context["path"]
                if not isinstance(path, str):
                    raise ValueError("Catalog source path has no context")
                record = {"repository": repository, "commit": commit, "path": path, "line": source[1]}
                if len(source) == 3:
                    symbol = source[2]
                    if symbol is not None and not isinstance(symbol, str):
                        raise ValueError("Invalid catalog source symbol")
                    if symbol == "" or (isinstance(symbol, str) and symbol.startswith(".")):
                        if not context:
                            raise ValueError("Catalog source symbol has no context")
                        symbol = context["owner"] + symbol
                    record["symbol"] = symbol
                return record
            return {key: sources(item, context) for key, item in value.items()}
        if isinstance(value, list):
            return [sources(item, context) for item in value]
        return value

    entries = result.pop("formats")
    result = sources(result)
    result["formats"] = []
    for entry in entries:
        source = entry["source"]["$source"]
        context = {"path": source[0], "owner": entry["qualified_class"]}
        result["formats"].append(sources(entry, context))
    result["schema_version"] = 1
    return result


def load_formats(path):
    path = Path(path)
    with path.open("rb") as stream:
        payload = stream.read(8_000_001)
    if len(payload) > 8_000_000:
        raise ValueError("Source catalog exceeds 8 MB input budget")
    return expand_formats(json.loads(payload.decode("utf-8")))


def dump_formats(document):
    """One format/shared record per line, with ordinary JSON field names."""
    compact = compact_formats(document)
    lines = []
    for key, value in compact.items():
        if key in ("formats", "shared"):
            body = "[\n" + ",\n".join("    " + _json(item) for item in value) + "\n  ]"
        else:
            body = _json(value)
        lines.append("  " + _json(key) + ": " + body)
    return "{\n" + ",\n".join(lines) + "\n}\n"
