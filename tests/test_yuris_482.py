"""Synthetic v482 YPF/YBN fixtures; no game assets."""
import copy
import io
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from python.archives.yuris_482 import murmur2, read_index, decode_member, pack_archive
from python.archives.yuris import SWAP_TABLE_00
from python.engines.yuris import read_command_list, toggle_ybn_sections
from python.engines.yuris_text import Profile, Scenario, commands_from, export_script, rebuild_script
from python.engines.yuris_extract import extract, rebuild, archive_members
from python.common.contract import dump_rows


def dictionary():
    body = b'WORD\0\x01\0\x03\0' + b'_\0\x01\0\x03\0' + b'IF\0\0'
    body += b'GOSUB\0\x31' + b''.join(b'P\0\0\0' for _ in range(49))
    return b'YSCM' + struct.pack('<III', 482, 4, 0) + body + b'error text\0' + bytes(range(256))


def scenario(text='【花子】「遅い」', shared=True):
    value = text.encode('cp932')
    commands = struct.pack('<BBH', 0, 1, 0) * (2 if shared else 1)
    attrs = struct.pack('<HHII', 0, 0, len(value), 0) * (2 if shared else 1)
    # A conditional pseudo-attribute target is not a string length.
    commands += struct.pack('<BBH', 2, 2, 0)
    attrs += struct.pack('<HHII', 0, 1, 0, 0) + struct.pack('<HHII', 0, 0, len(commands)//4, len(value))
    lines = bytes(len(commands))
    plain = b'YSTB' + struct.pack('<7I', 482, len(commands)//4, len(commands), len(attrs), len(value), len(lines), 0)
    return toggle_ybn_sections(plain + commands + attrs + value + lines, 0x96AC6FD3)


def archive(members):
    header_size = 32 + sum(27 + len(n.encode('cp932')) for n in members)
    head = bytearray(b'YPF\0' + struct.pack('<III', 482, len(members), header_size) + bytes(16))
    payload = bytearray()
    swaps = {}
    for a,b in zip(SWAP_TABLE_00[::2],SWAP_TABLE_00[1::2]): swaps[a]=b;swaps[b]=a
    for name, raw in members.items():
        n = name.encode('cp932'); stored = zlib.compress(raw)
        head.extend(struct.pack('<IB', murmur2(n), swaps.get(len(n),len(n)) ^ 255))
        head.extend(bytes(b ^ 255 for b in n))
        head.extend(struct.pack('<BBIIQI', 0, 1, len(raw), len(stored), header_size + len(payload), murmur2(stored)))
        payload.extend(stored)
    return bytes(head + payload) + b'opaque trailer'


class Yuris482Tests(unittest.TestCase):
    def setUp(self):
        self.ysc = dictionary()
        self.raw = scenario()
        self.profile = Profile(source_characters='遅', target_characters='迟')

    def test_murmur_known_upstream_vectors(self):
        self.assertEqual(murmur2(b'TEST'), 2297143075)
        self.assertEqual(murmur2(b'HELLO WORLD', 0x300), 3206656488)

    def test_yscm_diagnostics_and_opaque_table(self):
        self.assertEqual(len(commands_from(self.ysc)),4)
        with self.assertRaises(ValueError):read_command_list(self.ysc)
        with self.assertRaises(ValueError):commands_from(self.ysc[:-256] + b'x' + self.ysc[-256:])

    def test_shared_text_clone_and_control_targets_preserved(self):
        rows, meta = export_script(self.raw,self.ysc,self.profile)
        self.assertEqual(rows[0],{'name':'花子','message':'「迟い」'})
        self.assertEqual(rebuild_script(self.raw,self.ysc,rows,meta,self.profile),self.raw)
        rows[0]={'name':'太郎','message':'「迟い LONGER ABC」'}
        changed = rebuild_script(self.raw,self.ysc,rows,meta,self.profile)
        before=Scenario(self.raw,commands_from(self.ysc),self.profile.key)
        after=Scenario(changed,commands_from(self.ysc),self.profile.key)
        self.assertEqual(after.values[:len(before.values)],before.values)
        self.assertEqual(after.value(1),before.value(1))
        self.assertEqual(after.attrs[-1],before.attrs[-1])
        self.assertEqual(after.plain[-before.sizes[3]:],before.plain[-before.sizes[3]:])

    def test_manifest_controls_unencodable_and_key_rejected(self):
        rows, meta=export_script(self.raw,self.ysc,self.profile)
        for text in ('bad\nline','bad\\p','😀','遅'):
            t=copy.deepcopy(rows);t[0]['message']=text
            with self.assertRaises((ValueError,UnicodeError)):rebuild_script(self.raw,self.ysc,t,meta,self.profile)
        bad=copy.deepcopy(meta);bad['records'][0]['locator']['attribute']=1
        with self.assertRaises(ValueError):rebuild_script(self.raw,self.ysc,rows,bad,self.profile)
        with self.assertRaises(ValueError):export_script(self.raw,self.ysc,Profile(key=0))

    def test_empty_scripts_and_nonempty_eval_rejected(self):
        raw=scenario('',False);rows,_=export_script(raw,self.ysc)
        self.assertEqual(rows,[])
        p=bytearray(toggle_ybn_sections(self.raw,self.profile.key));p[32]=1
        bad=toggle_ybn_sections(bytes(p),self.profile.key)
        with self.assertRaises(ValueError):export_script(bad,self.ysc)

    def test_name_definition_and_choice_inner_length(self):
        def lit(text):
            value = ('"' + text + '"').encode('cp932')
            return b'M' + struct.pack('<H',len(value)) + value
        for target in ('ES.CHAR.NAME','ES.SEL.SET'):
            values = [lit(target),lit('花子'),lit('')]
            descriptors=bytearray();pool=bytearray()
            for aid,value in zip((0,33,34),values):
                descriptors.extend(struct.pack('<HHII',aid,3,len(value),len(pool)))
                pool.extend(value)
            plain=b'YSTB'+struct.pack('<7I',482,1,4,len(descriptors),len(pool),4,0)
            raw=toggle_ybn_sections(plain+struct.pack('<BBH',3,3,0)+descriptors+pool+bytes(4),self.profile.key)
            rows,meta=export_script(raw,self.ysc)
            self.assertEqual(rows,[{'message':'花子'}])
            result=rebuild_script(raw,self.ysc,[{'message':'太郎 ABC'}],meta)
            s=Scenario(result,commands_from(self.ysc),self.profile.key)
            value=s.value(1)
            self.assertEqual(struct.unpack_from('<H',value,1)[0],len(value)-3)
            self.assertEqual(s.value(0),values[0])

    def test_raw_control_sequence_roundtrip(self):
        raw=scenario('A\r\nB',False)
        p=bytearray(toggle_ybn_sections(raw,self.profile.key))
        cs,ds,vs,ls=struct.unpack_from('<IIII',p,12)
        start=32+cs+ds
        p[start:start+vs]=bytes(p[start:start+vs]).replace(b'\r\n',b'\xef\xf0')
        raw=toggle_ybn_sections(bytes(p),self.profile.key)
        rows,meta=export_script(raw,self.ysc)
        self.assertEqual(rows,[{'message':'A\nB'}])
        changed=rebuild_script(raw,self.ysc,[{'message':'AA\nBB'}],meta)
        self.assertIn(b'\xef\xf0',Scenario(changed,commands_from(self.ysc),self.profile.key).value(0))

    def test_archive_roundtrip_changed_sizes_and_hashes(self):
        raw=archive({'ysbin\\ysc.ybn':self.ysc,'ysbin\\yst00000.ybn':self.raw})
        self.assertEqual(pack_archive(raw,{}),raw)
        changed=pack_archive(raw,{'ysbin\\yst00000.ybn':self.raw+b'ABC'})
        self.assertEqual(archive_members(changed)['ysbin\\yst00000.ybn'],self.raw+b'ABC')
        self.assertTrue(changed.endswith(b'opaque trailer'))
        _,entries,_=read_index(io.BytesIO(changed))
        self.assertTrue(all(e.offset>=32 for e in entries))

    def test_archive_corruption_path_and_high_offset(self):
        raw=archive({'ysbin\\ysc.ybn':self.ysc})
        _,entries,_=read_index(io.BytesIO(raw));e=entries[0]
        bad=bytearray(raw);bad[e.offset+3]^=1
        with self.assertRaises(ValueError):archive_members(bytes(bad))
        bad=bytearray(raw);struct.pack_into('<Q',bad,e.field_offset+10,1<<32)
        with self.assertRaises(ValueError):read_index(io.BytesIO(bad))
        with self.assertRaises(ValueError):read_index(io.BytesIO(archive({'../bad':b'x'})))

    def test_workspace_translation_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'ysbin').mkdir();(root/'pac').mkdir()
            (root/'ysbin/ysc.ybn').write_bytes(self.ysc)
            (root/'ysbin/yst00000.ybn').write_bytes(self.raw)
            (root/'pac/update.ypf').write_bytes(archive({'ysbin\\ysc.ybn':self.ysc,'ysbin\\yst00000.ybn':self.raw}))
            report=extract(root,root/'work',archive='pac/update.ypf',loose='ysbin',smoke_test=True)
            self.assertEqual(report['counts']['rows'],2)
            rows,_=export_script(self.raw,self.ysc);rows[0]['message']='ABC'
            (root/'work/gt_output/yst00000.json').write_bytes(dump_rows(rows))
            result=rebuild(root/'work',root/'patch')
            self.assertEqual(result['translated_members'],['ysbin/yst00000.ybn'])
            self.assertEqual(archive_members((root/'patch/ysbin.ypf').read_bytes())['ysbin\\yst00000.ybn'],(root/'patch/ysbin/yst00000.ybn').read_bytes())
            with self.assertRaises(FileExistsError):extract(root,root/'work',archive='pac/update.ypf',loose='ysbin')


if __name__=='__main__':unittest.main()
