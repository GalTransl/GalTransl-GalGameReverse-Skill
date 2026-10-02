"""Validate the copied skill without imports from game or upstream code.

Checks links, Python syntax, document examples, index coverage and portability.
It does not prove engine support or substitute for source review/roundtrips.
"""

import ast
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_ENGINES = {
    "willplus", "artemis", "bgi", "catsystem2", "kirikiri", "musica", "qlie",
    "silky", "softpal", "yuris", "circus", "entis-gls", "escude", "exhibit",
    "favorite", "hexenhaus", "yaneurao", "arcgameengine", "cyberworks", "kaguya",
    "majiro", "mware", "propeller", "reallive", "renpy", "shsystem", "systemnnn",
    "tmrhiro", "whale", "nscripter", "siglus",
}
LOCAL_PATH = re.compile(r"(?:[A-Za-z]:[\\/]Users[\\/](?=[\w .-]+[\\/])|/c/Users/(?=[\w .-]+/)|\.claude/worktrees/)", re.IGNORECASE)
# Engine-specific optional codecs, documented in engines/nexas.md. Keep the
# exception scoped to its module; imports must remain lazy and ImportError-safe.
OPTIONAL_RUNTIME_IMPORTS = {"python/archives/nexas.py": {"zstandard"}}


def runtime_dependency_errors(tree: ast.AST, relative: str) -> list[str]:
    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    errors = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name.split(".")[0] for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [(node.module or "").split(".")[0]] if not node.level else []
        else:
            continue
        for name in names:
            if name in sys.stdlib_module_names or name in ("python", "__future__"):
                continue
            if name not in OPTIONAL_RUNTIME_IMPORTS.get(relative, set()):
                errors.append(f"{relative}: non-stdlib/runtime dependency: {name}")
                continue
            ancestors = []
            current = node
            while current in parents:
                current = parents[current]
                ancestors.append(current)
            lazy = any(isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)) for parent in ancestors)
            # The import itself must be in the protected try body, not in an
            # except/finally branch where missing dependencies would escape.
            guarded = any(
                isinstance(parent, ast.Try) and node in parent.body
                and any(isinstance(handler.type, ast.Name)
                        and handler.type.id in ("ImportError", "ModuleNotFoundError")
                        for handler in parent.handlers)
                for parent in ancestors
            )
            if not lazy or not guarded:
                errors.append(f"{relative}: optional dependency must be lazily imported under ImportError handling: {name}")
    return errors


def check() -> tuple[list[str], dict]:
    errors = []
    stats = {"python_files": 0, "markdown_files": 0, "python_examples": 0, "engine_pages": 0}
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        relative = path.relative_to(ROOT).as_posix()
        if path.suffix not in (".py", ".md", ".json"):
            continue
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeError as exc:
            errors.append(f"{relative}: not UTF-8: {exc}")
            continue
        # This checker contains the patterns by design, not a user's path.
        if relative != "tools/check_skill.py" and LOCAL_PATH.search(text):
            errors.append(f"{relative}: machine/worktree-specific path")
        if path.suffix == ".py":
            stats["python_files"] += 1
            try:
                tree = ast.parse(text, filename=relative)
            except SyntaxError as exc:
                errors.append(f"{relative}:{exc.lineno}: {exc.msg}")
                continue
            if relative.startswith("python/"):
                errors.extend(runtime_dependency_errors(tree, relative))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call):
                        function = node.func
                        if isinstance(function, ast.Name) and function.id in ("eval", "exec"):
                            errors.append(f"{relative}:{node.lineno}: forbidden dynamic execution")
                        if isinstance(function, ast.Attribute) and isinstance(function.value, ast.Name):
                            if function.value.id == "pickle" and function.attr in ("load", "loads"):
                                errors.append(f"{relative}:{node.lineno}: unrestricted pickle loading")
        elif path.suffix == ".md":
            stats["markdown_files"] += 1
            for match in re.finditer(r"```python\s*\n(.*?)\n```", text, re.DOTALL):
                stats["python_examples"] += 1
                try:
                    ast.parse(match.group(1), filename=relative)
                except SyntaxError as exc:
                    errors.append(f"{relative}: invalid Python example: {exc.msg}")
            link_text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
            link_text = re.sub(r"`+[^`\n]*`+", "", link_text)
            for match in re.finditer(r"\[[^\]\n]*\]\(([^)\n]+)\)", link_text):
                destination = match.group(1).strip().strip("<>")
                if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", destination) or destination.startswith("#"):
                    continue
                destination = unquote(destination.split("#", 1)[0])
                target = (path.parent / destination).resolve()
                if not target.is_relative_to(ROOT.resolve()):
                    errors.append(f"{relative}: link leaves copied skill: {destination}")
                elif not target.exists():
                    errors.append(f"{relative}: missing link: {destination}")
        else:
            try:
                json.loads(text)
            except (ValueError, RecursionError) as exc:
                errors.append(f"{relative}: invalid JSON: {exc}")
    entry = ROOT / "SKILL.md"
    if not entry.is_file():
        errors.append("missing SKILL.md")
    else:
        text = entry.read_text(encoding="utf-8")
        if not text.startswith("---\nname: galtransl-galgamereverse-skill\ndescription:"):
            errors.append("SKILL.md: missing portable frontmatter")
        if len(text.splitlines()) > 500:
            errors.append("SKILL.md: exceeds 500 lines; move shared guidance into guides and format details into engines")
    index_file = ROOT / "catalog/engines.json"
    if not index_file.exists():
        errors.append("missing generated catalog/engines.json")
    else:
        try:
            index = json.loads(index_file.read_text(encoding="utf-8"))
            engines = index["engines"]
            ids = [engine["id"] for engine in engines]
            pages = {path.stem for path in (ROOT / "engines").glob("*.md")}
            stats["engine_pages"] = len(pages)
            if len(ids) != len(set(ids)) or set(ids) != pages or index["count"] != len(pages):
                errors.append("engine index IDs/pages/count do not match")
            for missing in sorted(REQUIRED_ENGINES - pages):
                errors.append(f"missing baseline engine page: {missing}")
            for engine in engines:
                references = engine["python_references"]
                if not references:
                    errors.append(f"{engine['id']}: no shipped Python reference")
                for reference in references:
                    if not (ROOT / reference).is_file():
                        errors.append(f"{engine['id']}: missing Python reference {reference}")
        except (ValueError, KeyError, TypeError) as exc:
            errors.append(f"invalid engine index: {exc}")
    for required in ("catalog/formats.json", "catalog/source-registries.json", "provenance/sources.json",
                     "provenance/NOTICE.md", "LICENSE"):
        if not (ROOT / required).is_file():
            errors.append(f"missing {required}")
    return errors, stats


def main() -> None:
    errors, stats = check()
    print(json.dumps({"ok": not errors, "stats": stats, "errors": errors}, ensure_ascii=False, indent=2))
    raise SystemExit(bool(errors))


if __name__ == "__main__":
    main()
