"""Synthetic YDG tiles and a generated rectangle font; no game/font resources."""
import ast
import builtins
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

try:
    from PIL import Image
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    IMAGING = True
except ImportError:
    IMAGING = False

from python.engines import yuris_ydg as ydg
from python.engines import yuris_font as atlas
from python.engines import yuris_ydg_workflow as flow
from python.archives.yuris_482 import pack_archive, read_index
from python.engines.yuris_extract import archive_members
from tests.test_yuris_482 import archive
from tools.check_skill import runtime_dependency_errors


class DependencyTests(unittest.TestCase):
    def test_optional_imports_are_scoped_lazy_and_guarded(self):
        root = Path(__file__).resolve().parents[1]
        for name in ('yuris_ydg', 'yuris_font'):
            relative = f'python/engines/{name}.py'
            tree = ast.parse((root / relative).read_text('utf-8'))
            self.assertEqual(runtime_dependency_errors(tree, relative), [])
        for library, relative in (('PIL', 'python/engines/yuris_ydg.py'),
                                 ('fontTools', 'python/engines/yuris_font.py')):
            guarded = f'def codec():\n    try:\n        import {library}\n    except ImportError:\n        raise RuntimeError("missing renderer")\n'
            self.assertEqual(runtime_dependency_errors(ast.parse(guarded), relative), [])
            self.assertTrue(runtime_dependency_errors(ast.parse(guarded), 'python/engines/another.py'))
            self.assertTrue(runtime_dependency_errors(ast.parse(f'import {library}'), relative))

    def test_missing_pillow_fails_only_when_requested(self):
        original_import = builtins.__import__

        def without_pillow(name, *args, **kwargs):
            if name == 'PIL' or name.startswith('PIL.'):
                raise ImportError('synthetic missing Pillow')
            return original_import(name, *args, **kwargs)

        with patch('builtins.__import__', side_effect=without_pillow):
            with self.assertRaisesRegex(RuntimeError, 'requires Pillow'):
                ydg.imaging()


def tile_bytes(width, height, pixels, codec, channels=4, colorspace=0):
    image = Image.frombytes('RGBA', (width, height), pixels)
    if channels == 3:
        image = image.convert('RGB')
    stream = io.BytesIO()
    image.save(stream, format=codec.upper(), **(
        {'lossless': True, 'exact': True} if codec == 'webp' else
        {'colorspace': 'sRGB' if colorspace == 0 else 'linear'}))
    return stream.getvalue()


def fixture():
    # Logical order differs from physical order. X offsets leave transparent margins.
    qoi_pixels = bytes((90, 40, 20, 255)) * 4
    webp_pixels = bytes((200, 50, 80, 90)) * 6
    qoi = tile_bytes(2, 2, qoi_pixels, 'qoi', 3, 1)
    webp = tile_bytes(3, 2, webp_pixels, 'webp')
    out = bytearray(60 + 32)
    out[:12] = ydg.MAGIC
    struct.pack_into('<II', out, 12, 100, 56)
    out[24:32] = b'RESERVED'
    struct.pack_into('<HH', out, 32, 4, 4)
    out[36:56] = b'HEADER_EXTENSION1234'
    struct.pack_into('<I', out, 56, 2)
    out.extend(b'gap-before')
    wp = len(out)
    out.extend(webp)
    out.extend(b'gap-between')
    qp = len(out)
    out.extend(qoi)
    out.extend(b'opaque-tail')
    struct.pack_into('<IIHHI', out, 60, qp, len(qoi), 1, 2, 0xABCDEF01)
    struct.pack_into('<IIHHI', out, 76, wp, len(webp), 0, 2, 0x12345678)
    struct.pack_into('<I', out, 20, len(out))
    return bytes(out)


def rectangle_font(path):
    builder = FontBuilder(1000, isTTF=True)
    names = ['.notdef', 'space', 'box']
    builder.setupGlyphOrder(names)
    glyphs = {}
    for name in names:
        pen = TTGlyphPen(None)
        if name != 'space':
            pen.moveTo((100, 0))
            pen.lineTo((600, 0))
            pen.lineTo((600, 700))
            pen.lineTo((100, 700))
            pen.closePath()
        glyphs[name] = pen.glyph()
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({name: (700, 0) for name in names})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupCharacterMap({32: 'space', ord('中'): 'box', ord('A'): 'box'})
    builder.setupNameTable({'familyName': 'SyntheticAtlas', 'styleName': 'Regular',
                           'uniqueFontIdentifier': 'SyntheticAtlas', 'fullName': 'SyntheticAtlas',
                           'psName': 'SyntheticAtlas'})
    builder.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
    builder.setupPost()
    builder.setupMaxp()
    builder.save(path)


@unittest.skipUnless(IMAGING, 'requires Pillow and fonttools')
class YdgTests(unittest.TestCase):
    def test_mixed_codecs_geometry_extension_and_identity_writer(self):
        raw = fixture()
        resource = ydg.read_ydg(raw)
        self.assertEqual((resource.width, resource.height, resource.table_offset), (4, 4, 60))
        self.assertEqual([(t.x, t.y, t.codec, t.channels, t.colorspace) for t in resource.tiles],
                         [(1, 0, 'qoi', 3, 1), (0, 2, 'webp', 4, 0)])
        self.assertEqual(resource.pixels[:4], bytes(4))
        self.assertEqual(ydg.rebuild_ydg(raw, resource.pixels), raw)
        self.assertEqual(ydg.read_png(ydg.png_bytes(resource), 4, 4), resource.pixels)

    def test_growth_reparse_and_opaque_structure_preservation(self):
        raw = fixture()
        before = ydg.read_ydg(raw)
        canvas = Image.frombytes('RGBA', (4, 4), before.pixels)
        for y in range(2):
            for x in (1, 2):
                canvas.putpixel((x, y), (x * 65, y * 80, 255 - x * 60, 255))
        for y in (2, 3):
            for x in range(3):
                canvas.putpixel((x, y), (x * 47, y * 60, 190 - x * 30, 0 if x == 0 else 110))
        result = ydg.rebuild_ydg(raw, canvas.tobytes())
        after = ydg.read_ydg(result)
        self.assertEqual(after.pixels, canvas.tobytes())
        self.assertNotEqual(len(raw), len(result))
        self.assertEqual(result[:20], raw[:20])
        self.assertEqual(result[24:60], raw[24:60])
        for old, new in zip(before.tiles, after.tiles):
            self.assertEqual((old.x, old.y, old.width, old.height, old.reserved, old.codec),
                             (new.x, new.y, new.width, new.height, new.reserved, new.codec))
        self.assertIn(b'gap-before', result)
        self.assertIn(b'gap-between', result)
        self.assertTrue(result.endswith(b'opaque-tail'))

    def test_reject_unknown_layout_overlap_height_and_length(self):
        raw = fixture()
        for offset, fmt, value in ((12, '<I', 101), (16, '<I', 0x10000), (20, '<I', 0),
                                    (32, '<H', 0), (56, '<I', 0), (60, '<I', 0),
                                    (64, '<I', len(raw)), (68, '<H', 4), (70, '<H', 3)):
            bad = bytearray(raw)
            struct.pack_into(fmt, bad, offset, value)
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                ydg.read_ydg(bytes(bad))
        bad = bytearray(raw)
        bad[76:80] = bad[60:64]
        with self.assertRaises(ValueError):
            ydg.read_ydg(bytes(bad))
        with self.assertRaises(ValueError):
            ydg.read_ydg(raw[:-1])

    def test_qoi_truncation_run_trailer_and_pixel_budget(self):
        data = tile_bytes(2, 1, bytes((1, 2, 3, 255)) * 2, 'qoi')
        bad_run = data[:14] + b'\xfd' + ydg.QOI_END
        oversized = b'qoif' + struct.pack('>IIBB', 8192, 8192, 4, 0) + b'\xc0' + ydg.QOI_END
        for bad in (data[:-1], data[:14] + b'\xff\x01' + ydg.QOI_END,
                    data[:-8] + b'\0' + ydg.QOI_END,
                    bad_run, oversized):
            with self.assertRaises(ValueError):
                ydg._decode(bad)

    def test_reject_unrepresented_pixels_rgb_alpha_and_resize(self):
        raw = fixture()
        pixels = bytearray(ydg.read_ydg(raw).pixels)
        pixels[:4] = b'\xff\xff\xff\xff'
        with self.assertRaises(ValueError):
            ydg.rebuild_ydg(raw, bytes(pixels))
        pixels = bytearray(ydg.read_ydg(raw).pixels)
        pixels[7] = 100
        with self.assertRaises(ValueError):
            ydg.rebuild_ydg(raw, bytes(pixels))
        with self.assertRaises(ValueError):
            ydg.rebuild_ydg(raw, bytes(12))

    def test_explicit_create_qoi_and_webp(self):
        pixels = bytes((20, 50, 80, 0)) * 20
        for codec in ('qoi', 'webp'):
            raw = ydg.create_ydg(4, 5, pixels, codec=codec, section_height=2)
            resource = ydg.read_ydg(raw)
            self.assertEqual([tile.height for tile in resource.tiles], [2, 2, 1])
            self.assertEqual(resource.pixels, pixels)
            self.assertEqual(ydg.rebuild_ydg(raw, pixels), raw)
        with self.assertRaises(ValueError):
            ydg.create_ydg(4, 5, pixels, section_height=0)

    def test_webp_riff_length_and_animation_rejected(self):
        data = tile_bytes(2, 2, bytes((10, 20, 30, 255)) * 4, 'webp')
        with self.assertRaises(ValueError):
            ydg._decode(data[:-1])
        stream = io.BytesIO()
        Image.new('RGBA', (2, 2), 'red').save(stream, format='WEBP', save_all=True,
            append_images=[Image.new('RGBA', (2, 2), 'blue')], duration=100, lossless=True)
        with self.assertRaises(ValueError):
            ydg._decode(stream.getvalue())

    def test_ypf_repack_changed_ydg_and_preserve_other_members(self):
        original = fixture()
        before = ydg.read_ydg(original)
        canvas = Image.frombytes('RGBA', (4, 4), before.pixels)
        canvas.putpixel((1, 0), (10, 240, 80, 255))
        replacement = ydg.rebuild_ydg(original, canvas.tobytes())
        self.assertNotEqual(len(replacement), len(original))
        raw = archive({'images/image.ydg': original, 'opaque.bin': b'opaque member'})
        self.assertEqual(pack_archive(raw, {'images/image.ydg': original}), raw)
        rebuilt = pack_archive(raw, {'images/image.ydg': replacement})
        members = archive_members(rebuilt)
        self.assertEqual(members['opaque.bin'], b'opaque member')
        self.assertEqual(ydg.read_ydg(members['images/image.ydg']).pixels, canvas.tobytes())
        self.assertTrue(rebuilt.endswith(b'opaque trailer'))
        old_index = read_index(io.BytesIO(raw))[1]
        new_index = read_index(io.BytesIO(rebuilt))[1]
        self.assertEqual([(item.name, item.packed) for item in old_index],
                         [(item.name, item.packed) for item in new_index])
        old, new = old_index[1], new_index[1]
        self.assertEqual(raw[old.offset:old.offset + old.size], rebuilt[new.offset:new.offset + new.size])


@unittest.skipUnless(IMAGING, 'requires Pillow and fonttools')
class FontTests(unittest.TestCase):
    def test_cp932_pages_keep_undefined_slots_and_known_boundaries(self):
        pages = atlas.cp932_pages()
        self.assertEqual(pages[1][0], 0x81)
        self.assertEqual(pages[1][1][0], (0x40, '　'))
        self.assertEqual(pages[1][1][1], (0x41, '、'))
        self.assertEqual(len(pages[1][1]), 188)
        self.assertNotIn(0x7F, [trail for trail, _ in pages[1][1]])
        self.assertTrue(any(glyph is None for _, glyph in pages[1][1]))
        self.assertEqual(pages[len(pages)][0], 0xFC)

    def test_mapping_rejects_collisions_aliases_and_missing_page_proxies(self):
        self.assertEqual(atlas.reverse_mapping({'中': '　'}), {'　': '中'})
        for mapping in ({'中': '　', 'A': '　'}, {'long': '、'}, {'中': 'A'}, {'中': '\ue100'}):
            with self.assertRaises((ValueError, UnicodeError)):
                atlas.reverse_mapping(mapping)

    def test_render_styles_alpha_and_preserve_unselected_slots(self):
        with tempfile.TemporaryDirectory() as temp:
            font = Path(temp) / 'synthetic.ttf'
            rectangle_font(font)
            width, height = 456, 240
            original = bytes((11, 22, 33, 50)) * (width * height)
            grid = atlas.Grid(12, 24, 24, 19, 10)
            result, glyphs = atlas.render_page(original, width, height, 1, font, grid,
                mapping={'中': '　'}, mapped_only=True,
                style={'bold': 1, 'outline': 1, 'shadow_x': 1, 'shadow_y': 1,
                       'fill': [255, 255, 255, 128]},
                symbol_rules={'中': {'align': 'center'}})
            self.assertEqual(len(glyphs), 1)
            before, after = Image.frombytes('RGBA', (width, height), original), Image.frombytes('RGBA', (width, height), result)
            self.assertEqual(after.crop((24, 0, width, height)).tobytes(), before.crop((24, 0, width, height)).tobytes())
            self.assertNotEqual(after.crop((0, 0, 24, 24)).tobytes(), before.crop((0, 0, 24, 24)).tobytes())
            plain, _ = atlas.render_page(original, width, height, 1, font, grid,
                mapping={'中': '　'}, mapped_only=True, style={'fill': [255, 255, 255, 128]})
            self.assertIn(128, Image.frombytes('RGBA', (width, height), plain).getchannel('A').tobytes())
            for kwargs in ({'mapping': {'missing': '　'}}, {'mapping': {'文': '　'}},
                           {'mapping': {'中': '　'}, 'symbol_rules': {'中': {'dx': 100}}}):
                with self.assertRaises(ValueError):
                    atlas.render_page(original, width, height, 1, font, grid, mapped_only=True, **kwargs)
            with self.assertRaises(ValueError):
                atlas.Grid(12, 24, 24, 1, 1).validate(width, height)


@unittest.skipUnless(IMAGING, 'requires Pillow and fonttools')
class WorkflowTests(unittest.TestCase):
    def test_extract_pack_edits_metadata_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'source'
            source.mkdir()
            raw = fixture()
            (source / 'image.ydg').write_bytes(raw)
            work = root / 'extract'
            flow.extract(source, work)
            flow.pack(work, root / 'roundtrip')
            self.assertEqual((root / 'roundtrip/image.ydg').read_bytes(), raw)
            image_path = work / 'images/image.ydg.png'
            with Image.open(image_path) as image:
                image = image.convert('RGBA')
            image.putpixel((1, 0), (255, 80, 20, 255))
            image.save(image_path)
            flow.pack(work, root / 'translated')
            self.assertEqual(ydg.read_ydg((root / 'translated/image.ydg').read_bytes()).pixels, image.tobytes())
            self.assertEqual((source / 'image.ydg').read_bytes(), raw)
            for action, args in ((flow.extract, (source, work)), (flow.pack, (work, root / 'translated'))):
                with self.assertRaises(FileExistsError):
                    action(*args)
            sidecar = work / 'metadata/image.ydg.png.ydg.json'
            metadata = json.loads(sidecar.read_text('utf-8'))
            metadata['structure']['tiles'][0]['x'] = 2
            sidecar.write_text(json.dumps(metadata), encoding='utf-8')
            with self.assertRaises(ValueError):
                flow.pack(work, root / 'bad')
            self.assertFalse((root / 'bad').exists())

    def test_font_rebuild_pack_preview_and_coverage(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            font = root / 'synthetic.ttf'
            rectangle_font(font)
            raw = ydg.create_ydg(456, 240, bytes(456 * 240 * 4), section_height=80)
            source = root / 'fnt_s12_n1.ydg'
            source.write_bytes(raw)
            flow.extract(source, root / 'extract')
            config = root / 'grid.json'
            config.write_text(json.dumps({'grid': {'font_size': 12, 'cell_w': 24, 'cell_h': 24,
                                                   'columns': 19, 'rows': 10}}), encoding='utf-8')
            mapping = root / 'mapping.json'
            mapping.write_text(json.dumps({'chinese_to_proxy': {'中': '　'}}), encoding='utf-8')
            report = flow.font(root / 'extract', root / 'fonts', font_path=font,
                               config_path=config, mapping_path=mapping, mapped_only=True)
            self.assertEqual(len(report['resources'][0]['glyphs']), 1)
            result = ydg.read_ydg((root / 'fonts/fnt_s12_n1.ydg').read_bytes())
            self.assertTrue(any(result.pixels))
            self.assertEqual(ydg.read_png((root / 'fonts/preview/fnt_s12_n1.ydg.png').read_bytes(), 456, 240), result.pixels)
            mapping.write_text(json.dumps({'中': '亜'}), encoding='utf-8')
            with self.assertRaises(ValueError):
                flow.font(root / 'extract', root / 'uncovered', font_path=font,
                          config_path=config, mapping_path=mapping, mapped_only=True)
            self.assertFalse((root / 'uncovered').exists())

    def test_unknown_png_and_changed_original_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'image.ydg'
            source.write_bytes(fixture())
            flow.extract(source, root / 'work')
            (root / 'work/images/unknown.png').write_bytes(b'unknown')
            with self.assertRaises(ValueError):
                flow.pack(root / 'work', root / 'bad')
            (root / 'work/original/image.ydg').write_bytes(b'changed')
            with self.assertRaises(ValueError):
                flow.pack(root / 'work', root / 'changed')

    def test_font_coverage_is_per_size_and_mapping_formats(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            font = root / 'synthetic.ttf'
            rectangle_font(font)
            raw = ydg.create_ydg(456, 240, bytes(456 * 240 * 4))
            source = root / 'source'
            source.mkdir()
            (source / 'fnt_s12_n1.ydg').write_bytes(raw)
            (source / 'fnt_s14_n1.ydg').write_bytes(raw)
            flow.extract(source, root / 'work')
            config = root / 'grid.json'
            config.write_text(json.dumps({'grid': {'font_size': 12, 'cell_w': 24, 'cell_h': 24,
                'columns': 19, 'rows': 10}}), encoding='utf-8')
            mapping = root / 'uif.json'
            mapping.write_text(json.dumps({'character_substitution': {'enable': True,
                'source_characters': '　', 'target_characters': '中'}}), encoding='utf-8')
            report = flow.font(root / 'work', root / 'fonts', font_path=font,
                config_path=config, mapping_path=mapping, mapped_only=True)
            self.assertEqual(len(report['resources']), 2)
            mapping.write_text(json.dumps({'中': '亜'}), encoding='utf-8')
            pages = atlas.cp932_pages()
            page = next(number for number, (_, slots) in pages.items() if any(g == '亜' for _, g in slots))
            (source / f'fnt_s12_n{page}.ydg').write_bytes(raw)
            flow.extract(source, root / 'missing-size-page')
            with self.assertRaises(ValueError):
                flow.font(root / 'missing-size-page', root / 'bad', font_path=font,
                    config_path=config, mapping_path=mapping, mapped_only=True)
            self.assertFalse((root / 'bad').exists())


if __name__ == '__main__':
    unittest.main()
