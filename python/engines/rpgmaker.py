# SPDX-License-Identifier: GPL-3.0-only
"""RPG Maker MV JSON / VX converter-JSON, retaining typed paths and event codes.

This intentionally does NOT implement Ruby Marshal. Native dict/list values
are never recursively turned into JSON strings when restoring plugin data.
"""
from copy import deepcopy
from dataclasses import dataclass
import json

Path = tuple[str | int, ...]


@dataclass(frozen=True)
class Field:
    path: Path
    text: str
    code: int | None
    role: str


def _validate_tree(root: object, *, max_depth: int = 64, max_nodes: int = 1_000_000) -> None:
    stack = [(root, 0)]
    count = 0
    while stack:
        node, depth = stack.pop()
        count += 1
        if depth > max_depth or count > max_nodes:
            raise ValueError("JSON nesting/node limit exceeded (or cyclic input)")
        if type(node) is dict:
            if any(type(k) is not str for k in node):
                raise ValueError("JSON keys must be strings")
            stack.extend((v, depth + 1) for v in node.values())
        elif type(node) is list:
            stack.extend((v, depth + 1) for v in node)
        elif node is not None and type(node) not in (str, int, float, bool):
            raise TypeError("only JSON-native input types supported")


def _get(root: object, path: Path) -> object:
    node = root
    for step in path:
        if type(node) is list and type(step) is int and 0 <= step < len(node):
            node = node[step]
        elif type(node) is dict and type(step) is str and step in node:
            node = node[step]
        else:
            raise ValueError("invalid typed JSON path")
    return node


def _set(root: object, path: Path, value: object) -> object:
    if not path:
        return value
    parent = _get(root, path[:-1])
    _get(root, path)  # validate leaf key/index, including negative indices
    parent[path[-1]] = value
    return root


def extract_fields(root: object, *, variant: str = "mv", keys: tuple[str, ...] = ()) -> tuple[Field, ...]:
    """Safe event slots: 401/405[0], 102[0][choices], 320/324[1].

    Resource filenames in 101, code in 355/655, comments and Ruby type metadata
    are not text by default, even though upstream's broad table selects them.
    """
    if variant not in ("mv", "vx"):
        raise ValueError("variant must be mv or vx")
    _validate_tree(root)
    prefix = "@" if variant == "vx" else ""
    selected = {prefix + key.removeprefix(prefix) if prefix else key for key in keys}
    fields = []
    protected = {"ruby_class", "class", "bytes", "bytes_str"}

    def string(node: object, path: Path, code: int | None, role: str) -> None:
        if type(node) is str:
            fields.append(Field(path, node, code, role))
        elif variant == "vx" and type(node) is dict and set(node) == {"bytes_str"} and type(node["bytes_str"]) is str:
            fields.append(Field(path + ("bytes_str",), node["bytes_str"], code, role))

    def visit(node: object, path: Path) -> None:
        if type(node) is list:
            for i, child in enumerate(node):
                visit(child, path + (i,))
        elif type(node) is dict:
            code_key, params_key = prefix + "code", prefix + "parameters"
            if code_key in node:
                code = node[code_key]
                params = node.get(params_key)
                if type(code) is not int or type(params) is not list:
                    raise ValueError("invalid event command code/parameters")
                pp = path + (params_key,)
                if code in (401, 405):
                    if not params:
                        raise ValueError("message event has no parameter")
                    string(params[0], pp + (0,), code, "message")
                elif code == 102:
                    if not params or type(params[0]) is not list:
                        raise ValueError("choice event must retain nested choice array")
                    for i, child in enumerate(params[0]):
                        string(child, pp + (0, i), code, "choice")
                elif code in (320, 324):
                    if len(params) < 2:
                        raise ValueError("actor-name event missing value")
                    string(params[1], pp + (1,), code, "name")
                return
            if node.get("class") == "Symbol" or set(node) in ({"bytes"}, {"bytes_str"}):
                return
            for key, child in node.items():
                if key in protected:
                    continue
                child_path = path + (key,)
                if key in selected:
                    string(child, child_path, None, "name" if key == prefix + "name" else "metadata")
                visit(child, child_path)

    visit(root, ())
    return tuple(fields)


def apply_translations(root: object, replacements: dict[Path, str], *, variant: str = "mv", keys: tuple[str, ...] = ()) -> object:
    allowed = {field.path for field in extract_fields(root, variant=variant, keys=keys)}
    if any(path not in allowed for path in replacements):
        raise ValueError("replacement targets code, metadata, or an unselected field")
    result = deepcopy(root)
    for path, text in replacements.items():
        if type(text) is not str:
            raise TypeError("replacement must remain a JSON string")
        result = _set(result, path, text)
    return result


@dataclass(frozen=True)
class JsonBoundary:
    path: Path
    original: str
    decoded: object


def expand_json_strings(root: object, paths: tuple[Path, ...]) -> tuple[object, tuple[JsonBoundary, ...]]:
    """Only explicit string-valued paths are expanded; parents precede nested paths."""
    _validate_tree(root)
    if len(set(paths)) != len(paths):
        raise ValueError("duplicate embedded-JSON path")
    result = deepcopy(root)
    boundaries = []
    for path in sorted(paths, key=len):
        text = _get(result, path)
        if type(text) is not str:
            raise ValueError("embedded JSON boundary must originally be a string")
        parsed = json.loads(text)
        if type(parsed) not in (dict, list):
            raise ValueError("embedded JSON must encode an object or array")
        _validate_tree(parsed)
        boundaries.append(JsonBoundary(path, text, deepcopy(parsed)))
        result = _set(result, path, parsed)
        _validate_tree(result)
    return result, tuple(boundaries)


def restore_json_strings(expanded: object, boundaries: tuple[JsonBoundary, ...]) -> object:
    """Deepest boundaries first; untouched boundaries reuse original lexical JSON."""
    _validate_tree(expanded)
    result = deepcopy(expanded)
    for boundary in sorted(boundaries, key=lambda b: len(b.path), reverse=True):
        node = _get(result, boundary.path)
        if type(node) is not type(boundary.decoded):
            raise ValueError("embedded JSON root type changed")
        text = boundary.original if node == boundary.decoded else json.dumps(node, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        result = _set(result, boundary.path, text)
    return result


def load_ruby_marshal(data: bytes) -> object:
    raise NotImplementedError("Ruby Marshal class/symbol/object-link codec not included; use lossless converter")


def dump_ruby_marshal(root: object) -> bytes:
    raise NotImplementedError("cannot emit rvdata/rxdata from plain JSON without Ruby Marshal metadata")
