"""Bounded TLG5 decoder, raw encoder and PNG writer for KiriKiri images.

Only the ``TLG5.0\\0raw\\x1a`` variant with 3 or 4 colour channels is accepted.
TLG6 (Golomb/median filters), TLG0 ``sds``, indexed ``idx`` and QOI/mux/ref
variants are rejected instead of being half-decoded. The decoder is a pure
standard-library port of GARbro-Mod's ``ArcFormats/KiriKiri/ImageTLG.cs``
(MIT, Copyright (c) 2014-2020 morkt), itself a C# port of W.Dee's TLG5/6
decoder (Copyright (C) 2000-2005 W.Dee). Full notice:
provenance/licenses/MIT-GARbro.txt.

Layout (TLG5 raw):
  11 bytes  ``TLG5.0\\0raw\\x1a``
  u8        colours (3 = BGR, 4 = BGRA)
  u32le     width
  u32le     height
  u32le     block height
  u32le[]   per-block compressed sizes (skipped; the stream is authoritative)
  blocks    per row-block, per channel: u8 mark, u32le size, payload
             mark 0 = TLG5 LZSS, mark 1 = raw bytes

The output pixel order is BGRA for 4 channels and BGR + 0xff for 3 channels;
``encode_png`` converts it to RGBA. ``encode`` writes the inverse delta planes
with raw channel blocks (mark 1) and a matching block-size table; it does not
produce LZSS, so output is lossless but larger than compressed originals. No
game code is executed and every read is bounded by an explicit budget.
"""
from dataclasses import dataclass
import argparse
import struct
import sys
import zlib
from pathlib import Path

MAGIC5 = b"TLG5.0\x00raw\x1a"
MAGIC6 = b"TLG6.0\x00raw\x1a"
HEADER5 = 20
MAX_INPUT = 256 << 20
MAX_PIXELS = 64_000_000
MAX_FILES = 10_000
MAX_TOTAL_PIXELS = 500_000_000


@dataclass(frozen=True)
class TlgImage:
    width: int
    height: int
    channels: int
    pixels: bytes          # BGRA (4) or BGR + 0xff (3), stride = width * 4
    version: int = 5


def info(data: bytes) -> dict:
    """Return header fields without decoding the body."""
    _check_input(data)
    version = _header_version(data)
    colours, width, height, offset = _header_fields(data, version)
    return {"version": version, "width": width, "height": height,
            "channels": colours, "data_offset": offset}


def _check_input(data: bytes) -> None:
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise ValueError("TLG input must be bytes")
    if len(data) > MAX_INPUT:
        raise ValueError("TLG input exceeds the size budget")
    if len(data) < HEADER5:
        raise ValueError("truncated TLG header")


def _header_version(data: bytes) -> int:
    if data[:len(MAGIC5)] == MAGIC5:
        return 5
    if data[:len(MAGIC6)] == MAGIC6:
        return 6
    if data[:11].startswith(b"TLG6."):
        raise ValueError("TLG6 is not supported (only TLG5 raw)")
    if data[:11].startswith(b"TLG5."):
        raise ValueError("unsupported TLG5 variant (only TLG5.0 raw)")
    raise ValueError("not a TLG5 raw image")


def _header_fields(data: bytes, version: int):
    if version != 5:
        raise ValueError("TLG6 is not supported (only TLG5 raw)")
    colours = data[11]
    if colours not in (3, 4):
        raise ValueError("TLG5 supports only 3 or 4 colour channels")
    offset = 12
    if len(data) < offset + 8:
        raise ValueError("truncated TLG5 header")
    width, height = struct.unpack_from("<II", data, offset)
    if width == 0 or height == 0:
        raise ValueError("zero TLG dimensions")
    if width * height > MAX_PIXELS:
        raise ValueError("TLG pixel budget exceeded")
    return colours, width, height, offset + 8


def _lzss_decompress(inbuf: bytes, outbuf: bytearray, text: bytearray, r: int) -> tuple[int, int]:
    """TLG5 LZSS; returns (output_length, ring_position). Rejects overrun."""
    limit = len(outbuf)
    o = 0
    i = 0
    n = len(inbuf)
    flags = 0
    while i < n:
        flags >>= 1
        if (flags & 0x100) == 0:
            if i >= n:
                raise ValueError("truncated TLG5 LZSS flags")
            flags = inbuf[i] | 0xFF00
            i += 1
        if flags & 1:
            if i + 2 > n:
                raise ValueError("truncated TLG5 LZSS match")
            mpos = inbuf[i] | ((inbuf[i + 1] & 0x0F) << 8)
            mlen = (inbuf[i + 1] >> 4) + 3
            i += 2
            if mlen == 18:
                if i >= n:
                    raise ValueError("truncated TLG5 LZSS length")
                mlen += inbuf[i]
                i += 1
            if o + mlen > limit:
                raise ValueError("TLG5 LZSS output exceeds the block")
            for _ in range(mlen):
                value = text[mpos]
                text[r] = value
                mpos = (mpos + 1) & 4095
                r = (r + 1) & 4095
                outbuf[o] = value
                o += 1
        else:
            if i >= n:
                raise ValueError("truncated TLG5 LZSS literal")
            if o >= limit:
                raise ValueError("TLG5 LZSS output exceeds the block")
            value = inbuf[i]
            i += 1
            outbuf[o] = value
            o += 1
            text[r] = value
            r = (r + 1) & 4095
    return o, r


def _compose(planes, width: int, y0: int, rows: int, image: bytearray, channels: int) -> None:
    """Undo TLG5 per-line/per-channel delta coding into BGRA pixels."""
    stride = width * 4
    for row in range(rows):
        y = y0 + row
        base = y * stride
        src = row * width
        p0, p1, p2 = planes[0], planes[1], planes[2]
        if y == 0:
            pb = pg = pr = pa = 0
            for x in range(width):
                g = p1[src + x]
                b = p0[src + x] + g
                r = p2[src + x] + g
                pb = (pb + b) & 0xFF
                pg = (pg + g) & 0xFF
                pr = (pr + r) & 0xFF
                out = base + x * 4
                image[out] = pb
                image[out + 1] = pg
                image[out + 2] = pr
                if channels == 4:
                    pa = (pa + planes[3][src + x]) & 0xFF
                    image[out + 3] = pa
                else:
                    image[out + 3] = 0xFF
        else:
            prev = base - stride
            pc0 = pc1 = pc2 = pc3 = 0
            for x in range(width):
                c1 = p1[src + x]
                c0 = p0[src + x] + c1
                c2 = p2[src + x] + c1
                pc0 = (pc0 + c0) & 0xFF
                pc1 = (pc1 + c1) & 0xFF
                pc2 = (pc2 + c2) & 0xFF
                out = base + x * 4
                image[out] = (pc0 + image[prev + x * 4]) & 0xFF
                image[out + 1] = (pc1 + image[prev + x * 4 + 1]) & 0xFF
                image[out + 2] = (pc2 + image[prev + x * 4 + 2]) & 0xFF
                if channels == 4:
                    pc3 = (pc3 + planes[3][src + x]) & 0xFF
                    image[out + 3] = (pc3 + image[prev + x * 4 + 3]) & 0xFF
                else:
                    image[out + 3] = 0xFF


def decode(data: bytes, *, max_pixels: int = MAX_PIXELS) -> TlgImage:
    """Decode a TLG5 raw image; raises ValueError on any unsupported layout."""
    _check_input(data)
    version = _header_version(data)
    colours, width, height, offset = _header_fields(data, version)
    if width * height > max_pixels:
        raise ValueError("TLG pixel budget exceeded")

    if offset + 4 > len(data):
        raise ValueError("truncated TLG block header")
    block_height = struct.unpack_from("<I", data, offset)[0]
    if block_height == 0:
        raise ValueError("zero TLG block height")
    block_count = (height - 1) // block_height + 1
    offset += 4
    table_bytes = block_count * 4
    if table_bytes > len(data) - offset:
        raise ValueError("truncated TLG block table")
    offset += table_bytes

    image = bytearray(height * width * 4)
    text = bytearray(4096)
    ring = 0
    for y in range(0, height, block_height):
        rows = min(block_height, height - y)
        expected = rows * width
        planes = []
        for channel in range(colours):
            if offset + 5 > len(data):
                raise ValueError("truncated TLG block channel")
            mark = data[offset]
            size = struct.unpack_from("<I", data, offset + 1)[0]
            offset += 5
            if size > len(data) - offset:
                raise ValueError("truncated TLG channel payload")
            payload = data[offset:offset + size]
            offset += size
            if mark == 0:
                outbuf = bytearray(expected)
                produced, ring = _lzss_decompress(payload, outbuf, text, ring)
                if produced != expected:
                    raise ValueError("TLG LZSS channel size mismatch")
                plane = bytes(outbuf)
            elif mark == 1:
                if size != expected:
                    raise ValueError("TLG raw channel size mismatch")
                plane = bytes(payload)
            else:
                raise ValueError("unknown TLG channel compression mark")
            planes.append(plane)
        _compose(planes, width, y, rows, image, colours)
    if offset != len(data):
        raise ValueError("trailing bytes after the last TLG block")
    return TlgImage(width=width, height=height, channels=colours,
                    pixels=bytes(image), version=version)


def encode(image: TlgImage, *, block_height: int = 16) -> bytes:
    """Encode pixels as a lossless TLG5 raw stream.

    Raw channel blocks (mark 1) keep every BGRA byte; the block-size table is
    written with the exact per-block byte counts. This is a writer for patching,
    not a size-optimised encoder: LZSS compression is not produced.
    """
    if image.width <= 0 or image.height <= 0 or image.width * image.height > MAX_PIXELS:
        raise ValueError("TLG dimension budget")
    if image.channels not in (3, 4):
        raise ValueError("TLG5 supports only 3 or 4 colour channels")
    stride = image.width * 4
    if len(image.pixels) != stride * image.height:
        raise ValueError("TLG pixel buffer size mismatch")
    if block_height <= 0 or block_height > image.height:
        block_height = max(1, min(64, image.height))
    block_count = (image.height - 1) // block_height + 1
    block_payloads = []
    block_sizes = []
    for block in range(block_count):
        y0 = block * block_height
        rows = min(block_height, image.height - y0)
        planes = _delta_planes(image, y0, rows)
        payloads = []
        total = 0
        for plane in planes:
            total += 5 + len(plane)
            payloads.append((1, plane))
        block_payloads.append(payloads)
        block_sizes.append(total)

    out = bytearray(MAGIC5)
    out.append(image.channels)
    out.extend(struct.pack("<II", image.width, image.height))
    out.extend(struct.pack("<I", block_height))
    out.extend(struct.pack("<%dI" % block_count, *block_sizes))
    for payloads in block_payloads:
        for mark, payload in payloads:
            out.append(mark)
            out.extend(struct.pack("<I", len(payload)))
            out.extend(payload)
    return bytes(out)


def _delta_planes(image: TlgImage, y0: int, rows: int) -> list[bytes]:
    width = image.width
    channels = image.channels
    stride = width * 4
    planes = [bytearray(rows * width) for _ in range(channels)]
    for row in range(rows):
        y = y0 + row
        base = y * stride
        src = row * width
        pc0 = pc1 = pc2 = pc3 = 0
        if y == 0:
            for x in range(width):
                at = base + x * 4
                b, g, r, a = image.pixels[at:at + 4]
                c1 = (g - pc1) & 0xFF
                c0 = (b - pc0 - c1) & 0xFF
                c2 = (r - pc2 - c1) & 0xFF
                planes[0][src + x] = c0
                planes[1][src + x] = c1
                planes[2][src + x] = c2
                if channels == 4:
                    c3 = (a - pc3) & 0xFF
                    planes[3][src + x] = c3
                    pc3 = (pc3 + c3) & 0xFF
                pc0 = (pc0 + c0 + c1) & 0xFF
                pc1 = (pc1 + c1) & 0xFF
                pc2 = (pc2 + c2 + c1) & 0xFF
        else:
            prev = base - stride
            for x in range(width):
                at = base + x * 4
                b, g, r, a = image.pixels[at:at + 4]
                pb = image.pixels[prev + x * 4]
                pg = image.pixels[prev + x * 4 + 1]
                pr = image.pixels[prev + x * 4 + 2]
                c1 = (g - pc1 - pg) & 0xFF
                c0 = (b - pc0 - pb - c1) & 0xFF
                c2 = (r - pc2 - pr - c1) & 0xFF
                planes[0][src + x] = c0
                planes[1][src + x] = c1
                planes[2][src + x] = c2
                if channels == 4:
                    pa = image.pixels[prev + x * 4 + 3]
                    c3 = (a - pc3 - pa) & 0xFF
                    planes[3][src + x] = c3
                    pc3 = (pc3 + c3) & 0xFF
                pc0 = (pc0 + c0 + c1) & 0xFF
                pc1 = (pc1 + c1) & 0xFF
                pc2 = (pc2 + c2 + c1) & 0xFF
    return [bytes(plane) for plane in planes]


def encode_png(image: TlgImage, *, level: int = 6) -> bytes:
    """Encode a decoded image as a filter-0 RGBA PNG (standard library only)."""
    if image.width <= 0 or image.height <= 0 or image.width * image.height > MAX_PIXELS:
        raise ValueError("PNG dimension budget")
    stride = image.width * 4
    if len(image.pixels) != stride * image.height:
        raise ValueError("TLG pixel buffer size mismatch")
    raw = bytearray()
    for y in range(image.height):
        row = image.pixels[y * stride:(y + 1) * stride]
        rgba = bytearray(stride)
        rgba[0::4] = row[2::4]
        rgba[1::4] = row[1::4]
        rgba[2::4] = row[0::4]
        rgba[3::4] = row[3::4]
        raw.append(0)
        raw.extend(rgba)

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", image.width, image.height, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(bytes(raw), level)) + chunk(b"IEND", b""))


def decode_file(path: Path, *, max_pixels: int = MAX_PIXELS) -> TlgImage:
    data = Path(path).read_bytes()
    return decode(data, max_pixels=max_pixels)


def from_rgba_png(path: Path) -> TlgImage:
    """Load an RGBA PNG with Pillow and convert it to a BGRA TlgImage."""
    try:
        from PIL import Image
    except ImportError as ex:
        raise RuntimeError("Pillow is required to read PNG input") from ex
    with Image.open(path) as source:
        image = source.convert("RGBA")
        width, height = image.size
        if width * height > MAX_PIXELS:
            raise ValueError("PNG pixel budget exceeded")
        rgba = image.tobytes()
        pixels = bytearray(len(rgba))
        pixels[0::4] = rgba[2::4]
        pixels[1::4] = rgba[1::4]
        pixels[2::4] = rgba[0::4]
        pixels[3::4] = rgba[3::4]
    return TlgImage(width=width, height=height, channels=4, pixels=bytes(pixels))


def _convert_tree(source: Path, destination: Path) -> list[Path]:
    if destination.exists():
        raise FileExistsError(f"refusing existing output: {destination}")
    files = sorted(p for p in source.rglob("*") if p.is_file() and p.suffix.lower() == ".tlg")
    if not files or len(files) > MAX_FILES:
        raise ValueError("TLG file count budget")
    total_pixels = 0
    for path in files:
        header = info(path.read_bytes()[:HEADER5 + 16])
        total_pixels += header["width"] * header["height"]
        if total_pixels > MAX_TOTAL_PIXELS:
            raise ValueError("TLG cumulative pixel budget")
    destination.mkdir(parents=True)
    written = []
    for path in files:
        relative = path.relative_to(source).with_suffix(".png")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        image = decode_file(path)
        target.write_bytes(encode_png(image))
        written.append(target)
    return written


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    info_parser = sub.add_parser("info", help="print TLG5 header fields")
    info_parser.add_argument("input", type=Path)
    convert = sub.add_parser("convert", help="decode TLG5 to PNG")
    convert.add_argument("input", type=Path, help=".tlg file or directory")
    convert.add_argument("output", type=Path, help=".png file or new output directory")
    pack = sub.add_parser("encode", help="encode an RGBA PNG as TLG5 raw")
    pack.add_argument("input", type=Path)
    pack.add_argument("output", type=Path)
    args = parser.parse_args()

    if args.command == "info":
        print(info(args.input.read_bytes()))
        return

    if args.command == "encode":
        if args.output.exists():
            raise FileExistsError(f"refusing existing output: {args.output}")
        image = from_rgba_png(args.input)
        data = encode(image)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(data)
        print(f"{args.input.name}: {image.width}x{image.height} -> {args.output} "
              f"({len(data)} bytes, raw blocks)")
        return

    if args.input.is_dir():
        written = _convert_tree(args.input, args.output)
        print(f"converted {len(written)} file(s) to {args.output}")
        return
    if args.output.exists():
        raise FileExistsError(f"refusing existing output: {args.output}")
    image = decode_file(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(encode_png(image))
    print(f"{args.input.name}: {image.width}x{image.height} -> {args.output}")


if __name__ == "__main__":
    main()
