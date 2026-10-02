"""Validate gt_output -> ImoScripter patches -> new template-based QLIE PACKs.

Standard library only. No deployment, EXE modifications or translation calls.
"""
import argparse
from dataclasses import asdict
import hashlib
import io
import json
import os
from pathlib import Path

from python.archives.qlie import read_index, read_member, PACK_KEY_NAME
from python.archives.qlie_keys import game_key_from_pe
from python.archives.qlie_writer import rebuild
from python.common.contract import load_json, validate_translation
from python.common.safety import Limits, validate_names, write_new_tree
from python.engines.qlie_imos import REFERENCE, scan, patch
from python.engines.qlie_extract import _small, _ordinary, _json


def repack(game: Path, extracted: Path, output: Path, *, source_roundtrip: bool = False) -> dict:
    """Default reads matching flat gt_output files; missing translations skip.

    source_roundtrip explicitly uses gt_input and submits every .s (including
    empty system scripts) through the archive writer. Archives above 128 MiB
    use the separate streaming rebuild API instead of this bounded recipe.
    """
    game, extracted, output = map(lambda p: Path(os.path.abspath(p)), (game, extracted, output))
    if os.path.lexists(output):
        raise FileExistsError(f'refusing to replace output: {output}')
    report = load_json(_small(extracted / 'reports/extraction.json', 16 << 20))
    if (report.get('schema') != 'qlie-extract/1' or report.get('variant') != REFERENCE
            or report.get('status') != 'complete' or report.get('crypto') != 'keyed'):
        raise ValueError('incompatible/incomplete QLIE extraction report')
    identities = report['sources']
    if len(identities) != 2:
        raise ValueError('QLIE report requires the original EXE and key identities')
    source_names = validate_names([s['path'] for s in identities])
    key_inputs = []
    for name, identity in zip(source_names, identities):
        data = _small(game / name, 64 << 20)
        if len(data) != identity['size'] or hashlib.sha256(data).hexdigest() != identity['sha256']:
            raise ValueError(f'QLIE key/EXE source changed: {name}')
        key_inputs.append(data)
    game_key, external_key = game_key_from_pe(key_inputs[0]), key_inputs[1]
    archive_names = validate_names([a['path'] for a in report['archives']])
    known = set()
    work = {}
    for item in report['members']:
        if item['status'] not in ('exported', 'empty'):
            continue
        original_path = validate_names([item['original']])[0]
        raw = _small(extracted / original_path, 8 << 20)
        if hashlib.sha256(raw).hexdigest() != item['decoded_sha256']:
            raise ValueError('extracted QLIE original changed')
        text = raw.decode('cp932', errors='strict')
        records = scan(text)
        if item['status'] == 'exported':
            json_path, manifest_path = validate_names([item['json'], item['manifest']])
            if not json_path.startswith('gt_input/') or len(Path(json_path).parts) != 2:
                raise ValueError('expected flat QLIE gt_input filename')
            known.add(Path(json_path).name)
            original_rows = load_json(_small(extracted / json_path, 8 << 20))
            if original_rows != [r.row() for r in records]:
                raise ValueError('QLIE original JSON does not match freshly parsed script')
            manifest = load_json(_small(extracted / manifest_path, 16 << 20))
            if (manifest['engine']['id'] != 'qlie' or manifest['engine']['reference'] != REFERENCE
                    or manifest['encoding'] != 'cp932'
                    or [r['locator'] for r in manifest['records']]
                    != json.loads(json.dumps([asdict(r) for r in records]))):
                raise ValueError('QLIE manifest parser identity/locators changed')
            translated_path = extracted / 'gt_output' / Path(json_path).name
            if source_roundtrip:
                translated = original_rows
            elif translated_path.exists():
                translated = load_json(_small(translated_path, 8 << 20))
            else:
                continue
            checked = validate_translation(manifest, {original_path: raw}, original_rows, translated)
            changed = patch(text, checked).encode('cp932', errors='strict')
        elif source_roundtrip:
            if records:
                raise ValueError('QLIE script marked empty contains rows')
            changed = patch(text, []).encode('cp932', errors='strict')
        else:
            continue
        archive = item['archive']
        if archive not in archive_names:
            raise ValueError('QLIE member references an unknown archive')
        name = validate_names([item['name']])[0]
        if name in work.setdefault(archive, {}):
            raise ValueError('duplicate QLIE rebuild member')
        work[archive][name] = (raw, changed)
    if not source_roundtrip:
        actual = {p.name for p in (extracted / 'gt_output').iterdir() if p.suffix.lower() == '.json'}
        if actual - known:
            raise ValueError('unmatched translation filenames: ' + ', '.join(sorted(actual - known)))
    if not work:
        raise ValueError('no matching QLIE translations to pack')
    payloads = []
    result = {'schema': 'qlie-repack/1', 'source_roundtrip': source_roundtrip,
              'encoding': 'cp932', 'game_launch_tested': False, 'archives': []}
    for identity in report['archives']:
        name = identity['path']
        if name not in work:
            continue
        path = game / name
        _ordinary(path)
        if path.stat().st_size > 128 << 20:
            raise ValueError('archive exceeds recipe memory budget; use streaming rebuild API')
        with path.open('rb') as source:
            digest = hashlib.file_digest(source, 'sha256').hexdigest()
            if digest != identity['sha256'] or path.stat().st_size != identity['size']:
                raise ValueError(f'QLIE original archive changed: {name}')
            index = read_index(source)
            key = external_key
            replacements = {}
            for entry in index.entries:
                logical = entry.name.replace('\\', '/')
                if entry.name == PACK_KEY_NAME:
                    key = read_member(source, index, entry, mode='keyed', key_file=key, game_key=game_key)
                elif logical in work[name]:
                    original, changed = work[name][logical]
                    current = read_member(source, index, entry, mode='keyed', key_file=key, game_key=game_key)
                    if current != original:
                        raise ValueError('QLIE extracted original differs from archive member')
                    replacements[entry.name] = changed
            if len(replacements) != len(work[name]):
                raise ValueError('QLIE rebuild member not found in original index')
            destination = io.BytesIO()
            stats = rebuild(source, destination, replacements, mode='keyed', key_file=external_key, game_key=game_key)
            data = destination.getvalue()
            digest_out = hashlib.sha256(data).hexdigest()
            if source_roundtrip and digest_out != digest:
                raise ValueError('QLIE full archive original roundtrip changed bytes')
            result['archives'].append({'path': name, 'source_sha256': digest, 'sha256': digest_out, **stats})
            payloads.append((name, data))
    payloads.append(('reports/repack.json', _json(result)))
    write_new_tree(output, payloads, Limits(max_file_bytes=192 << 20, max_total_bytes=256 << 20))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('game', type=Path)
    parser.add_argument('extracted', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--source-roundtrip', action='store_true')
    args = parser.parse_args()
    result = repack(args.game, args.extracted, args.output, source_roundtrip=args.source_roundtrip)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
