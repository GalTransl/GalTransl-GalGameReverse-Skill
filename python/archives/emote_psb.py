"""Bounded, read-only reader for resource-bearing Emote PSB packages.

Files with a ``PSB\\0`` header carry either a Kirikiri SCN object tree or an
Emote image package (``dpak``/``pimg``/``psb``/``psbz``/``psp``) whose object
tree references an embedded payload table. This module reads the second shape:
it validates the header, rebuilds the name map, walks the object tree and
exposes the embedded payloads. It is not a writer and it does not decode images,
compose layers or touch encrypted bodies.

Layout reference: GARbro-Mod, ``ArcFormats/Emote/ArcPSB.cs``,
``PsbReader.Parse``/``ReadHeader``/``ReadNames``/``GetObject``/``GetArray``/
``GetChunk``/``GetChunks``/``GetLayers``/``GetTextures`` (MIT); the full MIT
notice is included in the adjacent ``xp3.py``. Copyright (C) 2014-2017 morkt.
Independent Python transcription of the documented layout only.
"""
from dataclasses import dataclass
import argparse
from pathlib import Path
import json
import struct
import zlib

from python.common.binary import FormatError
from python.common.safety import Limits, validate_names, write_new_tree

MAGIC = b"PSB\0"
HEADER_SIZE = 0x20          # bytes read after the version/flags pair, v2 and v3
SUPPORTED_VERSIONS = (2, 3)
MAX_INPUT_SIZE = 128 << 20
MAX_ARRAY_ENTRIES = 2_000_000
MAX_NODES = 2_000_000
MAX_DEPTH = 100
MAX_CHUNKS = 100_000
MAX_NAME_BYTES = 1024

# Flags bit 0 marks an encrypted header and bit 1 an encrypted body. The key
# schedule is documented but no available sample exercises it, so encrypted
# packages are refused instead of being half-decoded.
ENCRYPTED_FLAGS = 0x3


@dataclass(frozen=True)
class ChunkRef:
    """Reference from the object tree into the embedded payload table."""
    index: int


@dataclass(frozen=True)
class Resource:
    index: int
    name: str
    offset: int
    length: int
    kind: str
    extension: str


@dataclass(frozen=True)
class _Node:
    start: int
    end: int
    tag: int
    value: object


def _payload_kind(head: bytes) -> tuple[str, str]:
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png", ".png"
    if head.startswith(b"TLG"):
        return "tlg", ".tlg"
    if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        return "webp", ".webp"
    if head.startswith(b"BM"):
        return "bmp", ".bmp"
    return "unknown", ".bin"


def header(data: bytes) -> dict:
    """Validate and return the header fields of a PSB resource package.

    Section offsets must sit above the header, the payload section must end the
    file, and the v3 header checksum must match. Unknown versions and encrypted
    headers are refused rather than guessed.
    """
    if not isinstance(data, bytes) or len(data) > MAX_INPUT_SIZE:
        raise ValueError("PSB input type/size budget")
    if len(data) < 8 + HEADER_SIZE or data[:4] != MAGIC:
        raise ValueError("not a PSB package")
    version, flags = struct.unpack_from("<HH", data, 4)
    if version not in SUPPORTED_VERSIONS:
        raise ValueError(f"unsupported PSB version {version}")
    if flags & ENCRYPTED_FLAGS:
        raise ValueError("encrypted PSB is not supported")
    body = data[8:8 + HEADER_SIZE]
    names, strings, strings_data, chunk_offsets, chunk_lengths, chunk_data, root = \
        struct.unpack_from("<7I", body, 4)
    if not (0x28 <= root < chunk_data
            and 0x28 <= names < chunk_data and 0x28 <= strings < chunk_data
            and 0x28 <= strings_data < chunk_data
            and 0x28 <= chunk_offsets < chunk_data
            and 0x28 <= chunk_lengths < chunk_data
            and chunk_data <= len(data)):
        raise ValueError("PSB section bounds")
    if version == 3:
        if len(data) < 44:
            raise ValueError("PSB v3 header truncated")
        checksum, = struct.unpack_from("<I", data, 40)
        if zlib.adler32(body) & 0xFFFFFFFF != checksum:
            raise ValueError("PSB header checksum mismatch")
    return {"version": version, "flags": flags, "names": names, "strings": strings,
            "strings_data": strings_data, "chunk_offsets": chunk_offsets,
            "chunk_lengths": chunk_lengths, "chunk_data": chunk_data, "root": root}


class Psb:
    """Read a resource-bearing PSB package without decoding its payloads."""

    def __init__(self, data: bytes):
        self.header = header(data)
        self.data = data
        self.version = self.header["version"]
        self.names_at = self.header["names"]
        self.strings_at = self.header["strings"]
        self.strings_data_at = self.header["strings_data"]
        self.chunk_offsets_at = self.header["chunk_offsets"]
        self.chunk_lengths_at = self.header["chunk_lengths"]
        self.chunk_data_at = self.header["chunk_data"]
        self.root_at = self.header["root"]
        self._names = None
        self._strings = None
        self._offsets = None
        self._lengths = None
        self._root = None
        self._nodes = 0
        self._cache = {}
        self._active = set()

    # -- primitives ---------------------------------------------------------
    def take(self, at: int, count: int) -> bytes:
        if at < 0 or count < 0 or at + count > len(self.data):
            raise ValueError("PSB bounds")
        return self.data[at:at + count]

    def array(self, at: int) -> tuple[list[int], int]:
        """Read a packed integer array; returns (values, offset after it)."""
        count_type = self.take(at, 1)[0] - 12
        if not 1 <= count_type <= 4:
            raise ValueError("PSB array count type")
        count = int.from_bytes(self.take(at + 1, count_type), "little")
        width = self.take(at + 1 + count_type, 1)[0] - 12
        if not 1 <= width <= 4 or count > MAX_ARRAY_ENTRIES:
            raise ValueError("PSB array budget/type")
        start = at + 2 + count_type
        raw = self.take(start, count * width)
        return [int.from_bytes(raw[i:i + width], "little")
                for i in range(0, len(raw), width)], start + len(raw)

    # -- names and strings --------------------------------------------------
    def names(self) -> dict[int, str]:
        """Name-table offset -> property name, rebuilt from the name arrays."""
        if self._names is None:
            self._names = self._read_names()
        return self._names

    def _read_names(self) -> dict[int, str]:
        first, pos = self.array(self.names_at)
        second, _end = self.array(pos)
        table: dict[int, str] = {}
        pending = {0: b""}
        visited = 0
        while pending:
            following: dict[int, bytes] = {}
            for node, text in pending.items():
                if node >= len(first):
                    raise ValueError("PSB name node range")
                start = first[node]
                for char in range(min(256, len(second) - start)):
                    if second[start + char] != node:
                        continue
                    if char == 0:
                        if start >= len(first):
                            raise ValueError("PSB name terminal")
                        table[first[start]] = text.decode("utf-8")
                    else:
                        if len(text) >= MAX_NAME_BYTES:
                            raise ValueError("PSB name length budget")
                        following[start + char] = text + bytes([char])
            visited += len(pending)
            if visited > MAX_NODES:
                raise ValueError("PSB name node budget")
            pending = following
        return table

    def strings(self) -> list[str]:
        """String-pool values in table order."""
        if self._strings is None:
            offsets, end = self.array(self.strings_at)
            if end != self.strings_data_at:
                raise ValueError("PSB string index padding")
            pool = []
            for off in offsets:
                at = self.strings_data_at + off
                stop = self.data.find(b"\0", at, self.chunk_offsets_at)
                if not self.strings_data_at <= at <= stop < self.chunk_offsets_at:
                    raise ValueError("PSB string range")
                pool.append(self.data[at:stop].decode("utf-8"))
            self._strings = pool
        return self._strings

    # -- object tree --------------------------------------------------------
    def node(self, at: int, depth: int = 0) -> _Node:
        """Walk one object-tree node; cycle, depth and node count are bounded."""
        if at in self._active:
            raise ValueError("PSB node cycle")
        if at in self._cache:
            return self._cache[at]
        self._active.add(at)
        self._nodes += 1
        if depth > MAX_DEPTH or self._nodes > MAX_NODES:
            raise ValueError("PSB node budget")
        tag = self.take(at, 1)[0]
        stop = at + 1
        if tag in (1, 2, 3):
            value = {1: None, 2: True, 3: False}[tag]
        elif 4 <= tag <= 12:
            width = tag - 4
            stop += width
            value = int.from_bytes(self.take(at + 1, width), "little", signed=True) if width else 0
        elif 21 <= tag <= 24:
            width = tag - 20
            stop += width
            index = int.from_bytes(self.take(at + 1, width), "little")
            if index >= len(self.strings()):
                raise ValueError("PSB string id")
            value = self.strings()[index]
        elif 25 <= tag <= 28:
            width = tag - 24
            stop += width
            index = int.from_bytes(self.take(at + 1, width), "little")
            if index >= len(self.chunk_table_offsets()):
                raise ValueError("PSB chunk id")
            value = ChunkRef(index)
        elif 29 <= tag <= 31:
            if tag == 31:
                stop += 8
                value = struct.unpack_from("<d", self.data, at + 1)[0]
            elif tag == 30:
                stop += 4
                value = struct.unpack_from("<f", self.data, at + 1)[0]
            else:
                value = 0.0
        elif tag in (32, 33):
            keys = None
            if tag == 33:
                keys, stop = self.array(stop)
                if len(set(keys)) != len(keys):
                    raise ValueError("PSB dictionary keys")
            offsets, base = self.array(stop)
            if keys is not None and len(keys) != len(offsets):
                raise ValueError("PSB dictionary shape")
            children = [self.node(base + off, depth + 1) for off in offsets]
            # Shared nodes are legal, so identical spans collapse; the remaining
            # spans must tile the node body exactly.
            stop = base
            for start, finish in sorted({(child.start, child.end) for child in children}):
                if start != stop:
                    raise ValueError("PSB child gap/partial overlap")
                stop = finish
            if keys is None:
                value = [child.value for child in children]
            else:
                names = [(self.names().get(key), child.value) for key, child in zip(keys, children)]
                if any(name is None for name, _value in names):
                    raise ValueError("PSB dictionary key has no name")
                value = names
        else:
            raise ValueError(f"PSB unknown node tag {tag}")
        if stop > len(self.data):
            raise ValueError("PSB node exceeds input")
        node = _Node(at, stop, tag, value)
        self._cache[at] = node
        self._active.discard(at)
        return node

    def object(self) -> dict:
        """Root object reached through the object-tree offset."""
        if self._root is None:
            node = self.node(self.root_at)
            if node.tag != 33:
                raise ValueError("PSB root is not a dictionary")
            self._root = dict(node.value)
        return self._root

    # -- embedded payloads --------------------------------------------------
    def chunk_table_offsets(self) -> list[int]:
        if self._offsets is None:
            self._offsets = self.array(self.chunk_offsets_at)[0]
        return self._offsets

    def chunk_table(self) -> list[tuple[int, int]]:
        """(relative offset, length) per entry of the embedded payload table."""
        offsets = self.chunk_table_offsets()
        if self._lengths is None:
            self._lengths = self.array(self.chunk_lengths_at)[0]
        if len(offsets) != len(self._lengths):
            raise ValueError("PSB chunk table shape")
        table = []
        for offset, length in zip(offsets, self._lengths):
            if offset < 0 or length < 0 or self.chunk_data_at + offset + length > len(self.data):
                raise ValueError("PSB chunk range")
            table.append((offset, length))
        return table

    def references(self) -> dict[str, int]:
        """Container payload names as name -> table index.

        ``GetChunks`` names payload-valued root keys, ``GetLayers`` names the
        payload of ``<layer_id>.tlg``, and ``GetTextures`` names ``source``
        ``texture``/``icon`` payloads. All three documented shapes are read, so a
        package named through any of them keeps its labels; the first name seen
        for an index wins.
        """
        root = self.object()
        found: dict[str, int] = {}
        for key, value in root.items():
            if isinstance(value, ChunkRef):
                found.setdefault(key, value.index)
            elif isinstance(value, dict):
                pixel = value.get("pixel")
                if isinstance(pixel, ChunkRef):
                    found.setdefault(key, pixel.index)
        source = root.get("source")
        if isinstance(source, dict):
            for key, item in source.items():
                if not isinstance(item, dict):
                    continue
                texture = item.get("texture")
                if isinstance(texture, dict) and isinstance(texture.get("pixel"), ChunkRef):
                    found.setdefault(str(key), texture["pixel"].index)
                icons = item.get("icon")
                if isinstance(icons, dict):
                    for icon_key, layer in icons.items():
                        if isinstance(layer, dict) and isinstance(layer.get("pixel"), ChunkRef):
                            found.setdefault(f"{key}#{icon_key}", layer["pixel"].index)
        return found

    def resources(self) -> list[Resource]:
        """Embedded payloads with their container name where one is known."""
        by_index: dict[int, str] = {}
        for name, index in self.references().items():
            by_index.setdefault(index, name)
        result = []
        for index, (relative, length) in enumerate(self.chunk_table()):
            at = self.chunk_data_at + relative
            kind, extension = _payload_kind(self.data[at:at + 16])
            result.append(Resource(index=index, name=by_index.get(index, ""),
                                   offset=at, length=length, kind=kind, extension=extension))
        return result

    def extract(self) -> list[tuple[str, bytes]]:
        """Payloads as (container name or positional fallback, bytes)."""
        return [(resource.name or f"resource_{resource.index:03d}{resource.extension}",
                 self.data[resource.offset:resource.offset + resource.length])
                for resource in self.resources()]

    def summary(self) -> dict:
        resources = self.resources()
        kinds: dict[str, int] = {}
        for resource in resources:
            kinds[resource.kind] = kinds.get(resource.kind, 0) + 1
        return {"version": self.version, "payloads": len(resources),
                "named_payloads": sum(1 for resource in resources if resource.name),
                "payload_kinds": kinds, "name_count": len(self.names()),
                "root_keys": len(self.object())}


def output_names(resources: list[Resource]) -> list[str]:
    """Safe unique output basenames; the container name is used when usable."""
    names, used = [], set()
    for resource in resources:
        name = ""
        if resource.name:
            try:
                name = validate_names([resource.name])[0]
            except FormatError:
                name = ""
        if not name or name.casefold() in used:
            name = f"resource_{resource.index:03d}{resource.extension}"
            while name.casefold() in used:
                name = "_" + name
        used.add(name.casefold())
        names.append(name)
    return names


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("list", "extract"))
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path, nargs="?")
    args = parser.parse_args()
    if args.input.stat().st_size > MAX_INPUT_SIZE:
        raise ValueError("PSB input size budget")
    package = Psb(args.input.read_bytes())
    if args.command == "list":
        print(json.dumps({"file": args.input.name, **package.summary(),
                          "payloads": [{"index": r.index, "name": r.name, "kind": r.kind,
                                        "length": r.length} for r in package.resources()]},
                         ensure_ascii=False, indent=2))
        return
    if args.output is None:
        raise ValueError("extract requires an output directory")
    resources = package.resources()
    payloads = [package.data[r.offset:r.offset + r.length] for r in resources]
    write_new_tree(args.output, list(zip(output_names(resources), payloads)),
                   Limits(max_entries=MAX_CHUNKS, max_file_bytes=MAX_INPUT_SIZE,
                          max_total_bytes=2 * MAX_INPUT_SIZE))
    print(json.dumps({"file": args.input.name, "output": str(args.output),
                      "written": output_names(resources)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
