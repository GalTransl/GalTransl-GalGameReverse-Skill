"""Batch Haison export checks using synthetic archives only."""
import json
from pathlib import Path
import tempfile
import unittest

from test_engines_escude import archive, code_file, database, inst, message_file
from python.engines.escude_extract import extract


class EscudeExtractTests(unittest.TestCase):
    def setup_game(self, root, extra=()):
        game = root / 'game'
        game.mkdir()
        (game / 'data.bin').write_bytes(archive([('db_scripts.bin', database())]))
        files = [('staff\\scene.bin', code_file(inst(40, 1) + inst(41, 0), 1)),
                 ('staff\\scene.001', message_file(['試験<r>本文'])),
                 ('empty.bin', code_file(b'', 0))]
        (game / 'script.bin').write_bytes(archive(files + list(extra)))
        return game

    def test_export_is_flat_paired_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = self.setup_game(root)
            originals = {p.name: p.read_bytes() for p in game.iterdir()}
            output = root / 'output'
            report = extract(game, output)
            self.assertEqual(report['totals']['rows'], 1)
            self.assertEqual(report['totals']['original_roundtrip_pass'], 1)
            self.assertEqual(report['totals']['resized_roundtrip_pass'], 1)
            self.assertEqual(report['empty_code_members'], ['empty.bin'])
            self.assertEqual([p.name for p in (output / 'gt_input').iterdir()], ['scene.json'])
            rows = json.loads((output / 'gt_input/scene.json').read_text(encoding='utf-8'))
            self.assertEqual(rows, [{'message': '試験<r>本文', 'name': '甲＆乙'}])
            self.assertTrue((output / 'original/script/staff/scene.bin').is_file())
            self.assertTrue((output / 'gt_output').is_dir())
            with self.assertRaises(FileExistsError):
                extract(game, output)
            self.assertEqual(originals, {p.name: p.read_bytes() for p in game.iterdir()})

    def test_invalid_archive_set_never_publishes_partial_result(self):
        cases = [
            [('orphan.001', message_file(['試験']))],
            [('missing.bin', code_file(inst(41, 0), 1))],
            [('unknown.dat', b'unknown')],
            [('other/scene.bin', code_file(inst(41, 0), 1)),
             ('other/scene.001', message_file(['試験']))],
        ]
        for extra in cases:
            with self.subTest(extra=extra[0][0]), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                game = self.setup_game(root, extra)
                with self.assertRaises(ValueError):
                    extract(game, root / 'output')
                self.assertFalse((root / 'output').exists())


if __name__ == '__main__':
    unittest.main()
