# SPDX-License-Identifier: GPL-3.0-only
"""Bishop ``GSC`` script container: fixed header, six sections, NUL strings.

Header, little-endian int32::

    0x00  opaque word, not interpreted
    0x04  opaque word, not interpreted
    0x08  section 1 byte length
    0x0C  section 2 byte length
    0x10  string section byte length (0 means the layout is unsupported)
    0x14  section 3 byte length
    0x18  section 4 element count; its byte length is twice this value
    0x1C  section 5 byte length
    0x20  section 6 byte length

Sections follow in that order; the string section starts after sections 1 and
2. Strings are NUL-terminated byte runs. Each extracted entry keeps its
absolute offset and original byte length, so a translation is written into the
same span and padded with 0x20 when it is shorter.

Provenance: ``GameRes.LiosGame.ArcGSC`` from the third-party tool
"翻译肋手 v4.9D". Independent rewrite with explicit bounds: the reference
silently truncates oversized translations and ignores an unterminated trailing
string; this module rejects both. ``parseStringByStruct`` is not ported because
the reference exporter only uses the compact NUL walk.
"""
from dataclasses import dataclass
import struct

HEADER_SIZE = 36
FIELD_COUNT = 9
MAX_SECTION = 64 << 20


@dataclass(frozen=True)
class GscHeader:
    unknown: tuple
    section_sizes: tuple
    string_size: int


@dataclass(frozen=True)
class GscString:
    position: int
    maxlength: int
    text: str


@dataclass(frozen=True)
class GscScript:
    header: GscHeader
    string_offset: int
    strings: tuple


def open_gsc(data, encoding="cp932"):
    """Read the header and split the string section into NUL-terminated runs."""
    if not isinstance(data, bytes) or len(data) < HEADER_SIZE:
        raise ValueError("GSC file is smaller than its header")
    fields = struct.unpack_from("<9i", data, 0)
    unknown = fields[0:2]
    section1, section2, string_size, section3, section4_count, section5, section6 = fields[2:9]
    if string_size == 0:
        raise ValueError("GSC string section is empty; layout is unsupported")
    section4 = section4_count * 2
    lengths = (section1, section2, string_size, section3, section4, section5, section6)
    if any(value < 0 for value in lengths):
        raise ValueError("GSC section length is negative")
    if any(value > MAX_SECTION for value in lengths):
        raise ValueError("GSC section length exceeds the limit")
    string_offset = HEADER_SIZE + section1 + section2
    header = GscHeader(unknown, (section1, section2, section3, section4, section5, section6),
                       string_size)
    if string_size == 1:
        if string_offset + 1 > len(data):
            raise ValueError("GSC string section exceeds the file")
        return GscScript(header, string_offset, ())
    string_end = string_offset + string_size
    end = string_end + section3 + section4 + section5 + section6
    if end > len(data):
        raise ValueError("GSC section lengths exceed the file")
    return GscScript(header, string_offset, _split_strings(data, string_offset,
                                                           string_end, encoding))


def _split_strings(data, start, end, encoding):
    strings = []
    cursor = start
    for position in range(start, end):
        if data[position] != 0:
            continue
        if position > cursor:
            raw = data[cursor:position]
            try:
                text = raw.decode(encoding, "strict")
            except (UnicodeDecodeError, LookupError) as exc:
                raise ValueError("GSC string is not valid in the declared encoding") from exc
            strings.append(GscString(cursor, len(raw), text))
        cursor = position + 1
    if cursor != end:
        raise ValueError("GSC trailing string is not NUL terminated")
    return tuple(strings)


def apply_gsc_texts(data, script, texts, encoding="gbk"):
    """Write ``texts`` into a copy of ``data``; shorter text is space padded.

    A translation whose encoded length exceeds the original byte span is
    rejected instead of being truncated in the middle of a character.
    """
    if not isinstance(data, bytes) or not isinstance(script, GscScript):
        raise ValueError("invalid GSC input")
    texts = tuple(texts)
    if len(texts) != len(script.strings):
        raise ValueError("GSC translation count does not match the entry count")
    out = bytearray(data)
    for entry, text in zip(script.strings, texts):
        if not isinstance(text, str) or not text:
            raise ValueError("GSC translation must be a non-empty string")
        try:
            raw = text.encode(encoding, "strict")
        except (UnicodeEncodeError, LookupError) as exc:
            raise ValueError("GSC translation does not encode in the target encoding") from exc
        if b"\0" in raw:
            raise ValueError("GSC translation contains a NUL byte")
        if len(raw) > entry.maxlength:
            raise ValueError(
                f"GSC translation at 0x{entry.position:x} needs {len(raw)} bytes, "
                f"span is {entry.maxlength}")
        out[entry.position:entry.position + entry.maxlength] = (
            raw + b"\x20" * (entry.maxlength - len(raw)))
    return bytes(out)
