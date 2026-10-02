#!/usr/bin/env python3
"""Optional development-only catalog builder (Python standard library + Git).

Pass all four source repository paths explicitly. Reads pinned Git blobs, never
imports or executes source tools; installed skills only need the generated JSON.
No discovery of local installations, network access, or current-working-tree reads.
This is a bounded C# metadata lexer, not a C# interpreter: unknown expressions stay
raw. Source claims are not tested extraction/repacking or game compatibility.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from urllib.parse import quote

PINS = {
    "garbro": "bc26d991ef5cdc0e1ecb32122ee9a48c3375750c",
    "msg-tool": "f72716cee88554d40c1cdface2812493b14ca653",
    "sextractor": "8d8d976fd04ae54e7c677705af937273d04a376a",
    "vntextpatch": "d9c0fab7b72fdcf87d674ef12a84d3829c9188be",
}
EXPECTED = {"ArcFormats": (956, 531, 7), "Legacy": (291, 143, 1),
            "Experimental": (20, 7, 0), "GameRes": (29, 0, 2)}
KINDS = {"ArchiveFormat": "archive", "ScriptFormat": "script"}


class CatalogError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise CatalogError(message)


def stable_id(*parts):
    return ":".join(quote(str(p), safe="._-") for p in parts)


def safe_path(path):
    p = PurePosixPath(path)
    require(not p.is_absolute() and ".." not in p.parts and
            not re.match(r"^[A-Za-z]:", path) and "\\" not in path,
            f"Non-relative source path: {path!r}")
    return path


class Repository:
    def __init__(self, name, root):
        self.name, self.root, self.commit = name, Path(root), PINS[name]
        require(self.root.is_dir(), f"{name}: source repository directory does not exist")
        head = self.git("rev-parse", "HEAD").decode().strip()
        require(head == self.commit, f"{name}: expected HEAD {self.commit}, got {head}")
        self.blobs = {}
        for row in self.git("ls-tree", "-r", "-z", self.commit).split(b"\0"):
            if not row:
                continue
            meta, path = row.split(b"\t", 1)
            _, kind, oid = meta.decode().split()
            if kind == "blob":
                self.blobs[safe_path(path.decode("utf-8"))] = oid
        self.cache = {}
        self.inputs = set()

    def git(self, *args, data=None):
        proc = subprocess.run(["git", "-C", str(self.root), *args], input=data,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        require(proc.returncode == 0,
                f"{self.name}: Git {' '.join(args)} failed: {proc.stderr.decode('utf-8', 'replace').strip()}")
        return proc.stdout

    def preload(self, paths):
        paths = sorted(set(paths) - self.cache.keys())
        for path in paths:
            require(path in self.blobs, f"{self.name}@{self.commit}: missing tracked source {path}")
        if not paths:
            return
        output = self.git("cat-file", "--batch", data=("\n".join(self.blobs[p] for p in paths) + "\n").encode())
        offset = 0
        for path in paths:
            end = output.index(b"\n", offset)
            oid, kind, size = output[offset:end].split()
            require(kind == b"blob" and oid.decode() == self.blobs[path], f"{self.name}: invalid blob response for {path}")
            offset = end + 1
            self.cache[path] = output[offset:offset + int(size)].decode("utf-8-sig")
            offset += int(size) + 1

    def text(self, path):
        self.preload([path])
        self.inputs.add(path)
        return self.cache[path]

    def evidence(self, path, line=1, symbol=None):
        result = {"repository": self.name, "commit": self.commit, "path": safe_path(path), "line": line}
        if symbol:
            result["symbol"] = symbol
        return result


# Keep offsets/newlines while removing comments. Strings remain atomic tokens so
# commented Export annotations and braces inside text cannot become declarations.
TOKEN_RE = re.compile(r'(?P<comment>//[^\r\n]*|/\*[\s\S]*?\*/)|'
                      r'(?P<string>@"(?:[^"]|"")*"|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')|'
                      r'(?P<word>[A-Za-z_][\w]*|0[xX][0-9A-Fa-f]+[uUlL]*|\d+[uUlL]*)|'
                      r'(?P<punct>=>|::|&&|\|\||==|!=|<<|>>|\S)')


@dataclass
class Token:
    value: str
    pos: int


def lex(text):
    return [Token(m.group(), m.start()) for m in TOKEN_RE.finditer(text) if m.lastgroup != "comment"]


def pairs(tokens):
    stack, result = [], {}
    for i, token in enumerate(tokens):
        if token.value in ("{", "(", "["):
            stack.append((token.value, i))
        elif token.value in ("}", ")", "]"):
            require(bool(stack), f"Unbalanced source delimiters near offset {token.pos}")
            opening, start = stack.pop()
            require({"{": "}", "(": ")", "[": "]"}[opening] == token.value,
                    f"Mismatched source delimiters near offset {token.pos}")
            result[start], result[i] = i, start
    require(not stack, "Unclosed source delimiters")
    return result


def preprocess(text, defines=frozenset()):
    """Only conditional directives, never evaluate arbitrary source expressions."""
    defines = set(defines)
    active, stack, output = True, [], []

    def condition(expr):
        expr = expr.split("//", 1)[0].strip()
        parts = re.findall(r"&&|\|\||==|!=|!|\(|\)|[A-Za-z_]\w*", expr)
        require("".join(parts) == re.sub(r"\s", "", expr), f"Unsupported #if expression: {expr}")
        # Recursive descent for C# boolean preprocessor expressions.
        index = 0
        def primary():
            nonlocal index
            require(index < len(parts), f"Incomplete #if: {expr}")
            p = parts[index]
            index += 1
            if p == "!":
                return not primary()
            if p == "(":
                value = logical_or()
                require(index < len(parts) and parts[index] == ")", f"Unbalanced #if: {expr}")
                index += 1
                return value
            require(re.fullmatch(r"[A-Za-z_]\w*", p), f"Unsupported #if token: {p}")
            return p == "true" or (p != "false" and p in defines)
        def equality():
            nonlocal index
            value = primary()
            while index < len(parts) and parts[index] in ("==", "!="):
                op = parts[index]
                index += 1
                rhs = primary()
                value = (value == rhs) if op == "==" else (value != rhs)
            return value
        def logical_and():
            nonlocal index
            value = equality()
            while index < len(parts) and parts[index] == "&&":
                index += 1
                rhs = equality()
                value = value and rhs
            return value
        def logical_or():
            nonlocal index
            value = logical_and()
            while index < len(parts) and parts[index] == "||":
                index += 1
                rhs = logical_and()
                value = value or rhs
            return value
        value = logical_or()
        require(index == len(parts), f"Unsupported #if: {expr}")
        return value

    # Directives inside comments/string literals are not directives.
    commentless = list(text)
    for m in TOKEN_RE.finditer(text):
        if m.lastgroup in ("comment", "string"):
            commentless[m.start():m.end()] = ["\n" if c == "\n" else " " for c in m.group()]
    directive_lines = "".join(commentless).splitlines(keepends=True)
    for original, code in zip(text.splitlines(keepends=True), directive_lines):
        match = re.match(r"\s*#(\w+)\s*(.*)", code)
        if match:
            directive, expr = match.groups()
            if directive == "if":
                selected = condition(expr)
                stack.append([active, selected])
                active = active and selected
            elif directive == "elif":
                require(bool(stack), "#elif without #if")
                parent, taken = stack[-1]
                selected = condition(expr)
                active = parent and not taken and selected
                stack[-1][1] = taken or selected
            elif directive == "else":
                require(bool(stack), "#else without #if")
                parent, taken = stack[-1]
                active = parent and not taken
                stack[-1][1] = True
            elif directive == "endif":
                require(bool(stack), "#endif without #if")
                active = stack.pop()[0]
            elif directive == "define" and active:
                defines.add(expr.strip())
            elif directive == "undef" and active:
                defines.discard(expr.strip())
            elif directive == "error" and active:
                raise CatalogError(f"Active #error: {expr}")
            output.append("".join("\n" if c == "\n" else " " for c in original))
        else:
            output.append(original if active else "".join("\n" if c == "\n" else " " for c in original))
    require(not stack, "Unclosed #if")
    return "".join(output)


@dataclass
class Member:
    name: str
    form: str
    header: str
    raw: str
    pos: int


@dataclass
class CsClass:
    assembly: str
    path: str
    name: str
    qualified: str
    namespace: str
    bases: list
    exports: list
    pos: int
    text: str
    members: list
    usings: list

    def evidence(self, repo, member=None):
        return repo.evidence(self.path, self.text.count("\n", 0, member.pos if member else self.pos) + 1,
                             self.qualified + ("." + member.name if member else ""))


def parse_cs(text, assembly, path, defines=frozenset()):
    active = preprocess(text, defines)
    ts = lex(active)
    ps = pairs(ts)
    namespaces, declarations = [], []
    usings = re.findall(r"\busing\s+([\w.]+)\s*;", active)
    for i, token in enumerate(ts):
        if token.value not in ("namespace", "class", "struct") or i + 1 >= len(ts):
            continue
        if token.value in ("class", "struct") and ts[i + 1].value in (",", "{", "where"):
            continue  # generic constraints
        j = i + 1
        while j < len(ts) and ts[j].value not in ("{", ";", "}"):
            j += 1
        if j >= len(ts) or ts[j].value != "{":
            continue
        if token.value == "namespace":
            namespaces.append((j, ps[j], "".join(t.value for t in ts[i + 1:j])))
        else:
            declarations.append((i, j, ps[j]))
    classes = []
    for i, start, end in declarations:
        name = ts[i + 1].value
        namespace = ".".join(n for a, b, n in namespaces if a < i < b)
        enclosing = [ts[a + 1].value for a, b, c in declarations if b < i < c]
        qualified = ".".join([p for p in [namespace, *enclosing, name] if p])
        bases = []
        header = ts[i + 2:start]
        colon = next((j for j, t in enumerate(header) if t.value == ":"), None)
        if colon is not None:
            base_raw = "".join(t.value for t in header[colon + 1:])
            bases = base_raw.split(",")
        # Only attributes immediately belonging to this declaration count.
        k = i - 1
        while k >= 0 and ts[k].value in ("public", "internal", "private", "protected", "abstract", "sealed", "static", "partial", "new"):
            k -= 1
        attributes = []
        while k >= 0 and ts[k].value == "]":
            a = ps[k]
            attributes.append("".join(t.value for t in ts[a:k + 1]))
            k = a - 1
        exports = re.findall(r"(?<![\w])(?:[\w.]+\.)?Export(?:Attribute)?\(typeof\((?:GameRes\.)?(\w+)\)\)", " ".join(attributes))
        members, j, segment = [], start + 1, start + 1
        while j < end:
            t = ts[j].value
            if t == "[":
                j = ps[j] + 1
                continue
            if t == "(":
                j = ps[j] + 1
                continue
            if t in ("{", "=>", ";"):
                header_tokens = ts[segment:j]
                values = [x.value for x in header_tokens]
                member_end = ps[j] if t == "{" else j
                if t == "{" and member_end + 1 < end and ts[member_end + 1].value == "=":
                    member_end += 2
                    while member_end < end and ts[member_end].value != ";":
                        member_end += 1
                if t == "=>":
                    while member_end < end and ts[member_end].value != ";":
                        member_end += 1
                if header_tokens:
                    paren = next((p for p, v in enumerate(values) if v == "("), None)
                    if "=" in values and (paren is None or values.index("=") < paren):
                        member_name = values[values.index("=") - 1]
                        form = "field"
                    elif paren is not None and paren > 0:
                        member_name = values[paren - 1]
                        form = "constructor" if member_name == name else "method"
                    else:
                        member_name = values[-1]
                        form = "property" if t in ("{", "=>") and "=" not in values else "field"
                    if re.fullmatch(r"[A-Za-z_]\w*", member_name):
                        raw_start = ts[j].pos
                        raw_end = ts[member_end].pos + len(ts[member_end].value)
                        members.append(Member(member_name, form,
                                              active[header_tokens[0].pos:raw_start].strip(),
                                              active[raw_start:raw_end], header_tokens[0].pos))
                j = member_end + 1
                if j < end and ts[j].value == ";":
                    j += 1
                segment = j
            else:
                j += 1
        classes.append(CsClass(assembly, path, name, qualified, namespace, bases,
                               exports, ts[i].pos, text, members, usings))
    return classes


UNKNOWN = object()


def literal(expression):
    """Evaluate only complete literals/arrays; never fish strings out of code."""
    ts = lex(expression)
    value = "".join(t.value for t in ts)
    if value in ("true", "false"):
        return value == "true"
    if value == "null":
        return None
    if re.fullmatch(r"(?:0[xX][0-9a-fA-F]+|\d+)[uUlL]*", value):
        value = re.sub(r"[uUlL]+$", "", value)
        return int(value, 16 if value.lower().startswith("0x") else 10)
    if len(ts) == 1 and value.startswith('"'):
        try:
            # C# common string escape set, preserving Unicode source literally.
            def escape(m):
                char = m.group(1)
                common = {"0": "\0", "a": "\a", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v", '"': '"', "'": "'", "\\": "\\"}
                if char[0] in "xuU":
                    return chr(int(char[1:], 16))
                return common[char]
            return re.sub(r"\\(x[0-9a-fA-F]{1,4}|u[0-9a-fA-F]{4}|U[0-9a-fA-F]{8}|.)", escape, value[1:-1])
        except (ValueError, KeyError):
            return UNKNOWN
    if len(ts) == 1 and value.startswith('@"'):
        return value[2:-1].replace('""', '"')
    array = re.fullmatch(r"new(?:string|uint|int|byte)?\[\]\{(.*)\}", value, re.S)
    if array:
        items, current, depth = [], [], 0
        for token in lex(array.group(1)):
            if token.value == "," and depth == 0:
                if current:
                    items.append(literal("".join(current)))
                    current = []
            else:
                current.append(token.value)
                if token.value in ("{", "(", "["):
                    depth += 1
                elif token.value in ("}", ")", "]"):
                    depth -= 1
        if current:
            items.append(literal("".join(current)))
        return UNKNOWN if any(v is UNKNOWN for v in items) else items
    return UNKNOWN


def getter(member):
    ts = lex(member.raw)
    values = [t.value for t in ts]
    if values and values[0] == "=>":
        return member.raw[ts[1].pos:ts[-1].pos].strip()
    if values[:5] == ["{", "get", ";", "}", "="] and values[-1] == ";":
        return member.raw[ts[5].pos:ts[-1].pos].strip()
    # Only a single unconditional getter return is statically evaluated.
    if values[:3] == ["{", "get", "{"] and values[-2:] == ["}", "}"]:
        if len(values) >= 7 and values[3] == "return" and values[-3] == ";":
            middle = values[4:-3]
            if not any(v in (";", "return", "if", "switch") for v in middle):
                return member.raw[ts[4].pos:ts[-3].pos].strip()
    if values[:3] == ["{", "get", "=>"] and values[-2:] == [";", "}"]:
        return member.raw[ts[3].pos:ts[-2].pos].strip()
    return None


class Metadata:
    def __init__(self, repo, classes):
        self.repo, self.classes = repo, classes
        self.by_name = {}
        for cls in classes:
            self.by_name.setdefault(cls.qualified, []).append(cls)

    def base(self, cls):
        if not cls.bases:
            return None
        base = cls.bases[0]
        candidates = [base, cls.namespace + "." + base, *(u + "." + base for u in cls.usings)]
        namespace = cls.namespace
        while "." in namespace:
            namespace = namespace.rsplit(".", 1)[0]
            candidates.append(namespace + "." + base)
        for name in dict.fromkeys(candidates):
            found = self.by_name.get(name, [])
            same = [c for c in found if c.assembly == cls.assembly]
            if len(same) == 1:
                return same[0]
            if len(found) == 1:
                return found[0]
        return None

    def chain(self, cls):
        seen, chain = set(), []
        while cls is not None:
            key = (cls.assembly, cls.qualified)
            require(key not in seen, f"Cyclic inheritance: {key}")
            seen.add(key)
            chain.append(cls)
            cls = self.base(cls)
        return chain

    def evaluate(self, expression, owner, concrete, seen=frozenset()):
        value = literal(expression)
        if value is not UNKNOWN:
            return value, []
        compact = "".join(t.value for t in lex(expression))
        if compact == "Enumerable.Empty<string>()":
            return [], []
        if compact in ("Signature", "this.Signature"):
            for candidate in self.chain(concrete):
                member = next((m for m in candidate.members if m.name == "Signature" and m.form == "property"), None)
                if member:
                    key = (candidate.qualified, "Signature")
                    if key in seen or getter(member) is None:
                        return UNKNOWN, []
                    value, evidence = self.evaluate(getter(member), candidate, concrete, seen | {key})
                    return value, [candidate.evidence(self.repo, member), *evidence]
        array = re.fullmatch(r"new(?:string|uint|int|byte)?\[\]\{(.*)\}", compact, re.S)
        if array:
            chunks, current = [], []
            for token in lex(array[1]):
                if token.value == ",":
                    if current:
                        chunks.append("".join(current))
                        current = []
                else:
                    current.append(token.value)
            if current:
                chunks.append("".join(current))
            values, evidence = [], []
            for chunk in chunks:
                value, sources = self.evaluate(chunk, owner, concrete, seen)
                if value is UNKNOWN:
                    return UNKNOWN, []
                values.append(value)
                evidence.extend(sources)
            return values, evidence
        if re.fullmatch(r"[\w.]+", compact):
            target, _, name = compact.rpartition(".")
            candidates = self.chain(owner)
            if target:
                names = [target, owner.namespace + "." + target, *(u + "." + target for u in owner.usings)]
                candidates = [c for n in names for c in self.by_name.get(n, [])]
            for candidate in candidates:
                member = next((m for m in candidate.members if m.name == name and m.form == "field" and "const" in m.header.split()), None)
                key = (candidate.qualified, name)
                if member and key not in seen:
                    expression = (member.header.split("=", 1)[1] + member.raw).rstrip(";").strip()
                    value, sources = self.evaluate(expression, candidate, concrete, seen | {key})
                    return value, [candidate.evidence(self.repo, member), *sources]
        return UNKNOWN, []

    def neutral_resource(self, expression, owner):
        match = re.fullmatch(r"(?:Strings\.)?arcStrings\.(\w+)", expression or "")
        if not match:
            return None
        # Verify the generated accessor actually looks up this literal key.
        accessor = next((c for c in self.classes if c.qualified == "GameRes.Formats.Strings.arcStrings"), None)
        if not accessor:
            return None
        member = next((m for m in accessor.members if m.name == match[1] and m.form == "property"), None)
        if not member or not re.fullmatch(r'ResourceManager\.GetString\(\s*"' + re.escape(match[1]) + r'"\s*,\s*resourceCulture\s*\)', getter(member) or ""):
            return None
        path = "ArcFormats/Strings/arcStrings.resx"
        text = self.repo.text(path)
        xml = ET.fromstring(text)
        data = next((e for e in xml.findall("data") if e.get("name") == match[1]), None)
        if data is None or data.findtext("value") is None:
            return None
        location = re.search(r'<data\s+name="' + re.escape(match[1]) + r'"', text)
        return {"value": data.findtext("value"), "scope": "neutral_resource_only_runtime_localization_may_differ",
                "source": self.repo.evidence(path, text.count("\n", 0, location.start()) + 1, match[1]),
                "accessor_source": accessor.evidence(self.repo, member)}

    def property(self, cls, name):
        for owner in self.chain(cls):
            member = next((m for m in owner.members if m.name == name and m.form == "property"), None)
            if member:
                expression = getter(member)
                value, dependencies = self.evaluate(expression, owner, cls) if expression is not None else (UNKNOWN, [])
                result = {"status": "known" if value is not UNKNOWN else "unknown", "value": None if value is UNKNOWN else value,
                          "raw": expression if expression is not None else member.raw,
                          "source": owner.evidence(self.repo, member), "inherited": owner != cls}
                if dependencies:
                    result["constant_sources"] = dependencies
                if value is UNKNOWN:
                    result["reason"] = "Getter is not a supported constant expression; not executed."
                    resource = self.neutral_resource(expression, owner)
                    if resource:
                        result["neutral_resource_hint"] = resource
                        result["reason"] = "Runtime localized string is unknown; neutral resource text is available as a separate hint."
                return result
        return {"status": "unknown", "value": None, "raw": None,
                "reason": "No resolvable property declaration in the compiled inheritance chain."}

    def array(self, cls, name, tag, signature):
        # Assignments in constructors override inherited IResource defaults.
        for owner in self.chain(cls):
            assignments = []
            for constructor in [m for m in owner.members if m.form == "constructor" and "static" not in m.header.split()]:
                ts = lex(constructor.raw)
                for i, t in enumerate(ts[:-1]):
                    if t.value == name and ts[i + 1].value == "=":
                        end = i + 2
                        while end < len(ts) and ts[end].value != ";":
                            end += 1
                        require(end < len(ts), f"Unterminated {name} assignment: {owner.path}")
                        expression = constructor.raw[ts[i + 2].pos:ts[end].pos].strip()
                        assignments.append((constructor, expression, i, ts))
            if assignments:
                constructor, expression, index, ts = assignments[-1]
                value, dependencies = self.evaluate(expression, owner, cls)
                raw = expression
                # Conditional/overloaded initialization is deliberately unknown.
                control = any(t.value in ("if", "switch", "for", "foreach", "while", "?", "try") for t in ts)
                constructors = [m for m in owner.members if m.form == "constructor" and "static" not in m.header.split()]
                if len(assignments) != 1 or len(constructors) != 1 or control:
                    value = UNKNOWN
                    raw = "\n".join(c.raw for c in constructors)
                rule = "constructor_assignment"
                if owner.qualified == "GameRes.IResource" and name == "Extensions" and expression == "new string[] { GetDefaultExtension() }":
                    if tag["status"] == "known" and isinstance(tag["value"], str) and tag["value"].isascii():
                        value = [tag["value"].lower().split("/", 1)[0]]
                        rule = "IResource.GetDefaultExtension: Tag.ToLowerInvariant().Split('/')[0]"
                if owner.qualified == "GameRes.IResource" and name == "Signatures" and expression == "new uint[] { this.Signature }":
                    if signature["status"] == "known":
                        value, rule = [signature["value"]], "IResource constructor uses virtual Signature"
                result = {"status": "known" if value is not UNKNOWN else "unknown", "value": None if value is UNKNOWN else value,
                          "raw": raw, "source": owner.evidence(self.repo, constructor), "inherited": owner != cls,
                          **({"constant_sources": dependencies} if dependencies else {}),
                          "derivation": rule if value is not UNKNOWN else "Unsupported or conditional constructor expression; not executed."}
                if value is UNKNOWN and re.fullmatch(r"\w+", expression):
                    field = next((m for m in owner.members if m.form == "field" and m.name == expression and "=" in m.header), None)
                    if field:
                        initializer = (field.header.split("=", 1)[1] + field.raw).rstrip(";").strip()
                        initial = literal(initializer)
                        if initial is not UNKNOWN:
                            result["initializer_hint"] = {"value": initial, "raw": initializer,
                                                          "scope": "mutable_field_initial_value_only_not_runtime_value",
                                                          "source": owner.evidence(self.repo, field)}
                return result
            # A real getter takes priority over base constructor defaults.
            member = next((m for m in owner.members if m.name == name and m.form == "property" and getter(m) is not None), None)
            if member:
                return self.property(owner, name)
        return {"status": "unknown", "value": None, "raw": None, "reason": "No resolvable initialization."}

    def method(self, cls, name):
        for owner in self.chain(cls):
            method = next((m for m in owner.members if m.name == name and m.form == "method"), None)
            if method:
                code = "".join(t.value for t in lex(method.raw))
                stub = bool(re.fullmatch(r"\{thrownew(?:System\.)?(?:NotImplementedException|NotSupportedException)\([^;]*\);\}", code))
                abstract = "abstract" in method.header.split()
                return {"status": "source_claim", "declaration_found": True,
                        "implementation": "throw_only_stub" if stub else "abstract" if abstract else "body_present_not_validated",
                        "source": owner.evidence(self.repo, method), "inherited": owner != cls,
                        **({"raw": method.raw.strip()} if stub else {})}
        return {"status": "unknown", "declaration_found": False}


def build_garbro(repo):
    projects, all_classes, release_exports = [], [], set()
    project_paths = [f"{p}/{p}.csproj" for p in EXPECTED]
    repo.preload(project_paths)
    for project_path in project_paths:
        xml = ET.fromstring(repo.text(project_path))
        local = lambda e: e.tag.rsplit("}", 1)[-1]
        assembly = next(e.text for e in xml.iter() if local(e) == "AssemblyName")
        includes, case_resolutions = [], []
        for e in xml.iter():
            if local(e) != "Compile":
                continue
            require(not e.get("Condition"), f"Conditional Compile not supported: {project_path}")
            name = e.get("Include")
            require(name and not any(c in name for c in "*$?"), f"Unsupported Compile Include in {project_path}: {name}")
            path = safe_path(str(PurePosixPath(project_path).parent / name.replace("\\", "/")))
            if path not in repo.blobs:
                candidates = [p for p in repo.blobs if p.casefold() == path.casefold()]
                require(len(candidates) == 1, f"{project_path}: missing/ambiguous Compile source: {path}")
                case_resolutions.append({"declared": path, "tracked": candidates[0], "basis": "Windows case-insensitive Compile path"})
                path = candidates[0]
            includes.append(path)
        require(len(includes) == len(set(includes)), f"Duplicate Compile entries: {project_path}")
        # Catalog all pinned Debug registrations, retaining Release availability.
        # Three legacy exports are explicitly guarded by DEBUG.
        release_defines, debug_defines = set(), set()
        for group in xml:
            condition = group.get("Condition", "")
            for e in group:
                if local(e) == "DefineConstants" and e.text:
                    symbols = {s.strip() for s in e.text.split(";") if s.strip()}
                    if not condition or "Release|AnyCPU" in condition:
                        release_defines.update(symbols)
                    if not condition or "Debug|AnyCPU" in condition:
                        debug_defines.update(symbols)
        repo.preload(includes)
        classes, release_classes = [], []
        for path in includes:
            try:
                source = repo.text(path)
                classes.extend(parse_cs(source, assembly, path, debug_defines))
                release_classes.extend(parse_cs(source, assembly, path, release_defines))
            except CatalogError as exc:
                raise CatalogError(f"{path}: {exc}") from exc
        release_exports.update((c.assembly, c.qualified, k) for c in release_classes for k in c.exports)
        counts = Counter(k for cls in classes for k in cls.exports)
        release_counts = Counter(k for cls in release_classes for k in cls.exports)
        debug_keys = {(c.assembly, c.qualified, k) for c in classes for k in c.exports}
        require(all((c.assembly, c.qualified, k) in debug_keys for c in release_classes for k in c.exports),
                f"{project_path}: Release-only exports need explicit union handling")
        project = PurePosixPath(project_path).parent.name
        actual = (len(includes), counts["ArchiveFormat"], counts["ScriptFormat"])
        require(actual == EXPECTED[project], f"{project}: compiled/archive/script counts {actual}, expected {EXPECTED[project]}")
        projects.append({"project": project, "assembly": assembly, "source": repo.evidence(project_path),
                         "compiled_cs_count": len(includes), "compiled_sources": sorted(includes), "compile_path_case_resolutions": case_resolutions,
                         "effective_export_counts": dict(sorted(counts.items())), "debug_defines": sorted(debug_defines),
                         "release_export_counts": dict(sorted(release_counts.items())), "release_defines": sorted(release_defines)})
        all_classes.extend(classes)
    other_projects = []
    for project_path in sorted(p for p in repo.blobs if p.endswith(".csproj") and p not in project_paths):
        xml = ET.fromstring(repo.text(project_path))
        paths = [safe_path(str(PurePosixPath(project_path).parent / e.get("Include").replace("\\", "/")))
                 for e in xml.iter() if e.tag.rsplit("}", 1)[-1] == "Compile"]
        repo.preload(paths)
        for path in paths:
            values = [t.value for t in lex(repo.text(path))]
            # Conservative audit even includes conditional-but-uncommented
            # attributes; an unexpected format export requires explicit support.
            for i, value in enumerate(values):
                if value == "Export" and values[i + 1:i + 4] == ["(", "typeof", "("]:
                    require(values[i + 4] not in KINDS, f"Uncatalogued format export in {path}")
        other_projects.append({"source": repo.evidence(project_path), "compiled_cs_count": len(paths),
                               "compiled_sources": sorted(paths), "archive_or_script_exports": 0,
                               "scope": "non-format project Compile inventory audit"})
    metadata = Metadata(repo, all_classes)
    formats = []
    for cls in all_classes:
        for export in cls.exports:
            if export not in KINDS:
                continue
            tag = metadata.property(cls, "Tag")
            require(tag["status"] == "known" and isinstance(tag["value"], str), f"Unresolved stable-ID Tag: {cls.qualified}")
            description = metadata.property(cls, "Description")
            signature = metadata.property(cls, "Signature")
            extensions = metadata.array(cls, "Extensions", tag, signature)
            signatures = metadata.array(cls, "Signatures", tag, signature)
            can_write = metadata.property(cls, "CanWrite")
            kind = KINDS[export]
            methods = ["TryOpen", "OpenEntry", "Create"] if kind == "archive" else ["IsScript", "Read", "Write", "ConvertFrom", "ConvertBack"]
            evidence_text = description["value"] if description["status"] == "known" else description.get("neutral_resource_hint", {}).get("value", "")
            text_evidence = bool(re.search(r"\b(?:script|scenario|text)\b", evidence_text or "", re.I))
            parts = PurePosixPath(cls.path).parts
            magic_values = signatures["value"] if signatures["status"] == "known" else []
            magic_values = magic_values if isinstance(magic_values, list) else []
            formats.append({
                "id": stable_id("garbro", cls.assembly, cls.qualified, kind, tag["value"]),
                "kind": kind, "assembly": cls.assembly, "qualified_class": cls.qualified,
                "source": cls.evidence(repo), "export": export,
                "registration_configurations": ["Debug", "Release"] if (cls.assembly, cls.qualified, export) in release_exports else ["Debug"],
                "inheritance": [{"assembly": c.assembly, "symbol": c.qualified, "path": c.path} for c in metadata.chain(cls)[1:]],
                "tag": tag, "description": description, "extensions": extensions,
                "magic": {"strength": "weak_hint", "structure_validation_required": True,
                          "signature": signature, "signatures": signatures,
                          "nonzero_uint32_le_hex": [int(v).to_bytes(4, "little").hex() for v in magic_values if isinstance(v, int) and 0 < v <= 0xffffffff],
                          "zero_means": "variable_or_no_fixed_signature_not_four_zero_bytes"},
                "capabilities": {"status": "source_claim", "can_write": can_write,
                                 "methods": {m: metadata.method(cls, m) for m in methods},
                                 "roundtrip_verified": False, "all_versions_writable": "unknown"},
                "family_hint": {"value": parts[1] if len(parts) > 2 else None,
                                "basis": "source_directory_only", "engine_identity_confirmed": False},
                "text_relevance": {"status": "source_indicated" if text_evidence else "uncertain",
                                   "basis": "Description contains text/script/scenario" if text_evidence else "Registration kind/directory alone does not establish translatable text",
                                   "source": description.get("source", cls.evidence(repo))},
            })
    formats.sort(key=lambda f: f["id"])
    require(len({f["id"] for f in formats}) == len(formats), "Duplicate GARbro stable IDs")
    unknown = Counter()
    for f in formats:
        fields = {k: f[k] for k in ("tag", "description", "extensions")}
        fields.update({"signature": f["magic"]["signature"], "signatures": f["magic"]["signatures"], "can_write": f["capabilities"]["can_write"]})
        unknown.update(k for k, v in fields.items() if v["status"] == "unknown")
    return {"schema_version": 1, "catalog_kind": "static_source_format_registrations",
            "source_commit": PINS["garbro"],
            "policy": {"runtime_dependencies": [], "registration_is_engine_support": False,
                       "extensions_and_magic": "Weak hints only; validate structure before selecting a parser.",
                       "writer_claims": "CanWrite/Create/Write declarations are source claims, not all-version or tested roundtrip support.",
                       "unknown_fields": "Unexecuted expressions retain raw source; null with status unknown is not a negative claim.",
                       "images_audio": "Excluded from format entries and engine counts; only effective export summary counts are retained."},
            "counts": {"archive": sum(f["kind"] == "archive" for f in formats), "script": sum(f["kind"] == "script" for f in formats),
                       "total": len(formats), "unknown_fields": dict(sorted(unknown.items()))},
            "projects": projects, "other_project_audit": other_projects, "formats": formats}


def registry_entry(repo, category, name, path, line, **extra):
    return {"id": stable_id(repo.name, category, name), "name": name,
            "source": repo.evidence(path, line, name), "status": "source_only", **extra}


def build_sextractor(repo):
    path = "src/engine.ini"
    text = repo.text(path)
    matches = list(re.finditer(r"^\[(Engine_[^\]\r\n]+)\]\s*$", text, re.M))
    engines = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[match.end():end]
        settings = {}
        # Registration settings only; sample bodies are not interpreted as INI.
        for line in block.splitlines():
            if line.startswith("sample="):
                break
            value = re.match(r"(\w+)=(.*)$", line)
            if value:
                settings[value[1]] = value[2]
        engines.append(registry_entry(repo, "engine_ini", match[1], path, text.count("\n", 0, match.start()) + 1,
                                      active=True, settings_raw=settings,
                                      module_source=("src/extract_" + match[1].removeprefix("Engine_") + ".py") if "src/extract_" + match[1].removeprefix("Engine_") + ".py" in repo.blobs else None,
                                      module_basis="section_suffix_and_tracked_filename_only_no_implementation_inspection",
                                      capability="adapter_registration_only_not_validated"))
    require(len(engines) == 33, f"SExtractor engine.ini: expected 33 active sections, got {len(engines)}")
    path = "src/reg.yaml"
    text = repo.text(path)
    # This pinned file is a top-level scalar-key mapping of sample block strings.
    # Deliberately do not claim to implement general YAML.
    presets = [registry_entry(repo, "regex_preset", m[1], path, text.count("\n", 0, m.start()) + 1,
                              active=True, capability="regex_preset_not_engine")
               for m in re.finditer(r"^([^\s#][^:\r\n]*):[ \t]*$", text, re.M)]
    require(len(presets) == 31, f"SExtractor reg.yaml: expected 31 top-level presets, got {len(presets)}")
    # Tree metadata only: no tool implementation traversal/reads.
    tools = []
    for row in repo.git("ls-tree", "-z", "-d", repo.commit, "tools/").split(b"\0"):
        if not row:
            continue
        meta, path_bytes = row.split(b"\t", 1)
        path = path_bytes.decode("utf-8")
        _, kind, oid = meta.decode().split()
        require(kind == "tree", f"Unexpected tools inventory entry: {path}")
        tools.append({"id": stable_id(repo.name, "tool_directory", path), "name": PurePosixPath(path).name,
                      "source": {"repository": repo.name, "commit": repo.commit, "path": safe_path(path), "git_tree": oid},
                      "status": "source_only_inventory", "capabilities": "unknown_not_inspected",
                      "is_engine": "unconfirmed", "contents_read": False})
    return {"engine_ini": engines, "regex_presets": presets, "tool_directories": sorted(tools, key=lambda t: t["name"])}


def build_msg(repo):
    path = "src/scripts/mod.rs"
    text = repo.text(path)
    builders = []
    pattern = r'#\[cfg\(feature\s*=\s*"([^"]+)"\)\]\s*Box::new\(([\w:]+)\(\)\)'
    for m in re.finditer(pattern, text):
        builders.append(registry_entry(repo, "builder", m[2], path, text.count("\n", 0, m.start(2)) + 1,
                                       feature_gate=m[1], runtime_enabled="build_dependent",
                                       family_hint=m[2].split("::", 1)[0],
                                       support_claim="registered_builder_only"))
    require(len(builders) == text.count("Box::new("), "msg-tool: unparsed builder registration")
    path = "src/types.rs"
    text = repo.text(path)
    match = re.search(r"pub enum ScriptType\s*\{([\s\S]*?)^\}", text, re.M)
    require(match is not None, "msg-tool: missing ScriptType enum")
    body = match[1]
    variants, feature, aliases, docs = [], None, [], []
    offset = match.start(1)
    for line in body.splitlines(keepends=True):
        feature_match = re.search(r'#\[cfg\(feature\s*=\s*"([^"]+)"\)\]', line)
        if feature_match:
            feature = feature_match[1]
        if "#[value(" in line:
            aliases.extend(re.findall(r'"([^"]+)"', line))
        if "///" in line:
            docs.append(line.split("///", 1)[1].strip())
        variant = re.fullmatch(r"\s*([A-Za-z_]\w*),\s*", line)
        if variant:
            require(feature is not None, f"msg-tool: missing feature gate for {variant[1]}")
            description = " ".join(docs)
            if feature.endswith("-img"):
                kind = "image"
            elif feature.endswith("-audio"):
                kind = "audio"
            elif re.search(r"\barchive\b", description, re.I):
                kind = "archive"
            elif re.search(r"\bscript\b|scenario|text file", description, re.I):
                kind = "script_or_text"
            else:
                kind = "other_or_uncertain"
            variants.append(registry_entry(repo, "script_type", variant[1], path, text.count("\n", 0, offset) + 1,
                                           feature_gate=feature, aliases=aliases, description_source_claim=description,
                                           kind_hint=kind, classification_basis="feature_gate_and_enum_documentation_not_execution"))
            feature, aliases, docs = None, [], []
        offset += len(line)
    require(len(builders) == len(variants) == 78,
            f"msg-tool: expected 78 builders/types, got {len(builders)}/{len(variants)}")
    return {"builders": builders, "script_types": variants,
            "counts_by_type_hint": dict(sorted(Counter(v["kind_hint"] for v in variants).items())),
            "gaps": ["Builder-to-ScriptType pairing is not inferred by array order; consult implementation if needed.",
                     "Feature gates do not establish features enabled in a user's binary; registrations include image/audio/archive helpers."]}


def build_vn(repo):
    path = "VNTextPatch.Shared/Scripts/FolderScriptCollection.cs"
    text = repo.text(path)
    match = re.search(r"TemporaryScripts\s*=\s*new IScript\[\]\s*\{([\s\S]*?)\};", text)
    require(match is not None, "VNTextPatch: missing TemporaryScripts registry")
    entries = []
    for m in re.finditer(r"(?m)^\s*(//\s*)?new\s+(\w+)\s*\(\)", match[1]):
        name, active = m[2], m[1] is None
        candidates = [p for p in repo.blobs if p.startswith("VNTextPatch.Shared/Scripts/") and p.endswith("/" + name + ".cs")]
        require(len(candidates) == 1, f"VNTextPatch: expected one class file for {name}, got {candidates}")
        source_path = candidates[0]
        implementation = repo.text(source_path)
        namespace = re.search(r"(?m)^namespace\s+([\w.]+)", implementation)
        declaration = re.search(r"(?m)^[ \t]*(?:public|internal)\s+(?:(?:sealed|abstract|partial)\s+)*class\s+" + name + r"\b", implementation)
        require(namespace is not None and declaration is not None, f"VNTextPatch: missing class {name}")
        qualified = namespace[1] + "." + name
        source_evidence = repo.evidence(source_path, implementation.count("\n", 0, declaration.start()) + 1, qualified)
        # Registry metadata only. Do not lex full modern-C# method algorithms
        # (interpolated nested strings, etc.) merely to identify an extension.
        ext = re.search(r"(?m)^[ \t]*public\s+(?:override\s+)?string\s+Extension\s*=>\s*([^;]+);", implementation)
        extension = {"status": "unknown", "value": None, "raw": None, "reason": "No direct literal Extension getter; inheritance not inferred."}
        if ext:
            value = literal(ext[1])
            extension = {"status": "known" if value is not UNKNOWN else "unknown", "value": None if value is UNKNOWN else value,
                         "raw": ext[1], "source": repo.evidence(source_path, implementation.count("\n", 0, ext.start()) + 1, qualified + ".Extension")}
        method = re.search(r"(?m)^[ \t]*public\s+(?:override\s+)?void\s+WritePatched\s*\([^)]*\)\s*\{", implementation)
        writer = {"status": "unknown", "declaration_found": False, "reason": "No direct declaration; inherited writer not inferred."}
        if method:
            stub = re.match(r"\s*throw new (?:System\.)?(?:NotImplementedException|NotSupportedException)\([^;]*\);\s*\}", implementation[method.end():])
            writer = {"status": "source_claim", "declaration_found": True,
                      "implementation": "throw_only_stub" if stub else "body_present_not_validated",
                      "source": repo.evidence(source_path, implementation.count("\n", 0, method.start()) + 1, qualified + ".WritePatched")}
            if stub:
                writer["raw"] = stub[0].strip()
        entry = registry_entry(repo, "folder_script", name, path, text.count("\n", 0, match.start(1) + m.start(2)) + 1,
                               active=active, registration="active" if active else "disabled_commented_registration",
                               implementation_source=source_evidence,
                               extension=extension,
                               write_patched=writer,
                               capability="disabled" if not active else "no_writer" if writer.get("implementation") == "throw_only_stub" else "source_claim_not_roundtrip_verified")
        entries.append(entry)
    require(sum(e["active"] for e in entries) == 31 and len(entries) == 32,
            f"VNTextPatch: expected 31 active + 1 disabled, got {len(entries)}")
    require(any(e["name"] == "KirikiriScnScript" and not e["active"] for e in entries), "VNTextPatch: disabled SCN registration missing")
    require(any(e["name"] == "ShSystemScript" and e["capability"] == "no_writer" for e in entries), "VNTextPatch: ShSystem throw-only writer missing")
    return {"folder_scripts": entries,
            "gaps": ["A class registration is not an engine-family count; JSON/JSONL are interchange handlers.",
                     "Unresolved inherited Extension/WritePatched fields remain unknown; no runtime invocation."]}


def license_evidence(repo):
    path = "LICENSE"
    text = repo.text(path)
    title = "\n".join(text.splitlines()[:3]).strip()
    return {"scope": "repository_root_license_text_only", "source": repo.evidence(path), "title_excerpt": title,
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "not_a_blanket_license_for": ["third_party_dependencies", "vendored_tools", "every_source_file", "game_data"],
            "distribution_review_required": True}


def generate(repos):
    formats = build_garbro(repos["garbro"])
    registries = {"schema_version": 1, "catalog_kind": "source_registration_inventory",
                  "policy": {"runtime_dependencies": [], "engine_families_are_not_registration_counts": True,
                             "purpose": "Reconciliation input for a separate engine-family catalog, not engines.json.",
                             "capability": "source_only unless a more restrictive status is explicit"},
                  "sources": {name: {"commit": repo.commit} for name, repo in repos.items()},
                  "msg_tool": build_msg(repos["msg-tool"]),
                  "vntextpatch": build_vn(repos["vntextpatch"]),
                  "sextractor": build_sextractor(repos["sextractor"])}
    registries["counts"] = {"msg_tool_builders": len(registries["msg_tool"]["builders"]),
                            "msg_tool_script_types": len(registries["msg_tool"]["script_types"]),
                            "vntextpatch_active": sum(e["active"] for e in registries["vntextpatch"]["folder_scripts"]),
                            "vntextpatch_disabled": sum(not e["active"] for e in registries["vntextpatch"]["folder_scripts"]),
                            "sextractor_active_adapters": len(registries["sextractor"]["engine_ini"]),
                            "sextractor_regex_presets": len(registries["sextractor"]["regex_presets"]),
                            "sextractor_tool_directories": len(registries["sextractor"]["tool_directories"])}
    licenses = {name: license_evidence(repo) for name, repo in repos.items()}
    provenance = {"schema_version": 1, "artifacts": ["catalog/formats.json", "catalog/source-registries.json"],
                  "generator": "tools/build_source_catalog.py", "optional_development_tool": True,
                  "runtime_dependencies": [], "generation": "Deterministic pinned Git blob text/XML/lexical parsing; no source tool executed or imported.",
                  "sources": {name: {"commit": repo.commit, "license_evidence": licenses[name],
                                     "input_files": [{"path": path, "git_blob": repo.blobs[path]} for path in sorted(repo.inputs)]}
                              for name, repo in repos.items()},
                  "coverage": {"garbro": formats["counts"], "source_registries": registries["counts"]},
                  "limitations": [
                      "Only explicitly compiled sources of the four GARbro format projects produce registrations; comments/uncompiled sources do not.",
                      "Debug and Release preprocessor registrations are compared. Three Legacy archives are Debug-only; 681 is the combined inventory, not Release availability. No C# code executes.",
                      "Nonconstant getters, resource-manager lookups, complex/conditional constructor expressions remain raw and unknown.",
                      "A directory name is a family hint, not confirmed engine identity.",
                      "Create or CanWrite is a source claim only, not evidence that every game/version can be repacked.",
                      "ScriptFormat includes generic placeholders and converters; it does not establish translatable dialogue or a working writer.",
                      "Magic and extensions are weak hints requiring structural validation; zero signature means variable or absent, not literal zero bytes.",
                      "SExtractor tools are top-level Git directory inventory only. Tool implementations and transitive licenses were not audited.",
                      "Registrations are not merged into the separate 29-family engine catalog; consumers must reconcile aliases and variants explicitly.",
                      "No full engine algorithms, encrypted keys, game data, or implementation source code are bundled."]}
    return {"catalog/formats.json": formats, "catalog/source-registries.json": registries, "provenance/catalog.json": provenance}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--garbro-root", required=True, type=Path)
    parser.add_argument("--msg-tool-root", required=True, type=Path)
    parser.add_argument("--sextractor-root", required=True, type=Path)
    parser.add_argument("--vntextpatch-root", required=True, type=Path)
    parser.add_argument("--output-root", type=Path, default=Path(__file__).resolve().parents[1], help="Skill directory receiving the three JSON files")
    parser.add_argument("--check", action="store_true", help="Check byte-for-byte reproducibility without writing")
    args = parser.parse_args(argv)
    try:
        repos = {name: Repository(name, getattr(args, name.replace("-", "_") + "_root")) for name in PINS}
        artifacts = generate(repos)
        for relative, document in artifacts.items():
            payload = (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            target = args.output_root / relative
            if args.check:
                require(target.is_file() and target.read_bytes() == payload, f"Generated artifact differs: {relative}")
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(payload)
        print(json.dumps({"formats": artifacts["catalog/formats.json"]["counts"],
                          "registries": artifacts["catalog/source-registries.json"]["counts"]}, ensure_ascii=False))
    except (CatalogError, OSError, UnicodeError, ET.ParseError) as exc:
        parser.exit(2, f"catalog generation failed: {exc}\n")


if __name__ == "__main__":
    main()
