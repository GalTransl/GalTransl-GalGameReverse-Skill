"""Bounded PE resource/BRES/TJS constant inspection for Hxv4 key candidates.

Static reads only; no DLL loading or TJS execution. Algorithm reference:
msg-tool cx.rs static-analysis routines, GPL-3.0-or-later.
"""
import hashlib
import re
import struct
import zlib
from .kirikiri_hxv4 import chacha


class PE:
    def __init__(self,data):
        self.data=data
        pe=self.u32(60)
        if self.read(pe,4)!=b'PE\0\0':raise ValueError('not PE')
        count=self.u16(pe+6);optional=pe+24;magic=self.u16(optional)
        if count>96 or magic!=0x10b:raise ValueError('unsupported PE layout')
        self.base=self.u32(optional+28);self.sections=[]
        table=optional+self.u16(pe+20)
        for i in range(count):
            off=table+i*40
            self.sections.append((self.u32(off+12),self.u32(off+16),self.u32(off+20)))
        self.resources=self.rva(self.u32(optional+112))

    def read(self,at,n):
        if at<0 or n<0 or at+n>len(self.data):raise ValueError('PE bounds')
        return self.data[at:at+n]
    def u32(self,at):return struct.unpack('<I',self.read(at,4))[0]
    def u16(self,at):return struct.unpack('<H',self.read(at,2))[0]
    def rva(self,va):
        for start,size,raw in self.sections:
            if start<=va<start+size:return raw+va-start
        raise ValueError('unmapped PE RVA')
    def resource(self,kind,name):
        at=self.resources
        for wanted in (kind,name,None):
            count=self.u16(at+12)+self.u16(at+14)
            if count>4096:raise ValueError('PE resource budget')
            matches=[]
            for i in range(count):
                ident=self.u32(at+16+i*8);dest=self.u32(at+20+i*8)
                if ident>>31:
                    off=self.resources+(ident&0x7fffffff);units=self.u16(off)
                    if units>512:raise ValueError('PE resource name budget')
                    ident=self.read(off+2,units*2).decode('utf-16le')
                if wanted is None or ident==wanted:matches.append(dest)
            if not matches:raise ValueError('PE resource missing')
            dest=matches[0];at=self.resources+(dest&0x7fffffff)
        if dest>>31:raise ValueError('PE resource depth')
        size=self.u32(at+4)
        if size>16<<20:raise ValueError('PE resource size budget')
        return self.read(self.rva(self.u32(at)),size)

    def salts(self):
        found=set()
        for m in re.finditer(b'\xc7\x05',self.data):
            at=m.start()
            if at+10>len(self.data):continue
            try:off=self.rva(self.u32(at+6)-self.base)
            except ValueError:continue
            for n in re.finditer(b'\xc7\x05',self.data[at+10:at+64]):
                pos=at+10+n.start()
                if pos+10<=len(self.data) and self.u32(pos+6)==8192 and off+8192<=len(self.data):found.add(off)
        for m in re.finditer(b'V2Link\0\0',self.data):
            if m.start()>=8192:found.add(m.start()-8192)
        for m in re.finditer(b'forcedataxp3\0',self.data):
            start=(m.end()+15)&~15
            for off in range(start,min(m.start()+256,len(self.data)-8192)+1,16):found.add(off)
        if len(found)>64:raise ValueError('PE salt candidate budget')
        return [self.read(off,8192) for off in sorted(found)]


def bres(data,name,salt):
    digest=hashlib.sha3_384(name.encode('utf-16le')+salt).digest()
    return chacha(data,digest[:32],digest[44:48]+digest[32:40],int.from_bytes(digest[40:44],'little'),8,True)


def tjs_strings(data):
    if data[:8]!=b'TJS2100\0' or data[12:16]!=b'DATA':raise ValueError('TJS constants header')
    end=12+int.from_bytes(data[16:20],'little');at=20
    if end>len(data):raise ValueError('TJS DATA bounds')
    def read(n):
        nonlocal at
        if n<0 or at+n>end:raise ValueError('TJS constants bounds')
        v=data[at:at+n];at+=n;return v
    def count():
        n=int.from_bytes(read(4),'little')
        if n>1000000:raise ValueError('TJS constant count')
        return n
    for width in (1,2,4,8,8):
        read(count()*width);at=(at+3)&~3
    strings=[]
    for _ in range(count()):
        strings.append(read(count()*2).decode('utf-16le'));at=(at+3)&~3
    for _ in range(count()):read(count());at=(at+3)&~3
    if at!=end:raise ValueError('TJS DATA trailing bytes')
    return strings


def config(dll):
    at=dll.find(bytes(8)+b'PARAMS')
    if at<0:raise ValueError('Hx config marker missing')
    at+=8;result={}
    for _ in range(32):
        end=dll.find(b'\0',at,at+64)
        if end<0:raise ValueError('Hx config tag bounds')
        tag=dll[at:end].decode('ascii')
        if not tag:break
        if end+3>len(dll):raise ValueError('Hx config truncated')
        size=int.from_bytes(dll[end+1:end+3],'little');at=end+3
        if at+size>len(dll):raise ValueError('Hx config bounds')
        if tag in result:raise ValueError('Hx config duplicate')
        result[tag]=dll[at:at+size];at+=size
    else:raise ValueError('Hx config count')
    marker=b'p\0t\0-\0-\0n\0o\0\0\0\0\0';at=dll.find(marker)
    if at>=0:result['upperKey']=dll[at+len(marker):at+len(marker)+8]
    return result


def candidates(data):
    if len(data)>32<<20:raise ValueError('PE size budget')
    pe=PE(data);root=pe.resource('TEXT',127).decode('utf-16le').lstrip('\ufeff').rstrip('\0')
    if not root.startswith('bres://./'):raise ValueError('BRES root')
    startup=pe.resource(10,'STARTUP.TJS');bootstrap=pe.resource(10,'BOOTSTRAP');result=[]
    for salt in pe.salts():
        try:
            strings=tjs_strings(bres(startup,root[9:].rstrip('/'),salt))
            urls=[s for s in strings if s.startswith('bres://./') and s.lower().endswith('/bootstrap')]
            for url in urls:
                raw=bres(bootstrap,url[9:].split('/')[0],salt)
                dec=zlib.decompressobj();dll=dec.decompress(raw[8:],16<<20)
                if not dec.eof or dec.unconsumed_tail or not dll.startswith(b'MZ'):continue
                conf=config(dll)
                # Candidates only: the caller must validate the encrypted archive.
                for text in strings:
                    if 'copyright' not in text.lower() and 'rights' not in text.lower():continue
                    result.append({'bootStrap':text,'warning':conf['WARNING'].decode('utf-8').rstrip('\0'),
                                   'params':conf['PARAMS'].hex(),'archiveUniqueKey':conf['UNIQUE'].decode('utf-16le').rstrip('\0'),
                                   'upperKey':conf.get('upperKey',bytes(8)).hex()})
        except (ValueError,KeyError,UnicodeError,zlib.error):continue
    return result
