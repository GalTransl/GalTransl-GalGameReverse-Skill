"""Bounded XP3 with eliF filename mapping; plaintext member reader/writer.

LOVEREC's data.xp3 marks SCN as encrypted but the sampled payloads are plain.
Flagged plaintext requires explicit opt-in, full Adler-32 and inner parsing.
No cipher is guessed or applied. Mapping
layout: GARbro-Mod ArcFormats/KiriKiri/ArcXP3.cs (MIT, morkt, 2014-2017).
Full MIT notice is included in the adjacent xp3.py. Independent Python writer.
"""
from dataclasses import dataclass
import hashlib
import struct
import zlib
from .xp3 import MAGIC, _chunks, _inflate
from python.common.safety import validate_names


@dataclass(frozen=True)
class Entry:
    ordinal: int
    name: str
    alias: str
    checksum: int
    flags: int
    size: int
    segments: tuple
    issue: str | None = None


def read_index(stream, *, max_index=16 << 20):
    stream.seek(0,2); total=stream.tell()
    def read(at,size):
        if at<0 or size<0 or at+size>total or size>max_index: raise ValueError('eliF XP3 metadata bounds')
        stream.seek(at);value=stream.read(size)
        if len(value)!=size: raise ValueError('truncated XP3 metadata')
        return value
    if read(0,11)!=MAGIC:raise ValueError('not XP3')
    at,=struct.unpack('<Q',read(11,8))
    if at<19:raise ValueError('XP3 index overlaps header')
    if read(at,9)==b'\x80'+b'\0'*8:at,=struct.unpack('<Q',read(at+9,8))
    flag=read(at,1)[0]
    if flag==1:
        pk,size=struct.unpack('<QQ',read(at+1,16));index=_inflate(read(at+17,pk),size,max_index);index_end=at+17+pk
    elif flag==0:
        size,=struct.unpack('<Q',read(at+1,8));index=read(at+9,size);index_end=at+9+size
    else:raise ValueError('unsupported XP3 index flag')
    chunks=list(_chunks(index));mapping={};hashes={};entries=[]
    for tag,value in chunks:
        if tag==b'eliF':
            if len(value)<8:raise ValueError('short eliF mapping')
            checksum,units=struct.unpack_from('<IH',value)
            if not units or units>4096 or len(value)!=8+units*2 or value[-2:]!=b'\0\0':raise ValueError('invalid eliF mapping')
            name=value[6:-2].decode('utf-16le');alias=hashlib.md5(name.lower().encode('utf-16le')).hexdigest()
            if alias in mapping and mapping[alias]!=(checksum,name):raise ValueError('conflicting eliF mapping')
            mapping[alias]=(checksum,name);hashes.setdefault(checksum,set()).add(name)
        elif tag!=b'File':raise ValueError('unknown eliF XP3 record')
    for tag,value in chunks:
        if tag!=b'File':continue
        parts=list(_chunks(value));fields=dict(parts)
        if len(parts)!=len(fields) or set(fields)-{b'info',b'segm',b'adlr',b'time'}:raise ValueError('unknown/duplicate XP3 fields')
        if not {b'info',b'segm',b'adlr'}<=set(fields):raise ValueError('missing XP3 fields')
        checksum,=struct.unpack('<I',fields[b'adlr']);info=fields[b'info']
        flags,size,packed,units=struct.unpack_from('<IQQH',info);alias=info[22:22+units*2].decode('utf-16le')
        segments=tuple(struct.iter_unpack('<IQQQ',fields[b'segm']))
        if checksum==0x689792e4 and alias.startswith('$$$') and segments==((0,88,157,157),):
            if read(40,7)!=b'\x89PNG\n\x1a\n':raise ValueError('unknown security stub')
            continue
        if flags not in (0,0x80000000) or not units or units>4096:raise ValueError('unknown XP3 info flags/name')
        if len(info)!=22+units*2 and not (len(info)==24+units*2 and info[-2:]==b'\0\0'):raise ValueError('XP3 name size')
        name=alias
        if alias in mapping:
            h,name=mapping[alias]
            if h!=checksum:raise ValueError('eliF identity mismatch')
        elif alias in hashes.get(checksum,set()):pass
        elif len(hashes.get(checksum,set()))==1:name=next(iter(hashes[checksum]))
        if not segments or sum(s[2] for s in segments)!=size or sum(s[3] for s in segments)!=packed:raise ValueError('XP3 segment totals')
        issue = None
        for flag,offset,raw,stored in segments:
            if offset < 19:
                if name=='!scnlist.txt' and checksum==0x34d0bac8 and segments==((0,13,7268,7268),) and flags==0:
                    issue='known converted !scnlist.txt overlaps header; unreadable, not repaired'
                else:raise ValueError('XP3 segment overlaps header')
            if flag not in (0,1) or offset+stored>total or (stored and offset<index_end and offset+stored>at):raise ValueError('XP3 segment range')
            if flag==0 and raw!=stored:raise ValueError('plain segment sizes')
        validate_names([name])
        entries.append(Entry(len(entries),name,alias,checksum,flags,size,segments,issue))
    return entries


def read_member(stream,entry,*,max_size=32<<20,marked_plaintext=False):
    if entry.issue:raise ValueError(entry.issue)
    if entry.flags and not marked_plaintext:raise ValueError('flagged member requires a verified filter profile')
    if entry.size>max_size:raise ValueError('XP3 member budget')
    parts=[]
    for flag,offset,raw,packed in entry.segments:
        if packed>max_size:raise ValueError('XP3 stored member budget')
        stream.seek(offset);value=stream.read(packed)
        if len(value)!=packed:raise ValueError('truncated XP3 member')
        parts.append(_inflate(value,raw,max_size) if flag else value)
    result=b''.join(parts)
    if len(result)!=entry.size or zlib.adler32(result)&0xffffffff!=entry.checksum:raise ValueError('XP3 member checksum')
    return result


def build(files):
    validate_names([n for n,d in files])
    if not files or sum(len(d) for n,d in files)>256<<20:raise ValueError('XP3 build budget')
    chunk=lambda tag,value:tag+struct.pack('<Q',len(value))+value
    result=bytearray(MAGIC+b'\0'*8);index=bytearray()
    for name,data in files:
        if len(data)>32<<20:raise ValueError('XP3 build member budget')
        encoded=name.encode('utf-16le');units=len(encoded)//2
        if units>4096:raise ValueError('XP3 name budget')
        checksum=zlib.adler32(data)&0xffffffff;alias=hashlib.md5(name.lower().encode('utf-16le')).hexdigest().encode('utf-16le')
        index.extend(chunk(b'eliF',struct.pack('<IH',checksum,units)+encoded+b'\0\0'))
        packed=zlib.compress(data)
        info=struct.pack('<IQQH',0,len(data),len(packed),32)+alias
        segments=struct.pack('<IQQQ',1,len(result),len(data),len(packed))
        index.extend(chunk(b'File',chunk(b'info',info)+chunk(b'segm',segments)+chunk(b'adlr',struct.pack('<I',checksum))))
        result.extend(packed)
    struct.pack_into('<Q',result,11,len(result));packed=zlib.compress(index)
    result.extend(b'\x01'+struct.pack('<QQ',len(packed),len(index))+packed)
    return bytes(result)
