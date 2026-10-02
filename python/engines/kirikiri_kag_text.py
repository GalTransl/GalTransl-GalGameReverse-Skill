"""KAG page dialogue writer for the verified Alter nm/np/exlink macro dialect.

New semantic adapter over the shared lossless lexer. Does not execute macros.
Source evidence and deployment limits: engines/kirikiri/kag-text.md.
"""
import re
from python.common.contract import make_manifest, validate_translation
from .kirikiri_kag import decode, tokenize, attributes

PROFILE = 'kag-alter-nm-np/1'
# Verified non-text inline commands. Their entire literal spelling is protected.
INLINE = frozenset(('r', 'se', 'resetwait', 'bg', 'wait', 'fose', 'eff_all_delete',
    'q_small', 'extrans', 'dse', 'echr', 'font', 'resetfont', 'wse', 'sse', 'ev', 'eff'))


def prose(body):
    return ''.join(line for line in body.splitlines(keepends=True) if not line.lstrip(' \t').startswith(';'))


def restore_comments(old, new):
    lines=iter(new.splitlines(keepends=True));out=[]
    for line in old.splitlines(keepends=True):
        out.append(line if line.lstrip(' \t').startswith(';') else next(lines))
    if next(lines,None) is not None:raise ValueError('KAG physical line count changed')
    return ''.join(out)


def signature(message):
    """Protect command bytes and ruby readings while allowing ruby base edits."""
    result=[]
    for token in tokenize(message):
        if token.kind == 'text':
            if ']' in token.raw or '\\' in token.raw:
                raise ValueError('unsupported literal bracket/escape in KAG prose')
        elif token.kind == 'newline':
            result.append(('newline',token.raw))
        elif token.kind == 'tag':
            ruby=re.fullmatch(r"\[([^\[\]'\r\n]+)'([^\[\]'\r\n]+)\]",token.raw)
            if ruby and not re.search(r'[=\s]',ruby[1]):
                result.append(('ruby',ruby[2]))
            elif token.raw == '[・]':
                result.append(('tag',token.raw))
            else:
                name,_=attributes(token.raw)
                if name not in INLINE: raise ValueError('unverified inline KAG command: '+name)
                result.append(('tag',token.raw))
        else:
            raise ValueError('KAG dialogue contains command/label/comment/script boundary')
    if not message.strip(): raise ValueError('empty KAG dialogue')
    return result


def parse(raw):
    text,encoding,bom=decode(raw)
    if '\r' in text.replace('\r\n',''):raise ValueError('bare CR in KAG')
    records=[]; start=None; speaker=None; macro=False
    def literal_attribute(token, key):
        _,attrs=attributes(token.raw)
        if key not in attrs or attrs[key]['dynamic']:raise ValueError('dynamic/missing KAG text attribute')
        a,b=attrs[key]['span']
        # Only quoted literals: arbitrary expression output requires a dialect.
        if a == 0 or token.raw[a-1] not in "\"'" or token.raw[b] != token.raw[a-1]:
            raise ValueError('KAG display attribute must be quoted')
        return attrs[key]['value'],[token.start+a,token.start+b]
    for token in tokenize(text):
        if token.kind == 'script':continue
        if token.kind in ('command','tag'):
            cmd=re.match(r'\s*[@\[]([\w!]+)',token.raw)
            command=cmd[1] if cmd else None
            if command == 'macro':
                if macro or start is not None:raise ValueError('nested macro/dialogue boundary')
                macro=True;continue
            if command == 'endmacro':
                if not macro:raise ValueError('unmatched endmacro')
                macro=False;continue
            if macro:continue
            if command == 'nm':
                if start is not None or speaker is not None:raise ValueError('unconsumed KAG speaker')
                speaker=literal_attribute(token,'t');continue
            if command == 'exlink':
                if start is not None or speaker is not None:raise ValueError('choice inside KAG dialogue')
                value,span=literal_attribute(token,'txt')
                records.append({'row':{'message':value},'message':span,'name':None,'kind':'choice'})
                continue
            if command == 'np':
                if token.raw != '[np]' or start is None:raise ValueError('KAG page terminator without dialogue')
                value=prose(text[start:token.start]);signature(value)
                row={'name':speaker[0]} if speaker else {}
                row['message']=value.replace('\r\n','\n')
                records.append({'row':row,'message':[start,token.start],
                                'name':speaker[1] if speaker else None,'kind':'message'})
                start=None;speaker=None;continue
        if macro:continue
        if token.kind == 'text' and token.raw.strip():
            if start is None:start=token.start
        elif token.kind == 'tag' and start is None:
            # Ruby/emphasis may begin the page; ordinary commands cannot.
            tail=text[token.end:].split('\n',1)[0].rstrip('\r')
            inline_prose=any(t.kind=='text' and t.raw.strip() for t in tokenize(tail))
            if "'" in token.raw and '=' not in token.raw or token.raw == '[・]' or inline_prose:
                start=token.start
        elif token.kind in ('label','command') and start is not None:
            raise ValueError('unterminated KAG page before '+token.kind)
        if token.kind == 'label' and speaker is not None:raise ValueError('speaker crosses label')
    if macro or start is not None or speaker is not None:raise ValueError('incomplete KAG macro/page/name')
    return text,encoding,bom,records


def export_script(raw):
    text,encoding,bom,recs=parse(raw);rows=[r['row'] for r in recs]
    meta=make_manifest(engine='kirikiri',variant=PROFILE,reference='kirikiri_kag_text/1',
        sources={'script.ks':raw},rows=rows,encoding=encoding,
        locators=[{k:r[k] for k in ('message','name','kind')} for r in recs],
        name_policies=['writable' if r['name'] else 'absent' for r in recs])
    return rows,meta


def skeleton(text,recs):
    spans=sorted([tuple(r['message']) for r in recs]+[tuple(r['name']) for r in recs if r['name']])
    out=[];pos=0
    for a,b in spans:
        if a<pos:raise ValueError('overlapping KAG text slots')
        out.append(text[pos:a]);pos=b
    out.append(text[pos:]);return out


def rebuild_script(raw,translated,manifest):
    original,expected=export_script(raw)
    if manifest!=expected:raise ValueError('KAG manifest differs from source')
    translated=validate_translation(manifest,{'script.ks':raw},original,translated)
    text,encoding,bom,recs=parse(raw);edits=[]
    for rec,before,after in zip(recs,original,translated):
        a,b=rec['message'];value=after['message']
        if rec['kind']=='message':
            if signature(before['message'])!=signature(value):raise ValueError('KAG controls/ruby/newlines changed')
            old=text[a:b]
            if '\r\n' in old:value=value.replace('\n','\r\n')
            value=restore_comments(old,value)
        else:
            if any(c in value for c in "\r\n\0[]\\\"'") or value.startswith(('&','%')):
                raise ValueError('KAG choice introduces attribute syntax')
        edits.append((a,b,value))
        if rec['name']:
            value=after['name']
            if not value or any(c in value for c in "\r\n\0[]\\\"'") or value.startswith(('&','%')):
                raise ValueError('KAG name introduces attribute syntax')
            edits.append((*rec['name'],value))
    out=text
    for a,b,value in sorted(edits,reverse=True):out=out[:a]+value+out[b:]
    rebuilt=bom+out.encode(encoding,'strict');new,_,_,check=parse(rebuilt)
    if [r['row'] for r in check]!=translated or skeleton(text,recs)!=skeleton(new,check):
        raise ValueError('KAG reparse or non-text structure mismatch')
    return rebuilt
