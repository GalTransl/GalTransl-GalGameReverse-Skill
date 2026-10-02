"""Shared bounded XP3 segment reader/writer for registered byte filters.

Uses plaintext Adler32, decompression before filtering, logical member offsets.
Standard File index writer. No guessing of filters or game identity.
"""
import struct
import zlib
from .xp3 import MAGIC, _inflate
from .kirikiri_filters import validate, transform
from python.common.safety import validate_names


def read_member(stream,entry,spec,max_size=32<<20):
    spec=validate(spec)
    if entry.issue or entry.size>max_size: raise ValueError('filtered XP3 member bounds/issue')
    parts=[];position=0
    for flag,at,raw,packed in entry.segments:
        if packed>max_size: raise ValueError('filtered XP3 packed budget')
        stream.seek(at);data=stream.read(packed)
        if len(data)!=packed: raise ValueError('truncated filtered XP3 member')
        data=_inflate(data,raw,max_size) if flag else data
        if entry.flags: data=transform(data,entry.checksum,spec,offset=position)
        parts.append(data);position+=len(data)
    result=b''.join(parts)
    if len(result)!=entry.size or zlib.adler32(result)&0xffffffff!=entry.checksum: raise ValueError('filtered XP3 member checksum')
    return result


def build(files,spec):
    spec=validate(spec)
    validate_names([n for n,d in files])
    if not files or sum(len(d) for n,d in files)>256<<20: raise ValueError('filtered XP3 build budget')
    def chunk(tag,data):return tag+struct.pack('<Q',len(data))+data
    result=bytearray(MAGIC+b'\0'*8);index=bytearray()
    for name,data in files:
        if len(data)>32<<20: raise ValueError('filtered XP3 member budget')
        checksum=zlib.adler32(data)&0xffffffff;stored=zlib.compress(transform(data,checksum,spec,encrypt=True))
        encoded=name.encode('utf-16le');units=len(encoded)//2
        if units>4096:raise ValueError('filtered XP3 name budget')
        flags=0 if spec['algorithm']=='none' else 0x80000000
        info=struct.pack('<IQQH',flags,len(data),len(stored),units)+encoded
        seg=struct.pack('<IQQQ',1,len(result),len(data),len(stored))
        index+=chunk(b'File',chunk(b'info',info)+chunk(b'segm',seg)+chunk(b'adlr',struct.pack('<I',checksum)))
        result+=stored
    struct.pack_into('<Q',result,11,len(result));packed=zlib.compress(index)
    result+=b'\x01'+struct.pack('<QQ',len(packed),len(index))+packed
    return bytes(result)
