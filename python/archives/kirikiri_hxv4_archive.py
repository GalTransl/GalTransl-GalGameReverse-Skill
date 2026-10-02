"""Static Hxv4 archive extraction/rebuild CLI; raw resources, not a dialogue writer.

Always verifies plaintext checksums and reads the rebuilt archive back. Optional
replacement files must already have their internal script format/wrapper rebuilt.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
from python.archives.kirikiri_hxv4 import derive, read_index
from python.archives.kirikiri_hxv4_payload import Cipher, read_member, build
from python.common.safety import Limits, validate_names, write_new_tree
from python.archives.kirikiri_hxv4_names import inspect, resolve


def run(archive, exe, output, names_report=None, replacements=None, *, candidate_reader=None):
    archive, exe = Path(archive), Path(exe)
    if Path(output).exists(): raise FileExistsError('refusing existing output')
    if replacements and not Path(replacements).is_dir(): raise ValueError('replacement directory does not exist')
    report = inspect(archive, exe, [])
    keys = derive(report['key_package']); cipher = Cipher(keys)
    names = set(); paths = {''}
    if names_report:
        source = Path(names_report)
        if source.stat().st_size > 16 << 20: raise ValueError('name report budget')
        evidence = json.loads(source.read_text(encoding='utf-8'))
        if evidence['source_sha256'] != report['source_sha256']:
            raise ValueError('name report belongs to a different archive')
        names.update(e['name'] for e in evidence['entries'] if 'name' in e)
        paths.update(e['path'] for e in evidence['entries'] if 'path' in e)
    members = []; total = 0; parsed = 0; errors = []
    with archive.open('rb') as stream:
        index = read_index(stream, keys)
        if len(index['files']) > 100000: raise ValueError('Hx entry budget')
        if index['mapped'] != len(index['files']):
            raise ValueError('archive contains unmapped members; cannot claim complete encrypted rebuild')
        for e in index['files']:
            total += e['size']
            if total > 384 << 20: raise ValueError('Hx cumulative resource budget')
            data = read_member(stream, e, cipher)
            members.append((e, data))
            try:
                if candidate_reader is not None:
                    hints = candidate_reader(data); names.update(hints)
                    if data[:4] in (b'PSB\0', b'mdf\0') or data[:8] == b'TJS2100\0': parsed += 1
            except (ValueError, UnicodeError) as ex:
                errors.append({'alias': e['alias'], 'error': str(ex)})
            if len(names) > 100000: raise ValueError('Hx candidate budget')
    resolved = resolve(index['files'], names, paths)
    payloads = []; chosen = []; metadata = []; edited = 0; used = set()
    for (e, data), name in zip(members, resolved):
        if 'name' in name and 'path' in name:
            relative = 'resources/' + '/'.join(v for v in (name['path'], name['name']) if v)
        else:
            relative = 'unresolved/' + e['path_hash'] + '/' + e['name_hash'] + '.bin'
        validate_names([relative])
        replacement = Path(replacements)/relative if replacements else None
        result = data
        if replacement and replacement.exists():
            root = Path(replacements).resolve()
            if not replacement.resolve().is_relative_to(root): raise ValueError('replacement escapes root')
            if replacement.stat().st_size > 32 << 20: raise ValueError('replacement size budget')
            result = replacement.read_bytes(); used.add(relative)
            edited += result != data
        chosen.append((e, result)); payloads.append(('original/'+relative, data))
        metadata.append(dict(name, file=relative, sha256=hashlib.sha256(data).hexdigest(),
                             rebuilt_sha256=hashlib.sha256(result).hexdigest()))
    if replacements:
        supplied = {p.relative_to(replacements).as_posix() for p in Path(replacements).rglob('*') if p.is_file()}
        if supplied-used: raise ValueError('unmatched replacement files')
    rebuilt = build(chosen, keys, hx_flags=index['hx_flags'])
    stream = io.BytesIO(rebuilt); reread = read_index(stream, keys)
    if len(reread['files']) != len(chosen): raise ValueError('rebuilt member count mismatch')
    for e, (old, data) in zip(reread['files'], chosen):
        if any(e[k] != old[k] for k in ('id', 'key', 'path_hash', 'name_hash')):
            raise ValueError('rebuilt identity mismatch')
        if read_member(stream, e, cipher) != data: raise ValueError('rebuilt payload mismatch')
    report.update(schema='kirikiri-hxv4-archive/1', entries=metadata,
                  names_resolved=sum('name' in e for e in resolved),
                  payload_decryption_verified=True, archive_roundtrip_verified=True,
                  scripts_parsed_for_candidates=parsed, script_parse_errors=errors,
                  changed_resources=edited, rebuilt_sha256=hashlib.sha256(rebuilt).hexdigest(),
                  game_loading_verified=False, dialogue_exported=False)
    report['validation'] = 'Static EXE/index; all plaintext Adler32; identity and byte comparison after encrypted rebuild'
    payloads += [('repacked/'+archive.name, rebuilt),
                 ('metadata/report.json', (json.dumps(report, ensure_ascii=False, indent=2)+'\n').encode('utf-8'))]
    write_new_tree(Path(output), payloads, Limits(max_file_bytes=384 << 20, max_total_bytes=800 << 20))
    return {k: report[k] for k in ('index_entries', 'names_resolved', 'payload_decryption_verified',
                                  'archive_roundtrip_verified', 'scripts_parsed_for_candidates', 'changed_resources')}


def main(candidate_reader=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--names-report', type=Path)
    parser.add_argument('--replacements', type=Path, help='rebuilt raw resource files mirroring metadata file paths')
    args = parser.parse_args()
    print(json.dumps(run(args.archive, args.exe, args.output, args.names_report, args.replacements, candidate_reader=candidate_reader)))


if __name__ == '__main__': main()
