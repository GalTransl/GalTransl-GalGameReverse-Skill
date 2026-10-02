"""Kirikiri single/multilingual SCN: scene texts and choices, reference-local edits.

Semantics follow msg-tool kirikiri/scn.rs, GPL-3.0-or-later. Internal name IDs
remain context; display-name slots are writable. Only verified tuple shapes.
"""
import hashlib
import re
from .kirikiri_psb import Psb


def fields(psb, node, path):
    if node.tag != 33: raise ValueError('expected SCN object')
    return {psb.keys[k]: (v, path+(i,)) for i,(k,v) in enumerate(node.value)}


def list_nodes(pair):
    node, path = pair
    if node.tag != 32: raise ValueError('expected SCN list')
    return [(n, path+(i,)) for i,n in enumerate(node.value)]


# Display-text-less select records whose keys describe a link/storage jump: a
# nonnegative selection index, optional button/close flags, the owning script
# and a jump label. This classifies the record, not the button's image/UI text.
STRUCTURAL_CHOICE_KEYS = frozenset({'selidx', 'button', 'close', 'storage', 'target'})
FLAG_TOKEN = re.compile(r'[A-Za-z0-9_.\-]{1,32}')
LABEL_TOKEN = re.compile(r'\*[\w.\-]{1,255}')


def selection_index(node):
    return node.tag == 4 or 5 <= node.tag <= 12 and node.value >= 0


def structural_choice(psb, choice, self_name):
    """True when a display-text-less select matches the verified link/storage shape."""
    keys = set(choice)
    if keys - STRUCTURAL_CHOICE_KEYS: return False
    if keys == {'selidx'}:
        return selection_index(choice['selidx'][0])
    if not {'selidx', 'storage', 'target'} <= keys: return False
    strings = {key: psb.text(node) if 21 <= node.tag <= 24 else None for key, (node, _) in choice.items()}
    for key, (node, _) in choice.items():
        value = strings[key]
        if key == 'selidx': ok = selection_index(node)
        elif key == 'close': ok = node.tag in (2, 3) or value in ('true', 'false')
        elif key == 'target': ok = value is not None and LABEL_TOKEN.fullmatch(value) is not None
        elif key == 'storage': ok = value is not None and self_name is not None and value == self_name
        else: ok = value is not None and FLAG_TOKEN.fullmatch(value) is not None
        if not ok: return False
    return True


def records(psb, language_index=0, *, skipped=None):
    """Export scene texts and choices; collect non-display select keys in skipped."""
    if type(language_index) is not int or language_index < 0: raise ValueError('invalid language index')
    root = fields(psb, psb.root, ())
    self_name = psb.strings[root['name'][0].value] if 'name' in root and 21 <= root['name'][0].tag <= 24 else None
    result = []
    for scene_id, (scene, path) in enumerate(list_nodes(root['scenes'])):
        scene = fields(psb, scene, path)
        if 'texts' in scene:
            for text_id, (text, path) in enumerate(list_nodes(scene['texts'])):
                if text.tag != 32: raise ValueError('unknown SCN text tuple')
                values = text.value
                extra_fields = {}
                kind = 'message'
                zero_tail = bool(values) and (values[-1].tag == 4 or 5 <= values[-1].tag <= 12 and values[-1].value == 0)
                if (len(values) == 5 or len(values) == 6 and zero_tail) and values[1].tag == 32:
                    slot, has_length = 1, True
                elif len(values) == 6 and values[2].tag == 32:
                    slot, has_length = 2, False
                else:
                    slot = None
                if slot is not None:
                    langs = values[slot].value
                    if language_index >= len(langs): raise ValueError('SCN language slot missing')
                    localized = langs[language_index]
                    expected = (3,4,5) if has_length else (2,4)
                    if localized.tag != 32 or len(localized.value) not in expected: raise ValueError('unknown localized SCN tuple')
                    who = values[0]; display, message = localized.value[:2]
                    localized_path = path+(slot,language_index)
                    message_path, name_path = localized_path+(1,), localized_path+(0,)
                    cache_start = 3 if has_length else 2
                    cache_nodes = localized.value[cache_start:]
                    cache_paths = [localized_path+(i,) for i in range(cache_start,len(localized.value))]
                    image_alt = has_length and len(localized.value) == 4
                    if image_alt:
                        # A one-image message carries alt text, not speech/search
                        # caches. Keep the image command and visible count intact.
                        if (not re.fullmatch(r'%i1&[^%;\r\n]+;', psb.text(message))
                                or not 5 <= localized.value[2].tag <= 12 or localized.value[2].value != 1):
                            raise ValueError('unknown SCN image-alt tuple')
                        message = localized.value[3]
                        message_path = localized_path+(3,)
                        cache_nodes, cache_paths = [], []
                        kind = 'image-alt'
                    if has_length and not image_alt:
                        length = localized.value[2]
                        if not (length.tag == 4 or 5 <= length.tag <= 12): raise ValueError('unknown SCN text length')
                        visible = len(save_message(psb.text(message).replace('\\n','\n'),False))
                        if (0 if length.tag == 4 else length.value) != visible: raise ValueError('SCN visible length mismatch')
                        extra_fields['length'] = localized_path+(2,)
                else:
                    if language_index != 0 or len(values) not in (6,9): raise ValueError('unknown SCN text tuple/language')
                    who, display, message = values[:3]
                    message_path, name_path = path+(2,), path+(1,)
                    if len(values)==9 and values[6].tag!=1: raise ValueError('unknown SCN cached length slot')
                    cache_nodes = values[7:] if len(values)==9 else []
                    cache_paths = [path+(i,) for i in (7,8)] if cache_nodes else []
                if who.tag != 1 and not 21 <= who.tag <= 24: raise ValueError('unknown name ID')
                if display.tag != 1 and not 21 <= display.tag <= 24: raise ValueError('unknown display name')
                name = None if who.tag == 1 else psb.text(display if display.tag != 1 else who)
                row = {'name': name} if name is not None else {}
                row['message'] = psb.text(message).replace('\\n', '\n')
                for i, node in enumerate(cache_nodes):
                    stored = psb.text(node)
                    if stored != save_message(row['message'],i==0):
                        variants = ({'strip_ruby_dot': True}, {'trim_ruby_space': True},
                                    {'strip_ruby_dot': True, 'trim_ruby_space': True}) if i == 0 else ()
                        match = next((v for v in variants if stored == save_message(row['message'],True,**v)), None)
                        if match is None:
                            raise ValueError(f'SCN derived text mismatch: scene={scene_id}, text={text_id}, cache={i}')
                        extra_fields.update(match)
                result.append(dict(row=row, message=message_path, caches=cache_paths,
                                   name=name_path if name is not None and display.tag != 1 else None,
                                   kind=kind, scene=scene_id, index=text_id, **extra_fields))
        if 'selects' in scene:
            for choice_id, (choice, path) in enumerate(list_nodes(scene['selects'])):
                choice = fields(psb, choice, path)
                # These records are language-independent. Check before language
                # selection, and do not bypass validation for selidx-only markers.
                if 'text' not in choice and 'language' not in choice:
                    if not structural_choice(psb, choice, self_name):
                        raise ValueError('choice missing text')
                    if skipped is not None:
                        skipped.append(dict(scene=scene_id, index=choice_id, keys=sorted(choice)))
                    continue
                selected = choice
                if 'language' in choice:
                    langs = list_nodes(choice['language'])
                    if language_index >= len(langs): raise ValueError('SCN choice language missing')
                    node, loc = langs[language_index]
                    if node.tag == 33: selected = fields(psb,node,loc)
                    elif node.tag != 1 or language_index != 0: raise ValueError('SCN choice translation missing')
                elif language_index != 0: raise ValueError('SCN choice language unavailable')
                if 'text' not in selected: raise ValueError('choice missing text')
                node, loc = selected['text']
                result.append(dict(row={'message': psb.text(node).replace('\\n', '\n')},
                                   message=loc, caches=[], name=None, kind='choice', scene=scene_id, index=choice_id))
    return result


def controls(text):
    """Preserve literal inline tags/escapes; reject newly introduced syntax."""
    # An escaped opening bracket starts literal display text, not ruby.
    # Keep its delimiters protected while allowing the enclosed text to change.
    # Nested brackets and embedded control syntax need separate semantics.
    literal = r'\\\[[^\[\]\\%#\r\n]*\]'
    pattern = literal + r'|\[[^\[\]\r\n]*\]|\\[A-Za-z]|%[^%;]*;|%r|#[0-9a-fA-F]{6,8};'
    tokens = []
    for match in re.finditer(pattern, text):
        token = match.group()
        tokens.extend(('\\[', ']') if token.startswith('\\[') else (token,))
    rest = re.sub(pattern, '', text)
    if any(c in rest for c in '[]\\%#') or '\0' in text or '\r' in text:
        raise ValueError('unknown SCN text control syntax')
    return tokens


def save_message(text, ruby, *, strip_ruby_dot=False, trim_ruby_space=False):
    text = re.sub(r'%[^%;]*;|#[0-9a-fA-F]{6,8};', '', text.replace('\n', ''))
    output = []; pos = 0
    for match in re.finditer(r'(?<!\\)\[([^\]]*)\]', text):
        if match.start() < pos: raise ValueError('overlapping ruby span')
        output.append(text[pos:match.start()])
        reading = match[1]; count = 1
        if ',' in reading:
            reading, length = reading.rsplit(',', 1)
            if not length.isdecimal(): raise ValueError('unknown ruby length')
            count += int(length)
        end = match.end()+count
        if end > len(text): raise ValueError('ruby extends past text')
        spoken = reading.replace('・', '') if strip_ruby_dot else reading
        if trim_ruby_space: spoken = spoken.strip('\u3000')
        output.append(spoken if ruby and reading != '・' else text[match.end():end])
        pos = end
    text = ''.join(output)+text[pos:]
    return text.replace('%r', '').replace('\\[', '[')


def fingerprint(psb, excluded):
    """Semantic digest of every nonedited reference, independent of pool IDs."""
    digest = hashlib.sha256()
    def walk(node, path):
        if path in excluded:
            digest.update(b'EDIT'); return
        if 21 <= node.tag <= 24:
            raw = psb.text(node).encode('utf-8'); digest.update(b'S'+len(raw).to_bytes(4,'little')+raw)
        elif node.tag == 32:
            digest.update(b'L'+len(node.value).to_bytes(4,'little'))
            for i,child in enumerate(node.value): walk(child,path+(i,))
        elif node.tag == 33:
            digest.update(b'D'+len(node.value).to_bytes(4,'little'))
            for i,(key,child) in enumerate(node.value):
                digest.update(key.to_bytes(4,'little')); walk(child,path+(i,))
        else: digest.update(psb.data[node.pos:node.end])
    walk(psb.root, ())
    return digest.hexdigest()


def patch(psb, exported, rows):
    if len(rows) != len(exported): raise ValueError('SCN row count changed')
    edits = {}
    for rec, row in zip(exported, rows):
        original = rec['row']
        if set(row) != set(original): raise ValueError('SCN row fields changed')
        if not isinstance(row['message'], str) or controls(original['message']) != controls(row['message']):
            raise ValueError('SCN controls changed')
        edits[rec['message']] = row['message'].replace('\n', '\\n')
        for loc, ruby in zip(rec['caches'], (True, False)):
            edits[loc] = save_message(row['message'], ruby, strip_ruby_dot=rec.get('strip_ruby_dot',False),
                                     trim_ruby_space=rec.get('trim_ruby_space',False))
        if 'length' in rec:
            edits[rec['length']] = len(save_message(row['message'],False))
        if 'name' in row:
            if rec['name'] is None:
                if row['name'] != original['name']: raise ValueError('internal speaker ID is context only')
            else:
                if not isinstance(row['name'], str) or any(c in row['name'] for c in '\0\r\n[]\\'):
                    raise ValueError('invalid display name')
                edits[rec['name']] = row['name']
    return psb.patch(edits), set(edits)
