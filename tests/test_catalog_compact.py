"""Catalog storage, bounded lookup and lossless notice grouping regressions."""
from copy import deepcopy
import json
from pathlib import Path
import runpy
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from python.common.source_catalog import compact_formats, dump_formats, expand_formats, load_formats
from query_catalog import query

render_notices = runpy.run_path(str(ROOT / "tools/build_archive_notes.py"))["render_notices"]


def fixture():
    def source(path="Formats/One.cs", line=4, symbol="Fixture.One"):
        return {"repository": "garbro", "commit": "fixture", "path": path,
                "line": line, "symbol": symbol}
    return {"schema_version": 1, "source_commit": "fixture",
            "projects": [{"source": {"repository": "garbro", "commit": "fixture",
                                     "path": "Formats/Project.csproj", "line": 1}}],
            "formats": [{"qualified_class": "Fixture.One", "source": source(),
                         "tag": {"status": "known", "value": "ONE", "source": source(symbol="Fixture.One.Tag")},
                         "unknown": {"status": "unknown", "value": None, "raw": 'Runtime("保留证据")'},
                         "external": source(path="Base/Resource.cs", symbol="Base.Resource.Value"),
                         "null_symbol": source(symbol=None),
                         "foreign": {**source(), "repository": "other", "commit": "different"},
                         "default": {"explanation": "shared metadata " * 12}},
                        {"qualified_class": "Fixture.Two",
                         "source": source(path="Formats/Two.cs", symbol="Fixture.Two"),
                         "default": {"explanation": "shared metadata " * 12}}]}


class CompactCatalogTests(unittest.TestCase):
    def test_roundtrip_preserves_context_unknowns_and_foreign_evidence(self):
        original = fixture()
        baseline = deepcopy(original)
        packed = compact_formats(original)
        self.assertEqual(original, baseline)
        self.assertTrue(packed["shared"])
        self.assertEqual(packed["formats"][0]["tag"]["source"], {"$source": [None, 4, ".Tag"]})
        self.assertEqual(expand_formats(json.loads(dump_formats(original))), original)
        self.assertEqual(expand_formats(packed), original)
        self.assertEqual(dump_formats(original), dump_formats(original))
        restored = expand_formats(packed)
        restored["formats"][0]["default"]["explanation"] = "changed"
        self.assertNotEqual(restored["formats"][0]["default"], restored["formats"][1]["default"])

    def test_old_schema_and_rejected_markers(self):
        original = fixture()
        self.assertEqual(expand_formats(original), original)
        with self.assertRaises(ValueError):
            expand_formats({"schema_version": 3})
        original["bad"] = {"$ref": 0}
        with self.assertRaises(ValueError):
            compact_formats(original)

    def test_invalid_references_and_expansion_budgets(self):
        for reference in (-1, True, "0", 999):
            with self.subTest(reference=reference):
                packed = compact_formats(fixture())
                packed["formats"][0]["default"] = {"$ref": reference}
                with self.assertRaises(ValueError):
                    expand_formats(packed)
        packed = compact_formats(fixture())
        packed["shared"][0] = {"$ref": 0}
        with self.assertRaises(ValueError):
            expand_formats(packed)
        for budget in ({"max_nodes": 5}, {"max_depth": 2}):
            with self.assertRaises(ValueError):
                expand_formats(compact_formats(fixture()), **budget)
        packed = compact_formats(fixture())
        packed["formats"][0]["source"] = {"$source": [None, 0, ""]}
        with self.assertRaises(ValueError):
            expand_formats(packed)

    def test_shipped_inventory_serialization_is_canonical_and_small(self):
        path = ROOT / "catalog/formats.json"
        expanded = load_formats(path)
        self.assertEqual(len(expanded["formats"]), 691)
        self.assertEqual(path.read_text(encoding="utf-8"), dump_formats(expanded))
        self.assertLess(path.stat().st_size, 1_400_000)


class CatalogQueryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load_formats(ROOT / "catalog/formats.json")

    def test_tag_extension_magic_and_full_details(self):
        result = query(self.catalog, tag="xp3", magic="58 50 33 0D", details=True)
        self.assertEqual(result["total"], 1)
        entry = result["formats"][0]
        self.assertEqual(entry["tag"]["value"], "XP3")
        self.assertEqual(entry["source"]["commit"], self.catalog["source_commit"])
        self.assertEqual(query(self.catalog, tag="XP3", extension=".impossible")["total"], 0)
        result = query(self.catalog, extension=".DaT", limit=3)
        self.assertGreater(result["total"], 3)
        self.assertEqual(result["returned"], 3)
        self.assertTrue(all("dat" in e["extensions"] for e in result["formats"]))

    def test_pagination_recovers_inventory_once_and_search_expands_references(self):
        ids, offset = [], 0
        while True:
            result = query(self.catalog, offset=offset, limit=100)
            ids.extend(entry["id"] for entry in result["formats"])
            offset = result["next_offset"]
            if offset is None:
                break
        self.assertEqual(ids, [entry["id"] for entry in self.catalog["formats"]])
        nsa = query(self.catalog, tag="NSA", text="NScripter", details=True)["formats"][0]
        self.assertEqual(nsa["description"]["status"], "unknown")
        self.assertEqual(query(self.catalog, offset=len(ids))["formats"], [])

    def test_invalid_queries_fail_instead_of_truncating(self):
        for args in ({"offset": -1}, {"limit": 0}, {"limit": 101},
                     {"magic": "invalid"}, {"magic": "0000"}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                query(self.catalog, **args)


class NoticeGroupingTests(unittest.TestCase):
    def test_complete_notices_and_per_file_mapping_are_preserved(self):
        first = "// Copyright A\n// Complete license A"
        second = "// Copyright B\n// Complete license B"
        records = [("Format/B.cs", first), ("Format/A.cs", second), ("Format/C.cs", first)]
        rendered = render_notices(records)
        self.assertEqual(rendered.count(first), 1)
        self.assertEqual(rendered.count(second), 1)
        recovered = {}
        for section in rendered.split("\n## ")[1:]:
            listing, block = section.split("\n```text\n", 1)
            notice, _ = block.split("\n```", 1)
            for line in listing.splitlines():
                if line.startswith("- `"):
                    recovered[line[3:-1]] = notice
        self.assertEqual(recovered, dict(records))
        self.assertEqual(rendered, render_notices(list(reversed(records))))


if __name__ == "__main__":
    unittest.main()
