"""Synthetic KAG pages, inline controls, names, choices and encrypted archives."""
import json
from pathlib import Path
import tempfile
import unittest
from python.archives import kirikiri_xp3 as xp3
from python.engines.kirikiri_kag_text import export_script,rebuild_script,parse
from python.engines.kirikiri_kag_extract import extract,pack
from python.common.contract import dump_rows


def raw(text):return b'\xff\xfe'+text.encode('utf-16le')

SAMPLE='''; comment
*p1|
@nm t="人物" s=voice01
前文[r]
; private developer comment
[漢字'よみ]本文[wait time=1]。[np]
*p2|
地の文。[np]
@exlink txt="選択肢" target="*next" exp="f.x=true"
@jump storage="next.ks"
'''.replace('\n','\r\n')


class KagTextTests(unittest.TestCase):
    def test_names_pages_ruby_choices_comments_and_roundtrip(self):
        source=raw(SAMPLE);rows,meta=export_script(source)
        self.assertEqual(len(rows),3)
        self.assertEqual(rows[0],{'name':'人物','message':"前文[r]\n[漢字'よみ]本文[wait time=1]。"})
        self.assertNotIn('name',rows[1]);self.assertEqual(rows[2],{'message':'選択肢'})
        self.assertEqual(rebuild_script(source,rows,meta),source)
        changed=[dict(r,message='中文'+r['message']) for r in rows]
        changed[0]['name']='姓名';changed[0]['message']=changed[0]['message'].replace('漢字','汉字')
        result=rebuild_script(source,changed,meta)
        self.assertEqual(export_script(result)[0],changed)
        text=result.decode('utf-16')
        for untouched in ['; private developer comment\r\n','s=voice01','target="*next" exp="f.x=true"','@jump storage="next.ks"']:
            self.assertIn(untouched,text)

    def test_injection_controls_and_tampering_rejected(self):
        source=raw(SAMPLE);rows,meta=export_script(source)
        for message in [';comment','@eval exp="1"',rows[0]['message'].replace('time=1','time=2'),
                        rows[0]['message'].replace('よみ','new'), rows[0]['message'].replace('\n',''),
                        rows[0]['message']+'[emb exp="1"]']:
            changed=[dict(r) for r in rows];changed[0]['message']=message
            with self.subTest(message=message),self.assertRaises(ValueError):rebuild_script(source,changed,meta)
        changed=[dict(r) for r in rows];changed[2]['message']='" target="evil'
        with self.assertRaises(ValueError):rebuild_script(source,changed,meta)
        bad=json.loads(json.dumps(meta));bad['records'][0]['locator']['message'][0]+=1
        with self.assertRaises(ValueError):rebuild_script(source,rows,bad)
        with self.assertRaises(ValueError):rebuild_script(source+b'\0\0',rows,meta)

    def test_macro_script_blocks_empty_and_unclosed_pages(self):
        source=raw('@macro name="test"\nignored[np]\n@endmacro\n@iscript\nignored[np]\n@endscript\n')
        self.assertEqual(export_script(source)[0],[])
        for text in ['@nm t="&f.name"\n本文[np]','本文\n*next|\n','[unknown]本文[np]',
                     '@nm t="名前"\n*next|\n本文[np]','@macro name="x"\n']:
            with self.subTest(text=text),self.assertRaises(ValueError):parse(raw(text))

    def test_archive_workspace_pack_changed_translation_and_no_overwrite(self):
        spec={'algorithm':'akabei','seed':12345}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=raw(SAMPLE)
            archive=xp3.build([('scenario/main.ks',source),('system.ks',raw('@jump storage="main.ks"'))],'plain',spec)
            (root/'data.bin').write_bytes(archive);work=root/'work'
            report=extract(root,work,archives=['data.bin'],filter_spec=spec)
            self.assertEqual(report['counts'],{'files':1,'rows':3,'choices':1,'named':1})
            rows,_=export_script(source);rows[1]['message']='中文旁白。'
            (work/'gt_output/main.json').write_bytes(dump_rows(rows))
            packed=pack(work,root/'out',flat=True)
            self.assertEqual(packed['changed_members'],['scenario/main.ks'])
            with (root/'out/patch.xp3').open('rb') as f:
                profile,es=xp3.read_index(f);self.assertEqual([e.name for e in es],['main.ks'])
                self.assertEqual(export_script(xp3.read_member(f,es[0],profile,spec))[0],rows)
            self.assertEqual((root/'data.bin').read_bytes(),archive)
            with self.assertRaises(FileExistsError):pack(work,root/'out')
            (work/'gt_output/unknown.json').write_text('[]')
            with self.assertRaises(ValueError):pack(work,root/'bad')
            self.assertFalse((root/'bad').exists())


if __name__=='__main__':unittest.main()
