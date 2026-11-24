"""Synthetic QLIE text forms, partial workspaces, shared copies and CLI behaviour."""
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from python.archives import qlie
from python.archives.qlie_writer import hash14_tail, lookup_tail, lookup_version, rebuild
from python.common.handoff import STATE_FILE
from python.engines import qlie_imos as imos
from python.engines.qlie_extract import QlieInputError, default_archives, extract
from python.engines.qlie_repack import repack
from tests.test_qlie import FKEY, GKEY, SCRIPT, archive, archive31, pe, read31, read_script

ROOT = Path(__file__).resolve().parents[1]
PROFILE = [('avg/projectsetting.txt', b'FormatType=1\r\n'), ('avg/setting.txt', b'ReturnCode=[n]\r\n')]
GOOD = '@@MAIN\r\n\r\n【Alice】\r\n％voice01％\r\nHello there\r\n\r\nNarration line\r\n\r\n'
BAD = '@@MAIN\r\n\r\nFine text\r\n\r\nBroken [unknown,1] tag\r\n\r\n'


def run(module, *args):
    return subprocess.run([sys.executable, '-X', 'utf8', '-B', '-m', module, *map(str, args)],
                          cwd=ROOT, capture_output=True, text=True, encoding='utf-8')


class QlieTextFormTests(unittest.TestCase):
    def test_ruby_is_a_protected_group(self):
        script = '本文の[rb,漢字,かんじ]を読む。\r\n\r\n'
        rows = imos.rows(script)
        self.assertEqual(rows, [{'message': '本文の[rb,漢字,かんじ]を読む。'}])
        self.assertEqual(imos.patch(script, rows), script)
        for text in ('改写[rb,汉字,hàn zì]注音', '删除注音后的译文', '新增[rb,词,cí]与[rb,字,zì]'):
            result = imos.patch(script, [{'message': text}])
            self.assertEqual(imos.rows(result), [{'message': text}])
        for bad in ('[rb,底字]', '[rb,,读]', '[rb,a,b,c]', '[rb,a,b', 'x]', '[n]', '[pc,a]'):
            with self.assertRaisesRegex(ValueError, 'brackets'):
                imos.patch(script, [{'message': bad}])
        choice = '^select,Yes,No\r\n'
        with self.assertRaises(ValueError):
            imos.patch(choice, [{'message': '[rb,是,shi]'}, {'message': 'No'}])
        with self.assertRaisesRegex(imos.ScriptError, 'line 1'):
            imos.scan('[rb,only]\r\n')

    def test_timing_tags_stay_in_order(self):
        script = '【A】\r\n[w,200]\r\n[spd,100]\r\nSlow words\r\n[spd]\r\n\r\n'
        rows = imos.rows(script)
        self.assertEqual(rows, [{'name': 'A', 'message': '[w,200]\n[spd,100]\nSlow words\n[spd]'}])
        self.assertEqual(imos.patch(script, rows), script)
        rows[0]['message'] = '[w,200]\n[spd,100]\nLonger translated words\n[spd]'
        self.assertEqual(imos.rows(imos.patch(script, rows)), rows)
        for bad in ('[w,200]\n[spd,100]\nwords', '[spd,100]\n[w,200]\nwords\n[spd]', '[w,300]\n[spd,100]\nx\n[spd]'):
            with self.assertRaisesRegex(ValueError, 'timing'):
                imos.patch(script, [{'name': 'A', 'message': bad}])
        for unknown in ('[w]\r\n', 'text[spd,fast]\r\n'):
            with self.assertRaisesRegex(imos.ScriptError, 'unrecognized'):
                imos.scan(unknown)

    def test_pc_with_trailing_punctuation_only(self):
        script = '[pc,Line of verse]、\r\n\r\n'
        rows = imos.rows(script)
        self.assertEqual(rows, [{'message': 'Line of verse'}])
        self.assertEqual(imos.patch(script, rows), script)
        self.assertEqual(imos.patch(script, [{'message': 'Translated verse'}]), '[pc,Translated verse]、\r\n\r\n')
        with self.assertRaisesRegex(imos.ScriptError, 'mixed pc'):
            imos.scan('[pc,verse]and more text\r\n')

    def test_name_line_forms(self):
        for script, edited in (('【Alice】　\r\nHi\r\n\r\n', '【Alice＠艾丽丝】　\r\n'),
                               ('【Alice\r\nHi\r\n\r\n', '【Alice＠艾丽丝\r\n'),
                               ('【Alice＠？？？】　 \r\nHi\r\n\r\n', '【Alice＠艾丽丝】　 \r\n')):
            rows = imos.rows(script)
            self.assertEqual(rows[0]['message'], 'Hi')
            self.assertEqual(imos.patch(script, rows), script)
            rows[0]['name'] = '艾丽丝'
            result = imos.patch(script, rows)
            self.assertTrue(result.startswith(edited), result)
            self.assertEqual(imos.rows(result), rows)
        # The engine strips the first opener/closer of the whole line, so these
        # would merge names or swallow text: rejected with location and token.
        for line in ('【A】【B】', '【A】 【B】', '【A】text', '【', '【A＠B＠C】'):
            with self.assertRaises(imos.ScriptError) as caught:
                imos.scan(f'@@MAIN\r\n{line}\r\nHi\r\n')
            self.assertEqual((caught.exception.line, caught.exception.token), (2, line))

    def test_cal_inside_sentence_and_other_control_rejected(self):
        script = 'First line\r\n\\cal,flag=1\r\nSecond line\r\n\r\n'
        rows = imos.rows(script)
        self.assertEqual(rows, [{'message': 'First line\nSecond line'}])
        self.assertEqual(imos.patch(script, rows), script)
        with self.assertRaises(imos.ScriptError) as caught:
            imos.scan('【A】\r\nText\r\n\\sub,@@!Routine,1\r\n')
        self.assertEqual((caught.exception.line, caught.exception.token), (3, '\\sub'))
        self.assertIn('line 3', str(caught.exception))

    def test_indented_line_keeps_text_role(self):
        script = '　　Indented twice\r\n\r\n　【Not a name\r\n\r\nPlain\r\n\r\n'
        rows = imos.rows(script)
        self.assertEqual(rows, [{'message': '　Indented twice'}, {'message': '【Not a name'},
                                {'message': 'Plain'}])
        self.assertEqual(imos.patch(script, rows), script)
        changed = [{'message': '　变长的缩进译文'}, {'message': '^看起来像命令'}, {'message': 'Plain'}]
        self.assertEqual(imos.rows(imos.patch(script, changed)), changed)
        for bad in ('　indent', '【name', '^cmd', ' lead'):
            with self.assertRaisesRegex(ValueError, 'line role'):
                imos.patch(script, rows[:2] + [{'message': bad}])

    def test_unknown_tag_reports_line_and_token(self):
        with self.assertRaises(imos.ScriptError) as caught:
            imos.scan(BAD)
        self.assertEqual((caught.exception.reason, caught.exception.line, caught.exception.token),
                         ('unrecognized ImoScripter text tag', 5, '[unknown,1]'))


class QlieWorkspaceTests(unittest.TestCase):
    def _game30(self, temp, *packs):
        game = Path(temp)
        (game / 'game.exe').write_bytes(pe())
        (game / 'key.fkey').write_bytes(FKEY)
        (game / 'GameData').mkdir()
        for name, files in packs:
            (game / 'GameData' / name).write_bytes(archive(files))
        return game

    def test_partial_workspace_is_packable_and_failed_scripts_stay_verbatim(self):
        with tempfile.TemporaryDirectory() as temp:
            game = self._game30(temp, ('data0.pack', [('scenario/main/good.s', GOOD.encode('cp932')),
                                                      ('scenario/main/bad.s', BAD.encode('cp932')), *PROFILE]))
            output = game / 'out'
            report = extract(game, output, exe='game.exe', key_file='key.fkey')
            self.assertEqual(report['status'], 'partial')
            self.assertEqual(report['failure_reasons'], {'unrecognized ImoScripter text tag': 1})
            self.assertEqual(report['failed'][0]['line'], 5)
            self.assertEqual(sorted(p.name for p in (output / 'gt_input').iterdir()), ['good.json'])
            self.assertTrue((output / STATE_FILE).is_file())
            self.assertIn('1 个脚本', ''.join(report['delivery']['translation_notes']))
            rows = json.loads((output / 'gt_input/good.json').read_text(encoding='utf-8'))
            rows[0] = {'name': 'アリス', 'message': 'ずっと長い訳文です'}
            (output / 'gt_output/good.json').write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
            result = repack(game, output, game / 'rebuilt')
            self.assertEqual(result['copied_failed_members'], ['GameData/data0.pack:scenario/main/bad.s'])
            rebuilt = (game / 'rebuilt/GameData/data0.pack').read_bytes()
            self.assertEqual(imos.rows(read_script(rebuilt, 'scenario/main/good.s').decode('cp932')), rows)
            self.assertEqual(read_script(rebuilt, 'scenario/main/bad.s'), BAD.encode('cp932'))
            repack(game, output, game / 'roundtrip', source_roundtrip=True)
            self.assertEqual((game / 'roundtrip/GameData/data0.pack').read_bytes(),
                             (game / 'GameData/data0.pack').read_bytes())
            (output / 'gt_output/bad.json').write_text('[]', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, r'failed extraction.*bad\.json.*line 5'):
                repack(game, output, game / 'refused')
            proc = run('python.engines.qlie_repack', game, output, game / 'refused_cli')
            self.assertEqual(proc.returncode, 2)
            self.assertIn('bad.json', proc.stderr)
            self.assertNotIn('Traceback', proc.stderr)
            proc = run('python.engines.qlie_extract', game, game / 'cli', '--exe', 'game.exe', '--key-file', 'key.fkey')
            self.assertEqual(proc.returncode, 1)
            self.assertEqual(json.loads(proc.stdout)['status'], 'partial')

    def test_identical_copies_share_one_json_and_differing_copies_are_listed(self):
        other = GOOD.replace('Narration line', 'Patched narration')
        with tempfile.TemporaryDirectory() as temp:
            game = self._game30(temp, ('data1.pack', [('scenario/a.s', GOOD.encode('cp932')), *PROFILE]),
                                ('data2.pack', [('scenario/a.s', GOOD.encode('cp932')),
                                                ('scenario/b.s', GOOD.encode('cp932'))]),
                                ('data10.pack', [('scenario/b.s', other.encode('cp932'))]))
            self.assertEqual(default_archives(game), ['GameData/data1.pack', 'GameData/data2.pack',
                                                      'GameData/data10.pack'])
            output = game / 'out'
            report = extract(game, output, exe='game.exe', key_file='key.fkey')
            self.assertEqual(report['status'], 'complete')
            names = sorted(p.name for p in (output / 'gt_input').iterdir())
            self.assertEqual(names, ['a.json', 'b__a01_m00002.json', 'b__a02_m00001.json'])
            self.assertEqual(report['counts']['shared_json'], 1)
            [diff] = report['differing_copies']
            self.assertEqual(diff['archive_order'], ['GameData/data2.pack', 'GameData/data10.pack'])
            rows = json.loads((output / 'gt_input/a.json').read_text(encoding='utf-8'))
            rows[1]['message'] = 'Shared translation'
            (output / 'gt_output/a.json').write_text(json.dumps(rows), encoding='utf-8')
            result = repack(game, output, game / 'rebuilt')
            self.assertEqual(sorted(result['translated_members']),
                             ['GameData/data1.pack:scenario/a.s', 'GameData/data2.pack:scenario/a.s'])
            for pack in ('data1.pack', 'data2.pack'):
                data = read_script((game / 'rebuilt/GameData' / pack).read_bytes(), 'scenario/a.s')
                self.assertEqual(imos.rows(data.decode('cp932')), rows)
            self.assertFalse((game / 'rebuilt/GameData/data10.pack').exists())
            # A previous-parser workspace stays packable; an unknown parser does not.
            path = output / 'reports/extraction.json'
            legacy = json.loads(path.read_text(encoding='utf-8'))
            legacy.update(schema='qlie-extract/2', variant='qlie-imos-multi/2')
            path.write_text(json.dumps(legacy), encoding='utf-8')
            for manifest in (output / 'metadata').glob('*.json'):
                data = json.loads(manifest.read_text(encoding='utf-8'))
                data['engine']['reference'] = 'qlie-imos-multi/2'
                manifest.write_text(json.dumps(data), encoding='utf-8')
            repack(game, output, game / 'legacy', source_roundtrip=True)
            legacy['variant'] = 'qlie-imos-multi/9'
            path.write_text(json.dumps(legacy), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 're-extract'):
                repack(game, output, game / 'unknown')

    def test_stub_exe_and_missing_pack_folder_are_one_line_errors(self):
        with tempfile.TemporaryDirectory() as temp:
            game = self._game30(temp, ('data0.pack', [('scenario/a.s', GOOD.encode('cp932')), *PROFILE]))
            (game / 'stub.exe').write_bytes(b'MZ' + bytes(2046))
            with self.assertRaisesRegex(QlieInputError, 'stub'):
                extract(game, game / 'out', exe='stub.exe', key_file='key.fkey')
            proc = run('python.engines.qlie_extract', game, game / 'cli', '--exe', 'stub.exe',
                       '--key-file', 'key.fkey')
            self.assertEqual(proc.returncode, 2)
            self.assertIn('--exe', proc.stderr)
            self.assertNotIn('Traceback', proc.stderr)
            self.assertFalse((game / 'cli').exists())
            with self.assertRaisesRegex(QlieInputError, 'GameData'):
                extract(game / 'GameData', game / 'none')

    def test_pack31_default_archives_handoff_and_verify_edits(self):
        with tempfile.TemporaryDirectory() as temp:
            game = Path(temp)
            (game / 'GameData').mkdir()
            script = '@@MAIN\r\n\r\n【少女】\r\n“[rb,注音,zhù yīn]测试”\r\n\r\n旁白。\r\n\r\n'
            files = [('scenario\\main\\s01.s', b'\xff\xfe' + script.encode('utf-16-le')),
                     ('avg\\projectsetting.txt', b'\xff\xfe' + 'FormatType=1\r\n'.encode('utf-16-le')),
                     ('avg\\setting.txt', b'\xff\xfe' + 'ReturnCode=[n]\r\n'.encode('utf-16-le'))]
            (game / 'GameData/data0.pack').write_bytes(archive31(files))
            output = game / 'out'
            report = extract(game, output, verify_edits=True)
            self.assertEqual(report['archive_selection'].split()[0], 'default')
            self.assertEqual(report['counts']['ruby_rows'], 1)
            self.assertEqual(report['edit_check']['reparsed'], 'identical')
            self.assertTrue(report['edit_check']['name_alias_written'])
            delivery = report['delivery']
            self.assertEqual(delivery['suggested_first_json']['file'], 's01.json')
            self.assertEqual(delivery['not_verified'], ['游戏内加载与显示'])
            self.assertIn('UTF-16LE', ''.join(delivery['translation_notes']))
            state = (output / STATE_FILE).read_text(encoding='utf-8')
            self.assertIn('s01.json', state)
            rows = json.loads((output / 'gt_input/s01.json').read_text(encoding='utf-8'))
            rows[0]['message'] = '“更长的译文，删掉了注音”'
            (output / 'gt_output/s01.json').write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
            repack(game, output, game / 'rebuilt')
            data = read31((game / 'rebuilt/GameData/data0.pack').read_bytes(), 'scenario\\main\\s01.s')
            self.assertEqual(imos.rows(data[2:].decode('utf-16-le')), rows)

    def test_pack30_hashver14_lookup_roundtrip(self):
        raw = archive([('scene.s', SCRIPT.encode('cp932')), ('image.bin', b'MEDIA')], lookup14=True)
        index = qlie.read_index(io.BytesIO(raw))
        self.assertEqual(lookup_version(io.BytesIO(raw), index), 'HashVer1.4')
        self.assertEqual(hash14_tail(io.BytesIO(raw), index), lookup_tail(io.BytesIO(raw), index))
        dest = io.BytesIO()
        rebuild(io.BytesIO(raw), dest, {'scene.s': SCRIPT.encode('cp932')}, mode='keyed', key_file=FKEY, game_key=GKEY)
        self.assertEqual(dest.getvalue(), raw)
        changed = (SCRIPT + 'Longer appended narration.\r\n\r\n').encode('cp932')
        dest = io.BytesIO()
        rebuild(io.BytesIO(raw), dest, {'scene.s': changed}, mode='keyed', key_file=FKEY, game_key=GKEY)
        self.assertEqual(read_script(dest.getvalue()), changed)
        corrupt = bytearray(raw)
        at = index.index_end + 16 + 8  # ordinal-array size field
        corrupt[at] ^= 2
        with self.assertRaisesRegex(ValueError, 'HashVer1.4'):
            rebuild(io.BytesIO(bytes(corrupt)), io.BytesIO(), {}, mode='keyed', key_file=FKEY, game_key=GKEY)
        unknown = raw.replace(b'HashVer1.4', b'HashVer1.9', 1)
        with self.assertRaisesRegex(ValueError, 'does not support'):
            lookup_tail(io.BytesIO(unknown), qlie.read_index(io.BytesIO(unknown)))


if __name__ == '__main__':
    unittest.main()
