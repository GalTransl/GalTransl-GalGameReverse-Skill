"""Kirikiri single/multilingual SCN: scene texts and choices, reference-local edits.

Semantics follow msg-tool kirikiri/scn.rs, GPL-3.0-or-later. Internal name IDs
remain context; display-name slots are writable. The default reader prefers the
exact verified dialect and otherwise locates text by typed field prefixes: a
derived field is rewritten only when its stored value matches a known rule, and
everything else stays verbatim and is reported.
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
# Literal variable references only; never evaluate TJS expressions. SCN stores
# these as ${reference} in speech/search caches and counts each as one unit.
VARIABLE = r'\$([A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*);'
COLOR = r'#(?:[0-9a-fA-F]{6,8})?;'
IMAGE_ALT = re.compile(r'%i1&[^%;\r\n]+;')
CACHE_VARIANTS = ({'strip_ruby_dot': True}, {'trim_ruby_space': True},
                  {'strip_ruby_dot': True, 'trim_ruby_space': True})


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


def integer(node):
    """Value of a PSB integer node, or None when the node is not an integer."""
    if node.tag == 4: return 0
    if 5 <= node.tag <= 12: return node.value
    return None


def _derived_caches(psb, nodes, paths, message, locate_only, context):
    """Mark speech/search caches whose stored text matches a known rule.

    Only the first two positions are defined (speech, then search). A node that
    is not a string, sits past those positions, or matches no rule stays opaque;
    the exact reader rejects it instead, naming the scene/text/cache.
    """
    caches = []; variants = {}; opaque = []
    for index, (node, loc) in enumerate(zip(nodes, paths)):
        stored = psb.text(node) if 21 <= node.tag <= 24 else None
        if stored is None:
            if not locate_only: raise ValueError('expected PSB string')
            opaque.append(loc); continue
        if index >= 2: opaque.append(loc); continue
        if stored == save_message(message, index == 0):
            caches.append(loc); continue
        match = next((v for v in CACHE_VARIANTS if index == 0 and stored == save_message(message, True, **v)), None)
        if match is not None:
            caches.append(loc); variants.update(match); continue
        if not locate_only:
            raise ValueError(f'SCN derived text mismatch: scene={context[0]}, text={context[1]}, cache={index}')
        opaque.append(loc)
    return caches, variants, opaque


def records(psb, language_index=0, *, skipped=None):
    """Export scene texts and choices; collect non-display select keys in skipped."""
    return _records(psb, language_index, skipped=skipped, locate_only=False)


def locate_records(psb, language_index=0, *, skipped=None):
    """Locate scene text by typed field prefixes and record its write plan.

    Trailing tuple fields are opaque: a derived field (visible length,
    speech/search cache) is marked for rewrite only when its stored value
    matches a known rule, and everything else stays verbatim under 'opaque'.
    A message whose control syntax is not recognized is still exported, but
    marked 'non_writable' so pack refuses to change it instead of guessing.
    Missing language slots and ambiguous text types still fail, not disappear.
    """
    return _records(psb, language_index, skipped=skipped, locate_only=True)


def writable_records(psb, language_index=0, *, skipped=None):
    """Prefer the exact verified dialect, else fall back to typed location.

    Returns (records, strict_issue). strict_issue is None only when the whole
    member also passes the verified layout, derived-field and control rules.
    """
    exact = []
    try:
        found = _records(psb, language_index, skipped=exact, locate_only=False)
        for rec in found: controls(rec['row']['message'])
    except ValueError as exc:
        return _records(psb, language_index, skipped=skipped, locate_only=True), str(exc)
    if skipped is not None: skipped.extend(exact)
    return found, None


def _text_record(psb, text, path, scene_id, text_id, language_index, locate_only):
    values = text.value
    zero_tail = bool(values) and (values[-1].tag == 4 or 5 <= values[-1].tag <= 12 and values[-1].value == 0)
    if len(values) >= 2 and values[1].tag == 32 and (locate_only or len(values) == 5 or len(values) == 6 and zero_tail):
        slot = 1
    elif len(values) >= 3 and values[2].tag == 32 and (locate_only or len(values) == 6):
        slot = 2
    else:
        slot = None
    length_path = None; cache_paths = []; opaque = []; variants = {}; kind = 'message'
    if slot is not None:
        if slot == 2 and values[1].tag != 1 and not 21 <= values[1].tag <= 24:
            raise ValueError('unknown outer display name')
        langs = values[slot].value
        if language_index >= len(langs): raise ValueError('SCN language slot missing')
        localized = langs[language_index]
        expected = (3, 4, 5) if slot == 1 else (2, 4)
        if localized.tag != 32 or (len(localized.value) < 2 if locate_only else len(localized.value) not in expected):
            raise ValueError('unknown localized SCN tuple')
        who = values[0]; display, message = localized.value[:2]
        localized_path = path+(slot, language_index)
        message_path, name_path = localized_path+(1,), localized_path+(0,)
        message_text = psb.text(message).replace('\\n', '\n')
        tail = list(localized.value[2:]); tail_paths = [localized_path+(i,) for i in range(2, len(localized.value))]
        if slot == 1 and len(localized.value) == 4:
            # A one-image message carries alt text, not speech/search caches.
            if IMAGE_ALT.fullmatch(psb.text(message)) and integer(localized.value[2]) == 1:
                message = localized.value[3]; message_path = localized_path+(3,)
                tail = []; tail_paths = []; kind = 'image-alt'
            elif not locate_only:
                raise ValueError('unknown SCN image-alt tuple')
        elif slot == 1 and tail:
            length = integer(localized.value[2])
            if length is None:
                if not locate_only: raise ValueError('unknown SCN text length')
                opaque.append(localized_path+(2,))
            elif length == visible_length(message_text):
                length_path = localized_path+(2,)
            elif not locate_only:
                raise ValueError('SCN visible length mismatch')
            else:
                opaque.append(localized_path+(2,))
            tail = tail[1:]; tail_paths = tail_paths[1:]
        cache_paths, variants, extra = _derived_caches(psb, tail, tail_paths, message_text, locate_only, (scene_id, text_id))
        opaque.extend(extra)
    else:
        if language_index != 0 or len(values) < 3: raise ValueError('unknown SCN text tuple/language')
        if not locate_only and len(values) not in (6, 9): raise ValueError('unknown SCN text tuple/language')
        who, display, message = values[:3]
        message_path, name_path = path+(2,), path+(1,)
        if len(values) == 9:
            if values[6].tag != 1:
                if not locate_only: raise ValueError('unknown SCN cached length slot')
                opaque = [path+(i,) for i in range(6, len(values))]
            else:
                cache_paths, variants, opaque = _derived_caches(
                    psb, values[7:9], [path+(7,), path+(8,)], psb.text(message).replace('\\n', '\n'),
                    locate_only, (scene_id, text_id))
        elif len(values) > 6:
            opaque = [path+(i,) for i in range(6, len(values))]
    if who.tag != 1 and not 21 <= who.tag <= 24: raise ValueError('unknown name ID')
    if display.tag != 1 and not 21 <= display.tag <= 24: raise ValueError('unknown display name')
    name = None if who.tag == 1 else psb.text(display if display.tag != 1 else who)
    row = {'name': name} if name is not None else {}
    row['message'] = psb.text(message).replace('\\n', '\n')
    rec = dict(row=row, message=message_path, caches=cache_paths,
               name=name_path if name is not None and display.tag != 1 else None,
               kind=kind, scene=scene_id, index=text_id, **variants)
    if length_path is not None: rec['length'] = length_path
    if opaque: rec['opaque'] = sorted(set(opaque))
    return rec


def _records(psb, language_index, *, skipped, locate_only):
    if type(language_index) is not int or language_index < 0: raise ValueError('invalid language index')
    root = fields(psb, psb.root, ())
    self_name = psb.strings[root['name'][0].value] if 'name' in root and 21 <= root['name'][0].tag <= 24 else None
    result = []
    for scene_id, (scene, path) in enumerate(list_nodes(root['scenes'])):
        scene = fields(psb, scene, path)
        if 'texts' in scene:
            for text_id, (text, path) in enumerate(list_nodes(scene['texts'])):
                if text.tag != 32: raise ValueError('unknown SCN text tuple')
                result.append(_text_record(psb, text, path, scene_id, text_id, language_index, locate_only))
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
    if locate_only:
        for rec in result:
            try: controls(rec['row']['message'])
            except ValueError as exc:
                # The message control grammar is unknown: keep the text readable,
                # preserve every derived field and refuse later edits.
                rec['non_writable'] = str(exc)
                derived = list(rec['caches']) + ([rec['length']] if 'length' in rec else [])
                if derived: rec['opaque'] = sorted(set(rec.get('opaque', []) + derived))
                rec['caches'] = []; rec.pop('length', None)
                rec.pop('strip_ruby_dot', None); rec.pop('trim_ruby_space', None)
    return result


def controls(text):
    """Preserve literal inline tags/escapes; reject newly introduced syntax."""
    # An escaped opening bracket starts literal display text, not ruby.
    # Keep its delimiters protected while allowing the enclosed text to change.
    # Nested brackets and embedded control syntax need separate semantics.
    literal = r'\\\[[^\[\]\\%#$\r\n]*\]'
    pattern = literal + r'|\[[^\[\]\r\n]*\]|\\[A-Za-z]|%[^%;]*;|%r|' + COLOR + '|' + VARIABLE
    tokens = []
    for match in re.finditer(pattern, text):
        token = match.group()
        tokens.extend(('\\[', ']') if token.startswith('\\[') else (token,))
    rest = re.sub(pattern, '', text)
    if any(c in rest for c in '[]\\%#$') or '\0' in text or '\r' in text:
        raise ValueError('unknown SCN text control syntax')
    return tokens


def save_message(text, ruby, *, strip_ruby_dot=False, trim_ruby_space=False):
    text = re.sub(r'%[^%;]*;|' + COLOR, '', text.replace('\n', ''))
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
        if trim_ruby_space: spoken = spoken.strip('　')
        output.append(spoken if ruby and reading != '・' else text[match.end():end])
        pos = end
    text = ''.join(output)+text[pos:]
    text = text.replace('%r', '').replace('\\[', '[')
    return re.sub(VARIABLE, lambda m: '${' + m[1] + '}', text)


def visible_length(text):
    """Static SCN length: each dynamic reference occupies one placeholder unit."""
    saved = save_message(text, False)
    return len(re.sub(r'\$\{[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*\}', '￼', saved))


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
        if rec.get('non_writable'):
            if row['message'] != original['message']:
                raise ValueError('SCN message control syntax is not recognized: '
                                 f"scene={rec['scene']}, text={rec['index']}")
        elif not isinstance(row['message'], str) or controls(original['message']) != controls(row['message']):
            raise ValueError('SCN controls changed')
        else:
            edits[rec['message']] = row['message'].replace('\n', '\\n')
            for loc, ruby in zip(rec['caches'], (True, False)):
                edits[loc] = save_message(row['message'], ruby, strip_ruby_dot=rec.get('strip_ruby_dot',False),
                                         trim_ruby_space=rec.get('trim_ruby_space',False))
            if 'length' in rec:
                edits[rec['length']] = visible_length(row['message'])
        if 'name' in row:
            if rec['name'] is None:
                if row['name'] != original['name']: raise ValueError('internal speaker ID is context only')
            else:
                if not isinstance(row['name'], str) or any(c in row['name'] for c in '\0\r\n[]\\'):
                    raise ValueError('invalid display name')
                edits[rec['name']] = row['name']
    return psb.patch(edits), set(edits)
