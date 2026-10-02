"""Selected XP3 KAG scripts -> GalTransl workspace -> verified script-only XP3.

Explicit archive/member selection and filter parameters; no game-name dispatch.
Uses the Alter nm/np/exlink dialect, not the PSB/SCN writer.
"""
import argparse
import fnmatch
import hashlib
from pathlib import Path

from python.archives import kirikiri_xp3 as xp3
from python.common.contract import dump_rows, load_json, sha256
from python.common.safety import Limits, validate_names, write_new_tree
from .kirikiri_extract import read_file, js, verify_archive
from .kirikiri_kag_text import PROFILE, export_script, rebuild_script


def extract(game,output,*,archives,patterns=('scenario/*.ks',),filter_spec=None):
    game,output=Path(game),Path(output)
    if output.exists():raise FileExistsError(output)
    if filter_spec is not None:filter_spec=xp3.validate(filter_spec)
    names=validate_names(list(archives)); selected={}; sources=[];total=0
    for name in names:
        with (game/name).open('rb') as f:
            profile,entries=xp3.read_index(f)
            for entry in entries:
                if not any(fnmatch.fnmatchcase(entry.name,pattern) for pattern in patterns):continue
                if not entry.name.lower().endswith('.ks'):raise ValueError('KAG selection includes non-KS member')
                total+=entry.size
                if total>128<<20:raise ValueError('KAG selection exceeds budget')
                if entry.name in selected:raise ValueError('ambiguous archive overlay; select explicitly')
                selected[entry.name]=(name,xp3.read_member(f,entry,profile,filter_spec))
            f.seek(0);sources.append({'name':name,'sha256':hashlib.file_digest(f,'sha256').hexdigest()})
    validate_names(list(selected))
    flats=validate_names([Path(n).stem+'.json' for n in selected])
    if not selected:raise ValueError('no selected KAG scripts')
    payloads=[('gt_output/.keep',b'')];exports=[];originals=[];smokes=[];counts={'files':0,'rows':0,'choices':0,'named':0}
    for (name,(archive,raw)),flat in zip(selected.items(),flats):
        try:
            rows,meta=export_script(raw)
            if rebuild_script(raw,rows,meta)!=raw:raise ValueError('KAG original roundtrip differs')
            changed=[dict(r,message='验证'+r['message']) for r in rows]
            smoke=rebuild_script(raw,changed,meta)
        except ValueError as exc:raise ValueError(f'{archive}:{name}: {exc}') from exc
        payloads.append(('original/'+name,raw));originals.append((name,raw));smokes.append((name,smoke))
        exports.append({'member':name,'archive':archive,'json':flat if rows else None,'rows':len(rows),'sha256':sha256(raw)})
        if rows:
            payloads.extend([('gt_input/'+flat,dump_rows(rows)),('metadata/'+flat,js(meta))])
            counts['files']+=1;counts['rows']+=len(rows)
            counts['choices']+=sum(r['locator']['kind']=='choice' for r in meta['records'])
            counts['named']+=sum('name' in r for r in rows)
    reports={}
    for stage,files in [('roundtrip',originals),('smoke-test',smokes)]:
        packed=xp3.build(files,'plain',filter_spec);verify_archive(packed,files,'plain',filter_spec)
        payloads.append(('rebuilt/'+stage+'/scenario.xp3',packed))
        reports[stage]={'sha256':sha256(packed),'bytes':len(packed),'all_members_readback_equal':True}
    report={'profile':PROFILE,'archives':sources,'filter_spec':filter_spec,'exports':exports,'counts':counts,
            'validation':reports,'original_scripts_byte_identical':True,'runtime_verified':False,
            'scope':'Only selected KAG scenario scripts. System macros/UI and preexisting loose translations are excluded.',
            'deployment':'Script-only archives; original full archives must not be replaced with these. Patch mounting/priority needs runtime verification.'}
    payloads.append(('reports/extraction.json',js(report)))
    write_new_tree(output,payloads,Limits(max_file_bytes=128<<20,max_total_bytes=384<<20))
    return report


def pack(workspace,output,*,flat=False):
    workspace,output=Path(workspace),Path(output)
    if output.exists():raise FileExistsError(output)
    report=load_json(read_file(workspace/'reports/extraction.json'))
    if report['profile']!=PROFILE:raise ValueError('unsupported KAG workspace')
    exports=report['exports'];expected={e['json'] for e in exports if e['json']}
    validate_names([e['member'] for e in exports]);validate_names(list(expected))
    for folder in ('gt_input','metadata'):
        if {p.name for p in (workspace/folder).glob('*.json')}!=expected:raise ValueError('KAG source JSON set changed')
    if {p.name for p in (workspace/'gt_output').glob('*.json')}-expected:raise ValueError('unknown translation filename')
    files=[];changed=[];total=0
    for e in exports:
        raw=read_file(workspace/'original'/e['member']);total+=len(raw)
        if total>128<<20 or sha256(raw)!=e['sha256']:raise ValueError('KAG source budget/hash mismatch')
        rows,meta=export_script(raw);rewritten=raw
        if rows:
            name=e['json']
            if load_json(read_file(workspace/'gt_input'/name))!=rows or load_json(read_file(workspace/'metadata'/name))!=meta:
                raise ValueError('KAG original JSON/manifest changed')
            path=workspace/'gt_output'/name
            after=load_json(read_file(path)) if path.exists() else rows
            rewritten=rebuild_script(raw,after,meta)
        elif e['json'] is not None:raise ValueError('empty KAG source mapping changed')
        if rewritten!=raw:changed.append(e['member'])
        files.append((Path(e['member']).name if flat else e['member'],rewritten))
    validate_names([n for n,_ in files])
    packed=xp3.build(files,'plain',report['filter_spec']);verify_archive(packed,files,'plain',report['filter_spec'])
    result={'profile':PROFILE,'members':len(files),'changed_members':changed,'flat':flat,
            'sha256':sha256(packed),'runtime_verified':False,'all_members_readback_equal':True}
    write_new_tree(output,[('patch.xp3' if flat else 'scenario.xp3',packed),('verification.json',js(result))],
                   Limits(max_file_bytes=128<<20,max_total_bytes=256<<20))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    ex=sub.add_parser('extract');ex.add_argument('game');ex.add_argument('output')
    ex.add_argument('--archives',nargs='+',required=True);ex.add_argument('--members',nargs='+',default=['scenario/*.ks'])
    ex.add_argument('--filter-spec',type=Path)
    pk=sub.add_parser('pack');pk.add_argument('workspace');pk.add_argument('output');pk.add_argument('--flat',action='store_true')
    a=parser.parse_args()
    if a.command=='extract':
        result=extract(a.game,a.output,archives=a.archives,patterns=a.members,
                       filter_spec=load_json(read_file(a.filter_spec)) if a.filter_spec else None)
        print(js(result['counts']).decode('utf-8'))
    else:print(js(pack(a.workspace,a.output,flat=a.flat)).decode('utf-8'))


if __name__=='__main__':main()
