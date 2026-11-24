"""Hxv4 PSB SCN workflow, reusing the shared dialogue contract and writer.

Plain XP3 is an explicit intermediate for the shared SCN pipeline. Delivered
Hx archives preserve original identities and hashes; no game files are replaced.
"""
import argparse
import hashlib
import io
import json
from collections import Counter
from pathlib import Path
import tempfile
import zlib
from python.archives import xp3
from python.archives.xp3 import _inflate
from python.archives.kirikiri_hxv4 import derive, read_index, name_hash, path_hash
from python.archives.kirikiri_hxv4_names import inspect
from python.archives.kirikiri_hxv4_payload import Cipher, read_member, build
from python.common.safety import write_new_tree, Limits, validate_names, validate_new_tree_destination
from .kirikiri_psb import Psb
from . import kirikiri_extract as shared


MDF = b'mdf\0'


def unwrap(data, limit=32 << 20):
    """Return (payload, wrapper). MDF is `mdf\\0`, u32 LE inflated size, one
    zlib stream; size mismatch, truncation and trailing bytes are rejected."""
    if not data.startswith(MDF): return data, None
    if len(data) < 8: raise ValueError('truncated MDF')
    return _inflate(data[8:], int.from_bytes(data[4:8], 'little'), limit), 'mdf'


def wrap(payload, wrapper):
    if wrapper is None: return payload
    if wrapper != 'mdf': raise ValueError('unknown Hx script wrapper')
    if len(payload) > 0xffffffff: raise ValueError('MDF payload size')
    return MDF + len(payload).to_bytes(4, 'little') + zlib.compress(payload, 9)


def stored_script(name, data, evidence, originals=None):
    """Re-apply the recorded wrapper; unchanged scripts keep the original bytes."""
    wrapper = evidence.get('wrappers', {}).get(name)
    if wrapper is None: return data
    old = (originals or {}).get(name)
    if old is not None and unwrap(old)[0] == data: return old
    stored = wrap(data, wrapper)
    if unwrap(stored)[0] != data: raise ValueError('MDF rewrap mismatch')
    return stored


def encrypted_archive(files, evidence, originals=None):
    keys = derive(evidence['key_package']); cipher = Cipher(keys)
    entries = evidence['scripts']
    if set(entries) != {n for n, _ in files}:
        raise ValueError('Hx script identity set changed')
    members = []
    for name, data in files:
        e = entries[name]
        if name_hash(Path(name).name) != e['name_hash']:
            raise ValueError('Hx script name hash mismatch')
        members.append((e, stored_script(name, data, evidence, originals)))
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
            speaker_name=True, max_member_bytes=32 << 20, max_scan_bytes=384 << 20):
    """Select hash-verified PSB SCN from one Hx archive into a shared workspace.

    Oversized members remain uninspected, not classified as media or non-script.
    Diagnostics and scan_complete expose this incomplete candidate scan. The
    cumulative budget counts only inspected payload bytes and remains a hard stop.
    """
    archive, output = Path(archive), Path(output)
    validate_new_tree_destination(output)
    if (type(max_member_bytes) is not int or type(max_scan_bytes) is not int
            or not 0 < max_member_bytes <= max_scan_bytes): raise ValueError('Hx scan budgets')
    report = inspect(archive, exe, [])
    keys = derive(report['key_package']); cipher = Cipher(keys)
    directories = {}
    for path in paths:
        if path: validate_names([path.rstrip('/')])
        directories[path_hash(path)] = path
    files = []; identities = {}; diagnostics = []; total = 0; verified = 0; skipped = 0; skipped_bytes = 0
    wrappers = {}; originals = {}; heads = Counter()
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
            if total > max_scan_bytes:
                raise ValueError(f'Hx cumulative scan budget: {total} decrypted bytes exceed {max_scan_bytes} '
                                 f'after {verified} members ({len(files)} SCN so far). This archive is mostly '
                                 'non-script resources; pass the archive that holds the SCN (often scn.xp3), '
                                 'or raise --max-scan-mib after checking free memory')
            stored = read_member(stream, e, cipher, max_size=max_member_bytes); verified += 1
            try: data, wrapper = unwrap(stored, max_member_bytes)
            except ValueError as ex:
                diagnostics.append(dict(id=e['id'], reason='unsupported-mdf', issue=str(ex))); continue
            heads[('mdf>' if wrapper else '') + data[:4].hex()] += 1
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
                # Keep scanning: one SCN whose self-name differs from its storage
                # name must not hide the rest, but it is reported, not guessed.
                diagnostics.append(dict(id=e['id'], name_hash=e['name_hash'], path_hash=e['path_hash'],
                                        self_name=candidate, reason='scn-name-unresolved',
                                        issue=('self-name hash matches storage name' if matches else
                                               'SCN self-name does not hash to the storage name')
                                              + ('' if e['path_hash'] in directories else
                                                 '; directory hash not in --paths candidates')
                                              + '; not exported, dialogue completeness not established'))
                continue
            prefix = directories[e['path_hash']].rstrip('/')
            name = '/'.join(v for v in (prefix, matches[0]) if v)
            validate_names([name])
            if name in identities: raise ValueError('duplicate SCN storage name')
            identities[name] = e; files.append((name, data))
            if wrapper: wrappers[name] = wrapper; originals[name] = stored
    if not files:
        unmapped = sum(d['reason'] == 'unmapped' for d in diagnostics)
        raise ValueError(f'no supported SCN found: {len(index["files"])} index entries, {unmapped} unmapped, '
                         f'{verified} decrypted, {skipped} over the member budget; decrypted heads (hex, mdf> = '
                         f'inside MDF): {dict(heads.most_common(6))}. PSB heads are 50534200; other heads mean '
                         'this archive holds no PSB SCN or uses an unsupported wrapper')
    evidence = dict(schema='kirikiri-hxv4-text/1', archive=str(archive), exe=str(exe),
                    source_sha256=report['source_sha256'], exe_sha256=report['exe_sha256'],
                    key_package=report['key_package'], hx_flags=index['hx_flags'], scripts=identities,
                    wrappers=wrappers,
                    index_entries=len(index['files']), payloads_verified=verified,
                    decrypted_bytes=total, skipped_oversize_members=skipped, skipped_oversize_bytes=skipped_bytes,
                    scan_complete=not diagnostics, diagnostics=diagnostics,
                    scan_limits=dict(max_member_bytes=max_member_bytes,max_scan_bytes=max_scan_bytes),
                    directories=directories, game_loading_verified=False,
                    source_scope='Only hash-verified PSB SCN (direct or MDF-wrapped; wrapper recorded in wrappers) selected. Diagnostics mark unclassified members; dialogue completeness is not established. Other resources stay in original game.',
                    intermediate='Shared SCN pipeline uses a generated plaintext script-only XP3; use this Hx text pack command for encrypted output.')
    with archive.open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest() != report['source_sha256']:
            raise ValueError('input archive changed during scan')
    with tempfile.TemporaryDirectory(prefix='kirikiri-hx-text-') as tmp:
        base = Path(tmp); source = base/'source'; source.mkdir()
        (source/'scripts.xp3').write_bytes(xp3.build(files, filter_name='none', compress_contents=True))
        work = base/'work'
        result = shared.extract(source, work, archives=('scripts.xp3',), verify_edits=True,
                                language_index=language_index, speaker_name=speaker_name)
        payloads = [(p.relative_to(work).as_posix(), p.read_bytes()) for p in work.rglob('*') if p.is_file()]
        # Keep explicitly named plain intermediate evidence, plus encrypted deliverables.
        for stage in ('roundtrip', 'smoke-test'):
            plain = (work/'rebuilt'/stage/'scenario.xp3').read_bytes()
            rebuilt = encrypted_archive(plain_members(plain), evidence, originals)
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
    validate_new_tree_destination(output)
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
    wrappers = evidence.get('wrappers', {})
    if not isinstance(wrappers, dict) or set(wrappers) - set(evidence['scripts']) or set(wrappers.values()) - {'mdf'}:
        raise ValueError('Hx script wrapper metadata changed')
    originals = {}
    for name, e in evidence['scripts'].items():
        if json.loads(shared.js(lookup.get(e['id']))) != e: raise ValueError('Hx source identity metadata changed')
        slot = evidence['script_slots'][name]
        if Path(slot).name != slot: raise ValueError('Hx source slot is not flat')
        raw = shared.read_file(workspace/'original'/slot)
        with source.open('rb') as stream:stored = read_member(stream,e,cipher)
        payload, wrapper = unwrap(stored)
        if payload != raw or wrapper != wrappers.get(name):
            raise ValueError('workspace original differs from Hx source')
        if wrapper: originals[name] = stored
    with tempfile.TemporaryDirectory(prefix='kirikiri-hx-pack-') as tmp:
        plain = Path(tmp)/'plain'; result = shared.pack(workspace, plain, incremental=False)
        data = encrypted_archive(plain_members((plain/'scenario.xp3').read_bytes()), evidence, originals)
    result.pop('note', None)
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
    ex.add_argument('--max-scan-mib',type=int,default=384,
                    help='cumulative decrypted-byte budget (MiB, at most 2048); raise only for archives mixing SCN with media')
    ex.add_argument('--speaker-name',action=argparse.BooleanOptionalAction,default=True,
                    help='write string speakers when the display slot is null (default: enabled; --no-speaker-name keeps them read-only)')
    pk = sub.add_parser('pack'); pk.add_argument('workspace',type=Path); pk.add_argument('output',type=Path)
    args = parser.parse_args()
    if args.command=='extract' and not 32 <= args.max_scan_mib <= 2048: parser.error('--max-scan-mib must be 32..2048')
    result = extract(args.archive,args.exe,args.output,paths=args.paths,language_index=args.language_index,speaker_name=args.speaker_name,
                     max_scan_bytes=args.max_scan_mib<<20) if args.command=='extract' else pack(args.workspace,args.output)
    summary = dict(totals=result['totals'], scan_complete=result['scan_complete'],
                   skipped_oversize_members=result['skipped_oversize_members'],
                   decrypted_bytes=result['decrypted_bytes'], diagnostic_count=len(result['diagnostics'])) if args.command=='extract' else result
    print(json.dumps(summary,ensure_ascii=True))


if __name__ == '__main__': main()
