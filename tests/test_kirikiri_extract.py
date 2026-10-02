"""Shared CLI tests: arbitrary archive names, profiles, overlay and empty SCN."""
from pathlib import Path
import tempfile
import unittest

from test_kirikiri_senren import fixture_tree
from python.archives import xp3, kirikiri_elif
from python.engines.kirikiri_extract import extract,pack


def scene(message='本文'):
    return fixture_tree({'scenes':[{'texts':[[None,None,message,None,1,{}]]}]},version=2)


class SharedKirikiriTests(unittest.TestCase):
    def test_arbitrary_archive_names_path_collisions_and_empty_scene(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);game=root/'game';game.mkdir()
            empty=fixture_tree({'scenes':[]},version=2)
            (game/'base.assets').write_bytes(xp3.build([('left/scene.scn',scene()),('empty.scn',empty)],filter_name='none'))
            (game/'update.assets').write_bytes(xp3.build([('right/scene.scn',scene('別の本文'))],filter_name='none'))
            work=root/'work'
            report=extract(game,work,archives=('base.assets','update.assets'),verify_edits=True)
            self.assertEqual(report['output_format'],'plain')
            self.assertEqual(report['totals']['files'],2)
            self.assertEqual(len(list((work/'gt_input').iterdir())),2)
            self.assertTrue(all('__a' in e['json'] for e in report['exports']))
            self.assertEqual(report['non_target'][0]['role'],'empty-story')
            output=root/'pack';self.assertEqual(pack(work,output)['members'],3)
            self.assertEqual((output/'scenario.xp3').read_bytes(),(work/'rebuilt/roundtrip/scenario.xp3').read_bytes())
            overlay=root/'overlay'
            report=extract(game,overlay,archives=('base.assets','update.assets'),overlay='basename')
            self.assertEqual(report['totals']['files'],1)
            self.assertEqual(len(report['overridden']),1)
            self.assertEqual(report['exports'][0]['member'],'right/scene.scn')

    def test_mixed_profiles_require_explicit_output_choice(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'one.xp3').write_bytes(xp3.build([('one.scn',scene())],filter_name='none'))
            (root/'two.xp3').write_bytes(kirikiri_elif.build([('two.scn',scene())]))
            with self.assertRaises(ValueError):extract(root,root/'rejected',archives=('one.xp3','two.xp3'))
            self.assertFalse((root/'rejected').exists())
            report=extract(root,root/'accepted',archives=('one.xp3','two.xp3'),output_format='plain')
            self.assertEqual(report['totals']['files'],2)
            with self.assertRaises(ValueError):extract(root,root/'wrong-profile',archives=('one.xp3',),archive_profile='senren-cx')


if __name__=='__main__':unittest.main()
