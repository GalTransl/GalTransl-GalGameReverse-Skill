# SPDX-License-Identifier: GPL-3.0-only
"""SystemC Mamakano UTF-8 TXD/PTR with ACT/DAT/SPT identity evidence.

New implementation based on actual file structure. Runtime tables are edited;
source ACT line numbers and compiled SPT/voice/control records stay unchanged.
"""
import re
import struct
from ..common.binary import FormatError
from ..common.contract import make_manifest, validate_translation

VARIANT = 'mamakano-utf8-txd-ptr12'
TOKENS = re.compile(r'\\n|\$[A-Za-z]+|&[A-Za-z]+;')
ALLOWED = {'\\n', '$S', '$L', '$M', '&heart;', '&aseri;', '&ikari;', '&namida;',
           '&nakigao;', '&kirari;', '&egao;', '&kaminari;', '&dokuro;'}
OPCODES = {1,2,3,4,7,8,10,11,12,13,15,18,19,20,22,24,26,29,33,34,35,36,37,38,40,41,42}


def read_table(txd, ptr):
    if len(ptr) < 16 or ptr[:4] != b'PTR ' or max(len(txd),len(ptr)) > 64 << 20:
        raise FormatError('invalid TXD/PTR header/budget')
    count = struct.unpack_from('<I',ptr,4)[0]
    if count > 100000 or len(ptr) != 16 + count * 12:
        raise FormatError('PTR record count mismatch')
    records = list(struct.iter_unpack('<III',ptr[16:]));rows=[];cursor=0;seen=set()
    for identity,offset,size in records:
        if identity in seen or offset != cursor or not size or offset+size>len(txd):
            raise FormatError('duplicate ID or invalid/overlapping TXD span')
        seen.add(identity);cursor+=size
        value=txd[offset:offset+size].decode('utf-8','strict')
        if ',' not in value or any(ord(c)<32 for c in value):
            raise FormatError('invalid name,message TXD record')
        name,message=value.split(',',1)
        row={'message':message.replace('\\n','\n')}
        if name:row['name']=name
        if set(TOKENS.findall(value))-ALLOWED:
            raise FormatError('unknown SystemC display token')
        if re.search(r'[\\$&]',TOKENS.sub('',value)):
            raise FormatError('unrecognized SystemC control syntax')
        rows.append(row)
    if cursor!=len(txd):raise FormatError('unreferenced TXD bytes')
    return records,rows


def records(data,width):
    if len(data)<4 or len(data)>64<<20:raise FormatError('invalid compiled table size')
    count=struct.unpack_from('<I',data)[0]
    if count>100000 or len(data)!=4+count*width:raise FormatError('compiled record count mismatch')
    return [data[i:i+width] for i in range(4,len(data),width)]


def export_table(stem,members):
    if not re.fullmatch(r'ACT_[A-Z]_JA',stem):raise FormatError('unsupported table name/language')
    act=stem[:-3];names=(stem+'.TXD',stem+'.PTR',act+'.txt',act+'.DAT','charaid.tbl')
    if any(n not in members for n in names):raise FormatError('missing ACT/DAT/TXD/PTR/character companion')
    sources={n:members[n] for n in names}
    ptr,rows=read_table(sources[names[0]],sources[names[1]])
    by_id={p[0]:(i,r) for i,(p,r) in enumerate(zip(ptr,rows))}
    lines=sources[act+'.txt'].decode('utf-8').split('\r\n')
    if any('\r' in line or '\n' in line for line in lines):raise FormatError('mixed ACT line endings')
    charlines=sources['charaid.tbl'].decode('utf-8').splitlines()
    chars=[line.rsplit(' ',1)[0] for line in charlines if line and not line.startswith('//')]
    labels=[i for i,line in enumerate(lines) if line.lstrip(' \t').startswith('***')]
    dat=records(sources[act+'.DAT'],156)
    if len(labels)!=len(dat):raise FormatError('ACT/DAT section count mismatch')
    refs={};trimmed=[]
    for section,record in enumerate(dat):
        start,end,route,scene,block=struct.unpack_from('<5i',record,80)
        if not 0<=route<26 or not 0<=start<=end<len(lines) or start!=labels[section]+1:
            raise FormatError('DAT section bounds mismatch')
        match=re.match(r'^\*\*\*(SC|SS)_([A-Z])(\d+)_(\d+)',lines[start-1].lstrip(' \t'))
        if not match or (match[2],int(match[3]),int(match[4]))!=(chr(65+route),scene,block):
            raise FormatError('DAT scene identity mismatch')
        spt=f'{chr(65+route)}{scene:04d}_{block:02d}.spt'
        if spt not in members:raise FormatError('missing SPT')
        sources[spt]=members[spt]
        for number,raw in enumerate(records(members[spt],32)):
            op,char,voice,res,first,count,category,identity=struct.unpack('<8i',raw)
            if op not in OPCODES:raise FormatError(f'unknown SPT opcode {op}')
            if op!=1:continue
            if res!=-1 or category!=7 or not 0<char<=len(chars) or count<1 or first<start or first+count>end:
                raise FormatError('invalid text instruction range/shape')
            if identity not in by_id or identity in refs:raise FormatError('missing or multiply referenced text ID')
            position,row=by_id[identity];part=lines[first:first+count]
            marker=re.search(r'\[(\d+)\]$',part[0])
            if not marker or int(marker[1])!=identity:raise FormatError('ACT marker disagrees with SPT ID')
            part[0]=part[0][:marker.start()]
            header=re.match(r'^(.+?)　（([０-９]+)）',part[0])
            expected={}
            if header:
                if int(header[2])!=voice:raise FormatError('ACT voice identity mismatch')
                expected['name']=header[1];part=part[1:]
            elif voice or chars[char-1]!='ナレーション':raise FormatError('missing speaker header')
            expected['message']='\n'.join(part)
            if expected!=row:
                # Three source lines contain a leading ideographic indent which
                # the runtime table omits. Record it; do not normalize TXD text.
                if expected.get('name')!=row.get('name') or expected['message'].lstrip('　')!=row['message']:
                    raise FormatError(f'ACT/TXD text mismatch at {stem} ID {identity}')
                trimmed.append(identity)
            refs[identity]={'table_position':position,'text_id':identity,'spt':spt,'record':number,
                            'act_line':first,'kind':'choice' if match[1]=='SS' else 'message'}
    active=[(p,r,refs[p[0]]) for p,r in zip(ptr,rows) if p[0] in refs]
    exported=[r for _,r,_ in active]
    manifest=make_manifest(engine='systemc',variant=VARIANT,reference='systemc_txd/1',sources=sources,
        rows=exported,locators=[loc for _,_,loc in active],encoding='utf-8',
        name_policies=['writable' if 'name' in r else 'absent' for r in exported],
        settings={'stem':stem,'unreferenced_ids':[p[0] for p in ptr if p[0] not in refs],
                  'source_indent_omitted_ids':trimmed,'source_ACT_is_not_runtime_text':True})
    return exported,manifest


def inject_table(stem,members,translated,manifest):
    rows,expected=export_table(stem,members)
    if manifest!=expected:raise FormatError('manifest differs from reparsed companions')
    sources={item['path']:members[item['path']] for item in manifest['sources']}
    translated=validate_translation(manifest,sources,rows,translated)
    ptr,all_rows=read_table(members[stem+'.TXD'],members[stem+'.PTR'])
    changes={}
    for before,after,record in zip(rows,translated,manifest['records']):
        for field in before:
            old=before[field].replace('\n','\\n');new=after[field].replace('\n','\\n')
            if TOKENS.findall(old)!=TOKENS.findall(new):raise FormatError('ordered display controls changed')
            if re.search(r'[\\$&]',TOKENS.sub('',new)) or any(ord(c)<32 for c in new):raise FormatError('unknown control or literal newline')
        if 'name' in after and (not after['name'] or any(c in after['name'] for c in ',\n')):
            raise FormatError('invalid name delimiter')
        changes[record['locator']['table_position']]=after
    txd=bytearray();new_ptr=bytearray(members[stem+'.PTR'][:16])
    for i,(identity,offset,size) in enumerate(ptr):
        row=changes.get(i,all_rows[i])
        if row==all_rows[i]:raw=members[stem+'.TXD'][offset:offset+size]
        else:raw=(row.get('name','')+','+row['message'].replace('\n','\\n')).encode('utf-8','strict')
        if len(raw)>1<<20 or len(txd)+len(raw)>64<<20:raise FormatError('TXD output budget exceeded')
        new_ptr.extend(struct.pack('<III',identity,len(txd),len(raw)));txd.extend(raw)
    actual_ptr,actual_rows=read_table(bytes(txd),bytes(new_ptr))
    if [p[0] for p in actual_ptr]!=[p[0] for p in ptr] or actual_rows!=[changes.get(i,r) for i,r in enumerate(all_rows)]:
        raise FormatError('rewritten table mismatch')
    return {stem+'.TXD':bytes(txd),stem+'.PTR':bytes(new_ptr)}
