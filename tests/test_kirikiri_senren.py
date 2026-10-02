"""Synthetic Senren XP3 and PSB/SCN regression fixtures; no game dialogue."""
import io
import struct
import unittest
import zlib
import json
from pathlib import Path
import tempfile

from python.archives.kirikiri_senren import build, read_index, read_member, default_cipher, program
from python.engines.kirikiri_psb import Psb, array
from python.engines.kirikiri_scn import records, patch, fingerprint, save_message
from python.engines.kirikiri_scn import controls
from python.engines.kirikiri_extract import extract, pack


def fixture_tree(tree, *, share_nodes=False, version=3, zero_header_length=False):
    keys = sorted({k for d in dictionaries(tree) for k in d})
    trie = {}
    for index, key in enumerate(keys):
        node = trie
        for b in key.encode('utf-8'): node = node.setdefault(b, {})
        node[0] = index
    bases = [0]; parents = [0xffffffff]; used = {0}
    def grow(i):
        while len(bases) <= i: bases.append(0); parents.append(0xffffffff)
    def assign(node, index):
        first = 1
        while any(first+b in used for b in node): first += 1
        grow(index); bases[index] = first
        for b in node: used.add(first+b);grow(first+b);parents[first+b]=index
        for b,child in node.items():
            if b == 0:bases[first]=child
            else:assign(child,first+b)
    assign(trie,0)
    names = array(bases)+array(parents)
    strings=[]
    def node(value):
        if value is None:return b'\x01'
        if isinstance(value,str):
            if value not in strings:strings.append(value)
            index=strings.index(value);width=max(1,(index.bit_length()+7)//8)
            return bytes([20+width])+index.to_bytes(width,'little')
        if isinstance(value,int):return b'\x08'+struct.pack('<i',value)
        if isinstance(value,dict):
            ordered=sorted(value,key=keys.index);chunks=[node(value[k]) for k in ordered]
            prefix=b'\x21'+array([keys.index(k) for k in ordered])
        else:chunks=[node(v) for v in value];prefix=b'\x20'
        offsets=[];length=0;stored=[];seen={}
        for chunk in chunks:
            if share_nodes and chunk in seen:offsets.append(seen[chunk])
            else:
                offsets.append(length);seen[chunk]=length;length+=len(chunk);stored.append(chunk)
        return prefix+array(offsets)+b''.join(stored)
    root=node(tree);pool=bytearray();offsets=[]
    for s in strings:offsets.append(len(pool));pool.extend(s.encode('utf-8')+b'\0')
    header_size=44 if version==3 else 40
    indices=array(offsets);root_at=header_size+len(names);strings_at=root_at+len(root);pool_at=strings_at+len(indices)
    co=pool_at+len(pool);cl=co+len(array([]));cd=cl+len(array([]))
    header=struct.pack('<8I',0 if zero_header_length else header_size,header_size,strings_at,pool_at,co,cl,cd,root_at)
    return b'PSB\0'+struct.pack('<HH',version,0)+header+(struct.pack('<I',zlib.adler32(header)) if version==3 else b'')+names+root+indices+pool+array([])*2


def dictionaries(value):
    if isinstance(value,dict):
        yield value
        for v in value.values():yield from dictionaries(v)
    elif isinstance(value,list):
        for v in value:yield from dictionaries(v)


def scene_fixture():
    text='[よ,1]漢字の試験'
    return fixture_tree({'scenes':[{'texts':[
        ['actor',None,'本文',None,1,{}],
        ['actor','表示名',text,None,2,{},None,'よの試験','漢字の試験']],
        'selects':[{'text':'選択','target':'label'}]}], 'unchanged':'本文'})


class SenrenTests(unittest.TestCase):
    def test_encrypted_archive_roundtrip_and_hash_failure(self):
        cipher=default_cipher();data=scene_fixture()
        archive=build([('scn/a.ks.scn',data),('b.ks.scn',b'B'*70000)],cipher)
        stream=io.BytesIO(archive);es=read_index(stream)
        self.assertEqual([read_member(stream,e,cipher) for e in es],[data,b'B'*70000])
        damaged=bytearray(archive);damaged[es[0].segments[0][1]+3]^=1
        with self.assertRaises(ValueError):read_member(io.BytesIO(damaged),es[0],cipher)
        for seed in range(128):self.assertTrue(program(seed))

    def test_psb_noop_growth_and_shared_string_reference(self):
        data=scene_fixture();p=Psb(data);recs=records(p);rows=[r['row'] for r in recs]
        self.assertEqual(patch(p,recs,rows)[0],data)
        rows[0]['message']='增长的中文正文';rows[1]['name']='新显示名'
        rows[1]['message']='中文[よ,1]汉字正文';rows[2]['message']='新的选择'
        out,edits=patch(p,recs,rows);q=Psb(out)
        self.assertEqual([r['row'] for r in records(q)],rows)
        self.assertEqual(fingerprint(p,edits),fingerprint(q,edits))
        self.assertEqual(q.text(q.object(q.root)['unchanged']),'本文')

    def test_invalid_controls_names_and_psb_header(self):
        for change in ('name','control'):
            p=Psb(scene_fixture());r=records(p);rows=[dict(v['row']) for v in r]
            if change=='name':rows[0]['name']='改名'
            else:rows[1]['message']='missing ruby'
            with self.assertRaises(ValueError):patch(p,r,rows)
        damaged=bytearray(scene_fixture());damaged[40]^=1
        with self.assertRaises(ValueError):Psb(bytes(damaged))
        with self.assertRaises(ValueError):Psb(scene_fixture()[:-1])
        with self.assertRaises(ValueError):controls('new %unknown command')
        with self.assertRaises(ValueError):controls('new #color syntax')

    def test_same_physical_node_can_have_distinct_replacements(self):
        p=Psb(fixture_tree({'a':'same','b':'same'},share_nodes=True))
        self.assertEqual(p.root.value[0][1].pos,p.root.value[1][1].pos)
        q=Psb(p.patch({(0,):'中文新文本'}))
        self.assertEqual(q.text(q.object(q.root)['a']),'中文新文本')
        self.assertEqual(q.text(q.object(q.root)['b']),'same')

    def test_ruby_length_emphasis_and_cache_generation(self):
        self.assertEqual(save_message('[りゅう,1]龍成[・]君',True),'りゅう君')
        self.assertEqual(save_message('[りゅう,1]龍成[・]君',False),'龍成君')
        self.assertEqual(save_message('%f$font$;#123456;本文%r\n',True),'本文')
        with self.assertRaises(ValueError):save_message('[ruby,3]a',True)

    def test_workspace_translation_pack_and_manifest_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);game=root/'game';game.mkdir();cipher=default_cipher()
            for name,member in [('data.xp3','scn/test.ks.scn'),('patch.xp3','test.ks.scn')]:
                (game/name).write_bytes(build([(member,scene_fixture())],cipher))
            work=root/'work';result=extract(game,work,archives=('data.xp3','patch.xp3'),overlay='basename',verify_edits=True)
            self.assertEqual(result['totals']['rows'],3)
            self.assertEqual(result['exports'][0]['archive'],'patch.xp3')
            with self.assertRaises(FileExistsError):extract(game,work)
            result=pack(work,root/'unchanged');self.assertEqual(result['changed_files'],0)
            rows=json.loads((work/'gt_input/test.ks.json').read_bytes());rows[0]['message']='中文变长测试'
            (work/'gt_output/test.ks.json').write_text(json.dumps(rows),encoding='utf-8')
            result=pack(work,root/'translated');self.assertEqual(result['changed_files'],1)
            path=work/'metadata/test.ks.json';manifest=json.loads(path.read_bytes())
            manifest['records'][0]['locator']['message']=[99]
            path.write_text(json.dumps(manifest),encoding='utf-8')
            with self.assertRaises(ValueError):pack(work,root/'invalid')
            self.assertFalse((root/'invalid').exists())


if __name__=='__main__':unittest.main()
