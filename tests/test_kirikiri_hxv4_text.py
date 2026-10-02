"""Hx SCN contract re-use, encrypted edits, empty members and identity protection."""
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_kirikiri_senren import fixture_tree
from python.archives.kirikiri_hxv4 import derive, name_hash, path_hash, read_index
from python.archives.kirikiri_hxv4_payload import Cipher, build, read_member
from python.engines.kirikiri_hxv4_text import extract, pack, main
from python.engines.kirikiri_psb import Psb
from python.engines.kirikiri_scn import records


class HxTextTests(unittest.TestCase):
    def test_extract_pack_translations_and_identity_tampering(self):
        package=dict(bootStrap='test',warning='test',archiveUniqueKey='{test}',
                     params='000102030405060700010203040500010280ff010001')
        keys=derive(package)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'data.xp3';work=root/'work'
            members=[]
            for ident, title, texts in ((1,'main.txt',[[None,None,'本文',None,1,{}]]),(2,'empty.txt',[])):
                e=dict(id=ident,key=789,name_hash=name_hash(title+'.scn'),path_hash=path_hash('scn/'))
                raw=fixture_tree(dict(name=title,scenes=[dict(texts=texts)]))
                members.append((e,raw))
            source.write_bytes(build(members,keys))
            evidence=dict(key_package=package,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),exe_sha256='test')
            with patch('python.engines.kirikiri_hxv4_text.inspect',return_value=evidence):
                result=extract(source,root/'not-executed.exe',work)
            self.assertEqual(result['totals']['rows'],1)
            self.assertTrue(result['scan_complete'])
            self.assertEqual(len(list((work/'gt_input').iterdir())),1)
            self.assertEqual(pack(work,root/'unchanged')['changed_files'],0)
            rows=[dict(message='中文变长测试内容')]
            (work/'gt_output/main.txt.json').write_text(json.dumps(rows),encoding='utf-8')
            self.assertEqual(pack(work,root/'translated')['changed_files'],1)
            stream=io.BytesIO((root/'translated/scenario.xp3').read_bytes())
            entries=read_index(stream,keys)['files']
            self.assertEqual(len(entries),2)
            decoded=read_member(stream,entries[0],Cipher(keys))
            self.assertEqual([r['row'] for r in records(Psb(decoded))],rows)
            report=work/'reports/hxv4.json';bad=json.loads(report.read_text(encoding='utf-8'))
            bad['scripts']['scn/main.txt.scn']['key']+=1
            report.write_text(json.dumps(bad),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'identity'): pack(work,root/'rejected')
            self.assertFalse((root/'rejected').exists())

    def test_oversize_member_skipped_before_decryption(self):
        package=dict(bootStrap='test',warning='test',archiveUniqueKey='{test}',
                     params='000102030405060700010203040500010280ff010001')
        keys=derive(package)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'data.xp3'
            raw=fixture_tree(dict(name='main.txt',scenes=[dict(texts=[[None,None,'本文',None,1,{}]])]))
            oversized_script=fixture_tree(dict(name='large.txt',scenes=[dict(texts=[[None,None,'文'*70000,None,1,{}]])]))
            members=[(dict(id=1,key=789,name_hash=name_hash('main.txt.scn'),path_hash=path_hash('scn/')),raw),
                     (dict(id=2,key=790,name_hash=name_hash('ep_99.mov'),path_hash=path_hash('scn/')),b'\0'*200000),
                     (dict(id=3,key=791,name_hash=name_hash('large.txt.scn'),path_hash=path_hash('scn/')),oversized_script)]
            source.write_bytes(build(members,keys))
            evidence=dict(key_package=package,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),exe_sha256='test')
            with patch('python.engines.kirikiri_hxv4_text.inspect',return_value=evidence), \
                    patch('python.engines.kirikiri_hxv4_text.read_member',wraps=read_member) as reader:
                result=extract(source,root/'not-executed.exe',root/'work',max_member_bytes=4096)
            self.assertTrue(all(call.args[1]['id']==1 for call in reader.call_args_list))
            self.assertEqual(result['totals']['rows'],1)
            self.assertEqual(result['skipped_oversize_members'],2)
            self.assertEqual(result['skipped_oversize_bytes'],200000+len(oversized_script))
            self.assertEqual(result['decrypted_bytes'],len(raw))
            self.assertFalse(result['scan_complete'])
            self.assertEqual(result['payloads_verified'],1)
            self.assertTrue(any('per-resource budget' in d.get('issue','') for d in result['diagnostics']))
            self.assertEqual([d['name_hash'] for d in result['diagnostics']],[m[0]['name_hash'] for m in members[1:]])
            self.assertEqual(['main.txt.json'],[p.name for p in (root/'work/gt_input').iterdir()])
            self.assertFalse(pack(root/'work',root/'partial-pack')['source_scan_complete'])
            # The CLI must expose incomplete coverage, not print only row totals.
            with patch('sys.argv',['hx-text','extract','archive','output','--exe','game.exe']), \
                    patch('python.engines.kirikiri_hxv4_text.extract',return_value=result), \
                    patch('sys.stdout',new_callable=io.StringIO) as stdout:
                main()
            self.assertFalse(json.loads(stdout.getvalue())['scan_complete'])
            budget=root/'budget.xp3'
            budget.write_bytes(build([(dict(id=1,key=789,name_hash=name_hash('main.txt.scn'),
                                           path_hash=path_hash('scn/')),raw),
                                      (dict(id=2,key=790,name_hash=name_hash('filler.bin'),
                                            path_hash=path_hash('scn/')),b'\0'*4090)],keys))
            evidence['source_sha256']=hashlib.sha256(budget.read_bytes()).hexdigest()
            with patch('python.engines.kirikiri_hxv4_text.inspect',return_value=evidence):
                with self.assertRaisesRegex(ValueError,'cumulative scan budget'):
                    extract(budget,root/'not-executed.exe',root/'over-budget',max_member_bytes=4096,max_scan_bytes=4096)
                with self.assertRaisesRegex(ValueError,'scan budgets'):
                    extract(budget,root/'not-executed.exe',root/'bad-budget',max_member_bytes=0,max_scan_bytes=1024)
                with self.assertRaisesRegex(ValueError,'scan budgets'):
                    extract(budget,root/'not-executed.exe',root/'boolean-budget',max_member_bytes=True,max_scan_bytes=1024)


if __name__=='__main__': unittest.main()
