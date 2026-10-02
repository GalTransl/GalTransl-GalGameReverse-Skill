"""Self-contained checks: no upstream checkout, dotnet, or source tool required.

Run: python -m unittest discover -s tests -p test_catalog_source.py
"""
import contextlib
import io
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import runpy
import unittest


ROOT = Path(__file__).resolve().parents[1]
BUILDER = runpy.run_path(str(ROOT / "tools/build_source_catalog.py"))


def load(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def walk(value):
    yield value
    if isinstance(value, dict):
        for item in value.values():
            yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item)


class StaticCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.formats = load("catalog/formats.json")
        cls.registry = load("catalog/source-registries.json")
        cls.provenance = load("provenance/catalog.json")
        cls.entries = cls.formats["formats"]

    def by_tag(self, tag):
        matches = [entry for entry in self.entries if entry["tag"]["value"] == tag]
        self.assertEqual(len(matches), 1, tag)
        return matches[0]

    def test_registration_counts_and_compile_inventories(self):
        self.assertEqual(len(self.entries), 691)
        self.assertEqual(sum(f["kind"] == "archive" for f in self.entries), 681)
        self.assertEqual(sum(f["kind"] == "script" for f in self.entries), 10)
        self.assertEqual({f["kind"] for f in self.entries}, {"archive", "script"})
        for project in self.formats["projects"]:
            expected = BUILDER["EXPECTED"][project["project"]]
            actual = (project["compiled_cs_count"], project["effective_export_counts"].get("ArchiveFormat", 0),
                      project["effective_export_counts"].get("ScriptFormat", 0))
            self.assertEqual(actual, expected)
            self.assertEqual(len(project["compiled_sources"]), expected[0])
            self.assertEqual(len(set(project["compiled_sources"])), expected[0])
        self.assertEqual(len(self.formats["other_project_audit"]), 5)
        self.assertTrue(all(p["archive_or_script_exports"] == 0 for p in self.formats["other_project_audit"]))

    def test_stable_unique_identifiers(self):
        ids = [f["id"] for f in self.entries]
        self.assertEqual(ids, sorted(ids))
        self.assertEqual(len(ids), len(set(ids)))
        for entry in self.entries:
            self.assertEqual(entry["id"], BUILDER["stable_id"]("garbro", entry["assembly"],
                             entry["qualified_class"], entry["kind"], entry["tag"]["value"]))
        registry_ids = [item["id"] for item in walk(self.registry) if isinstance(item, dict) and "id" in item]
        self.assertEqual(len(registry_ids), len(set(registry_ids)))

    def test_pins_relative_paths_and_standalone_payloads(self):
        for document in (self.formats, self.registry, self.provenance):
            for item in walk(document):
                if isinstance(item, dict) and "repository" in item:
                    self.assertEqual(item["commit"], BUILDER["PINS"][item["repository"]])
                    if "line" in item:
                        self.assertGreater(item["line"], 0)
                if isinstance(item, str):
                    self.assertNotRegex(item, r"(?i)(?:(?<!\w)[a-z]:[/\\]|/Users/|/home/|\\\\Users\\|Administrator)")
                if isinstance(item, dict):
                    for key in ("path", "module_source"):
                        if key in item and item[key] is not None:
                            path = item[key]
                            self.assertFalse(PurePosixPath(path).is_absolute(), path)
                            self.assertFalse(PureWindowsPath(path).is_absolute(), path)
                            self.assertNotIn("..", PurePosixPath(path).parts)
                            self.assertNotIn("\\", path)
        self.assertEqual(self.formats["policy"]["runtime_dependencies"], [])
        self.assertEqual(self.registry["policy"]["runtime_dependencies"], [])
        self.assertEqual(self.provenance["runtime_dependencies"], [])

    def test_formats_are_compiled_and_debug_only_is_explicit(self):
        projects = {p["assembly"]: p for p in self.formats["projects"]}
        for entry in self.entries:
            self.assertIn(entry["source"]["path"], projects[entry["assembly"]]["compiled_sources"])
            self.assertEqual(entry["inheritance"][-1]["symbol"], "GameRes.IResource")
        debug_only = [f for f in self.entries if f["registration_configurations"] == ["Debug"]]
        self.assertEqual({f["source"]["path"] for f in debug_only},
                         {"Legacy/EbgSystem/ArcBIN.cs", "Legacy/Factor/ArcRES.cs", "Legacy/Weapon/ArcDAT.cs"})
        self.assertFalse(any(f["source"]["path"] == "Legacy/Weapon/ArcVoice.cs" for f in self.entries))
        self.assertEqual(sum(f["kind"] == "archive" and "Release" in f["registration_configurations"] for f in self.entries), 678)

    def test_key_formats_inheritance_and_weak_magic(self):
        nsa = self.by_tag("NSA")
        claim = nsa["capabilities"]["can_write"]
        self.assertIs(claim["value"], True)
        self.assertTrue(claim["inherited"])
        self.assertEqual(claim["source"]["symbol"], "GameRes.Formats.NScripter.SarOpener.CanWrite")
        self.assertEqual(nsa["extensions"]["value"], ["nsa", "dat"])
        self.assertEqual(nsa["magic"]["nonzero_uint32_le_hex"], [])
        self.assertEqual(self.by_tag("XP3")["magic"]["signature"]["value"], 0x0d335058)
        self.assertEqual(self.by_tag("DXR")["magic"]["signature"]["value"], 0x52494658)
        for tag in ("XP3", "YPF", "SAR", "NPA", "TXT", "SCR", "DAT/GENERIC"):
            self.by_tag(tag)
        for entry in self.entries:
            self.assertEqual(entry["magic"]["strength"], "weak_hint")
            self.assertIs(entry["magic"]["structure_validation_required"], True)
            self.assertEqual(entry["capabilities"]["status"], "source_claim")
            self.assertIs(entry["capabilities"]["roundtrip_verified"], False)
            self.assertEqual(entry["capabilities"]["all_versions_writable"], "unknown")
            self.assertIs(entry["family_hint"]["engine_identity_confirmed"], False)
        self.assertEqual(self.by_tag("TXT")["capabilities"]["methods"]["Write"]["implementation"], "throw_only_stub")

    def test_unknowns_preserve_raw_and_neutral_resource_evidence(self):
        for entry in self.entries:
            fields = [entry["description"], entry["extensions"], entry["magic"]["signature"], entry["magic"]["signatures"]]
            for field in fields:
                if field["status"] == "unknown":
                    self.assertIsNone(field["value"])
                    self.assertTrue(field["raw"])
        description = self.by_tag("NSA")["description"]
        self.assertEqual(description["status"], "unknown")
        self.assertIn("NScripter", description["neutral_resource_hint"]["value"])
        self.assertEqual(description["neutral_resource_hint"]["source"]["path"], "ArcFormats/Strings/arcStrings.resx")
        self.assertEqual(self.by_tag("ODN")["extensions"]["initializer_hint"]["value"], ["odn", "dat", "pni"])

    def test_source_registries_and_disabled_or_unimplemented_handlers(self):
        counts = self.registry["counts"]
        self.assertEqual(counts, {"msg_tool_builders": 78, "msg_tool_script_types": 78,
                                 "vntextpatch_active": 31, "vntextpatch_disabled": 1,
                                 "sextractor_active_adapters": 33, "sextractor_regex_presets": 31,
                                 "sextractor_tool_directories": 73})
        vn = {e["name"]: e for e in self.registry["vntextpatch"]["folder_scripts"]}
        self.assertFalse(vn["KirikiriScnScript"]["active"])
        self.assertEqual(vn["ShSystemScript"]["capability"], "no_writer")
        self.assertEqual(vn["ShSystemScript"]["write_patched"]["source"]["line"], 62)
        self.assertEqual(vn["ShSystemScript"]["write_patched"]["implementation"], "throw_only_stub")
        self.assertTrue(all(e["source"]["path"] == "src/scripts/mod.rs" for e in self.registry["msg_tool"]["builders"]))
        self.assertTrue(all(e["source"]["path"] == "src/types.rs" for e in self.registry["msg_tool"]["script_types"]))
        self.assertTrue(any(e["kind_hint"] == "image" for e in self.registry["msg_tool"]["script_types"]))
        self.assertTrue(all(e["status"] == "source_only_inventory" and not e["contents_read"]
                            for e in self.registry["sextractor"]["tool_directories"]))
        self.assertFalse(any(e["name"] == "Engine_AST" for e in self.registry["sextractor"]["engine_ini"]))

    def test_license_scope_is_evidence_not_blanket_mit(self):
        for source in self.provenance["sources"].values():
            license_info = source["license_evidence"]
            self.assertEqual(license_info["scope"], "repository_root_license_text_only")
            self.assertTrue(license_info["distribution_review_required"])
            self.assertIn("vendored_tools", license_info["not_a_blanket_license_for"])
        for name in ("sextractor", "msg-tool"):
            self.assertIn("GNU GENERAL PUBLIC LICENSE", self.provenance["sources"][name]["license_evidence"]["title_excerpt"])


class LexerUnitTests(unittest.TestCase):
    def parse(self, text, defines=frozenset()):
        return BUILDER["parse_cs"](text, "Fixture", "Fixture.cs", defines)

    def test_comments_strings_and_preprocessor_do_not_register(self):
        text = '''namespace Fixture {
// [Export(typeof(ArchiveFormat))]
class Commented {}
/* [Export(typeof(ScriptFormat))] class AlsoCommented {} */
class Strings { string s = "[Export(typeof(ArchiveFormat))] class Fake { }"; }
#if DEBUG
[Export(typeof(ArchiveFormat))]
#endif
public class Conditional {}
[Export(typeof(ScriptFormat))]
public class Active {}
}'''
        release = {c.name: c.exports for c in self.parse(text)}
        debug = {c.name: c.exports for c in self.parse(text, {"DEBUG"})}
        self.assertEqual(release, {"Commented": [], "Strings": [], "Conditional": [], "Active": ["ScriptFormat"]})
        self.assertEqual(debug["Conditional"], ["ArchiveFormat"])

    def test_getters_initializers_and_nested_class_names(self):
        text = '''namespace Fixture { class Outer { class Inner {
 public string Tag => "TAG";
 public uint Signature { get; } = 0x1234u;
 public bool CanWrite { get { return true; } }
 public string Dynamic { get { return GetRuntimeValue(); } }
} } }'''
        cls = next(c for c in self.parse(text) if c.name == "Inner")
        self.assertEqual(cls.qualified, "Fixture.Outer.Inner")
        values = {m.name: BUILDER["literal"](BUILDER["getter"](m)) for m in cls.members}
        self.assertEqual(values["Tag"], "TAG")
        self.assertEqual(values["Signature"], 0x1234)
        self.assertIs(values["CanWrite"], True)
        self.assertIs(values["Dynamic"], BUILDER["UNKNOWN"])

    def test_literals_do_not_guess_nested_runtime_strings(self):
        literal = BUILDER["literal"]
        self.assertEqual(literal('new[] { "nsa", /* ignored */ "dat", "" }'), ["nsa", "dat", ""])
        self.assertEqual(literal('new uint[] { 0x12345678u, 0 }'), [0x12345678, 0])
        self.assertIs(literal('GetSetting("nsa")'), BUILDER["UNKNOWN"])
        self.assertIs(literal('flag ? "yes" : "no"'), BUILDER["UNKNOWN"])

    def test_literal_arrays_constants_and_inheritance_are_not_guessed(self):
        text = '''namespace Fixture {
 class Base {
  public bool CanWrite => true;
  public const uint Magic = 0x01020304;
  public uint Signature => Magic;
  public string Tag => "FAKE/2";
  public void Create() { throw new System.NotImplementedException(); }
 }
 class Derived : Base {
  public Derived() { Extensions = new[] { "one", "two" }; Signatures = new[] { this.Signature, Magic, 0u }; }
 }
 class Conditional : Base {
  public Conditional() { if (RuntimeFlag) Extensions = new[] { "maybe" }; }
 }
}'''
        class FakeRepository:
            def evidence(self, path, line=1, symbol=None):
                return {"path": path, "line": line, "symbol": symbol}
        classes = self.parse(text)
        metadata = BUILDER["Metadata"](FakeRepository(), classes)
        derived = next(c for c in classes if c.name == "Derived")
        conditional = next(c for c in classes if c.name == "Conditional")
        tag = metadata.property(derived, "Tag")
        signature = metadata.property(derived, "Signature")
        self.assertIs(metadata.property(derived, "CanWrite")["value"], True)
        self.assertTrue(metadata.property(derived, "CanWrite")["inherited"])
        self.assertEqual(signature["value"], 0x01020304)
        self.assertEqual(metadata.array(derived, "Extensions", tag, signature)["value"], ["one", "two"])
        self.assertEqual(metadata.array(derived, "Signatures", tag, signature)["value"], [0x01020304, 0x01020304, 0])
        self.assertEqual(metadata.array(conditional, "Extensions", tag, signature)["status"], "unknown")
        self.assertEqual(metadata.method(derived, "Create")["implementation"], "throw_only_stub")

    def test_cli_requires_explicit_paths_without_discovery(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exc:
            BUILDER["main"]([])
        self.assertEqual(exc.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
