"""Bounded TJS2100 disassembly for static loader research; never executes code.

Layout/opcode sizes adapted from Cxdec_Tools src/struct/tjs.rs, MIT,
Copyright (c) 2026 bfloat16. See provenance/kirikiri-cxdec-tools-MIT.txt.
No semantic decompiler or bytecode writer is implied.
"""
import argparse
import struct
from pathlib import Path

OPS = ('NOP CONST CP CL CCL TT TF CEQ CDEQ CLT CGT SETF SETNF LNOT NF JF JNF JMP '
       'INC INCPD INCPI INCP DEC DECPD DECPI DECP').split()
for base in 'LOR LAND BOR BXOR BAND SAR SAL SR ADD SUB MOD DIV IDIV MUL'.split():
    OPS.extend([base, base+'PD', base+'PI', base+'P'])
OPS += ('BNOT TYPEOF TYPEOFD TYPEOFI EVAL EEXP CHKINS ASC CHR NUM CHS INV CHKINV INT REAL STR OCTET '
        'CALL CALLD CALLI NEW GPD SPD SPDE SPDEH GPI SPI SPIE GPDS SPDS GPIS SPIS SETP GETP DELD DELI '
        'SRV RET ENTRY EXTRY THROW CHGTHIS GLOBAL ADDCI REGMEMBER DEBUGGER').split()


class Reader:
    def __init__(self, data): self.data, self.at = data, 0
    def take(self, n):
        if n < 0 or self.at+n > len(self.data): raise ValueError('TJS bounds')
        data = self.data[self.at:self.at+n]; self.at += n; return data
    def num(self): return struct.unpack('<i', self.take(4))[0]
    def count(self):
        n = self.num()
        if not 0 <= n <= 1000000: raise ValueError('TJS count budget')
        return n
    def align(self): self.take((-self.at) % 4)
    def chunk(self, tag):
        if self.take(4) != tag: raise ValueError('TJS chunk tag')
        size = self.count()
        if size < 8: raise ValueError('TJS chunk size')
        return self.take(size-8)


def parse(data):
    if len(data) > 32 << 20: raise ValueError('TJS file budget')
    r = Reader(data)
    if r.take(8) != b'TJS2100\0' or r.num() != len(data): raise ValueError('TJS header')
    p = Reader(r.chunk(b'DATA')); pools = {}
    for ty, fmt in ((6,'b'),(7,'h'),(8,'i'),(9,'q'),(5,'d')):
        n = p.count(); pools[ty] = list(struct.unpack('<'+fmt*n, p.take(n*struct.calcsize(fmt)))); p.align()
    pools[3] = []
    for _ in range(p.count()): pools[3].append(p.take(p.count()*2).decode('utf-16le')); p.align()
    pools[4] = []
    for _ in range(p.count()): pools[4].append(p.take(p.count()).hex()); p.align()
    if p.at != len(p.data): raise ValueError('TJS DATA trailing bytes')
    p = Reader(r.chunk(b'OBJS')); top = p.num(); objects = []
    for ident in range(p.count()):
        if p.take(4) != b'TJS2': raise ValueError('TJS object tag')
        declared = p.count(); start = p.at
        header = [p.num() for _ in range(12)]
        p.take(p.count()*8)
        count = p.count(); code = list(struct.unpack('<'+'h'*count,p.take(count*2))); p.align()
        constants = []
        for _ in range(p.count()):
            ty, ix = struct.unpack('<hh', p.take(4))
            if ty in pools:
                if not 0 <= ix < len(pools[ty]): raise ValueError('TJS constant index')
                constants.append(pools[ty][ix])
            elif ty == 0: constants.append(None)
            elif ty == 1: constants.append({'null_object':ix})
            elif ty in (2,10): constants.append({'object':ix})
            else: raise ValueError('unknown TJS variant')
        p.take(p.count()*4); p.take(p.count()*8)
        if p.at-start not in (declared, declared-8): raise ValueError('TJS object length')
        name = pools[3][header[1]] if header[1] >= 0 else None
        objects.append(dict(id=ident,name=name,parent=header[0],code=code,constants=constants))
    if p.at != len(p.data) or r.at != len(data): raise ValueError('TJS trailing bytes')
    if not 0 <= top < len(objects): raise ValueError('TJS top object')
    return top, objects


def instructions(code):
    at = 0; out = []
    while at < len(code):
        op = code[at]
        if not 0 <= op < 128: raise ValueError('unknown TJS opcode')
        name = OPS[op]
        if name in ('NOP','NF','RET','EXTRY','REGMEMBER','DEBUGGER'): size = 1
        elif op in (99,100,101,102):
            base = 5 if op in (100,101) else 4
            if at+base > len(code): raise ValueError('truncated TJS call')
            argc = code[at+base-1]
            if argc == -1: size = base
            elif argc == -2:
                if at+base >= len(code) or code[at+base]<0: raise ValueError('TJS call expansion')
                size = base+1+code[at+base]*2
            elif argc >= 0: size = base+argc
            else: raise ValueError('TJS argument count')
        elif 26 <= op <= 81: size = (3,5,5,4)[(op-26)%4]
        elif name in ('CONST','CP','CEQ','CDEQ','CLT','CGT','CHKINS','CHGTHIS','ADDCI','CCL','ENTRY','SETP','GETP','INCP','DECP'): size = 3
        elif name in ('INCPD','DECPD','INCPI','DECPI','GPD','GPDS','GPI','GPIS','SPD','SPDE','SPDEH','SPDS','SPI','SPIE','SPIS','DELD','DELI','TYPEOFD','TYPEOFI'): size = 4
        else: size = 2
        if at+size > len(code): raise ValueError('truncated TJS instruction')
        args = code[at+1:at+size]; out.append((at,name,args)); at += size
    starts = {at for at,_,_ in out}
    for at,name,args in out:
        if name in ('JF','JNF','JMP','ENTRY') and at+args[0] not in starts:
            raise ValueError('TJS branch is not an instruction boundary')
    return out


def disassemble(data):
    top, objects = parse(data); lines = [f'Top object: {top}']
    for obj in objects:
        lines.append(f'\nObject {obj["id"]} {obj["name"]!r} parent={obj["parent"]}')
        for at, name, args in instructions(obj['code']):
            annotation = ''
            index = args[1] if name in ('CONST','SPD','SPDE','SPDEH','SPDS') else args[2] if name in ('GPD','GPDS','CALLD','DELD','TYPEOFD') else None
            if index is not None:
                if not 0 <= index < len(obj['constants']): raise ValueError('TJS operand constant index')
                annotation = ' ; '+repr(obj['constants'][index])
            if name in ('JF','JNF','JMP','ENTRY'): annotation = f' ; -> {at+args[0]}'
            lines.append(f'{at:05d} {name} {args}{annotation}')
    return '\n'.join(lines)+'\n'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('file',type=Path)
    args = parser.parse_args()
    if args.file.stat().st_size > 32 << 20: raise ValueError('TJS file budget')
    print(disassemble(args.file.read_bytes()))
