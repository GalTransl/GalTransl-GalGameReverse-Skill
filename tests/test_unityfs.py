"""Synthetic UnityFS, serialized v17-v22 and TextAsset contracts (no game data)."""
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest

from python.archives import unity_serialized as us
from python.archives import unityfs as fs
from python.common.binary import FormatError
from python.engines import unity_scan, unity_textasset as ta
from tests import unity_fixtures as fx

SCRIPT = "***BGround_BG00\n\n名前(V_0001)\n『セリフ』\n\n地の文。\n".encode("utf-8")


def asset_v22(script=SCRIPT, tree=True, version=22, unity="2022.3.27f1", path_name=None):
    trees = {49: fx.textasset_tree(path_name is not None), 142: [(0, "AssetBundle", "Base", 0x8000, 0)] + fx.string_nodes(1, "m_Name")} if tree else None
    objects = [(1, 142, fx.string("bundle")), (-77, 49, fx.textasset("scene_a", script, path_name)),
               (900000000000, 49, fx.textasset("scene_b", b"\xef\xbb\xbfplain", path_name))]
    return fx.serialized(objects, version=version, unity=unity, trees=trees)


class LZ4Tests(unittest.TestCase):
    def test_literals_and_overlapping_match(self):
        self.assertEqual(fs.lz4_block(fx.lz4_literals(b"x" * 300), 300), b"x" * 300)
        block, expected = fx.lz4_repeat(b"abc", 64)
        self.assertEqual(fs.lz4_block(block, len(expected)), expected)

    def test_bad_streams(self):
        for block, size in ((b"", 0), (b"\x10", 1), (b"\x10a\x05\x00", 6), (fx.lz4_literals(b"abc"), 4),
                            (fx.lz4_literals(b"abcd"), 3), (b"\x1fa\x01\x00", 30)):
            with self.subTest(block=block), self.assertRaises(FormatError):
                fs.lz4_block(block, size)

    def test_lzma_block(self):
        data = b"unity lzma " * 50
        self.assertEqual(fs.lzma_block(fx.lzma_block(data), len(data)), data)
        with self.assertRaises(FormatError):
            fs.lzma_block(fx.lzma_block(data), len(data) + 1)
        with self.assertRaises(FormatError):
            fs.lzma_block(b"\xff" + bytes(10), 4)


class BundleTests(unittest.TestCase):
    nodes = [("CAB-one", asset_v22(), 4), ("CAB-one.resS", b"\x01\x02raw" * 9, 0)]

    def test_versions_compressions_and_layouts(self):
        for version in (6, 7, 8):
            for method in (0, 1, 2, 3):
                for at_end in (False, True):
                    with self.subTest(version=version, method=method, at_end=at_end):
                        raw = fx.bundle(self.nodes, version=version, method=method, at_end=at_end,
                                        padding=version >= 7, engine="5.6.5f1" if version == 6 else "2022.3.27f1")
                        bundle, _, contents = fs.read_bundle(raw)
                        self.assertEqual(bundle.version, version)
                        self.assertEqual([n.path for n in bundle.nodes], ["CAB-one", "CAB-one.resS"])
                        self.assertEqual(contents["CAB-one"], self.nodes[0][1])
                        reader = fs.BundleReader(io.BytesIO(raw))
                        node = reader.bundle.nodes[1]
                        self.assertEqual(reader.read(node.offset + 2, 5), self.nodes[1][1][2:7])

    def test_rebuild_identity_and_replacement(self):
        for at_end in (False, True):
            raw = fx.bundle(self.nodes, version=7, engine="2021.3.5f1", at_end=at_end)
            same = fs.rebuild(raw, {})
            before, _, old = fs.read_bundle(raw)
            after, _, new = fs.read_bundle(same)
            self.assertEqual(old, new)
            self.assertEqual((after.engine_version, after.flags & ~0x3F), (before.engine_version, before.flags & ~0x3F))
            self.assertEqual(after.compression, 0)
            self.assertEqual({b.flags for b in after.blocks}, {fs.BLOCK_STREAMED})
            changed = fs.rebuild(raw, {"CAB-one.resS": b"longer replacement payload" * 3})
            _, _, new = fs.read_bundle(changed)
            self.assertEqual(new["CAB-one"], old["CAB-one"])
            self.assertEqual(new["CAB-one.resS"], b"longer replacement payload" * 3)

    def test_rejections(self):
        good = fx.bundle(self.nodes, version=8)
        cases = {
            "signature": b"UnityWeb\0" + good[9:],
            "version": good[:8] + struct.pack(">I", 9) + good[12:],
            "truncated": good[:-1],
            "trailing": good + b"\0",
            "unknown flag": fx.bundle(self.nodes, extra_flags=0x400),
            "old 0x200": fx.bundle(self.nodes, version=6, engine="2019.4.1f1", padding=True),
            "lzham": fx.bundle(self.nodes, info_method=4),
        }
        for label, raw in cases.items():
            with self.subTest(label), self.assertRaises(FormatError):
                fs.read_bundle(raw)
        with self.assertRaises(FormatError):
            fs.rebuild(good, {"missing": b""})
        hashed = fx.bundle(self.nodes, info_hash=b"\x01" * 16)
        fs.rebuild(hashed, {})
        with self.assertRaises(FormatError):
            fs.rebuild(hashed, {"CAB-one.resS": b"x"})

    def test_bad_node_table_and_budget(self):
        dup = fx.bundle([("a", b"1234", 4), ("a", b"5678", 4)], info_method=0, method=0)
        with self.assertRaises(FormatError):
            fs.read_bundle(dup)
        raw = bytearray(fx.bundle([("a", b"1234", 4)], info_method=0, method=0, version=6, padding=False, engine="5.6.5f1"))
        at = raw.index(b"a\0") - 20
        struct.pack_into(">q", raw, at + 8, 99)
        with self.assertRaises(FormatError):
            fs.read_bundle(bytes(raw))
        big = fx.bundle([("a", bytes(4096), 4)], method=2, block_size=1024)
        reader = fs.BundleReader(io.BytesIO(big), budget=2048)
        reader.read(0, 1500)
        with self.assertRaises(FormatError):
            reader.read(2048, 2048)


class SerializedTests(unittest.TestCase):
    def test_v17_through_v22_with_type_trees(self):
        for version in (17, 18, 19, 20, 21, 22):
            with self.subTest(version=version):
                unity = "5.6.5f1" if version == 17 else "2022.3.27f1"
                raw = asset_v22(version=version, unity=unity, path_name="" if version == 17 else None)
                index = us.read_index(io.BytesIO(raw))
                self.assertEqual((index.version, index.type_tree, len(index.objects)), (version, True, 3))
                obj = index.objects[1]
                self.assertEqual(obj.path_id, -77)
                fields = us.walk_object(index.types[obj.type_index].nodes, raw[obj.offset:obj.offset + obj.size])
                self.assertEqual(fields[1].value, SCRIPT)
                rebuilt = us.rebuild(raw, {900000000000: raw[index.objects[2].offset:index.objects[2].offset + index.objects[2].size] + b"tail"})
                after = us.read_index(io.BytesIO(rebuilt))
                self.assertEqual(rebuilt[after.objects[1].offset:after.objects[1].offset + after.objects[1].size],
                                 raw[obj.offset:obj.offset + obj.size])
                self.assertEqual(us.rebuild(raw, {}), raw)

    def test_header_rejections(self):
        raw = bytearray(asset_v22())
        for offset, fmt, value in ((8, ">I", 16), (8, ">I", 23), (16, "B", 1), (0, ">I", 5), (40, ">Q", 1), (24, ">q", 1)):
            bad = bytearray(raw)
            struct.pack_into(fmt, bad, offset, value)
            with self.subTest(offset=offset, value=value), self.assertRaises(FormatError):
                us.read_index(io.BytesIO(bytes(bad)))

    def test_type_tree_rejections(self):
        nodes = fx.textasset_tree()
        bad_level = [nodes[0], (3,) + nodes[1][1:]] + nodes[2:]
        with self.assertRaises(FormatError):
            us.read_type_tree(us.Reader(fx.type_tree(bad_level, 22)), 22)
        unknown = us.read_type_tree(us.Reader(struct.pack("<ii", 1, 0) + struct.pack(
            "<HBBIIiiiQ", 1, 0, 0, 0x80000000 | 99999, 0x80000000 | 99999, -1, 0, 0, 0)), 22)
        with self.assertRaises(FormatError):
            us.walk_object(unknown, b"")
        index = us.read_index(io.BytesIO(asset_v22()))
        obj = index.objects[1]
        data = asset_v22()[obj.offset:obj.offset + obj.size]
        with self.assertRaises(FormatError):
            us.walk_object(index.types[obj.type_index].nodes, data + b"\0\0\0\0")
        with self.assertRaises(FormatError):
            us.walk_object(index.types[obj.type_index].nodes, data[:-4])


class TextAssetTests(unittest.TestCase):
    def test_typetree_and_stripped_layouts(self):
        for tree, unity, path_name in ((True, "2022.3.27f1", None), (False, "2022.3.27f1", None),
                                       (False, "5.6.5f1", ""), (True, "5.6.5f1", "")):
            with self.subTest(tree=tree, unity=unity):
                raw = asset_v22(tree=tree, unity=unity, path_name=path_name, version=22 if unity[0] == "2" else 17)
                index = us.read_index(io.BytesIO(raw))
                obj = index.objects[1]
                body = raw[obj.offset:obj.offset + obj.size]
                item = ta.read_textasset(index, obj, body)
                self.assertEqual((item.name, item.script), ("scene_a", SCRIPT))
                for payload in (b"", b"a", "中文变长替换𠀋".encode("utf-8") * 7):
                    patched = ta.patch_textasset(index, obj, body, payload)
                    self.assertEqual(ta.read_textasset(index, obj, patched).script, payload)
                    self.assertEqual(len(patched) % 4, 0)

    def test_stripped_layout_mismatch_rejected(self):
        raw = asset_v22(tree=False, unity="2022.3.27f1", path_name="extra")  # 3 strings on a 2-field engine
        index = us.read_index(io.BytesIO(raw))
        obj = index.objects[1]
        with self.assertRaises(FormatError):
            ta.read_textasset(index, obj, raw[obj.offset:obj.offset + obj.size])

    def test_encoding_guess(self):
        cases = {b"": "empty", b"abc": "ascii", "日本語".encode(): "utf-8", b"\xef\xbb\xbfx": "utf-8-sig",
                 "日本語".encode("utf-16"): "utf-16le", "テキスト".encode("cp932"): "cp932",
                 bytes(range(256)) * 4: "binary"}
        for raw, expected in cases.items():
            self.assertEqual(ta.guess_encoding(raw), expected, raw[:8])
        self.assertGreater(ta.entropy(bytes(range(256)) * 4), 7.9)


class UtageBoundaryTests(unittest.TestCase):
    def test_utage_profile_stays_on_stripped_v20(self):
        from python.engines import unity_utage_extract as workflow
        for raw in (asset_v22(), asset_v22(tree=False)):
            with self.assertRaises(FormatError):
                workflow.inventory(raw, {})


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.bundle = fx.bundle([("CAB-x", asset_v22(), 4), ("CAB-x.resS", b"opaque", 0)],
                                version=8, method=2, block_size=0x80)
        (self.root / "game").mkdir()
        self.source = self.root / "game" / "scenario"
        self.source.write_bytes(self.bundle)

    def tearDown(self):
        self.tmp.cleanup()

    def test_extract_pack_variable_length_text(self):
        report = ta.extract(self.source, self.root / "ws", target="Game_Data/scenario")
        self.assertEqual(report["textassets"], 2)
        ws = self.root / "ws"
        self.assertEqual((ws / "original/textassets/scene_a.txt").read_bytes(), SCRIPT)
        manifest = json.loads((ws / "metadata/manifest.json").read_text(encoding="utf-8"))
        self.assertEqual({m["encoding"] for m in manifest["members"]}, {"utf-8", "utf-8-sig"})
        roundtrip = (ws / "rebuilt/roundtrip/Game_Data/scenario").read_bytes()
        _, _, nodes = fs.read_bundle(roundtrip)
        _, _, old = fs.read_bundle(self.bundle)
        self.assertEqual(nodes, old)
        (ws / "replace/scene_b.txt").write_text("中文替换，更长的内容𠀋", encoding="utf-8")
        result = ta.pack(ws, self.root / "out", text=True)
        self.assertEqual(len(result["changed_objects"]), 1)
        rebuilt = (self.root / "out/files/Game_Data/scenario").read_bytes()
        container = ta.open_container(rebuilt)
        scripts = {item.name: item.script for _, _, _, item in ta.text_assets(container)}
        self.assertEqual(scripts["scene_b"], b"\xef\xbb\xbf" + "中文替换，更长的内容𠀋".encode("utf-8"))
        self.assertEqual(scripts["scene_a"], SCRIPT)
        _, _, new_nodes = fs.read_bundle(rebuilt)
        self.assertEqual(new_nodes["CAB-x.resS"], b"opaque")

    def test_raw_mode_tamper_and_no_overwrite(self):
        ta.extract(self.source, self.root / "ws")
        ws = self.root / "ws"
        with self.assertRaises(FormatError):
            ta.pack(ws, self.root / "out")  # nothing to replace
        (ws / "replace/scene_a.txt").write_bytes(b"\x00\x01raw")
        (self.root / "busy/reports").mkdir(parents=True)
        (self.root / "busy/reports/old.json").write_bytes(b"x")
        with self.assertRaises(FileExistsError):
            ta.pack(ws, self.root / "busy")
        self.assertEqual(sorted(p.name for p in (self.root / "busy").iterdir()), ["reports"])
        result = ta.pack(ws, self.root / "out")
        self.assertFalse(result["text_mode"])
        (ws / "original/textassets/scene_a.txt").write_bytes(b"edited")
        with self.assertRaises(FormatError):
            ta.pack(ws, self.root / "out2")

    def test_cp932_text_mode_rejects_unencodable(self):
        raw = fx.bundle([("CAB-x", asset_v22(script="テキスト本文です".encode("cp932")), 4)], version=8)
        self.source.unlink()
        self.source.write_bytes(raw)
        ta.extract(self.source, self.root / "ws", names=["scene_a"])
        (self.root / "ws/replace/scene_a.txt").write_text("简体中文", encoding="utf-8")
        with self.assertRaises(FormatError):
            ta.pack(self.root / "ws", self.root / "out", text=True)

    def test_selection_without_match(self):
        with self.assertRaises(FormatError):
            ta.extract(self.source, self.root / "ws", names=["absent*"])


class ScanTests(unittest.TestCase):
    def test_stripped_monoscript_layouts(self):
        for tail in (b"", b"\x00", b"\x01\x00\x00\x00"):
            raw = fx.serialized([(1, 115, fx.monoscript("A", "Cls", "Ns") + tail)], version=17, unity="5.6.5f1")
            index = us.read_index(io.BytesIO(raw))
            obj = index.objects[0]
            self.assertEqual(unity_scan.mono_script(index, obj, raw[obj.offset:obj.offset + obj.size]), ("Ns", "Cls"))
        raw = fx.serialized([(1, 115, fx.monoscript("A", "Cls") + b"\x00\x00")], version=17, unity="5.6.5f1")
        index = us.read_index(io.BytesIO(raw))
        obj = index.objects[0]
        self.assertIsNone(unity_scan.mono_script(index, obj, raw[obj.offset:obj.offset + obj.size]))

    def test_scan_reports_containers_textassets_and_scripts(self):
        with tempfile.TemporaryDirectory() as tmp:
            game = Path(tmp) / "game"
            data = game / "Demo_Data"
            (data / "StreamingAssets").mkdir(parents=True)
            (data / "il2cpp_data/Metadata").mkdir(parents=True)
            (data / "il2cpp_data/Metadata/global-metadata.dat").write_bytes(b"\xaf\x1b\xb1\xfa" + bytes(60))
            (data / "StreamingAssets/lines.csv").write_text("id,text\n1,こんにちは\n", encoding="utf-8")
            scripts = fx.serialized([(1, 115, fx.monoscript("Talk", "TalkData", "Game"))], version=22, unity="2021.3.5f1")
            (data / "globalgamemanagers.assets").write_bytes(scripts)
            level = fx.serialized([(5, 114, fx.behaviour(1, 1, "talk")), (6, 49, fx.textasset("story", SCRIPT))],
                                  version=22, unity="2021.3.5f1", externals=("globalgamemanagers.assets",))
            (data / "data.unity3d").write_bytes(fx.bundle([("level0", level, 4)], version=7, engine="2021.3.5f1"))
            result = unity_scan.scan(game)
            self.assertFalse(result["partial"])
            self.assertEqual(result["il2cpp_metadata"][0]["parsed"], False)
            self.assertEqual(result["streaming_assets"][0]["encoding"], "utf-8")
            bundle = next(c for c in result["containers"] if c["kind"] == "unityfs")
            node = bundle["nodes"][0]
            self.assertEqual(node["textassets"][0]["name"], "story")
            self.assertEqual(node["monobehaviour_classes"], {"Game.TalkData": 1})
            self.assertEqual(result["summary"]["text_textassets"], 1)
            limited = unity_scan.scan(game, max_files=1)
            self.assertTrue(limited["partial"])
            tight = unity_scan.scan(game, max_bytes=8)
            self.assertTrue(tight["partial"])


if __name__ == "__main__":
    unittest.main()
