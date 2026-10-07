"""Typed SCN text location writes back: verified fields are rewritten, the rest is kept."""
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch as mock_patch

from test_kirikiri_senren import fixture_tree
from python.archives import xp3, kirikiri_elif, kirikiri_xp3
from python.archives.kirikiri_hxv4 import derive, name_hash, path_hash
from python.archives.kirikiri_hxv4_payload import build as build_hx
from python.engines import kirikiri_extract as shared, kirikiri_hxv4_text as hx
from python.engines.kirikiri_psb import Psb
from python.engines.kirikiri_scn import locate_records, records, writable_records, patch, fingerprint


def script(texts, **extra):
    return fixture_tree(dict(name='main.txt', scenes=[dict(texts=texts)], **extra))


# Extra outer fields, an unverified length/cache and a partly non-string tail:
# text is locatable and the message/name stay writable in every case.
OPAQUE_TEXTS = [
    ['id', '表示名', '本文', {'unknown': ['opaque']}, 99],
    ['id', [['表示名', '原文', 999, {'unknown_cache': 'opaque'}],
            ['Name', 'Other', 42, {'extra': 'opaque'}, None, 123]], {'future': 1}, 9],
    ['id', None, [[None, '別本文', None, 45, {}, 'extra']]],
]
OPAQUE_ROWS = [dict(name='表示名', message='本文'),
               dict(name='表示名', message='原文'),
               dict(name='id', message='別本文')]


class TypedLocationTests(unittest.TestCase):
    def test_search_cache_keeps_its_role_when_speech_cache_is_opaque(self):
        text = '[よみ,1]漢字'
        raw = script([['id', [[None, text, 2, {'opaque': 1}, '漢字']], None, 1, {}]])
        p = Psb(raw); found, issue = writable_records(p)
        self.assertTrue(issue)
        self.assertTrue(found[0]['search_only'])
        self.assertEqual(patch(p, found, [r['row'] for r in found])[0], raw)
        rows = [dict(found[0]['row'], message='中文前缀' + text)]
        rebuilt, paths = patch(p, found, rows); q = Psb(rebuilt)
        new = writable_records(q)[0]
        self.assertEqual([r['row'] for r in new], rows)
        self.assertEqual(new[0]['caches'], found[0]['caches'])
        self.assertTrue(new[0]['search_only'])
        self.assertEqual(fingerprint(p, paths), fingerprint(q, paths))

    def test_opaque_tail_fields_are_located_and_still_writable(self):
        raw = script(OPAQUE_TEXTS); p = Psb(raw)
        located = locate_records(p)
        self.assertEqual([r['row'] for r in located], OPAQUE_ROWS)
        self.assertTrue(any(r.get('opaque') for r in located))
        self.assertTrue(all('non_writable' not in r for r in located))
        found, issue = writable_records(p)
        self.assertEqual([r['row'] for r in found], OPAQUE_ROWS)
        self.assertTrue(issue)  # the exact dialect does not apply, so it fell back
        rows = [dict(r['row']) for r in found]
        rows[0]['message'] = '中文变长正文'; rows[1]['name'] = '译名'
        rebuilt, paths = patch(p, found, rows); q = Psb(rebuilt)
        self.assertEqual([r['row'] for r in writable_records(q)[0]], rows)
        self.assertEqual(fingerprint(p, paths), fingerprint(q, paths))  # opaque bytes intact

    def test_verified_derived_fields_are_rewritten(self):
        # The known 5-slot multilingual layout: length plus speech/search caches.
        raw = script([['id', [[None, '原文', 2, '原文', '原文']], None, 1, {}]])
        p = Psb(raw); found, issue = writable_records(p)
        self.assertIsNone(issue)
        self.assertNotIn('opaque', found[0]); self.assertNotIn('non_writable', found[0])
        self.assertIn('length', found[0])
        self.assertEqual(len(found[0]['caches']), 2)
        rows = [dict(found[0]['row'], message='中文译文加长')]
        rebuilt, _ = patch(p, found, rows); q = Psb(rebuilt)
        # The exact reader re-validates the rewritten length and caches.
        self.assertEqual([r['row'] for r in records(q)], rows)

    def test_unknown_control_syntax_is_exported_but_not_writable(self):
        raw = script([[None, None, '本文#unknown;$call();', None, 1, {}]])
        found, issue = writable_records(Psb(raw))
        self.assertEqual(found[0]['row'], dict(message='本文#unknown;$call();'))
        self.assertIn('control syntax', found[0]['non_writable'])
        self.assertIn('control syntax', issue)
        p = Psb(raw)
        self.assertEqual(patch(p, found, [dict(found[0]['row'])])[0], raw)
        with self.assertRaisesRegex(ValueError, 'not recognized'):
            patch(p, found, [dict(message='改写的正文')])

    def test_mixed_archive_profiles_require_an_explicit_output_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); raw = script([[None, None, '本文', None, 1, {}]])
            (root/'one.xp3').write_bytes(xp3.build([('one.scn', raw)], filter_name='none'))
            (root/'two.xp3').write_bytes(kirikiri_elif.build([('two.scn', raw)]))
            with self.assertRaisesRegex(ValueError, 'mixed archive profiles'):
                shared.extract(root, root/'rejected', archives=('one.xp3', 'two.xp3'))
            self.assertFalse((root/'rejected').exists())
            report = shared.extract(root, root/'accepted', archives=('one.xp3', 'two.xp3'), output_format='plain')
            self.assertEqual(report['totals']['rows'], 2)

    def test_missing_slots_and_ambiguous_types_still_fail(self):
        invalid = [[], [None], [None, 1, 'text'], [None, 1, [[None, 'text']]], [123, None, 'text'],
                   [None, None, 123], [None, [[]]], [None, [None]], [None, []]]
        for text in invalid:
            with self.subTest(text=text), self.assertRaises(ValueError):
                writable_records(Psb(script([text])))
        with self.assertRaisesRegex(ValueError, 'language slot missing'):
            writable_records(Psb(script([[None, [[None, 'text']]]])), 1)

    def test_workspace_translates_opaque_records_and_preserves_the_rest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'data.xp3').write_bytes(xp3.build(
                [('opaque.scn', script(OPAQUE_TEXTS)), ('plain.scn', script([[None, None, '本文', None, 1, {}]]))],
                filter_name='none'))
            work = root/'work'; result = shared.extract(root, work, verify_edits=True)
            self.assertEqual(result['totals']['rows'], 4)
            self.assertTrue(result['totals']['opaque_fields'])
            export = next(e for e in result['exports'] if e['json'] == 'opaque.json')
            self.assertTrue(export['verified_dialect_issue'])
            self.assertEqual([e['json'] for e in result['exports']], ['opaque.json', 'plain.json'])
            rows = json.loads((work/'gt_input/opaque.json').read_bytes())
            rows[0]['message'] = '中文变长回填'; rows[1]['message'] = '另一条译文'
            (work/'gt_output/opaque.json').write_text(json.dumps(rows), encoding='utf-8')
            packed = shared.pack(work, root/'packed')
            self.assertEqual(packed['changed_files'], 1)
            stream = io.BytesIO((root/'packed/scenario.xp3').read_bytes())
            profile, entries = kirikiri_xp3.read_index(stream)
            member = next(e for e in entries if e.name == 'opaque.scn')
            decoded = kirikiri_xp3.read_member(stream, member, profile)
            self.assertEqual([r['row'] for r in writable_records(Psb(decoded))[0]], rows)

    def test_read_only_records_refuse_a_changed_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = script([[None, None, '本文#unknown;', None, 1, {}]])
            (root/'data.xp3').write_bytes(xp3.build([('main.scn', raw)], filter_name='none'))
            work = root/'work'; result = shared.extract(root, work)
            self.assertEqual(result['exports'][0]['non_writable'][0]['index'], 0)
            rows = json.loads((work/'gt_input/main.json').read_bytes()); rows[0]['message'] = '改动'
            (work/'gt_output/main.json').write_text(json.dumps(rows), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'not recognized'): shared.pack(work, root/'bad')
            self.assertFalse((root/'bad').exists())
            # Keeping the row unchanged packs it back byte-identical.
            (work/'gt_output/main.json').unlink()
            self.assertEqual(shared.pack(work, root/'kept')['changed_files'], 0)

    def test_hx_entrypoint_writes_back_an_opaque_dialect(self):
        package = dict(bootStrap='test', warning='test', archiveUniqueKey='{test}',
                       params='000102030405060700010203040500010280ff010001')
        keys = derive(package)
        raw = script([['id', [[None, '本文', 500, 'opaque', 'cache']], None, 1, {}, 9]])
        entry = dict(id=1, key=789, name_hash=name_hash('main.txt.scn'), path_hash=path_hash('scn/'))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root/'scn.xp3'; source.write_bytes(build_hx([(entry, raw)], keys))
            evidence = dict(key_package=package, source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), exe_sha256='test')
            with mock_patch('python.engines.kirikiri_hxv4_text.inspect', return_value=evidence):
                result = hx.extract(source, root/'unused.exe', root/'work')
            self.assertTrue(result['scan_complete'])
            self.assertEqual(result['totals']['rows'], 1)
            self.assertEqual((root/'work/original/main.txt.scn').read_bytes(), raw)
            rows = json.loads((root/'work/gt_input/main.txt.json').read_bytes()); rows[0]['message'] = '中文回填'
            (root/'work/gt_output/main.txt.json').write_text(json.dumps(rows), encoding='utf-8')
            self.assertEqual(hx.pack(root/'work', root/'packed')['changed_files'], 1)

    def test_default_cli_needs_no_mode_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'data.xp3').write_bytes(xp3.build([('main.scn', script(OPAQUE_TEXTS))], filter_name='none'))
            with mock_patch('sys.argv', ['kirikiri_extract', 'extract', str(root), str(root/'work')]), \
                    mock_patch('sys.stdout', new_callable=io.StringIO) as stdout:
                shared.main()
            captured = stdout.getvalue()  # progress lines precede the JSON summary
            self.assertEqual(json.loads(captured[captured.index('{'):])['rows'], 3)
            with mock_patch('sys.argv', ['kirikiri_extract', 'extract', '--help']), \
                    mock_patch('sys.stdout', new_callable=io.StringIO) as help_out:
                with self.assertRaises(SystemExit): shared.main()
            self.assertNotIn('--text-only', help_out.getvalue())
            self.assertIn('--verify-edits', help_out.getvalue())


if __name__ == '__main__': unittest.main()
