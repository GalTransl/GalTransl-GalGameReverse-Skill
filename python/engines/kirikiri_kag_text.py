"""KAG page dialogue writer for the verified Alter nm/np/exlink macro dialect.

New semantic adapter over the shared lossless lexer. Does not execute macros.
Source evidence and deployment limits: engines/kirikiri/kag-text.md.
"""
import re
from python.common.contract import make_manifest, validate_translation
from python.common.line_layout import drops_only_line_breaks
from .kirikiri_kag import decode, tokenize, attributes

PROFILE = 'kag-alter-nm-np/1'
# Verified non-text inline commands. Their entire literal spelling is protected.
INLINE = frozenset(('r', 'se', 'resetwait', 'bg', 'wait', 'fose', 'eff_all_delete',
    'q_small', 'extrans', 'dse', 'echr', 'font', 'resetfont', 'wse', 'sse', 'ev', 'eff'))
# Commands that carry page/name/choice/macro structure; never configurable inline.
STRUCTURAL = frozenset(('nm', 'np', 'exlink', 'macro', 'endmacro', 'iscript', 'endscript',
    'if', 'elsif', 'else', 'endif', 'ignore', 'endignore', 'jump', 'call', 'return', 's', 'link', 'endlink'))


def inline_tags(extra=()):
    """Validated set of extra protected inline tags (explicit dialect config).

    Each name must be confirmed from macro/plugin definitions to be an inline
    tag that does not end a page, set a name or branch; its literal spelling is
    then protected like the built-in INLINE set.
    """
    if isinstance(extra,str):raise ValueError('inline tags must be a list of names')
    names=tuple(extra)
    for name in names:
        if (type(name) is not str or not name or len(name)>32
                or re.search(r'[\s\[\]=\'"@*;&%\\/]',name) or name in STRUCTURAL):
            raise ValueError(f'invalid/structural extra inline KAG tag: {name!r}')
    if len(set(names))!=len(names):raise ValueError('duplicate extra inline KAG tag')
    return frozenset(names)


def prose(body):
    return ''.join(line for line in body.splitlines(keepends=True) if not line.lstrip(' \t').startswith(';'))


def restore_comments(old, new):
    """Reinsert comments; drop prose lines the translation no longer uses.

    A shorter translation may occupy fewer physical lines. Comments are kept in
    place, and any prose line left over after the translated lines run out is
    removed with its line ending. Extra translated lines are still rejected.
    """
    old_lines=old.splitlines(keepends=True)
    translated=list(new.splitlines(keepends=True))
    prose=[i for i,line in enumerate(old_lines) if not line.lstrip(' \t').startswith(';')]
    if not translated or not prose:
        raise ValueError('KAG page has no translatable prose line')
    if len(translated)>len(prose):
        raise ValueError('KAG translation uses more physical lines than the source')
    if len(translated)<len(prose):
        last=prose[len(translated)-1]
        if any(old_lines[i].lstrip(' \t').startswith(';')
               for i in range(last+1,len(old_lines))):
            raise ValueError('KAG shorter page ends before a comment; keep the line '
                             'count or move that comment')
    lines=iter(enumerate(translated));out=[]
    for i,line in enumerate(old_lines):
        if line.lstrip(' \t').startswith(';'):
            out.append(line)
        else:
            pair=next(lines,None)
            if pair is not None:
                index,value=pair
                ending=line[len(line.rstrip('\r\n')):]
                # JSON text has no trailing EOL. Intermediate lines need one to
                # stay separate; the last line keeps the ending only when the
                # translation itself ends with a line break.
                if value.endswith(('\r','\n')) or index<len(translated)-1:
                    out.append(value if value.endswith(('\r','\n')) else value+ending)
                else:
                    out.append(value)
    return ''.join(out)


def signature(message,extra=frozenset()):
    """Protect command bytes and ruby readings while allowing ruby base edits."""
    result=[];allowed=INLINE|extra
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
                if name not in allowed:
                    raise ValueError(f'unverified inline KAG command [{name}] (U+{" U+".join(f"{ord(c):04X}" for c in name)}): '
                                     'confirm from its macro/plugin definition that it is an inline, non-paging tag, '
                                     'then pass it with --inline-tags')
                result.append(('tag',token.raw))
        else:
            raise ValueError('KAG dialogue contains command/label/comment/script boundary')
    if not message.strip(): raise ValueError('empty KAG dialogue')
    return result


def parse(raw,extra=()):
    extra=inline_tags(extra)
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
    token=None
    try:
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
                value=prose(text[start:token.start]);signature(value,extra)
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
    except ValueError as exc:
        # Report the physical source line so the dialect mismatch can be inspected.
        at=token.start if token is not None else 0
        raise ValueError(f'line {text.count(chr(10),0,at)+1}: {exc}') from exc
    return text,encoding,bom,records


def export_script(raw,extra=()):
    """Rows and manifest. `extra` lists explicitly configured inline tags; a
    non-empty set is recorded in manifest settings so rebuild uses the same."""
    extra=inline_tags(extra)
    text,encoding,bom,recs=parse(raw,extra);rows=[r['row'] for r in recs]
    meta=make_manifest(engine='kirikiri',variant=PROFILE,reference='kirikiri_kag_text/1',
        sources={'script.ks':raw},rows=rows,encoding=encoding,
        locators=[{k:r[k] for k in ('message','name','kind')} for r in recs],
        name_policies=['writable' if r['name'] else 'absent' for r in recs],
        settings={'inline_tags':sorted(extra)} if extra else None)
    return rows,meta


def skeleton(text,recs):
    spans=sorted([tuple(r['message']) for r in recs]+[tuple(r['name']) for r in recs if r['name']])
    out=[];pos=0
    for a,b in spans:
        if a<pos:raise ValueError('overlapping KAG text slots')
        out.append(text[pos:a]);pos=b
    out.append(text[pos:]);return out


def rebuild_script(raw,translated,manifest,extra=()):
    extra=inline_tags(extra)
    original,expected=export_script(raw,extra)
    if manifest!=expected:raise ValueError('KAG manifest differs from source')
    translated=validate_translation(manifest,{'script.ks':raw},original,translated)
    text,encoding,bom,recs=parse(raw,extra);edits=[]
    for rec,before,after in zip(recs,original,translated):
        a,b=rec['message'];value=after['message']
        if rec['kind']=='message':
            if not drops_only_line_breaks(signature(before['message'],extra),signature(value,extra),
                                          lambda item:item[0]=='newline'):
                raise ValueError('KAG controls/ruby changed or line breaks added/moved')
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
    rebuilt=bom+out.encode(encoding,'strict');new,_,_,check=parse(rebuilt,extra)
    if [r['row'] for r in check]!=translated or skeleton(text,recs)!=skeleton(new,check):
        raise ValueError('KAG reparse or non-text structure mismatch')
    return rebuilt
