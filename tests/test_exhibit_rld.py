"""Synthetic ExHibit v3 fixtures: no commercial scripts/keys or game records."""
import copy
import json
from pathlib import Path
import struct
import tempfile
import unittest

from python.engines.exhibit import xor_rld
from python.engines.exhibit_rld import crypt, export_rld, mt_keys, parse, rebuild_rld
from python.engines.exhibit_keys import bitmap_bits, ini_checksum, scenario_seed, recover_def_seed
from python.engines.exhibit_extract import extract, rebuild
from python.common.contract import dump_rows


def op(code, strings=(), integers=(), flags=0):
    return (struct.pack("<HBB", code, len(integers), flags | len(strings))
            + b"".join(struct.pack("<I", x) for x in integers)
            + b"".join((s if isinstance(s, bytes) else s.encode("cp932")) + b"\0" for s in strings))


def script(*ops, tag=b"a,b,c"):
    return b"\0DLR" + struct.pack("<4I", 3, 272, len(ops), len(tag.split(b",")) if tag else 0) + tag.ljust(256, b"\0") + b"".join(ops)


def choice():
    return "\t".join(["1010", "0", "0", "1", "2"] + ["-1"] * 7 + ["-12345"] * 2
                     + ["Yes", "No"] + ["*"] * 9 + ["-1", "-2", "0", "-12345", ""])


def dib(value=0x12345678, width=33, height=34, bpp=24):
    stride = ((width * bpp + 31) // 32) * 4
    data = bytearray(40 + height * stride)
    struct.pack_into("<IiiHHII", data, 0, 40, width, height, 1, bpp, 0, height * stride)
    for i in range(32):
        data[40 + (height - 32 + i) * stride + 31 * (bpp // 8)] = (value >> (31 - i)) & 1
    return bytes(data)


def pe(blob=None, code=b""):
    blob = dib() if blob is None else blob
    resource = bytearray(88)
    for at in (0, 24, 48):
        struct.pack_into("<H", resource, at + 14, 1)
    struct.pack_into("<II", resource, 16, 2, 0x80000018)
    struct.pack_into("<II", resource, 40, 152, 0x80000030)
    struct.pack_into("<II", resource, 64, 0, 72)
    struct.pack_into("<II", resource, 72, 0x1000 + 88, len(blob))
    resource += blob
    data = bytearray(512)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x80)
    data[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<HH", data, 0x84, 0x14C, 1)
    struct.pack_into("<H", data, 0x94, 224)
    opt = 0x98
    struct.pack_into("<H", data, opt, 0x10B)
    struct.pack_into("<I", data, opt + 92, 16)
    struct.pack_into("<II", data, opt + 112, 0x1000, len(resource))
    sec = opt + 224
    struct.pack_into("<III", data, sec + 12, 0x1000, len(resource) + len(code), 512)
    struct.pack_into("<I", data, sec + 36, 0x60000040)
    return bytes(data + resource + code)


class CryptoTests(unittest.TestCase):
    def test_old_mt_known_vector(self):
        # Legacy MT sgenrand(4357), unlike the modern init_genrand sequence.
        self.assertEqual(mt_keys(4357)[:5], (2867219139, 1585203162, 3113124129, 2953900839, 2463794868))
        for seed in (-1, 0x100000000, True):
            with self.assertRaises(ValueError):
                mt_keys(seed)

    def test_runtime_cutoff_and_partial_dword(self):
        seed = 4357
        for length in (16, 19, 20, 0xFFCD, 0xFFD0, 0xFFD7, 0x10010):
            raw = b"\0DLR" + bytes(length - 4)
            encrypted = crypt(raw, seed)
            end = min(length // 4 * 4, 0xFFD0)
            self.assertEqual(encrypted[:16], raw[:16])
            self.assertEqual(encrypted[end:], raw[end:])
            if end > 16:
                at = end - 4
                self.assertEqual(struct.unpack_from("<I", encrypted, at)[0], seed ^ mt_keys(seed)[((at - 16) // 4) & 255])
            self.assertEqual(crypt(encrypted, seed), raw)
            self.assertEqual(crypt(raw, 0), raw)
        self.assertNotEqual(crypt(raw, seed), xor_rld(raw, seed, mt_keys(seed)))

    def test_growth_crosses_encryption_boundary(self):
        for size in (0xFFCC - 284, 0xFFD0 - 284, 0xFFD4 - 284):
            raw = crypt(script(op(28, ("N", "A" * size))), 17)
            rows, manifest = export_rld(raw, 17)
            rows[0]["message"] += "BCDEF"
            rebuilt = rebuild_rld(raw, 17, rows, manifest)
            self.assertEqual(len(rebuilt), len(raw) + 5)
            self.assertEqual(parse(crypt(rebuilt, 17)).ops[0].strings[1], rows[0]["message"])


class RldTests(unittest.TestCase):
    def setUp(self):
        self.definitions = crypt(script(op(48, ("7,a,b,Alice",)), tag=b""), 19)
        self.plain = script(op(28, ("*", "Hello\nworld", "opaque"), (7, 3), 0x60),
                            op(28, ("*", "Narration"), (1,), 0x20),
                            op(28, ("Bob", "Next")), op(28, ("$noname$", "Unvoiced")),
                            op(21, (choice(),), flags=0x60),
                            op(0xFACE, (b"\x87\x90",), (2, 0xFFFFFFFF), 0xA0), op(17, ("next,*,0",)))
        self.raw = crypt(self.plain, 17)
        self.kw = {"definitions": self.definitions, "definition_seed": 19}
        self.rows, self.manifest = export_rld(self.raw, 17, **self.kw)

    def test_complete_identity_aliases_unknown_opcode_last_command(self):
        parsed = parse(self.plain)
        self.assertEqual(len(parsed.ops), 7)
        self.assertEqual(parsed.ops[0].opcode, 28)
        self.assertEqual(parsed.ops[-1].opcode, 17)
        self.assertEqual(parsed.ops[-2].opcode, 0xFACE)
        self.assertEqual(rebuild_rld(self.raw, 17, self.rows, self.manifest, **self.kw), self.raw)
        self.assertEqual(list(json.loads(dump_rows(self.rows))[0]), ["name", "message"])

    def test_names_and_choice_edits_preserve_opaque_operands(self):
        self.assertEqual(self.rows[0]["name"], "Alice")
        self.assertNotIn("name", self.rows[1])
        self.assertNotIn("name", self.rows[3])
        rows = copy.deepcopy(self.rows)
        rows[0]["message"] = "Longer\nmessage"
        rows[2]["name"] = "Ben"
        rows[4]["message"], rows[5]["message"] = "Accept", "Decline"
        new = parse(crypt(rebuild_rld(self.raw, 17, rows, self.manifest, **self.kw), 17))
        original = parse(self.plain)
        self.assertEqual(new.ops[0].strings, ("*", "Longer\nmessage", "opaque"))
        self.assertEqual(new.ops[2].strings[0], "Ben")
        self.assertEqual(new.ops[4].strings[0].split("\t")[:14], choice().split("\t")[:14])
        self.assertEqual(new.ops[4].strings[0].split("\t")[16:], choice().split("\t")[16:])
        self.assertEqual(new.plain[slice(*new.spans[5][0])], original.plain[slice(*original.spans[5][0])])

    def test_translation_rejections(self):
        for index, field, value in ((0, "name", "Other"), (0, "message", "lost newline"),
                                    (2, "name", "*"), (2, "message", "bad\0"),
                                    (2, "message", "<unknown>"), (4, "message", "bad\tchoice")):
            rows = copy.deepcopy(self.rows)
            rows[index][field] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                rebuild_rld(self.raw, 17, rows, self.manifest, **self.kw)
        manifest = copy.deepcopy(self.manifest)
        manifest["records"][0]["locator"]["op"] = 5
        with self.assertRaises(ValueError):
            rebuild_rld(self.raw, 17, self.rows, manifest, **self.kw)
        with self.assertRaises(ValueError):
            rebuild_rld(self.raw, 17, self.rows[:-1], self.manifest, **self.kw)

    def test_wrong_seed_header_count_and_truncation(self):
        bad_header = bytearray(self.plain)
        struct.pack_into("<I", bad_header, 8, 276)
        bad_count = bytearray(self.plain)
        struct.pack_into("<I", bad_count, 12, 6)
        bad_imports = bytearray(self.plain)
        struct.pack_into("<I", bad_imports, 16, 1)
        for raw in (bad_header, bad_count, bad_imports, self.plain[:-1], self.plain + b"\0", crypt(self.raw, 18)):
            with self.assertRaises(ValueError):
                parse(raw)

    def test_unsupported_choice_fails_explicitly(self):
        for value in ("not\t1010", choice().replace("1010", "1011", 1), choice().replace("\t2\t", "\t3\t", 1)):
            with self.assertRaises(ValueError):
                export_rld(script(op(21, (value,), flags=0x60)), 0)


class KeysTests(unittest.TestCase):
    def test_bitmap_padding_order_and_ini_branches(self):
        for bpp in (24, 32):
            self.assertEqual(bitmap_bits(dib(bpp=bpp)), 0x12345678)
        self.assertEqual(ini_checksum(b"[setting]\nCLASS=abcd\nSYSVER=1\nTITLE=ignored\n"), 0x64636261)
        self.assertEqual(ini_checksum(b"[setting]\nCLASS=abcd\nTITLE=EF\n"), 0x6463A8A6)
        self.assertEqual(ini_checksum(b"[setting]\nCLASS=A\nSYSVER=1\nFLAGS=4\nGUID=B\nSVDATA=C\n"), 0x43423441)
        self.assertEqual(ini_checksum(b"[SETTING]\nCLASS=\"abcd\"\nSYSVER=1\nFLAGS=0x100\n"), 0x64636261)
        seed, _ = scenario_seed(pe(), b"[setting]\nCLASS=abcd\nSYSVER=1\n")
        self.assertEqual(seed, 0x12345678 ^ 0x64636261)

    def test_static_def_seed_validation(self):
        seed = 0x12345678
        resident = pe(code=b"\xc7\x83\x20\x11\0\0" + struct.pack("<I", seed))
        raw = crypt(script(op(99, ("opaque",)), tag=b""), seed)
        found, info = recover_def_seed(resident, raw)
        self.assertEqual(found, seed)
        self.assertGreaterEqual(info["candidates"], 2)
        with self.assertRaises(ValueError):
            recover_def_seed(pe(), raw)

    def test_malformed_pe_bitmap_ini(self):
        for data in (b"", pe()[:300]):
            with self.assertRaises(ValueError):
                scenario_seed(data, b"[setting]\n")
        for data in (dib()[:100], dib(height=32)[:40], b"\0" * 40):
            with self.assertRaises(ValueError):
                bitmap_bits(data)
        with self.assertRaises(ValueError):
            ini_checksum(b"[setting]\nFLAGS=bad\n")


class WorkspaceTests(unittest.TestCase):
    def test_workspace_jis_rebuild_and_source_guards(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / "game"
            (game / "rld").mkdir(parents=True)
            (game / "engine.exe").write_bytes(pe())
            raw = crypt(script(op(28, ("$noname$", "Hello")), op(21, (choice(),), flags=0x60)), 23)
            (game / "rld/start.rld").write_bytes(raw)
            (game / "rld/system.rld").write_bytes(crypt(script(op(0x1234), tag=b""), 23))
            work = root / "extracted"
            info = extract(game, work, exe=game / "engine.exe", seed=23, smoke_test=True)
            self.assertEqual((info["json_files"], info["rows"], info["identity_verified"]), (1, 3, 2))
            self.assertEqual(len(list((work / "gt_input").glob("*.json"))), 1)
            self.assertEqual((work / "rebuilt/roundtrip/rld/start.rld").read_bytes(), raw)
            self.assertEqual(rebuild(work, root / "empty")["changed_members"], [])
            with self.assertRaises(FileExistsError):
                extract(game, work, seed=23)
            rows = json.loads((work / "gt_input/start.json").read_bytes())
            rows[0]["message"] = "这是中文显示测试。"
            rows[1]["message"] = "选择这里"
            (work / "gt_output/start.json").write_bytes(dump_rows(rows))
            result = rebuild(work, root / "packed")
            self.assertEqual(result["changed_members"], ["start.rld"])
            self.assertGreater(result["jis_substitution"]["used_count"], 0)
            config = json.loads((root / "packed/uif_config.json").read_bytes())["character_substitution"]
            table = str.maketrans(config["source_characters"], config["target_characters"])
            saved = (root / "packed/rld/start.rld").read_bytes()
            decoded = parse(crypt(saved, 23))
            self.assertEqual(decoded.ops[0].strings[1].translate(table), rows[0]["message"])
            self.assertTrue((root / "packed/winmm.dll").is_file())
            self.assertEqual((game / "rld/start.rld").read_bytes(), raw)
            (work / "original/encrypted/start.rld").write_bytes(raw + b"\0")
            with self.assertRaises(ValueError):
                rebuild(work, root / "bad")
            self.assertFalse((root / "bad").exists())

    def test_reject_unknown_translation_and_unsafe_manifest_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "game/rld").mkdir(parents=True)
            (root / "game/rld/start.rld").write_bytes(script(op(28, ("N", "text"))))
            work = root / "work"
            extract(root / "game", work)
            (work / "gt_output/stray.json").write_text("[]")
            with self.assertRaises(ValueError):
                rebuild(work, root / "bad")
            report = json.loads((work / "reports/extraction.json").read_bytes())
            report["members"][0]["name"] = "../start.rld"
            (work / "reports/extraction.json").write_text(json.dumps(report))
            with self.assertRaises(ValueError):
                rebuild(work, root / "bad")

    def test_jis_collision_does_not_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "game/rld").mkdir(parents=True)
            (root / "game/rld/start.rld").write_bytes(script(op(28, ("N", "text")), op(191, ("這",))))
            work = root / "work"
            extract(root / "game", work)
            (work / "gt_output/start.json").write_bytes(dump_rows([{"name": "N", "message": "这"}]))
            with self.assertRaisesRegex(ValueError, "JIS proxy"):
                rebuild(work, root / "bad")
            self.assertFalse((root / "bad").exists())


if __name__ == "__main__":
    unittest.main()
