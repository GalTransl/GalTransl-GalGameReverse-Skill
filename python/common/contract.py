"""Minimal ordered translation JSON and an independent provenance sidecar.

New implementation; no GalTransl dependency. Compatibility was checked against
GalTransl/Loader.py and the upstream name/message serializers listed in
provenance/sources.json. Locators and control tokens must come from a real
engine parser: this module cannot discover dialogue or fix a binary format.
"""

from copy import deepcopy
import codecs
import hashlib
import json
from typing import Any

from .binary import FormatError
from .safety import validate_names

SCHEMA = "galgame-roundtrip/1"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise FormatError("value is not strict UTF-8 JSON") from exc


def validate_rows(rows: Any) -> list[dict]:
    """Validate the minimal interchange, retaining optional multi-speaker names."""
    if not isinstance(rows, list):
        raise FormatError("translation JSON must be an array")
    for i, row in enumerate(rows):
        if not isinstance(row, dict) or not isinstance(row.get("message"), str):
            raise FormatError(f"row {i}: message must be a string")
        if set(row) - {"name", "names", "message"}:
            raise FormatError(f"row {i}: keep IDs and other metadata in the sidecar")
        if "name" in row and "names" in row:
            raise FormatError(f"row {i}: name and names are mutually exclusive")
        if "name" in row and not isinstance(row["name"], str):
            raise FormatError(f"row {i}: name must be a string")
        if "names" in row:
            if not isinstance(row["names"], list) or not all(isinstance(n, str) for n in row["names"]):
                raise FormatError(f"row {i}: names must be a string array")
    _json_bytes(rows)  # Includes rejection of unpaired Unicode surrogates.
    return deepcopy(rows)


def dump_rows(rows: list[dict]) -> bytes:
    """Serialize dialogue with name/names before message for every engine."""
    rows = validate_rows(rows)
    rows = [{key: row[key] for key in ("name", "names", "message") if key in row}
            for row in rows]
    return (json.dumps(rows, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def load_json(data: bytes, *, max_bytes: int = 16 * 1024 * 1024) -> Any:
    """Read bounded strict JSON; duplicate keys/NaN are errors, not last-wins."""
    if not isinstance(data, bytes) or len(data) > max_bytes:
        raise FormatError("JSON input exceeds limit or is not bytes")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise FormatError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def constant(value):
        raise FormatError(f"non-JSON numeric constant: {value}")

    try:
        return json.loads(data.decode("utf-8-sig"), object_pairs_hook=pairs,
                          parse_constant=constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise FormatError(f"invalid JSON: {exc}") from exc


def _validate_manifest(manifest: Any) -> None:
    """Validate basic identity/types, independently of engine locator semantics."""
    def digest(value):
        return (isinstance(value, str) and len(value) == 64
                and all(char in "0123456789abcdef" for char in value))

    def nonempty(value):
        return isinstance(value, str) and bool(value.strip())

    try:
        if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA:
            raise FormatError("unsupported manifest schema")
        engine = manifest["engine"]
        if not isinstance(engine, dict) or not all(nonempty(engine[key]) for key in ("id", "variant", "reference")):
            raise FormatError("manifest requires nonempty engine/variant/reference")
        encoding = manifest["encoding"]
        if not nonempty(encoding):
            raise FormatError("manifest requires an explicit text encoding")
        "".encode(encoding, errors="strict")  # Validate even when there are no rows.
        if not isinstance(manifest["settings"], dict):
            raise FormatError("manifest settings must be an object")
        source_records = manifest["sources"]
        if not isinstance(source_records, list) or not source_records:
            raise FormatError("manifest requires original sources")
        names = []
        for source in source_records:
            if not isinstance(source, dict) or type(source["size"]) is not int or source["size"] < 0:
                raise FormatError("source size must be a nonnegative integer")
            if not digest(source["sha256"]):
                raise FormatError("invalid source digest")
            names.append(source["path"])
        if validate_names(names) != names:
            raise FormatError("source paths must use relative slash paths")
        translation = manifest["translation"]
        if not isinstance(translation, dict) or type(translation["count"]) is not int or translation["count"] < 0:
            raise FormatError("translation count must be a nonnegative integer")
        if not digest(translation["source_rows_sha256"]):
            raise FormatError("invalid original export digest")
        if translation["order"] != "must-preserve; equal-length-reorder-not-detectable":
            raise FormatError("unsupported translation identity policy")
        records = manifest["records"]
        if not isinstance(records, list) or len(records) != translation["count"]:
            raise FormatError("manifest records/count disagree")
        ids = set()
        for i, record in enumerate(records):
            if not isinstance(record, dict) or type(record["position"]) is not int or record["position"] != i:
                raise FormatError("record position must be an ordered integer")
            if not nonempty(record["id"]) or record["id"] in ids:
                raise FormatError("record IDs must be nonempty and unique")
            ids.add(record["id"])
            if not isinstance(record["locator"], dict) or not record["locator"]:
                raise FormatError("record requires an engine locator object")
            if record["name_policy"] not in ("absent", "context", "writable"):
                raise FormatError("invalid name policy")
            tokens = record["message_tokens"]
            if not isinstance(tokens, list) or not all(isinstance(token, str) and token for token in tokens):
                raise FormatError("invalid protected token inventory")
            if len(tokens) != len(set(tokens)):
                raise FormatError("duplicate protected tokens")
        _json_bytes(manifest)
    except (KeyError, TypeError, LookupError, UnicodeError) as exc:
        raise FormatError(f"invalid manifest schema or encoding: {exc}") from exc


def make_manifest(*, engine: str, variant: str, reference: str,
                  sources: dict[str, bytes], rows: list[dict],
                  locators: list[dict], encoding: str,
                  name_policies: list[str] | None = None,
                  protected_tokens: list[list[str]] | None = None,
                  settings: dict | None = None) -> dict:
    """Build metadata from parser-owned locations. No discovery or filesystem IO.

    name_policies: 'context' (default), 'writable', or 'absent'. Context-only
    names are not editable here; the engine may expose a separate name table.
    protected_tokens lists exact MESSAGE literals, not regexes or code.
    """
    rows = validate_rows(rows)
    if not all(isinstance(value, str) and value for value in (engine, variant, reference, encoding)):
        raise FormatError("engine, variant, reference and encoding must be explicit")
    if not sources or not all(isinstance(value, bytes) for value in sources.values()):
        raise FormatError("original source bytes are required")
    paths = validate_names(list(sources))
    if paths != list(sources):
        raise FormatError("source keys must already use relative slash paths")
    if len(locators) != len(rows) or not all(isinstance(item, dict) and item for item in locators):
        raise FormatError("every record requires an explicit engine locator")
    if name_policies is None:
        name_policies = ["context" if "name" in row or "names" in row else "absent" for row in rows]
    if protected_tokens is None:
        protected_tokens = [[] for _ in rows]
    if len(name_policies) != len(rows) or len(protected_tokens) != len(rows):
        raise FormatError("metadata and row counts disagree")
    records = []
    for i, (row, locator, policy, tokens) in enumerate(zip(rows, locators, name_policies, protected_tokens)):
        if policy not in ("context", "writable", "absent"):
            raise FormatError(f"row {i}: unknown name policy")
        has_name = "name" in row or "names" in row
        if (policy == "absent") == has_name:
            raise FormatError(f"row {i}: name policy disagrees with JSON fields")
        if not isinstance(tokens, list) or not all(isinstance(token, str) and token for token in tokens):
            raise FormatError(f"row {i}: tokens must be nonempty string literals")
        if len(set(tokens)) != len(tokens) or any(token not in row["message"] for token in tokens):
            raise FormatError(f"row {i}: duplicate tokens or token absent from source")
        records.append({
            "id": f"r{i + 1:08d}", "position": i, "locator": deepcopy(locator),
            "name_policy": policy, "message_tokens": list(tokens),
        })
    manifest = {
        "schema": SCHEMA,
        "engine": {"id": engine, "variant": variant, "reference": reference},
        "sources": [{"path": path, "size": len(sources[path]), "sha256": sha256(sources[path])}
                    for path in sorted(sources)],
        "translation": {"count": len(rows), "source_rows_sha256": sha256(_json_bytes(rows)),
                        "order": "must-preserve; equal-length-reorder-not-detectable"},
        "encoding": encoding, "settings": deepcopy({} if settings is None else settings), "records": records,
    }
    _validate_manifest(manifest)
    return manifest


def validate_translation(manifest: dict, sources: dict[str, bytes],
                         original_rows: list[dict], translated_rows: list[dict],
                         *, text_codec=None) -> list[dict]:
    """Validate correspondence, not game semantics; preserve-order is mandatory.

    A matching row count cannot detect equal-length reordering of translations.
    Do not use this result alone to authorize writing arbitrary script bytes.
    The adapter must validate locators, control syntax, lengths and references.
    An explicit text_codec may implement a reversible encoding policy (e.g.
    JIS substitution); its encoding must match the manifest. Return real text,
    never proxy rows. The writer must use the SAME codec and reverse-verify it.
    """
    _validate_manifest(manifest)
    original = validate_rows(original_rows)
    translated = validate_rows(translated_rows)
    try:
        if text_codec is not None and codecs.lookup(text_codec.encoding).name != codecs.lookup(manifest["encoding"]).name:
            raise FormatError("text codec differs from manifest script encoding")
        def encode_text(text):
            return text_codec.encode(text) if text_codec is not None else text.encode(manifest["encoding"], errors="strict")

        if manifest["schema"] != SCHEMA:
            raise FormatError("unsupported manifest schema")
        if manifest["translation"]["count"] != len(original) or len(translated) != len(original):
            raise FormatError("record count changed")
        if manifest["translation"]["source_rows_sha256"] != sha256(_json_bytes(original)):
            raise FormatError("original export has changed")
        source_records = manifest["sources"]
        names = [record["path"] for record in source_records]
        if validate_names(names) != names or set(names) != set(sources):
            raise FormatError("source file set changed")
        for record in source_records:
            data = sources[record["path"]]
            if not isinstance(data, bytes) or len(data) != record["size"] or sha256(data) != record["sha256"]:
                raise FormatError(f"source changed: {record['path']}")
        records = manifest["records"]
        if not isinstance(records, list) or len(records) != len(original):
            raise FormatError("manifest record count changed")
        ids = set()
        for i, (before, after, record) in enumerate(zip(original, translated, records)):
            if record["position"] != i or not isinstance(record["id"], str) or record["id"] in ids:
                raise FormatError("duplicate IDs or inconsistent manifest order")
            ids.add(record["id"])
            if set(before) != set(after):
                raise FormatError(f"row {i}: fields were added or removed")
            if "names" in before and len(before["names"]) != len(after["names"]):
                raise FormatError(f"row {i}: multi-speaker slot count changed")
            policy = record["name_policy"]
            if policy not in ("absent", "context", "writable"):
                raise FormatError(f"row {i}: invalid name policy")
            has_name = "name" in before or "names" in before
            if (policy == "absent") == has_name:
                raise FormatError(f"row {i}: name policy disagrees with JSON fields")
            if policy == "context":
                for field in ("name", "names"):
                    if before.get(field) != after.get(field):
                        raise FormatError(f"row {i}: context-only name was translated")
            tokens = record["message_tokens"]
            if not isinstance(tokens, list) or not all(isinstance(t, str) and t for t in tokens):
                raise FormatError("invalid token inventory")
            for token in tokens:
                if text_codec is not None:
                    # Tokens are engine syntax, not substitution candidates.
                    token.encode(manifest["encoding"], errors="strict")
                count = before["message"].count(token)
                if count == 0 or after["message"].count(token) != count:
                    raise FormatError(f"row {i}: protected token changed: {token!r}")
            encode_text(after["message"])
            if policy == "writable":
                names_to_encode = after.get("names", [after["name"]] if "name" in after else [])
                for name in names_to_encode:
                    encode_text(name)
    except (KeyError, TypeError, IndexError, LookupError, UnicodeError) as exc:
        raise FormatError(f"invalid manifest, encoding or translation: {exc}") from exc
    return translated
