import copy
import struct
import unittest
import tempfile
from pathlib import Path
from python.engines.systemc_txd import export_table,inject_table,read_table


def fixture():
    text='花子,「こんにちは」\\n次の行'.encode('utf-8')
    ptr=b'PTR '+struct.pack('<III',1,0,0)+struct.pack('<III',17,0,len(text))
    act=' ***SC_A0000_00\r\n花子　（０００１）[17]\r\n「こんにちは」\r\n次の行\r\n'
    dat=bytes(80)+struct.pack('<19i',1,4,0,0,0,*([0]*14))
    return {'ACT_A_JA.TXD':text,'ACT_A_JA.PTR':ptr,'ACT_A.txt':act.encode('utf-8'),
            'ACT_A.DAT':struct.pack('<I',1)+dat,'charaid.tbl':'花子 1\r\nナレーション 0\r\n'.encode('utf-8'),
            'A0000_00.spt':struct.pack('<I8i',1,1,1,1,-1,1,3,7,17)}


class TxdTests(unittest.TestCase):
    def test_workspace_pack_and_no_overwrite(self):
        from tests.test_systemc import archive
        from python.engines.systemc_txd_extract import extract,pack
        from python.common.contract import dump_rows
        from python.archives.systemc import unpack_fpk
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);m=fixture();raw=archive(m);(root/'data.fpk').write_bytes(raw)
            report=extract(root,root/'work',verify_edits=True)
            self.assertEqual(report['rows'],1)
            rows=[{'name':'姓名','message':'测试\n第二行'}]
            (root/'work/gt_output/ACT_A_JA.json').write_bytes(dump_rows(rows))
            pack(root/'work',root/'patch')
            _,result=unpack_fpk((root/'patch/data.fpk').read_bytes())
            self.assertEqual(read_table(result['ACT_A_JA.TXD'],result['ACT_A_JA.PTR'])[1],rows)
            self.assertEqual(result['A0000_00.spt'],m['A0000_00.spt'])
            with self.assertRaises(FileExistsError):extract(root,root/'work')

    def test_roundtrip_chinese_name_and_byte_lengths(self):
        m=fixture();rows,meta=export_table('ACT_A_JA',m)
        self.assertEqual(rows,[{'name':'花子','message':'「こんにちは」\n次の行'}])
        self.assertTrue(all(v==m[k] for k,v in inject_table('ACT_A_JA',m,rows,meta).items()))
        changed=[{'name':'测试姓名','message':'「中文文本」\n第二行'}]
        r=inject_table('ACT_A_JA',m,changed,meta)
        ptr,actual=read_table(r['ACT_A_JA.TXD'],r['ACT_A_JA.PTR'])
        self.assertEqual(actual,changed);self.assertEqual(ptr[0],(17,0,len(r['ACT_A_JA.TXD'])))
        self.assertEqual(set(r),{'ACT_A_JA.TXD','ACT_A_JA.PTR'})

    def test_bad_pointer_id_and_compiled_binding(self):
        for offset in (1,100000):
            m=fixture();p=bytearray(m['ACT_A_JA.PTR']);struct.pack_into('<I',p,20,offset);m['ACT_A_JA.PTR']=bytes(p)
            with self.assertRaises(ValueError):export_table('ACT_A_JA',m)
        m=fixture();b=bytearray(m['A0000_00.spt']);struct.pack_into('<i',b,32,18);m['A0000_00.spt']=bytes(b)
        with self.assertRaises(ValueError):export_table('ACT_A_JA',m)

    def test_controls_manifest_and_name_separator(self):
        m=fixture();rows,meta=export_table('ACT_A_JA',m)
        for row in ({'name':'a,b','message':rows[0]['message']},{'name':'花子','message':'lost newline'},
                    {'name':'花子','message':'$NEW\ntext'}):
            with self.assertRaises(ValueError):inject_table('ACT_A_JA',m,[row],meta)
        bad=copy.deepcopy(meta);bad['records'][0]['locator']['text_id']=99
        with self.assertRaises(ValueError):inject_table('ACT_A_JA',m,rows,bad)

    def test_unreferenced_runtime_record_is_preserved_not_exported(self):
        m=fixture();extra=',未使用'.encode('utf-8');n=len(m['ACT_A_JA.TXD'])
        m['ACT_A_JA.TXD']+=extra;p=bytearray(m['ACT_A_JA.PTR']);struct.pack_into('<I',p,4,2)
        p.extend(struct.pack('<III',819,n,len(extra)));m['ACT_A_JA.PTR']=bytes(p)
        rows,meta=export_table('ACT_A_JA',m)
        self.assertEqual(meta['settings']['unreferenced_ids'],[819]);self.assertEqual(len(rows),1)
        rows[0]['message']='长文本\n二行'
        r=inject_table('ACT_A_JA',m,rows,meta)
        records,actual=read_table(r['ACT_A_JA.TXD'],r['ACT_A_JA.PTR'])
        self.assertEqual(records[1][0],819);self.assertEqual(actual[1],{'message':'未使用'})


if __name__=='__main__':unittest.main()
