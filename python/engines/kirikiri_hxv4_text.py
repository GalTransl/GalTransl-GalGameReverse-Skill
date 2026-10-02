"""Hxv4 PSB SCN workflow, reusing the shared dialogue contract and writer.

Plain XP3 is an explicit intermediate for the shared SCN pipeline. Delivered
Hx archives preserve original identities and hashes; no game files are replaced.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import tempfile
from python.archives import xp3
from python.archives.kirikiri_hxv4 import derive, read_index, name_hash, path_hash
from python.archives.kirikiri_hxv4_names import inspect
from python.archives.kirikiri_hxv4_payload import Cipher, read_member, build
from python.common.safety import write_new_tree, Limits, validate_names
from .kirikiri_psb import Psb
from . import kirikiri_extract as shared


def encrypted_archive(files, evidence):
    keys = derive(evidence['key_package']); cipher = Cipher(keys)
    entries = evidence['scripts']
    if set(entries) != {n for n, _ in files}:
        raise ValueError('Hx script identity set changed')
    members = []
    for name, data in files:
        e = entries[name]
        if name_hash(Path(name).name) != e['name_hash']:
            raise ValueError('Hx script name hash mismatch')
        members.append((e, data))
    raw = build(members, keys, hx_flags=evidence['hx_flags'])
    stream = io.BytesIO(raw); new = read_index(stream, keys)['files']
    if len(new) != len(members): raise ValueError('Hx output count changed')
    for e, (old, data) in zip(new, members):
        if any(e[k] != old[k] for k in ('id','key','name_hash','path_hash')):
            raise ValueError('Hx output identity changed')
        if read_member(stream, e, cipher) != data: raise ValueError('Hx output plaintext changed')
    return raw


def plain_members(raw):
    from python.archives import kirikiri_xp3
    stream = io.BytesIO(raw); profile, entries = kirikiri_xp3.read_index(stream)
    return [(e.name, kirikiri_xp3.read_member(stream, e, profile)) for e in entries]


def extract(archive, exe, output, *, paths=('', 'scn/', 'scenario/'), language_index=0,
            max_member_bytes=32 << 20, max_scan_bytes=384 << 20):
    """Select hash-verified PSB SCN from one Hx archive into a shared workspace.

    Oversized members remain uninspected, not classified as media or non-script.
    Diagnostics and scan_complete expose this incomplete candidate scan. The
    cumulative budget counts only inspected payload bytes and remains a hard stop.
    """
    archive, output = Path(archive), Path(output)
    if output.exists(): raise FileExistsError(output)
    if (type(max_member_bytes) is not int or type(max_scan_bytes) is not int
            or not 0 < max_member_bytes <= max_scan_bytes): raise ValueError('Hx scan budgets')
    report = inspect(archive, exe, [])
    keys = derive(report['key_package']); cipher = Cipher(keys)
    directories = {}
    for path in paths:
        if path: validate_names([path.rstrip('/')])
        directories[path_hash(path)] = path
    files = []; identities = {}; diagnostics = []; total = 0; verified = 0; skipped = 0; skipped_bytes = 0
    with archive.open('rb') as stream:
        index = read_index(stream, keys)
        for e in index['files']:
            if 'id' not in e:
                diagnostics.append(dict(alias=e['alias'], size=e['size'], reason='unmapped',
                                        issue='unmapped resource; not selected as SCN'))
                continue
            if type(e['size']) is not int or e['size'] < 0: raise ValueError('Hx member size')
            if e['size'] > max_member_bytes:
                skipped += 1
                skipped_bytes += e['size']
                diagnostics.append(dict(id=e['id'], size=e['size'],
                                        name_hash=e['name_hash'], path_hash=e['path_hash'], reason='member-budget',
                                        issue='member above per-resource budget; uninspected, script status unknown'))
                continue
            total += e['size']
            if total > max_scan_bytes: raise ValueError('Hx cumulative scan budget')
            data = read_member(stream, e, cipher, max_size=max_member_bytes); verified += 1
            if not data.startswith(b'PSB\0'): continue
            # Resource-bearing PSB images are not SCN. Unsupported PSB remains diagnostic.
            try: psb = Psb(data)
            except ValueError as ex:
                diagnostics.append(dict(id=e['id'], reason='unsupported-psb', issue=str(ex))); continue
            root = psb.object(psb.root)
            if 'scenes' not in root: continue
            if 'name' not in root: raise ValueError('SCN lacks self-name candidate')
            node = root['name']
            if not 21 <= node.tag <= 24: raise ValueError('SCN name is not a string')
            candidate = psb.strings[node.value]
            candidates = [candidate, candidate+'.scn']
            matches = [n for n in candidates if name_hash(n) == e['name_hash']]
            if len(matches) != 1 or e['path_hash'] not in directories:
                raise ValueError('SCN name/directory hash unresolved; supply --paths candidates')
            prefix = directories[e['path_hash']].rstrip('/')
            name = '/'.join(v for v in (prefix, matches[0]) if v)
            validate_names([name])
            if name in identities: raise ValueError('duplicate SCN storage name')
            identities[name] = e; files.append((name, data))
    if not files: raise ValueError('no supported SCN found')
    evidence = dict(schema='kirikiri-hxv4-text/1', archive=str(archive), exe=str(exe),
                    source_sha256=report['source_sha256'], exe_sha256=report['exe_sha256'],
                    key_package=report['key_package'], hx_flags=index['hx_flags'], scripts=identities,
                    index_entries=len(index['files']), payloads_verified=verified,
                    decrypted_bytes=total, skipped_oversize_members=skipped, skipped_oversize_bytes=skipped_bytes,
                    scan_complete=not diagnostics, diagnostics=diagnostics,
                    scan_limits=dict(max_member_bytes=max_member_bytes,max_scan_bytes=max_scan_bytes),
                    directories=directories, game_loading_verified=False,
                    source_scope='Only hash-verified direct PSB SCN selected. Diagnostics mark unclassified members; dialogue completeness is not established. Other resources stay in original game.',
                    intermediate='Shared SCN pipeline uses a generated plaintext script-only XP3; use this Hx text pack command for encrypted output.')
    with archive.open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest() != report['source_sha256']:
            raise ValueError('input archive changed during scan')
    with tempfile.TemporaryDirectory(prefix='kirikiri-hx-text-') as tmp:
        base = Path(tmp); source = base/'source'; source.mkdir()
        (source/'scripts.xp3').write_bytes(xp3.build(files, filter_name='none', compress_contents=True))
        work = base/'work'
        result = shared.extract(source, work, archives=('scripts.xp3',), verify_edits=True, language_index=language_index)
        payloads = [(p.relative_to(work).as_posix(), p.read_bytes()) for p in work.rglob('*') if p.is_file()]
        # Keep explicitly named plain intermediate evidence, plus encrypted deliverables.
        for stage in ('roundtrip', 'smoke-test'):
            plain = (work/'rebuilt'/stage/'scenario.xp3').read_bytes()
            rebuilt = encrypted_archive(plain_members(plain), evidence)
            payloads.append(('rebuilt/hx-'+stage+'/scenario.xp3', rebuilt))
            evidence[stage] = dict(sha256=shared.digest(rebuilt), bytes=len(rebuilt),
                                   plaintext_readback_equal=True, identities_preserved=True)
        evidence['totals'] = result['totals']
        evidence['script_slots'] = {e['member']: e['name'] for e in result['exports'] + result['non_target']
                                    if e.get('role') != 'system-index'}
        payloads.append(('reports/hxv4.json', shared.js(evidence)))
        write_new_tree(output, payloads, Limits(max_file_bytes=256<<20, max_total_bytes=768<<20))
    return evidence


def pack(workspace, output):
    workspace, output = Path(workspace), Path(output)
    if output.exists(): raise FileExistsError(output)
    evidence = json.loads(shared.read_file(workspace/'reports/hxv4.json', 16<<20))
    if evidence['schema'] != 'kirikiri-hxv4-text/1': raise ValueError('Hx text workspace schema')
    # Source index remains authority for keys/IDs, independent of editable metadata.
    source = shared.regular(evidence['archive'])
    with source.open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest() != evidence['source_sha256']:
            raise ValueError('original Hx archive changed')
        originals = read_index(stream, derive(evidence['key_package']))['files']
    lookup = {e.get('id'): e for e in originals if 'id' in e}
    cipher = Cipher(derive(evidence['key_package']))
    if set(evidence['script_slots']) != set(evidence['scripts']): raise ValueError('Hx source slots changed')
    validate_names(list(evidence['script_slots'].values()))
    for name, e in evidence['scripts'].items():
        if json.loads(shared.js(lookup.get(e['id']))) != e: raise ValueError('Hx source identity metadata changed')
        slot = evidence['script_slots'][name]
        if Path(slot).name != slot: raise ValueError('Hx source slot is not flat')
        raw = shared.read_file(workspace/'original'/slot)
        with source.open('rb') as stream:
            if read_member(stream,e,cipher) != raw:
                raise ValueError('workspace original differs from Hx source')
    with tempfile.TemporaryDirectory(prefix='kirikiri-hx-pack-') as tmp:
        plain = Path(tmp)/'plain'; result = shared.pack(workspace, plain)
        data = encrypted_archive(plain_members((plain/'scenario.xp3').read_bytes()), evidence)
    result.update(output_format='hxv4', sha256=shared.digest(data), bytes=len(data),
                  identities_preserved=True, game_loading_verified=False,
                  source_scan_complete=evidence.get('scan_complete',not evidence.get('diagnostics',[])))
    write_new_tree(output, [('scenario.xp3',data),('verification.json',shared.js(result))],
                   Limits(max_file_bytes=256<<20,max_total_bytes=300<<20))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest='command',required=True)
    ex = sub.add_parser('extract'); ex.add_argument('archive',type=Path); ex.add_argument('output',type=Path)
    ex.add_argument('--exe',required=True,type=Path); ex.add_argument('--paths',nargs='+',default=['','scn/','scenario/'])
    ex.add_argument('--language-index',type=int,default=0)
    pk = sub.add_parser('pack'); pk.add_argument('workspace',type=Path); pk.add_argument('output',type=Path)
    args = parser.parse_args()
    result = extract(args.archive,args.exe,args.output,paths=args.paths,language_index=args.language_index) if args.command=='extract' else pack(args.workspace,args.output)
    summary = dict(totals=result['totals'], scan_complete=result['scan_complete'],
                   skipped_oversize_members=result['skipped_oversize_members'],
                   decrypted_bytes=result['decrypted_bytes'], diagnostic_count=len(result['diagnostics'])) if args.command=='extract' else result
    print(json.dumps(summary,ensure_ascii=True))


if __name__ == '__main__': main()
