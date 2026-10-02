"""Read-only, bounded Kirikiri archive/filter/inner-format evidence CLI.

No game-name dispatch, script execution, deployment or automatic key adoption.
"""
import argparse
from collections import Counter
import fnmatch
import hashlib
import io
import json
from pathlib import Path
import struct
import zlib

from python.archives import kirikiri_xp3 as xp3
from python.archives.xp3 import _inflate
from .kirikiri_psb import Psb
from .kirikiri_kag import decode, tokenize


def png_valid(data):
    if data[:8]!=b'\x89PNG\r\n\x1a\n':return False
    at=8;first=True
    while at+12<=len(data):
        size,=struct.unpack_from('>I',data,at);end=at+12+size
        if end>len(data):return False
        tag=data[at+4:at+8];body=data[at+4:end-4]
        if first and (tag!=b'IHDR' or size!=13):return False
        if zlib.crc32(body)&0xffffffff!=struct.unpack_from('>I',data,end-4)[0]:return False
        if tag==b'IEND':return size==0 and end==len(data)
        at=end;first=False
    return False


def classify(data):
    if data.startswith(b'PSB\0'):
        psb=Psb(data);root=psb.object(psb.root)
        return {'kind':'psb','version':psb.version,'root_keys':list(root),'validation':'bounded-tree'}
    if data.startswith(b'TJS2'):
        return {'kind':'tjs-bytecode','validation':'signature-only','writable':False}
    if data.startswith(b'\x89PNG'):
        if not png_valid(data):raise ValueError('PNG chunk CRC/layout mismatch')
        return {'kind':'png','validation':'chunk-crc-layout'}
    text,encoding,bom=decode(data);tokens=tokenize(text)
    kinds=Counter(t.kind for t in tokens)
    if not (kinds['label'] or kinds['command'] or kinds['tag']):
        return {'kind':'bom-text','encoding':encoding,'validation':'strict-decode','writable':False}
    return {'kind':'kag-text','encoding':encoding,'validation':'lossless-lexical',
            'tokens':dict(kinds),'dialogue_export_verified':False}


def recover_akabei(stream,entries):
    """PNG known-prefix candidate, confirmed by >=2 independent full CRCs/checksums.

    Uses at most 8 images of <=8 MiB each. Seed bit31 is unobservable in Akabei.
    """
    evidence={};tried=0
    for entry in entries:
        if not entry.name.lower().endswith('.png') or not entry.flags or not 8<=entry.size<=8<<20:continue
        if tried>=8:break
        tried+=1;parts=[]
        for flag,at,raw,packed in entry.segments:
            if packed>8<<20:raise ValueError('PNG candidate packed budget')
            stream.seek(at);part=stream.read(packed)
            if len(part)!=packed:raise ValueError('truncated PNG candidate')
            parts.append(_inflate(part,raw,8<<20) if flag else part)
        encrypted=b''.join(parts)
        first=int.from_bytes(bytes(a^b for a,b in zip(encrypted[:4],b'\x89PNG')),'little')
        seed=(first^entry.checksum)&0x7fffffff
        spec={'algorithm':'akabei','seed':seed}
        try:plain=xp3.read_member(stream,entry,'plain',spec)
        except ValueError:continue
        if png_valid(plain):evidence.setdefault(seed,{}).setdefault(hashlib.sha256(plain).hexdigest(),entry.name)
    return [{'filter_spec':{'algorithm':'akabei','seed':seed},'evidence_members':list(names.values()),
             'seed_bit31_ignored_by_algorithm':True}
            for seed,names in evidence.items() if len(names)>=2]


def probe(archive, *, patterns=('*.scn','*.ks'), filter_spec=None, recover=False,
          verify_repack=False, max_members=512, max_total=64<<20):
    if filter_spec is not None:filter_spec=xp3.validate(filter_spec)
    with Path(archive).open('rb') as stream:
        profile,entries=xp3.read_index(stream)
        selected=[e for e in entries if any(fnmatch.fnmatchcase(e.name,p) for p in patterns)]
        if len(selected)>max_members or sum(e.size for e in selected)>max_total:raise ValueError('probe selection budget; narrow --members')
        report={'schema':'kirikiri-probe/1','archive':Path(archive).name,'index_profile':profile,
                'index_is_not_filter_evidence':True,'entries':len(entries),'selected':len(selected),
                'filter_spec':filter_spec,'members':[]}
        if recover:
            if profile!='plain':raise ValueError('Akabei recovery currently requires standard File index')
            report['candidates']=recover_akabei(stream,entries)
        files=[]
        for entry in selected:
            item={'name':entry.name,'size':entry.size,'flags':entry.flags}
            try:
                raw=xp3.read_member(stream,entry,profile,filter_spec)
                item['plaintext_checksum']='passed';item['sha256']=hashlib.sha256(raw).hexdigest()
                files.append((entry.name,raw))
                try:item['inner']=classify(raw)
                except (ValueError,UnicodeError) as ex:item['inner']={'kind':'unclassified','error':str(ex)}
            except (ValueError,zlib.error) as ex:item['error']=str(ex)
            report['members'].append(item)
        report['checksum_passed']=len(files)
        if verify_repack:
            if not files or len(files)!=len(selected):raise ValueError('cannot repack incomplete selection')
            packed=xp3.build(files,profile,filter_spec);test=io.BytesIO(packed);detected,rebuilt=xp3.read_index(test,profile)
            if [e.name for e in rebuilt]!=[n for n,d in files]:raise ValueError('repack member mapping')
            for e,(name,wanted) in zip(rebuilt,files):
                if xp3.read_member(test,e,detected,filter_spec)!=wanted:raise ValueError('repack content mismatch')
            report['archive_roundtrip']={'members':len(files),'bytes':len(packed),'sha256':hashlib.sha256(packed).hexdigest(),
                                         'scope':'archive bytes only; no semantic text edits'}
        stream.seek(0);report['source_sha256']=hashlib.file_digest(stream,'sha256').hexdigest()
        return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path);parser.add_argument('--members',nargs='+',default=['*.scn','*.ks'])
    parser.add_argument('--filter-spec',type=Path);parser.add_argument('--recover-akabei-png',action='store_true')
    parser.add_argument('--verify-repack',action='store_true')
    args=parser.parse_args()
    spec=None
    if args.filter_spec:
        if args.filter_spec.stat().st_size>4096:raise ValueError('filter spec budget')
        spec=json.loads(args.filter_spec.read_text(encoding='utf-8'))
    result=probe(args.archive,patterns=args.members,filter_spec=spec,recover=args.recover_akabei_png,verify_repack=args.verify_repack)
    print(json.dumps(result,ensure_ascii=True,indent=2))


if __name__=='__main__':main()
