"""Search the bundled format inventory without printing its entire payload."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from python.common.source_catalog import load_formats


def query(document, *, tag=None, extension=None, magic=None, text=None,
          offset=0, limit=20, details=False):
    if offset < 0 or not 1 <= limit <= 100:
        raise ValueError("offset must be >= 0; limit must be 1..100")
    if extension is not None:
        extension = extension.lstrip(".").casefold()
    if magic is not None:
        magic = bytes.fromhex(magic).hex()
        if len(magic) != 8:
            raise ValueError("magic must contain exactly four header bytes in file order")
    matches = []
    for entry in document["formats"]:
        if tag is not None and tag.casefold() != entry["tag"]["value"].casefold():
            continue
        extensions = entry["extensions"].get("value") or []
        if extension is not None and extension not in [item.casefold() for item in extensions]:
            continue
        if magic is not None and magic not in entry["magic"]["nonzero_uint32_le_hex"]:
            continue
        if text is not None and text.casefold() not in json.dumps(entry, ensure_ascii=False).casefold():
            continue
        matches.append(entry)
    selected = matches[offset:offset + limit]
    if not details:
        selected = [{"id": e["id"], "tag": e["tag"]["value"], "kind": e["kind"],
                     "extensions": e["extensions"]["value"],
                     "magic": e["magic"]["nonzero_uint32_le_hex"],
                     "source": e["source"], "capability_status": e["capabilities"]["status"],
                     "roundtrip_verified": e["capabilities"]["roundtrip_verified"]} for e in selected]
    end = offset + len(selected)
    return {"total": len(matches), "offset": offset, "returned": len(selected),
            "next_offset": end if end < len(matches) else None, "formats": selected}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", help="Exact format Tag (case insensitive)")
    parser.add_argument("--extension", help="Exact extension, with or without leading dot")
    parser.add_argument("--magic", help="Four header bytes in file order, e.g. 5850330d")
    parser.add_argument("--text", help="Substring in expanded metadata")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=20, help="Records per page, 1..100")
    parser.add_argument("--details", action="store_true", help="Include full source evidence and unknown fields")
    args = parser.parse_args(argv)
    try:
        result = query(load_formats(ROOT / "catalog/formats.json"), **vars(args))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.exit(2, f"catalog query failed: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
