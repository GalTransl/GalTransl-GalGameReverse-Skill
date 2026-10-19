"""Collect bounded Hx name candidates from one archive for other archives.

Scans small PSB/TJS/text members, applies the staging rules from
engines/kirikiri/hxv4.md, and writes candidates.txt plus a verification report.
It never builds or modifies an archive; names remain candidates until the
target archive's name hashes confirm them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from python.archives.kirikiri_hxv4 import _inflate, derive, read_index
from python.archives.kirikiri_hxv4_names import inspect, resolve
from python.archives.kirikiri_hxv4_payload import Cipher, read_member
from python.common.safety import Limits, write_new_tree
from python.engines.kirikiri_hxv4_recover import script_names
from python.engines.kirikiri_tjs_decompile import strings as tjs_strings
from python.engines.kirikiri_psb import Psb
from python.engines import kirikiri_hxv4_tables as tables

MAX_NAMES = 500000
DEFAULT_PATHS = (
    '', 'data/', 'system/', 'scenario/', 'scn/', 'image/', 'evimage/', 'fgimage/',
    'bgimage/', 'thum/', 'sound/', 'bgm/', 'voice/', 'video/', 'font/', 'plugin/',
    'k2compat/', 'main/', 'scenario/scripts/', 'uipsd/',
)


def collect(archive, exe, *, domain='xp3hnp', paths=None,
            max_member_bytes=8 << 20, max_total_bytes=384 << 20):
    archive, exe = Path(archive), Path(exe)
    paths = tuple(paths) if paths else DEFAULT_PATHS
    if max_member_bytes <= 0 or max_total_bytes <= 0:
        raise ValueError('candidate scan budget must be positive')
    report = inspect(archive, exe, set(), paths, domain)
    keys = derive(report['key_package'])
    cipher = Cipher(keys)
    names = set()
    sources = {'tjs': 0, 'psb': 0, 'text': 0, 'ogg': 0}
    errors = []
    scanned = 0
    total = 0
    oversize = 0
    unmapped = 0
    complete = True
    with archive.open('rb') as stream:
        index = read_index(stream, keys)
        if len(index['files']) > 100000:
            raise ValueError('Hx entry budget')
        for entry in sorted(index['files'], key=lambda item: item['size']):
            if 'key' not in entry or 'name_hash' not in entry:
                unmapped += 1
                continue
            if entry['size'] > max_member_bytes:
                oversize += 1
                continue
            if total + entry['size'] > max_total_bytes:
                complete = False
                break
            data = read_member(stream, entry, cipher)
            total += entry['size']
            scanned += 1
            try:
                if data[:8] == b'TJS2100\0':
                    hints = script_names(data)
                    hints |= tables.token_candidates(
                        value['text'] for value in tjs_strings(data))
                    sources['tjs'] += 1
                elif data[:4] == b'PSB\0':
                    hints = script_names(data)
                    hints |= tables.token_candidates(Psb(data).strings)
                    sources['psb'] += 1
                elif data[:4] == b'OggS':
                    hints = tables.ogg_title_candidates(data)
                    if hints:
                        sources['ogg'] += 1
                elif data[:4] == b'mdf\0':
                    hints = script_names(data)
                    try:
                        payload = _inflate(data[8:], int.from_bytes(data[4:8], 'little'), 32 << 20)
                        if payload[:4] == b'PSB\0':
                            hints |= tables.token_candidates(Psb(payload).strings)
                    except ValueError:
                        pass
                    sources['psb'] += 1
                else:
                    hints = tables.candidate_names(data)
                    if hints:
                        sources['text'] += 1
            except (ValueError, UnicodeError) as error:
                errors.append({'alias': entry.get('alias', ''), 'error': str(error)})
                hints = set()
            names.update(hints)
            if len(names) > MAX_NAMES:
                raise ValueError('Hx candidate budget')
    names |= tables.series_candidates(names)
    return {
        'report': report,
        'index': index,
        'names': names,
        'sources': sources,
        'errors': errors,
        'scanned_members': scanned,
        'bytes_read': total,
        'skipped_oversize_members': oversize,
        'skipped_unmapped_members': unmapped,
        'scan_complete': complete,
        'paths': tuple(paths),
        'domain': domain,
    }


def write_candidates(result, output):
    report = result['report']
    index = result['index']
    resolved = resolve(index['files'], result['names'], result['paths'], result['domain'])
    matched = [entry for entry in resolved if 'name' in entry or 'path' in entry]
    report.update({
        'schema': 'kirikiri-hxv4-candidate-scan/1',
        'candidate_count': len(result['names']),
        'candidate_paths': list(result['paths']),
        'candidate_sources': result['sources'],
        'candidate_errors': result['errors'],
        'scanned_members': result['scanned_members'],
        'bytes_read': result['bytes_read'],
        'skipped_oversize_members': result['skipped_oversize_members'],
        'skipped_unmapped_members': result['skipped_unmapped_members'],
        'scan_complete': result['scan_complete'],
        'names_resolved': sum('name' in entry for entry in resolved),
        'paths_resolved': sum('path' in entry for entry in resolved),
        'entries': matched,
    })
    report['candidate_sha256'] = hashlib.sha256(
        '\n'.join(sorted(result['names'])).encode('utf-8')).hexdigest()
    payloads = [
        ('candidates.txt', ('\n'.join(sorted(result['names'])) + '\n').encode('utf-8')),
        ('report.json', (json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode('utf-8')),
    ]
    write_new_tree(Path(output), payloads, Limits(max_file_bytes=32 << 20, max_total_bytes=64 << 20))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--domain', default='xp3hnp',
                        help='hash domain/media name from STARTUP.TJS; empty string if absent')
    parser.add_argument('--paths', nargs='*', default=None,
                        help='directory candidates; defaults to common Kirikiri directories')
    parser.add_argument('--max-member-bytes', type=int, default=8 << 20)
    parser.add_argument('--max-total-bytes', type=int, default=384 << 20)
    args = parser.parse_args()
    result = collect(args.archive, args.exe, domain=args.domain, paths=args.paths,
                     max_member_bytes=args.max_member_bytes,
                     max_total_bytes=args.max_total_bytes)
    report = write_candidates(result, args.output)
    print(json.dumps({key: report[key] for key in (
        'index_entries', 'candidate_count', 'names_resolved', 'paths_resolved',
        'scanned_members', 'bytes_read', 'scan_complete')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
