"""Synthetic regressions for field-tested entry-point behaviour: Yuzu-mapped
indexes, filter trial evidence, empty-selection guidance and explicit extra
KAG inline tags. No game data; every archive is built here."""
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from test_kirikiri_senren import fixture_tree
from test_kirikiri_kag_text import raw as kag_raw
from python.archives import xp3 as std_xp3, kirikiri_xp3 as xp3, kirikiri_elif
from python.common.contract import dump_rows
from python.engines import kirikiri_extract, kirikiri_kag_extract, kirikiri_probe
from python.engines.kirikiri_kag_text import export_script, rebuild_script, inline_tags
from python.engines.kirikiri_psb import Psb
from python.engines.kirikiri_scn import writable_records

YUZU = {'algorithm': 'yuzu'}


def scene(message='本文'):
    return fixture_tree({'scenes': [{'texts': [[None, None, message, None, 1, {}]]}]}, version=2)


def index_tags(data):
    at, = struct.unpack_from('<Q', data, 11)
    packed, length = struct.unpack_from('<QQ', data, at + 1)
    return [tag for tag, _ in std_xp3._chunks(zlib.decompress(data[at + 17:at + 17 + packed]))]


class YuzuMappedIndexTests(unittest.TestCase):
    def test_filtered_roundtrip_names_and_rejections(self):
        files = [('scn/first.scn', scene()), ('Second.SCN', scene('二つ目'))]
        data = xp3.build(files, 'yuzu-names', YUZU)
        self.assertEqual(xp3.detect(io.BytesIO(data)), 'yuzu-names')
        self.assertIn(b'Yuzu', index_tags(data))
        stream = io.BytesIO(data)
        profile, entries = xp3.read_index(stream)
        self.assertEqual(profile, 'yuzu-names')
        self.assertEqual([e.name for e in entries], [n for n, _ in files])
        self.assertTrue(all(e.flags == 0x80000000 and len(e.alias) == 32 for e in entries))
        self.assertEqual([xp3.read_member(stream, e, profile, YUZU) for e in entries], [d for _, d in files])
        # Without the verified filter the plaintext checksum fails with guidance.
        with self.assertRaisesRegex(ValueError, 'kirikiri_probe'):
            xp3.read_member(stream, entries[0], profile)
        with self.assertRaises(ValueError):
            xp3.read_member(stream, entries[0], profile, {'algorithm': 'hash'})
        # Plaintext variant and the eliF writer with a filter use the same reader.
        plain = xp3.build(files, 'yuzu-names')
        stream = io.BytesIO(plain); profile, entries = xp3.read_index(stream)
        self.assertEqual([xp3.read_member(stream, e, profile) for e in entries], [d for _, d in files])
        elif_filtered = kirikiri_elif.build(files, filter_spec=YUZU)
        stream = io.BytesIO(elif_filtered); profile, entries = xp3.read_index(stream)
        self.assertEqual(profile, 'elif-plain')
        self.assertEqual([xp3.read_member(stream, e, profile, YUZU) for e in entries], [d for _, d in files])

    def test_unknown_index_chunk_names_tags(self):
        data = bytearray(xp3.build([('a.scn', scene())], 'yuzu-names'))
        at, = struct.unpack_from('<Q', data, 11)
        packed, length = struct.unpack_from('<QQ', data, at + 1)
        index = zlib.decompress(bytes(data[at + 17:at + 17 + packed])).replace(b'Yuzu', b'Zzzz')
        repacked = zlib.compress(index)
        data[at:] = b'\x01' + struct.pack('<QQ', len(repacked), len(index)) + repacked
        with self.assertRaisesRegex(ValueError, 'Zzzz'):
            xp3.detect(io.BytesIO(bytes(data)))

    def test_extract_and_flat_patch_keep_mapping_and_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); game = root / 'game'; game.mkdir()
            (game / 'scn.xp3').write_bytes(xp3.build([('scn/a.scn', scene())], 'yuzu-names', YUZU))
            work = root / 'work'
            report = kirikiri_extract.extract(game, work, archives=('scn.xp3',), filter_spec=YUZU, verify_edits=True)
            self.assertEqual(report['output_format'], 'yuzu-names')
            rows = json.loads((work / 'gt_input/a.json').read_text(encoding='utf-8'))
            rows[0]['message'] = '更长一些的中文译文'
            (work / 'gt_output/a.json').write_bytes(dump_rows(rows))
            out = root / 'out'
            result = kirikiri_extract.pack(work, out)
            self.assertEqual(result['output_format'], 'yuzu-names')
            stream = io.BytesIO((out / 'patch.xp3').read_bytes())
            profile, entries = xp3.read_index(stream)
            self.assertEqual((profile, [e.name for e in entries]), ('yuzu-names', ['a.scn']))
            recs, _ = writable_records(Psb(xp3.read_member(stream, entries[0], profile, YUZU)), 0)
            self.assertEqual([r['row'] for r in recs], rows)


class FilterTrialTests(unittest.TestCase):
    def test_parameterless_candidate_needs_two_verified_members(self):
        spec = {'algorithm': 'hash'}
        files = [('a.ks', kag_raw('一行目[np]\r\n')), ('b.ks', kag_raw('二行目[np]\r\n'))]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'data.xp3'
            path.write_bytes(xp3.build(files, 'plain', spec))
            report = kirikiri_probe.probe(path, patterns=('*.ks',), filters=True)
            verdict = {r['filter_spec']['algorithm']: r['candidate'] for r in report['filter_trial']['results']}
            self.assertTrue(verdict['hash'])
            self.assertFalse(any(v for k, v in verdict.items() if k != 'hash'))
            self.assertEqual(report['checksum_passed'], 0)
            self.assertEqual(sum(report['error_counts'].values()), 2)
            path.write_bytes(xp3.build(files[:1], 'plain', spec))
            single = kirikiri_probe.probe(path, patterns=('*.ks',), filters=True)
            self.assertFalse(any(r['candidate'] for r in single['filter_trial']['results']))


class SelectionGuidanceTests(unittest.TestCase):
    def test_empty_scn_selection_points_to_sibling_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            game = Path(tmp)
            (game / 'data.xp3').write_bytes(xp3.build([('system/first.ks', kag_raw('x[np]'))], 'plain'))
            (game / 'scn.xp3').write_bytes(xp3.build([('a.scn', scene())], 'plain'))
            with self.assertRaisesRegex(ValueError, r'scn\.xp3 \(1 \.scn, plain\).*--archives'):
                kirikiri_extract.extract(game, game / 'out')
            self.assertFalse((game / 'out').exists())
            (game / 'scn.xp3').unlink()
            with self.assertRaisesRegex(ValueError, 'kirikiri_kag_extract'):
                kirikiri_extract.extract(game, game / 'out')

    def test_member_read_failure_names_archive_and_member(self):
        with tempfile.TemporaryDirectory() as tmp:
            game = Path(tmp)
            (game / 'data.xp3').write_bytes(xp3.build([('scn/a.scn', scene())], 'plain', {'algorithm': 'hash'}))
            with self.assertRaisesRegex(ValueError, r'data\.xp3:scn/a\.scn \(flags 0x80000000\).*filter'):
                kirikiri_extract.extract(game, game / 'out')


class ExtraInlineTagTests(unittest.TestCase):
    PAGE = kag_raw('@nm t="人物"\r\n「[ＬＣ]、こんにちは」[np]\r\n')

    def test_extra_tag_is_explicit_protected_and_recorded(self):
        with self.assertRaisesRegex(ValueError, r'^line 2: unverified inline KAG command \[ＬＣ\] \(U\+FF2C U\+FF23\).*--inline-tags'):
            export_script(self.PAGE)
        rows, meta = export_script(self.PAGE, ['ＬＣ'])
        self.assertEqual(meta['settings'], {'inline_tags': ['ＬＣ']})
        self.assertEqual(rebuild_script(self.PAGE, rows, meta, ['ＬＣ']), self.PAGE)
        changed = [dict(rows[0], message='「[ＬＣ]，你好，这是更长的译文」')]
        result = rebuild_script(self.PAGE, changed, meta, ['ＬＣ'])
        self.assertEqual(export_script(result, ['ＬＣ'])[0], changed)
        for bad in ('「你好」', '「[ＬＣ][ＬＣ]你好」'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                rebuild_script(self.PAGE, [dict(rows[0], message=bad)], meta, ['ＬＣ'])
        # The manifest pins the configuration used at extraction.
        with self.assertRaises(ValueError):
            rebuild_script(self.PAGE, rows, meta)
        for bad in (['np'], ['a b'], ['x=1'], ['ok', 'ok'], 'ＬＣ'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                inline_tags(bad)

    def test_workspace_reuses_tags_and_excludes_members(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'data.xp3').write_bytes(xp3.build(
                [('scenario/a.ks', self.PAGE), ('scenario/test.ks', kag_raw('[np]\r\n'))], 'plain'))
            with self.assertRaises(ValueError):
                kirikiri_kag_extract.extract(root, root / 'rejected', archives=['data.xp3'], inline_tags=['ＬＣ'])
            work = root / 'work'
            report = kirikiri_kag_extract.extract(root, work, archives=['data.xp3'], inline_tags=['ＬＣ'],
                                                  exclude=['scenario/test.ks'])
            self.assertEqual((report['inline_tags'], report['counts']['rows']), (['ＬＣ'], 1))
            rows = json.loads((work / 'gt_input/a.json').read_text(encoding='utf-8'))
            rows[0]['message'] = '「[ＬＣ]，中文」'
            (work / 'gt_output/a.json').write_bytes(dump_rows(rows))
            kirikiri_kag_extract.pack(work, root / 'out')
            with (root / 'out/patch.xp3').open('rb') as f:
                profile, entries = xp3.read_index(f)
                self.assertEqual(export_script(xp3.read_member(f, entries[0], profile), ['ＬＣ'])[0], rows)


if __name__ == '__main__':
    unittest.main()
