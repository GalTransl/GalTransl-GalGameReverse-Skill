"""Static Hxv4 index + candidate-name verification CLI. No game execution.

Writes new evidence directory only; does not rename extracted/game files.
"""
import argparse
from collections import defaultdict
import hashlib
import json
import zlib
from pathlib import Path
from python.archives.kirikiri_hxv4 import derive,read_index,name_hash,path_hash
from python.archives.kirikiri_hxv4_static import candidates
from python.archives import kirikiri_xp3
from python.common.safety import write_new_tree,Limits,validate_names


def resolve(entries,names,paths=('',)):
    nm=defaultdict(set);pm=defaultdict(set)
    for name in names:
        validate_names([name]);nm[name_hash(name)].add(name)
    for path in paths:
        if path:validate_names([path])
        pm[path_hash(path)].add(path)
    result=[]
    for e in entries:
        item={k:v for k,v in e.items() if k!='key'}
        for key,mapping,field in (('name_hash',nm,'name'),('path_hash',pm,'path')):
            values=mapping.get(e.get(key),set())
            if len({v.lower() for v in values})==1:item[field]=sorted(values)[0]
            elif values:item[field+'_ambiguous']=sorted(values)
        result.append(item)
    return result


def inspect(archive,exe,names,paths=('',)):
    exe=Path(exe);archive=Path(archive)
    if exe.stat().st_size>32<<20:raise ValueError('EXE budget')
    raw=exe.read_bytes();packages=candidates(raw);accepted=[]
    for package in packages:
        try:
            with archive.open('rb') as stream:r=read_index(stream,derive(package))
            accepted.append((package,r))
        except (ValueError,UnicodeError,zlib.error):continue
    unique={json.dumps(p,sort_keys=True):(p,r) for p,r in accepted}
    if len(unique)!=1:raise ValueError('need one uniquely validated static key candidate')
    package,r=next(iter(unique.values()));entries=resolve(r['files'],names,paths)
    with archive.open('rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
    report={'schema':'kirikiri-hxv4-name-evidence/1','archive':archive.name,'source_sha256':sha,
            'exe':exe.name,'exe_sha256':hashlib.sha256(raw).hexdigest(),'key_package':package,
            'index_entries':len(entries),'index_mapped':r['mapped'],'names_resolved':sum('name' in e for e in entries),
            'paths_resolved':sum('path' in e for e in entries),'entries':entries,
            'validation':'Static PE resources -> BRES -> candidate config -> ChaCha/zlib -> bounded Hx object -> exact candidate hashes',
            'payload_decryption_verified':False,'runtime_used':False}
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path);parser.add_argument('--exe',required=True,type=Path)
    parser.add_argument('--names',action='append',type=Path,default=[],help='BOM-aware UTF-8/UTF-16 candidate filenames, one per line; supplied hashes are not trusted')
    parser.add_argument('--candidate-archive',action='append',type=Path,default=[],help='standard/eliF XP3 whose index contains plaintext candidate names')
    parser.add_argument('--paths',nargs='*',default=['']);parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();names=set();sources=[]
    for path in args.names:
        if path.stat().st_size>8<<20:raise ValueError('candidate text budget')
        raw=path.read_bytes();encoding='utf-16' if raw[:2] in (b'\xff\xfe',b'\xfe\xff') else 'utf-8-sig'
        names.update(s for s in raw.decode(encoding).splitlines() if s)
        sources.append({'path':str(path),'sha256':hashlib.sha256(raw).hexdigest(),'use':'names only'})
    for path in args.candidate_archive:
        with path.open('rb') as stream:
            _,entries=kirikiri_xp3.read_index(stream);names.update(e.name.rsplit('/',1)[-1] for e in entries)
            stream.seek(0);sha=hashlib.file_digest(stream,'sha256').hexdigest()
        sources.append({'path':str(path),'sha256':sha,'use':'index names only; payloads not used'})
    if len(names)>100000:raise ValueError('name candidate budget')
    report=inspect(args.archive,args.exe,names,args.paths);report['candidate_sources']=sources
    matches=set()
    for e in report['entries']:
        for field in ('name','path'):
            if field in e:matches.add(e[field+'_hash']+':'+e[field])
    write_new_tree(args.output,[('report.json',(json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode('utf-8')),
                                ('HxNames.lst',('\n'.join(sorted(matches))+'\n').encode('utf-8'))],Limits())
    print(json.dumps({k:v for k,v in report.items() if k not in ('entries','key_package','candidate_sources')},ensure_ascii=True,indent=2))


if __name__=='__main__':main()
