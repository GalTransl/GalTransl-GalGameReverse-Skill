"""Static Hxv4 index and name evidence; never executes game code.

Key derivation/name hashes: msg-tool xp3/crypt/cx.rs, GPL-3.0-or-later.
Index layout: GARbro-Mod HxCrypt.cs (MIT notice in xp3.py).
Fixed-parameter Argon2i derivation is implemented with the standard library.
Payload operations live in kirikiri_hxv4_payload.py.
"""
import hashlib
import hmac
import struct
import zlib
from .xp3 import MAGIC, _chunks, _inflate


def rot(v,n,bits=32):
    return ((v<<n)|(v>>(bits-n)))&((1<<bits)-1)


def rounds(state,count=20):
    x=list(state)
    def qr(a,b,c,d):
        x[a]=(x[a]+x[b])&0xffffffff;x[d]=rot(x[d]^x[a],16)
        x[c]=(x[c]+x[d])&0xffffffff;x[b]=rot(x[b]^x[c],12)
        x[a]=(x[a]+x[b])&0xffffffff;x[d]=rot(x[d]^x[a],8)
        x[c]=(x[c]+x[d])&0xffffffff;x[b]=rot(x[b]^x[c],7)
    for _ in range(count//2):
        for args in ((0,4,8,12),(1,5,9,13),(2,6,10,14),(3,7,11,15),(0,5,10,15),(1,6,11,12),(2,7,8,13),(3,4,9,14)):qr(*args)
    return x


def chacha(data,key,nonce,counter=1,count=20,xor_counter=False):
    if len(key)!=32 or len(nonce)!=12:raise ValueError('ChaCha key/nonce size')
    prefix=list(struct.unpack('<12I',b'expand 32-byte k'+key));n=list(struct.unpack('<3I',nonce));out=bytearray()
    for i in range(0,len(data),64):
        ctr=counter^(i//64) if xor_counter else counter+i//64
        if ctr>0xffffffff:raise ValueError('ChaCha counter overflow')
        state=prefix+[ctr]+n;block=struct.pack('<16I',*((a+b)&0xffffffff for a,b in zip(state,rounds(state,count))))
        out.extend(a^b for a,b in zip(data[i:i+64],block))
    return bytes(out)


def hchacha(key,nonce):
    state=struct.unpack('<16I',b'expand 32-byte k'+key+nonce)
    x=rounds(state);return struct.pack('<8I',*(x[i] for i in (0,1,2,3,12,13,14,15)))


def poly1305(data,key):
    """RFC 8439 authenticator; callers derive a fresh one-time key per nonce."""
    if len(key)!=32:raise ValueError('Poly1305 key size')
    r=int.from_bytes(key[:16],'little')&0x0ffffffc0ffffffc0ffffffc0fffffff
    s=int.from_bytes(key[16:],'little');acc=0
    for at in range(0,len(data),16):
        acc=(acc+int.from_bytes(data[at:at+16]+b'\1','little'))*r%((1<<130)-5)
    return ((acc+s)&((1<<128)-1)).to_bytes(16,'little')


def index_tag(ciphertext,key,nonce):
    """Hx index uses ChaCha20-Poly1305, empty AAD, tag prepended to ciphertext.

    Nonce/key selection stays archive-profile specific. Authenticating a new
    artifact does not prove the game will mount it or accept an external .sig.
    """
    one_time_key=chacha(bytes(32),key,nonce,counter=0)
    message=ciphertext+bytes(-len(ciphertext)%16)+struct.pack('<QQ',0,len(ciphertext))
    return poly1305(message,one_time_key)


def triple32(v):
    for shift,mul in ((17,0xed5ad4bb),(11,0xac4c1b51),(15,0x31848bab)):
        v=((v^(v>>shift))*mul)&0xffffffff
    return v^(v>>14)


def fnv_blake(data,base):
    h=((0x811c9dc5^base)*0x1000193)&0xffffffff;out=bytearray(32)
    for i,b in enumerate(data):
        h=triple32(h^b)
        for j,v in enumerate(h.to_bytes(4,'little')):out[(i*4)%32+j]^=v
    return hashlib.blake2s(data+out).digest()


def derive(package):
    from .kirikiri_hxv4_argon import derive as argon2i
    keys={'bootStrap','warning','params','archiveUniqueKey','upperKey'}
    if set(package)-keys or not keys-{'upperKey'}<=set(package):raise ValueError('Hxv4 package fields')
    params=bytes.fromhex(package['params'])
    if len(params)!=22:raise ValueError('Hxv4 params length')
    bw=(package['bootStrap']+package['warning']).encode('utf-16le')
    unique=package['archiveUniqueKey'].encode('utf-16le')
    if max(len(bw),len(unique))>65536:raise ValueError('Hxv4 package budget')
    upper=bytes.fromhex(package.get('upperKey') or '0000000000000000')
    if len(upper)!=8:raise ValueError('Hxv4 upper key size')
    if not any(upper):upper=bytes.fromhex('ceeaaf2cefbeadde')
    lower=argon2i(bw,hashlib.sha3_224(params).digest()[:16])
    upper=fnv_blake(upper,int.from_bytes(upper[:4],'little'))
    buf=bytearray(fnv_blake(bw,0)+fnv_blake(params,1)+fnv_blake(unique,2))
    for i in range(64):buf[i]^=lower[i%32]
    for i in range(32):buf[64+i]^=upper[i]
    key=bytes(buf[:32]);na=bytes(buf[32:64]);nb=bytes(buf[64:96])
    drip=hashlib.shake_256(lower).digest(8192)
    block=bytes(a^b for a,b in zip(drip[:4096],drip[4096:])) if params[17]&1 else drip[:4096]
    return {'key':key,'nonce_a':na,'nonce_b':nb,'index_a':hchacha(key,na[:16]),'index_b':hchacha(key,nb[:16]),
            'control_block':block,'filter_key':int.from_bytes(nb[:8],'little'),'params':params}


def siphash(data):
    v=[0x736f6d6570736575,0x646f72616e646f6d,0x6c7967656e657261,0x7465646279746573];mask=(1<<64)-1
    def rnd():
        v[0]=(v[0]+v[1])&mask;v[1]=rot(v[1],13,64)^v[0];v[0]=rot(v[0],32,64)
        v[2]=(v[2]+v[3])&mask;v[3]=rot(v[3],16,64)^v[2]
        v[0]=(v[0]+v[3])&mask;v[3]=rot(v[3],21,64)^v[0]
        v[2]=(v[2]+v[1])&mask;v[1]=rot(v[1],17,64)^v[2];v[2]=rot(v[2],32,64)
    tail=data[len(data)//8*8:];words=[int.from_bytes(data[i:i+8],'little') for i in range(0,len(data)-len(tail),8)]
    words.append(int.from_bytes(tail,'little')|((len(data)&255)<<56))
    for m in words:
        v[3]^=m;rnd();rnd();v[0]^=m
    v[2]^=255
    for _ in range(4):rnd()
    return v[0]^v[1]^v[2]^v[3]


def name_hash(name,salt='xp3hnp'):
    return hashlib.blake2s((name.lower()+salt).encode('utf-16le')).hexdigest().upper()


def path_hash(name,salt='xp3hnp'):
    return siphash((name.lower()+salt).encode('utf-16le')).to_bytes(8,'little').hex().upper()


def deserialize(data):
    at=0;nodes=0
    def read(size):
        nonlocal at
        if size<0 or at+size>len(data):raise ValueError('Hx object bounds')
        value=data[at:at+size];at+=size;return value
    def number():return int.from_bytes(read(4),'big')
    def value(depth=0):
        nonlocal nodes
        nodes+=1
        if depth>64 or nodes>1000000:raise ValueError('Hx object budget')
        tag=read(1)[0]
        if tag in (0,1):return None
        if tag==2:return read(number()*2).decode('utf-16le')
        if tag==3:return read(number())
        if tag==4:return int.from_bytes(read(8),'big',signed=True)
        if tag==5:return struct.unpack('>d',read(8))[0]
        if tag==0x81:
            n=number()
            if n>200000:raise ValueError('Hx array budget')
            return [value(depth+1) for _ in range(n)]
        raise ValueError('unsupported Hx object tag')
    root=value()
    if at!=len(data):raise ValueError('Hx object trailing bytes')
    return root


def read_index(stream,keys=None):
    stream.seek(0,2);size=stream.tell()
    def read(at,n):
        if at<0 or n<0 or at+n>size or n>16<<20:raise ValueError('Hx index bounds/budget')
        stream.seek(at);value=stream.read(n)
        if len(value)!=n:raise ValueError('Hx index truncated')
        return value
    if read(0,11)!=MAGIC:raise ValueError('not XP3')
    at,=struct.unpack('<Q',read(11,8))
    if read(at,9)==b'\x80'+bytes(8):at,=struct.unpack('<Q',read(at+9,8))
    flag=read(at,1)[0]
    if flag==1:
        packed,raw=struct.unpack('<QQ',read(at+1,16));index=_inflate(read(at+17,packed),raw,16<<20)
    elif flag==0:
        n,=struct.unpack('<Q',read(at+1,8));index=read(at+9,n)
    else:raise ValueError('unknown XP3 index flag')
    files=[];hx=None
    for tag,body in _chunks(index):
        if tag==b'Hxv4':
            if hx is not None or len(body)!=14:raise ValueError('Hx extension layout')
            hx=struct.unpack('<QIH',body)
        elif tag==b'File':
            fields=dict(_chunks(body));info=fields[b'info'];flags,raw,packed,units=struct.unpack_from('<IQQH',info)
            alias=info[22:22+units*2].decode('utf-16le')
            if len(info) not in (22+units*2,24+units*2):raise ValueError('Hx alias length')
            segments=list(struct.iter_unpack('<IQQQ',fields[b'segm']))
            if fields[b'adlr']==bytes.fromhex('e4929768') and raw==packed==910 and segments==[(0,88,157,157)]:
                if read(40,7)!=b'\x89PNG\n\x1a\n':raise ValueError('unknown Hx security stub')
                continue
            if sum(s[2] for s in segments)!=raw or sum(s[3] for s in segments)!=packed:raise ValueError('Hx segment totals')
            for f,o,r,p in segments:
                if f not in (0,1) or o<19 or o+p>size:raise ValueError('Hx segment range')
            files.append({'alias':alias,'size':raw,'flags':flags,'checksum':struct.unpack('<I',fields[b'adlr'])[0],'segments':segments})
        else:raise ValueError('unknown Hx index record')
    if hx is None:raise ValueError('missing Hxv4 extension')
    result={'files':files,'hx_offset':hx[0],'hx_size':hx[1],'hx_flags':hx[2]}
    encrypted=read(hx[0],hx[1])
    if keys is None:return result
    if hx[2] not in (0,1) or len(encrypted)<20:raise ValueError('Hx flags/header')
    suffix='a' if hx[2] else 'b'
    key=keys['index_'+suffix];nonce=bytes(4)+keys['nonce_'+suffix][16:24]
    if not hmac.compare_digest(encrypted[:16],index_tag(encrypted[16:],key,nonce)):
        raise ValueError('Hx index Poly1305 authentication failed')
    plain=chacha(encrypted[16:],key,nonce)
    length=int.from_bytes(plain[:4],'little')
    root=deserialize(_inflate(plain[4:],length,16<<20))
    if not isinstance(root,list) or len(root)%2:raise ValueError('Hx root shape')
    mapping={}
    for path,entries in zip(root[::2],root[1::2]):
        if not isinstance(path,bytes) or len(path)!=8 or not isinstance(entries,list) or len(entries)%2:raise ValueError('Hx path shape')
        for name,entry in zip(entries[::2],entries[1::2]):
            if not isinstance(name,bytes) or len(name)!=32 or not isinstance(entry,list) or len(entry)<2:raise ValueError('Hx file shape')
            ident,key=entry[:2]
            if type(ident) is not int or type(key) is not int or not 0<=ident<=0x1ffffffff:raise ValueError('Hx identity/key')
            n=ident&0xffffffff;alias=''
            while True:
                alias+=chr((n&0x3fff)+0x5000);n>>=14
                if not n:break
            if alias in mapping:raise ValueError('duplicate Hx identity')
            mapping[alias]={'path_hash':path.hex().upper(),'name_hash':name.hex().upper(),'id':ident,'key':key}
    for f in files:
        if f['alias'] in mapping:f.update(mapping[f['alias']])
    result['mapped']=sum('name_hash' in f for f in files)
    return result
