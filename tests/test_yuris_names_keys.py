"""Synthetic tests: YSTL compile-list naming, section-key selection and the v487/v488 workspace."""
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from python.archives.yuris import SWAP_TABLE_00
from python.archives.yuris_482 import murmur2
from python.common.contract import dump_rows
from python.engines.yuris import toggle_ybn_sections
from python.engines.yuris_extract import archive_members, extract, rebuild
from python.engines.yuris_names import json_names, read_script_list
from python.engines.yuris_text import DEFAULT_KEY, commands_from, export_script, select_key, Profile

KEY = 0x13572468


def dictionary(version=488):
    body = b'WORD\0\x01\0\x03\0' + b'_\0\x01\0\x03\0' + b'IF\0\0'
    body += b'GOSUB\0\x31' + b''.join(b'P\0\0\0' for _ in range(49))
    return b'YSCM' + struct.pack('<III', version, 4, 0) + body + b'error text\0' + bytes(range(256))


def scene(texts, *, version=488, key=KEY):
    """One WORD instruction per text; the first descriptor points at pool offset 0."""
    commands, descriptors, pool = bytearray(), bytearray(), bytearray()
    for text in texts:
        value = text.encode('cp932')
        commands.extend(struct.pack('<BBH', 0, 1, 0))
        descriptors.extend(struct.pack('<HHII', 0, 0, len(value), len(pool)))
        pool.extend(value)
    plain = b'YSTB' + struct.pack('<7I', version, len(texts), len(commands), len(descriptors),
                                  len(pool), len(commands), 0)
    return toggle_ybn_sections(plain + commands + descriptors + pool + bytes(len(commands)), key)


def script_list(paths, version=488, tail=b''):
    data = bytearray(b'YSTL' + struct.pack('<II', version, len(paths)))
    for index, path in enumerate(paths):
        encoded = path.encode('cp932')
        data += struct.pack('<II', index, len(encoded)) + encoded + bytes(range(20))
    return bytes(data) + tail


def archive(members, version=487):
    header_size = 32 + sum(27 + len(n.encode('cp932')) for n in members)
    head = bytearray(b'YPF\0' + struct.pack('<III', version, len(members), header_size) + bytes(16))
    payload, swaps = bytearray(), {}
    for a, b in zip(SWAP_TABLE_00[::2], SWAP_TABLE_00[1::2]):
        swaps[a], swaps[b] = b, a
    for name, raw in members.items():
        n, stored = name.encode('cp932'), zlib.compress(raw)
        head.extend(struct.pack('<IB', murmur2(n), swaps.get(len(n), len(n)) ^ 255))
        head.extend(bytes(b ^ 255 for b in n))
        head.extend(struct.pack('<BBIIQI', 0, 1, len(raw), len(stored), header_size + len(payload), murmur2(stored)))
        payload.extend(stored)
    return bytes(head + payload)


class ScriptListTests(unittest.TestCase):
    def test_layout_is_consumed_exactly(self):
        paths = ['data\\script\\名前.txt', 'data\\script\\story\\ep01.txt']
        self.assertEqual(read_script_list(script_list(paths)), tuple(paths))
        self.assertEqual(read_script_list(script_list(paths, version=482)), tuple(paths))

    def test_unknown_or_inconsistent_layouts_are_rejected(self):
        paths = ['a.txt', 'b.txt']
        for data in (script_list(paths, version=300), script_list(paths, tail=b'x'),
                     script_list(paths)[:-3], b'YSTX' + script_list(paths)[4:]):
            with self.subTest(head=data[:8]), self.assertRaises(ValueError):
                read_script_list(data)
        swapped = bytearray(script_list(paths))
        struct.pack_into('<I', swapped, 12, 1)
        with self.assertRaises(ValueError):
            read_script_list(bytes(swapped))

    def test_json_names_prefer_original_and_disambiguate(self):
        sources = ['ysbin/yst00000.ybn', 'ysbin/yst00001.ybn', 'ysbin/yst00002.ybn', 'ysbin/yst00003.ybn']
        paths = ('s\\start.txt', 'a\\ep.txt', 'b\\EP.txt', '')
        names = json_names(sources, paths)
        self.assertEqual(names[sources[0]], {'json': 'start.json', 'naming': 'original', 'original_path': 's\\start.txt'})
        self.assertEqual(names[sources[1]]['json'], 'ep__yst00001.json')
        self.assertEqual(names[sources[2]]['json'], 'EP__yst00002.json')
        self.assertEqual(names[sources[3]]['naming'], 'internal')
        self.assertEqual({v['json'] for v in json_names(sources, None).values()},
                         {f'yst0000{i}.json' for i in range(4)})


class KeySelectionTests(unittest.TestCase):
    def setUp(self):
        self.commands = commands_from(dictionary())

    def test_key_is_derived_and_validated_by_full_parses(self):
        scenarios = {f'm{i}': scene([f'「本文{i}」', '地の文']) for i in range(3)}
        key, evidence = select_key(scenarios, self.commands)
        self.assertEqual((key, evidence['source'], evidence['parsed']), (KEY, 'derived-first-descriptor', 3))
        default = {f'm{i}': scene(['「本文」'], key=DEFAULT_KEY) for i in range(2)}
        self.assertEqual(select_key(default, self.commands)[1]['source'],
                         'derived-first-descriptor (equals profile default)')

    def test_explicit_wrong_key_and_inconsistent_sets_are_refused(self):
        scenarios = {f'm{i}': scene(['「本文」']) for i in range(2)}
        with self.assertRaises(ValueError):
            select_key(scenarios, self.commands, explicit=0x01020304)
        self.assertEqual(select_key(scenarios, self.commands, explicit=KEY)[0], KEY)
        mixed = {'a': scene(['「本文」'], key=0x11111111), 'b': scene(['「本文」'], key=0x22222222)}
        with self.assertRaises(ValueError):
            select_key(mixed, self.commands)
        with self.assertRaises(ValueError):
            select_key({}, self.commands)


class Version488WorkspaceTests(unittest.TestCase):
    def test_v487_archive_with_named_v488_scenes_extracts_and_rebuilds(self):
        ysc = dictionary()
        names = scene([])  # no text: published as empty, never as JSON
        first = scene(['【花子】「待って」', '彼女は笑った。'])
        members = {'ysbin\\ysc.ybn': ysc, 'ysbin\\yst00000.ybn': names, 'ysbin\\yst00001.ybn': first,
                   'ysbin\\yst_list.ybn': script_list(['data\\script\\names.txt', 'data\\script\\story\\opening.txt'])}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'pac').mkdir()
            (root / 'pac/ysbin.ypf').write_bytes(archive(members))
            report = extract(root, root / 'work', archive='pac/ysbin.ypf', smoke_test=True)
            self.assertEqual(report['status'], 'complete')
            self.assertEqual(report['versions'], [488])
            self.assertEqual(report['key_selection']['key'], f'0x{KEY:08X}')
            self.assertEqual(report['script_list'], 'used')
            self.assertEqual(sorted(p.name for p in (root / 'work/gt_input').iterdir()), ['opening.json'])
            self.assertEqual(report['delivery']['suggested_first_json']['file'], 'opening.json')
            self.assertTrue((root / 'work/reports/translation-state.md').is_file())
            rows, _ = export_script(first, ysc, Profile(key=KEY))
            rows[1]['message'] = '彼女は長い間ずっと笑っていた。'
            (root / 'work/gt_output/opening.json').write_bytes(dump_rows(rows))
            result = rebuild(root / 'work', root / 'patch')
            self.assertEqual(result['translated_members'], ['ysbin/yst00001.ybn'])
            packed = archive_members((root / 'patch/pac/ysbin.ypf').read_bytes())
            self.assertEqual(export_script(packed['ysbin\\yst00001.ybn'], ysc, Profile(key=KEY))[0], rows)
            self.assertEqual(packed['ysbin\\yst00000.ybn'], names)
            (root / 'work/gt_output/yst00001.json').write_bytes(dump_rows(rows))
            with self.assertRaises(ValueError):
                rebuild(root / 'work', root / 'patch2')

    def test_unlisted_ypf_version_is_named_in_the_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'a.ypf').write_bytes(archive({'ysbin\\ysc.ybn': dictionary()}, version=500))
            with self.assertRaises(ValueError) as caught:
                extract(root, root / 'work', archive='a.ypf')
            self.assertIn('500', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
