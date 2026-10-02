"""Filter inverse/offset/corruption and common CLI integration regressions."""
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from python.archives.kirikiri_filters import transform, validate
from python.archives import kirikiri_xp3 as xp3
from python.engines.kirikiri_probe import recover_akabei, probe
from python.engines.kirikiri_kag import tokenize, attributes
from python.engines.kirikiri_extract import extract, pack
from test_kirikiri_senren import fixture_tree

SPECS=[{'algorithm':name} for name in ('none','hash','haikuo','exa','yuzu')]+[
    {'algorithm':'xor','key':93},{'algorithm':'stripe','key':173},{'algorithm':'akabei','seed':0x2f91de55}]


def png(pixel):
    def chunk(tag,data):return struct.pack('>I',len(data))+tag+data+struct.pack('>I',zlib.crc32(tag+data))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b'\0'+bytes(pixel)))+chunk(b'IEND',b'')


class FilterTests(unittest.TestCase):
    def test_direction_and_logical_offsets(self):
        data=bytes(range(256))*3;checksum=zlib.adler32(data)
        for spec in SPECS:
            encoded=transform(data,checksum,spec,encrypt=True)
            self.assertEqual(transform(encoded,checksum,spec),data)
            self.assertEqual(transform(encoded[:37],checksum,spec)+transform(encoded[37:],checksum,spec,offset=37),data)
        self.assertEqual(transform(bytes([0,255,42]),0,{'algorithm':'stripe','key':1}),bytes([2,255,44]))
        self.assertEqual(transform(bytes(5),0x12345678,{'algorithm':'exa'}),bytes([0x78,0x3c,0x9e,0xcf,0x67]))
        for spec in ({'algorithm':'xor'},{'algorithm':'hash','key':1},{'algorithm':'akabei','seed':True}):
            with self.assertRaises(ValueError):validate(spec)

    def test_all_filter_archive_roundtrips_and_wrong_key(self):
        files=[('dir/main.ks',b'\xff\xfe'+('*start\r\n本文[np]\r\n'*20).encode('utf-16le'))]
        for spec in SPECS:
            data=xp3.build(files,'plain',spec);stream=io.BytesIO(data);profile,entries=xp3.read_index(stream)
            self.assertEqual(xp3.read_member(stream,entries[0],profile,spec),files[0][1])
        with self.assertRaises(ValueError):xp3.read_member(stream,entries[0],profile,{'algorithm':'akabei','seed':1})

    def test_evidence_recovery_and_probe_does_not_adopt_candidate(self):
        spec={'algorithm':'akabei','seed':0x2f91de55}
        files=[('one.png',png((255,0,0))),('two.png',png((0,255,0))),('main.ks',b'\xff\xfe'+'*start\r\n本文[np]'.encode('utf-16le'))]
        raw=xp3.build(files,'plain',spec);stream=io.BytesIO(raw);_,es=xp3.read_index(stream)
        self.assertEqual(recover_akabei(stream,es)[0]['filter_spec'],spec)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'arbitrary.bin';path.write_bytes(raw)
            result=probe(path,recover=True)
            self.assertEqual(result['checksum_passed'],0)
            result=probe(path,filter_spec=spec,verify_repack=True)
            self.assertEqual(result['checksum_passed'],1)
            self.assertEqual(result['members'][0]['inner']['validation'],'lossless-lexical')
            self.assertEqual(result['archive_roundtrip']['members'],1)

    def test_filter_spec_persisted_for_scn_pack(self):
        raw=fixture_tree({'scenes':[{'texts':[[None,None,'本文',None,1,{}]]}]})
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);spec={'algorithm':'stripe','key':5}
            (root/'data.xp3').write_bytes(xp3.build([('main.scn',raw)],'plain',spec))
            report=extract(root,root/'work',filter_spec=spec,verify_edits=True)
            self.assertEqual(report['filter_spec'],spec)
            pack(root/'work',root/'packed')
            self.assertEqual((root/'packed/scenario.xp3').read_bytes(),(root/'work/rebuilt/roundtrip/scenario.xp3').read_bytes())

    def test_kag_lexical_preservation_and_dynamic_attributes(self):
        text=';comment\r\r\n*p0|\r\n@nm t="Name" s=voice\n[font face="a]b"]text[[literal[漢字\'かんじ][np]\n@iscript\n[not a tag\n@endscript\n'
        tokens=tokenize(text)
        self.assertEqual(''.join(t.raw for t in tokens),text)
        self.assertTrue(any(t.kind=='script' for t in tokens))
        name,attrs=attributes('@nm t="&variable" s=voice')
        self.assertEqual(name,'nm');self.assertTrue(attrs['t']['dynamic'])
        for text in ('[font face="oops]','@iscript\ncode','@endscript'):
            with self.assertRaises(ValueError):tokenize(text)


if __name__=='__main__':unittest.main()
