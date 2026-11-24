"""Hx SCN stored inside the MDF zlib wrapper, unresolved self-names and
actionable empty-scan errors. Synthetic keys and scripts only."""
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from test_kirikiri_senren import fixture_tree
from python.archives.kirikiri_hxv4 import derive, name_hash, path_hash, read_index
from python.archives.kirikiri_hxv4_payload import Cipher, build, read_member
from python.engines.kirikiri_hxv4_text import extract, pack, unwrap, wrap
from python.engines.kirikiri_psb import Psb
from python.engines.kirikiri_scn import records

PACKAGE = dict(bootStrap='test', warning='test', archiveUniqueKey='{test}',
               params='000102030405060700010203040500010280ff010001')


def mdf(payload, level=1):
    return b'mdf\0' + len(payload).to_bytes(4, 'little') + zlib.compress(payload, level)


def script(title, message):
    return fixture_tree(dict(name=title, scenes=[dict(texts=[[None, None, message, None, 1, {}]])]))


class HxMdfTests(unittest.TestCase):
    def run_extract(self, root, members, **kw):
        keys = derive(PACKAGE); source = root / 'scn.xp3'
        source.write_bytes(build(members, keys))
        evidence = dict(key_package=PACKAGE, source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), exe_sha256='test')
        with patch('python.engines.kirikiri_hxv4_text.inspect', return_value=evidence):
            return extract(source, root / 'not-executed.exe', root / 'work', **kw)

    def test_wrapper_strictness(self):
        payload = script('a.txt', '本文')
        self.assertEqual(unwrap(mdf(payload)), (payload, 'mdf'))
        self.assertEqual(unwrap(payload), (payload, None))
        self.assertEqual(unwrap(wrap(payload, 'mdf'))[0], payload)
        for bad in (mdf(payload) + b'\0', mdf(payload)[:-3], b'mdf\0' + (len(payload) + 1).to_bytes(4, 'little') + zlib.compress(payload), b'mdf\0'):
            with self.subTest(bad=bad[:12]), self.assertRaises(ValueError):
                unwrap(bad)
        with self.assertRaises(ValueError):
            wrap(payload, 'lz4')

    def test_mdf_scn_roundtrip_unresolved_name_and_rewrap(self):
        keys = derive(PACKAGE)
        main = script('main.txt', '本文')
        other = script('other.txt', '二つ目')
        renamed = script('self-name.txt', '名前違い')
        members = [(dict(id=1, key=789, name_hash=name_hash('main.txt.scn'), path_hash=path_hash('scn/')), mdf(main)),
                   (dict(id=2, key=790, name_hash=name_hash('other.txt.scn'), path_hash=path_hash('scn/')), mdf(other)),
                   (dict(id=3, key=791, name_hash=name_hash('storage.txt.scn'), path_hash=path_hash('scn/')), mdf(renamed))]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = self.run_extract(root, members)
            self.assertEqual(result['totals']['files'], 2)
            self.assertEqual(result['wrappers'], {'scn/main.txt.scn': 'mdf', 'scn/other.txt.scn': 'mdf'})
            self.assertFalse(result['scan_complete'])
            self.assertEqual([d['reason'] for d in result['diagnostics']], ['scn-name-unresolved'])
            rows = [dict(message='更长的中文变长回写测试')]
            (root / 'work/gt_output/main.txt.json').write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
            self.assertEqual(pack(root / 'work', root / 'out')['changed_files'], 1)
            stream = io.BytesIO((root / 'out/scenario.xp3').read_bytes())
            entries = read_index(stream, keys)['files']
            stored = [read_member(stream, e, Cipher(keys)) for e in entries]
            self.assertTrue(all(s.startswith(b'mdf\0') for s in stored))
            self.assertEqual([r['row'] for r in records(Psb(unwrap(stored[0])[0]))], rows)
            # The unchanged script keeps its original wrapped bytes (original zlib level).
            self.assertEqual(stored[1], members[1][1])
            report = root / 'work/reports/hxv4.json'; bad = json.loads(report.read_text(encoding='utf-8'))
            bad['wrappers'] = {}
            report.write_text(json.dumps(bad), encoding='utf-8')
            with self.assertRaises(ValueError):
                pack(root / 'work', root / 'rejected')

    def test_empty_scan_reports_heads_and_bad_wrapper(self):
        members = [(dict(id=1, key=789, name_hash=name_hash('a.bin'), path_hash=path_hash('scn/')), b'OggS' + b'\0' * 60),
                   (dict(id=2, key=790, name_hash=name_hash('b.scn'), path_hash=path_hash('scn/')), mdf(b'PSB\0') + b'x')]
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, r"no supported SCN found.*4f676753"):
                self.run_extract(Path(tmp), members)


if __name__ == '__main__':
    unittest.main()
