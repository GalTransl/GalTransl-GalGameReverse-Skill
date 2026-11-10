"""Incremental flat patch.xp3, speaker-key audit and SCN layout variants."""
import io
import json
from pathlib import Path
import tempfile
import unittest

from test_kirikiri_senren import fixture_tree
from test_kirikiri_kag_text import SAMPLE, raw as kag_raw
from python.archives import kirikiri_xp3 as xp3
from python.common.contract import dump_rows
from python.engines.kirikiri_psb import Psb
from python.engines.kirikiri_scn import records
from python.engines.kirikiri_extract import (extract, pack, member_name_keys, speaker_key_conflicts,
                                             flat_patch_members)
from python.engines import kirikiri_kag_extract as kag
from python.engines.kirikiri_kag_text import export_script

SPEAKER = 'ナギ'


def scene(message='本文', who=None, display=None):
    return fixture_tree({'scenes': [{'texts': [[who, display, message, None, 1, {}]]}]}, version=2)


def read_all(data, spec=None):
    stream = io.BytesIO(data); profile, entries = xp3.read_index(stream)
    return {e.name: xp3.read_member(stream, e, profile, spec) for e in entries}


def translate(work, name, edit):
    rows = json.loads((work/'gt_input'/name).read_bytes()); edit(rows)
    (work/'gt_output'/name).write_bytes(dump_rows(rows))
    return rows


class ScnPatchTests(unittest.TestCase):
    def build(self, root, members, spec=None, **extra):
        game = root/'game'; game.mkdir()
        (game/'data.xp3').write_bytes(xp3.build(members, 'plain', spec))
        for name, files in extra.items(): (game/name).write_bytes(xp3.build(files, 'plain'))
        work = root/'work'
        report = extract(game, work, archives=('data.xp3',), filter_spec=spec)
        return game, work, report

    def test_only_changed_members_flat_and_read_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game, work, _ = self.build(root, [('scn/a.scn', scene('一')), ('scn/sub/b.scn', scene('二')),
                                              ('empty.scn', fixture_tree({'scenes': []}, version=2))])
            original = (game/'data.xp3').read_bytes()
            rows = translate(work, 'a.json', lambda r: r[0].update(message='变长的中文译文'))
            result = pack(work, root/'patch')
            self.assertEqual(result['mode'], 'patch')
            self.assertEqual(result['changed_members'], [{'member': 'scn/a.scn', 'packed_as': 'a.scn'}])
            self.assertEqual(sorted(p.name for p in (root/'patch').iterdir()), ['patch.xp3', 'verification.json'])
            members = read_all((root/'patch/patch.xp3').read_bytes())
            self.assertEqual(list(members), ['a.scn'])
            self.assertEqual([r['row'] for r in records(Psb(members['a.scn']))], rows)
            self.assertEqual(json.loads((root/'patch/verification.json').read_bytes())['changed_members'][0]['packed_as'], 'a.scn')
            self.assertEqual((game/'data.xp3').read_bytes(), original)
            full = pack(work, root/'full', incremental=False)
            self.assertEqual(full['members'], 3)
            self.assertEqual(full['changed_members'], [{'member': 'scn/a.scn', 'packed_as': 'scn/a.scn'}])

    def test_no_change_is_rejected_without_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); _, work, _ = self.build(root, [('scn/a.scn', scene())])
            with self.assertRaisesRegex(ValueError, 'no changed members'): pack(work, root/'patch')
            self.assertFalse((root/'patch').exists())
            # An identical gt_output is still no change.
            translate(work, 'a.json', lambda r: None)
            with self.assertRaisesRegex(ValueError, 'no changed members'): pack(work, root/'patch')
            self.assertEqual(pack(work, root/'full', incremental=False)['changed_files'], 0)

    def test_basename_collisions_are_rejected(self):
        for left, right in (('left/scene.scn', 'right/scene.scn'), ('left/Scene.scn', 'right/scene.scn')):
            with self.subTest(left=left), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); _, work, report = self.build(root, [(left, scene('一')), (right, scene('二'))])
                name = report['exports'][0]['json']
                translate(work, name, lambda r: r[0].update(message='中文'))
                with self.assertRaisesRegex(ValueError, 'basename collision'): pack(work, root/'patch')
                self.assertFalse((root/'patch').exists())
                self.assertEqual(pack(work, root/'full', incremental=False)['changed_files'], 1)
        with self.assertRaisesRegex(ValueError, 'collision'):
            flat_patch_members([('a/X.scn', b'1'), ('b/x.scn', b'2')], ['a/X.scn', 'b/x.scn'])

    def test_patch_reuses_filter_spec_or_writes_plain(self):
        spec = {'algorithm': 'akabei', 'seed': 12345}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); _, work, _ = self.build(root, [('scn/a.scn', scene())], spec)
            rows = translate(work, 'a.json', lambda r: r[0].update(message='中文'))
            same = pack(work, root/'same')
            self.assertEqual(same['filter_spec'], spec)
            data = (root/'same/patch.xp3').read_bytes()
            self.assertEqual([r['row'] for r in records(Psb(read_all(data, spec)['a.scn']))], rows)
            with self.assertRaises(ValueError): read_all(data)
            plain = pack(work, root/'plain', patch_filter='none')
            self.assertIsNone(plain['filter_spec'])
            self.assertEqual(read_all((root/'plain/patch.xp3').read_bytes())['a.scn'],
                             read_all(data, spec)['a.scn'])


class SpeakerKeyTests(unittest.TestCase):
    def test_tokens_from_directories_and_filenames(self):
        keys = member_name_keys(['fgimage/ナギ/body.png', 'voice/ミナ_001.ogg', 'image/ユウa.png',
                                 'scenario/ハル_route.ks', 'bg/room01.png'])
        self.assertEqual(set(speaker_key_conflicts({'ナギ', 'ミナ', 'ユウ', 'ハル', 'room', '先生'}, keys)),
                         {'ナギ', 'ミナ', 'ユウ', 'room'})

    def run_case(self, root, media, **options):
        game = root/'game'; game.mkdir()
        (game/'scn.xp3').write_bytes(xp3.build([('scn/a.scn', scene('本文', SPEAKER)),
                                                ('scn/b.scn', scene('別', SPEAKER, '表示名'))], 'plain'))
        if media: (game/'fgimage.xp3').write_bytes(xp3.build(media, 'plain'))
        work = root/'work'
        return work, extract(game, work, archives=('scn.xp3',), **options)

    def test_auto_keeps_who_read_only_on_path_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work, report = self.run_case(root, [(f'fgimage/{SPEAKER}/{SPEAKER}_01.png', b'png')])
            self.assertIs(report['speaker_name'], False)
            self.assertEqual(report['speaker_key_warning']['names'], [SPEAKER])
            self.assertIn('fgimage.xp3', report['name_scan']['archives'])
            totals = report['totals']
            self.assertEqual((totals['who_names'], totals['writable_who_names'], totals['display_names']), (1, 0, 1))
            translate(work, 'a.json', lambda r: r[0].update(name='中文名'))
            with self.assertRaises(ValueError): pack(work, root/'rejected')
            self.assertFalse((root/'rejected').exists())
            translate(work, 'a.json', lambda r: r[0].update(message='中文正文'))
            translate(work, 'b.json', lambda r: r[0].update(name='显示名'))
            self.assertEqual(len(pack(work, root/'patch')['changed_members']), 2)

    def test_auto_without_evidence_and_explicit_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work, report = self.run_case(root, [('bg/room.png', b'png')])
            self.assertIs(report['speaker_name'], True)
            self.assertNotIn('speaker_key_warning', report)
            self.assertEqual(report['totals']['writable_who_names'], 1)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work, report = self.run_case(root, [(f'voice/{SPEAKER}_0001.ogg', b'ogg')], speaker_name=True)
            self.assertIs(report['speaker_name'], True)
            self.assertEqual(report['speaker_name_mode'], 'explicit')
            self.assertEqual(report['speaker_key_warning']['names'], [SPEAKER])
            translate(work, 'a.json', lambda r: r[0].update(name='中文名'))
            self.assertEqual(pack(work, root/'patch')['changed_members'][0]['packed_as'], 'a.scn')


class LayoutVariantTests(unittest.TestCase):
    def test_multilanguage_variant_and_legacy_manifest(self):
        langs = [[None, '本文', 2], ['Other', 'Other text', 10]]
        data = fixture_tree({'scenes': [{'texts': [[SPEAKER, langs, None, 1, {}]]}]})
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); game = root/'game'; game.mkdir()
            (game/'data.xp3').write_bytes(xp3.build([('a.scn', data)], 'plain'))
            for index in (0, 1):
                work = root/f'work{index}'
                extract(game, work, language_index=index)
                meta = json.loads((work/'metadata/a.json').read_bytes())
                self.assertEqual(meta['engine']['variant'], f'psb-scn-multi-language:{index}')
            work = root/'work0'
            meta = json.loads((work/'metadata/a.json').read_bytes())
            meta['engine']['variant'] = 'psb-scn-single-language'
            (work/'metadata/a.json').write_text(json.dumps(meta, ensure_ascii=False), encoding='utf-8')
            translate(work, 'a.json', lambda r: r[0].update(message='中文'))
            self.assertEqual(pack(work, root/'legacy')['changed_files'], 1)
            meta['engine']['variant'] = 'tampered'
            (work/'metadata/a.json').write_text(json.dumps(meta, ensure_ascii=False), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'manifest'): pack(work, root/'bad')


class KagPatchTests(unittest.TestCase):
    def test_changed_only_noop_and_collision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = kag_raw(SAMPLE); other = kag_raw('@nm t="人"\n本文[np]\n')
            (root/'data.xp3').write_bytes(xp3.build([('scenario/main.ks', source), ('scenario/sub.ks', other)], 'plain'))
            work = root/'work'; kag.extract(root, work, archives=['data.xp3'])
            with self.assertRaisesRegex(ValueError, 'no changed members'): kag.pack(work, root/'noop')
            self.assertFalse((root/'noop').exists())
            rows, _ = export_script(source); rows[1]['message'] = '中文旁白。'
            (work/'gt_output/main.json').write_bytes(dump_rows(rows))
            result = kag.pack(work, root/'patch')
            self.assertEqual(result['changed_members'], [{'member': 'scenario/main.ks', 'packed_as': 'main.ks'}])
            members = read_all((root/'patch/patch.xp3').read_bytes())
            self.assertEqual(list(members), ['main.ks'])
            self.assertEqual(export_script(members['main.ks'])[0], rows)
            self.assertEqual(kag.pack(work, root/'full', incremental=False)['members'], 2)
        # A changed script may not shadow another selected member's basename.
        with self.assertRaisesRegex(ValueError, 'collision'):
            flat_patch_members([('a/main.ks', b'x')], ['a/main.ks', 'b/MAIN.ks'])


if __name__ == '__main__':
    unittest.main()
