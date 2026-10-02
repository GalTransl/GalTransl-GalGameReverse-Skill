"""Hx resource boundaries, identity preservation, encrypted rebuild and rejection."""
import io
import struct
import unittest
import zlib
from python.archives.kirikiri_hxv4 import derive, read_index, name_hash, path_hash
from python.archives.kirikiri_hxv4_payload import Cipher, build, read_member, build_flat_patch
from python.engines.kirikiri_hxv4_recover import script_names
from test_kirikiri_senren import fixture_tree


def keys(flags=128):
    params = bytes(range(8))+bytes(range(6))+bytes(range(3))+bytes([flags])+struct.pack('<HH', 1023, 400)
    return derive(dict(bootStrap='test', warning='test warning', params=params.hex(), archiveUniqueKey='{test}'))


def entry(ident=1):
    return dict(id=ident, key=-123456789, name_hash=name_hash('main.ks.scn'), path_hash=path_hash(''))


class PayloadTests(unittest.TestCase):
    def test_flat_patch_relocates_hash_directory_and_preserves_filter_identity(self):
        k = keys(); e = dict(entry(), path_hash=path_hash('scn/'))
        raw = b'edited resource'
        stream = io.BytesIO(build_flat_patch([(e,raw,'main.ks.scn')],k))
        result = read_index(stream,k)['files'][0]
        self.assertEqual(result['path_hash'],path_hash(''))
        self.assertNotEqual(result['path_hash'],e['path_hash'])
        for key in ('id','key','name_hash'): self.assertEqual(result[key],e[key])
        self.assertEqual(read_member(stream,result,Cipher(k)),raw)
        for name in ('scn/main.ks.scn','wrong.scn'):
            with self.assertRaises(ValueError): build_flat_patch([(e,raw,name)],k)

    def test_offset_equivalence_and_both_random_variants(self):
        raw = bytes(range(256))*300
        for flags in (0, 1, 128, 129):
            cipher = Cipher(keys(flags))
            for ident in (1, 0x100000001):
                e = entry(ident); encrypted = cipher.transform(raw, e)
                self.assertNotEqual(encrypted, raw)
                self.assertEqual(cipher.transform(encrypted, e), raw)
                cuts = (0, 7, 16, 99, 400, 1423, 65535, len(raw))
                chunks = [cipher.transform(raw[a:b], e, a) for a,b in zip(cuts, cuts[1:])]
                self.assertEqual(b''.join(chunks), encrypted)

    def test_archive_roundtrip_edits_and_corruption(self):
        k = keys(); cipher = Cipher(k)
        for flag in (0, 1):
            for raw in (b'', b'original', b'changed variable length'*10000):
                e = entry(0x100000001)
                archive = build([(e,raw)], k, hx_flags=flag)
                stream = io.BytesIO(archive); parsed = read_index(stream, k)['files'][0]
                for field in e: self.assertEqual(e[field], parsed[field])
                self.assertEqual(read_member(stream, parsed, cipher), raw)
                broken = dict(parsed, checksum=parsed['checksum'] ^ 1)
                with self.assertRaisesRegex(ValueError, 'checksum'):
                    read_member(stream, broken, cipher)
                broken = dict(parsed, flags=123)
                with self.assertRaises(ValueError): read_member(stream, broken, cipher)
        for members in ([(entry(), b'a')]*2, [({}, b'a')]):
            with self.assertRaises(ValueError): build(members, k)
        with self.assertRaises(ValueError): build([(entry(), b'too big')], k, max_total=2)
        with self.assertRaises(ValueError): Cipher(dict(k, params=bytes(22)))

    def test_mdf_candidates_are_structurally_parsed(self):
        raw = fixture_tree({'name':'main.ks','scenes':[], 'other':'next.txt'})
        wrapped = b'mdf\0'+struct.pack('<I',len(raw))+zlib.compress(raw)
        self.assertEqual(script_names(wrapped), {'main.ks', 'main.ks.scn', 'next.txt', 'next.txt.scn'})
        with self.assertRaises(ValueError): script_names(wrapped[:-3])
        self.assertEqual(script_names(b'unknown header main.ks'), set())


if __name__ == '__main__': unittest.main()
