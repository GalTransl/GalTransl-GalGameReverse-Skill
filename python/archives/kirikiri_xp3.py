"""Kirikiri XP3 capability dispatch, independent of game directory names.

Supports standard/eliF plaintext and the verified sen: Cx profile. Adding a
filter belongs here or in a leaf adapter, not in another game's batch script.
"""
import struct
from . import xp3, kirikiri_elif, kirikiri_senren, kirikiri_filtered
from .kirikiri_filters import validate

FORMATS = ('plain', 'elif-plain', 'senren-cx')


def detect(stream):
    stream.seek(0,2);size=stream.tell()
    def read(at,count):
        if at<0 or count<0 or at+count>size or count>16<<20:raise ValueError('XP3 probe bounds')
        stream.seek(at);data=stream.read(count)
        if len(data)!=count:raise ValueError('truncated XP3 probe')
        return data
    if read(0,11)!=xp3.MAGIC:raise ValueError('not XP3')
    at,=struct.unpack('<Q',read(11,8))
    if at<19:raise ValueError('XP3 index overlaps header')
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
    if tags=={b'File'}:return 'plain'
    raise ValueError(f'unsupported XP3 metadata/filter tags: {tags!r}')


def read_index(stream, profile='auto'):
    detected=detect(stream)
    if detected=='hxv4':raise ValueError('Hxv4 requires static key/identity context: use python.engines.kirikiri_hxv4_text for supported PSB SCN, or python.archives.kirikiri_hxv4_archive for resources')
    if profile!='auto' and profile!=detected:raise ValueError('XP3 profile conflicts with index evidence')
    module=kirikiri_senren if detected=='senren-cx' else kirikiri_elif
    return detected,module.read_index(stream)


def read_member(stream, entry, profile, filter_spec=None):
    if filter_spec is not None:
        validate(filter_spec)
        if profile not in ('plain','elif-plain'):raise ValueError('explicit byte filter conflicts with specialized archive adapter')
        return kirikiri_filtered.read_member(stream,entry,filter_spec)
    if profile=='senren-cx':return kirikiri_senren.read_member(stream,entry,kirikiri_senren.default_cipher())
    if profile in ('plain','elif-plain'):
        # Caller must also parse the selected member as PSB. Any actual cipher
        # causes the mandatory plaintext checksum or inner-format check to fail.
        return kirikiri_elif.read_member(stream,entry,marked_plaintext=True)
    raise ValueError('unsupported XP3 filter')


def build(files, profile, filter_spec=None):
    if filter_spec is not None:
        validate(filter_spec)
        if profile!='plain':raise ValueError('explicit filter writer requires standard File index output')
        return kirikiri_filtered.build(files,filter_spec)
    if profile=='senren-cx':return kirikiri_senren.build(files,kirikiri_senren.default_cipher())
    if profile=='elif-plain':return kirikiri_elif.build(files)
    if profile=='plain':return xp3.build(files,filter_name='none',compress_contents=True)
    raise ValueError('unsupported XP3 writer profile')
