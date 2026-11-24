"""Bounded XP3 with an eliF/Yuzu filename mapping; plaintext member reader/writer.

Both mapping chunks use the same body: u32 checksum, u16 name units, UTF-16LE
name, NUL. File records carry md5(lower(name) as UTF-16LE) as their info name.
Some archives flag members as encrypted although the payloads are plain:
flagged plaintext requires explicit opt-in, full Adler-32 and inner parsing.
No cipher is guessed or applied here; filtered writers pass a registered,
already verified filter spec. Mapping layout: GARbro-Mod
ArcFormats/KiriKiri/ArcXP3.cs (MIT, morkt, 2014-2017). Full MIT notice is
included in the adjacent xp3.py. Independent Python writer.
"""
from dataclasses import dataclass
import hashlib
import struct
import zlib
from .xp3 import MAGIC, _chunks, _inflate, resolve_index_offset
from python.common.safety import validate_names

MAPPING_TAGS = (b'eliF', b'Yuzu')


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


def read_index(stream, *, max_index=16 << 20, mapping_tag=b'eliF'):
    """Read File records, resolving md5 aliases through one mapping chunk type."""
    if mapping_tag not in MAPPING_TAGS:raise ValueError('unknown XP3 name mapping chunk')
    stream.seek(0,2); total=stream.tell()
    def read(at,size):
        if at<0 or size<0 or at+size>total or size>max_index: raise ValueError('eliF XP3 metadata bounds')
        stream.seek(at);value=stream.read(size)
        if len(value)!=size: raise ValueError('truncated XP3 metadata')
        return value
    if read(0,11)!=MAGIC:raise ValueError('not XP3')
    at=resolve_index_offset(read,total)
    if read(at,9)==b'\x80'+b'\0'*8:at,=struct.unpack('<Q',read(at+9,8))
    flag=read(at,1)[0]
    if flag==1:
        pk,size=struct.unpack('<QQ',read(at+1,16));index=_inflate(read(at+17,pk),size,max_index);index_end=at+17+pk
    elif flag==0:
        size,=struct.unpack('<Q',read(at+1,8));index=read(at+9,size);index_end=at+9+size
    else:raise ValueError('unsupported XP3 index flag')
    chunks=list(_chunks(index));mapping={};hashes={};entries=[]
    for tag,value in chunks:
        if tag==mapping_tag:
            if len(value)<8:raise ValueError('short XP3 name mapping')
            checksum,units=struct.unpack_from('<IH',value)
            if not units or units>4096 or len(value)!=8+units*2 or value[-2:]!=b'\0\0':raise ValueError('invalid XP3 name mapping')
            name=value[6:-2].decode('utf-16le');alias=hashlib.md5(name.lower().encode('utf-16le')).hexdigest()
            if alias in mapping and mapping[alias]!=(checksum,name):raise ValueError('conflicting XP3 name mapping')
            mapping[alias]=(checksum,name);hashes.setdefault(checksum,set()).add(name)
        elif tag!=b'File':raise ValueError(f'unknown XP3 index record {tag!r}')
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
        elif mapping_tag==b'eliF' and len(hashes.get(checksum,set()))==1:name=next(iter(hashes[checksum]))
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
    if len(result)!=entry.size or zlib.adler32(result)&0xffffffff!=entry.checksum:
        if entry.flags:raise ValueError(FLAGGED_CHECKSUM)
        raise ValueError('XP3 member checksum')
    return result


FLAGGED_CHECKSUM=('XP3 member checksum mismatch on a member flagged 0x80000000: the payload is filtered/encrypted. '
                  'Run python -m python.engines.kirikiri_probe on the archive (add --try-filters, or '
                  '--recover-akabei-png when it has PNG members) and pass a verified --filter-spec; '
                  'if no registered filter verifies, the cipher is unsupported')


def build(files,*,mapping_tag=b'eliF',filter_spec=None):
    """Write a mapped-name XP3. A filter spec encrypts payloads after the
    plaintext Adler-32 is computed and marks members 0x80000000, matching the
    reader in kirikiri_filtered; no spec writes unflagged plaintext."""
    if mapping_tag not in MAPPING_TAGS:raise ValueError('unknown XP3 name mapping chunk')
    if filter_spec is not None:
        from .kirikiri_filters import validate,transform
        filter_spec=validate(filter_spec)
        if filter_spec['algorithm']=='none':filter_spec=None
    validate_names([n for n,d in files])
    if not files or sum(len(d) for n,d in files)>256<<20:raise ValueError('XP3 build budget')
    chunk=lambda tag,value:tag+struct.pack('<Q',len(value))+value
    result=bytearray(MAGIC+b'\0'*8);index=bytearray()
    for name,data in files:
        if len(data)>32<<20:raise ValueError('XP3 build member budget')
        encoded=name.encode('utf-16le');units=len(encoded)//2
        if units>4096:raise ValueError('XP3 name budget')
        checksum=zlib.adler32(data)&0xffffffff;alias=hashlib.md5(name.lower().encode('utf-16le')).hexdigest().encode('utf-16le')
        index.extend(chunk(mapping_tag,struct.pack('<IH',checksum,units)+encoded+b'\0\0'))
        stored=data if filter_spec is None else transform(data,checksum,filter_spec,encrypt=True)
        packed=zlib.compress(stored);flags=0 if filter_spec is None else 0x80000000
        segments=chunk(b'segm',struct.pack('<IQQQ',1,len(result),len(data),len(packed)))
        adlr=chunk(b'adlr',struct.pack('<I',checksum))
        if mapping_tag==b'Yuzu':
            # Field order and NUL-terminated alias as observed in Yuzu-mapped indexes.
            info=chunk(b'info',struct.pack('<IQQH',flags,len(data),len(packed),32)+alias+b'\0\0')
            body=chunk(b'time',b'\0'*8)+adlr+segments+info
        else:
            body=chunk(b'info',struct.pack('<IQQH',flags,len(data),len(packed),32)+alias)+segments+adlr
        index.extend(chunk(b'File',body))
        result.extend(packed)
    struct.pack_into('<Q',result,11,len(result));packed=zlib.compress(index)
    result.extend(b'\x01'+struct.pack('<QQ',len(packed),len(index))+packed)
    return bytes(result)
