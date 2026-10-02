"""Static Hxv4 crypto vectors, bounded index and candidate validation."""
import io
import struct
import unittest
import zlib
from python.archives.kirikiri_hxv4 import (chacha,hchacha,derive,read_index,
    deserialize,name_hash,path_hash,triple32,siphash,index_tag,poly1305)
from python.archives.kirikiri_hxv4_static import PE,tjs_strings
from python.engines.kirikiri_hxv4_names import resolve
from python.archives.xp3 import MAGIC


def fixture():
    def obj(value):
        if isinstance(value,bytes):return b'\3'+struct.pack('>I',len(value))+value
        if isinstance(value,int):return b'\4'+struct.pack('>q',value)
        return b'\x81'+struct.pack('>I',len(value))+b''.join(map(obj,value))
    root=obj([bytes.fromhex(path_hash('')), [bytes.fromhex(name_hash('main.ks.scn')),[1,123]]])
    key=bytes(range(32));nonce=bytes(range(32));keys={'index_b':key,'nonce_b':nonce}
    plain=struct.pack('<I',len(root))+zlib.compress(root)
    ciphertext=chacha(plain,key,bytes(4)+nonce[16:24])
    blob=index_tag(ciphertext,key,bytes(4)+nonce[16:24])+ciphertext
    chunk=lambda tag,b:tag+struct.pack('<Q',len(b))+b
    alias='倁'.encode('utf-16le') # id 1: 0x5001
    info=struct.pack('<IQQH',0x80000000,3,3,1)+alias
    index=chunk(b'Hxv4',struct.pack('<QIH',22,len(blob),0))+chunk(b'File',
        chunk(b'info',info)+chunk(b'segm',struct.pack('<IQQQ',0,19,3,3))+chunk(b'adlr',struct.pack('<I',zlib.adler32(b'abc'))))
    at=22+len(blob);packed=zlib.compress(index)
    return MAGIC+struct.pack('<Q',at)+b'abc'+blob+b'\1'+struct.pack('<QQ',len(packed),len(index))+packed,keys


class HxTests(unittest.TestCase):
    def test_poly1305_rfc8439_and_index_authentication(self):
        key=bytes.fromhex('85d6be7857556d337f4452fe42d506a80103808afb0db2fd4abff6af4149f51b')
        self.assertEqual(poly1305(b'Cryptographic Forum Research Group',key).hex(),
                         'a8061dc1305136c6c22b8baf0c0127a9')
        raw,keys=fixture()
        for at in (22,38):
            damaged=bytearray(raw);damaged[at]^=1
            with self.assertRaisesRegex(ValueError,'authentication'):read_index(io.BytesIO(damaged),keys)
        empty=bytearray(raw);empty[22:38]=bytes(16)
        with self.assertRaisesRegex(ValueError,'authentication'):read_index(io.BytesIO(empty),keys)

    def test_crypto_vectors(self):
        self.assertEqual(chacha(bytes(16),bytes(32),bytes(12),0).hex(),'76b8e0ada0f13d90405d6ae55386bd28')
        self.assertEqual(hchacha(bytes(range(32)),bytes.fromhex('000000090000004a0000000031415927')).hex(),
                         '82413b4227b27bfed30e42508a877d73a0f9e4d58a74a853c12ec41326d3ecdc')
        self.assertEqual(triple32(0x281ff4b9),0x3389ba89)
        self.assertEqual(siphash(b''),0x1e924b9d737700d7)
        self.assertEqual(path_hash(''),'94D4A97C61498621')
        self.assertEqual(name_hash('004.共通－今後もよろしく.ks.scn'),
                         '4660141315215E3AD02E01A906A78439B4B376837246AA44B7FECAF9DBBC47C0')

    def test_key_derivation_upstream_vector(self):
        key=derive({'bootStrap':'BOOTSTRAPbootstrap0123456789','warning':'WARNINGwarning0123456789',
                    'params':bytes(list(range(11))*2).hex(),'archiveUniqueKey':'ArchiveUniqueKey0123456789','upperKey':'0011223344556677'})
        self.assertEqual(key['key'].hex(),'4fb07f17eb1d7d0f14fba645e067d5d90a973494f4161da962ee49ccfc9ad237')
        self.assertEqual(key['nonce_a'][:24].hex(),'c84f47adef9093396d421105bd8893c925b3853aef22d346')

    def test_index_and_names_are_independently_validated(self):
        data,keys=fixture();r=read_index(io.BytesIO(data),keys)
        self.assertEqual(r['mapped'],1)
        self.assertNotIn('name',r['files'][0])
        self.assertEqual(resolve(r['files'],['wrong.scn'])[0].get('name'),None)
        self.assertEqual(resolve(r['files'],['main.ks.scn'])[0]['name'],'main.ks.scn')
        for broken in (data[:-2],data[:11]):
            with self.assertRaises((ValueError,zlib.error)):read_index(io.BytesIO(broken),keys)
        bad=dict(keys,index_b=bytes(32))
        with self.assertRaises((ValueError,zlib.error)):read_index(io.BytesIO(data),bad)

    def test_malformed_objects_and_static_sources(self):
        for data in (b'\x81\xff\xff\xff\xff',b'\3\0\0\0\5a',b'\0trailing'):
            with self.assertRaises(ValueError):deserialize(data)
        with self.assertRaises(ValueError):PE(bytes(64))
        with self.assertRaises(ValueError):tjs_strings(b'TJS2100\0'+bytes(50))


if __name__=='__main__':unittest.main()
