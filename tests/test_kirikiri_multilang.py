"""Localized SCN layouts, derived fields and untouched-language invariants."""
import json
from pathlib import Path
import tempfile
import unittest

from test_kirikiri_senren import fixture_tree
from python.archives import xp3
from python.engines.kirikiri_psb import Psb
from python.engines.kirikiri_scn import records, patch, fingerprint, save_message, controls
from python.engines.kirikiri_extract import extract, pack


def fixture(slot=1):
    message='[よみ,1]漢字\\n本文'
    local=[None,message]
    if slot==1: local.append(len(save_message(message.replace('\\n','\n'),False)))
    local += [save_message(message.replace('\\n','\n'),True),save_message(message.replace('\\n','\n'),False)]
    other=['Other','Other text',10] if slot==1 else ['Other','Other text']
    langs=[local,other]
    text=['actor',langs,None,1,{}] if slot==1 else ['actor',None,langs,None,1,{}]
    return fixture_tree({'scenes':[{'texts':[text], 'selects':[{'selidx':0},
        {'text':'選択','language':[None,{'text':'Choice'}],'target':'label'}]}],
        'untouched':message},share_nodes=True)


class MultilingualTests(unittest.TestCase):
    def test_literal_brackets_are_not_ruby_and_remain_editable(self):
        text = r'前文\[表示]後文[よみ,1]漢字'
        self.assertEqual(controls(text), [r'\[', ']', '[よみ,1]'])
        self.assertEqual(save_message(text, False), '前文[表示]後文漢字')
        self.assertEqual(save_message(text, True), '前文[表示]後文よみ')
        local = [None, text, 10, '前文[表示]後文よみ', '前文[表示]後文漢字']
        raw = fixture_tree({'scenes': [{'texts': [['actor', [local], None, 1, {}]]}]})
        p = Psb(raw); recs = records(p)
        self.assertEqual(patch(p, recs, [recs[0]['row']])[0], raw)
        rows = [dict(recs[0]['row'], message=r'译文\[更长的文字]后文[よみ,1]汉字')]
        rebuilt, paths = patch(p, recs, rows); q = Psb(rebuilt)
        self.assertEqual(records(q)[0]['row'], rows[0])
        self.assertEqual(fingerprint(p, paths), fingerprint(q, paths))
        self.assertEqual(controls(r'正文\[▼]'), [r'\[', ']'])
        for invalid in (r'正文\[未闭合', r'正文\[嵌套[x]]', r'正文\[含%r控制]'):
            with self.assertRaises(ValueError): controls(invalid)
        for changed in ('正文[表示]', '正文', r'正文\[表示]\[新增]'):
            with self.assertRaises(ValueError):
                patch(p, recs, [dict(recs[0]['row'], message=changed)])

    def test_both_layouts_preserve_other_language_and_controls(self):
        for slot in (1,2):
            for language in (0,1):
                raw=fixture(slot);p=Psb(raw);recs=records(p,language)
                self.assertEqual(len(recs),2)
                rows=[dict(r['row']) for r in recs]
                self.assertEqual(patch(p,recs,rows)[0],raw)
                rows[0]['message']='测试'*140+rows[0]['message']
                if language==1:rows[0]['name']='译名'
                rebuilt,paths=patch(p,recs,rows);q=Psb(rebuilt)
                self.assertEqual([r['row'] for r in records(q,language)],rows)
                self.assertEqual(records(p,1-language),records(q,1-language))
                self.assertEqual(fingerprint(p,paths),fingerprint(q,paths))
                bad=[dict(row) for row in rows];bad[0]['message']+='[new]'
                with self.assertRaises(ValueError):patch(p,recs,bad)
            with self.assertRaises(ValueError):records(Psb(raw),2)

    def test_known_ruby_normalization_and_unknown_cache_rejected(self):
        text='[よ・み,1]漢字'
        local=[None,text,'よみ','漢字']
        raw=fixture_tree({'scenes':[{'texts':[['actor',None,[local],None,1,{}]]}]})
        p=Psb(raw);recs=records(p)
        self.assertTrue(recs[0]['strip_ruby_dot'])
        self.assertEqual(patch(p,recs,[recs[0]['row']])[0],raw)
        rows=[dict(recs[0]['row'],message='前文'+text)]
        self.assertEqual(records(Psb(patch(p,recs,rows)[0]))[0]['row'],rows[0])
        local[2]='unexplained cache'
        with self.assertRaises(ValueError):records(Psb(fixture_tree({'scenes':[{'texts':[['actor',None,[local],None,1,{}]]}]})))

    def test_common_entrypoint_records_language_for_pack(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'script.xp3').write_bytes(xp3.build([('main.scn',fixture())],filter_name='none'))
            work=root/'work';report=extract(root,work,archives=('script.xp3',),language_index=1,verify_edits=True)
            self.assertEqual(report['language_index'],1)
            self.assertEqual(pack(work,root/'noop')['changed_files'],0)
            rows=json.loads((work/'gt_input/main.json').read_bytes());rows[0]['message']='译文'
            (work/'gt_output/main.json').write_text(json.dumps(rows),encoding='utf-8')
            self.assertEqual(pack(work,root/'translated')['changed_files'],1)

    def test_ruby_padding_normalization_stays_inside_reading(self):
        text='本文　[　よみ　,1]漢字　後文'
        local=[None,text,'本文　よみ　後文','本文　漢字　後文']
        raw=fixture_tree({'scenes':[{'texts':[['actor',None,[local],None,1,{}]]}]})
        p=Psb(raw); recs=records(p)
        self.assertTrue(recs[0]['trim_ruby_space'])
        self.assertEqual(patch(p,recs,[recs[0]['row']])[0],raw)
        rows=[dict(recs[0]['row'],message='译文'+text)]
        rebuilt,paths=patch(p,recs,rows); q=Psb(rebuilt)
        self.assertEqual(records(q)[0]['row'],rows[0])
        self.assertEqual(fingerprint(p,paths),fingerprint(q,paths))
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'script.xp3').write_bytes(xp3.build([('ruby.scn',raw)],filter_name='none'))
            work=root/'work'
            extract(root,work,archives=('script.xp3',),verify_edits=True)
            meta=json.loads((work/'metadata/ruby.json').read_bytes())
            self.assertTrue(meta['records'][0]['locator']['trim_ruby_space'])
            (work/'gt_output/ruby.json').write_text(json.dumps(rows),encoding='utf-8')
            self.assertEqual(pack(work,root/'packed')['changed_files'],1)
        local[2]='本文よみ後文'  # Body spacing cannot be normalized away.
        with self.assertRaisesRegex(ValueError,'scene=0, text=0, cache=0'):
            records(Psb(fixture_tree({'scenes':[{'texts':[['actor',None,[local],None,1,{}]]}]})))

    def test_structural_link_choices_are_preserved_and_reported(self):
        choice={'button':'yes','close':'true','selidx':0,'storage':'main.txt','target':'*next_go'}
        scenes=[{'texts':[['actor',None,'本文',None,1,{}]],'selects':[choice]}]
        raw=fixture_tree({'name':'main.txt','scenes':scenes,'untouched':'x'})
        p=Psb(raw);skipped=[];recs=records(p,skipped=skipped)
        self.assertEqual([r['kind'] for r in recs],['message'])
        self.assertEqual(skipped,[{'scene':0,'index':0,'keys':['button','close','selidx','storage','target']}])
        self.assertEqual(patch(p,recs,[r['row'] for r in recs])[0],raw)
        translated=[dict(r['row'],message='中文长度增长测试') for r in recs]
        rebuilt,paths=patch(p,recs,translated);q=Psb(rebuilt)
        self.assertEqual([r['row'] for r in records(q)],translated)
        self.assertEqual(fingerprint(p,paths),fingerprint(q,paths))
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'script.xp3').write_bytes(xp3.build([('main.txt.scn',raw)],filter_name='none'))
            work=root/'work';report=extract(root,work,archives=('script.xp3',),verify_edits=True)
            self.assertEqual(report['totals']['structural_choices'],1)
            self.assertEqual(report['exports'][0]['skipped_structural_choices'],skipped)
            self.assertEqual(pack(work,root/'noop')['changed_files'],0)
        for bad in ({'selidx':0,'caption':'表示'},{'button':'はい','selidx':0,'storage':'main.txt','target':'*go'},
                    {'selidx':0,'storage':'other.txt','target':'*go'},{'button':'yes','selidx':0,'target':'go'}):
            with self.assertRaisesRegex(ValueError,'choice missing text'):
                records(Psb(fixture_tree({'name':'main.txt','scenes':[{'texts':[],'selects':[bad]}]})))

    def test_structural_choices_validate_types_shape_and_language(self):
        route={'selidx':0,'storage':'main.txt','target':'*次へ','button':'yes','close':'true'}
        def script(choice):
            return Psb(fixture_tree({'name':'main.txt','scenes':[{'selects':[choice]}]}))
        invalid=[{}, {'selidx':'表示文字'}, {'selidx':None}, {'selidx':-1}, {'button':'Caption'},
                 {'close':'true'}, {'storage':'main.txt','target':'*go'}]
        invalid += [dict(route,selidx=v) for v in (None,-1,'0')]
        invalid += [dict(route,close=v) for v in (None,0,1,123,'yes')]
        invalid += [dict(route,target=v) for v in ('*','*next\n表示文字','*next caption','*go[cmd]')]
        invalid += [dict(route,language=[{}]),dict(route,language=[None])]
        for choice in invalid:
            with self.subTest(choice=choice), self.assertRaisesRegex(ValueError,'choice missing text'):
                records(script(choice))
        for language in (0,1,2):
            for choice in ({'selidx':0},route,{'selidx':3,'storage':'main.txt','target':'*jump'}):
                skipped=[];p=script(choice)
                self.assertEqual(records(p,language,skipped=skipped),[])
                self.assertEqual(skipped,[{'scene':0,'index':0,'keys':sorted(choice)}])
        # Real PSB boolean tags must not be mistaken for integer indexes.
        for key in ('selidx','close'):
            p=script(dict(route,**{key:None}))
            scene=p.object(p.root)['scenes'].value[0]
            choice=p.object(p.object(scene)['selects'].value[0])
            for tag in (2,3):
                raw=bytearray(p.data);raw[choice[key].pos]=tag
                if key=='selidx':
                    with self.assertRaises(ValueError):records(Psb(bytes(raw)))
                else:self.assertEqual(records(Psb(bytes(raw))),[])

    def test_structural_only_file_is_counted_without_empty_json(self):
        route={'selidx':0,'storage':'links.txt','target':'*next'}
        empty=fixture_tree({'name':'links.txt','scenes':[{'selects':[{'selidx':0},route]}]})
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'script.xp3').write_bytes(xp3.build([('text.scn',fixture()),('links.scn',empty)],filter_name='none'))
            work=root/'work'
            report=extract(root,work,archives=('script.xp3',),language_index=1,verify_edits=True)
            self.assertEqual(report['totals']['structural_choices'],3) # one in text, two in links
            self.assertEqual(len(report['non_target'][0]['skipped_structural_choices']),2)
            self.assertEqual(report['non_target'][0]['archive'],'script.xp3')
            self.assertFalse((work/'gt_input/links.json').exists())
            self.assertEqual(pack(work,root/'packed')['changed_files'],0)

    def test_localized_tail_flag_voice_list_and_image_alt(self):
        for voice in (None,[{'voice':'v001'}]):
            text=['actor',[[None,'正文',2]],voice,230,{},0]
            image=['actor',[[None,'%i1&stamp_example;',1,'画像']],None,226,{},0]
            raw=fixture_tree({'scenes':[{'texts':[text,image]}]})
            p=Psb(raw); recs=records(p)
            self.assertEqual([r['kind'] for r in recs],['message','image-alt'])
            self.assertEqual(patch(p,recs,[r['row'] for r in recs])[0],raw)
            rows=[dict(r['row'],message='译文'+r['row']['message']) for r in recs]
            rebuilt,paths=patch(p,recs,rows); q=Psb(rebuilt)
            self.assertEqual([r['row'] for r in records(q)],rows)
            self.assertEqual(fingerprint(p,paths),fingerprint(q,paths))
            # Unknown fourth local fields and unsupported tail flags still fail.
            image[1][0][1]='ordinary text'
            with self.assertRaises(ValueError):
                records(Psb(fixture_tree({'scenes':[{'texts':[image]}]})))
            text[-1]=1
            with self.assertRaises(ValueError):
                records(Psb(fixture_tree({'scenes':[{'texts':[text]}]})))


if __name__=='__main__':unittest.main()
