"""Escu:de template writer and validated workspace packing regressions."""
import io
import json
from pathlib import Path
import tempfile
import unittest

from test_engines_escude import archive, acp
import test_escude_extract as fixture
from python.archives.escude import encode_acp_literal, decode_acp, read_index, read_member, repack
from python.engines.escude_extract import extract
from python.engines.escude_pack import pack


class EscudePackTests(unittest.TestCase):
    def test_acp_literals_reset_and_limits(self):
        for data in (b'', b'x', bytes(range(256)) * 300):
            self.assertEqual(decode_acp(encode_acp_literal(data)), data)
        with self.assertRaises(ValueError):
            encode_acp_literal(b'abc', max_output=9)

    def test_archive_preserves_untouched_compression_and_repairs_index(self):
        original = archive([('sub\\a.001', acp([65, 0x103, 0x100], 3)), ('b.bin', b'code')])
        self.assertEqual(repack(original, {'sub/a.001': b'AAA'}), original)
        rebuilt = repack(original, {'sub/a.001': b'B' * 70000})
        stream = io.BytesIO(rebuilt)
        entries = read_index(stream).entries
        self.assertEqual([read_member(stream, e) for e in entries], [b'B'*70000, b'code'])
        self.assertEqual(rebuilt[entries[0].offset:entries[0].offset+4], b'acp\0')
        with self.assertRaises(ValueError):
            repack(original, {'unknown': b'bad'})
        with self.assertRaises(ValueError):
            repack(original + b'trailer', {})
        with self.assertRaises(ValueError):
            repack(original, {'sub/a.001': b'x'*100}, max_output=len(original))

    def test_workspace_roundtrip_and_translated_pack(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = fixture.EscudeExtractTests().setup_game(root)
            work = root / 'work'
            extract(game, work)
            result = pack(work, root / 'roundtrip')
            self.assertTrue(result['byte_identical'])
            rows = json.loads((work / 'gt_input/scene.json').read_bytes())
            rows[0]['message'] = '追加試験<r>長い本文です'
            (work / 'gt_output/scene.json').write_text(json.dumps(rows), encoding='utf-8')
            result = pack(work, root / 'translated')
            self.assertEqual(result['changed_members'], ['staff/scene.001'])
            self.assertEqual(result['members_verified'], 3)
            with self.assertRaises(FileExistsError):
                pack(work, root / 'translated')
            self.assertEqual(pack(work, root / 'smoke', verify_edits=True)['mode'], 'smoke-test')

    def test_tampered_inputs_and_invalid_translations_never_publish(self):
        for case in ('manifest', 'source', 'unknown', 'name', 'encoding', 'controls'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                game = fixture.EscudeExtractTests().setup_game(root)
                work = root / 'work'
                extract(game, work)
                rows = json.loads((work / 'gt_input/scene.json').read_bytes())
                if case == 'manifest':
                    p = work / 'metadata/scene.json'
                    value = json.loads(p.read_bytes())
                    value['records'][0]['locator']['pool_index'] = 99
                    p.write_text(json.dumps(value), encoding='utf-8')
                elif case == 'source':
                    (work / 'original/script/empty.bin').write_bytes(b'bad')
                elif case == 'unknown':
                    (work / 'gt_output/typo.json').write_text('[]')
                else:
                    if case == 'name':
                        rows[0]['name'] = '乙'
                    elif case == 'encoding':
                        rows[0]['message'] = '简体中文<r>测试'
                    else:
                        rows[0]['message'] = '本文'
                    (work / 'gt_output/scene.json').write_text(json.dumps(rows), encoding='utf-8')
                with self.assertRaises(ValueError):
                    pack(work, root / 'failed')
                self.assertFalse((root / 'failed').exists())


if __name__ == '__main__':
    unittest.main()
