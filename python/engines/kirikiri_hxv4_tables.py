"""Bounded candidate extraction from Hx text tables and script text.

Covers the staging rules documented in engines/kirikiri/hxv4.md: SimpleCrypt
unwrapping, scene-list and image-diff-map parsing, generic table tokens, and
extension/path variants.  Names are candidates only; the caller must verify
them with the Hx name hashes.
"""
from __future__ import annotations

import re
from python.engines.kirikiri_simple_crypt import detect, unpack
from python.common.safety import validate_names

MAX_TEXT = 4 << 20
MAX_TOKENS = 300000
BOM_LE = b'\xff\xfe'
BOM_BE = b'\xfe\xff'

# Ordered from runtime resource paths to table/archive formats.
FILE_EXTENSIONS = (
    '.tjs', '.ks', '.scn', '.txt', '.csv', '.tsv', '.ini', '.json', '.func',
    '.pimg', '.pbd', '.psb', '.sli', '.opus.sli', '.png', '.tlg', '.tlg5',
    '.tlg6', '.jpg', '.jpeg', '.bmp', '.webp', '.psd', '.stand', '.sinfo',
    '.event', '.ogg', '.opus', '.wav', '.tcw', '.webm', '.mp4', '.wmv',
    '.avi', '.amv', '.dref', '.dpak',
)
TABLE_EXTENSIONS = (
    '.scn', '.txt', '.ks', '.csv', '.ini', '.png', '.tlg', '.dref', '.dpak',
    '.ogg', '.opus', '.webm', '.psd', '.stand', '.sinfo', '.pimg', '.psb',
    '.stage', '.wav', '.jpg', '.webp',
)
IMAGE_EXTENSIONS = (
    '.dref', '.dpak', '.tlg', '.tlg5', '.tlg6', '.png', '.webp', '.jpg',
    '.jpeg', '.bmp', '.psd',
)
_SPLIT = re.compile(r'[,\t|=:]')
_QUOTED = re.compile(r'''["']([^"'\r\n]{1,180})["']''')
_FILE_TOKEN = re.compile(r'''[A-Za-z0-9_./\\-]{2,180}\.[A-Za-z0-9]{1,8}''')
_PSB_REF = re.compile(r'''psb://([^\s/]+)/([^\s]+)''', re.IGNORECASE)


def decode_text(data: bytes):
    """Return bounded text after SimpleCrypt/BOM decoding, else None."""
    if not isinstance(data, (bytes, bytearray, memoryview)):
        return None
    data = bytes(data)
    if data.startswith((b'PSB\0', b'TJS2100\0', b'mdf\0', b'\x89PNG', b'TLG')):
        return None
    if len(data) > MAX_TEXT * 2:
        return None
    mode = detect(data)
    if mode is not None:
        try:
            data = unpack(data)[0]
        except ValueError:
            return None
    if len(data) > MAX_TEXT:
        return None
    if data.startswith(BOM_LE):
        text = data.decode('utf-16-le', errors='replace')
    elif data.startswith(BOM_BE):
        text = data.decode('utf-16-be', errors='replace')
    else:
        for encoding in ('utf-8-sig', 'cp932'):
            try:
                text = data.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            return None
    if '\x00' in text:
        return None
    return text.lstrip('\ufeff')


def clean_token(token: str):
    if not isinstance(token, str):
        return None
    token = token.strip().strip('"\'`').strip()
    token = re.sub(r'^\d+:', '', token)
    token = token.replace('\\', '/').lstrip('@')
    if '|' in token:
        token = token.split('|', 1)[0]
    token = token.split('#', 1)[0].split('@', 1)[0]
    token = token.strip().strip(',;:[](){}').strip()
    if not token or len(token) > 180:
        return None
    if token.startswith(('#', '@', '&', '*', '%', '$')):
        return None
    if any(ch in token for ch in '?<>'):
        return None
    if any(ch.isspace() or ord(ch) < 0x20 for ch in token):
        return None
    if token.replace('.', '', 1).isdigit():
        return None
    token = token.lstrip('./').lstrip('/')
    if not token:
        return None
    try:
        validate_names([token])
    except ValueError:
        return None
    return token


def looks_like_stem(value: str) -> bool:
    leaf = value.rsplit('/', 1)[-1]
    if not 2 <= len(leaf) <= 80:
        return False
    return any(ch.isdigit() or ch in '_-' for ch in leaf)


def _add(out: set, name: str, seen: set):
    if not name or len(out) >= MAX_TOKENS:
        return
    key = name.lower()
    if key in seen:
        return
    seen.add(key)
    out.add(name)


def name_variants(value: str, extensions=TABLE_EXTENSIONS, expand=True):
    """Return the token plus realistic extension/SCN variants."""
    out = set()
    seen = set()
    token = clean_token(value)
    if token is None:
        return out
    _add(out, token, seen)
    lower = token.lower()
    if lower.endswith('.scn'):
        return out
    if lower.endswith(('.ks', '.txt')):
        for suffix in ('.scn',):
            _add(out, token + suffix, seen)
        stem = token.rsplit('.', 1)[0]
        _add(out, stem + '.scn', seen)
        if lower.endswith('.txt'):
            _add(out, stem + '.ks.scn', seen)
        return out
    if '.' in token.rsplit('/', 1)[-1]:
        return out
    if not expand or not looks_like_stem(token):
        return out
    for extension in extensions:
        _add(out, token + extension, seen)
    return out


def _lines(text: str):
    return text.splitlines()[:20000]


def scene_candidates(text: str):
    """Parse tab-separated !scnlist.txt rows into .scn candidates."""
    out = set()
    seen = set()
    for line in _lines(text):
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        for field in line.split('\t'):
            field = field.strip()
            if not field or field == '-' or 'dummy' in field.lower():
                continue
            field = field.split('*', 1)[0].strip().rstrip(':').strip()
            if '.' not in field:
                continue
            for name in name_variants(field, ('.scn',), expand=False):
                if name.lower().endswith('.scn'):
                    _add(out, name, seen)
    return out


def diff_map_candidates(text: str):
    """Parse image-name -> actual-name rows from imagediffmap files."""
    out = set()
    seen = set()
    for line in _lines(text):
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        fields = [field.strip() for field in line.split('\t') if field.strip()]
        if len(fields) < 2:
            fields = [field.strip() for field in line.split(',') if field.strip()]
        if len(fields) < 2:
            continue
        logical, actual = fields[0], fields[1]
        for token in (actual, logical):
            if '.' in token.rsplit('/', 1)[-1]:
                for name in name_variants(token, TABLE_EXTENSIONS, expand=False):
                    _add(out, name, seen)
            else:
                for name in name_variants(token, IMAGE_EXTENSIONS, expand=True):
                    _add(out, name, seen)
    return out


def table_tokens(text: str):
    """Extract file-like fields from CSV/INI/text tables."""
    out = set()
    seen = set()
    for line in _lines(text):
        if line.lstrip().startswith('#'):
            continue
        for field in _SPLIT.split(line):
            token = clean_token(field)
            if token is None:
                continue
            if '.' not in token.rsplit('/', 1)[-1] and not looks_like_stem(token):
                continue
            for name in name_variants(token, TABLE_EXTENSIONS, expand=True):
                _add(out, name, seen)
    return out


def psb_ref_candidates(text: str):
    """Path components from psb:// package/file references."""
    out = set()
    seen = set()
    for match in _PSB_REF.finditer(text):
        for token in match.groups():
            for name in name_variants(token, FILE_EXTENSIONS, expand=False):
                _add(out, name, seen)
    return out


def text_candidates(text: str):
    """Quoted strings and file-like tokens from ordinary script text."""
    out = set()
    seen = set()
    sample = text[:1 << 20]
    for match in _QUOTED.finditer(sample):
        token = clean_token(match.group(1))
        if token is None or ('.' not in token and not looks_like_stem(token)):
            continue
        for name in name_variants(token, FILE_EXTENSIONS, expand=False):
            _add(out, name, seen)
    for match in _FILE_TOKEN.finditer(sample):
        for name in name_variants(match.group(0), FILE_EXTENSIONS, expand=False):
            _add(out, name, seen)
    return out


def token_candidates(values, max_tokens=300000):
    """Short literal tokens from scripts, expanded with runtime extensions.

    Covers English UI names and short Japanese effect labels; long dialogue
    lines are ignored before any extension expansion.  ASCII tokens are
    processed first so a cap does not hide short asset identifiers.
    """
    tokens = []
    for value in values:
        token = value.strip().strip('"\'`').strip()
        if not token or len(token) > 60 or not token.isprintable():
            continue
        if any(ch in token for ch in '\r\n\t?<>:"|*'):
            continue
        if '/' in token or '\\' in token:
            token = token.replace('\\', '/').rsplit('/', 1)[-1]
        if token:
            tokens.append(token)
    out = set()
    seen = set()

    def add(candidate):
        try:
            validate_names([candidate])
        except ValueError:
            return
        _add(out, candidate, seen)

    def stripped_variants(token):
        values = [token]
        for prefix in ('cg_', 'ev_', 'ev', 'thum_', 'image_', 'img_', 'bg_'):
            if token.startswith(prefix) and len(token) > len(prefix):
                remainder = token[len(prefix):]
                values.append(remainder)
                if prefix == 'cg_' and remainder.startswith('ev'):
                    values.append(remainder[2:])
        return values

    for token in tokens:
        if len(out) >= max_tokens:
            break
        if not re.fullmatch(r'[A-Za-z0-9_.\-@]+', token):
            continue
        for value in stripped_variants(token):
            add(value)
            for extension in ('.png', '.webp', '.jpg', '.tlg', '.ogg', '.opus', '.wav'):
                add(value + extension)
            stem = value.rsplit('.', 1)[0]
            if stem != value:
                for extension in ('.png', '.webp', '.jpg', '.tlg', '.ogg', '.opus', '.wav'):
                    add(stem + extension)
    for token in tokens:
        if len(out) >= max_tokens:
            break
        if re.fullmatch(r'[A-Za-z0-9_.\-@]+', token):
            continue
        if len(token) > 24 or any(ch.isspace() for ch in token):
            continue
        add(token)
        for extension in ('.png', '.webp', '.jpg'):
            add(token + extension)
    return out


def ogg_title_candidates(data: bytes):
    """TITLE comments from Ogg Vorbis data, expanded as audio names."""
    if data[:4] != b'OggS':
        return set()
    at = data.find(b'\x03vorbis')
    if at < 0:
        return set()
    at += 7
    try:
        vendor_length = int.from_bytes(data[at:at + 4], 'little')
        at += 4 + vendor_length
        count = int.from_bytes(data[at:at + 4], 'little')
        at += 4
    except (IndexError, ValueError):
        return set()
    titles = set()
    for _ in range(min(count, 32)):
        if at + 4 > len(data):
            break
        length = int.from_bytes(data[at:at + 4], 'little')
        at += 4
        value = data[at:at + length].decode('utf-8', errors='replace')
        at += length
        if '=' in value:
            key, title = value.split('=', 1)
            if key.lower() == 'title' and title.strip():
                titles.add(title.strip())
    out = set()
    seen = set()
    for title in titles:
        for name in (title, title + '.ogg', title + '.opus', title + '.wav'):
            try:
                validate_names([name])
            except ValueError:
                continue
            _add(out, name, seen)
    return out


def series_candidates(names, extra=64, max_candidates=200000):
    """Extend observed numeric series (asset_01, asset_02, ...) with neighbours."""
    groups = {}
    for name in names:
        match = re.match(r'^(.*?)(\d{2,3})(\.[A-Za-z0-9]+)$', name)
        if not match:
            continue
        prefix, digits, extension = match.groups()
        if not prefix:
            continue
        groups.setdefault((prefix, len(digits), extension), set()).add(int(digits))
    out = set()
    # Series with more observed members are more likely to be real asset families.
    for (prefix, width, extension), values in sorted(groups.items(), key=lambda item: -len(item[1])):
        if len(values) < 2:
            continue
        upper = min(999, max(values) + extra)
        for number in range(1, upper + 1):
            out.add(f'{prefix}{number:0{width}d}{extension}')
            if len(out) >= max_candidates:
                return out
    return out


def candidate_names(data: bytes):
    """Collect text/table candidates; PSB/TJS are handled by script_names."""
    text = decode_text(data)
    if text is None:
        return set()
    names = set()
    names |= scene_candidates(text)
    names |= diff_map_candidates(text)
    names |= psb_ref_candidates(text)
    names |= table_tokens(text)
    names |= text_candidates(text)
    return names
