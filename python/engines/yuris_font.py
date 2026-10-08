# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: Lite0812 / Yuris_YDG_Tool contributors
"""Explicit CP932 page layout and bounded glyph rendering for YDG font atlases.

Page order research: Yuris_YDG_Tool; provenance/yuris-ydg.json. Grid dimensions
are caller evidence, not engine defaults. JIS data remains in common modules.
"""
from dataclasses import dataclass
from pathlib import Path

from .yuris_ydg import imaging, _dimensions

LEADS = (*range(0x81, 0xA0), *range(0xE0, 0xF1), *range(0xFA, 0xFD))
TRAILS = (*range(0x40, 0x7F), *range(0x80, 0xFD))


def cp932_pages():
    """One-based pages; undefined byte pairs keep their original slot positions."""
    pages = {}
    for lead in LEADS:
        entries = []
        for trail in TRAILS:
            try:
                glyph = bytes((lead, trail)).decode("cp932", "strict")
            except UnicodeDecodeError:
                glyph = None
            entries.append((trail, glyph))
        if any(glyph is not None for _, glyph in entries):
            pages[len(pages) + 1] = (lead, tuple(entries))
    return pages


@dataclass(frozen=True)
class Grid:
    font_size: int
    cell_w: int
    cell_h: int
    columns: int
    rows: int
    offset_x: int = 0
    offset_y: int = 0

    def validate(self, width, height):
        _dimensions(width, height)
        if any(type(value) is not int for value in self.__dict__.values()):
            raise ValueError("font grid fields must be integers")
        if min(self.font_size, self.cell_w, self.cell_h, self.columns, self.rows) <= 0:
            raise ValueError("font grid sizes must be positive")
        if self.font_size > 512 or self.columns * self.rows < len(TRAILS):
            raise ValueError("font grid must contain all CP932 slots")
        if (min(self.offset_x, self.offset_y) < 0
                or self.offset_x + self.columns * self.cell_w > width
                or self.offset_y + self.rows * self.cell_h > height):
            raise ValueError("font grid extends outside atlas")


def reverse_mapping(mapping):
    if not isinstance(mapping, dict):
        raise ValueError("expected target-to-CP932-proxy mapping")
    result = {}
    available = {glyph for _, entries in cp932_pages().values() for _, glyph in entries if glyph}
    for target, proxy in mapping.items():
        if not isinstance(target, str) or not isinstance(proxy, str) or len(target) != 1 or len(proxy) != 1:
            raise ValueError("glyph mapping must contain single characters")
        encoded = proxy.encode("cp932", "strict")
        if len(encoded) != 2 or encoded.decode("cp932") != proxy or proxy not in available:
            raise ValueError("glyph proxy is absent from this CP932 page profile")
        if proxy in result:
            raise ValueError("ambiguous glyph proxy")
        result[proxy] = target
    return result


def _color(value):
    if not isinstance(value, (list, tuple)) or len(value) != 4 or any(
            type(channel) is not int or not 0 <= channel <= 255 for channel in value):
        raise ValueError("font colors require four byte channels")
    return tuple(value)


def render_page(original_pixels, width, height, page, font_path, grid, *, mapping=None,
                mapped_only=False, style=None, symbol_rules=None):
    """Retain invalid/unselected slots; reject missing or clipped replacement glyphs."""
    Image = imaging()
    try:
        from PIL import ImageDraw, ImageFont, ImageFilter, ImageChops
        from fontTools.ttLib import TTFont
    except ImportError as exc:
        raise RuntimeError("font atlas rendering requires Pillow and fonttools") from exc
    grid.validate(width, height)
    if len(original_pixels) != width * height * 4 or page not in cp932_pages():
        raise ValueError("invalid font atlas pixels/page")
    inverse = reverse_mapping(mapping or {})
    if mapped_only and not inverse:
        raise ValueError("mapped-only rendering requires a nonempty glyph mapping")
    style = dict(style or {})
    if set(style) - {"bold", "outline", "shadow_x", "shadow_y", "fill", "outline_color", "shadow_color"}:
        raise ValueError("unknown font style option")
    bold, outline = style.get("bold", 0), style.get("outline", 0)
    sx, sy = style.get("shadow_x", 0), style.get("shadow_y", 0)
    if any(type(n) is not int or abs(n) > 32 for n in (bold, outline, sx, sy)) or min(bold, outline) < 0:
        raise ValueError("invalid font style extent")
    fill = _color(style.get("fill", (255, 255, 255, 255)))
    stroke = _color(style.get("outline_color", (0, 0, 0, 255)))
    shadow = _color(style.get("shadow_color", (0, 0, 0, 255)))
    font_path = Path(font_path)
    if font_path.stat().st_size > 64 << 20:
        raise ValueError("font file exceeds budget")
    with TTFont(str(font_path), lazy=True, fontNumber=0) as tt:
        supported = set((tt.getBestCmap() or {}).keys())
    font = ImageFont.truetype(str(font_path), grid.font_size, index=0)
    image = Image.frombytes("RGBA", (width, height), original_pixels)
    symbol_rules = dict(symbol_rules or {})
    for source, rule in symbol_rules.items():
        if (not isinstance(source, str) or len(source) != 1 or not isinstance(rule, dict)
                or set(rule) - {"glyph", "dx", "dy", "align"}):
            raise ValueError("invalid symbol rule")
        if any(type(rule.get(key, 0)) is not int or abs(rule.get(key, 0)) > 512 for key in ("dx", "dy")):
            raise ValueError("invalid symbol offset")
    lead, entries = cp932_pages()[page]
    changed = []
    for slot, (trail, source) in enumerate(entries):
        if source is None or mapped_only and source not in inverse:
            continue
        target = inverse.get(source, source)
        rule = symbol_rules.get(target, {})
        glyph = rule.get("glyph", target)
        if not isinstance(glyph, str) or len(glyph) != 1 or ord(glyph) not in supported:
            raise ValueError(f"font lacks requested glyph U+{ord(target):04X} at {lead:02X}{trail:02X}")
        cell = Image.new("RGBA", (grid.cell_w, grid.cell_h))
        left, top, right, bottom = font.getbbox(glyph, anchor="ls")
        ascent, descent = font.getmetrics()
        x = (grid.cell_w - (right - left)) / 2 - left + rule.get("dx", 0)
        y = (grid.cell_h - ascent - descent) / 2 + ascent + rule.get("dy", 0)
        align = rule.get("align", "baseline")
        if align == "center":
            y = grid.cell_h / 2 - (top + bottom) / 2 + rule.get("dy", 0)
        elif align == "bottom":
            y = grid.cell_h - bottom - outline - max(sy, 0) + rule.get("dy", 0)
        elif align == "left":
            x = -left + outline - min(sx, 0) + rule.get("dx", 0)
        elif align != "baseline":
            raise ValueError("unknown symbol alignment")
        if not glyph.isspace() and (x + left - outline + min(sx, 0) < 0
                or x + right + bold + outline + max(sx, 0) > grid.cell_w
                or y + top - outline + min(sy, 0) < 0
                or y + bottom + outline + max(sy, 0) > grid.cell_h):
            raise ValueError(f"glyph U+{ord(glyph):04X} clips its font cell")
        mask = Image.new("L", cell.size)
        draw = ImageDraw.Draw(mask)
        for shift in range(bold + 1):
            draw.text((x + shift, y), glyph, font=font, fill=255, anchor="ls")
        if not glyph.isspace() and mask.getbbox() is None:
            raise ValueError("requested glyph rendered empty")
        outer = mask.filter(ImageFilter.MaxFilter(outline * 2 + 1)) if outline else mask
        layers = []
        if sx or sy:
            shifted = Image.new("L", cell.size)
            shifted.paste(outer, (sx, sy))
            layers.append((shifted, shadow))
        if outline:
            layers.append((ImageChops.subtract(outer, mask), stroke))
        layers.append((mask, fill))
        for alpha, color in layers:
            layer = Image.new("RGBA", cell.size, color)
            layer.putalpha(alpha.point(lambda value: value * color[3] // 255))
            cell.alpha_composite(layer)
        origin = (grid.offset_x + slot % grid.columns * grid.cell_w,
                  grid.offset_y + slot // grid.columns * grid.cell_h)
        image.paste(cell, origin)
        changed.append({"slot": slot, "bytes": f"{lead:02X}{trail:02X}", "source": source,
                        "target": target, "glyph": glyph})
    return image.tobytes(), changed
