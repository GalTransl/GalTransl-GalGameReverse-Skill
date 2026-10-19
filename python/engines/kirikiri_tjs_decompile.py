"""Bounded TJS2 (TJS2100) bytecode to readable source reconstruction.

The opcode encoding and VM condition semantics follow the TJS2 implementation in
krkrz (BSD-3-Clause-style Kirikiri license); see provenance/kirikiri-tjs.json.
The structuring, naming and rejection rules are an independent implementation
for this skill.
Only the shapes listed in engines/kirikiri/tjs.md are reconstructed; anything
else raises Unsupported instead of emitting guessed source.  Code is never
executed and the input file is never modified.
"""
from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass
from pathlib import Path

from .kirikiri_tjs_inspect import OPS, disassemble, instructions, parse

# TJS2 operator precedence, low to high.  Parentheses are added whenever a
# child expression binds more weakly than its parent slot.
P_ASSIGN, P_COND, P_OR, P_AND, P_BOR, P_BXOR, P_BAND = 1, 2, 3, 4, 5, 6, 7
P_EQ, P_REL, P_SHIFT, P_ADD, P_MUL, P_UNARY, P_POSTFIX, P_PRIMARY = 8, 9, 10, 11, 12, 13, 14, 15

BINARY_SYMBOLS = {
    'LOR': '||', 'LAND': '&&', 'BOR': '|', 'BXOR': '^', 'BAND': '&',
    'SAR': '>>', 'SAL': '<<', 'SR': '>>>', 'ADD': '+', 'SUB': '-',
    'MOD': '%', 'DIV': '/', 'IDIV': '\\', 'MUL': '*',
}
BINARY_PRECEDENCE = {
    '||': P_OR, '&&': P_AND, '|': P_BOR, '^': P_BXOR, '&': P_BAND,
    '==': P_EQ, '===': P_EQ, '!=': P_EQ, '!==': P_EQ,
    '<': P_REL, '>': P_REL, '<=': P_REL, '>=': P_REL, 'instanceof': P_REL,
    '>>': P_SHIFT, '<<': P_SHIFT, '>>>': P_SHIFT,
    '+': P_ADD, '-': P_ADD, '*': P_MUL, '/': P_MUL, '%': P_MUL, '\\': P_MUL,
}
INVERSE_COMPARISON = {'==': '!=', '!=': '==', '===': '!==', '!==': '===',
                      '<': '>=', '>=': '<', '>': '<=', '<=': '>'}
BINARY_VARIANTS = {}
for _name in BINARY_SYMBOLS:
    BINARY_VARIANTS[_name] = (_name, 0)
    for _suffix, _variant in (('PD', 1), ('PI', 2), ('P', 3)):
        BINARY_VARIANTS[_name + _suffix] = (_name, _variant)

CONTEXT_NAMES = {0: 'top', 1: 'function', 2: 'anonymous-function', 3: 'property',
                 4: 'property-setter', 5: 'property-getter', 6: 'class',
                 7: 'super-class-getter'}

# Instructions that only compute values and may therefore be folded into a
# reconstructed condition.  Anything with an observable side effect is excluded.
PURE_OPS = set('CONST TT TF SETF SETNF LNOT BNOT CHS NUM TYPEOF CHKINV CHKINS '
               'INT REAL STR OCTET GLOBAL CEQ CDEQ CLT CGT NF'.split())
PURE_OPS |= set(BINARY_SYMBOLS)
PURE_OPS |= set(BINARY_VARIANTS)
PURE_OPS |= {'GPD', 'GPDS', 'GPI', 'GPIS', 'TYPEOFD', 'TYPEOFI', 'CP'}


class Unsupported(ValueError):
    """A bytecode shape this module does not reconstruct."""

    def __init__(self, message: str, obj: dict | None = None, addr: int | None = None):
        where = ''
        if obj is not None:
            label = obj.get('name') or f'object#{obj.get("id")}'
            where = label
            if addr is not None:
                where += f' @{addr:05d}'
            where += ': '
        super().__init__(where + message)


@dataclass(frozen=True)
class Expr:
    text: str
    prec: int = P_PRIMARY

    def at(self, parent: int) -> str:
        return f'({self.text})' if self.prec < parent else self.text


TRUE = Expr('true')
FALSE = Expr('false')


def negate(value: Expr) -> Expr:
    if value.text == 'true':
        return FALSE
    if value.text == 'false':
        return TRUE
    if value.prec == P_UNARY and value.text.startswith('!') and not value.text.startswith('!='):
        return Expr(value.text[1:], P_UNARY)
    if value.prec in (P_EQ, P_REL) and ' ' in value.text:
        left, operator, right = value.text.split(' ', 2)
        if operator in INVERSE_COMPARISON:
            return Expr(f'{left} {INVERSE_COMPARISON[operator]} {right}', value.prec)
    return Expr(f'!{value.at(P_UNARY)}', P_UNARY)


def conjunction(left: Expr, right: Expr) -> Expr:
    if left.text == 'true':
        return right
    if right.text == 'true':
        return left
    if left.text == 'false' or right.text == 'false':
        return FALSE
    if left.text == right.text:
        return left
    return Expr(f'{left.at(P_AND)} && {right.at(P_AND + 1)}', P_AND)


def disjunction(left: Expr, right: Expr) -> Expr:
    if left.text == 'false':
        return right
    if right.text == 'false':
        return left
    if left.text == 'true' or right.text == 'true':
        return TRUE
    if left.text == right.text:
        return left
    # A linear short-circuit chain produces a || (!a && b); fold the negation.
    for first, second in ((left, right), (right, left)):
        prefix = f'!{first.text} && '
        if second.prec == P_AND and second.text.startswith(prefix):
            rest = Expr(second.text[len(prefix):], P_AND)
            return Expr(f'{first.at(P_OR)} || {rest.at(P_OR + 1)}', P_OR)
    return Expr(f'{left.at(P_OR)} || {right.at(P_OR + 1)}', P_OR)


def binary(left: Expr, symbol: str, right: Expr) -> Expr:
    precedence = BINARY_PRECEDENCE[symbol]
    return Expr(f'{left.at(precedence)} {symbol} {right.at(precedence + 1)}', precedence)


def unary(symbol: str, value: Expr, postfix: bool = False) -> Expr:
    if postfix:
        return Expr(f'{value.at(P_POSTFIX)}{symbol}', P_POSTFIX)
    return Expr(f'{symbol}{value.at(P_UNARY)}', P_UNARY)


def escape_string(text: str) -> str:
    out = []
    for char in text:
        code = ord(char)
        if char == '\\':
            out.append('\\\\')
        elif char == '"':
            out.append('\\"')
        elif char == '\n':
            out.append('\\n')
        elif char == '\r':
            out.append('\\r')
        elif char == '\t':
            out.append('\\t')
        elif code < 0x20 or 0xD800 <= code <= 0xDFFF:
            out.append(f'\\x{code:02X}' if code <= 0xFF else f'\\u{code:04X}')
        else:
            out.append(char)
    return ''.join(out)


def real_literal(value: float) -> str:
    if math.isinf(value):
        return 'Infinity' if value > 0 else '-Infinity'
    if math.isnan(value):
        return 'NaN'
    text = repr(value)
    if 'e' not in text and 'E' not in text and '.' not in text:
        text += '.0'
    return text


def is_identifier(name: str) -> bool:
    if not name or not name.isascii() or not (name[0].isalpha() or name[0] in '_$'):
        return False
    return all(char.isascii() and (char.isalnum() or char in '_$') for char in name[1:])


@dataclass
class Stmt:
    head: str
    body: list | None = None
    tail: str | None = '}'
    else_head: str | None = None
    else_body: list | None = None


def render(stmts: list[Stmt], indent: int = 0) -> list[str]:
    pad = '    ' * indent
    lines = []
    for stmt in stmts:
        lines.append(pad + stmt.head)
        if stmt.body is not None:
            lines.extend(render(stmt.body, indent + 1))
            if stmt.else_head is not None:
                lines.append(pad + stmt.else_head)
                lines.extend(render(stmt.else_body or [], indent + 1))
            if stmt.tail:
                lines.append(pad + stmt.tail)
        elif stmt.tail:
            lines.append(pad + stmt.tail)
    return lines


def source_registers(ins) -> list[int]:
    """Registers read by one instruction; constant indexes and jump offsets excluded."""
    name, operands = ins[1], ins[2]

    def pick(*indexes):
        return [operands[i] for i in indexes if i < len(operands)]

    if name in ('NOP', 'REGMEMBER', 'DEBUGGER', 'EXTRY', 'CL', 'CCL', 'CONST',
                'GLOBAL', 'SETF', 'SETNF', 'RET', 'ENTRY', 'JMP', 'JF', 'JNF'):
        return []
    if name in ('TT', 'TF', 'LNOT', 'BNOT', 'CHS', 'NUM', 'ASC', 'CHR', 'TYPEOF',
                'CHKINV', 'INT', 'REAL', 'STR', 'OCTET', 'INC', 'DEC', 'INV', 'SRV', 'THROW'):
        return pick(0)
    if name in ('CP', 'GETP'):
        return pick(1)
    if name in ('CEQ', 'CDEQ', 'CLT', 'CGT', 'CHKINS', 'SETP', 'CHGTHIS'):
        return pick(0, 1)
    if name in ('GPD', 'GPDS', 'DELD', 'TYPEOFD'):
        return pick(1)
    if name in ('GPI', 'GPIS', 'DELI', 'TYPEOFI'):
        return pick(1, 2)
    if name in ('SPD', 'SPDE', 'SPDEH', 'SPDS'):
        return pick(0, 2)
    if name in ('SPI', 'SPIE', 'SPIS'):
        return pick(0, 1, 2)
    if name in ('INCPD', 'DECPD', 'INCP', 'DECP'):
        return pick(1)
    if name in ('INCPI', 'DECPI'):
        return pick(1, 2)
    if name == 'CALL':
        return pick(1) + (pick(*range(3, 3 + operands[2])) if operands[2] > 0 else [])
    if name == 'CALLD':
        return pick(1) + (pick(*range(4, 4 + operands[3])) if operands[3] > 0 else [])
    if name == 'CALLI':
        return pick(1, 2) + (pick(*range(4, 4 + operands[3])) if operands[3] > 0 else [])
    if name == 'NEW':
        return pick(1) + (pick(*range(3, 3 + operands[2])) if operands[2] > 0 else [])
    if name in BINARY_VARIANTS:
        variant = BINARY_VARIANTS[name][1]
        if variant == 0:
            return pick(0, 1)
        if variant == 1:
            return pick(1, 3)
        if variant == 2:
            return pick(1, 2, 3)
        return pick(1, 2)
    return pick(0)


@dataclass
class Loop:
    header: int          # instruction index of the loop header block
    latch: int           # block containing the back edge
    body: set            # instruction indices of blocks in the natural loop
    exit_index: int      # first instruction after the loop
    continue_index: int  # where continue jumps


class Method:
    """Reconstruct one code object.  Registers become named locals or temporaries."""

    def __init__(self, program: 'Program', obj: dict, class_context: bool = False):
        self.program = program
        self.obj = obj
        self.class_context = class_context
        if obj.get('collapse_base', -1) >= 0 or obj.get('unnamed_arg_base', 0) > 0:
            raise Unsupported('collapsed or unnamed argument lists are not reconstructed', obj)
        self.insns = instructions(obj['code'])
        self.count = len(self.insns)
        self.addr_index = {ins[0]: i for i, ins in enumerate(self.insns)}
        self.regs: dict[int, Expr] = {}
        self.flag: Expr | None = None
        self.flag_negated = False
        self.declared: set[str] = set(self.argument_names())
        self.out: list[Stmt] = []
        self.loops: list[Loop] = []
        self._address = 0
        self._index = 0
        self._loop_bodies: set[int] = set()
        self._prepare()

    # -- names -----------------------------------------------------------
    def argument_names(self) -> list[str]:
        return [f'arg{i}' for i in range(max(0, self.obj.get('arg_count', 0)))]

    def local_name(self, register: int) -> str:
        index = -register - 3
        args = max(0, self.obj.get('arg_count', 0))
        if index < args:
            return f'arg{index}'
        return f'local{max(0, index - args)}'

    def is_local(self, register: int) -> bool:
        return register < -2

    def read(self, register: int) -> Expr:
        if register == 0:
            return Expr('void')
        if register in (-1, -2):
            return Expr('this')
        if register < -2:
            return Expr(self.local_name(register))
        if register in self.regs:
            return self.regs[register]
        raise Unsupported(f'undefined temporary register {register}', self.obj, self._address)

    def write_register(self, register: int, value: Expr, statement: bool = False):
        if register < -2:
            self.assign_local(register, value)
        elif register > 0:
            self.regs[register] = value
        elif register == 0 and statement:
            self.emit(f'{value.text};')

    def assign_local(self, register: int, value: Expr):
        name = self.local_name(register)
        self.regs[register] = Expr(name)
        if name not in self.declared:
            self.declared.add(name)
            self.emit(f'var {name} = {value.text};')
        else:
            self.emit(f'{name} = {value.text};')

    def clear_local(self, register: int):
        if not self.is_local(register):
            if register > 0:
                self.regs.pop(register, None)
            return
        name = self.local_name(register)
        self.regs[register] = Expr(name)
        if name not in self.declared:
            self.declared.add(name)
            self.emit(f'var {name};')

    # -- constants -------------------------------------------------------
    def constant(self, index: int) -> Expr:
        constants = self.obj['constants']
        if not 0 <= index < len(constants):
            raise Unsupported(f'constant index {index} out of range', self.obj, self._address)
        value = constants[index]
        if value is None:
            return Expr('void')
        if isinstance(value, str):
            return Expr('"' + escape_string(value) + '"')
        if isinstance(value, bytes):
            return Expr('<% ' + value.hex(' ') + ' %>')
        if isinstance(value, bool):
            return Expr('true' if value else 'false')
        if isinstance(value, int):
            return Expr(str(value))
        if isinstance(value, float):
            return Expr(real_literal(value))
        if isinstance(value, dict) and 'null_object' in value:
            return Expr('null')
        if isinstance(value, dict) and 'object' in value:
            return self.program.object_expression(value['object'])
        raise Unsupported(f'unknown constant {value!r}', self.obj, self._address)

    # -- helpers ---------------------------------------------------------
    def emit(self, text: str):
        self.out.append(Stmt(text, None, None))

    def target_index(self, ins) -> int:
        address = ins[0] + ins[2][0]
        if address == len(self.obj['code']):
            return self.count  # the compiler patches jumps to the end of the code area
        if address not in self.addr_index:
            raise Unsupported(f'branch target {address} is not an instruction', self.obj, ins[0])
        return self.addr_index[address]

    def property(self, object_register: int, name: Expr) -> Expr:
        target = self.read(object_register)
        if name.text.startswith('"') and name.text.endswith('"'):
            literal = name.text[1:-1]
            if is_identifier(literal):
                return Expr(f'{target.at(P_POSTFIX)}.{literal}', P_POSTFIX)
        return Expr(f'{target.at(P_POSTFIX)}[{name.text}]', P_POSTFIX)

    def flag_condition(self, negated: bool) -> Expr:
        if self.flag is None:
            raise Unsupported('conditional jump without a tracked flag', self.obj, self._address)
        value = self.flag
        if self.flag_negated != negated:
            value = negate(value)
        return value

    # -- block graph -----------------------------------------------------
    def _prepare(self):
        n = self.count
        leaders = {0} if n else set()
        for index, ins in enumerate(self.insns):
            op = ins[1]
            if op in ('JF', 'JNF', 'JMP'):
                leaders.add(self.target_index(ins))
                if index + 1 < n:
                    leaders.add(index + 1)
            elif op in ('RET', 'THROW', 'EXTRY', 'SRV'):
                if index + 1 < n:
                    leaders.add(index + 1)
            elif op == 'ENTRY':
                leaders.add(self.target_index(ins))
                if index + 1 < n:
                    leaders.add(index + 1)
        self.leaders = sorted(leaders)
        self.block_at = [0] * n
        self.block_end: dict[int, int] = {}
        for position, start in enumerate(self.leaders):
            end = self.leaders[position + 1] if position + 1 < len(self.leaders) else n
            self.block_end[start] = end
            for index in range(start, end):
                self.block_at[index] = start
        if n in leaders:
            self.block_end[n] = n  # virtual block for jumps to the end of the code area
        self.successors = {start: self._successors(start) for start in self.leaders}
        self.predecessors = self._reverse_edges(self.leaders)
        self.idom = self._idom_map(0, self.successors.get, self.predecessors.get)[0] if n else {0: 0}
        self.ipdom = self._compute_ipdom()
        self.loops_by_header = self._natural_loops()
        self.last_read: dict[int, int] = {}
        for position, ins in enumerate(self.insns):
            for register in source_registers(ins):
                if register not in (0, -1, -2):
                    self.last_read[register] = position

    def _successors(self, start: int) -> list[int]:
        end = self.block_end[start]
        if end <= start or start >= self.count:
            return []
        last = self.insns[end - 1]
        op = last[1]
        if op == 'JMP':
            return [self.target_index(last)]
        if op in ('JF', 'JNF'):
            result = [self.target_index(last)]
            if end < self.count:
                result.append(end)
            return result
        if op in ('RET', 'THROW'):
            return []
        if op == 'ENTRY':
            result = [self.target_index(last)]
            if end < self.count:
                result.insert(0, end)
            return result
        return [end] if end < self.count else []

    def _reverse_edges(self, nodes) -> dict[int, list[int]]:
        edges = {node: [] for node in nodes}
        for node, successors in self.successors.items():
            for successor in successors:
                if successor in edges:
                    edges[successor].append(node)
        return edges

    def _rpo(self, entry: int, successors) -> list[int]:
        seen: set[int] = set()
        post: list[int] = []
        stack = [(entry, False)]
        while stack:
            node, expanded = stack.pop()
            if expanded:
                post.append(node)
                continue
            if node in seen:
                continue
            seen.add(node)
            stack.append((node, True))
            for successor in reversed(successors(node) or []):
                if successor not in seen:
                    stack.append((successor, False))
        return list(reversed(post))

    @staticmethod
    def _intersect(first: int, second: int, idom: dict[int, int], order: dict[int, int]) -> int:
        while first != second:
            while order.get(first, 1 << 30) > order.get(second, 1 << 30):
                parent = idom.get(first, first)
                if parent == first:
                    break
                first = parent
            while order.get(second, 1 << 30) > order.get(first, 1 << 30):
                parent = idom.get(second, second)
                if parent == second:
                    break
                second = parent
        return first

    def _idom_map(self, entry: int, successors, predecessors):
        order_list = self._rpo(entry, successors)
        order = {node: index for index, node in enumerate(order_list)}
        idom = {entry: entry}
        changed = True
        while changed:
            changed = False
            for node in order_list[1:]:
                parents = [parent for parent in predecessors(node) or [] if parent in idom]
                if not parents:
                    continue
                new = parents[0]
                for parent in parents[1:]:
                    new = self._intersect(new, parent, idom, order)
                if idom.get(node) != new:
                    idom[node] = new
                    changed = True
        return idom, order

    def _compute_ipdom(self) -> dict[int, int]:
        """Dominators of the reversed CFG give immediate postdominators."""
        virtual_exit = -1
        reversed_successors = {node: list(self.predecessors.get(node, [])) for node in self.leaders}
        reversed_successors[virtual_exit] = [
            node for node in self.leaders if not self.successors.get(node)]
        reversed_predecessors = {node: list(self.successors.get(node) or [virtual_exit])
                                 for node in self.leaders}
        reversed_predecessors[virtual_exit] = []
        idom, _ = self._idom_map(virtual_exit, reversed_successors.get,
                                 reversed_predecessors.get)
        return {node: idom.get(node, virtual_exit) for node in self.leaders}

    def _dominates(self, first: int, second: int) -> bool:
        if first == second:
            return True
        seen: set[int] = set()
        node = second
        while node in self.idom and node not in seen:
            seen.add(node)
            node = self.idom[node]
            if node == first:
                return True
        return False

    def _natural_loops(self) -> dict[int, Loop]:
        loops: dict[int, Loop] = {}
        for start in self.leaders:
            for successor in self.successors[start]:
                if successor > start or not self._dominates(successor, start):
                    continue  # not a back edge: the target does not dominate the source
                body = {start, successor}
                work = [start]
                while work:
                    node = work.pop()
                    for predecessor in self.predecessors.get(node, []):
                        if predecessor not in body and self._dominates(successor, predecessor):
                            body.add(predecessor)
                            work.append(predecessor)
                previous = loops.get(successor)
                if previous is None or start > previous.latch:
                    loops[successor] = Loop(successor, start, body,
                                            self.block_end[start], successor)
        return loops

    # -- linear translation ---------------------------------------------
    def run(self) -> list[Stmt]:
        self.emit_range(0, self.count)
        return self.out

    def emit_range(self, start: int, end: int):
        index = start
        while index < end:
            ins = self.insns[index]
            self._address = ins[0]
            if index in self.loops_by_header and index not in self._loop_bodies and start <= index < end:
                index = self.emit_loop(index, end)
                continue
            op = ins[1]
            if op == 'ENTRY':
                index = self.emit_try(index, end)
                continue
            if op in ('JF', 'JNF'):
                index = self.emit_branch(index, end)
                continue
            if op == 'JMP':
                index = self.emit_jump(index, end)
                continue
            self._address, self._index = ins[0], index
            literal = self._array_literal(index)
            if literal is not None:
                next_index, value = literal
                self.write_register(ins[2][0], value)
                index = next_index
                continue
            self.translate(index)
            index += 1

    def emit_loop(self, header: int, end: int) -> int:
        loop = self.loops_by_header[header]
        latch = loop.latch
        if latch >= end:
            raise Unsupported('loop extends beyond its enclosing range', self.obj, self.insns[header][0])
        latch_jump = self.block_end[latch] - 1
        last = self.insns[latch_jump]
        op = last[1]
        if self.target_index(last) != header:
            raise Unsupported('loop back edge does not target its header', self.obj, last[0])

        exit_index = self.block_end[latch]
        loop.exit_index = exit_index
        body_start, body_end = header, latch_jump
        condition = None

        if op == 'JMP':
            branch = self._header_exit_branch(header, exit_index)
            if branch is not None:
                for position in range(header, branch):
                    self.translate(position)
                condition = self.flag_condition(True if self.insns[branch][1] == 'JF' else False)
                body_start = branch + 1
                body_end = latch_jump
        elif op in ('JF', 'JNF'):
            condition_start = self._condition_suffix(latch, self.block_end[latch] - 1)
            for position in range(condition_start, self.block_end[latch] - 1):
                self.translate(position)
            condition = self.flag_condition(False if op == 'JF' else True)
            body_end = condition_start
            loop.continue_index = condition_start
        else:
            raise Unsupported('loop latch is not a jump', self.obj, last[0])

        saved_loops = self.loops
        self.loops = saved_loops + [loop]
        self._loop_bodies.add(header)
        try:
            body = self.sub(body_start, body_end)
        finally:
            self._loop_bodies.discard(header)
            self.loops = saved_loops

        if op == 'JMP':
            head = f'while ({condition.text}) {{' if condition is not None else 'while (true) {'
            self.out.append(Stmt(head, body))
        else:
            self.out.append(Stmt('do {', body, f'}} while ({condition.text});'))
        return exit_index

    def _array_literal(self, index: int):
        """Recognise the compiler's NEW Array + SPIS/INC constant-fill loop."""
        ins = self.insns[index]
        if ins[1] != 'NEW' or len(ins[2]) < 3 or ins[2][2] != 0:
            return None
        destination = ins[2][0]
        if self.read(ins[2][1]).text not in ('Array', 'global.Array'):
            return None
        at = index + 1
        index_register = None
        if at < self.count and self.insns[at][1] == 'CONST':
            operands = self.insns[at][2]
            value = (self.obj['constants'][operands[1]]
                     if 0 <= operands[1] < len(self.obj['constants']) else None)
            if operands[0] > 0 and isinstance(value, int):
                index_register = operands[0]
                at += 1
        items = []
        while at < self.count:
            op = self.insns[at][1]
            if op == 'CONST' and at + 2 < self.count:
                constant, assign, increment = self.insns[at:at + 3]
                if constant[2][0] <= 0 or assign[1] != 'SPIS' or assign[2][0] != destination:
                    break
                value_register, constant_index = constant[2]
                if index_register is None:
                    index_register = assign[2][1]
                if (assign[2][1] != index_register or assign[2][2] != value_register
                        or increment[1] != 'INC' or increment[2][0] != index_register):
                    break
                items.append(self.constant(constant_index))
                at += 3
            elif op == 'SPIS' and at + 1 < self.count:
                assign, increment = self.insns[at:at + 2]
                if assign[2][0] != destination or assign[2][2] != 0:
                    break
                if index_register is None:
                    index_register = assign[2][1]
                if (assign[2][1] != index_register
                        or increment[1] != 'INC' or increment[2][0] != index_register):
                    break
                items.append(Expr('void'))  # sparse element / hole
                at += 2
            else:
                break
        if not items:
            return None
        return at, Expr('[' + ', '.join(item.text for item in items) + ']')

    def _condition_suffix(self, block: int, branch: int) -> int:
        start = branch
        while start > block and self._pure_instruction(self.insns[start - 1]):
            start -= 1
        if not any(self.insns[position][1] in ('TT', 'TF', 'CEQ', 'CDEQ', 'CLT', 'CGT', 'NF')
                   for position in range(start, branch)):
            raise Unsupported('loop condition is not reconstructable', self.obj, self.insns[branch][0])
        return start

    def _header_exit_branch(self, header: int, exit_index: int) -> int | None:
        for index in range(header, self.block_end[header]):
            ins = self.insns[index]
            op = ins[1]
            if op in ('JF', 'JNF') and self.target_index(ins) >= exit_index:
                if all(self._pure_instruction(self.insns[check]) for check in range(header, index)):
                    return index
                return None
        return None

    def _pure_instruction(self, ins) -> bool:
        op = ins[1]
        if op == 'CP':
            return len(ins[2]) == 2 and ins[2][0] > 0
        if op in ('SETF', 'SETNF'):
            return bool(ins[2]) and ins[2][0] > 0
        return op in PURE_OPS

    def _pure_block(self, start: int, end: int) -> bool:
        return all(self._pure_instruction(ins) for ins in self.insns[start:end])

    def _condition_block(self, start: int) -> bool:
        end = self.block_end[start]
        if end <= start:
            return False
        if self.insns[end - 1][1] not in ('JF', 'JNF'):
            return False
        return self._pure_block(start, end - 1)

    def emit_branch(self, index: int, end: int) -> int:
        ins = self.insns[index]
        target = self.target_index(ins)
        op = ins[1]
        taken = self.flag_condition(False) if op == 'JF' else self.flag_condition(True)
        if target <= index:
            if not self.loops:
                raise Unsupported('backward branch outside a loop', self.obj, ins[0])
            loop = self.loops[-1]
            if target == loop.continue_index:
                self.emit(f'if ({taken.text}) continue;')
                return index + 1
            if target >= loop.exit_index:
                self.emit(f'if ({taken.text}) break;')
                return index + 1
            raise Unsupported('backward branch that is not break/continue', self.obj, ins[0])

        if self.loops:
            loop = self.loops[-1]
            if target == loop.continue_index:
                self.emit(f'if ({taken.text}) continue;')
                return index + 1
            if target >= loop.exit_index:
                self.emit(f'if ({taken.text}) break;')
                return index + 1

        fallthrough = self.flag_condition(True) if op == 'JF' else self.flag_condition(False)
        if self._outward_branch(index + 1, target):
            return self._emit_condition_dag(index, target, end)

        join = self.ipdom.get(self.block_at[index], -1)
        join = end if join < 0 else min(join, end)
        join = max(target, join)
        then_end = target
        if then_end - 1 >= index + 1 and self.insns[then_end - 1][1] == 'JMP':
            after = self.target_index(self.insns[then_end - 1])
            break_or_continue = bool(self.loops) and after in (
                self.loops[-1].exit_index, self.loops[-1].continue_index)
            if after == join and not break_or_continue:
                then_end -= 1  # the compiler's skip jump is implied by if/else
        then_body = self.sub(index + 1, then_end)
        else_body = self.sub(target, join) if join > target else None
        self.out.append(Stmt(f'if ({fallthrough.text}) {{', then_body, '}',
                             '} else {' if else_body is not None else None, else_body))
        return join

    def _outward_branch(self, start: int, limit: int) -> bool:
        """True when the fallthrough path immediately continues testing conditions.

        A simple if body never branches beyond its own end; an OR-style chain
        does, because its true target is the body while the false path goes on
        to another comparison.
        """
        for index in range(start, limit):
            ins = self.insns[index]
            if ins[1] not in ('JF', 'JNF'):
                continue
            target = self.target_index(ins)
            if target <= limit:
                continue
            if self.loops and target >= self.loops[-1].exit_index:
                continue  # break out of the enclosing loop
            return True
        return False

    def _emit_condition_dag(self, index: int, target: int, end: int) -> int:
        start_block = self.block_at[index]
        nodes: dict[int, list[tuple[int, Expr]]] = {}
        incoming: dict[int, int] = {}
        states: dict[int, tuple[dict[int, Expr], Expr | None, bool]] = {
            start_block: (dict(self.regs), self.flag, self.flag_negated)}
        pending = [start_block]
        while pending:
            block = pending.pop(0)
            if len(nodes) > 64:
                raise Unsupported('condition graph exceeds the node budget', self.obj, self.insns[index][0])
            regs, flag, negated = states[block]
            saved = (self.regs, self.flag, self.flag_negated, self.out)
            self.regs, self.flag, self.flag_negated = dict(regs), flag, negated
            self.out = []
            try:
                if block != start_block:
                    for position in range(block, self.block_end[block] - 1):
                        self.translate(position)
            finally:
                after_state = (dict(self.regs), self.flag, self.flag_negated)
                discarded = self.out
                self.regs, self.flag, self.flag_negated, self.out = saved
            if discarded:
                raise Unsupported('condition block contains statements', self.obj, self.insns[block][0])
            last = self.insns[self.block_end[block] - 1]
            last_op = last[1]
            branch_target = self.target_index(last)
            after_flag, after_negated = after_state[1], after_state[2]
            if after_flag is None:
                raise Unsupported('condition block did not set a flag', self.obj, last[0])
            def value(want_negated: bool) -> Expr:
                return after_flag if after_negated == want_negated else negate(after_flag)
            taken = value(False) if last_op == 'JF' else value(True)
            fall = value(True) if last_op == 'JF' else value(False)
            edges = [(branch_target, taken)]
            if self.block_end[block] < self.count:
                edges.append((self.block_end[block], fall))
            nodes[block] = edges
            for successor, _ in edges:
                if successor <= block:
                    raise Unsupported('condition graph contains a backward edge', self.obj, last[0])
                incoming[successor] = incoming.get(successor, 0) + 1
                if self._condition_block(successor) and successor < end:
                    if incoming[successor] > 1:
                        raise Unsupported('condition blocks merge', self.obj, self.insns[successor][0])
                    if successor not in states:
                        states[successor] = after_state
                        pending.append(successor)

        values: dict[int, Expr] = {start_block: TRUE}
        exits: dict[int, Expr] = {}
        for block in sorted(nodes):
            base = values.get(block)
            if base is None:
                raise Unsupported('condition block without a reconstructed entry', self.obj,
                                  self.insns[block][0])
            for successor, predicate in nodes[block]:
                term = conjunction(base, predicate)
                if successor in nodes:
                    values[successor] = disjunction(values.get(successor, FALSE), term)
                else:
                    exits[successor] = disjunction(exits.get(successor, FALSE), term)
        if len(exits) != 2:
            raise Unsupported('unsupported conditional dispatch (switch-like or merged branches)',
                              self.obj, self.insns[index][0])
        small, large = sorted(exits)
        condition = exits[small]
        if condition.text in ('true', 'false') or small < index + 1:
            raise Unsupported('degenerate condition reconstruction', self.obj, self.insns[index][0])
        join = self.ipdom.get(start_block, -1)
        join = end if join < 0 else min(join, end)
        join = max(large, join)
        then_body = self.sub(small, large)
        else_body = self.sub(large, join) if large < join else None
        self.out.append(Stmt(f'if ({condition.text}) {{', then_body, '}',
                             '} else {' if else_body is not None else None, else_body))
        return join

    def sub(self, start: int, end: int) -> list[Stmt]:
        body: list[Stmt] = []
        previous = self.out
        self.out = body
        try:
            self.emit_range(start, end)
        finally:
            self.out = previous
        return body

    def emit_jump(self, index: int, end: int) -> int:
        ins = self.insns[index]
        target = self.target_index(ins)
        if self.loops:
            loop = self.loops[-1]
            if target == loop.continue_index:
                self.emit('continue;')
                return index + 1
            if target >= loop.exit_index:
                self.emit('break;')
                return index + 1
        if target >= end:
            return index + 1
        if not self.loops:
            raise Unsupported('forward jump outside a structured statement', self.obj, ins[0])
        raise Unsupported('unstructured jump', self.obj, ins[0])

    def emit_try(self, index: int, end: int) -> int:
        ins = self.insns[index]
        catch_index = self.target_index(ins)
        exception_register = ins[2][1]
        extry = None
        for position in range(index + 1, catch_index):
            if self.insns[position][1] == 'EXTRY':
                extry = position
        if extry is None:
            raise Unsupported('try block without EXTRY', self.obj, ins[0])
        after = None
        for position in range(extry + 1, catch_index):
            if self.insns[position][1] == 'JMP':
                after = self.target_index(self.insns[position])
                break
        if after is None:
            raise Unsupported('try/catch without a skip jump', self.obj, ins[0])
        try_body = self.sub(index + 1, extry)
        catch_start = catch_index
        catch_name = None
        if exception_register < -2:
            catch_name = self.local_name(exception_register)
            self.declared.add(catch_name)
            self.regs[exception_register] = Expr(catch_name)
        catch_body = self.sub(catch_start, after) if catch_start < after else []
        head = 'try {'
        tail = '} catch {' if catch_name is None else f'}} catch ({catch_name}) {{'
        self.out.append(Stmt(head, try_body, '}', tail, catch_body))
        return after

    # -- instruction translation ----------------------------------------
    def translate(self, index: int):
        ins = self.insns[index]
        address, op, operands = ins
        self._address = address
        self._index = index

        if op in ('NOP', 'REGMEMBER', 'ADDCI', 'EXTRY'):
            return  # compiler bookkeeping / class instance info, no source form
        if op == 'DEBUGGER':
            self.emit('debugger;')
            return
        if op == 'NF':
            self.flag = negate(self.flag) if self.flag is not None else None
            return
        if op == 'CONST':
            value = self.constant(operands[1])
            if operands[0] < -2:
                self.assign_local(operands[0], value)
            elif operands[0] > 0:
                self.regs[operands[0]] = value
            else:
                self.emit(f'{value.text};')
            return
        if op == 'CP':
            destination, source = operands[0], operands[1]
            value = self.read(source)
            if destination < -2:
                self.assign_local(destination, value)
            elif destination > 0:
                self.regs[destination] = value
            elif destination == 0:
                self.emit(f'{value.text};')
            else:
                raise Unsupported('assignment to this', self.obj, address)
            return
        if op == 'CL':
            self.clear_local(operands[0])
            return
        if op == 'CCL':
            for offset in range(operands[1]):
                self.clear_local(operands[0] + offset)
            return
        if op == 'GLOBAL':
            self.write_register(operands[0], Expr('global'))
            return
        if op == 'TT':
            self.flag, self.flag_negated = self.read(operands[0]), False
            return
        if op == 'TF':
            self.flag, self.flag_negated = self.read(operands[0]), True
            return
        if op in ('CEQ', 'CDEQ', 'CLT', 'CGT'):
            symbol = {'CEQ': '==', 'CDEQ': '===', 'CLT': '<', 'CGT': '>'}[op]
            self.flag = binary(self.read(operands[0]), symbol, self.read(operands[1]))
            self.flag_negated = False
            return
        if op in ('SETF', 'SETNF'):
            value = self.flag_condition(op == 'SETNF')
            self.write_register(operands[0], value)
            return
        if op in ('LNOT', 'BNOT', 'CHS', 'NUM', 'ASC', 'CHR', 'TYPEOF', 'CHKINV',
                  'INT', 'REAL', 'STR', 'OCTET'):
            operand = self.read(operands[0])
            symbol = {'LNOT': '!', 'BNOT': '~', 'CHS': '-', 'NUM': '+'}.get(op)
            if symbol is not None:
                value = unary(symbol, operand)
            elif op == 'TYPEOF':
                value = Expr(f'typeof {operand.at(P_UNARY)}', P_UNARY)
            elif op == 'CHKINV':
                value = Expr(f'isvalid {operand.at(P_UNARY)}', P_UNARY)
            else:
                value = Expr(f'{op.lower()} {operand.at(P_UNARY)}', P_UNARY)
            self.write_register(operands[0], value)
            return
        if op in ('INC', 'DEC'):
            if operands[0] >= -2:
                raise Unsupported('increment of a non-local register',
                                  self.obj, address)
            target = self.read(operands[0])
            self.emit(f'{target.text}{"++" if op == "INC" else "--"};')
            return
        if op in ('INCPD', 'DECPD', 'INCPI', 'DECPI', 'INCP'):
            destination = operands[0]
            if op in ('INCPD', 'DECPD'):
                target = self.property(operands[1], self.constant(operands[2]))
            elif op in ('INCPI', 'DECPI'):
                target = self.property(operands[1], self.read(operands[2]))
            else:
                target = Expr(f'*{self.read(operands[1]).at(P_UNARY)}', P_UNARY)
            symbol = '++' if op.startswith('INC') else '--'
            self.emit(f'{target.text}{symbol};')
            if destination > 0:
                self.regs[destination] = target
            return
        if op in BINARY_VARIANTS:
            self.binary_instruction(op, operands)
            return
        if op in ('GPD', 'GPDS', 'GPI', 'GPIS'):
            destination = operands[0]
            if op in ('GPD', 'GPDS'):
                target = self.property(operands[1], self.constant(operands[2]))
            else:
                target = self.property(operands[1], self.read(operands[2]))
            if op in ('GPDS', 'GPIS'):
                target = unary('&', target)
            if destination > 0 and self.last_read.get(destination, -1) <= self._index:
                self.emit(f'{target.text};')
            else:
                self.write_register(destination, target, statement=True)
            return
        if op in ('SPD', 'SPDE', 'SPDEH', 'SPDS', 'SPI', 'SPIE', 'SPIS'):
            self.property_set(op, operands)
            return
        if op in ('CALL', 'CALLD', 'CALLI', 'NEW'):
            self.call(op, operands)
            return
        if op == 'CHKINS':
            destination = operands[0]
            value = binary(self.read(destination), 'instanceof', self.read(operands[1]))
            self.write_register(destination, value)
            self.flag, self.flag_negated = value, False
            return
        if op == 'CHGTHIS':
            self.write_register(operands[0], Expr(
                f'{self.read(operands[0]).at(P_REL)} incontextof {self.read(operands[1]).at(P_REL)}', P_REL))
            return
        if op == 'SETP':
            target = Expr(f'*{self.read(operands[0]).at(P_UNARY)}', P_UNARY)
            self.emit(f'{target.text} = {self.read(operands[1]).text};')
            return
        if op == 'GETP':
            self.write_register(operands[0], Expr(f'*{self.read(operands[1]).at(P_UNARY)}', P_UNARY))
            return
        if op in ('DELD', 'DELI', 'TYPEOFD', 'TYPEOFI'):
            destination = operands[0]
            if op in ('DELD', 'TYPEOFD'):
                target = self.property(operands[1], self.constant(operands[2]))
            else:
                target = self.property(operands[1], self.read(operands[2]))
            value = Expr(f'delete {target.at(P_UNARY)}', P_UNARY) if op.startswith('DEL') \
                else Expr(f'typeof {target.at(P_UNARY)}', P_UNARY)
            if destination > 0 and op.startswith('DEL') \
                    and self.last_read.get(destination, -1) <= self._index:
                self.emit(f'{value.text};')
            else:
                self.write_register(destination, value, statement=True)
            return
        if op == 'SRV':
            self.emit('return;' if operands[0] == 0 else f'return {self.read(operands[0]).text};')
            self.return_pending = True
            return
        if op == 'RET':
            if index > 0 and self.insns[index - 1][1] == 'SRV':
                return  # SRV already emitted the return statement
            if index != self.count - 1:
                self.emit('return;')
            return
        if op == 'THROW':
            self.emit(f'throw {self.read(operands[0]).text};')
            return
        if op == 'INV':
            self.emit(f'invalidate {self.read(operands[0]).text};')
            return
        raise Unsupported(f'opcode {op} is not reconstructed', self.obj, address)

    def binary_instruction(self, op: str, operands: list[int]):
        base, variant = BINARY_VARIANTS[op]
        symbol = BINARY_SYMBOLS[base]
        destination = operands[0]
        if variant == 0:
            left = self.read(destination)
            right = self.read(operands[1])
            if destination < -2:
                self.emit(f'{left.text} {symbol}= {right.text};')
                self.regs[destination] = Expr(self.local_name(destination))
            else:
                self.regs[destination] = binary(left, symbol, right)
            return
        if variant == 1:
            target = self.property(operands[1], self.constant(operands[2]))
            value = self.read(operands[3])
        elif variant == 2:
            target = self.property(operands[1], self.read(operands[2]))
            value = self.read(operands[3])
        else:
            target = Expr(f'*{self.read(operands[1]).at(P_UNARY)}', P_UNARY)
            value = self.read(operands[2])
        self.emit(f'{target.text} {symbol}= {value.text};')
        if destination > 0:
            self.regs[destination] = target

    def property_set(self, op: str, operands: list[int]):
        if op in ('SPD', 'SPDE', 'SPDEH', 'SPDS'):
            name = self.constant(operands[1])
            target = self.property(operands[0], name)
            value = self.read(operands[2])
            value_register = operands[2]
            literal = self.obj['constants'][operands[1]] if 0 <= operands[1] < len(self.obj['constants']) else None
        else:
            target = self.property(operands[0], self.read(operands[1]))
            value = self.read(operands[2])
            value_register = operands[2]
            literal = None
        if (op == 'SPDS' and operands[0] == -1 and self.class_context
                and isinstance(literal, str)):
            if member_is_registration(self.program, self.obj, literal, value):
                return
            self.emit(f'var {literal}' + ('' if value.text == 'void' else f' = {value.text}') + ';')
            self.declared.add(literal)
            return
        plain = target
        if op in ('SPDS', 'SPIS') and operands[0] != -1:
            target = unary('&', target)
        self.emit(f'{target.text} = {value.text};')
        if value_register > 0:
            self.regs[value_register] = plain

    def call(self, op: str, operands: list[int]):
        destination = operands[0]
        if op == 'CALL':
            function = self.read(operands[1])
            start, argument_count = 3, operands[2]
            prefix = ''
        elif op == 'CALLD':
            function = self.property(operands[1], self.constant(operands[2]))
            start, argument_count = 4, operands[3]
            prefix = ''
        elif op == 'CALLI':
            function = self.property(operands[1], self.read(operands[2]))
            start, argument_count = 4, operands[3]
            prefix = ''
        else:
            function = self.read(operands[1])
            start, argument_count = 3, operands[2]
            prefix = 'new '
        arguments = self.call_arguments(operands, start, argument_count)
        value = Expr(f'{prefix}{function.at(P_POSTFIX)}({", ".join(arguments)})', P_POSTFIX)
        if destination > 0 and self.last_read.get(destination, -1) <= self._index:
            self.emit(f'{value.text};')  # dead result, but the call still executes
        else:
            self.write_register(destination, value, statement=True)

    def call_arguments(self, operands: list[int], start: int, count: int) -> list[str]:
        if count == -1:
            return ['...']
        if count == -2:
            raise Unsupported('expanded argument lists are not reconstructed', self.obj, self._address)
        if count < 0:
            raise Unsupported('negative argument count', self.obj, self._address)
        if start + count > len(operands):
            raise Unsupported('truncated argument list', self.obj, self._address)
        return [self.read(register).text for register in operands[start:start + count]]


def member_is_registration(program: 'Program', obj: dict, member: str, value: Expr) -> bool:
    """Compiler prologue registers methods on the class object; skip the copy."""
    for child in program.objects:
        if child['parent'] == obj['id'] and child['name'] == member and child['context'] in (1, 3):
            return value.text == member or value.text.endswith(f' {member}')
    return False


class Program:
    def __init__(self, data: bytes):
        self.top, self.objects = parse(data)
        self.by_id = {obj['id']: obj for obj in self.objects}
        self.active: set[int] = set()

    def object_expression(self, index: int) -> Expr:
        if not 0 <= index < len(self.objects):
            raise Unsupported(f'object reference {index} out of range')
        obj = self.objects[index]
        name = obj.get('name')
        if obj['context'] == 2:
            if index in self.active:
                raise Unsupported('recursive anonymous function reference')
            self.active.add(index)
            try:
                return Expr('(' + self.anonymous_function(obj) + ')', P_PRIMARY)
            finally:
                self.active.discard(index)
        if name:
            return Expr(name)
        return Expr(f'null /* object#{index} */')

    def anonymous_function(self, obj: dict) -> str:
        method = Method(self, obj)
        body = drop_trailing_return(method.run())
        arguments = ', '.join(method.argument_names())
        if len(body) == 1 and body[0].body is None and body[0].head.startswith('return '):
            return f'function({arguments}) {{ {body[0].head} }}'
        inner = '\n'.join(render(body, 1))
        return f'function({arguments}) {{\n{inner}\n}}'

    def definition(self, obj: dict, indent: int = 0) -> list[str]:
        context = obj['context']
        if context == 6:
            return self.class_definition(obj, indent)
        if context == 3:
            return self.property_definition(obj, indent)
        if context == 1:
            return self.function_definition(obj, indent)
        return []

    def function_definition(self, obj: dict, indent: int = 0) -> list[str]:
        method = Method(self, obj)
        body = drop_trailing_return(method.run())
        arguments = ', '.join(method.argument_names())
        name = obj.get('name') or f'_func{obj["id"]}'
        pad = '    ' * indent
        lines = [f'{pad}function {name}({arguments}) {{']
        lines.extend(render(body, indent + 1))
        lines.append(pad + '}')
        return lines

    def class_definition(self, obj: dict, indent: int = 0) -> list[str]:
        method = Method(self, obj, class_context=True)
        body = drop_trailing_return(method.run())
        pad = '    ' * indent
        lines = [f'{pad}class {obj.get("name") or "_class"}' + self._extends(obj) + ' {']
        lines.extend(render(body, indent + 1))
        for child in self.children(obj['id']):
            if child['context'] in (1, 3, 6):
                lines.extend(self.definition(child, indent + 1))
        lines.append(pad + '}')
        return lines

    def property_definition(self, obj: dict, indent: int = 0) -> list[str]:
        pad = '    ' * indent
        lines = [f'{pad}property {obj.get("name") or "_property"} {{']
        getter_index = obj.get('prop_getter', -1)
        setter_index = obj.get('prop_setter', -1)
        if 0 <= getter_index < len(self.objects):
            method = Method(self, self.objects[getter_index])
            body = drop_trailing_return(method.run())
            lines.append(pad + '    getter() {')
            lines.extend(render(body, indent + 2))
            lines.append(pad + '    }')
        if 0 <= setter_index < len(self.objects):
            method = Method(self, self.objects[setter_index])
            body = drop_trailing_return(method.run())
            arguments = ', '.join(method.argument_names())
            lines.append(pad + f'    setter({arguments}) {{')
            lines.extend(render(body, indent + 2))
            lines.append(pad + '    }')
        lines.append(pad + '}')
        return lines

    def _extends(self, obj: dict) -> str:
        parent = obj.get('parent', -1)
        if parent in self.by_id and parent != self.top:
            name = self.by_id[parent].get('name')
            if name and is_identifier(name):
                return f' extends {name}'
        return ''

    def children(self, parent: int) -> list[dict]:
        return [obj for obj in self.objects if obj.get('parent') == parent and obj['id'] != parent]

    def decompile(self) -> str:
        top = self.by_id[self.top]
        lines: list[str] = []
        for child in self.children(top['id']):
            if child['context'] in (1, 3, 6):
                lines.extend(self.definition(child))
                lines.append('')
        body = drop_trailing_return(Method(self, top).run())
        lines.extend(render(body))
        return '\n'.join(lines).rstrip() + '\n'


def drop_trailing_return(body: list[Stmt]) -> list[Stmt]:
    while body and body[-1].body is None and body[-1].head == 'return;':
        body.pop()
    return body


def decompile(data: bytes) -> str:
    return Program(data).decompile()


def _constant_operand(name: str, operands: list[int]) -> int | None:
    """Constant-pool operand for instructions that name a member by index."""
    if name in ('CONST', 'SPD', 'SPDE', 'SPDEH', 'SPDS'):
        return operands[1] if len(operands) > 1 else None
    if name in ('GPD', 'GPDS', 'CALLD', 'DELD', 'TYPEOFD'):
        return operands[2] if len(operands) > 2 else None
    return None


def strings(data: bytes) -> list[dict]:
    """List string constants with the objects and instructions that reference them."""
    _, objects = parse(data)
    result = []
    for obj in objects:
        constants = obj['constants']
        for address, name, operands in instructions(obj['code']):
            index = _constant_operand(name, operands)
            if index is not None and 0 <= index < len(constants) and isinstance(constants[index], str):
                result.append({'object': obj['id'], 'name': obj.get('name'),
                               'address': address, 'opcode': name,
                               'constant': index, 'text': constants[index]})
    return result


def info(data: bytes) -> str:
    top, objects = parse(data)
    lines = [f'Top object: {top}',
             'ID  Name                          Context             Parent  Args  Code  Strings']
    for obj in objects:
        lines.append('{:<3} {:<29} {:<19} {:<7} {:<5} {:<5} {:<7}'.format(
            obj['id'], (obj.get('name') or '')[:29],
            CONTEXT_NAMES.get(obj['context'], str(obj['context'])),
            obj['parent'], obj.get('arg_count', 0), len(obj['code']),
            sum(1 for value in obj['constants'] if isinstance(value, str))))
    return '\n'.join(lines) + '\n'


ENCODINGS = {
    'utf-8': 'utf-8', 'utf-8-bom': 'utf-8-sig',
    'utf-16le-bom': 'utf-16', 'shift_jis': 'cp932', 'gbk': 'gbk',
}


def encode_source(text: str, encoding: str) -> bytes:
    if encoding not in ENCODINGS:
        raise ValueError(f'unsupported encoding: {encoding}')
    return text.encode(ENCODINGS[encoding])


def process_file(source: Path, mode: str, encoding: str) -> str:
    data = source.read_bytes()
    if mode == 'disasm':
        return disassemble(data)
    if mode == 'info':
        return info(data)
    if mode == 'strings':
        rows = strings(data)
        width = max([len(repr(row['text'])) for row in rows], default=0)
        return '\n'.join(
            f'{row["object"]:>4} {row["address"]:05d} {row["name"] or "":<24} '
            f'{row["text"]!r:<{width}}' for row in rows) + ('\n' if rows else '')
    return decompile(data)


def iter_sources(source: Path, recursive: bool):
    if source.is_file():
        yield source
        return
    pattern = '**/*.tjs' if recursive else '*.tjs'
    for path in sorted(source.glob(pattern)):
        if path.is_file():
            yield path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Reconstruct readable TJS2 source from TJS2100 bytecode; '
                    'unsupported bytecode shapes raise instead of guessing.')
    parser.add_argument('input', type=Path, help='compiled .tjs file or directory')
    parser.add_argument('-o', '--output', type=Path, help='output file or new directory')
    parser.add_argument('--mode', choices=('decompile', 'disasm', 'info', 'strings'),
                        default='decompile')
    parser.add_argument('--encoding', choices=sorted(ENCODINGS), default='utf-8')
    parser.add_argument('-r', '--recursive', action='store_true', help='include subdirectories')
    parser.add_argument('-f', '--flat', action='store_true', help='write all results into one directory')
    args = parser.parse_args(argv)

    source = args.input
    if not source.exists():
        parser.error(f'input does not exist: {source}')
    files = list(iter_sources(source, args.recursive or args.flat))
    if not files:
        parser.error(f'no .tjs files under {source}')

    if source.is_file():
        try:
            text = process_file(source, args.mode, args.encoding)
        except (ValueError, Unsupported) as error:
            print(f'{source}: {error}', file=sys.stderr)
            return 1
        payload = encode_source(text, args.encoding) if args.mode == 'decompile' else text.encode('utf-8')
        if args.output is None:
            sys.stdout.buffer.write(payload)
            return 0
        if args.output.exists():
            print(f'refusing to replace existing output: {args.output}', file=sys.stderr)
            return 1
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('xb') as stream:
            stream.write(payload)
        return 0

    if args.output is None:
        parser.error('directory input requires -o/--output')
    if args.output.exists():
        print(f'refusing to replace existing output: {args.output}', file=sys.stderr)
        return 1

    entries: list[tuple[str, bytes]] = []
    failures = 0
    for path in files:
        relative = path.relative_to(source).as_posix()
        name = Path(relative).name if args.flat else relative
        if args.mode != 'decompile':
            name += '.txt'
        try:
            text = process_file(path, args.mode, args.encoding)
        except (ValueError, Unsupported) as error:
            print(f'{path}: {error}', file=sys.stderr)
            failures += 1
            continue
        payload = encode_source(text, args.encoding) if args.mode == 'decompile' else text.encode('utf-8')
        entries.append((name, payload))
    if entries:
        from python.common.safety import write_new_tree
        write_new_tree(args.output, entries)
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
