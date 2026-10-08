# SPDX-License-Identifier: GPL-3.0-or-later
"""YDG image/font workspaces: original templates, PNG edits, verified new output."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
import stat

from ..common.contract import load_json
from ..common.safety import write_new_tree, validate_names, _check_existing_ancestors
from .yuris_ydg import MAX_BYTES, read_ydg, rebuild_ydg, png_bytes, read_png
from .yuris_font import Grid, render_page, reverse_mapping, cp932_pages

SCHEMA = "yuris-ydg/1"
FONT_PAGE = re.compile(r"fnt_s(\d+)_n(\d+)\.ydg", re.IGNORECASE)
MAX_TOTAL = 256 << 20
MAX_FILES = 1024


def _json(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _small(path, limit=MAX_BYTES):
    path = Path(path)
    _check_existing_ancestors(path.parent)
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or getattr(info, "st_file_attributes", 0) & 0x400 or info.st_size > limit):
        raise ValueError(f"invalid or oversized input: {path}")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("input grew beyond budget")
    return data


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _shape(resource):
    return {"width": resource.width, "height": resource.height,
            "table_offset": resource.table_offset,
            "tiles": [{key: value for key, value in asdict(tile).items() if key != "pixels"}
                      for tile in resource.tiles]}


def _add(entries, name, data):
    if sum(len(payload) for _, payload in entries) + len(data) > MAX_TOTAL:
        raise ValueError("YDG workspace exceeds total budget")
    entries.append((name, data))


def extract(source, destination):
    source = Path(source).resolve()
    destination = Path(destination).absolute()
    if destination.exists():
        raise FileExistsError(f"refusing to replace output: {destination}")
    if source.is_file():
        root, paths = source.parent, [source]
    elif source.is_dir():
        if destination.resolve().is_relative_to(source):
            raise ValueError("YDG workspace must be outside the scanned resource directory")
        root, paths = source, []
        for path in root.rglob("*"):
            if path.suffix.lower() == ".ydg":
                if any((parent / "reports/extraction.json").is_file()
                       for parent in path.parents if parent.is_relative_to(root)):
                    raise ValueError("source contains a prior extraction workspace; select raw resources")
                if len(paths) >= MAX_FILES:
                    raise ValueError("too many YDG resources")
                paths.append(path)
        paths.sort()
    else:
        raise ValueError("YDG source is not a file/directory")
    if not paths:
        raise ValueError("no YDG resources selected")
    names = validate_names([path.relative_to(root).as_posix() for path in paths])
    records, entries, input_total = [], [], 0
    for path, name in zip(paths, names):
        if not path.resolve().is_relative_to(root):
            raise ValueError("YDG input escapes source directory")
        raw = _small(path)
        input_total += len(raw)
        if input_total > MAX_TOTAL:
            raise ValueError("YDG source exceeds total budget")
        resource = read_ydg(raw)
        if rebuild_ydg(raw, resource.pixels) != raw:
            raise ValueError("YDG parser/writer identity roundtrip differs")
        image_name = name + ".png"
        record = {"source": name, "sha256": _sha(raw), "image": image_name,
                  "structure": _shape(resource)}
        records.append(record)
        _add(entries, "original/" + name, raw)
        _add(entries, "images/" + image_name, png_bytes(resource))
        _add(entries, "metadata/" + image_name + ".ydg.json", _json(record))
    report = {"schema": SCHEMA, "resources": records, "count": len(records),
              "identity_roundtrip": True, "game_display_verified": False}
    _add(entries, "reports/extraction.json", _json(report))
    write_new_tree(Path(destination), entries)
    return report


def _workspace(workspace):
    root = Path(workspace).resolve()
    report = load_json(_small(root / "reports/extraction.json", 8 << 20))
    if report.get("schema") != SCHEMA or not isinstance(report.get("resources"), list):
        raise ValueError("unsupported YDG workspace")
    records = report["resources"]
    if not 0 < len(records) <= MAX_FILES or report.get("count") != len(records):
        raise ValueError("invalid YDG workspace count")
    names = validate_names([record["source"] for record in records])
    resources, total = [], 0
    for name, record in zip(names, records):
        if record.get("image") != name + ".png":
            raise ValueError("YDG image/source identity changed")
        original_path = root / "original" / name
        if not original_path.resolve().is_relative_to(root):
            raise ValueError("original path escapes workspace")
        raw = _small(original_path)
        total += len(raw)
        if total > MAX_TOTAL:
            raise ValueError("YDG originals exceed total budget")
        resource = read_ydg(raw)
        sidecar = load_json(_small(root / "metadata" / (record["image"] + ".ydg.json"), 1 << 20))
        if _sha(raw) != record.get("sha256") or _shape(resource) != record.get("structure") or sidecar != record:
            raise ValueError("YDG original or metadata changed; re-extract reliable sources")
        resources.append((record, raw, resource))
    return root, resources


def pack(workspace, destination, *, images=None):
    root, resources = _workspace(workspace)
    images = Path(images).resolve() if images is not None else root / "images"
    expected = {record["image"] for record, _, _ in resources}
    actual = {path.relative_to(images).as_posix() for path in images.rglob("*") if path.is_file()}
    if actual != expected:
        raise ValueError("PNG file set differs from YDG workspace")
    entries, results = [], []
    for record, raw, resource in resources:
        path = images / record["image"]
        if not path.resolve().is_relative_to(images):
            raise ValueError("PNG path escapes image directory")
        pixels = read_png(_small(path), resource.width, resource.height)
        rebuilt = rebuild_ydg(raw, pixels)
        _add(entries, record["source"], rebuilt)
        results.append({"source": record["source"], "changed": rebuilt != raw,
                        "sha256": _sha(rebuilt), "pixels_verified": True})
    report = {"schema": SCHEMA, "resources": results, "game_display_verified": False}
    _add(entries, "reports/repack.json", _json(report))
    write_new_tree(Path(destination), entries)
    return report


def _mapping(path, preset):
    if preset:
        from ..common.jis_substitution import MAPPING_SHA256
        data = _small(Path(__file__).resolve().parents[1] / "common/jis_cn_jp.json", 1 << 20)
        if _sha(data) != MAPPING_SHA256:
            raise ValueError("public JIS preset hash changed")
        return load_json(data)
    if path is None:
        return {}
    value = load_json(_small(path, 1 << 20))
    if isinstance(value, dict) and "chinese_to_proxy" in value:
        return value["chinese_to_proxy"]
    if isinstance(value, dict) and "character_substitution" in value:
        config = value["character_substitution"]
        source, target = config.get("source_characters"), config.get("target_characters")
        if (config.get("enable") is not True or not isinstance(source, str) or not isinstance(target, str)
                or len(source) != len(target) or len(set(target)) != len(target)):
            raise ValueError("invalid enabled UIF character mapping")
        return dict(zip(target, source))
    return value


def font(workspace, destination, *, font_path, config_path, mapping_path=None,
         jis_preset=False, mapped_only=False):
    if mapping_path is not None and jis_preset:
        raise ValueError("mapping and JIS preset are mutually exclusive")
    _, resources = _workspace(workspace)
    font_sha = _sha(_small(font_path, 64 << 20))
    config = load_json(_small(config_path, 1 << 20))
    if not isinstance(config, dict) or set(config) - {"grid", "grids", "style", "styles", "symbol_rules"}:
        raise ValueError("invalid font atlas configuration")
    mapping = _mapping(mapping_path, jis_preset)
    inverse = reverse_mapping(mapping)
    available, seen, entries, records = {}, set(), [], []
    for record, raw, resource in resources:
        source = Path(record["source"])
        match = FONT_PAGE.fullmatch(source.name)
        if match is None:
            raise ValueError("font workspace must contain only fnt_sSIZE_nPAGE.ydg resources")
        size, page = map(int, match.groups())
        group = source.parent.as_posix()
        atlas_group = (group, size)
        if (atlas_group, page) in seen:
            raise ValueError("duplicate font page in atlas group")
        seen.add((atlas_group, page))
        grid_data = config.get("grid", config.get("grids", {}).get(str(size)))
        if not isinstance(grid_data, dict):
            raise ValueError(f"missing explicit grid for font size {size}")
        grid = Grid(**grid_data)
        styles = config.get("styles", {})
        style = styles.get(group, config.get("style", {}))
        pixels, glyphs = render_page(resource.pixels, resource.width, resource.height, page,
                                    font_path, grid, mapping=mapping, mapped_only=mapped_only,
                                    style=style, symbol_rules=config.get("symbol_rules"))
        available.setdefault(atlas_group, set()).update(
            source_glyph for _, source_glyph in cp932_pages()[page][1] if source_glyph)
        rebuilt = rebuild_ydg(raw, pixels)
        _add(entries, record["source"], rebuilt)
        rendered = read_ydg(rebuilt)
        _add(entries, "preview/" + record["image"], png_bytes(rendered))
        records.append({"source": record["source"], "page": page,
                        "grid": asdict(grid), "style": style, "glyphs": glyphs,
                        "pixels_verified": True})
    if any(set(inverse) - glyphs for glyphs in available.values()):
        raise ValueError("selected font pages do not cover every requested glyph proxy")
    report = {"schema": SCHEMA, "resources": records, "font_sha256": font_sha,
              "mapping": mapping, "mapped_only": mapped_only,
              "symbol_rules": config.get("symbol_rules", {}), "game_display_verified": False}
    _add(entries, "reports/font.json", _json(report))
    write_new_tree(Path(destination), entries)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    unpack = commands.add_parser("extract")
    unpack.add_argument("source")
    unpack.add_argument("destination")
    repack = commands.add_parser("pack")
    repack.add_argument("workspace")
    repack.add_argument("destination")
    repack.add_argument("--images")
    render = commands.add_parser("font")
    render.add_argument("workspace")
    render.add_argument("destination")
    render.add_argument("--font", dest="font_path", required=True)
    render.add_argument("--config", dest="config_path", required=True)
    mapping = render.add_mutually_exclusive_group()
    mapping.add_argument("--mapping", dest="mapping_path")
    mapping.add_argument("--jis-preset", action="store_true")
    render.add_argument("--mapped-only", action="store_true")
    args = vars(parser.parse_args())
    command = args.pop("command")
    print(json.dumps({"extract": extract, "pack": pack, "font": font}[command](**args),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
