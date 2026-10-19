"""Synthetic TJS2100 bytecode for the bounded decompiler; no game data used."""
import struct
import unittest

from python.engines.kirikiri_tjs_decompile import Unsupported, decompile, info, strings
from python.engines.kirikiri_tjs_inspect import OPS, parse

OP = {name: number for number, name in enumerate(OPS)}


def u32(value): return struct.pack('<I', value & 0xffffffff)
def i32(value): return struct.pack('<i', value)
def i16(value): return struct.pack('<h', value)


def chunk(tag, payload):
    return tag + u32(len(payload) + 8) + payload


def data_chunk(strings=(), integers=(), reals=(), octets=()):
    payload = u32(0) + u32(0)
    payload += u32(len(integers)) + b''.join(i32(value) for value in integers)
    payload += u32(0)
    payload += u32(len(reals)) + b''.join(struct.pack('<d', value) for value in reals)
    payload += u32(len(strings))
    for text in strings:
        units = text.encode('utf-16le')
        payload += u32(len(units) // 2) + units
        if len(units) // 2 % 2:
            payload += b'\0\0'
    payload += u32(len(octets))
    for blob in octets:
        payload += u32(len(blob)) + blob + bytes((-len(blob)) % 4)
    return chunk(b'DATA', payload)


def code_object(parent, name, context, arg_count, code, constants, max_var=10, collapse=-1,
                setter=-1, getter=-1):
    header = b''.join(i32(value) for value in (
        parent, name, context, max_var, 2, 8, arg_count, 0, collapse, setter, getter, -1))
    header += u32(0) + u32(len(code)) + b''.join(i16(value) for value in code)
    if len(code) % 2:
        header += b'\0\0'
    header += u32(len(constants))
    header += b''.join(struct.pack('<hh', ty, index) for ty, index in constants)
    header += u32(0) + u32(0)
    return b'TJS2' + u32(len(header) + 8) + header


def bytecode(strings, integers, objects, top=0):
    payload = i32(top) + u32(len(objects)) + b''.join(objects)
    body = data_chunk(strings, integers) + chunk(b'OBJS', payload)
    return b'TJS2100\0' + u32(len(body) + 12) + body


def ins(name, *operands):
    return [OP[name], *operands]


def rel(code, target, at):
    code[at + 1] = target - at
    return code


TOP = code_object(-1, 0, 0, 0, ins('RET'), [], max_var=1)


def program(code, name='f', args=1, constants=(), strings=None, integers=(), others=()):
    pool = ['top', name] + list(strings or ())
    objects = [TOP, code_object(0, 1, 1, args, code, constants)] + list(others)
    return bytecode(pool, integers, objects)


class TjsDecompileTests(unittest.TestCase):
    def test_expression_and_return(self):
        data = program(ins('CONST', 1, 0) + ins('ADD', 1, -3) + ins('SRV', 1) + ins('RET'),
                       constants=[(8, 0)], integers=[1])
        self.assertIn('function f(arg0) {\n    return 1 + arg0;\n}', decompile(data))

    def test_if_else_and_locals(self):
        code = ins('CONST', 1, 0) + ins('CP', -4, 1) + ins('CGT', -3, -4) + ins('JF', 0)
        code += ins('CONST', -4, 1) + ins('JMP', 0) + ins('CONST', -4, 2) + ins('SRV', -4) + ins('RET')
        rel(code, 16, 9)
        rel(code, 22, 14)
        text = decompile(program(code, name='g', constants=[(8, 0), (8, 1), (8, 2)],
                                 integers=[1, 2, 3]))
        self.assertIn('var local0 = 1;', text)
        self.assertIn('if (arg0 <= local0) {\n        local0 = 2;\n    } else {\n'
                      '        local0 = 3;\n        return local0;\n    }', text)

    def test_while_and_do_while(self):
        code = ins('CONST', 1, 0) + ins('CGT', -3, 1) + ins('JNF', 0) + ins('DEC', -3) \
            + ins('JMP', 0) + ins('SRV', -3) + ins('RET')
        rel(code, 12, 6)
        rel(code, 3, 10)
        self.assertIn('while (arg0 > 0) {\n        arg0--;\n    }',
                      decompile(program(code, name='w', constants=[(8, 0)], integers=[0])))

        code = ins('CONST', 1, 0) + ins('DEC', -3) + ins('CGT', -3, 1) + ins('JF', 0) \
            + ins('SRV', -3) + ins('RET')
        rel(code, 3, 8)
        self.assertIn('do {\n        arg0--;\n    } while (arg0 > 0);',
                      decompile(program(code, name='h', constants=[(8, 0)], integers=[0])))

    def test_or_chain_becomes_one_condition(self):
        code = ins('TT', -3) + ins('JF', 0) + ins('TT', -4) + ins('JNF', 0) + ins('CONST', -5, 0) \
            + ins('JMP', 0) + ins('CONST', -5, 1) + ins('SRV', -5) + ins('RET')
        rel(code, 8, 2)
        rel(code, 13, 6)
        rel(code, 18, 11)
        text = decompile(program(code, name='o', args=2, constants=[(8, 0), (8, 1)],
                                 integers=[1, 2]))
        self.assertIn('if (arg0 || arg1) {', text)
        self.assertNotIn('goto', text)

    def test_class_member_and_method(self):
        class_code = ins('CONST', 1, 0) + ins('SPDS', -1, 1, 1)
        method_code = ins('GPD', 1, -1, 0) + ins('SRV', 1) + ins('RET')
        cls = code_object(0, 1, 6, 0, class_code, [(8, 0), (3, 3)])
        method = code_object(1, 2, 1, 1, method_code, [(3, 3)])
        text = decompile(bytecode(['top', 'C', 'method', 'member'], [7], [TOP, cls, method]))
        self.assertIn('class C {', text)
        self.assertIn('var member = 7;', text)
        self.assertIn('function method(arg0) {\n        return this.member;\n    }', text)

    def test_constant_array_literal_with_sparse_tail(self):
        code = (ins('GLOBAL', 1) + ins('GPD', 2, 1, 0) + ins('NEW', 3, 2, 0)
                + ins('CONST', 4, 1) + ins('CONST', 5, 2) + ins('SPIS', 3, 4, 5)
                + ins('INC', 4) + ins('CONST', 5, 3) + ins('SPIS', 3, 4, 5)
                + ins('INC', 4) + ins('SPIS', 3, 4, 0) + ins('INC', 4)
                + ins('SPD', -1, 4, 3) + ins('RET'))
        text = decompile(program(code, name='f', args=0,
                                 constants=[(3, 2), (8, 0), (3, 3), (3, 4), (3, 5)],
                                 strings=['Array', 'a', 'b', 'arr'], integers=[0]))
        self.assertIn('this.arr = ["a", "b", void];', text)

    def test_dead_call_result_still_emits_the_call(self):
        code = ins('CALLD', 1, -1, 0, 0) + ins('RET')
        text = decompile(program(code, name='f', args=0, constants=[(3, 2)],
                                 strings=['call']))
        self.assertIn('this.call();', text)

    def test_assignment_value_is_not_evaluated_twice(self):
        cls = code_object(0, 1, 6, 0, ins('RET'), [])
        code = (ins('CONST', 1, 0) + ins('NEW', 2, 1, 0) + ins('SPD', -1, 1, 2)
                + ins('SRV', 2) + ins('RET'))
        fn = code_object(0, 2, 1, 0, code, [(2, 1), (3, 3)])
        text = decompile(bytecode(['top', 'C', 'f', 'btn'], [], [TOP, cls, fn]))
        self.assertIn('this.btn = new C();\n    return this.btn;', text)
        self.assertEqual(text.count('new C()'), 1)

    def test_try_catch(self):
        code = ins('ENTRY', 0, -4) + ins('CONST', -5, 0) + ins('EXTRY') + ins('JMP', 0) \
            + ins('CONST', -5, 1) + ins('SRV', -5) + ins('RET')
        rel(code, 9, 0)
        rel(code, 15, 7)
        text = decompile(program(code, name='t', args=0, constants=[(8, 0), (8, 1)],
                                 integers=[1, 2]))
        self.assertIn('try {\n        var local2 = 1;\n    } catch (local1) {', text)

    def test_strings_and_info(self):
        data = program(ins('CONST', 1, 0) + ins('GPD', 0, 1, 1) + ins('RET'),
                       name='f', constants=[(3, 2), (3, 3)], strings=['member', 'text'])
        rows = strings(data)
        self.assertEqual([row['text'] for row in rows], ['member', 'text'])
        self.assertEqual(rows[0]['opcode'], 'CONST')
        self.assertIn('function', info(data))

    def test_class_property_accessors(self):
        cls = code_object(0, 1, 6, 0, ins('RET'), [])
        prop = code_object(1, 2, 3, 0, ins('RET'), [], setter=4, getter=3)
        getter = code_object(2, 3, 5, 0, ins('CONST', 1, 0) + ins('SRV', 1) + ins('RET'), [(8, 0)])
        setter = code_object(2, 4, 4, 1, ins('RET'), [])
        text = decompile(bytecode(['top', 'C', 'p', 'get_p', 'set_p'], [5],
                                  [TOP, cls, prop, getter, setter]))
        self.assertIn('property p {', text)
        self.assertIn('getter() {\n            return 5;\n        }', text)
        self.assertIn('setter(arg0) {', text)

    def test_collapsed_argument_list_is_rejected(self):
        obj = code_object(0, 1, 1, 1, ins('RET'), [], collapse=3)
        data = bytecode(['top', 'f'], [], [TOP, obj])
        with self.assertRaises(Unsupported):
            decompile(data)

    def test_unsupported_opcode_is_reported(self):
        data = program(ins('EVAL', 1) + ins('RET'), name='u', args=0)
        with self.assertRaises(Unsupported) as raised:
            decompile(data)
        self.assertIn('EVAL', str(raised.exception))

    def test_parse_keeps_object_metadata(self):
        top, objects = parse(program(ins('RET'), name='f', args=2))
        self.assertEqual(objects[1]['arg_count'], 2)
        self.assertEqual(objects[1]['context'], 1)
        self.assertEqual(objects[1]['variable_reserve'], 2)


if __name__ == '__main__':
    unittest.main()
