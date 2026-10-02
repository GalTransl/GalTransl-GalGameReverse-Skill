"""Lossless KAG lexical layer, independent of tag semantics and game titles.

Offsets refer to decoded characters. Commands and script blocks are never run.
This is not a dialogue exporter: tag/name/control semantics need a dialect.
"""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Token:
    kind: str
    start: int
    end: int
    raw: str


def decode(data):
    if data.startswith(b'\xff\xfe'):return data[2:].decode('utf-16le'),'utf-16le',b'\xff\xfe'
    if data.startswith(b'\xfe\xff'):return data[2:].decode('utf-16be'),'utf-16be',b'\xfe\xff'
    if data.startswith(b'\xef\xbb\xbf'):return data[3:].decode('utf-8'),'utf-8',b'\xef\xbb\xbf'
    raise ValueError('KAG encoding needs BOM or an explicitly implemented encoding policy')


def tokenize(text):
    if '\0' in text:raise ValueError('NUL in KAG text')
    result=[];script=False
    def emit(kind,a,b):
        if b>a:result.append(Token(kind,a,b,text[a:b]))
    for match in re.finditer(r'[^\r\n]+|[\r\n]+',text):
        a,b=match.span();line=match[0]
        if line[0] in '\r\n':emit('newline',a,b);continue
        clean=line.lstrip(' \t');lead=len(line)-len(clean)
        if script:
            if clean.strip() in ('@endscript','[endscript]'):
                script=False;emit('command',a,b)
            else:emit('script',a,b)
            continue
        if clean.strip() in ('@endscript','[endscript]'):raise ValueError('unmatched KAG endscript')
        if clean.strip() in ('@iscript','[iscript]'):
            script=True;emit('command',a,b);continue
        if clean.startswith((';','*','@')):
            emit({';':'comment','*':'label','@':'command'}[clean[0]],a,b);continue
        i=0;start=0
        while i<len(line):
            if line[i:i+2]=='[[':i+=2;continue
            if line[i]!='[':i+=1;continue
            emit('text',a+start,a+i);j=i+1;quote=None
            while j<len(line):
                c=line[j]
                if quote:
                    if c=='\\':j+=2;continue
                    if c==quote:quote=None
                elif c in ('"',"'") and line[i+1:j].rstrip().endswith('='):quote=c
                elif c==']':break
                elif c=='[':raise ValueError('nested KAG bracket')
                j+=1
            if j>=len(line) or quote:raise ValueError('unterminated KAG tag')
            emit('tag',a+i,a+j+1);i=j+1;start=i
        emit('text',a+start,b)
    if script:raise ValueError('unterminated KAG script')
    if ''.join(t.raw for t in result)!=text:raise ValueError('KAG lexical coverage')
    return result


def attributes(command):
    """Parse literal attributes with exact spans; expressions stay opaque.

    Unknown syntax is rejected by this optional semantic helper, not discarded.
    """
    name=re.match(r'\s*(?:@|\[)?([\w!]+)',command)
    if not name:raise ValueError('missing KAG command name')
    pos=name.end();fields={}
    while pos<len(command):
        tail=command[pos:]
        if not tail.strip() or tail.strip()==']':break
        m=re.match(r'''\s+(\w+)\s*=\s*(?:"([^"\\]*)"|'([^'\\]*)'|([^\s\]]+))''',tail)
        if not m:raise ValueError('KAG attribute needs dialect/expression parser')
        key=m[1]
        if key in fields:raise ValueError('duplicate KAG attribute')
        group=next(i for i in (2,3,4) if m[i] is not None)
        fields[key]={'value':m[group],'span':(pos+m.start(group),pos+m.end(group)),
                     'dynamic':m[group].startswith(('&','%'))}
        pos+=m.end()
    return name[1],fields
