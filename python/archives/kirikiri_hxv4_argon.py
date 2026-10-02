"""Fixed Hxv4 Argon2i v1.3: p=1, m=8 KiB, t=3, output=64 bytes.

Independent RFC 9106 algorithm implementation using hashlib.blake2b.
Intentionally not a general password-hashing API or configurable KDF.
"""
import hashlib
import struct

MASK=(1<<64)-1


def expand(data,size):
    value=struct.pack('<I',size)+data
    if size<=64:return hashlib.blake2b(value,digest_size=size).digest()
    value=hashlib.blake2b(value).digest();out=bytearray()
    while len(out)+64<size:
        out+=value[:32]
        if len(out)+64<size:value=hashlib.blake2b(value).digest()
    return bytes(out)+hashlib.blake2b(value,digest_size=size-len(out)).digest()


def compress(left,right,old=None):
    original=[a^b for a,b in zip(left,right)];v=list(original)
    def add(a,b):return (a+b+2*(a&0xffffffff)*(b&0xffffffff))&MASK
    def rr(x,n):return ((x>>n)|(x<<(64-n)))&MASK
    def g(a,b,c,d):
        v[a]=add(v[a],v[b]);v[d]=rr(v[d]^v[a],32)
        v[c]=add(v[c],v[d]);v[b]=rr(v[b]^v[c],24)
        v[a]=add(v[a],v[b]);v[d]=rr(v[d]^v[a],16)
        v[c]=add(v[c],v[d]);v[b]=rr(v[b]^v[c],63)
    def permutation(indices):
        for group in ((0,4,8,12),(1,5,9,13),(2,6,10,14),(3,7,11,15),(0,5,10,15),(1,6,11,12),(2,7,8,13),(3,4,9,14)):
            g(*(indices[i] for i in group))
    for row in range(8):permutation(list(range(row*16,row*16+16)))
    for col in range(8):permutation([row*16+col*2+j for row in range(8) for j in range(2)])
    if old is None:old=[0]*128
    return [a^b^c for a,b,c in zip(original,v,old)]


def derive(password,salt):
    if len(password)>65536 or len(salt)!=16:raise ValueError('Hxv4 Argon2 input bounds')
    header=struct.pack('<6I',1,64,8,3,19,1)
    header+=struct.pack('<I',len(password))+password+struct.pack('<I',len(salt))+salt+bytes(8)
    h0=hashlib.blake2b(header).digest();blocks=[[0]*128 for _ in range(8)]
    for i in (0,1):blocks[i]=list(struct.unpack('<128Q',expand(h0+struct.pack('<II',i,0),1024)))
    zero=[0]*128
    for turn in range(3):
        for section in range(4):
            address_input=[turn,0,section,8,3,1,1]+[0]*121
            address=compress(zero,compress(zero,address_input))
            start=2 if turn==0 and section==0 else 0
            for i in range(start,2):
                current=section*2+i
                area=section*2+i-1 if turn==0 else 8-2+i-1
                pseudo=address[i]&0xffffffff
                relative=area-1-((area*((pseudo*pseudo)>>32))>>32)
                begin=0 if turn==0 else ((section+1)*2)%8
                reference=(begin+relative)%8
                blocks[current]=compress(blocks[(current-1)%8],blocks[reference],blocks[current] if turn else None)
    return expand(struct.pack('<128Q',*blocks[-1]),64)
