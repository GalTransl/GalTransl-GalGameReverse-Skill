"""Explicit QLIE 3.0 + keyed ImoScripter FormatType=1 extraction recipe.

Run from skill root with python -m python.engines.qlie_extract --help.
Reads only explicitly named inputs. Writes one new tree via common.safety.
Archives with duplicate script names remain separate; no load-order guessing.
"""
import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat

from python.archives.qlie import PACK_KEY_NAME, read_index, read_member
from python.archives.qlie_keys import game_key_from_pe
from python.common.contract import dump_rows, make_manifest, validate_translation
from python.common.safety import Limits, validate_names, write_new_tree
from python.engines.qlie_imos import REFERENCE, scan, patch


def _json(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _ordinary(path):
    for parent in (path, *path.parents):
        info = parent.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError(f'linked/reparse input: {parent}')
    if not path.is_file():
        raise ValueError(f'not an ordinary input file: {path}')


def _small(path, limit):
    _ordinary(path)
    with path.open('rb') as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f'input exceeds size budget: {path}')
    return data


def extract(game: Path, output: Path, *, archives: list[str], exe: str,
            key_file: str = 'DLL/key.fkey', max_total: int = 64 << 20) -> dict:
    """Keep every archive version, validate scripts and perform byte roundtrips.

    The full archive SHA-256 is streamed; only .s/.txt payloads plus the internal
    key are decrypted. The entire batch is bounded before publishing output.
    """
    game, output = Path(os.path.abspath(game)), Path(os.path.abspath(output))
    if os.path.lexists(output):
        raise FileExistsError(f'refusing to replace output: {output}')
    paths = validate_names([*archives, exe, key_file])
    archives, exe, key_file = paths[:-2], paths[-2], paths[-1]
    exe_data = _small(game / exe, 64 << 20)
    external_key = _small(game / key_file, 1 << 20)
    game_key = game_key_from_pe(exe_data)
    report = {'schema': 'qlie-extract/1', 'engine': 'qlie', 'variant': REFERENCE,
              'archive_version': 'FilePackVer3.0', 'crypto': 'keyed',
              'sources': [], 'archives': [], 'members': [], 'counts': {},
              'duplicate_policy': 'retain-every-version; archive-load-priority-unverified',
              'scope': 'Japanese PACK scripts; external localization overlays are not parsed',
              'game_launch_tested': False, 'pack_writer': 'template-pack3.0-hash1.3'}
    for name, data in ((exe, exe_data), (key_file, external_key)):
        report['sources'].append({'path': name, 'size': len(data), 'sha256': _digest(data)})
    report['game_key_sha256'] = _digest(game_key)
    payloads, scripts, total, configuration = [], [], 0, {}
    for archive_number, name in enumerate(archives):
        path = game / name
        _ordinary(path)
        with path.open('rb') as stream:
            index = read_index(stream)
            names = validate_names([e.name for e in index.entries])
            key = external_key
            if index.entries[0].name != PACK_KEY_NAME or sum(e.name == PACK_KEY_NAME for e in index.entries) != 1:
                raise ValueError('keyed recipe requires one internal key as the first entry')
            selected = 0
            for ordinal, (entry, logical) in enumerate(zip(index.entries, names)):
                if ordinal == 0:
                    key = read_member(stream, index, entry, mode='keyed', key_file=key, game_key=game_key,
                                      max_stored=1 << 20, max_output=1 << 20)
                    continue
                if PurePosixPath(logical).suffix.lower() not in ('.s', '.txt'):
                    continue
                if total + entry.unpacked_size > max_total:
                    raise ValueError('QLIE total decoded budget exceeded')
                raw = read_member(stream, index, entry, mode='keyed', key_file=key, game_key=game_key,
                                  max_stored=8 << 20, max_output=8 << 20)
                total += len(raw)
                text = raw.decode('cp932', errors='strict')
                if text.encode('cp932', errors='strict') != raw:
                    raise ValueError('CP932 cannot preserve original bytes')
                original = f'original/a{archive_number:02d}/{logical}'
                payloads.append((original, raw))
                item = {'archive': name, 'archive_number': archive_number, 'ordinal': ordinal,
                        'name': logical, 'offset': entry.offset, 'stored_size': entry.size,
                        'decoded_size': len(raw), 'stored_checksum': entry.checksum,
                        'decoded_sha256': _digest(raw), 'original': original}
                report['members'].append(item)
                selected += 1
                if logical.lower() in ('avg/projectsetting.txt', 'avg/setting.txt'):
                    configuration.setdefault(logical.lower(), []).append(text)
                if logical.lower().endswith('.s'):
                    scripts.append((item, raw, text))
                else:
                    item['status'] = 'supporting-text'
            stream.seek(0)
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            report['archives'].append({'path': name, 'size': index.file_size, 'sha256': digest,
                                       'entries': len(index.entries), 'selected': selected,
                                       'index_offset': index.index_offset, 'index_end': index.index_end,
                                       'arc_key': index.arc_key})
    for filename, setting in (('avg/projectsetting.txt', 'FormatType=1'), ('avg/setting.txt', 'ReturnCode=[n]')):
        if filename not in configuration or not all(setting in [l.strip() for l in text.splitlines()]
                                                    for text in configuration[filename]):
            raise ValueError(f'required ImoScripter profile evidence missing: {filename}: {setting}')
    planned = []
    counts = Counter()
    for item, raw, text in scripts:
        try:
            records = scan(text)
            rows = [record.row() for record in records]
            rebuilt = patch(text, rows).encode('cp932', errors='strict')
            if rebuilt != raw:
                raise ValueError('original text roundtrip is not byte-identical')
            item['original_roundtrip'] = 'byte-identical'
            item['rows'] = len(rows)
            if not rows:
                item['status'] = 'empty'
                counts['empty_scripts'] += 1
                continue
            planned.append((item, raw, records, rows))
        except ValueError as exc:
            item['status'], item['error'] = 'failed', str(exc)
            counts['failed_scripts'] += 1
    stems = Counter(PurePosixPath(item['name']).stem.casefold() for item, *_ in planned)
    for item, raw, records, rows in planned:
        stem = PurePosixPath(item['name']).stem
        if stems[stem.casefold()] > 1:
            stem += f"__a{item['archive_number']:02d}_m{item['ordinal']:05d}"
        json_path = f'gt_input/{stem}.json'
        manifest_path = f'metadata/{stem}.json'
        policies = [('context' if record.speaker.raw.startswith('$') else 'writable')
                    if record.speaker else 'absent' for record in records]
        manifest = make_manifest(engine='qlie', variant='imos-format1-cp932-keyed-pack3.0', reference=REFERENCE,
                                 sources={item['original']: raw}, rows=rows, encoding='cp932',
                                 locators=[asdict(record) for record in records], name_policies=policies,
                                 settings={'archive': item['archive'], 'member': item['name'],
                                           'physical_multiline': 'preserve-line-count',
                                           'name_write': 'preserve-identity-and-write-display-alias',
                                           'container_writer': 'template-pack3.0-hash1.3'})
        validate_translation(manifest, {item['original']: raw}, rows, rows)
        payloads.extend(((json_path, dump_rows(rows)), (manifest_path, _json(manifest))))
        item.update(status='exported', json=json_path, manifest=manifest_path)
        counts['exported_scripts'] += 1
        counts['rows'] += len(rows)
        counts['named_rows'] += sum('name' in row for row in rows)
        counts['choice_rows'] += sum(r.parts[0].kind == 'choice' for r in records)
        counts['pc_rows'] += sum(any(p.kind == 'pc' for p in r.parts) for r in records)
    counts['scripts'] = len(scripts)
    counts['decoded_bytes'] = total
    report['counts'] = dict(counts)
    report['status'] = 'partial' if counts['failed_scripts'] else 'complete'
    payloads.append(('reports/extraction.json', _json(report)))
    write_new_tree(output, payloads, Limits(max_file_bytes=16 << 20, max_total_bytes=256 << 20))
    (output / 'gt_output').mkdir()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('game', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--exe', required=True, help='explicit game-relative PE path; read as data only')
    parser.add_argument('--key-file', default='DLL/key.fkey')
    parser.add_argument('--archives', nargs='+', required=True, help='explicit game-relative PACK paths')
    args = parser.parse_args()
    result = extract(args.game, args.output, archives=args.archives, exe=args.exe, key_file=args.key_file)
    print(json.dumps({'status': result['status'], 'counts': result['counts'], 'output': str(args.output)},
                     ensure_ascii=False, indent=2))
    raise SystemExit(result['status'] != 'complete')


if __name__ == '__main__':
    main()
