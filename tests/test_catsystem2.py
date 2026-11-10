"""Synthetic CatSystem2 INT/CST tests; no commercial assets or executable loading."""
from io import BytesIO
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from python.engines import catsystem2
from python.archives import catsystem2_int
from python.engines.catsystem2_extract import extract_game


def make_cst(items, compressed=True):
    prefix = b"screen!!"
    pool = bytearray()
    offsets = []
    for kind, text in items:
        offsets.append(len(pool))
        pool.extend(bytes((1, kind)) + text.encode("cp932") + b"\0")
    table = b"".join(struct.pack("<I", offset) for offset in offsets)
    raw = struct.pack("<IIII", len(prefix + table + pool), 1, 8, 8 + len(table))
    raw += prefix + table + pool
    packed = zlib.compress(raw) if compressed else raw
    return b"CatScene" + struct.pack("<II", len(packed) if compressed else 0, len(raw)) + packed


def encrypt_blocks(data, cipher):
    out = bytearray(data)
    for offset in range(0, len(out) // 8 * 8, 8):
        left, right = struct.unpack_from("<II", out, offset)
        left, right = cipher.encrypt(left, right)
        struct.pack_into("<II", out, offset, left, right)
    return bytes(out)


def encrypt_name(name, key):
    target = name.encode("cp932")
    alphabet = b"zyxwvutsrqponmlkjihgfedcbaZYXWVUTSRQPONMLKJIHGFEDCBA"
    initial = ((key >> 24) + (key >> 16) + (key >> 8) + key) & 0xFF
    raw = bytearray()
    for position, expected in enumerate(target):
        if not (65 <= expected <= 90 or 97 <= expected <= 122):
            raw.append(expected)
            continue
        found = None
        step = (initial + position) % 0x34
        for candidate in alphabet:
            index = alphabet.index(candidate) - step
            if index < 0:
                index += 0x34
            decoded = alphabet[0x33 - index]
            if decoded == expected:
                found = candidate
                break
        if found is None:
            raise AssertionError(f"cannot encrypt name byte at {position}")
        raw.append(found)
    return bytes(raw).ljust(0x40, b"\0")


def make_encrypted_int(member, name="scene.cst", password="test-pass", seed=0x12345678):
    twister = catsystem2_int.MersenneTwister(seed)
    cipher = catsystem2_int.Blowfish(struct.pack("<I", twister.rand()))
    password_key = catsystem2_int.encode_passphrase(password)
    twister.s_rand((password_key + 1) & 0xFFFFFFFF)
    encrypted_name = encrypt_name(name, twister.rand())
    member_offset = 0x50 + 0x48
    encrypted_offset, encrypted_size = cipher.encrypt(member_offset, len(member))
    record = encrypted_name + struct.pack("<II", (encrypted_offset - 1) & 0xFFFFFFFF,
                                          encrypted_size)
    header = bytearray(0x50)
    struct.pack_into("<4sI", header, 0, b"KIF\0", 2)
    header[8:8 + len(b"__key__.dat\0")] = b"__key__.dat\0"
    struct.pack_into("<I", header, 0x4C, seed)
    return bytes(header) + record + encrypt_blocks(member, cipher)


def make_plain_int(name, member):
    encoded = name.encode("cp932")
    if len(encoded) >= 0x20:
        raise ValueError("test filename is too long")
    offset = 8 + 0x20 + 8
    return (struct.pack("<4sI", b"KIF\0", 1) + encoded.ljust(0x20, b"\0")
            + struct.pack("<II", offset, len(member)) + member)


def make_password_pe(password, pe32_plus=False):
    code = (password.encode("cp932") + b"\0").ljust(16, b"\0")
    code = encrypt_blocks(code, catsystem2_int.Blowfish(b"windmill"))
    pe_offset = 0x80
    optional_size = 0xF0 if pe32_plus else 0xE0
    optional = pe_offset + 4 + 20
    section = optional + optional_size
    resource_raw = 0x200
    resource_rva = 0x1000
    data = bytearray(0x400)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, pe_offset)
    data[pe_offset:pe_offset + 4] = b"PE\0\0"
    struct.pack_into("<H", data, pe_offset + 4 + 2, 1)
    struct.pack_into("<H", data, pe_offset + 4 + 16, optional_size)
    struct.pack_into("<H", data, optional, 0x20B if pe32_plus else 0x10B)
    directory_base = optional + (0x70 if pe32_plus else 0x60)
    struct.pack_into("<II", data, directory_base + 2 * 8, resource_rva, 0x100)
    struct.pack_into("<IIII", data, section + 8, 0x200, resource_rva, 0x200, resource_raw)

    def directory(relative, named, ids):
        struct.pack_into("<IIHHHH", data, resource_raw + relative, 0, 0, 0, 0, named, ids)

    def resource_name(relative, value):
        encoded = value.encode("utf-16le")
        struct.pack_into("<H", data, resource_raw + relative, len(value))
        data[resource_raw + relative + 2:resource_raw + relative + 2 + len(encoded)] = encoded

    directory(0x00, 1, 0)
    struct.pack_into("<II", data, resource_raw + 0x10, 0x80000080, 0x80000020)
    directory(0x20, 1, 0)
    struct.pack_into("<II", data, resource_raw + 0x30, 0x800000A0, 0x80000040)
    directory(0x40, 0, 1)
    struct.pack_into("<II", data, resource_raw + 0x50, 0x411, 0x60)
    struct.pack_into("<IIII", data, resource_raw + 0x60, resource_rva + 0xC0,
                     len(code), 0, 0)
    resource_name(0x80, "V_CODE2")
    resource_name(0xA0, "DATA")
    data[resource_raw + 0xC0:resource_raw + 0xC0 + len(code)] = code
    return bytes(data)


class CatSystemIntTests(unittest.TestCase):
    def test_known_crypto_vectors(self):
        self.assertEqual(catsystem2_int.Blowfish(bytes(8)).encrypt(0, 0),
                         (0x4EF99745, 0x6198DD78))
        self.assertEqual(catsystem2_int.encode_passphrase("test-pass"), 0xCEA49656)
        twister = catsystem2_int.MersenneTwister(0x12345678)
        self.assertEqual([twister.rand() for _ in range(3)],
                         [0x7899B975, 0xBD008E30, 0x02285C9A])
        with self.assertRaises(ValueError):
            catsystem2_int.encode_passphrase(b"not-text")

    def test_encrypted_index_stream_path_and_password_optional(self):
        member = make_cst([(0x20, "hello")])
        data = make_encrypted_int(member)
        probe = catsystem2_int.probe_int(data)
        self.assertTrue(probe.encrypted)
        self.assertEqual(probe.entry_count, 2)

        anonymous = catsystem2_int.read_int(data)
        self.assertFalse(anonymous.names_recovered)
        self.assertFalse(anonymous.entries[0].name_known)
        self.assertEqual(catsystem2_int.probe_member(
            data, anonymous.entries[0], anonymous.cipher, max_bytes=8), b"CatScene")
        self.assertEqual(catsystem2_int.read_member(
            data, anonymous.entries[0], anonymous.cipher), member)

        stream = BytesIO(data)
        named = catsystem2_int.read_int(stream, password="test-pass")
        self.assertFalse(stream.closed)
        self.assertEqual(named.entries[0].name, "scene.cst")
        self.assertEqual(named.entries[0].offset, 0x98)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "scene.int"
            path.write_bytes(data)
            from_path = catsystem2_int.read_int(path, password="test-pass")
            self.assertEqual(from_path.entries, named.entries)
            self.assertEqual(catsystem2_int.read_member(
                path, from_path.entries[0], from_path.cipher), member)

    def test_plain_index_and_limits(self):
        member = make_cst([(0x20, "plain")], compressed=False)
        data = make_plain_int("plain.cst", member)
        archive = catsystem2_int.read_int(data)
        self.assertFalse(archive.encrypted)
        self.assertEqual(archive.entries[0].name, "plain.cst")
        self.assertEqual(catsystem2_int.read_member(data, archive.entries[0]), member)
        with self.assertRaises(ValueError):
            catsystem2_int.probe_int(data, max_entries=0)
        with self.assertRaises(ValueError):
            catsystem2_int.read_member(data, archive.entries[0], max_member=1)

    def test_password_from_pe32_and_pe32_plus_language_leaf(self):
        for pe32_plus in (False, True):
            image = make_password_pe("秘密pass", pe32_plus)
            self.assertEqual(catsystem2_int.extract_exe_password(image), "秘密pass")
            with tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / "cs2.exe"
                path.write_bytes(image)
                self.assertEqual(catsystem2_int.extract_exe_password(path), "秘密pass")


class CatSystemDialogueTests(unittest.TestCase):
    def test_export_dynamic_names_controls_and_choices(self):
        data = make_cst([
            (0x21, "$str20"),
            (0x20, r"first\nline\@"),
            (0x21, "Alice"),
            (0x30, "1 select choice"),
            (0x20, "hello"),
            (0x21, "Unused"),
            (0x21, "Bob"),
            (0x20, "bye"),
            (0x21, "Tail"),
        ])
        exported = catsystem2.export_cst(data)
        self.assertEqual(exported.rows, (
            {"name": "$str20", "message": "first\nline\\@"},
            {"message": "choice"},
            {"name": "Alice", "message": "hello"},
            {"name": "Bob", "message": "bye"},
        ))
        self.assertEqual(exported.name_policies, ("context", "absent", "writable", "writable"))
        self.assertEqual(exported.excluded_choices, ())
        self.assertEqual(exported.locators[1]['choice_span'], (9, 15))
        self.assertEqual(exported.orphan_names, (5, 8))
        self.assertEqual(exported.name_command_crossings, ((2, (3,)),))
        self.assertNotIn("\n", exported.protected_tokens[0])
        self.assertIn(r"\@", exported.protected_tokens[0])
        self.assertEqual(catsystem2.patch_dialogue(data, exported,
                                                   list(exported.rows)), data)
        shorter = [dict(row) for row in exported.rows]
        shorter[0] = dict(shorter[0], message=r"single line\@")
        self.assertEqual(catsystem2.export_cst(
            catsystem2.patch_dialogue(data, exported, shorter)).rows[0]["message"],
            r"single line\@")
        longer = [dict(row) for row in exported.rows]
        longer[0] = dict(longer[0], message="three\nlines\nhere\\@")
        with self.assertRaises(ValueError):
            catsystem2.patch_dialogue(data, exported, longer)

    def test_choice_caption_growth_preserves_prefix_and_nontext_records(self):
        for compressed in (True, False):
            data = make_cst([(0x30, '1\tselect  Old'), (0x30, 'jump label'),
                             (0x20, 'Body')], compressed=compressed)
            exported = catsystem2.export_cst(data)
            translated = [{'message': '更長的選択'}, {'message': '更長的本文'}]
            result = catsystem2.patch_dialogue(data, exported, translated)
            before, after = catsystem2.read_cst(data), catsystem2.read_cst(result)
            self.assertEqual(after.records[0].text, '1\tselect  更長的選択')
            self.assertEqual(after.records[1], before.records[1])
            self.assertEqual(after.payload[before.pool_offset:len(before.payload)],
                             before.payload[before.pool_offset:])
            self.assertEqual(catsystem2.export_cst(result).rows, tuple(translated))
            for text in ('', ' leading', 'bad\nline', 'bad\0text'):
                with self.assertRaises(ValueError):
                    catsystem2.patch_dialogue(data, exported, [{'message': text}, exported.rows[1]])
            with self.assertRaises(ValueError):
                catsystem2.patch_cst(data, {1: 'wrong command'})
            with self.assertRaises(ValueError):
                catsystem2.patch_dialogue(result, exported, translated)

    def test_patch_dialogue_and_reject_context_or_token_changes(self):
        data = make_cst([(0x21, "$str20"), (0x20, r"old\@"),
                         (0x21, "Alice"), (0x20, "hello")])
        exported = catsystem2.export_cst(data)
        translated = [dict(row) for row in exported.rows]
        translated[0]["message"] = r"new\@"
        translated[1] = {"name": "Alicia", "message": "world"}
        patched = catsystem2.patch_dialogue(data, exported, translated)
        records = catsystem2.read_cst(patched).records
        self.assertEqual(records[1].text, r"new\@")
        self.assertEqual(records[2].text, "Alicia")
        self.assertEqual(records[3].text, "world")
        bad_name = [dict(row) for row in exported.rows]
        bad_name[0]["name"] = "player"
        with self.assertRaises(ValueError):
            catsystem2.patch_dialogue(data, exported, bad_name)
        bad_token = [dict(row) for row in exported.rows]
        bad_token[0]["message"] = "lost"
        with self.assertRaises(ValueError):
            catsystem2.patch_dialogue(data, exported, bad_token)

    def test_choice_controls_remain_raw_and_protected(self):
        data = make_cst([(0x30, r'1 select old\ntext\@')])
        exported = catsystem2.export_cst(data)
        self.assertEqual(exported.rows, ({'message': r'old\ntext\@'},))
        self.assertEqual(catsystem2.patch_dialogue(data, exported, exported.rows), data)
        translated = [{'message': r'new\ncaption\@'}]
        result = catsystem2.patch_dialogue(data, exported, translated)
        self.assertEqual(catsystem2.read_cst(result).records[0].text, r'1 select new\ncaption\@')
        with self.assertRaises(ValueError):
            catsystem2.patch_dialogue(data, exported, [{'message': 'lost controls'}])

    def test_pipeline_uses_update_overlay_and_writes_contract(self):
        base = make_plain_int("scene.cst", make_cst([(0x20, "base")]))
        update = make_plain_int("scene.cst", make_cst([(0x20, "update")]))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "scene.int").write_bytes(base)
            (root / "update01.int").write_bytes(update)
            (root / "broken.int").write_bytes(b"not-kif")
            destination = root / f"{root.name}_extract"
            destination.mkdir()
            summary = extract_game(root)
            output = Path(summary["output"])
            self.assertEqual(output, destination)
            self.assertEqual(summary["overridden_cst_members"], 1)
            self.assertEqual(summary["scripts_exported"], 1)
            self.assertEqual(summary["parse_failures"], 1)
            self.assertEqual(summary["identity_roundtrip"]["status"], "complete")
            rows = json.loads((output / "gt_input" / "scene.json").read_text("utf-8"))
            self.assertEqual(rows, [{"message": "update"}])
            self.assertTrue((output / "gt_output").is_dir())
            on_disk_summary = json.loads((output / "reports" / "summary.json").read_text("utf-8"))
            self.assertEqual(on_disk_summary, summary)
            manifest = json.loads(next((output / "metadata").rglob("*.json")).read_text("utf-8"))
            self.assertEqual(manifest["translation"]["count"], 1)
            self.assertEqual(manifest["records"][0]["locator"]["message_record"], 0)
            self.assertTrue((output / manifest["sources"][0]["path"]).is_file())

    def test_choice_only_script_is_exported_with_caption_locator(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'scene.int').write_bytes(make_plain_int('choice.cst', make_cst([
                (0x30, '1 select Option'), (0x30, 'jump label')])))
            summary = extract_game(root)
            output = Path(summary['output'])
            self.assertEqual(summary['scripts_exported'], 1)
            rows = json.loads((output / 'gt_input' / 'choice.json').read_text('utf-8'))
            self.assertEqual(rows, [{'message': 'Option'}])
            manifest = json.loads(next((output / 'metadata').rglob('*.json')).read_text('utf-8'))
            self.assertEqual(manifest['records'][0]['locator']['choice_span'], [9, 15])
            self.assertEqual(manifest['translation']['count'], 1)

    def test_pipeline_accepts_relative_root_and_encrypted_archive(self):
        member = make_cst([(0x20, "encrypted")])
        archive = make_encrypted_int(member)
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            root = Path(temporary)
            relative_root = root.relative_to(Path.cwd())
            (root / "scene.int").write_bytes(archive)
            (root / "cs2.exe").write_bytes(make_password_pe("test-pass"))
            (root / "result").mkdir()
            summary = extract_game(relative_root, output="result")
            output = root / "result"
            self.assertEqual(Path(summary["output"]), output)
            self.assertTrue(summary["password_recovered"])
            rows = json.loads((output / "gt_input" / "scene.json").read_text("utf-8"))
            self.assertEqual(rows, [{"message": "encrypted"}])


class CatSystemIntWriterTests(unittest.TestCase):
    def test_encrypted_writer_matches_independent_fixture_and_reads_back(self):
        member = make_cst([(0x20, "hello")])
        compact = catsystem2_int.write_int([("scene.cst", member)], encrypted=True,
                                           password="test-pass", seed=0x12345678, key_slot=0,
                                           record_prefix=False)
        self.assertEqual(compact, make_encrypted_int(member))
        members = [("アbc.cst", member), ("Zz_name.cst", b"short"), ("empty.cst", b"")]
        data = catsystem2_int.write_int(members, encrypted=True, password="test-pass")
        archive = catsystem2_int.read_int(data, password="test-pass")
        self.assertEqual([e.name for e in archive.entries], [m[0] for m in members])
        for entry, (_, payload) in zip(archive.entries, members):
            self.assertEqual(catsystem2_int.read_member(data, entry, archive.cipher), payload)
        layout = catsystem2_int.detect_int_layout(data, archive)
        self.assertTrue(layout.record_prefix)
        self.assertEqual((layout.seed, layout.key_slot), (archive.seed, archive.key_slot))
        again = catsystem2_int.write_int(members, encrypted=True, password="test-pass",
                                         seed=layout.seed, key_slot=layout.key_slot)
        self.assertEqual(again, data)
        self.assertEqual(catsystem2_int.read_int(data).entries[0].name_known, False)

    def test_plain_writer_name_sizes(self):
        member = make_cst([(0x20, "plain")], compressed=False)
        self.assertEqual(catsystem2_int.write_int([("plain.cst", member)], encrypted=False,
                                                  name_size=0x20),
                         make_plain_int("plain.cst", member))
        long_name = "n" * 40 + ".cst"
        data = catsystem2_int.write_int([(long_name, member), ("b.cst", b"x")], encrypted=False)
        archive = catsystem2_int.read_int(data)
        self.assertEqual(archive.name_size, 0x40)
        self.assertEqual([e.name for e in archive.entries], [long_name, "b.cst"])
        self.assertFalse(catsystem2_int.detect_int_layout(data, archive).record_prefix)

    def test_writer_rejects_bad_input(self):
        ok = [("a.cst", b"x")]
        bad_calls = [
            dict(members=[("a.cst", b"x"), ("A.CST", b"y")], encrypted=False),
            dict(members=[("n" * 64, b"x")], encrypted=True, password="p"),
            dict(members=[("n" * 32, b"x")], encrypted=False, name_size=0x20),
            dict(members=[("汉.cst", b"x")], encrypted=False),
            dict(members=[("__key__.dat", b"x")], encrypted=True, password="p"),
            dict(members=[("dir/a.cst", b"x")], encrypted=False),
            dict(members=[], encrypted=False),
            dict(members=[("a.cst", "text")], encrypted=False),
            dict(members=ok, encrypted=True),
            dict(members=ok, encrypted=True, password="p", key=1),
            dict(members=ok, encrypted=True, key=1 << 32),
            dict(members=ok, encrypted=True, key=1, seed=-1),
            dict(members=ok, encrypted=False, seed=1),
            dict(members=ok, encrypted=False, record_prefix=True),
            dict(members=ok, encrypted=False, name_size=0x30),
            dict(members=[("a.cst", b"12345678")], encrypted=False, max_total=4),
            dict(members=[("a.cst", b"x"), ("b.cst", b"y")], encrypted=False, max_members=1),
        ]
        for call in bad_calls:
            with self.subTest(call=call), self.assertRaises(ValueError):
                catsystem2_int.write_int(call.pop("members"), **call)
        data = catsystem2_int.write_int(ok, encrypted=True, key=7)
        with self.assertRaises(ValueError):
            catsystem2_int.verify_int(data, [("a.cst", b"y")], key=7)
        with self.assertRaises(ValueError):
            catsystem2_int.verify_int(data, ok, key=8)


class CatSystemTextRuleTests(unittest.TestCase):
    def test_display_name_after_at_is_the_only_writable_part(self):
        data = make_cst([(0x21, "結灯＠少女"), (0x20, "a"), (0x21, "＠x"), (0x20, "b"),
                         (0x21, "ID＠"), (0x20, "c")])
        exported = catsystem2.export_cst(data)
        self.assertEqual(exported.rows[0], {"name": "少女", "message": "a"})
        self.assertEqual(exported.locators[0]["name_prefix"], "結灯＠")
        self.assertEqual(exported.name_policies, ("writable", "writable", "context"))
        self.assertEqual(exported.rows[1]["name"], "＠x")
        rows = [dict(r) for r in exported.rows]
        rows[0]["name"] = "少年"
        patched = catsystem2.patch_dialogue(data, exported, rows)
        self.assertEqual(catsystem2.read_cst(patched).records[0].text, "結灯＠少年")
        for name in ("結灯＠少年", ""):
            bad = [dict(r) for r in exported.rows]
            bad[0]["name"] = name
            with self.subTest(name=name), self.assertRaises(ValueError):
                catsystem2.patch_dialogue(data, exported, bad)
        bad = [dict(r) for r in exported.rows]
        bad[2]["name"] = "changed"
        with self.assertRaises(ValueError):
            catsystem2.patch_dialogue(data, exported, bad)

    def test_leading_continuation_newline_is_kept(self):
        data = make_cst([(0x20, r"\nnext line"), (0x20, "first\\nsecond")])
        exported = catsystem2.export_cst(data)
        self.assertEqual(exported.rows[0]["message"], "\nnext line")
        ok = [{"message": "\n下一行"}, {"message": "一行"}]
        catsystem2.patch_dialogue(data, exported, ok)
        for rows in ([{"message": "下一行"}, ok[1]], [ok[0], {"message": "\n一行"}]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                catsystem2.patch_dialogue(data, exported, rows)

    def test_ruby_brackets_must_stay_well_formed(self):
        data = make_cst([(0x20, r"[漢字/かんじ]を\f読む")])
        exported = catsystem2.export_cst(data)
        for text in ("[漢字/hanzi]読", "漢字読", "[一/yi]と[二/er]"):
            catsystem2.patch_dialogue(data, exported, [{"message": text + r"\f"}])
        for text in ("[漢字]読", "[漢字/]読", "漢字/かんじ]読", "[[a/b]]", "[a/b/c]"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                catsystem2.patch_dialogue(data, exported, [{"message": text + r"\f"}])


def _make_game(root, scripts, *, updates=()):
    """Encrypted base scene.int (observed record-prefixed layout) + cs2.exe."""
    root.mkdir()
    (root / "cs2.exe").write_bytes(make_password_pe("test-pass"))
    (root / "scene.int").write_bytes(catsystem2_int.write_int(
        [(name, make_cst(items)) for name, items in scripts], encrypted=True,
        password="test-pass"))
    for name, members in updates:
        (root / name).write_bytes(catsystem2_int.write_int(
            [(n, make_cst(items)) for n, items in members], encrypted=True, password="test-pass"))
    return root


class CatSystemPackTests(unittest.TestCase):
    scripts = [
        ("01_common_02.cst", [(0x21, "結灯＠少女"), (0x20, r"「[漢字/かんじ]」\@"),
                              (0x20, r"\n続き")]),
        ("02_other.cst", [(0x20, "untouched")]),
        ("03_empty.cst", [(0x30, "jump label")]),
    ]

    def _workspace(self, root, **game):
        game_root = _make_game(root / "game", self.scripts, **game)
        summary = extract_game(game_root, output=root / "ws")
        self.assertEqual(summary["identity_roundtrip"]["failed"], 0)
        return game_root, root / "ws"

    def _translate(self, ws, rows=None):
        rows = rows or [{"name": "少年", "message": "「[漢字/hanzi]」\\@"},
                        {"message": "\n継続"}]
        (ws / "gt_output" / "01_common_02.json").write_text(
            json.dumps(rows, ensure_ascii=False), "utf-8")

    def test_pack_only_changed_members_real_names_and_readback(self):
        from python.engines.catsystem2_pack import pack, read_back
        from python.common.contract import load_json
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            game, ws = self._workspace(root, updates=[("update01.int", [("02_other.cst", [(0x20, "new")])])])
            rows = [{"name": "結灯", "message": "「[漢字/かんじ]」\\@"}, {"message": "\n続きだ"}]
            self._translate(ws, rows)
            (ws / "gt_output" / "02_other.json").write_bytes((ws / "gt_input" / "02_other.json").read_bytes())
            result = pack(ws, root / "rebuilt", readback=root / "readback")
            self.assertEqual(result["archive"], "update02.int")
            self.assertEqual([m["member"] for m in result["changed_members"]], ["01_common_02.cst"])
            self.assertEqual(result["unchanged_translation_files"], ["02_other.json"])
            self.assertTrue(result["encrypted"] and result["record_prefix"])
            self.assertEqual(sorted(p.relative_to(root / "rebuilt").as_posix()
                                    for p in (root / "rebuilt").rglob("*") if p.is_file()),
                             ["README.txt", "reports/verification.json", "update02.int"])
            packed = (root / "rebuilt" / "update02.int").read_bytes()
            archive = catsystem2_int.read_int(packed, password="test-pass")
            self.assertEqual([e.name for e in archive.entries], ["01_common_02.cst"])
            records = catsystem2.read_cst(catsystem2_int.read_member(
                packed, archive.entries[0], archive.cipher)).records
            self.assertEqual(records[0].text, "結灯＠結灯")
            self.assertEqual(load_json((root / "readback/gt_input/01_common_02.json").read_bytes()), rows)
            self.assertEqual(load_json((root / "readback/gt_input/02_other.json").read_bytes()),
                             [{"message": "new"}])
            self.assertEqual(sorted(p.name for p in (root / "readback/gt_input").iterdir()),
                             sorted(p.name for p in (ws / "gt_input").iterdir()))
            again = read_back(ws, root / "rebuilt", root / "readback2")
            self.assertEqual(again["replaced_members"], 1)
            with self.assertRaises(ValueError):
                pack(ws, root / "numbered", number=1)
            self.assertEqual(pack(ws, root / "numbered", number=7)["archive"], "update07.int")

    def test_pack_rejections(self):
        from python.engines.catsystem2_pack import pack
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            game, ws = self._workspace(root)
            original = json.loads((ws / "gt_input" / "01_common_02.json").read_text("utf-8"))
            cases = {
                "unchanged": original,
                "continuation": [original[0], {"message": "続き"}],
                "id prefix": [dict(original[0], name="結灯＠少年"), original[1]],
                "ruby": [dict(original[0], message="「[漢字]」\\@"), original[1]],
                "row count": original[:1],
            }
            for label, rows in cases.items():
                self._translate(ws, rows)
                with self.subTest(label=label), self.assertRaises(ValueError):
                    pack(ws, root / f"out-{label.replace(' ', '_')}")
            self._translate(ws)
            (ws / "gt_output" / "unknown.json").write_text("[]", "utf-8")
            with self.assertRaises(ValueError):
                pack(ws, root / "out-unknown")
            (ws / "gt_output" / "unknown.json").unlink()
            with self.assertRaises(ValueError):
                pack(ws, root / "out-password", password="wrong")
            with self.assertRaises(ValueError):
                pack(ws, game / "inside")
            (game / "update05.int").write_bytes(catsystem2_int.write_int(
                [("01_common_02.cst", make_cst([(0x20, "newer")]))], encrypted=True,
                password="test-pass"))
            with self.assertRaises(ValueError):
                pack(ws, root / "out-unscanned")
            self.assertFalse(any((root / name).exists() for name in (
                "out-unchanged", "out-unknown", "out-password", "out-unscanned")))

    def test_jis_finalize_delivers_update_int(self):
        from python.common.jis_workflow import finalize, prepare
        from python.engines.catsystem2_extract import main
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            game, ws = self._workspace(root)
            self._translate(ws, [{"name": "少年", "message": "「[汉字/hanzi]」\\@"},
                                 {"message": "\n继续"}])
            prepare(ws, root / "prep", encoding="cp932", proxy_policy="unused")
            self.assertEqual(main(["pack", str(root / "prep/workspace"), str(root / "rebuilt")]), 0)
            self.assertEqual(main(["readback", str(root / "prep/workspace"), str(root / "rebuilt"),
                                   str(root / "readback")]), 0)
            finalize(root / "prep", root / "rebuilt", root / "readback/gt_input", root / "deliver")
            delivered = sorted(p.relative_to(root / "deliver").as_posix()
                               for p in (root / "deliver").rglob("*") if p.is_file())
            self.assertIn("update01.int", delivered)
            self.assertFalse(any(name.endswith(".cst") or name.startswith("gt_input/")
                                 for name in delivered))


if __name__ == "__main__":
    unittest.main()
