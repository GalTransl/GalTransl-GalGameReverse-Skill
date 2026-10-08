"""The speaker field doubles as the display name when the display slot is empty.

Speakers are writable by default; dialects using internal IDs can opt out.
"""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch as mock_patch

from test_kirikiri_senren import fixture_tree
from python.engines.kirikiri_psb import Psb
from python.engines.kirikiri_scn import records, locate_records, writable_records, patch, fingerprint
from python.engines.kirikiri_extract import extract, pack
from python.engines import kirikiri_extract, kirikiri_hxv4_text
from python.archives import kirikiri_xp3 as xp3

SPEAKER = "\u30ca\u30ae"
RENAMED = "中文显示姓名加长"
DISPLAY = "\u8868\u793a\u540d"


def fixture(display=None):
    return fixture_tree({'scenes': [{'texts': [['\u30ca\u30ae', display, '\u672c\u6587', None, 1, {}]]}],
                         'unchanged': '\u672c\u6587'})


class SpeakerNameTests(unittest.TestCase):
    def test_opt_out_keeps_a_string_speaker_read_only(self):
        psb = Psb(fixture())
        recs = records(psb, speaker_name=False)
        self.assertEqual(recs[0]['row']['name'], SPEAKER)
        self.assertIsNone(recs[0]['name'])
        rows = [dict(r['row']) for r in recs]
        self.assertEqual(patch(psb, recs, rows)[0], psb.data)
        rows[0]['name'] = RENAMED
        with self.assertRaises(ValueError):
            patch(psb, recs, rows)

    def test_default_opens_the_speaker_slot(self):
        psb = Psb(fixture())
        recs, issue = writable_records(psb)
        self.assertIsNone(issue)
        self.assertEqual(records(psb), recs)
        self.assertEqual(locate_records(psb), recs)
        self.assertEqual(recs[0]['name'], recs[0]['message'][:4] + (0,))
        rows = [dict(r['row']) for r in recs]
        rows[0]['name'] = RENAMED
        out, edited = patch(psb, recs, rows)
        self.assertNotEqual(out, psb.data)
        self.assertTrue(edited)
        self.assertEqual(fingerprint(psb, edited), fingerprint(Psb(out), edited))
        self.assertEqual(records(Psb(out))[0]['row']['name'], RENAMED)
        # 正文与非文本部分不受影响
        self.assertEqual(records(Psb(out))[0]['row']['message'], '\u672c\u6587')

    def test_explicit_display_slot_wins_in_both_modes(self):
        for flag in (False, True):
            psb = Psb(fixture(DISPLAY))
            recs = records(psb, speaker_name=flag)
            self.assertEqual(recs[0]['row']['name'], DISPLAY)
            self.assertIsNotNone(recs[0]['name'])
            rows = [dict(r['row']) for r in recs]
            rows[0]['name'] = RENAMED
            out, _ = patch(psb, recs, rows)
            self.assertEqual(records(Psb(out))[0]['row']['name'], RENAMED)

    def test_null_speaker_has_no_name_and_numeric_is_rejected(self):
        # who = null -> 无名；who 为整数等未知类型时不猜，直接拒绝解析
        psb = Psb(fixture_tree({'scenes': [{'texts': [[None, None, '\u672c\u6587', None, 1, {}]]}],
                                'unchanged': '\u672c\u6587'}))
        for flag in (False, True):
            recs = writable_records(psb, speaker_name=flag)[0]
            self.assertNotIn('name', recs[0]['row'])
            self.assertIsNone(recs[0]['name'])
        numeric = Psb(fixture_tree({'scenes': [{'texts': [[7, None, '\u672c\u6587', None, 1, {}]]}],
                                    'unchanged': '\u672c\u6587'}))
        with self.assertRaises(ValueError):
            writable_records(numeric, speaker_name=True)

    def test_null_speaker_stays_narration_even_with_display_slot(self):
        raw = fixture_tree({'scenes': [{'texts': [[None, DISPLAY, '本文', None, 1, {}]]}]})
        for flag in (False, True):
            p = Psb(raw); recs = writable_records(p, speaker_name=flag)[0]
            self.assertNotIn('name', recs[0]['row'])
            self.assertEqual(patch(p, recs, [r['row'] for r in recs])[0], raw)

    def test_localized_and_fallback_paths_preserve_other_fields(self):
        for slot in (1, 2):
            for opaque in (False, True):
                langs = [[None, '本文', 2] if slot == 1 else [None, '本文'],
                         ['Other', 'Other text', 10] if slot == 1 else ['Other', 'Other text']]
                text = [SPEAKER, langs, None, 1, {}] if slot == 1 else [SPEAKER, None, langs, None, 1, {}]
                if opaque: text.append({'future': 7})
                raw = fixture_tree({'scenes': [{'texts': [text]}], 'unchanged': SPEAKER}, share_nodes=True)
                p = Psb(raw); recs, issue = writable_records(p, speaker_name=True)
                self.assertEqual(bool(issue), opaque)
                self.assertEqual(patch(p, recs, [r['row'] for r in recs])[0], raw)
                rows = [dict(name=RENAMED, message='变长中文正文')]
                changed, paths = patch(p, recs, rows); q = Psb(changed)
                self.assertEqual([r['row'] for r in writable_records(q, speaker_name=True)[0]], rows)
                self.assertEqual(fingerprint(p, paths), fingerprint(q, paths))
                self.assertEqual(writable_records(p, 1)[0], writable_records(q, 1)[0])

    def test_workspace_retains_flag_and_rejects_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'script.xp3').write_bytes(xp3.build([('main.scn', fixture())], 'plain'))
            for flag in (None, False, True):
                work = root/str(flag)
                options = {} if flag is None else dict(speaker_name=flag)
                result = extract(root, work, archives=('script.xp3',), verify_edits=True, **options)
                enabled = flag is not False
                self.assertIs(result['speaker_name'], enabled)
                self.assertEqual(pack(work, root/(str(flag)+'-noop'))['changed_files'], 0)
                if not enabled:
                    # A pre-flag workspace must retain its original name policy.
                    result.pop('speaker_name')
                    (work/'reports/extraction.json').write_text(json.dumps(result), encoding='utf-8')
                    self.assertEqual(pack(work, root/'legacy-noop')['changed_files'], 0)
                rows = json.loads((work/'gt_input/main.json').read_bytes())
                rows[0]['name'] = RENAMED
                (work/'gt_output/main.json').write_text(json.dumps(rows), encoding='utf-8')
                output = root/(str(flag)+'-translated')
                if not enabled:
                    with self.assertRaises(ValueError): pack(work, output)
                    self.assertFalse(output.exists())
                    continue
                self.assertEqual(pack(work, output)['changed_files'], 1)
                stream = io.BytesIO((output/'scenario.xp3').read_bytes())
                profile, entries = xp3.read_index(stream)
                rebuilt = xp3.read_member(stream, entries[0], profile)
                self.assertEqual([r['row'] for r in records(Psb(rebuilt), speaker_name=True)], rows)
                report = work/'reports/extraction.json'
                for value in (False, 'true', 1):
                    bad = dict(result, speaker_name=value)
                    report.write_text(json.dumps(bad), encoding='utf-8')
                    with self.assertRaises(ValueError): pack(work, root/'rejected')
                    self.assertFalse((root/'rejected').exists())

    def test_cli_default_and_explicit_name_policies(self):
        for module in (kirikiri_extract, kirikiri_hxv4_text):
            for flags, expected in (([], True), (['--speaker-name'], True), (['--no-speaker-name'], False)):
                args = ['extract', 'source', 'output', *flags]
                if module is kirikiri_hxv4_text:
                    args += ['--exe', 'not-executed.exe']
                result = dict(totals={}, scan_complete=True, skipped_oversize_members=0,
                              decrypted_bytes=0, diagnostics=[])
                with self.subTest(module=module.__name__, flags=flags), \
                        mock_patch('sys.argv', [module.__name__, *args]), \
                        mock_patch.object(module, 'extract', return_value=result) as run, \
                        mock_patch('sys.stdout', new_callable=io.StringIO):
                    module.main()
                    self.assertIs(run.call_args.kwargs['speaker_name'], expected)

    def test_flag_requires_bool(self):
        for flag in (1, 'true', None):
            with self.assertRaisesRegex(ValueError, 'speaker_name'):
                writable_records(Psb(fixture()), speaker_name=flag)


if __name__ == "__main__":
    unittest.main()
