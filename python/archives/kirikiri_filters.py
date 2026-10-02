"""Parameter-only XP3 byte filter registry (no title lookup or executable code).

Ported from GARbro-Mod CryptAlgorithms.cs, MIT, morkt; see xp3.py notice.
Algorithms below filter decompressed bytes and use plaintext Adler32.
"""
from .kirikiri_akabei import crypt

SCHEMAS = {
    'none': {}, 'hash': {}, 'xor': {'key':255}, 'stripe': {'key':255},
    'akabei': {'seed':0xffffffff}, 'haikuo': {}, 'exa': {}, 'yuzu': {},
}


def validate(spec):
    if not isinstance(spec,dict) or spec.get('algorithm') not in SCHEMAS:
        raise ValueError('unknown XP3 filter algorithm')
    params=SCHEMAS[spec['algorithm']]
    if set(spec)!={'algorithm',*params}:raise ValueError('missing/unknown XP3 filter parameter')
    for name,maximum in params.items():
        if type(spec[name]) is not int or not 0<=spec[name]<=maximum:
            raise ValueError('XP3 filter parameter range/type')
    return dict(spec)


def transform(data, checksum, spec, *, offset=0, encrypt=False):
    spec=validate(spec);algorithm=spec['algorithm']
    if type(offset) is not int or offset<0:raise ValueError('invalid logical filter offset')
    if not 0<=checksum<=0xffffffff:raise ValueError('invalid plaintext checksum')
    if algorithm=='none':return data
    if algorithm=='akabei':return crypt(data,checksum,spec['seed'],offset)
    if algorithm=='exa':return bytes(v^((checksum>>((offset+i)%5))&255) for i,v in enumerate(data))
    if algorithm=='stripe':
        key=spec['key']
        return bytes(((v-1)&255)^key if encrypt else ((v^key)+1)&255 for v in data)
    if algorithm=='xor':key=spec['key']
    elif algorithm=='hash':key=checksum&255
    elif algorithm=='haikuo':key=(checksum^(checksum>>8))&255
    elif algorithm=='yuzu':
        h=checksum^0x1ddb6e7a;key=(h^(h>>8)^(h>>16)^(h>>24))&255
        key=key or 0xd0
    else:raise ValueError('unimplemented XP3 filter')
    return bytes(v^key for v in data)
