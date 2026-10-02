"""Static TJS instruction boundaries and constant references, without execution."""
import struct
import unittest
from python.engines.kirikiri_tjs_inspect import parse, instructions, disassemble


def fixture():
    i = lambda n: struct.pack('<i', n)
    chunk = lambda tag, data: tag+i(len(data)+8)+data
    text = 'patch.xp3'.encode('utf-16le')
    pool = i(0)*5+i(1)+i(len(text)//2)+text
    pool += bytes((-len(pool))%4)+i(0)
    code = struct.pack('<4h',1,1,0,119)
    obj = i(-1)+i(0)+i(0)*10+i(0)+i(4)+code+i(1)+struct.pack('<hh',3,0)+i(0)*2
    body = chunk(b'DATA',pool)+chunk(b'OBJS',i(0)+i(1)+chunk(b'TJS2',obj))
    return b'TJS2100\0'+i(len(body)+12)+body


class TjsInspectTests(unittest.TestCase):
    def test_constants_objects_and_annotation(self):
        data=fixture();top,objects=parse(data)
        self.assertEqual(top,0)
        self.assertEqual(objects[0]['constants'],['patch.xp3'])
        self.assertIn("CONST [1, 0] ; 'patch.xp3'",disassemble(data))
        for bad in (data[:-1],b'wrong'):
            with self.assertRaises(ValueError): parse(bad)

    def test_calls_and_branch_targets(self):
        self.assertEqual(instructions([100,0,1,2,1,3,119])[0],(0,'CALLD',[0,1,2,1,3]))
        self.assertEqual(instructions([17,2,119])[-1],(2,'RET',[]))
        for code in ([128],[1,2],[100,0,1,2,4],[17,1,119]):
            with self.assertRaises(ValueError): instructions(code)


if __name__=='__main__': unittest.main()
