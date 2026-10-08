# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: Lite0812 / Yuris_YDG_Tool contributors
# SPDX-FileCopyrightText: msg-tool contributors
"""Bounded YU-RIS YDG QOI/WebP tiles with template-preserving image writes.

Format research: Yuris_YDG_Tool YDG_Tool.py and msg-tool yuris/img/ydg.rs.
See provenance/yuris-ydg.json. Pillow provides codecs; no GUI or DLL loading.
"""
from dataclasses import dataclass
import io
import struct

MAGIC = b"YDG\0YU-RIS\0\0"
MAX_BYTES = 128 << 20
MAX_PIXELS = 16 << 20
QOI_END = b"\0\0\0\0\0\0\0\1"


def imaging():
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("YDG conversion requires Pillow with QOI/WebP support") from exc
    return Image


def _dimensions(width, height):
    if not 0 < width <= 8192 or not 0 < height <= 8192 or width * height > MAX_PIXELS:
        raise ValueError("YDG dimensions exceed budget")


def _qoi_structure(data):
    if len(data) < 22 or data[-8:] != QOI_END:
        raise ValueError("invalid QOI terminator")
    width, height, channels, colorspace = struct.unpack_from(">IIBB", data, 4)
    _dimensions(width, height)
    if channels not in (3, 4) or colorspace not in (0, 1):
        raise ValueError("invalid QOI channels/colorspace")
    # Validate exact opcode consumption before asking the image library to decode.
    position, pixels, end = 14, 0, len(data) - 8
    while pixels < width * height:
        if position >= end:
            raise ValueError("truncated QOI pixels")
        code = data[position]
        position += 1
        extra = 3 if code == 254 else 4 if code == 255 else 1 if code & 192 == 128 else 0
        run = (code & 63) + 1 if 192 <= code < 254 else 1
        position += extra
        pixels += run
        if position > end or pixels > width * height:
            raise ValueError("truncated QOI opcode or oversized run")
    if position != end:
        raise ValueError("unconsumed QOI payload")
    return width, height, channels, colorspace


def _decode(data):
    Image = imaging()
    if data.startswith(b"qoif"):
        width, height, channels, colorspace = _qoi_structure(data)
        codec = "qoi"
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        if len(data) < 20 or struct.unpack_from("<I", data, 4)[0] + 8 != len(data):
            raise ValueError("invalid WebP RIFF length")
        codec, colorspace = "webp", 0
        with Image.open(io.BytesIO(data), formats=["WEBP"]) as image:
            width, height = image.size
            _dimensions(width, height)
            channels = 4 if "A" in image.getbands() else 3
            if getattr(image, "n_frames", 1) != 1:
                raise ValueError("animated WebP is not a YDG tile")
    else:
        raise ValueError("unsupported YDG tile codec")
    with Image.open(io.BytesIO(data), formats=[codec.upper()]) as image:
        if image.size != (width, height):
            raise ValueError("tile dimensions changed during decode")
        pixels = image.convert("RGBA").tobytes()
    return codec, width, height, channels, colorspace, pixels


def _encode(codec, width, height, pixels, channels=4, colorspace=0):
    Image = imaging()
    _dimensions(width, height)
    if len(pixels) != width * height * 4:
        raise ValueError("RGBA payload size mismatch")
    image = Image.frombytes("RGBA", (width, height), pixels)
    output = io.BytesIO()
    if codec == "qoi":
        if channels == 3:
            if any(alpha != 255 for alpha in pixels[3::4]):
                raise ValueError("RGB QOI tile cannot retain translated alpha")
            image = image.convert("RGB")
        image.save(output, format="QOI", colorspace="sRGB" if colorspace == 0 else "linear")
    elif codec == "webp":
        image.save(output, format="WEBP", lossless=True, exact=True, method=6)
    else:
        raise ValueError("unsupported YDG tile codec")
    data = output.getvalue()
    if _decode(data)[-1] != pixels:
        raise ValueError("image codec did not retain exact RGBA pixels")
    return data


@dataclass(frozen=True)
class Tile:
    offset: int
    size: int
    x: int
    y: int
    width: int
    height: int
    reserved: int
    codec: str
    channels: int
    colorspace: int
    pixels: bytes


@dataclass(frozen=True)
class Resource:
    width: int
    height: int
    table_offset: int
    tiles: tuple[Tile, ...]
    pixels: bytes


def read_ydg(data: bytes) -> Resource:
    if not isinstance(data, bytes) or not 40 <= len(data) <= MAX_BYTES or data[:12] != MAGIC:
        raise ValueError("expected bounded YDG resource")
    version, header_size, file_size = struct.unpack_from("<III", data, 12)
    if version != 100 or not 36 <= header_size <= 4096 or header_size + 4 > len(data):
        raise ValueError("unsupported YDG version/header layout")
    if file_size != len(data):
        raise ValueError("YDG file size mismatch")
    width, height = struct.unpack_from("<HH", data, 32)
    _dimensions(width, height)
    count, = struct.unpack_from("<I", data, header_size)
    table_offset, table_end = header_size + 4, header_size + 4 + count * 16
    if not 0 < count <= height or table_end > len(data):
        raise ValueError("invalid YDG tile table")
    descriptors = [struct.unpack_from("<IIHHI", data, table_offset + i * 16) for i in range(count)]
    previous = table_end
    for offset, size, x, tile_height, reserved in sorted(descriptors):
        if not size or offset < previous or offset + size > len(data):
            raise ValueError("overlapping or out-of-range YDG tiles")
        previous = offset + size
    canvas = imaging().new("RGBA", (width, height), (0, 0, 0, 0))
    tiles, y = [], 0
    for offset, size, x, tile_height, reserved in descriptors:
        codec, tw, th, channels, colorspace, pixels = _decode(data[offset:offset + size])
        if th != tile_height or y + th > height or x + tw > width:
            raise ValueError("YDG tile geometry mismatch")
        canvas.paste(imaging().frombytes("RGBA", (tw, th), pixels), (x, y))
        tiles.append(Tile(offset, size, x, y, tw, th, reserved, codec, channels, colorspace, pixels))
        y += th
    if y != height:
        raise ValueError("YDG tile heights do not cover canvas")
    return Resource(width, height, table_offset, tuple(tiles), canvas.tobytes())


def rebuild_ydg(original: bytes, pixels: bytes) -> bytes:
    resource = read_ydg(original)
    if not isinstance(pixels, bytes) or len(pixels) != resource.width * resource.height * 4:
        raise ValueError("replacement must retain YDG canvas dimensions")
    Image = imaging()
    canvas = Image.frombytes("RGBA", (resource.width, resource.height), pixels)
    chunks = {}
    for tile in resource.tiles:
        value = canvas.crop((tile.x, tile.y, tile.x + tile.width, tile.y + tile.height)).tobytes()
        chunks[tile.offset] = (original[tile.offset:tile.offset + tile.size] if value == tile.pixels
                              else _encode(tile.codec, tile.width, tile.height, value,
                                           tile.channels, tile.colorspace))
    table_end = resource.table_offset + len(resource.tiles) * 16
    out, cursor, offsets = bytearray(original[:table_end]), table_end, {}
    for tile in sorted(resource.tiles, key=lambda item: item.offset):
        out.extend(original[cursor:tile.offset])
        offsets[tile.offset] = len(out)
        out.extend(chunks[tile.offset])
        cursor = tile.offset + tile.size
    out.extend(original[cursor:])
    if len(out) > MAX_BYTES:
        raise ValueError("rebuilt YDG exceeds budget")
    for index, tile in enumerate(resource.tiles):
        struct.pack_into("<II", out, resource.table_offset + index * 16,
                         offsets[tile.offset], len(chunks[tile.offset]))
    struct.pack_into("<I", out, 20, len(out))
    result = bytes(out)
    check = read_ydg(result)
    if check.pixels != pixels:
        raise ValueError("replacement changes pixels outside original tile rectangles")
    return result


def create_ydg(width, height, pixels, *, codec="qoi", section_height=160):
    """Explicit new format-100 resource; template rebuild is preferred for games."""
    _dimensions(width, height)
    if type(section_height) is not int or section_height <= 0:
        raise ValueError("invalid section height")
    if len(pixels) != width * height * 4:
        raise ValueError("RGBA payload size mismatch")
    heights = [min(section_height, height - y) for y in range(0, height, section_height)]
    out = bytearray(52 + len(heights) * 16)
    out[:12] = MAGIC
    struct.pack_into("<II", out, 12, 100, 48)
    struct.pack_into("<HH", out, 32, width, height)
    struct.pack_into("<I", out, 48, len(heights))
    y = 0
    for index, th in enumerate(heights):
        data = _encode(codec, width, th, pixels[y * width * 4:(y + th) * width * 4])
        struct.pack_into("<IIHHI", out, 52 + index * 16, len(out), len(data), 0, th, 0)
        out.extend(data)
        y += th
    struct.pack_into("<I", out, 20, len(out))
    result = bytes(out)
    if read_ydg(result).pixels != pixels:
        raise ValueError("new YDG verification failed")
    return result


def png_bytes(resource):
    image = imaging().frombytes("RGBA", (resource.width, resource.height), resource.pixels)
    stream = io.BytesIO()
    image.save(stream, format="PNG", compress_level=4)
    return stream.getvalue()


def read_png(data, width, height):
    if len(data) > MAX_BYTES:
        raise ValueError("PNG exceeds budget")
    with imaging().open(io.BytesIO(data), formats=["PNG"]) as image:
        if image.size != (width, height) or getattr(image, "n_frames", 1) != 1:
            raise ValueError("PNG must retain original dimensions and a single frame")
        return image.convert("RGBA").tobytes()
