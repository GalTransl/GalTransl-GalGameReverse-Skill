"""Synthetic table/text candidate extraction; no game assets used."""
import unittest

from python.engines.kirikiri_hxv4_tables import (
    candidate_names, diff_map_candidates, name_variants, psb_ref_candidates,
    scene_candidates, table_tokens,
)
from python.engines.kirikiri_simple_crypt import pack


class HxCandidateTests(unittest.TestCase):
    def test_scene_list_skips_comments_dummies_and_keeps_scn_variants(self):
        text = ('# comment\nsystem:\n\tgameloop.txt\n\tsc_1_st01.txt\t*label\n'
                '\tdummy.txt\n\t-\n\tfoo.ks\n')
        names = scene_candidates(text)
        self.assertIn('gameloop.txt.scn', names)
        self.assertIn('sc_1_st01.txt.scn', names)
        self.assertIn('sc_1_st01.scn', names)
        self.assertIn('foo.ks.scn', names)
        self.assertNotIn('dummy.txt.scn', names)

    def test_diff_map_uses_actual_names_and_image_extensions(self):
        text = ('# header\n'
                'evcg001_01\tcg001_01\tdiff\tcg001_01\n'
                'image001\tstand01.stand\tdress\t制服\n')
        names = diff_map_candidates(text)
        self.assertIn('cg001_01.dref', names)
        self.assertIn('cg001_01.tlg', names)
        self.assertIn('cg001_01.dpak', names)
        self.assertIn('stand01.stand', names)

    def test_table_tokens_expand_stems_and_keep_full_names(self):
        names = table_tokens('thum_cg001_01,\tsc_1.txt\nplain text, 001\n')
        self.assertIn('thum_cg001_01.png', names)
        self.assertIn('sc_1.txt.scn', names)
        self.assertNotIn('plain text', names)

    def test_psb_reference_components_become_package_and_file_names(self):
        text = ('psb://cg001_01__vkaqky.dpak/cg001_01.tlg\n'
                'psb://cg001_01__vkaqky.dpak/28b995f460.png\n')
        names = psb_ref_candidates(text)
        self.assertIn('cg001_01__vkaqky.dpak', names)
        self.assertIn('cg001_01.tlg', names)
        self.assertIn('28b995f460.png', names)

    def test_simplecrypt_table_is_decoded_before_parsing(self):
        text = 'system:\n\tsc_1_st01.txt\n'
        wrapped = pack(b'\xff\xfe' + text.encode('utf-16-le'), 1)
        names = candidate_names(wrapped)
        self.assertIn('sc_1_st01.txt.scn', names)

    def test_name_variants_do_not_expand_plain_words(self):
        self.assertEqual(name_variants('Array'), {'Array'})
        self.assertIn('foo01.scn', name_variants('foo01'))
        self.assertIn('foo.txt.scn', name_variants('foo.txt'))


if __name__ == '__main__':
    unittest.main()
