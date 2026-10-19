"""Synthetic TLG5 fixtures for the bounded decoder and PNG writer."""
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from python.engines.kirikiri_tlg import (MAGIC5, TlgImage, decode, encode,
                                         encode_png, from_rgba_png, info,
                                         _lzss_decompress)


def _pack_tlg5(width, height, channels, pixels, *, block_height=None, lzss=False):
    """Build a TLG5 raw stream from BGRA pixels (alpha ignored for 3 channels)."""
    if block_height is None:
        block_height = height
    stride = width * 4
    planes = [bytearray() for _ in range(channels)]
    previous = None
    for y in range(height):
        pc0 = pc1 = pc2 = pc3 = 0
        current = []
        for x in range(width):
            at = y * stride + x * 4
            b, g, r, a = pixels[at:at + 4]
            current.append((b, g, r, a))
            if y == 0:
                c1 = (g - pc1) & 0xFF
                c0 = (b - pc0 - c1) & 0xFF
                c2 = (r - pc2 - c1) & 0xFF
                c3 = (a - pc3) & 0xFF
                pc0 = (pc0 + c0 + c1) & 0xFF
                pc1 = (pc1 + c1) & 0xFF
                pc2 = (pc2 + c2 + c1) & 0xFF
                pc3 = (pc3 + c3) & 0xFF
            else:
                pb, pg, pr, pa = previous[x]
                c1 = (g - pc1 - pg) & 0xFF
                c0 = (b - pc0 - pb - c1) & 0xFF
                c2 = (r - pc2 - pr - c1) & 0xFF
                c3 = (a - pc3 - pa) & 0xFF
                pc0 = (pc0 + c0 + c1) & 0xFF
                pc1 = (pc1 + c1) & 0xFF
                pc2 = (pc2 + c2 + c1) & 0xFF
                pc3 = (pc3 + c3) & 0xFF
            planes[0].append(c0)
            planes[1].append(c1)
            planes[2].append(c2)
            if channels == 4:
                planes[3].append(c3)
        previous = current

    block_count = (height - 1) // block_height + 1
    out = bytearray(MAGIC5)
    out.append(channels)
    out.extend(struct.pack("<II", width, height))
    out.extend(struct.pack("<I", block_height))
    out.extend(b"\0" * (block_count * 4))
    for block in range(block_count):
        y0 = block * block_height
        rows = min(block_height, height - y0)
        for channel in range(channels):
            plane = bytes(planes[channel][y0 * width:(y0 + rows) * width])
            if lzss:
                payload = bytearray()
                for at in range(0, len(plane), 8):
                    payload.append(0)
                    payload.extend(plane[at:at + 8])
                out.append(0)
            else:
                payload = plane
                out.append(1)
            out.extend(struct.pack("<I", len(payload)))
            out.extend(payload)
    return bytes(out)


def _zero_plane_lzss(length):
    """Literal zero followed by one match copy; exercises the match path."""
    payload = bytearray([0x02])        # flags: bit0 literal, bit1 match
    payload.append(0)                  # literal zero
    payload.append(0x00)               # match position low
    payload.append((min(length - 1, 18) - 3) << 4)  # match length high nibble
    if length - 1 > 18:
        payload.append(length - 1 - 18)
    return bytes(payload)


class Tlg5DecodeTests(unittest.TestCase):
    def test_raw_rgba(self):
        pixels = bytes([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16])
        data = _pack_tlg5(2, 2, 4, pixels)
        image = decode(data)
        self.assertEqual((image.width, image.height, image.channels), (2, 2, 4))
        self.assertEqual(image.pixels, pixels)

    def test_raw_rgb_sets_opaque_alpha(self):
        pixels = bytes([10, 20, 30, 0, 40, 50, 60, 0, 70, 80, 90, 0, 100, 110, 120, 0])
        image = decode(_pack_tlg5(2, 2, 3, pixels))
        self.assertEqual(image.channels, 3)
        self.assertEqual(image.pixels[3::4], b"\xff\xff\xff\xff")
        self.assertEqual(image.pixels[0::4], bytes([10, 40, 70, 100]))
        self.assertEqual(image.pixels[1::4], bytes([20, 50, 80, 110]))
        self.assertEqual(image.pixels[2::4], bytes([30, 60, 90, 120]))

    def test_lzss_literals(self):
        pixels = bytes(range(1, 4 * 3 * 2 + 1))
        data = _pack_tlg5(3, 2, 4, pixels, lzss=True)
        self.assertEqual(decode(data).pixels, pixels)

    def test_lzss_match(self):
        # One literal and one match per channel; the ring starts zero-filled.
        planes = []
        for _ in range(4):
            encoded = _zero_plane_lzss(4)
            planes.append((0, encoded))
        out = bytearray(MAGIC5)
        out.append(4)
        out.extend(struct.pack("<II", 2, 2))
        out.extend(struct.pack("<I", 2))
        out.extend(b"\0" * 4)
        for mark, payload in planes:
            out.append(mark)
            out.extend(struct.pack("<I", len(payload)))
            out.extend(payload)
        image = decode(bytes(out))
        self.assertEqual(image.pixels, bytes(16))

    def test_block_split(self):
        pixels = bytes([x & 0xFF for x in range(2 * 5 * 4)])
        data = _pack_tlg5(2, 5, 4, pixels, block_height=2)
        self.assertEqual(decode(data).pixels, pixels)

    def test_info(self):
        data = _pack_tlg5(4, 3, 3, bytes(4 * 3 * 4))
        fields = info(data)
        self.assertEqual(fields["width"], 4)
        self.assertEqual(fields["height"], 3)
        self.assertEqual(fields["channels"], 3)
        self.assertEqual(fields["version"], 5)

    def test_rejects_tlg6(self):
        data = b"TLG6.0\x00raw\x1a" + bytes(40)
        with self.assertRaisesRegex(ValueError, "TLG6"):
            decode(data)

    def test_rejects_bad_colours(self):
        data = bytearray(_pack_tlg5(1, 1, 3, bytes(4)))
        data[11] = 2
        with self.assertRaisesRegex(ValueError, "colour"):
            decode(bytes(data))

    def test_rejects_zero_block_height(self):
        data = bytearray(_pack_tlg5(1, 1, 3, bytes(4)))
        struct.pack_into("<I", data, 20, 0)
        with self.assertRaisesRegex(ValueError, "block height"):
            decode(bytes(data))

    def test_rejects_truncated(self):
        data = _pack_tlg5(2, 2, 4, bytes(16))
        with self.assertRaises(ValueError):
            decode(data[:-4])

    def test_rejects_trailing_bytes(self):
        data = _pack_tlg5(1, 1, 3, bytes(4))
        with self.assertRaisesRegex(ValueError, "trailing"):
            decode(data + b"x")

    def test_rejects_pixel_budget(self):
        data = _pack_tlg5(2, 2, 4, bytes(16))
        with self.assertRaisesRegex(ValueError, "pixel budget"):
            decode(data, max_pixels=3)

    def test_lzss_output_overrun(self):
        out = bytearray(2)
        text = bytearray(4096)
        with self.assertRaises(ValueError):
            _lzss_decompress(b"\x00\x00\x00\x00", out, text, 0)


class Tlg5EncodeTests(unittest.TestCase):
    def test_roundtrip_rgba(self):
        pixels = bytes((x * 7) & 0xFF for x in range(3 * 4 * 4))
        image = TlgImage(width=3, height=4, channels=4, pixels=pixels)
        data = encode(image, block_height=2)
        self.assertEqual(data[:11], MAGIC5)
        self.assertEqual(decode(data).pixels, pixels)

    def test_roundtrip_rgb(self):
        pixels = bytes((x * 11) & 0xFF for x in range(2 * 3 * 4))
        image = TlgImage(width=2, height=3, channels=3, pixels=pixels)
        decoded = decode(encode(image))
        self.assertEqual(decoded.pixels[0::4], pixels[0::4])
        self.assertEqual(decoded.pixels[1::4], pixels[1::4])
        self.assertEqual(decoded.pixels[2::4], pixels[2::4])
        self.assertEqual(decoded.pixels[3::4], b"\xff" * 6)

    def test_block_table_matches_stream(self):
        pixels = bytes(range(2 * 5 * 4))
        image = TlgImage(width=2, height=5, channels=4, pixels=pixels)
        data = encode(image, block_height=2)
        block_height = struct.unpack_from("<I", data, 20)[0]
        block_count = (image.height - 1) // block_height + 1
        table = struct.unpack_from("<%dI" % block_count, data, 24)
        at = 24 + block_count * 4
        for expected in table:
            start = at
            for _ in range(image.channels):
                size = struct.unpack_from("<I", data, at + 1)[0]
                at += 5 + size
            self.assertEqual(at - start, expected)
        self.assertEqual(at, len(data))

    def test_rejects_wrong_pixel_count(self):
        image = TlgImage(width=2, height=2, channels=4, pixels=bytes(15))
        with self.assertRaises(ValueError):
            encode(image)

    def test_png_input_roundtrip(self):
        try:
            import PIL  # noqa: F401
        except ImportError:
            self.skipTest("Pillow not installed")
        pixels = bytes((x * 5) & 0xFF for x in range(2 * 2 * 4))
        image = TlgImage(width=2, height=2, channels=4, pixels=pixels)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.png"
            path.write_bytes(encode_png(image))
            loaded = from_rgba_png(path)
            self.assertEqual(loaded.pixels, pixels)
            self.assertEqual(decode(encode(loaded)).pixels, pixels)


class PngWriterTests(unittest.TestCase):
    def test_png_roundtrip(self):
        pixels = bytes([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16])
        image = TlgImage(width=2, height=2, channels=4, pixels=pixels)
        png = encode_png(image)
        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        width, height = struct.unpack(">II", png[16:24])
        self.assertEqual((width, height), (2, 2))
        # Collect IDAT and verify filter-0 scanlines are RGBA, not BGRA.
        at = 8
        idat = b""
        while at < len(png):
            size = struct.unpack(">I", png[at:at + 4])[0]
            tag = png[at + 4:at + 8]
            body = png[at + 8:at + 8 + size]
            if tag == b"IDAT":
                idat += body
            at += 12 + size
        raw = zlib.decompress(idat)
        self.assertEqual(raw[0], 0)
        self.assertEqual(raw[1:5], bytes([3, 2, 1, 4]))
        self.assertEqual(raw[9], 0)
        self.assertEqual(raw[10:14], bytes([11, 10, 9, 12]))

    def test_rejects_size_mismatch(self):
        image = TlgImage(width=2, height=2, channels=4, pixels=bytes(15))
        with self.assertRaises(ValueError):
            encode_png(image)


if __name__ == "__main__":
    unittest.main()
