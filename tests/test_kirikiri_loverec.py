"""LOVEREC eliF / PSB v2 regression tests with synthetic data only."""
from dataclasses import replace
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest

from test_kirikiri_senren import fixture_tree
from python.archives.kirikiri_elif import build,read_index,read_member
from python.engines.kirikiri_psb import Psb
from python.engines.kirikiri_scn import records,patch,fingerprint
from python.engines.kirikiri_extract import extract,pack


def fixture(zero=False):
    return fixture_tree({'scenes':[{'texts':[['actor',None,'本文',None,1,{}]],
                                   'selects':[{'text':'選択','target':'label'}]}],
                         'unchanged':'本文'},version=2,zero_header_length=zero)


class LoverecTests(unittest.TestCase):
    def test_psb2_header_variants_growth_and_noop(self):
        for zero in (False,True):
            raw=fixture(zero);p=Psb(raw);recs=records(p);rows=[dict(r['row']) for r in recs]
            self.assertEqual(patch(p,recs,rows)[0],raw)
            rows[0]['message']='中文文本增长测试';out,paths=patch(p,recs,rows);q=Psb(out)
            self.assertEqual(q.version,2)
            self.assertEqual(struct.unpack_from('<I',out,8)[0],0 if zero else 40)
            self.assertEqual([r['row'] for r in records(q)],rows)
            self.assertEqual(fingerprint(p,paths),fingerprint(q,paths))
            self.assertEqual(q.text(q.object(q.root)['unchanged']),'本文')

    def test_elif_mapping_marked_plaintext_and_corruption(self):
        raw=build([('scn/start.ks.scn',fixture()),('same.ks.scn',fixture())])
        stream=io.BytesIO(raw);es=read_index(stream)
        self.assertEqual([e.name for e in es],['scn/start.ks.scn','same.ks.scn'])
        entry=replace(es[0],flags=0x80000000)
        with self.assertRaises(ValueError):read_member(stream,entry)
        self.assertEqual(read_member(stream,entry,marked_plaintext=True),fixture())
        with self.assertRaises(ValueError):read_member(stream,replace(entry,checksum=1),marked_plaintext=True)
        with self.assertRaises(ValueError):read_member(stream,replace(es[0],issue='invalid header overlap'))
        bad=bytearray(raw);bad[es[0].segments[0][1]+3]^=1
        with self.assertRaises(ValueError):read_member(io.BytesIO(bad),es[0])

    def test_extract_pack_ignores_translation_archives_and_checks_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);game=root/'game';game.mkdir()
            (game/'data.xp3').write_bytes(build([('scn/start.ks.scn',fixture())]))
            (game/'patch.xp3').write_bytes(b'must not be read')
            (game/'patch_append.xp3').write_bytes(b'must not be read')
            work=root/'work';report=extract(game,work,verify_edits=True)
            self.assertEqual(report['totals']['rows'],2)
            self.assertEqual(pack(work,root/'roundtrip')['changed_files'],0)
            rows=json.loads((work/'gt_input/start.ks.json').read_bytes());rows[0]['message']='中文回填'
            (work/'gt_output/start.ks.json').write_text(json.dumps(rows),encoding='utf-8')
            self.assertEqual(pack(work,root/'translated')['changed_files'],1)
            with self.assertRaises(FileExistsError):pack(work,root/'translated')
            path=work/'metadata/start.ks.json';m=json.loads(path.read_bytes());m['records'][0]['locator']['message']=[99]
            path.write_text(json.dumps(m),encoding='utf-8')
            with self.assertRaises(ValueError):pack(work,root/'bad')
            self.assertFalse((root/'bad').exists())


if __name__=='__main__':unittest.main()
