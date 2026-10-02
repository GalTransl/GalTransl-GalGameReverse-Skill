"""Synthetic QLIE fixtures only: keys, PE/DFM, compressed PACK and scripts."""
from copy import deepcopy
from dataclasses import replace
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest

from python.archives import qlie
from python.archives.qlie_keys import game_key_from_pe, icon_key_from_dfm
from python.archives.qlie_writer import hash13_tail, rebuild
from python.engines import qlie_imos as imos
from python.engines.qlie_extract import extract
from python.engines.qlie_repack import repack

FKEY = bytes((i * 3) % 256 for i in range(256))
GKEY = bytes((i * 7) % 256 for i in range(256))
PKEY = bytes((i * 11) % 256 for i in range(256))
SCRIPT = ('@@@AVG\\header.s\r\n@@MAIN\r\n\r\n'
          '【Alice】\r\n％voice01％\r\nHello\r\n\r\n'
          'Narration\r\n\r\n'
          '[spd,0][pc,A poem][spd]\r\n\r\n'
          '^select,Yes,,No\r\n\r\n')


def literal(data):
    result = b'1PC\xff\x01\0\0\0' + struct.pack('<I', len(data))
    # Skip nodes 0..127; emit identity 128; skip 129..255.
    for pos in range(0, len(data), 65535):
        chunk = data[pos:pos + 65535]
        result += b'\xff\x80\xfe' + struct.pack('<H', len(chunk)) + chunk
    return result


def dfm():
    def short(s):
        return bytes([len(s)]) + s
    child = short(b'TImage') + short(b'IconKeyImage')
    value = b'\x05TIcon' + GKEY
    child += short(b'Picture.Data') + b'\x0a' + struct.pack('<I', len(value)) + value + b'\0\0'
    return b'TPF0' + short(b'TForm1') + short(b'Form1') + b'\0' + child + b'\0'


def pe():
    form = dfm()
    rsrc = bytearray(256 + len(form))
    # root -> RCDATA -> named TFORM1 -> language -> data
    for at in (0, 24, 48):
        struct.pack_into('<H', rsrc, at + 14, 1)
    struct.pack_into('<II', rsrc, 16, 10, 0x80000000 | 24)
    struct.pack_into('<II', rsrc, 40, 0x80000000 | 96, 0x80000000 | 48)
    struct.pack_into('<II', rsrc, 64, 0, 72)
    struct.pack_into('<IIII', rsrc, 72, 0x1000 + 256, len(form), 0, 0)
    struct.pack_into('<H', rsrc, 96, 6)
    rsrc[98:110] = 'TFORM1'.encode('utf-16le')
    rsrc[256:] = form
    head = bytearray(512)
    head[:2] = b'MZ'
    struct.pack_into('<I', head, 0x3C, 0x80)
    head[0x80:0x84] = b'PE\0\0'
    struct.pack_into('<H', head, 0x86, 1)
    struct.pack_into('<H', head, 0x94, 224)
    opt = 0x98
    struct.pack_into('<H', head, opt, 0x10B)
    struct.pack_into('<I', head, opt + 92, 16)
    struct.pack_into('<II', head, opt + 112, 0x1000, len(rsrc))
    section = opt + 224
    head[section:section + 8] = b'.rsrc\0\0\0'
    struct.pack_into('<IIII', head, section + 8, len(rsrc), 0x1000, len(rsrc), 512)
    return bytes(head + rsrc)


def archive(files=None, *, bad_mapping=False, reverse_physical=False):
    files = files or [('scene.s', SCRIPT.encode('cp932')), ('image.bin', b'UNCHANGED_MEDIA')]
    files = [(qlie.PACK_KEY_NAME, PKEY), *files]
    key_blob = bytes((i * i + 17) % 256 for i in range(1024))
    arc_key = qlie.hash_v3(key_blob[:256]) & 0xFFFFFFF
    entries, encrypted = [], []
    for i, (name, data) in enumerate(files):
        packed = int(name.endswith(('.s', '.txt')))
        stored = literal(data) if packed else data
        entry = qlie.Entry(name, name.encode('cp932'), 0, len(stored), len(data), packed, 4, 0)
        cipher = qlie.encrypt(stored, entry, arc_key, mode='keyed', key_file=FKEY if i == 0 else PKEY, game_key=GKEY)
        entries.append(replace(entry, checksum=qlie.hash_v3(cipher)))
        encrypted.append(cipher)
    payload = bytearray()
    order = list(range(len(entries)))
    if reverse_physical:
        order.reverse()
    for i in order:
        entries[i] = replace(entries[i], offset=len(payload))
        payload.extend(encrypted[i])
    index_offset = len(payload)
    for e in entries:
        payload.extend(struct.pack('<H', len(e.raw_name)) + qlie.crypt_name(e.raw_name, arc_key))
        payload.extend(struct.pack('<QIIIII', e.offset, e.size, e.unpacked_size, e.packed, e.encryption, e.checksum))
    lookup = struct.pack('<H', len(entries))
    for i, entry in enumerate(entries):
        lookup += struct.pack('<H', len(entry.raw_name)) + entry.raw_name + struct.pack('<QI', i * 2, 0)
    lookup += bytes(255 * 2)
    lookup += struct.pack('<' + 'H' * len(entries), *([0] * len(entries) if bad_mapping else range(len(entries))))
    packed = literal(lookup)
    dummy = qlie.Entry('hash', b'hash', 0, len(packed), len(packed), 0, 1, 0)
    packed = qlie.encrypt(packed, dummy, 0x428, mode='legacy')
    tail = b'HashVer1.3' + bytes(6) + struct.pack('<IIII', 256, len(entries), len(entries) * 2, len(packed)) + packed
    tail += bytes(32) + struct.pack('<I', len(tail)) + key_blob
    return bytes(payload) + tail + b'FilePackVer3.0\0\0' + struct.pack('<IQ', len(entries), index_offset)


def read_script(data, name='scene.s'):
    stream = io.BytesIO(data)
    index = qlie.read_index(stream)
    entry = next(e for e in index.entries if e.name == name)
    return qlie.read_member(stream, index, entry, mode='keyed', key_file=PKEY, game_key=GKEY)


class QlieArchiveTests(unittest.TestCase):
    def test_crypto_vectors_and_remainder(self):
        entry = qlie.Entry('scene.s', b'scene.s', 0, 35, 35, 0, 4, 0)
        data = bytes(range(35))
        expected = bytes.fromhex('7465898970618d8deb3533daeb3533dafd167f56f50e476ef5f2f45eed022f36202122')
        self.assertEqual(qlie.decrypt(data, entry, 0x1234567, mode='legacy'), expected)
        options = dict(mode='keyed', key_file=bytes(range(256)), game_key=bytes(reversed(range(256))))
        expected = bytes.fromhex('71bd74973b4d0fda2f80bbebcdf0b0bbb1fa662287c6677e6fa4c4f2e924e8d6202122')
        self.assertEqual(qlie.decrypt(data, entry, 0x1234567, **options), expected)
        self.assertEqual(qlie.encrypt(expected, entry, 0x1234567, **options), data)
        with self.assertRaises(ValueError):
            qlie.decrypt(data, entry, 0, mode='keyed', key_file=FKEY)

    def test_compression_output_budget_truncation_and_cycles(self):
        data = bytes(range(256)) * 300
        self.assertEqual(qlie.decompress(literal(data), expected_size=len(data)), data)
        for value in (literal(data)[:-1], b'garbage'):
            with self.assertRaises(ValueError):
                qlie.decompress(value, expected_size=len(data))
        with self.assertRaises(ValueError):
            qlie.decompress(literal(data), expected_size=len(data), max_output=10)
        # 0 -> (1, 1), 1 -> (0, 0): reachable cycle, not an oversized output.
        table = b'\x01\x01\x01\x00\x00\xff\x82\xfc'
        malformed = b'1PC\xff\x01\0\0\0\x01\0\0\0' + table + b'\x01\0\0'
        with self.assertRaisesRegex(ValueError, 'cyclic'):
            qlie.decompress(malformed, expected_size=1)

    def test_index_checks_and_wrong_key(self):
        raw = archive()
        stream = io.BytesIO(raw)
        index = qlie.read_index(stream)
        self.assertEqual(read_script(raw), SCRIPT.encode('cp932'))
        with self.assertRaises(ValueError):
            qlie.read_index(stream, max_entries=1)
        with self.assertRaises(ValueError):
            qlie.read_index(stream, max_index_bytes=10)
        entry = index.entries[1]
        with self.assertRaises(ValueError):
            qlie.read_member(stream, index, entry, mode='keyed', key_file=FKEY, game_key=GKEY)
        corrupt = bytearray(raw)
        corrupt[entry.offset] ^= 1
        with self.assertRaisesRegex(ValueError, 'checksum'):
            qlie.read_member(io.BytesIO(corrupt), index, entry, mode='keyed', key_file=PKEY, game_key=GKEY)
        with self.assertRaises(ValueError):
            qlie.read_index(io.BytesIO(raw[:-1]))

    def test_original_and_changed_archive_roundtrip(self):
        for reverse in (False, True):
            with self.subTest(reverse_physical=reverse):
                raw = archive(reverse_physical=reverse)
                dest = io.BytesIO()
                rebuild(io.BytesIO(raw), dest, {'scene.s': SCRIPT.encode('cp932')}, mode='keyed', key_file=FKEY, game_key=GKEY)
                self.assertEqual(dest.getvalue(), raw)
                changed = (SCRIPT + '\r\nMore text, much longer.\r\n\r\n').encode('cp932')
                dest = io.BytesIO()
                result = rebuild(io.BytesIO(raw), dest, {'scene.s': changed}, mode='keyed', key_file=FKEY, game_key=GKEY)
                self.assertEqual(result['changed'], 1)
                self.assertEqual(read_script(dest.getvalue()), changed)
                before, after = qlie.read_index(io.BytesIO(raw)), qlie.read_index(dest)
                self.assertEqual(hash13_tail(io.BytesIO(raw), before), hash13_tail(dest, after))
                old_media, new_media = before.entries[-1], after.entries[-1]
                self.assertEqual(raw[old_media.offset:old_media.offset + old_media.size],
                                 dest.getvalue()[new_media.offset:new_media.offset + new_media.size])
                self.assertEqual(after.entries[1].packed, 0)

    def test_writer_rejects_bad_table_unknown_member_and_existing_output(self):
        for raw, edits, out in [(archive(bad_mapping=True), {}, io.BytesIO()),
                                (archive(), {'unknown.s': b'x'}, io.BytesIO()),
                                (archive(), {qlie.PACK_KEY_NAME: b'x'}, io.BytesIO()),
                                (archive(), {}, io.BytesIO(b'existing'))]:
            with self.assertRaises(ValueError):
                rebuild(io.BytesIO(raw), out, edits, mode='keyed', key_file=FKEY, game_key=GKEY)

    def test_static_pe_dfm_key_and_bounds(self):
        self.assertEqual(icon_key_from_dfm(dfm()), GKEY)
        self.assertEqual(game_key_from_pe(pe()), GKEY)
        for data in (pe()[:-1], b'MZ', bytes(4096)):
            with self.assertRaises(ValueError):
                game_key_from_pe(data)
        with self.assertRaises(ValueError):
            icon_key_from_dfm(dfm() + b'junk')


class QlieTextTests(unittest.TestCase):
    def test_name_scope_pc_empty_choice_and_preserving_identity(self):
        rows = imos.rows(SCRIPT)
        self.assertEqual(rows, [{'name': 'Alice', 'message': 'Hello'}, {'message': 'Narration'},
                               {'message': 'A poem'}, {'message': 'Yes'}, {'message': ''}, {'message': 'No'}])
        self.assertEqual(imos.patch(SCRIPT, rows), SCRIPT)
        rows[0] = {'name': 'エリス', 'message': 'Longer\nmessage'}
        rows[2]['message'] = 'New poem'
        result = imos.patch(SCRIPT, rows)
        self.assertIn('【Alice＠エリス】', result)
        self.assertIn('[spd,0][pc,New poem][spd]', result)
        self.assertIn('％voice01％', result)
        self.assertEqual(imos.rows(result), rows)

    def test_alias_and_multiline_spacer(self):
        script = '【Alice＠？？？】\r\nHello\r\nworld\r\n\r\n　\r\n\r\nNarration\r\n'
        rows = imos.rows(script)
        self.assertEqual(rows, [{'name': '？？？', 'message': 'Hello\nworld'}, {'message': 'Narration'}])
        self.assertEqual(imos.patch(script, rows), script)
        rows[0]['message'] = 'joined'
        with self.assertRaises(ValueError):
            imos.patch(script, rows)

    def test_injection_and_unknown_dialects(self):
        for i, text in [(0, '^command'), (0, '[newtag]'), (2, 'bad,parameter'), (3, 'new,choice')]:
            rows = imos.rows(SCRIPT)
            rows[i]['message'] = text
            with self.assertRaises(ValueError):
                imos.patch(SCRIPT, rows)
        for script in ('[unknown]text', '【Alice】\n\nHi', 'text\n\\go,label', 'text[pc,inner]'):
            with self.assertRaises(ValueError):
                imos.scan(script)


class QlieWorkflowTests(unittest.TestCase):
    def test_extract_translate_pack_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            game = Path(temp)
            (game / 'game.exe').write_bytes(pe())
            (game / 'key.fkey').write_bytes(FKEY)
            files = [('scenario/scene.s', SCRIPT.encode('cp932')), ('system.s', b'@@MAIN\r\n\\ret\r\n'),
                     ('avg/projectsetting.txt', b'FormatType=1\r\n'), ('avg/setting.txt', b'ReturnCode=[n]\r\n')]
            (game / 'a.pack').write_bytes(archive(files))
            (game / 'b.pack').write_bytes(archive([('scenario/scene.s', b'Another version\r\n')]))
            output = game / 'extract'
            report = extract(game, output, archives=['a.pack', 'b.pack'], exe='game.exe', key_file='key.fkey')
            self.assertEqual(report['counts']['exported_scripts'], 2)
            self.assertEqual(report['counts']['empty_scripts'], 1)
            self.assertEqual(len(list((output / 'gt_input').glob('*.json'))), 2)
            first = next(i for i in report['members'] if i.get('json') and i['archive'] == 'a.pack')
            rows = json.loads((output / first['json']).read_text(encoding='utf-8'))
            rows[0] = {'name': 'エリス', 'message': 'Longer message'}
            (output / 'gt_output' / Path(first['json']).name).write_text(json.dumps(rows), encoding='utf-8')
            result = repack(game, output, game / 'rebuilt')
            self.assertEqual(len(result['archives']), 1)
            self.assertEqual(result['archives'][0]['changed'], 1)
            script = read_script((game / 'rebuilt/a.pack').read_bytes(), 'scenario/scene.s').decode('cp932')
            self.assertEqual(imos.rows(script), rows)
            result = repack(game, output, game / 'roundtrip', source_roundtrip=True)
            for name in ('a.pack', 'b.pack'):
                self.assertEqual((game / name).read_bytes(), (game / 'roundtrip' / name).read_bytes())
            with self.assertRaises(FileExistsError):
                repack(game, output, game / 'rebuilt')
            with self.assertRaises(FileExistsError):
                extract(game, output, archives=['a.pack'], exe='game.exe', key_file='key.fkey')
            # Fresh parser locators, not arbitrary offsets from the manifest.
            path = output / first['manifest']
            manifest = json.loads(path.read_text(encoding='utf-8'))
            manifest['records'][0]['locator']['parts'][0]['start'] += 1
            path.write_text(json.dumps(manifest), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'locators'):
                repack(game, output, game / 'tampered')
            self.assertFalse((game / 'tampered').exists())


if __name__ == '__main__':
    unittest.main()
