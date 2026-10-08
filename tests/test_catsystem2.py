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
        self.assertIn("\n", exported.protected_tokens[0])
        self.assertIn(r"\@", exported.protected_tokens[0])
        self.assertEqual(catsystem2.patch_dialogue(data, exported,
                                                   list(exported.rows)), data)

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
            summary = extract_game(root)
            output = Path(summary["output"])
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
            summary = extract_game(relative_root, output="result")
            output = root / "result"
            self.assertEqual(Path(summary["output"]), output)
            self.assertTrue(summary["password_recovered"])
            rows = json.loads((output / "gt_input" / "scene.json").read_text("utf-8"))
            self.assertEqual(rows, [{"message": "encrypted"}])


if __name__ == "__main__":
    unittest.main()
