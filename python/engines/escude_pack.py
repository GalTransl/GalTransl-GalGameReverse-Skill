"""Pack a Haison extraction workspace into a new ESC-ARC2 script.bin.

python -m python.engines.escude_pack WORKSPACE NEW_OUTPUT [--verify-edits]
Default reads gt_output; --verify-edits instead prefixes every original message
with CP932 test text and labels the result as a test archive. Never installs it.
Independent implementation, GPL-3.0-or-later.
"""
import argparse
from dataclasses import asdict
import io
import os
from pathlib import Path
import stat
import tempfile

from python.archives.escude import read_index, read_member, repack
from python.common.contract import load_json, validate_translation
from python.common.safety import Limits, validate_names, write_new_tree
from python.engines.escude_extract import digest, extract, json_bytes, require
from python.engines.escude_mdb import read_names
from python.engines.escude_mess import extract_pair, patch_mess


def read_file(path, limit=16 << 20):
    path = Path(os.path.abspath(path))
    for component in (path, *path.parents):
        info = component.lstat()
        require(not stat.S_ISLNK(info.st_mode) and not (
            getattr(info, 'st_file_attributes', 0) & 0x400), 'linked workspace path')
    require(path.is_file() and path.stat().st_size <= limit, f'invalid/oversized file: {path}')
    with path.open('rb') as stream:
        data = stream.read(limit + 1)
    require(len(data) <= limit, 'input grew past budget')
    return data


def pack(workspace: Path, output: Path, *, verify_edits=False) -> dict:
    workspace, output = Path(workspace), Path(output)
    if os.path.lexists(output):
        raise FileExistsError(f'refusing to replace output: {output}')
    # Derive all member paths, locators and manifests from archived source bytes,
    # never from mutable sidecar addresses. Fresh extraction also checks coverage.
    with tempfile.TemporaryDirectory(prefix='escude-pack-') as tmp:
        root = Path(tmp)
        game = root / 'sources'
        game.mkdir()
        for name in ('data.bin', 'script.bin'):
            (game / name).write_bytes(read_file(workspace / 'original/archives' / name, 8 << 20))
        fresh = root / 'fresh'
        expected = extract(game, fresh)
        saved = load_json(read_file(workspace / 'reports/extraction.json'))
        for field in ('schema', 'profile', 'totals', 'members', 'exports', 'name_table_slots', 'empty_code_members'):
            require(saved.get(field) == expected[field], f'extraction report changed: {field}')
        require([(s['size'], s['sha256']) for s in saved['sources']]
                == [(s['size'], s['sha256']) for s in expected['sources']], 'archive source hashes changed')
        # Check every saved decoded source, including code-only members.
        for source in (fresh / 'original').rglob('*'):
            if source.is_file():
                require(read_file(workspace / source.relative_to(fresh)) == source.read_bytes(),
                        f'original source changed: {source.name}')
        filenames = {Path(e['json']).name for e in expected['exports']}
        for folder in ('gt_input', 'metadata'):
            require({p.name for p in (workspace / folder).iterdir()} == filenames,
                    f'{folder} file set changed')
        translations = {}
        translation_bytes = 0
        if not verify_edits:
            for path in (workspace / 'gt_output').iterdir():
                if path.name == '.keep':
                    continue
                require(path.name in filenames, f'unmatched translation: {path.name}')
                data = read_file(path)
                translation_bytes += len(data)
                require(translation_bytes <= 128 << 20, 'translation batch exceeds budget')
                translations[path.name] = load_json(data)
        database = (fresh / 'original/data/db_scripts.bin').read_bytes()
        names = read_names(database)
        replacements, changed, rows_count = {}, [], 0
        for export in expected['exports']:
            rows = load_json(read_file(fresh / export['json']))
            manifest = load_json(read_file(fresh / export['manifest']))
            require(load_json(read_file(workspace / export['json'])) == rows, 'original JSON changed')
            require(load_json(read_file(workspace / export['manifest'])) == manifest, 'manifest changed')
            sources = {s['path']: (fresh / s['path']).read_bytes() for s in manifest['sources']}
            target = ([dict(row, message='検証：' + row['message']) for row in rows]
                      if verify_edits else translations.get(Path(export['json']).name, rows))
            checked = validate_translation(manifest, sources, rows, target)
            original = (fresh / 'original/script' / export['member']).read_bytes()
            code = (fresh / 'original/script' / export['code']).read_bytes()
            records = extract_pair(code, original, names=names)
            rebuilt = patch_mess(original, {r.index: row['message'] for r, row in zip(records, checked)})
            verified = extract_pair(code, rebuilt, names=names)
            require([dict(message=r.message, **({'name': r.name} if r.name is not None else {}))
                     for r in verified] == checked, 'message roundtrip mismatch')
            require([asdict(r) | {'message': ''} for r in records]
                    == [asdict(r) | {'message': ''} for r in verified], 'nontext binding changed')
            replacements[export['member']] = rebuilt
            rows_count += len(rows)
            if rebuilt != original:
                changed.append(export['member'])
        template = (game / 'script.bin').read_bytes()
        rebuilt = repack(template, replacements)
        stream = io.BytesIO(rebuilt)
        index = read_index(stream)
        normalized = validate_names([e.name for e in index.entries])
        require(normalized == [e['normalized_name'] for e in expected['members']['script.bin']],
                'archive member order changed')
        for entry, name in zip(index.entries, normalized):
            wanted = replacements.get(name)
            if wanted is None:
                wanted = (fresh / 'original/script' / name).read_bytes()
            require(read_member(stream, entry, max_output=16 << 20) == wanted,
                    f'repacked member mismatch: {name}')
        require(bool(changed) or rebuilt == template, 'no-edit archive differs')
        report = dict(schema='escude-haison-pack/1', mode='smoke-test' if verify_edits else 'gt_output',
                      rows=rows_count, members_verified=len(index.entries),
                      translated_files=len(translations), changed_members=changed,
                      original_sha256=digest(template), rebuilt_sha256=digest(rebuilt),
                      rebuilt_size=len(rebuilt), byte_identical=rebuilt == template,
                      limitations=['CP932 messages only; names remain context.',
                                   'PK02 patch excluded; game loading and fonts untested.'])
        write_new_tree(output, [('script.bin', rebuilt), ('verification.json', json_bytes(report))],
                       Limits(max_file_bytes=128 << 20, max_total_bytes=160 << 20))
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('workspace', type=Path)
    parser.add_argument('output', type=Path, help='new directory; parent must exist')
    parser.add_argument('--verify-edits', action='store_true')
    args = parser.parse_args()
    report = pack(args.workspace, args.output, verify_edits=args.verify_edits)
    print(json_bytes({k: v for k, v in report.items() if k != 'changed_members'}).decode('utf-8'))


if __name__ == '__main__':
    main()
