# SPDX-License-Identifier: GPL-3.0-only
"""Synthetic YSTB version-boundary fixtures; no game assets."""

import struct
import unittest

from python.engines.yuris import toggle_ybn_sections
from python.engines.yuris_text import (PARSE_VERSIONS, WRITE_VERSION, Profile, Scenario,
                                       commands_from, export_script, rebuild_script,
                                       ystb_version)

KEY = 0x96AC6FD3


def dictionary(version=482):
    body = b'WORD\0\x01\0\x03\0' + b'_\0\x01\0\x03\0' + b'IF\0\0'
    body += b'GOSUB\0\x31' + b''.join(b'P\0\0\0' for _ in range(49))
    return b'YSCM' + struct.pack('<III', version, 4, 0) + body + b'error text\0' + bytes(range(256))


def scenario(version=482, text='【花子】「遅い」'):
    value = text.encode('cp932')
    commands = struct.pack('<BBH', 0, 1, 0)
    attrs = struct.pack('<HHII', 0, 0, len(value), 0)
    lines = bytes(len(commands))
    plain = b'YSTB' + struct.pack('<7I', version, len(commands) // 4, len(commands),
                                  len(attrs), len(value), len(lines), 0)
    return toggle_ybn_sections(plain + commands + attrs + value + lines, KEY)


class YstbVersionTests(unittest.TestCase):
    def test_range_bounds_are_enforced_on_the_version_word(self):
        self.assertEqual(PARSE_VERSIONS.start, 234)
        self.assertEqual(PARSE_VERSIONS.stop - 1, 490)
        for version in (234, 490):
            self.assertEqual(ystb_version(scenario(version)), version)
        for version in (233, 491):
            with self.assertRaises(ValueError):
                ystb_version(scenario(version))

    def test_non_writer_version_is_read_only(self):
        raw, ysc = scenario(400), dictionary(400)
        self.assertEqual(export_script(raw, ysc), export_script(raw, ysc))
        rows, manifest = export_script(raw, ysc, Profile(source_characters='遅', target_characters='迟'))
        self.assertEqual(rows, [{'name': '花子', 'message': '「迟い」'}])
        self.assertEqual(manifest['engine']['variant'], '400-word-raw-readonly')
        with self.assertRaises(ValueError):
            rebuild_script(raw, ysc, rows, manifest)
        # Structure still parses and the pool accessor still works.
        parsed = Scenario(raw, commands_from(ysc, 400), KEY)
        self.assertEqual(parsed.version, 400)
        self.assertEqual(parsed.value(0), '【花子】「遅い」'.encode('cp932'))

    def test_writer_version_keeps_its_manifest_variant(self):
        raw, ysc = scenario(WRITE_VERSION), dictionary(WRITE_VERSION)
        rows, manifest = export_script(raw, ysc)
        self.assertEqual(manifest['engine']['variant'], '482-word-raw')
        self.assertEqual(rebuild_script(raw, ysc, rows, manifest), raw)

    def test_dictionary_version_must_match_the_scenario(self):
        raw, ysc = scenario(482), dictionary(482)
        with self.assertRaises(ValueError):
            export_script(raw, dictionary(400))
        self.assertEqual(len(commands_from(ysc)), 4)
        with self.assertRaises(ValueError):
            commands_from(dictionary(233))

    def test_structurally_broken_headers_are_rejected_not_guessed(self):
        plain = bytearray(toggle_ybn_sections(scenario(400), KEY))
        struct.pack_into('<I', plain, 16, 10)  # descriptor section not 12-aligned
        with self.assertRaises(ValueError):
            Scenario(toggle_ybn_sections(bytes(plain), KEY), commands_from(dictionary(400), 400), KEY)
        with self.assertRaises(ValueError):
            ystb_version(b'YSTB' + b'\0' * 8)
        with self.assertRaises(ValueError):
            ystb_version(b'XXXX' + b'\0' * 40)


if __name__ == '__main__':
    unittest.main()
