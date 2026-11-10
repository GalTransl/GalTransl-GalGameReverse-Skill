"""Shared Kirikiri XP3 / PSB v2-v3 single/multilingual SCN extract and pack CLI.

Select input archives explicitly; default is only data.xp3. Archive adapters
are detected from bounded index evidence, not game names. Never deploys.
GPL-3.0-or-later. See engines/kirikiri.md for capability limits.
"""
import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat

from python.archives import kirikiri_xp3 as xp3
from python.common.contract import make_manifest, validate_translation, dump_rows, load_json
from python.common.safety import Limits, validate_names, write_new_tree, validate_new_tree_destination
from .kirikiri_psb import Psb
from .kirikiri_scn import writable_records, patch, controls, fingerprint

PROFILE='kirikiri-psb-scn/1'
# Read compatibility for workspaces already delivered before entrypoint unification.
LEGACY={'kirikiri-senren-psb3/1':('senren-scn-psb3','senren-cx',3),
        'kirikiri-loverec-psb2/1':('loverec-scn-psb2','elif-plain',2)}


def digest(data):return hashlib.sha256(data).hexdigest()


def js(value):return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf-8')


def regular(path):
    path=Path(os.path.abspath(path))
    for part in (path,*path.parents):
        info=part.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400:raise ValueError('linked input path')
    if not path.is_file():raise ValueError('input is not an ordinary file')
    return path


def read_file(path,limit=32<<20):
    path=regular(path)
    if path.stat().st_size>limit:raise ValueError('input file budget')
    with path.open('rb') as stream:data=stream.read(limit+1)
    if len(data)>limit:raise ValueError('input grew past budget')
    return data


LEGACY_VARIANT='psb-scn-single-language'


def scn_variant(recs,language_index=0):
    """Name the SCN layout from parsed structure, not from a fixed label."""
    if language_index or any(r.get('localized') for r in recs):return f'psb-scn-multi-language:{language_index}'
    return 'psb-scn-single-language'


def manifest_for(name,data,recs,profile=PROFILE,language_index=0,*,variant=None):
    if variant is None:variant=LEGACY[profile][0] if profile in LEGACY else scn_variant(recs,language_index)
    return make_manifest(engine='kirikiri',variant=variant,reference=profile,
                         sources={'original/'+name:data},rows=[r['row'] for r in recs],encoding='utf-8',
                         locators=[{k:r[k] for k in ('message','name','caches','kind','scene','index','length','strip_ruby_dot','trim_ruby_space','search_only','opaque','non_writable') if k in r} for r in recs],
                         name_policies=['writable' if r['name'] else 'context' if 'name' in r['row'] else 'absent' for r in recs],
                         protected_tokens=[[] if r.get('non_writable') else list(dict.fromkeys(controls(r['row']['message']))) for r in recs])


def verify_archive(data,files,profile,filter_spec=None):
    stream=io.BytesIO(data);detected,entries=xp3.read_index(stream,profile)
    if [e.name for e in entries]!=[n for n,d in files]:raise ValueError('XP3 output members/order mismatch')
    for entry,(name,wanted) in zip(entries,files):
        if xp3.read_member(stream,entry,detected,filter_spec)!=wanted:raise ValueError('XP3 output member mismatch')


# Script/data members are named after routes or scenes, not speaker assets.
SCRIPT_EXTENSIONS=('.ks','.scn','.tjs','.txt','.csv','.json','.ini','.psb')
NAME_SPLIT=re.compile(r'[_\-.\s()\[\]{},+#@]+')
MAX_NAME_SCAN_ARCHIVES=64


def member_name_keys(names):
    """Map casefolded directory names and filename tokens to one sample path.

    A token also yields its prefix before a trailing ASCII run or first digit,
    so `key_01.png`, `keya.png` and `dir/key/x.png` all expose `key`. Script
    and data members are skipped: they are often named after routes.
    """
    keys={}
    for raw in names:
        path=raw.replace('\\','/');parts=[p for p in path.split('/') if p]
        if not parts or parts[-1].lower().endswith(SCRIPT_EXTENSIONS):continue
        stem=parts[-1].rsplit('.',1)[0] if '.' in parts[-1] else parts[-1]
        found={p.casefold() for p in parts[:-1]}
        for token in NAME_SPLIT.split(stem):
            if not token:continue
            found.add(token.casefold())
            head=re.match(r'(.+?)[0-9A-Za-z]+$',token)
            if head and not head.group(1).isascii():found.add(head.group(1).casefold())
            head=re.match(r'(\D+?)\d',token)
            if head:found.add(head.group(1).casefold())
        for key in found:keys.setdefault(key,path)
    return keys


def speaker_key_conflicts(who_names,keys):
    """Speaker values that also name an archive directory or filename token."""
    return {who:keys[who.casefold()] for who in sorted(who_names) if who and who.casefold() in keys}


def name_scan_archives(game,selected):
    """Other top-level *.xp3 beside the selected ones; only indexes are read."""
    extra=sorted(p.name for p in Path(game).iterdir()
                 if p.suffix.lower()=='.xp3' and p.name not in selected and p.is_file())
    return extra[:MAX_NAME_SCAN_ARCHIVES],extra[MAX_NAME_SCAN_ARCHIVES:]


def flat_patch_members(changed,known):
    """Map changed (member, data) to root basenames; reject collisions, incl. case.

    `known` is every member path selected in the workspace, so a flattened
    patch name never shadows a different member sharing that basename.
    """
    owners={}
    for member in known:
        owners.setdefault(Path(member.replace('\\','/')).name.casefold(),set()).add(member)
    result=[];seen={}
    for member,data in changed:
        base=Path(member.replace('\\','/')).name;key=base.casefold()
        clash=owners.get(key,{member})-{member}
        if key in seen or clash:
            raise ValueError(f'flat patch basename collision for {base!r}: {sorted(clash|{member}|({seen[key]} if key in seen else set()))}')
        seen[key]=member;result.append((member,base,data))
    validate_names([b for _,b,_ in result])
    return result


def extract(game,output,*,archives=('data.xp3',),overlay='path',archive_profile='auto',
            output_format='same',verify_edits=False,language_index=0,filter_spec=None,
            speaker_name='auto'):
    """Extract supported SCN from selected archives, later inputs overriding earlier.

    'path' overlays exact storage paths. 'basename' is an explicit choice for
    games whose patch moves base subdirectory members to root. Duplicate JSON
    basenames under path mode receive deterministic suffixes; never guess merge.

    speaker_name='auto' writes string speakers (who) only while no who value
    also names an archive directory or filename token; on such evidence who
    stays read-only and the report carries speaker_key_warning. True/False
    force the policy (the warning is still reported).
    """
    if type(language_index) is not int or language_index < 0: raise ValueError('invalid language index')
    if speaker_name!='auto' and type(speaker_name) is not bool: raise ValueError('invalid speaker_name flag')
    if filter_spec is not None: filter_spec=xp3.validate(filter_spec)
    game,output=Path(game),Path(output)
    validate_new_tree_destination(output)
    if overlay not in ('path','basename'):raise ValueError('unknown overlay mode')
    archive_names=validate_names(list(archives))
    if not archive_names:raise ValueError('select at least one input archive')
    selected={};sources=[];inventories={};profiles=set();overridden=[];member_names=[]
    for archive_id,archive in enumerate(archive_names):
        path=regular(game/archive)
        with path.open('rb') as stream:
            profile,entries=xp3.read_index(stream,archive_profile);profiles.add(profile)
            member_names.extend(e.name for e in entries)
            candidates=[(i,e) for i,e in enumerate(entries) if e.name.lower().endswith('.scn')]
            validate_names([e.name for i,e in candidates])
            if overlay=='basename':validate_names([Path(e.name).name for i,e in candidates])
            inventories[archive]=[asdict(e) for i,e in candidates]
            for ordinal,e in candidates:
                key=e.name if overlay=='path' else Path(e.name).name
                item=dict(archive=archive,archive_id=archive_id,ordinal=ordinal,entry=e,profile=profile)
                if key in selected:
                    old=selected[key];overridden.append(dict(archive=old['archive'],member=old['entry'].name,
                                                             replacement_archive=archive,replacement_member=e.name))
                selected[key]=item
            stream.seek(0);h=hashlib.file_digest(stream,'sha256').hexdigest()
            sources.append(dict(name=archive,size=path.stat().st_size,sha256=h,profile=profile,
                                archive_entries=len(entries),scn_entries=len(candidates),
                                diagnostics=[dict(member=e.name,issue=e.issue) for e in entries if getattr(e,'issue',None)]))
    if not selected or sum(x['entry'].size for x in selected.values())>256<<20:raise ValueError('SCN selection empty/exceeds budget')
    if output_format=='same':
        if len(profiles)!=1:raise ValueError('mixed archive profiles: select --output-format explicitly')
        output_format=next(iter(profiles))
    if output_format not in xp3.FORMATS:raise ValueError('unsupported output format')
    # Case-insensitive: Windows and XP3 storage lookup do not distinguish case.
    counts=Counter(Path(x['entry'].name).name.casefold() for x in selected.values())
    slots=[]
    for item in selected.values():
        e=item['entry'];name=Path(e.name).name
        if counts[name.casefold()]>1:name=name[:-4]+f'__a{item["archive_id"]:02d}_{item["ordinal"]:05d}.scn'
        item['slot']=name;slots.append(name)
    validate_names(slots)
    # Speaker-key audit: member paths of the selected and sibling top-level XP3.
    scanned,unscanned=list(archive_names),[]
    extra,over_budget=name_scan_archives(game,set(archive_names))
    for archive in extra:
        try:
            with regular(game/archive).open('rb') as stream:member_names.extend(e.name for e in xp3.read_index(stream)[1])
            scanned.append(archive)
        except (ValueError,OSError) as exc:unscanned.append(dict(archive=archive,reason=str(exc)[:200]))
    unscanned.extend(dict(archive=a,reason='name scan archive budget') for a in over_budget)
    name_keys=member_name_keys(member_names);del member_names
    flag=True if speaker_name=='auto' else speaker_name
    scan=_scan_scn(game,selected,flag,language_index,filter_spec,verify_edits)
    conflicts=speaker_key_conflicts(scan['who'],name_keys)
    if speaker_name=='auto' and conflicts:
        # Evidence that who doubles as an asset key: re-run with who read-only
        # so manifests mark these names as context and pack rejects edits.
        flag=False;scan=_scan_scn(game,selected,flag,language_index,filter_spec,verify_edits)
    payloads,files,smokes,exports,non_target,totals,versions=(
        scan[k] for k in ('payloads','files','smokes','exports','non_target','totals','versions'))
    warning=None
    if conflicts:
        warning=dict(names=sorted(conflicts),evidence=conflicts,
                     action=('who read-only (auto)' if speaker_name=='auto' else
                             'who kept writable by explicit speaker_name=True' if flag else 'who already read-only'),
                     note='Speaker (who) values also appear as archive directory/file names; they are likely internal keys for sprites or voices. Display slots stay writable.')
    rebuilt_info=None
    roundtrip=xp3.build(files,output_format,filter_spec);verify_archive(roundtrip,files,output_format,filter_spec)
    payloads.append(('rebuilt/roundtrip/scenario.xp3',roundtrip))
    rebuilt_info=dict(members=len(files),original_psb_byte_identical=True,roundtrip_sha256=digest(roundtrip),roundtrip_bytes=len(roundtrip))
    if verify_edits:
        smoke=xp3.build(smokes,output_format,filter_spec);verify_archive(smoke,smokes,output_format,filter_spec)
        payloads.append(('rebuilt/smoke-test/scenario.xp3',smoke))
        rebuilt_info.update(smoke_sha256=digest(smoke),smoke_bytes=len(smoke),smoke_all_messages_prefix='验证',nontext_semantics_unchanged=True)
    for source in sources:
        with (game/source['name']).open('rb') as stream:
            if hashlib.file_digest(stream,'sha256').hexdigest()!=source['sha256']:raise ValueError('input archive changed')
    report=dict(profile=PROFILE,filter_spec=filter_spec,language_index=language_index,speaker_name=flag,
                speaker_name_mode='auto' if speaker_name=='auto' else 'explicit',
                output_format=output_format,overlay=overlay,sources=sources,inventories=inventories,
                overridden=overridden,exports=exports,non_target=non_target,totals=dict(totals),
                name_scan=dict(archives=scanned,unscanned=unscanned),
                psb_versions=dict(versions),packed_members=[n for n,d in files],rebuilt=rebuilt_info,
                limitations=['Only explicitly selected archives; no automatic patch language/priority inference.',
                             'New script-only XP3; no .sig signing, game load or font validation.',
                             'Scene-state phonechat history snapshots are preserved; their UI text is not automatically rebound to dialogue rows.',
                             'Select records without a display field (link/storage shape) are preserved but not exported; their key sets are listed in skipped_structural_choices.'])
    if warning:report['speaker_key_warning']=warning
    if any(e.get('opaque_fields') or e.get('non_writable') for e in exports):
        report['limitations'].append('Records with unverified derived fields keep their original length/cache bytes; records with unrecognized control syntax are exported but cannot be rewritten. See per-export opaque_fields and non_writable, and re-extract after extending the writer rules.')
    payloads.extend([('reports/extraction.json',js(report)),('gt_output/.keep',b'')])
    write_new_tree(output,payloads,Limits(max_file_bytes=256<<20,max_total_bytes=512<<20))
    return report


def _scan_scn(game,selected,speaker_name,language_index,filter_spec,verify_edits):
    payloads=[];files=[];smokes=[];exports=[];non_target=[];totals=Counter();versions=Counter();who=set()
    for i,item in enumerate(selected.values()):
        e=item['entry'];name=item['slot']
        with (game/item['archive']).open('rb') as stream:data=xp3.read_member(stream,e,item['profile'],filter_spec)
        psb=Psb(data);versions[psb.version]+=1;root=psb.object(psb.root)
        if 'scenes' not in root:
            if set(root)!={'list','map'}:raise ValueError(f'unclassified SCN root: {e.name}')
            payloads.append(('original/system/'+name,data))
            non_target.append(dict(name=name,member=e.name,role='system-index',sha256=digest(data)));continue
        skipped=[]
        try:
            recs,strict_issue=writable_records(psb,language_index,skipped=skipped,speaker_name=speaker_name)
            rows=[r['row'] for r in recs];original,_=patch(psb,recs,rows)
        except ValueError as exc:
            raise ValueError(f"SCN {item['archive']}:{e.name}: {exc}") from exc
        if original!=data:raise ValueError('original PSB writer differs')
        structure=dict(skipped_structural_choices=skipped) if skipped else {}
        opaque=sum(len(r['opaque']) for r in recs if r.get('opaque'))
        non_writable=[dict(scene=r['scene'],index=r['index'],reason=r['non_writable']) for r in recs if r.get('non_writable')]
        if strict_issue is not None:structure['verified_dialect_issue']=strict_issue
        if opaque:structure['opaque_fields']=opaque
        if non_writable:structure['non_writable']=non_writable
        totals.update(structural_choices=len(skipped),opaque_fields=opaque,non_writable_records=len(non_writable))
        payloads.append(('original/'+name,data));files.append((e.name,original))
        if not rows:
            non_target.append(dict(name=name,member=e.name,archive=item['archive'],role='empty-story',sha256=digest(data),**structure))
            if verify_edits:smokes.append((e.name,data))
            continue
        # Only speakers that would be exported as the name (display slot null).
        who.update(r['row']['name'] for r in recs if r.get('name_source')=='who')
        flat=name[:-4]+'.json';manifest=manifest_for(name,data,recs,language_index=language_index)
        payloads.extend([('gt_input/'+flat,dump_rows(rows)),('metadata/'+flat,js(manifest))])
        exports.append(dict(name=name,member=e.name,archive=item['archive'],json=flat,
                            sha256=digest(data),rows=len(rows),psb_version=psb.version,**structure))
        totals.update(files=1,rows=len(rows),choices=sum(r['kind']=='choice' for r in recs),
                      image_alts=sum(r['kind']=='image-alt' for r in recs),
                      named=sum('name' in r['row'] for r in recs),writable_names=sum(r['name'] is not None for r in recs),
                      who_names=sum(r.get('name_source')=='who' for r in recs),
                      writable_who_names=sum(r.get('name_source')=='who' and r['name'] is not None for r in recs),
                      display_names=sum(r.get('name_source')=='display' for r in recs),
                      derived_cache_rows=sum(bool(r['caches']) for r in recs))
        if verify_edits:
            translated=[dict(row,message=row['message'] if rec.get('non_writable') else '验证'+row['message'])
                        for rec,row in zip(recs,rows)]
            changed,paths=patch(psb,recs,translated);check=Psb(changed)
            if [r['row'] for r in writable_records(check,language_index,speaker_name=speaker_name)[0]]!=translated or fingerprint(psb,paths)!=fingerprint(check,paths):
                raise ValueError('changed PSB text/nontext mismatch')
            smokes.append((e.name,changed));del check
        if i%25==0:print(f'verified {i+1}/{len(selected)} SCN, {totals["rows"]} rows',flush=True)
        del psb
    return dict(payloads=payloads,files=files,smokes=smokes,exports=exports,non_target=non_target,
                totals=totals,versions=versions,who=who)


PATCH_FILTERS=('same','none')


def build_patch(changed,known,output_format,filter_spec,patch_filter='same'):
    """Flat incremental patch.xp3 from (member, rebuilt) pairs that differ.

    patch_filter='same' reuses the source archive writer and filter spec (a
    filter installed for every mounted archive also decodes the patch);
    'none' writes a standard unfiltered File index. Read back member by member.
    """
    if patch_filter not in PATCH_FILTERS:raise ValueError('unknown patch filter mode')
    if not changed:raise ValueError('no changed members: nothing to patch (gt_output matches the original); use the full pack only for roundtrip verification')
    flat=flat_patch_members(changed,known)
    files=[(base,data) for _,base,data in flat]
    if patch_filter=='none':output_format,filter_spec='plain',None
    packed=xp3.build(files,output_format,filter_spec);verify_archive(packed,files,output_format,filter_spec)
    return packed,dict(output_format=output_format,filter_spec=filter_spec,patch_filter=patch_filter,
                       changed_members=[dict(member=m,packed_as=b) for m,b,_ in flat])


def pack(workspace,output,*,incremental=True,patch_filter='same'):
    """Rebuild SCN from gt_output.

    incremental=True (default) writes patch.xp3 holding only members whose rebuilt
    bytes differ, flattened to basenames. incremental=False writes the full
    script-only scenario.xp3 for roundtrip verification, not for delivery.
    """
    workspace,output=Path(workspace),Path(output)
    validate_new_tree_destination(output)
    if type(incremental) is not bool or patch_filter not in PATCH_FILTERS:raise ValueError('invalid patch options')
    report=load_json(read_file(workspace/'reports/extraction.json'));profile=report.get('profile')
    if profile!=PROFILE and profile not in LEGACY:raise ValueError('unknown workspace profile')
    filter_spec=report.get('filter_spec')
    if filter_spec is not None:
        filter_spec=xp3.validate(filter_spec)
        if profile in LEGACY:raise ValueError('legacy workspace filter changed')
    language_index=report.get('language_index',0)
    if type(language_index) is not int or language_index < 0: raise ValueError('invalid language index')
    if profile in LEGACY and language_index != 0: raise ValueError('legacy workspace language changed')
    # Workspaces created before the flag existed used context-only speakers.
    speaker_name=report.get('speaker_name',False)
    if type(speaker_name) is not bool: raise ValueError('invalid speaker_name flag')
    output_format=LEGACY[profile][1] if profile in LEGACY else report['output_format']
    exports=report['exports'];filenames=[e['json'] for e in exports]
    validate_names(filenames);validate_names([e['name'] for e in exports]);validate_names([e['member'] for e in exports])
    for e in exports:
        if Path(e['name']).name!=e['name'] or not e['name'].lower().endswith('.scn') or e['json']!=e['name'][:-4]+'.json':raise ValueError('invalid export mapping')
    for folder in ('gt_input','metadata'):
        if {p.name for p in (workspace/folder).iterdir()}!=set(filenames):raise ValueError('workspace file set changed')
    translations={};total=0
    for path in (workspace/'gt_output').iterdir():
        if path.name=='.keep':continue
        if path.name not in filenames:raise ValueError('unmatched translation filename')
        raw=read_file(path);total+=len(raw)
        if total>64<<20:raise ValueError('translation budget')
        translations[path.name]=load_json(raw)
    files=[];changed=[]
    for e in exports:
        data=read_file(workspace/'original'/e['name'])
        if digest(data)!=e['sha256']:raise ValueError('source SCN changed')
        psb=Psb(data)
        if profile in LEGACY and psb.version!=LEGACY[profile][2]:raise ValueError('legacy PSB version mismatch')
        recs,_=writable_records(psb,language_index,speaker_name=speaker_name);rows=[r['row'] for r in recs]
        manifest=manifest_for(e['name'],data,recs,profile,language_index)
        stored=load_json(read_file(workspace/'metadata'/e['json']))
        if stored!=load_json(js(manifest)):
            # Workspaces written before layout-aware variants used one fixed label.
            legacy=manifest_for(e['name'],data,recs,profile,language_index,variant=LEGACY_VARIANT)
            if profile in LEGACY or stored!=load_json(js(legacy)):raise ValueError('manifest changed')
            manifest=legacy
        if load_json(read_file(workspace/'gt_input'/e['json']))!=rows:raise ValueError('original JSON changed')
        translated=translations.get(e['json'],rows)
        validate_translation(manifest,{'original/'+e['name']:data},rows,translated)
        rebuilt,paths=patch(psb,recs,translated)
        if rebuilt!=data:
            check=Psb(rebuilt)
            if [r['row'] for r in writable_records(check,language_index,speaker_name=speaker_name)[0]]!=translated or fingerprint(psb,paths)!=fingerprint(check,paths):raise ValueError('PSB roundtrip mismatch')
            changed.append((e['member'],rebuilt))
        files.append((e['member'],rebuilt))
    for e in report.get('non_target',[]):
        if e['role']!='empty-story':continue
        validate_names([e['name']]);validate_names([e['member']])
        if Path(e['name']).name!=e['name']:raise ValueError('invalid empty SCN source slot')
        data=read_file(workspace/'original'/e['name'])
        if digest(data)!=e['sha256'] or writable_records(Psb(data),language_index,speaker_name=speaker_name)[0]:raise ValueError('empty SCN changed')
        files.append((e['member'],data))
    # Keep extraction order even when empty scripts were interleaved.
    if profile==PROFILE:
        order=validate_names(report['packed_members'])
        if set(order)!={n for n,d in files}:raise ValueError('packed member mapping changed')
        positions={name:i for i,name in enumerate(order)}
        files.sort(key=lambda item:positions[item[0]])
    known=[n for n,_ in files]+[e['member'] for e in report.get('non_target',[]) if e.get('role')=='system-index']
    if incremental:
        packed,info=build_patch(changed,known,output_format,filter_spec,patch_filter)
        result=dict(profile=profile,mode='patch',members=len(changed),changed_files=len(changed),**info,
                    translated_files=len(translations),sha256=digest(packed),bytes=len(packed),
                    all_members_readback_equal=True,runtime_verified=False)
        name='patch.xp3'
    else:
        packed=xp3.build(files,output_format,filter_spec);verify_archive(packed,files,output_format,filter_spec)
        result=dict(profile=profile,mode='full',output_format=output_format,members=len(files),changed_files=len(changed),
                    changed_members=[dict(member=m,packed_as=m) for m,_ in changed],
                    translated_files=len(translations),sha256=digest(packed),bytes=len(packed),
                    all_members_readback_equal=True,runtime_verified=False,
                    note='Full script-only archive for roundtrip verification; deliver patch mode instead.')
        name='scenario.xp3'
    write_new_tree(output,[(name,packed),('verification.json',js(result))],Limits(max_file_bytes=256<<20,max_total_bytes=300<<20))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);subs=parser.add_subparsers(dest='command',required=True)
    extract_parser=subs.add_parser('extract');extract_parser.add_argument('source',type=Path);extract_parser.add_argument('output',type=Path)
    extract_parser.add_argument('--archives',nargs='+',default=['data.xp3'],help='relative paths, earlier to later; no automatic patch selection')
    extract_parser.add_argument('--overlay',choices=('path','basename'),default='path')
    extract_parser.add_argument('--archive-profile',choices=('auto',)+xp3.FORMATS,default='auto')
    extract_parser.add_argument('--output-format',choices=('same',)+xp3.FORMATS,default='same')
    extract_parser.add_argument('--filter-spec',type=Path,help='JSON algorithm and parameters for supported XP3 byte filter')
    extract_parser.add_argument('--language-index',type=int,default=0,help='zero-based existing SCN language slot; never inserts a language')
    extract_parser.add_argument('--verify-edits',action='store_true')
    extract_parser.add_argument('--speaker-name',action=argparse.BooleanOptionalAction,default='auto',
                                help='write string speakers when the display slot is null (default auto: enabled unless a speaker value also names an archive directory/file; --speaker-name forces, --no-speaker-name keeps them read-only)')
    pack_parser=subs.add_parser('pack');pack_parser.add_argument('source',type=Path);pack_parser.add_argument('output',type=Path)
    pack_parser.add_argument('--patch',action=argparse.BooleanOptionalAction,default=True,
                             help='default: flat patch.xp3 with changed members only; --no-patch writes the full verification scenario.xp3')
    pack_parser.add_argument('--patch-filter',choices=PATCH_FILTERS,default='same',
                             help='same: reuse the source filter spec/format (default); none: unfiltered standard XP3')
    args=parser.parse_args()
    report=(extract(args.source,args.output,archives=args.archives,overlay=args.overlay,archive_profile=args.archive_profile,
                    output_format=args.output_format,verify_edits=args.verify_edits,language_index=args.language_index,filter_spec=load_json(read_file(args.filter_spec)) if args.filter_spec else None,
                    speaker_name=args.speaker_name) if args.command=='extract' else pack(args.source,args.output,incremental=args.patch,patch_filter=args.patch_filter))
    print(json.dumps(report.get('totals',report),ensure_ascii=True,indent=2))


if __name__=='__main__':main()
