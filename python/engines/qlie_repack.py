"""Validate gt_output -> ImoScripter patches -> new template-based QLIE PACKs.

Supports FilePackVer3.0 (HashVer1.3) and 3.1 (HashVer1.4) with the per-archive
key mode recorded at extraction. Standard library only. No deployment, EXE
modifications or translation calls.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sys
import tempfile

from python.archives.qlie import external_key_required, member_keys, read_index, read_member
from python.archives.qlie_writer import rebuild
from python.common.contract import load_json, validate_translation
from python.common.safety import Limits, validate_names, write_new_tree, validate_new_tree_destination
from python.engines.qlie_imos import COMPATIBLE_REFERENCES, scan, patch
from python.engines.qlie_extract import (SCHEMA, KeyMaterial, _small, _ordinary, _json,
                                         decode_script, encode_script)

# /2 workspaces (one JSON per member) remain packable; their scripts parse
# identically under the current parser, which the locator check confirms.
SCHEMAS = ('qlie-extract/1', 'qlie-extract/2', SCHEMA)


def _failed_names(report: dict) -> dict[str, str]:
    """Flat JSON names a failed script would have had -> archive, member and reason."""
    failed = {}
    for item in report['members']:
        if item.get('status') == 'failed' and item['name'].lower().endswith('.s'):
            stem = PurePosixPath(item['name']).stem
            where = f"{item['archive']}:{item['name']}: {item.get('error', 'failed')}"
            for name in (f'{stem}.json', f"{stem}__a{item['archive_number']:02d}_m{item['ordinal']:05d}.json"):
                failed.setdefault(name.casefold(), where)
    return failed


def repack(game: Path, extracted: Path, output: Path, *, source_roundtrip: bool = False) -> dict:
    """Default reads matching flat gt_output files; missing translations skip.

    source_roundtrip explicitly uses gt_input and submits every parsed .s
    (including empty system scripts) through the archive writer. Scripts that
    failed at extraction are never submitted: the writer copies their original
    encrypted bytes, and a translation supplied for one is refused. A JSON
    shared by identical copies is written into every copy. Archives above
    128 MiB use the separate streaming rebuild API instead of this recipe.
    """
    game, extracted, output = map(lambda p: Path(os.path.abspath(p)), (game, extracted, output))
    validate_new_tree_destination(output)
    report = load_json(_small(extracted / 'reports/extraction.json', 16 << 20))
    if report.get('schema') not in SCHEMAS or report.get('variant') not in COMPATIBLE_REFERENCES:
        raise ValueError('incompatible QLIE extraction report; re-extract from the original game into a new directory')
    if report.get('status') not in ('complete', 'partial'):
        raise ValueError(f"QLIE extraction status is {report.get('status')!r}; nothing exported can be packed")
    identities = report['sources']
    if report['schema'] == 'qlie-extract/1':
        # Legacy workspaces: 3.0 keyed, sources = [EXE, key file], CP932 scripts.
        if report.get('crypto') != 'keyed' or len(identities) != 2:
            raise ValueError('QLIE report requires the original EXE and key identities')
        identities = [dict(identities[0], role='exe'), dict(identities[1], role='key-file')]
        for archive in report['archives']:
            archive.setdefault('version', '3.0')
            archive.setdefault('mode', 'keyed')
    by_role = {}
    for identity in identities:
        if identity['role'] in ('exe', 'key-file'):
            by_role[identity['role']] = validate_names([identity['path']])[0]
    keys = KeyMaterial(game, by_role.get('exe'), by_role.get('key-file'))
    archive_names = validate_names([a['path'] for a in report['archives']])
    known, documents, work, translated_members = set(), {}, {}, []
    available = set()
    if not source_roundtrip:
        available = {p.name for p in (extracted / 'gt_output').iterdir() if p.suffix.lower() == '.json'}
    for item in report['members']:
        if item.get('status') not in ('exported', 'empty'):
            continue
        original_path = validate_names([item['original']])[0]
        raw = _small(extracted / original_path, 8 << 20)
        if hashlib.sha256(raw).hexdigest() != item['decoded_sha256']:
            raise ValueError(f'extracted QLIE original changed: {original_path}')
        text, encoding, bom = decode_script(raw)
        if (encoding, bom) != (item.get('encoding', 'cp932'), item.get('bom', False)):
            raise ValueError('QLIE script encoding differs from extraction report')
        records = scan(text)
        if item['status'] == 'exported':
            json_path, manifest_path = validate_names([item['json'], item['manifest']])
            if not json_path.startswith('gt_input/') or len(Path(json_path).parts) != 2:
                raise ValueError('expected flat QLIE gt_input filename')
            filename = Path(json_path).name
            known.add(filename)
            if json_path not in documents:
                original_rows = load_json(_small(extracted / json_path, 8 << 20))
                manifest = load_json(_small(extracted / manifest_path, 16 << 20))
                if (manifest['engine']['id'] != 'qlie' or manifest['engine']['reference'] not in COMPATIBLE_REFERENCES
                        or manifest['encoding'] != encoding):
                    raise ValueError('QLIE manifest parser identity changed')
                if source_roundtrip:
                    translated = original_rows
                elif filename in available:
                    translated = load_json(_small(extracted / 'gt_output' / filename, 8 << 20))
                else:
                    translated = None
                documents[json_path] = (original_rows, manifest, translated)
            original_rows, manifest, translated = documents[json_path]
            if original_rows != [r.row() for r in records]:
                raise ValueError(f'QLIE original JSON does not match freshly parsed script: {json_path}')
            if [r['locator'] for r in manifest['records']] != json.loads(json.dumps([asdict(r) for r in records])):
                raise ValueError(f'QLIE manifest parser identity/locators changed: {manifest_path}')
            if translated is None:
                continue
            # Copies sharing a JSON have identical bytes, so the manifest's
            # recorded source identity applies to each of them.
            source = manifest['sources'][0]['path']
            checked = validate_translation(manifest, {source: raw}, original_rows, translated)
            try:
                changed = encode_script(patch(text, checked), encoding, bom)
            except ValueError as exc:
                raise ValueError(f"{filename} ({item['archive']}:{item['name']}): {exc}") from None
            if not source_roundtrip:
                translated_members.append(f"{item['archive']}:{item['name']}")
        elif source_roundtrip:
            if records:
                raise ValueError('QLIE script marked empty contains rows')
            changed = encode_script(patch(text, []), encoding, bom)
        else:
            continue
        archive = item['archive']
        if archive not in archive_names:
            raise ValueError('QLIE member references an unknown archive')
        name = validate_names([item['name']])[0]
        if name in work.setdefault(archive, {}):
            raise ValueError('duplicate QLIE rebuild member')
        work[archive][name] = (raw, changed)
    failed = _failed_names(report)
    if not source_roundtrip:
        unknown = sorted(available - known)
        refused = [f'{name} ({failed[name.casefold()]})' for name in unknown if name.casefold() in failed]
        if refused:
            raise ValueError('translation supplied for script(s) that failed extraction and were not exported: '
                             + '; '.join(refused))
        if unknown:
            raise ValueError('unmatched translation filenames: ' + ', '.join(unknown))
    if not work:
        raise ValueError('no matching QLIE translations to pack')
    payloads = []
    copied_failed = sorted(f"{i['archive']}:{i['name']}" for i in report['members']
                           if i.get('status') == 'failed' and i['archive'] in work)
    result = {'schema': 'qlie-repack/3', 'source_roundtrip': source_roundtrip,
              'translated_members': translated_members, 'copied_failed_members': copied_failed,
              'game_launch_tested': False, 'archives': []}
    temporary, streams = [], []
    try:
        _rebuild_all(game, report, work, keys, source_roundtrip, result, temporary, streams)
        recorded = {(i['role'], i['path'], i['sha256']) for i in identities}
        for loaded in keys.sources:
            if (loaded['role'], loaded['path'], loaded['sha256']) not in recorded:
                raise ValueError(f"QLIE key/EXE source changed: {loaded['path']}")
        result['key_sources'] = keys.sources
        payloads.append(('reports/repack.json', _json(result)))
        write_new_tree(output, payloads, Limits(max_file_bytes=16 << 20, max_total_bytes=64 << 20), streams=streams)
    finally:
        for stream in temporary:
            stream.close()
    return result


def _copier(stream):
    def write(sink):
        stream.seek(0)
        while chunk := stream.read(1 << 20):
            sink.write(chunk)
    return write


def _rebuild_all(game, report, work, keys, source_roundtrip, result, temporary, streams):
    """Rebuild each touched PACK into an anonymous temporary file (bounded
    memory for large script packs); publication streams it into the new tree."""
    for identity in report['archives']:
        name = identity['path']
        if name not in work:
            continue
        path = game / name
        _ordinary(path)
        with path.open('rb') as source:
            digest = hashlib.file_digest(source, 'sha256').hexdigest()
            if digest != identity['sha256'] or path.stat().st_size != identity['size']:
                raise ValueError(f'QLIE original archive changed: {name}')
            index = read_index(source)
            mode = identity['mode']
            if index.version != identity['version']:
                raise ValueError(f'QLIE PACK version changed: {name}')
            external, game_key = None, None
            if external_key_required(index, mode):
                external, game_key, _ = keys.external(index.version, mode)
            chain = member_keys(source, index, mode=mode, key_file=external, game_key=game_key)
            replacements = {}
            for entry, key in zip(index.entries, chain):
                logical = entry.name.replace('\\', '/')
                if logical in work[name]:
                    original, changed = work[name][logical]
                    current = read_member(source, index, entry, mode=mode, key_file=key, game_key=game_key,
                                          max_stored=8 << 20, max_output=8 << 20)
                    if current != original:
                        raise ValueError('QLIE extracted original differs from archive member')
                    replacements[entry.name] = changed
            if len(replacements) != len(work[name]):
                raise ValueError('QLIE rebuild member not found in original index')
            destination = tempfile.TemporaryFile()
            temporary.append(destination)
            stats = rebuild(source, destination, replacements, mode=mode, key_file=external, game_key=game_key)
            destination.seek(0)
            digest_out = hashlib.file_digest(destination, 'sha256').hexdigest()
            if source_roundtrip and digest_out != digest:
                raise ValueError('QLIE full archive original roundtrip changed bytes')
            result['archives'].append({'path': name, 'source_sha256': digest, 'sha256': digest_out, **stats})
            streams.append((name, _copier(destination), stats['output_size']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('game', type=Path)
    parser.add_argument('extracted', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--source-roundtrip', action='store_true')
    args = parser.parse_args()
    try:
        result = repack(args.game, args.extracted, args.output, source_roundtrip=args.source_roundtrip)
    except (ValueError, OSError, UnicodeError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        raise SystemExit(2)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
