"""Synthetic contracts for prefixed UnityFS bundles and the Unity scan summary (no game data)."""
import io
import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest import mock

from python.archives import unityfs as fs
from python.common.binary import FormatError
from python.engines import unity_scan, unity_textasset as ta
from tests import unity_fixtures as fx

SCRIPT = "名前\n『セリフ』\n\n地の文。\n".encode("utf-8")
PREFIX = b"\x0f" * 128


def level(script=SCRIPT, externals=("globalgamemanagers.assets",), script_id=1):
    return fx.serialized([(5, 114, fx.behaviour(1, script_id, "obj")), (6, 49, fx.textasset("story", script))],
                         version=22, unity="2021.3.5f1", externals=externals)


def scripts(cls, namespace="Game", path_id=1):
    return fx.serialized([(path_id, 115, fx.monoscript(cls, cls, namespace))], version=22, unity="2021.3.5f1")


def bundle(payload=None, **kw):
    return fx.bundle([("CAB-a", payload or level(), 4), ("CAB-a.resS", b"opaque" * 5, 0)],
                     version=8, engine="2021.3.5f1", **kw)


class PrefixTests(unittest.TestCase):
    def test_signature_window(self):
        raw = bundle()
        self.assertEqual(fs.signature_offset(raw), 0)
        self.assertEqual(fs.signature_offset(PREFIX + raw), 128)
        self.assertEqual(fs.signature_offset(bytes(fs.MAX_PREFIX) + raw), fs.MAX_PREFIX)
        self.assertIsNone(fs.signature_offset(bytes(fs.MAX_PREFIX + 1) + raw))
        self.assertIsNone(fs.signature_offset(b"x" * 64))
        with self.assertRaises(FormatError):
            fs.split_prefix(bytes(fs.MAX_PREFIX + 1) + raw)

    def test_substream_reads_bundle_after_prefix(self):
        raw = bundle()
        sub = fs.SubStream(io.BytesIO(PREFIX + raw), len(PREFIX))
        self.assertEqual(sub.read(), raw)
        sub.seek(-4, 2)
        self.assertEqual(sub.read(10), raw[-4:])
        header = fs.read_header(fs.SubStream(io.BytesIO(PREFIX + raw), len(PREFIX)))
        self.assertEqual(header.size, len(raw))
        with self.assertRaises(FormatError):
            fs.SubStream(io.BytesIO(raw), len(raw) + 1)
        with self.assertRaises(FormatError):  # read_header itself stays strict at offset 0
            fs.read_header(io.BytesIO(PREFIX + raw))


class PrefixedWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, raw, name="scenario.bundle"):
        path = self.root / name
        path.write_bytes(raw)
        return path

    def test_prefix_kept_on_identity_and_variable_length_edit(self):
        raw = PREFIX + bundle()
        report = ta.extract(self.write(raw), self.root / "ws", target="Game_Data/scenario.bundle")
        self.assertEqual(report["bundle_prefix"]["length"], 128)
        self.assertEqual(report["bundle_prefix"]["uniform_byte"], "0x0f")
        ws = self.root / "ws"
        roundtrip = (ws / "rebuilt/roundtrip/Game_Data/scenario.bundle").read_bytes()
        self.assertEqual(roundtrip[:128], PREFIX)
        self.assertEqual(fs.read_bundle(roundtrip[128:])[2], fs.read_bundle(raw[128:])[2])
        # The writer's own (uncompressed) output rebuilds byte-identically, prefix included.
        self.assertEqual(ta.rebuild_container(ta.open_container(roundtrip), {}), roundtrip)
        (ws / "replace/story.txt").write_bytes(("中文替换，更长的一段𠀋\n" * 4).encode("utf-8"))
        result = ta.pack(ws, self.root / "out", text=True)
        self.assertEqual(result["bundle_prefix"]["length"], 128)
        rebuilt = (self.root / "out/files/Game_Data/scenario.bundle").read_bytes()
        self.assertEqual(rebuilt[:128], PREFIX)
        container = ta.open_container(rebuilt)
        self.assertEqual(container.prefix, PREFIX)
        found = {t.name: t.script for _, _, _, t in ta.text_assets(container)}
        self.assertEqual(found["story"], ("中文替换，更长的一段𠀋\n" * 4).encode("utf-8"))
        self.assertEqual(fs.read_bundle(rebuilt[128:])[2]["CAB-a.resS"], b"opaque" * 5)

    def test_unprefixed_report_and_plain_serialized_unchanged(self):
        report = ta.extract(self.write(bundle()), self.root / "ws")
        self.assertIsNone(report["bundle_prefix"])
        report = ta.extract(self.write(level(), "level.assets"), self.root / "ws2")
        self.assertEqual(report["container"], "serialized")
        self.assertTrue(report["identity_bundle_byte_identical"])

    def test_rejections_are_explicit(self):
        good = bundle()
        broken = bytearray(PREFIX + good)
        broken[128 + 8:128 + 12] = b"\0\0\0\x63"  # unsupported format version after the prefix
        with self.assertRaisesRegex(FormatError, "128-byte prefix"):
            ta.open_container(bytes(broken))
        with self.assertRaisesRegex(FormatError, "declared size"):
            ta.open_container(PREFIX + good + b"tail")
        with self.assertRaisesRegex(FormatError, "neither a UnityFS bundle"):
            ta.open_container(bytes(fs.MAX_PREFIX + 1) + good)
        with self.assertRaisesRegex(FormatError, "neither a UnityFS bundle"):
            ta.open_container(random.Random(3).randbytes(4096))
        with self.assertRaisesRegex(FormatError, "legacy"):
            ta.open_container(b"UnityWeb\0" + bytes(200))


class ScanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.game = Path(self.tmp.name) / "game"
        self.data = self.game / "Demo_Data"
        (self.data / "StreamingAssets/aa").mkdir(parents=True)
        (self.data / "globalgamemanagers.assets").write_bytes(scripts("TalkData"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_prefixed_bundle_is_scanned(self):
        (self.data / "StreamingAssets/aa/a.bundle").write_bytes(PREFIX + bundle())
        result = unity_scan.scan(self.game)
        self.assertFalse(result["partial"], result["partial_reasons"])
        entry = next(c for c in result["containers"] if c["path"].endswith("a.bundle"))
        self.assertEqual((entry["kind"], entry["prefix_length"]), ("unityfs", 128))
        self.assertEqual(entry["nodes"][0]["textassets"][0]["name"], "story")
        self.assertEqual(entry["nodes"][0]["monobehaviour_classes"], {"Game.TalkData": 1})
        self.assertEqual(result["summary"]["prefixed_bundles"], 1)
        self.assertEqual(result["summary"]["text_textassets"], 1)

    def test_unopened_and_unrecognised_bundles_mark_partial(self):
        broken = bytearray(PREFIX + bundle())
        broken[128 + 8:128 + 12] = b"\0\0\0\x63"
        (self.data / "StreamingAssets/aa/broken.bundle").write_bytes(bytes(broken))
        noise = random.Random(5).randbytes(3000)
        (self.data / "StreamingAssets/aa/opaque.bundle").write_bytes(noise)
        (self.data / "StreamingAssets/aa/12345").write_bytes(noise)
        (self.data / "StreamingAssets/aa/12345.manifest").write_text("ManifestFileVersion: 0\n", encoding="utf-8")
        (self.data / "StreamingAssets/notes.bin").write_bytes(noise)
        result = unity_scan.scan(self.game)
        self.assertTrue(result["partial"])
        summary = result["summary"]
        self.assertEqual([u["path"] for u in summary["unopened_containers"]],
                         ["Demo_Data/StreamingAssets/aa/broken.bundle"])
        self.assertEqual(summary["unopened_containers"][0]["prefix_length"], 128)
        self.assertEqual(sorted(summary["unrecognized_bundles"]),
                         ["Demo_Data/StreamingAssets/aa/12345", "Demo_Data/StreamingAssets/aa/opaque.bundle"])
        reasons = {b["path"].rsplit("/", 1)[-1]: b["reason"] for b in result["unrecognized_bundles"]}
        self.assertEqual(reasons, {"12345": "sibling .manifest file", "opaque.bundle": ".bundle extension"})
        self.assertEqual(len(result["partial_reasons"]), 2)

    def test_monoscripts_are_not_mixed_across_data_dirs(self):
        for sub, cls in (("Desktop", "DeskTalk"), ("VR", "VrTalk")):
            data = self.game / sub / f"{sub}_Data"
            data.mkdir(parents=True)
            (data / "globalgamemanagers.assets").write_bytes(scripts(cls))
            (data / "level0").write_bytes(level(externals=("globalgamemanagers.assets",)))
        root = unity_scan.scan(self.game)

        def classes(result, prefix=""):
            return {prefix + c["path"]: c.get("monobehaviour_classes") for c in result["containers"]}

        merged = classes(root)
        self.assertEqual(merged["Desktop/Desktop_Data/level0"], {"Game.DeskTalk": 1})
        self.assertEqual(merged["VR/VR_Data/level0"], {"Game.VrTalk": 1})
        union = {}
        for sub in ("Desktop", "VR"):
            union.update(classes(unity_scan.scan(self.game / sub), sub + "/"))
        self.assertEqual({k: v for k, v in merged.items() if k in union}, union)

    def test_same_named_copies_are_flagged_and_never_guessed(self):
        backup = self.data / "Backup"
        backup.mkdir()
        (backup / "globalgamemanagers.assets").write_bytes(scripts("Other"))
        (self.data / "level0").write_bytes(level())  # exact path wins over the backup copy
        (backup / "level1").write_bytes(level(externals=("shared.assets",)))
        (self.data / "Sub1").mkdir()
        (self.data / "Sub1/shared.assets").write_bytes(scripts("One"))
        (backup / "shared.assets").write_bytes(scripts("Two"))
        result = unity_scan.scan(self.game)
        by_path = {c["path"]: c for c in result["containers"]}
        self.assertEqual(by_path["Demo_Data/level0"]["monobehaviour_classes"], {"Game.TalkData": 1})
        ambiguous = by_path["Demo_Data/Backup/level1"]
        self.assertEqual((ambiguous["monobehaviour_classes"], ambiguous["monobehaviour_ambiguous"]), ({}, 1))
        groups = {g["name"]: g for g in result["summary"]["duplicate_container_names"]}
        self.assertEqual(set(groups), {"globalgamemanagers.assets", "shared.assets"})
        self.assertTrue(groups["globalgamemanagers.assets"]["same_data_dir"])

    def test_known_route_objects_listed_outside_top_classes(self):
        (self.data / "globalgamemanagers.assets").write_bytes(
            fx.serialized([(1, 115, fx.monoscript("AdvImportBook", "AdvImportBook", "Utage"))]
                          + [(10 + i, 115, fx.monoscript(f"C{i}", f"C{i}", "Ui")) for i in range(40)],
                          version=22, unity="2021.3.5f1"))
        objects = [(100, 114, fx.behaviour(1, 1, "01.Story.book"))]
        objects += [(200 + i * 40 + k, 114, fx.behaviour(1, 10 + i, "ui")) for i in range(40) for k in range(i % 3 + 2)]
        (self.data / "sharedassets0.assets").write_bytes(
            fx.serialized(objects, version=22, unity="2021.3.5f1", externals=("globalgamemanagers.assets",)))
        summary = unity_scan.scan(self.game)["summary"]
        self.assertNotIn("Utage.AdvImportBook", summary["top_monobehaviour_classes"])
        self.assertEqual(summary["known_route_objects"], [
            {"container": "Demo_Data/sharedassets0.assets", "path_id": 100, "name": "01.Story.book",
             "class": "Utage.AdvImportBook", "route": "utage-book",
             "size": len(fx.behaviour(1, 1, "01.Story.book"))}])

    def test_large_opaque_files_get_sampled_entropy(self):
        noise = random.Random(7).randbytes(20000)
        (self.data / "StreamingAssets/blob").write_bytes(noise)
        (self.data / "StreamingAssets/movie.ogg").write_bytes(b"OggS" + noise)
        (self.data / "StreamingAssets/table.txt").write_bytes(b"id,text\n" * 200)
        with mock.patch.object(unity_scan, "WHOLE_FILE", 4096), mock.patch.object(unity_scan, "SAMPLE_SIZE", 512):
            result = unity_scan.scan(self.game)
        items = {s["path"].rsplit("/", 1)[-1]: s for s in result["streaming_assets"]}
        self.assertEqual(items["blob"]["entropy_samples"], {"count": 16, "bytes_each": 512})
        self.assertNotIn("entropy_samples", items["table.txt"])
        self.assertGreater(items["blob"]["entropy"], 7.5)
        self.assertEqual(items["movie.ogg"]["magic"], "ogg")
        self.assertNotIn("suspected", items["movie.ogg"])
        self.assertLess(items["table.txt"]["entropy"], 5)
        self.assertEqual([f["path"] for f in result["summary"]["suspected_encrypted_files"]],
                         ["Demo_Data/StreamingAssets/blob"])
        self.assertFalse(result["partial"])
        json.dumps(result)


if __name__ == "__main__":
    unittest.main()
