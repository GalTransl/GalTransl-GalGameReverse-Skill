# SPDX-License-Identifier: GPL-3.0-only
"""SystemC UTF-8 TXD/PTR workspace; only new output trees, no installation."""
import argparse
from pathlib import Path
from ..archives.systemc import unpack_fpk,rebuild_fpk,read_fpk_index
from ..common.contract import dump_rows,load_json,sha256
from ..common.handoff import STATE_FILE,handoff
from ..common.safety import write_new_tree, logical_path, validate_new_tree_destination
from .systemc_extract import _read,_json,_verify_archive
from .systemc_txd import VARIANT,export_table,inject_table


def stems(members):
    result=sorted(n[:-4] for n in members if n.endswith('_JA.TXD'))
    if not result:raise ValueError('no Japanese TXD/PTR tables')
    return result


def extract(game,output,*,verify_edits=False,references=()):
    game,output=Path(game),Path(output)
    validate_new_tree_destination(output)
    raw=_read(game/'data.fpk');index,members=unpack_fpk(raw)
    files=[('original/data.fpk',raw),('gt_output/.keep',b'')]
    files.extend((f'original/members/{n}',v) for n,v in members.items())
    report={'variant':VARIANT,'source_sha256':sha256(raw),'members':len(members),
            'tables':[],'rows':0,'names':0,'choices':0,'runtime_verified':False,'references':[]}
    rebuilt=dict(members);edited=dict(members)
    for stem in stems(members):
        rows,manifest=export_table(stem,members)
        updated=inject_table(stem,members,rows,manifest)
        if any(v!=members[n] for n,v in updated.items()):raise ValueError('table original roundtrip differs')
        rebuilt.update(updated)
        rec={'stem':stem,'rows':len(rows),'status':'exported' if rows else 'empty',
             'unreferenced_ids':manifest['settings']['unreferenced_ids'],
             'source_indent_omitted_ids':manifest['settings']['source_indent_omitted_ids']}
        report['tables'].append(rec);report['rows']+=len(rows)
        report['names']+=sum('name'in r for r in rows)
        report['choices']+=sum(r['locator']['kind']=='choice' for r in manifest['records'])
        if rows:
            files.extend([(f'gt_input/{stem}.json',dump_rows(rows)),(f'metadata/{stem}.json',_json(manifest))])
        if verify_edits and rows:
            changed=[dict(r,message='验证'+r['message']) for r in rows]
            if 'name'in changed[0]:changed[0]['name']+='验证'
            edited.update(inject_table(stem,members,changed,manifest))
    packed=rebuild_fpk(raw,rebuilt);_verify_archive(packed,rebuilt)
    if packed!=raw:raise ValueError('original archive roundtrip differs')
    files.append(('rebuilt/roundtrip/data.fpk',packed))
    report['archive_roundtrip_identical']=True
    if verify_edits:
        smoke=rebuild_fpk(raw,edited);_verify_archive(smoke,edited)
        files.append(('rebuilt/smoke-test/data.fpk',smoke))
        changed_members=[n for n in members if members[n]!=edited[n]]
        if any(not n.endswith(('.TXD','.PTR')) for n in changed_members):raise ValueError('non-table member changed')
        report['smoke']={'changed_rows':report['rows'],'changed_members':changed_members,
                         'size':len(smoke),'sha256':sha256(smoke),'reextracted_all_members':True}
    for name in references:
        name=logical_path(name);data=_read(game/name);idx=read_fpk_index(data)
        report['references'].append({'path':name,'sha256':sha256(data),'same_as_data_fpk':data==raw,
            'member_count':len(idx.entries),'text_table_members':[e.name for e in idx.entries if e.name.endswith(('.TXD','.PTR','.spt','.DAT'))]})
    if _read(game/'data.fpk')!=raw:raise ValueError('input changed during extraction')
    exported=[t['stem']+'.json' for t in report['tables'] if t['rows']]
    notes=['每条正文的换行可以比原文少，不能新增','保持 $S/$L/$M 字号控制码和 &heart; 等符号的顺序与数量',
           '姓名可翻译，不能含半角逗号']
    if len(report['tables'])>len(exported):notes.append(f"{len(report['tables'])-len(exported)} 个文本表没有对白，未生成 JSON")
    report['delivery'],state=handoff(
        workspace=output,engine='SystemC（FPK 内 UTF-8 TXD/PTR 文本表）',json_files=len(exported),rows=report['rows'],
        notes=notes,verified='全部 TXD/PTR 与整包 data.fpk 经 writer 重建后字节一致',edit_checked=verify_edits,
        first_json=exported[0] if exported else None,first_json_basis='按名称排序的第一个文本表，未确认是否为开场',
        command='extract --verify-edits' if verify_edits else 'extract')
    files.extend([('reports/extraction.json',_json(report)),(STATE_FILE,state)])
    write_new_tree(output,files)
    return report


def pack(workspace,output):
    workspace,output=Path(workspace),Path(output)
    validate_new_tree_destination(output)
    report=load_json(_read(workspace/'reports/extraction.json'))
    raw=_read(workspace/'original/data.fpk')
    if report['variant']!=VARIANT or sha256(raw)!=report['source_sha256']:raise ValueError('workspace/source identity changed')
    _,members=unpack_fpk(raw);rewritten=dict(members);expected=set();used=[]
    for name,data in members.items():
        if _read(workspace/'original/members'/name)!=data:raise ValueError('decoded source snapshot changed')
    for stem in stems(members):
        rows,manifest=export_table(stem,members)
        if not rows:continue
        filename=stem+'.json';expected.add(filename)
        if load_json(_read(workspace/'gt_input'/filename))!=rows or load_json(_read(workspace/'metadata'/filename))!=manifest:
            raise ValueError('original JSON/manifest changed')
        path=workspace/'gt_output'/filename
        if path.exists():
            rewritten.update(inject_table(stem,members,load_json(_read(path)),manifest));used.append(filename)
    if {p.name for p in (workspace/'gt_output').glob('*.json')}-expected:raise ValueError('unknown translation filenames')
    packed=rebuild_fpk(raw,rewritten);_verify_archive(packed,rewritten)
    result={'variant':VARIANT,'translated_files':used,'sha256':sha256(packed),'runtime_verified':False}
    write_new_tree(output,[('data.fpk',packed),('verification.json',_json(result))])
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    ex=sub.add_parser('extract');ex.add_argument('game');ex.add_argument('--output',required=True)
    ex.add_argument('--verify-edits',action='store_true');ex.add_argument('--reference',action='append',default=[])
    pk=sub.add_parser('pack');pk.add_argument('workspace');pk.add_argument('--output',required=True)
    a=p.parse_args()
    r=extract(a.game,a.output,verify_edits=a.verify_edits,references=a.reference) if a.command=='extract' else pack(a.workspace,a.output)
    print(_json({k:v for k,v in r.items() if k not in ('tables','references')}).decode('utf-8'))


if __name__=='__main__':main()
