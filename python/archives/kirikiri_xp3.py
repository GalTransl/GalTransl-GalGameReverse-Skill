"""Kirikiri XP3 capability dispatch, independent of game directory names.

Supports standard/eliF/Yuzu-mapped indexes with plaintext or registered byte
filters and the verified sen: Cx profile. Adding a filter belongs here or in a
leaf adapter, not in another game's batch script.
"""
import struct
from . import xp3, kirikiri_elif, kirikiri_senren, kirikiri_filtered
from .kirikiri_filters import validate

FORMATS = ('plain', 'elif-plain', 'yuzu-names', 'senren-cx')
# Indexes that keep md5 aliases in File/info and real names in a mapping chunk.
MAPPED = {'elif-plain': b'eliF', 'yuzu-names': b'Yuzu'}
# Profiles whose payload filter is a separate, explicitly configured spec.
FILTERABLE = ('plain',) + tuple(MAPPED)


def detect(stream):
    stream.seek(0,2);size=stream.tell()
    def read(at,count):
        if at<0 or count<0 or at+count>size or count>16<<20:raise ValueError('XP3 probe bounds')
        stream.seek(at);data=stream.read(count)
        if len(data)!=count:raise ValueError('truncated XP3 probe')
        return data
    if read(0,11)!=xp3.MAGIC:raise ValueError('not XP3')
    at=xp3.resolve_index_offset(read,size)
    if read(at,9)==b'\x80'+b'\0'*8:at,=struct.unpack('<Q',read(at+9,8))
    flag=read(at,1)[0]
    if flag==1:
        packed,length=struct.unpack('<QQ',read(at+1,16))
        index=xp3._inflate(read(at+17,packed),length,16<<20)
    elif flag==0:
        length,=struct.unpack('<Q',read(at+1,8));index=read(at+9,length)
    else:raise ValueError('unsupported XP3 index chaining/flags')
    tags={tag for tag,body in xp3._chunks(index)}
    if tags=={b'File',b'Hxv4'}:return 'hxv4'
    if tags=={b'File',b'sen:'}:return 'senren-cx'
    if tags=={b'File',b'eliF'}:return 'elif-plain'
    if tags=={b'File',b'Yuzu'}:return 'yuzu-names'
    if tags=={b'File'}:return 'plain'
    raise ValueError(f'unsupported XP3 metadata/filter tags: {sorted(tags)!r}; an unknown index chunk needs its '
                     'layout and name/filter semantics established from evidence before an adapter is added')


HXV4_HINT=('Hxv4 requires static key/identity context: run python -m python.engines.kirikiri_hxv4_text extract '
           '"<this archive>" "<new output dir>" --exe "<game exe>" for supported PSB SCN (usually scn.xp3), or '
           'python.archives.kirikiri_hxv4_archive for resources')


def read_index(stream, profile='auto'):
    detected=detect(stream)
    if detected=='hxv4':raise ValueError(HXV4_HINT)
    if profile!='auto' and profile!=detected:raise ValueError('XP3 profile conflicts with index evidence')
    if detected=='senren-cx':return detected,kirikiri_senren.read_index(stream)
    return detected,kirikiri_elif.read_index(stream,mapping_tag=MAPPED.get(detected,b'eliF'))


def read_member(stream, entry, profile, filter_spec=None):
    if filter_spec is not None:
        validate(filter_spec)
        if profile not in FILTERABLE:raise ValueError('explicit byte filter conflicts with specialized archive adapter')
        return kirikiri_filtered.read_member(stream,entry,filter_spec)
    if profile=='senren-cx':return kirikiri_senren.read_member(stream,entry,kirikiri_senren.default_cipher())
    if profile in FILTERABLE:
        # Caller must also parse the selected member as PSB. Any actual cipher
        # causes the mandatory plaintext checksum or inner-format check to fail.
        return kirikiri_elif.read_member(stream,entry,marked_plaintext=True)
    raise ValueError('unsupported XP3 filter')


def build(files, profile, filter_spec=None):
    if profile in MAPPED:return kirikiri_elif.build(files,mapping_tag=MAPPED[profile],filter_spec=filter_spec)
    if filter_spec is not None:
        validate(filter_spec)
        if profile!='plain':raise ValueError('explicit filter writer requires a standard or name-mapped File index output')
        return kirikiri_filtered.build(files,filter_spec)
    if profile=='senren-cx':return kirikiri_senren.build(files,kirikiri_senren.default_cipher())
    if profile=='plain':return xp3.build(files,filter_name='none',compress_contents=True)
    raise ValueError('unsupported XP3 writer profile')
