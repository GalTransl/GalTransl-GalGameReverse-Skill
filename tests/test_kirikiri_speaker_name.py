"""The speaker field doubles as the display name when the display slot is empty.

Default behaviour keeps such a name read-only (it may be an internal id), so the
opt-in flag is what turns the speaker slot into a writable name slot.
"""
import io
import json
from pathlib import Path
import tempfile
import unittest

from test_kirikiri_senren import fixture_tree
from python.engines.kirikiri_psb import Psb
from python.engines.kirikiri_scn import records, writable_records, patch, fingerprint
from python.engines.kirikiri_extract import extract, pack
from python.archives import kirikiri_xp3 as xp3

SPEAKER = "\u30ca\u30ae"
RENAMED = "中文显示姓名加长"
DISPLAY = "\u8868\u793a\u540d"


def fixture(display=None):
    return fixture_tree({'scenes': [{'texts': [['\u30ca\u30ae', display, '\u672c\u6587', None, 1, {}]]}],
                         'unchanged': '\u672c\u6587'})


class SpeakerNameTests(unittest.TestCase):
    def test_default_keeps_a_string_speaker_read_only(self):
        psb = Psb(fixture())
        recs = records(psb)
        self.assertEqual(recs[0]['row']['name'], SPEAKER)
        self.assertIsNone(recs[0]['name'])
        rows = [dict(r['row']) for r in recs]
        self.assertEqual(patch(psb, recs, rows)[0], psb.data)
        rows[0]['name'] = RENAMED
        with self.assertRaises(ValueError):
            patch(psb, recs, rows)

    def test_flag_opens_the_speaker_slot(self):
        psb = Psb(fixture())
        recs, issue = writable_records(psb, speaker_name=True)
        self.assertIsNone(issue)
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
            recs = records(psb) if not flag else writable_records(psb, speaker_name=True)[0]
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
            for flag in (False, True):
                work = root/str(flag)
                result = extract(root, work, archives=('script.xp3',), speaker_name=flag, verify_edits=True)
                self.assertIs(result['speaker_name'], flag)
                self.assertEqual(pack(work, root/(str(flag)+'-noop'))['changed_files'], 0)
                rows = json.loads((work/'gt_input/main.json').read_bytes())
                rows[0]['name'] = RENAMED
                (work/'gt_output/main.json').write_text(json.dumps(rows), encoding='utf-8')
                output = root/(str(flag)+'-translated')
                if not flag:
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

    def test_flag_requires_bool(self):
        for flag in (1, 'true', None):
            with self.assertRaisesRegex(ValueError, 'speaker_name'):
                writable_records(Psb(fixture()), speaker_name=flag)


if __name__ == "__main__":
    unittest.main()
