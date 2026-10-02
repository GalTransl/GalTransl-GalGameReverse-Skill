"""Akabei XP3 filter, parameterized by seed (no game-name dispatch).

Algorithm: GARbro-Mod CryptAlgorithms.cs / AkabeiCrypt, MIT, morkt.
Full MIT notice in adjacent xp3.py. Independent bounded archive writer.
"""
from .kirikiri_elif import read_index


def crypt(data, checksum, seed, offset=0):
    if not 0 <= seed <= 0xffffffff: raise ValueError('Akabei seed must be uint32')
    h=(checksum^seed)&0x7fffffff; h=(h|(h<<31))&0xffffffff
    key=[]
    for _ in range(32):
        key.append(h&255);h=(((h&0xfffffffe)<<23)|(h>>8))&0xffffffff
    return bytes(v^key[(offset+i)&31] for i,v in enumerate(data))


def read_member(stream, entry, seed, max_size=32<<20):
    from .kirikiri_filtered import read_member as read
    return read(stream,entry,{'algorithm':'akabei','seed':seed},max_size)


def build(files,seed):
    from .kirikiri_filtered import build as write
    return write(files,{'algorithm':'akabei','seed':seed})
