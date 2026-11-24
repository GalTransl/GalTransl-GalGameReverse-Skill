# SPDX-License-Identifier: GPL-3.0-only
"""YU-RIS compile list (``yst_list.ybn``, magic YSTL) and JSON naming.

The list maps the compiler's sequence numbers (``yst00012.ybn``) back to the
source paths the scripts were compiled from. Layout verified on real v482 and
v488 lists by exact consumption to the last byte; other versions are rejected
by name instead of being read with a guessed record size.
"""
import re
import struct
import unicodedata

from ..common.safety import logical_path

# Versions whose record layout was confirmed on real lists.
YSTL_VERSIONS = (482, 488)
LIST_NAME = "yst_list.ybn"
_MEMBER = re.compile(r"yst(\d{1,9})\.ybn", re.I)
_TRAILER = 20  # opaque per-entry bytes (build stamp and counters); never interpreted


def read_script_list(data, *, max_entries=10000, max_path=520):
    """YSTL -> tuple of source paths; position equals the compiler sequence number.

    Header ``YSTL / u32 version / u32 count``; each record is ``u32 index /
    u32 path length / CP932 path / 20 opaque bytes``. Indices must count up
    from zero and the records must end exactly at the end of the file.
    """
    if not isinstance(data, bytes) or len(data) > 4 << 20:
        raise ValueError("YSTL exceeds budget")
    if len(data) < 12 or data[:4] != b"YSTL":
        raise ValueError("expected YSTL script list")
    version, count = struct.unpack_from("<II", data, 4)
    if version not in YSTL_VERSIONS:
        raise ValueError(f"YSTL version {version} has no verified layout "
                         f"(verified: {', '.join(map(str, YSTL_VERSIONS))})")
    if not 0 < count <= max_entries:
        raise ValueError("YSTL entry count out of range")
    position, paths = 12, []
    for ordinal in range(count):
        if position + 8 > len(data):
            raise ValueError("truncated YSTL record")
        index, length = struct.unpack_from("<II", data, position)
        if index != ordinal or not 0 < length <= max_path:
            raise ValueError(f"unexpected YSTL record {ordinal} (index {index}, path length {length})")
        end = position + 8 + length
        if end + _TRAILER > len(data):
            raise ValueError("truncated YSTL record")
        path = data[position + 8:end].decode("cp932", "strict")
        if any(ord(char) < 32 for char in path):
            raise ValueError("control character in YSTL path")
        paths.append(path)
        position = end + _TRAILER
    if position != len(data):
        raise ValueError("unexpected data after the last YSTL record")
    return tuple(paths)


def member_number(source):
    """Sequence number of ``…/yst00012.ybn``, else None."""
    match = _MEMBER.fullmatch(source.replace("\\", "/").rsplit("/", 1)[-1])
    return int(match[1]) if match else None


def _internal(source):
    return source.replace("\\", "/").rsplit("/", 1)[-1].rsplit(".", 1)[0]


def _key(name):
    return unicodedata.normalize("NFC", name).casefold()


def _safe_stem(path):
    """Extension-less basename usable as a flat file name, else None."""
    base = path.replace("\\", "/").rsplit("/", 1)[-1]
    stem = base.rsplit(".", 1)[0] if "." in base else base
    try:
        if not stem or logical_path(stem + ".json") != stem + ".json":
            return None
    except ValueError:
        return None
    return stem


def json_names(sources, paths):
    """Flat JSON name for every scenario member.

    ``sources`` are scenario member names; ``paths`` is ``read_script_list``
    output or None. Returns ``{source: {"json", "naming", "original_path"}}``.
    A member takes the basename of its source path; members sharing a basename
    get ``__<sequence name>`` appended, and a member without a usable original
    name keeps its sequence name. ``naming`` states which rule applied.
    """
    result, stems = {}, {}
    for source in sources:
        number = member_number(source)
        path = paths[number] if paths is not None and number is not None and number < len(paths) else None
        stems[source] = _safe_stem(path) if path else None
        result[source] = {"json": _internal(source) + ".json", "naming": "internal", "original_path": path}
    shared = {}
    for source, stem in stems.items():
        if stem:
            shared.setdefault(_key(stem), []).append(source)
    for group in shared.values():
        for source in group:
            suffix = f"__{_internal(source)}" if len(group) > 1 else ""
            result[source].update(json=stems[source] + suffix + ".json",
                                  naming="original+sequence-suffix" if suffix else "original")
    # A leftover clash (an original name equal to another member's sequence
    # name) falls back to the sequence names, which the archive keeps unique.
    seen = {}
    for source, item in result.items():
        seen.setdefault(_key(item["json"]), []).append(source)
    for group in seen.values():
        if len(group) > 1:
            for source in group:
                result[source].update(json=_internal(source) + ".json", naming="internal")
    if len({_key(item["json"]) for item in result.values()}) != len(result):
        raise ValueError("scenario members do not have unique names")
    return result
