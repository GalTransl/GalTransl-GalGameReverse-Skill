# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 GalTransl contributors
"""Fail-closed BGI Ver1 tests; synthetic data only, no source-repo imports."""
import ast
import json
from pathlib import Path
import struct
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from python.engines import bgi
from python.engines.bgi_v1_opcodes import OPERAND_TEMPLATES
from bgi_v1_fixtures import assemble_v1, make_v1_fixture


def put_u32(data, offset, value):
    result = bytearray(data)
    struct.pack_into('<I', result, offset, value)
    return bytes(result)


class BgiCase(unittest.TestCase):
    def assert_error(self, code, callable_, *args, **kwargs):
        with self.assertRaises(bgi.BgiV1Error) as caught:
            callable_(*args, **kwargs)
        self.assertEqual(caught.exception.code, code, str(caught.exception))
        return caught.exception

    def assert_semantic_blocked(self, data):
        analysis = bgi.scan_v1(data)
        self.assertGreater(analysis.code_length, 0)
        self.assertTrue(analysis.semantic_diagnostics)
        self.assertEqual(analysis.events, ())
        json.dumps(analysis.semantic_diagnostics)
        diagnostic = analysis.semantic_diagnostics[0]
        error = self.assert_error('semantic_unsupported', bgi.export_v1, analysis)
        writer_error = self.assert_error('semantic_unsupported', bgi.patch_v1, data, {})
        for failure in (error, writer_error):
            self.assertEqual((failure.code, failure.offset, failure.opcode),
                             (diagnostic['code'], diagnostic['offset'], diagnostic['opcode']))
        return error

    def simple(self, text='Hello', **kwargs):
        return make_v1_fixture(((None, text),), first_forward=False,
                               referenced_scripts=(), labels=(), **kwargs)


class HeaderAndBoundaryTests(BgiCase):
    def test_real_header_formula_first_forward_and_json_evidence(self):
        data = make_v1_fixture(padding=b'\0' * 7)
        analysis = bgi.scan_v1(data)
        header_size, = struct.unpack_from('<I', data, 28)
        self.assertEqual(analysis.code_base, 28 + header_size)
        self.assertEqual(analysis.instructions[0].opcode, 1)
        self.assertEqual(analysis.profile, bgi.PROFILE)
        self.assertEqual(analysis.boundary['opcode_layout'], bgi.LAYOUT_STACK)
        header = analysis.boundary['header']
        self.assertEqual(header['referenced_scripts'], ['common', 'system', 'chapter'])
        self.assertEqual(header['labels'][0]['address'], 8)
        self.assertEqual(header['padding_size'], 7)
        self.assertEqual(json.loads(json.dumps(analysis.boundary)), analysis.boundary)
        self.assertEqual(bgi.patch_v1(data, {}), data)

    def test_header_sizes_and_reference_counts_are_not_hardcoded(self):
        for names in ((), ('a',), ('one', 'two', 'three', 'four')):
            for pad in (b'', b'\0' * 11):
                with self.subTest(names=names, padding=len(pad)):
                    data = make_v1_fixture(referenced_scripts=names, labels=(), padding=pad)
                    analysis = bgi.scan_v1(data)
                    self.assertEqual(analysis.boundary['header']['referenced_scripts'], list(names))
                    self.assertEqual(len(bgi.export_v1(analysis)[0]), 2)

    def test_minimal4_is_explicit_no_tables_profile(self):
        data = assemble_v1(((3, 'm'), (0x140,), (0x1B,)), {'m': 'Hi'}, minimal_header=True)
        result = bgi.scan_v1(data)
        self.assertEqual(result.code_base, 32)
        self.assertEqual(result.boundary['header']['layout'], 'minimal4-no-tables')
        self.assertEqual(bgi.patch_v1(data, {}), data)

    def test_headerless_v0_bad_signature_and_truncated_header(self):
        data = self.simple()
        for bad in (data[bgi.code_offset(data):], b'\x10\0' * 20,
                    data.replace(b'Ver1', b'Ver0', 1), bgi.MAGIC, bgi.MAGIC + b'\4'):
            with self.subTest(size=len(bad)):
                self.assert_error('malformed', bgi.scan_v1, bad)
        for size in (0, 3, 0xFFFFFFFF):
            self.assert_error('malformed', bgi.scan_v1, put_u32(data, 28, size))

    def test_malformed_count_tables_and_nonzero_extra_header(self):
        data = self.simple()
        self.assert_error('malformed', bgi.scan_v1, put_u32(data, 32, 0xFFFFFFFF))
        self.assert_error('malformed', bgi.scan_v1, put_u32(data, 36, 1))
        self.assert_error('malformed', bgi.scan_v1, self.simple(padding=b'\0\1'))
        self.assert_error('malformed', bgi.scan_v1, put_u32(data, 28, 8))
        bad_name = bgi.MAGIC + struct.pack('<II', 9, 1) + b'x'
        self.assert_error('malformed', bgi.scan_v1, bad_name)

    def test_forward_targets_keep_early_terminals_inside_code(self):
        instructions = ((1, 'late'), (1, 'middle'), (0x1B,),
                        ('label', 'middle'), (1, 'late'), (0xF4,),
                        ('label', 'late'), (3, 'm'), (0x140,), (0x1B,))
        data = assemble_v1(instructions, {'m': 'Message'}, labels=('middle', 'late'))
        result = bgi.scan_v1(data)
        self.assertEqual(result.code_length, 48)
        self.assertEqual([t['eligible'] for t in result.boundary['terminals']], [False, False, True])
        self.assertEqual(len(result.boundary['targets']), 5)
        self.assertEqual(bgi.export_v1(result)[0], [{'message': 'Message'}])

    def test_labels_alone_extend_scan_past_early_terminal(self):
        data = assemble_v1(((0x1B,), ('label', 'later'), (3, 'm'), (0x143,), (0xF4,)),
                           {'m': 'Later'}, labels=('later',))
        result = bgi.scan_v1(data)
        self.assertEqual(result.code_length, 20)
        self.assertEqual(result.boundary['terminals'][-1]['opcode'], 0xF4)

    def test_target_on_terminal_is_a_valid_instruction_start(self):
        data = assemble_v1(((1, 'return'), (3, 'm'), (0x140,),
                           ('label', 'return'), (0x1B,)), {'m': 'Body'})
        self.assertEqual(bgi.scan_v1(data).code_length, 24)

    def test_forward_backward_and_header_targets_cannot_land_in_operands(self):
        bad = assemble_v1(((1, 12), (0, 0x140), (3, 'm'), (0x140,), (0x1B,)), {'m': 'Text'})
        error = self.assert_error('malformed', bgi.scan_v1, bad)
        self.assertEqual(error.offset, bgi.code_offset(bad) + 4)
        backward = assemble_v1(((0, 5), (1, 4), (0x1B,)))
        self.assert_error('malformed', bgi.scan_v1, backward)
        header = assemble_v1(((3, 'm'), (0x140,), (0x1B,)), {'m': 'Text'}, labels={'bad': 4})
        self.assert_error('malformed', bgi.scan_v1, header)

    def test_misaligned_outside_pool_and_eof_targets(self):
        for target in (1, 16, 0xFFFFFFFF):
            data = assemble_v1(((1, target), (3, 'm'), (0x140,), (0x1B,)), {'m': 'Text'})
            if target == 16:  # Valid start: use the actual pool start instead.
                data = put_u32(data, bgi.code_offset(data) + 4, 24)
            self.assert_error('malformed', bgi.scan_v1, data)
        for target in (3, 0xFFFFFFFC):
            data = assemble_v1(((0x1B,),), labels={'bad': target})
            self.assert_error('malformed', bgi.scan_v1, data)

    def test_two_possible_terminal_boundaries_are_rejected(self):
        data = assemble_v1(((3, 'm'), (0x140,), (0x1B,), (0, 9), (0xF4,)), {'m': 'Text'})
        error = self.assert_error('boundary_unknown', bgi.scan_v1, data)
        self.assertIn('multiple', str(error))

    def test_missing_terminal_and_string_overlapping_instruction(self):
        data = assemble_v1(((3, 'm'), (0x140,)), {'m': 'Text'})
        self.assert_error('boundary_unknown', bgi.scan_v1, data)
        data = self.simple()
        for target in (0, 4, 100000):
            self.assert_error('malformed', bgi.scan_v1,
                              put_u32(data, bgi.code_offset(data) + 4, target))
        # A pointer exactly at the next opcode leaves no proven terminal; the
        # scanner must not step into data that its own operand declared a pool.
        self.assert_error('boundary_unknown', bgi.scan_v1,
                          put_u32(data, bgi.code_offset(data) + 4, 8))

    def test_empty_code_no_ref_terminal_and_unproved_trailer(self):
        self.assert_error('boundary_unknown', bgi.scan_v1, assemble_v1(()))
        data = assemble_v1(((0x1B,),))
        self.assertEqual(bgi.export_v1(bgi.scan_v1(data)), ([], [], []))
        self.assertEqual(bgi.patch_v1(data, {}), data)
        with self.assertRaises(bgi.BgiV1Error):
            bgi.scan_v1(data + b'opaque')

    def test_legacy_whitelist_stays_frozen_while_default_accepts_stack_extensions(self):
        data = assemble_v1(((1, 'later'), ('label', 'later'), (3, 'm'), (0x140,),
                            (0x461,), (0x462,), (0x463,), (0x464,), (0x1B,)), {'m': 'Kept'})
        analysis = bgi.scan_v1(data)
        self.assertEqual([inst.opcode for inst in analysis.instructions],
                         [1, 3, 0x140, 0x461, 0x462, 0x463, 0x464, 0x1B])
        self.assertEqual(analysis.code_length, 40)
        self.assertEqual(bgi.export_v1(analysis)[0], [{'message': 'Kept'}])
        self.assertEqual(bgi.patch_v1(data, {}), data)
        for opcode in (0x346, 0x460, 0x465, 0x47F):
            blocked = assemble_v1(((1, 'later'), (opcode,), ('label', 'later'),
                                   (3, 'm'), (0x140,), (0x1B,)), {'m': 'Blocked'})
            generic = bgi.scan_v1(blocked)
            self.assertEqual(generic.boundary['stack_extension_opcodes'], [opcode])
            error = self.assert_error('unsupported_opcode', bgi.scan_v1, blocked,
                                      profile=bgi.PROFILE_EXPLICIT)
            self.assertEqual(error.opcode, opcode)
            self.assertEqual(error.offset, bgi.code_offset(blocked) + 8)
            self.assertEqual(error.relative_offset, 8)
            self.assert_error('unsupported_opcode', bgi.patch_v1, blocked, {},
                              profile=bgi.PROFILE_EXPLICIT)

    def test_early_terminal_cannot_hide_unknown_or_incomplete_code(self):
        for continuation, code in ((((0x460,),), 'boundary_unknown'),
                                   (((0x04,),), 'unsupported_opcode'),
                                   (((0, 10),), 'boundary_unknown'),
                                   (((0x80,), (0xDEADBEEF,)), 'boundary_unknown')):
            data = assemble_v1(((3, 'm'), (0x140,), (0x1B,)) + continuation, {'m': 'Text'})
            self.assert_error(code, bgi.scan_v1, data)

    def test_stack_call_extensions_preserve_following_debug_and_dialogue(self):
        # Also cover IDs never present in the legacy table; this must remain
        # a layout rule rather than additions for individual titles.
        for opcode in (0x177, 0x468, 0x4B0, 0x17C, 0x342, 0x777, 0xFFFF):
            data = assemble_v1(((3, 'internal'), (0x3F, 1), (opcode,),
                                (0x7F, 0, 123), (3, 'name'), (3, 'message'),
                                (0x140,), (0x1B,)),
                               {'internal': 'resource', 'name': 'Actor', 'message': 'Text'})
            analysis = bgi.scan_v1(data)
            rows, locators, _ = bgi.export_v1(analysis)
            self.assertEqual(rows, [{'name': 'Actor', 'message': 'Text'}])
            self.assertEqual(list(rows[0]), ['name', 'message'])
            self.assertEqual(analysis.instructions[3].opcode, 0x7F)
            self.assertEqual(analysis.instructions[3].operands, (0, 123))
            self.assertEqual(bgi.patch_v1(data, {}), data)
            rebuilt = bgi.patch_v1(data, {locators[0]['message_operand']: 'Longer text'})
            after = bgi.scan_v1(rebuilt)
            self.assertEqual(after.code_length, analysis.code_length)
            self.assertEqual(bgi.export_v1(after)[0][0]['message'], 'Longer text')
            # Width knowledge must not turn a returned VM value into narration.
            ambiguous = assemble_v1(((opcode,), (3, 'm'), (0x140,), (0x1B,)), {'m': 'Text'})
            self.assert_error('semantic_unsupported', bgi.export_v1, bgi.scan_v1(ambiguous))

    def test_generic_stack_calls_preserve_forward_targets_and_reject_bad_operands(self):
        data = assemble_v1(((1, 'body'), (0x777,), (0x1B,),
                            ('label', 'body'), (0x7F, 0, 42), (3, 'm'),
                            (0x140,), (0x1B,)), {'m': 'Text'}, labels=('body',))
        parsed = bgi.scan_v1(data)
        self.assertEqual([t['eligible'] for t in parsed.boundary['terminals']], [False, True])
        self.assertEqual(bgi.export_v1(parsed)[0], [{'message': 'Text'}])
        # The label/branch target cannot be hidden inside the following debug record.
        bad = put_u32(data, parsed.code_base + 4, 20)
        self.assert_error('malformed', bgi.scan_v1, bad)
        # An unregistered instruction with apparent inline data does not get
        # arbitrary width recovery or a byte-search resynchronization.
        bad = assemble_v1(((0x777,), (0xDEADBEEF,), (0x1B,)))
        self.assert_error('unsupported_opcode', bgi.scan_v1, bad)

    def test_old_profile_ids_keep_their_layout_and_roundtrip_behavior(self):
        data = self.simple()
        for profile in bgi.PROFILES:
            with self.subTest(profile=profile):
                parsed = bgi.scan_v1(data, profile=profile)
                self.assertEqual(parsed.profile, profile)
                rows, locs, _ = bgi.export_v1(parsed)
                self.assertEqual(bgi.patch_v1(data, {locs[0]['message_operand']: rows[0]['message']},
                                              profile=profile), data)
        # 568-only entries must not be retroactively enabled in 565 manifests.
        data = assemble_v1(((0x177,), (0x1B,)))
        self.assertEqual(bgi.scan_v1(data, profile=bgi.PROFILE_EXPLICIT).code_length, 8)
        for profile in (bgi.PROFILE_EXPLICIT565, bgi.PROFILE_EXPLICIT565_VNTEXTPATCH):
            self.assert_error('unsupported_opcode', bgi.scan_v1, data, profile=profile)

    def test_unknown_other_than_0461_and_truncated_operands(self):
        for opcode in (0xDEADBEEF, 0x0004, 0x10000):
            data = assemble_v1(((opcode,), (0x1B,)))
            self.assert_error('unsupported_opcode', bgi.scan_v1, data)
        data = assemble_v1(((0x007B, 1, 2),))
        self.assert_error('malformed', bgi.scan_v1, data)

    def test_truncations_never_return_a_partial_analysis(self):
        data = make_v1_fixture()
        for end in range(len(data)):
            with self.subTest(end=end), self.assertRaises(bgi.BgiV1Error):
                bgi.scan_v1(data[:end])


class SemanticTests(BgiCase):
    def test_name_message_pairing_absent_empty_and_no_stale_speaker(self):
        data = make_v1_fixture((('Alice', 'Same'), ('', 'Same'), (None, 'Same'), ('Bob', 'Last')))
        analysis = bgi.scan_v1(data)
        rows, locators, policies = bgi.export_v1(analysis)
        self.assertEqual(rows, [{'name': 'Alice', 'message': 'Same'}, {'message': 'Same'},
                                {'message': 'Same'}, {'name': 'Bob', 'message': 'Last'}])
        self.assertEqual(policies, ['writable', 'absent', 'absent', 'writable'])
        self.assertEqual([loc['speaker_status'] for loc in locators], ['static', 'absent', 'absent', 'static'])
        self.assertIsNone(locators[1]['name_operand'])
        self.assertIsNone(locators[2]['name_operand'])
        self.assertEqual(len({loc['message_operand'] for loc in locators}), 4)
        empty = next(ref for ref in analysis.references if ref.text == '')
        self.assertEqual(empty.kind, 'internal')
        self.assert_error('semantic_unsupported', bgi.patch_v1, data, {empty.operand: 'invented'})
        for row in rows:
            self.assertLessEqual(row.keys(), {'name', 'message'})

    def test_empty_message_remains_internal_and_cannot_patch_hidden_name(self):
        data = make_v1_fixture((('Alice', ''), (None, 'After')))
        analysis = bgi.scan_v1(data)
        self.assertEqual(bgi.export_v1(analysis)[0], [{'message': 'After'}])
        hidden_name = next(ref for ref in analysis.references if ref.text == 'Alice')
        self.assert_error('semantic_unsupported', bgi.patch_v1, data, {hidden_name.operand: 'Bob'})

    def test_choice_order_duplicates_empty_and_function_names_internal(self):
        for function in (None, '_SelectEx', '_SelectExtend'):
            with self.subTest(function=function):
                data = make_v1_fixture((), choices=('Yes', 'Yes', '', 'No'), choice_function=function)
                analysis = bgi.scan_v1(data)
                rows, locators, policies = bgi.export_v1(analysis)
                self.assertEqual(rows, [{'message': text} for text in ('Yes', 'Yes', '', 'No')])
                self.assertEqual([loc['choice_index'] for loc in locators], list(range(4)))
                self.assertEqual([loc['choice_group'] for loc in locators], [0] * 4)
                self.assertEqual(policies, ['absent'] * 4)
                if function is not None:
                    ref = next(ref for ref in analysis.references if ref.text == function)
                    self.assertEqual(ref.kind, 'internal')
                    self.assert_error('semantic_unsupported', bgi.patch_v1, data, {ref.operand: 'bad'})

    def test_multiple_choice_groups_and_dialogue_are_ordered(self):
        data = assemble_v1(((3, 'a'), (0x160,), (3, 'm'), (0x140,),
                           (3, 'b'), (3, 'a'), (0x160,), (0x1B,)),
                          {'a': 'A', 'm': 'Message', 'b': 'B'})
        _, locators, _ = bgi.export_v1(bgi.scan_v1(data))
        self.assertEqual([(loc['choice_group'], loc['choice_index']) for loc in locators],
                         [(0, 0), (None, None), (1, 0), (1, 1)])

    def test_internal_flushes_and_nonchoice_call_do_not_leak_arguments(self):
        for flush in ((0x7E, 0), (0x7F, 0, 0), (0xFE,)):
            data = assemble_v1(((3, 'resource'), flush, (3, 'm'), (0x140,), (0x1B,)),
                               {'resource': 'background.png', 'm': 'Text'})
            analysis = bgi.scan_v1(data)
            self.assertEqual([ref.kind for ref in analysis.references], ['internal', 'message'])
            self.assertEqual(bgi.export_v1(analysis)[0], [{'message': 'Text'}])
        data = assemble_v1(((3, 'arg'), (3, 'function'), (0x1C,), (0xFE,),
                           (3, 'm'), (0x143,), (0x1B,)),
                          {'arg': 'asset', 'function': '_NotSelect', 'm': 'Body'})
        analysis = bgi.scan_v1(data)
        self.assertEqual([ref.kind for ref in analysis.references], ['internal', 'internal', 'message'])
        output = bgi.patch_v1(data, {analysis.references[-1].operand: 'Longer body'})
        self.assertEqual(bgi.scan_v1(output).references[:2], analysis.references[:2])

    def test_unrelated_variables_before_two_fresh_literals_are_not_global_taint(self):
        data = assemble_v1(((2, 4), (8, 1), (0x20,), (3, 'n'), (3, 'm'), (0x140,),
                           (3, 'next'), (0x143,), (0x1B,)),
                          {'n': 'Name', 'm': 'Body', 'next': 'Narration'})
        analysis = bgi.scan_v1(data)
        self.assertEqual(analysis.semantic_diagnostics, ())
        self.assertEqual(bgi.export_v1(analysis)[0],
                         [{'name': 'Name', 'message': 'Body'}, {'message': 'Narration'}])

    def test_plain_literal_function_accepts_unresolved_numeric_arguments(self):
        data = assemble_v1(((2, 4), (8, 1), (3, 'arg'), (3, 'function'), (0x1C,),
                           (3, 'n'), (3, 'm'), (0x140,), (0x1B,)),
                          {'arg': 'asset', 'function': '_ResourceFunction', 'n': 'Name', 'm': 'Body'})
        analysis = bgi.scan_v1(data)
        self.assertEqual(analysis.semantic_diagnostics, ())
        self.assertEqual([ref.kind for ref in analysis.references], ['internal', 'internal', 'name', 'message'])
        self.assertEqual(bgi.export_v1(analysis)[0], [{'name': 'Name', 'message': 'Body'}])

    def test_stored_select_strings_keep_structural_evidence_but_block_export(self):
        data = assemble_v1(((2, 4), (3, 'a'), (9, 2), (2, 8), (3, 'b'), (9, 2),
                           (3, 'function'), (0x1C,), (0x1B,)),
                          {'a': 'First', 'b': 'Second', 'function': '_SelectEx'})
        error = self.assert_semantic_blocked(data)
        analysis = bgi.scan_v1(data)
        self.assertEqual(len(analysis.references), 3)
        self.assertTrue(all(ref.kind == 'internal' for ref in analysis.references))
        self.assertEqual(error.opcode, 0x1C)

    def test_old_dialects_are_explicitly_blocked(self):
        for opcode in (0x145, 0x14E, 0x1B5):
            data = assemble_v1(((3, 'm'), (opcode,), (0x1B,)), {'m': 'Text'})
            error = self.assert_semantic_blocked(data)
            self.assertEqual(error.opcode, opcode)

    def test_dynamic_name_before_or_after_literal_is_not_narration(self):
        for body in (((2, 4), (8, 1), (3, 'm')),
                     ((3, 'm'), (2, 4), (8, 1)),
                     ((3, 'n'), (2, 4), (8, 1), (3, 'm'))):
            data = assemble_v1(body + ((0x140,), (0x1B,)), {'m': 'Body', 'n': 'Stale'})
            self.assert_semantic_blocked(data)

    def test_dynamic_event_after_static_speaker_fails_instead_of_inheriting(self):
        data = assemble_v1(((3, 'n'), (3, 'm'), (0x140,), (2, 4),
                           (3, 'next'), (0x143,), (0x1B,)),
                          {'n': 'Alice', 'm': 'First', 'next': 'Second'})
        self.assert_semantic_blocked(data)

    def test_arithmetic_call_results_and_uncertain_string_roles_are_blocked(self):
        for prefix in (((3, 'n'), (0x20,), (3, 'm')),
                       ((3, 'function'), (0x1C,), (3, 'm')),
                       ((0x1C,), (3, 'm')),
                       ((3, 'resource'), (3, 'n'), (3, 'm'))):
            data = assemble_v1(prefix + ((0x140,), (0x1B,)),
                               {'n': 'Name', 'm': 'Text', 'function': '_Compute', 'resource': 'asset'})
            self.assert_semantic_blocked(data)

    def test_entry_join_with_pending_literals_is_blocked(self):
        data = assemble_v1(((1, 'join'), (3, 'n'), ('label', 'join'),
                           (3, 'm'), (0x140,), (0x1B,)), {'n': 'Name', 'm': 'Body'})
        self.assert_semantic_blocked(data)

    def test_no_literal_underflow_is_not_silently_skipped(self):
        for opcode in (0x140, 0x143, 0x160):
            data = assemble_v1(((opcode,), (0x1B,)))
            self.assert_semantic_blocked(data)

    def test_unknown_semantics_with_only_internal_strings_can_be_preserved(self):
        data = assemble_v1(((0x80,), (3, 'asset'), (0xF4,)), {'asset': 'sprite'})
        analysis = bgi.scan_v1(data)
        self.assertEqual(analysis.references[0].kind, 'internal')
        self.assertEqual(bgi.patch_v1(data, {}), data)


class ProfileTests(BgiCase):
    """The opt-in VNTextPatch grouping must differ only in event evidence."""

    def stored_select(self):
        # Upstream idiom: literals are stored through 0009 before the 001C call,
        # so the default profile cannot prove which literals become options.
        return assemble_v1(((2, 4), (3, 'a'), (9, 2), (2, 8), (3, 'b'), (9, 2),
                            (3, 'function'), (0x1C,), (0x1B,)),
                           {'a': 'First', 'b': 'Second', 'function': '_SelectEx'})

    def test_default_profile_is_strict_and_unknown_profiles_are_rejected(self):
        data = make_v1_fixture()
        self.assertEqual(bgi.PROFILE, bgi.PROFILES[0])
        self.assertEqual(bgi.scan_v1(data).profile, bgi.PROFILE)
        for profile in ('', 'bgi-headered-v1', None, 0):
            self.assert_error('malformed', bgi.scan_v1, data, profile=profile)
            self.assert_error('malformed', bgi.patch_v1, data, {}, profile=profile)

    def test_stored_select_blocked_strictly_is_exported_by_vntextpatch_profile(self):
        data = self.stored_select()
        self.assert_semantic_blocked(data)
        analysis = bgi.scan_v1(data, profile=bgi.PROFILE_VNTEXTPATCH)
        self.assertEqual(analysis.profile, bgi.PROFILE_VNTEXTPATCH)
        self.assertEqual(analysis.semantic_diagnostics, ())
        rows, locators, policies = bgi.export_v1(analysis)
        self.assertEqual(rows, [{'message': 'First'}, {'message': 'Second'}])
        self.assertEqual([loc['choice_index'] for loc in locators], [0, 1])
        self.assertEqual(policies, ['absent', 'absent'])
        self.assertEqual(bgi.patch_v1(data, {}, profile=bgi.PROFILE_VNTEXTPATCH), data)

    def test_dynamic_value_between_two_literals_becomes_name_and_body(self):
        data = assemble_v1(((3, 'n'), (0x20,), (3, 'm'), (0x140,), (0x1B,)),
                           {'n': 'Name', 'm': 'Body'})
        self.assert_semantic_blocked(data)
        rows, locators, _ = bgi.export_v1(bgi.scan_v1(data, profile=bgi.PROFILE_VNTEXTPATCH))
        self.assertEqual(rows, [{'name': 'Name', 'message': 'Body'}])
        self.assertEqual([loc['speaker_status'] for loc in locators], ['static'])

    def test_leftover_pending_literals_stay_internal_instead_of_becoming_a_name(self):
        data = assemble_v1(((3, 'a'), (3, 'b'), (3, 'm'), (0x140,), (0x1B,)),
                           {'a': 'Stale', 'b': 'Name', 'm': 'Body'})
        analysis = bgi.scan_v1(data, profile=bgi.PROFILE_VNTEXTPATCH)
        kinds = {ref.text: ref.kind for ref in analysis.references}
        self.assertEqual(kinds, {'Stale': 'internal', 'Name': 'name', 'Body': 'message'})
        self.assertEqual(bgi.export_v1(analysis)[0], [{'name': 'Name', 'message': 'Body'}])

    def test_nonchoice_call_and_internal_flush_discard_pending_arguments(self):
        data = assemble_v1(((3, 'arg'), (3, 'function'), (0x1C,), (0xFE,),
                            (3, 'm'), (0x143,), (0x1B,)),
                           {'arg': 'asset', 'function': '_ResourceFunction', 'm': 'Body'})
        analysis = bgi.scan_v1(data, profile=bgi.PROFILE_VNTEXTPATCH)
        self.assertEqual([ref.kind for ref in analysis.references],
                         ['internal', 'internal', 'message'])
        self.assertEqual(bgi.export_v1(analysis)[0], [{'message': 'Body'}])

    def test_empty_speaker_is_internal_and_missing_message_stack_is_blocked(self):
        data = assemble_v1(((3, 'e'), (3, 'm'), (0x140,), (0x1B,)), {'e': '', 'm': 'Body'})
        analysis = bgi.scan_v1(data, profile=bgi.PROFILE_VNTEXTPATCH)
        rows, locators, _ = bgi.export_v1(analysis)
        self.assertIsNone(locators[0]['name_operand'])
        self.assertEqual(rows, [{'message': 'Body'}])
        empty = next(ref for ref in analysis.references if ref.text == '')
        self.assertEqual(empty.kind, 'internal')
        underflow = assemble_v1(((0x140,), (0x1B,)))
        blocked = bgi.scan_v1(underflow, profile=bgi.PROFILE_VNTEXTPATCH)
        self.assertTrue(blocked.semantic_diagnostics)
        error = self.assert_error('semantic_unsupported', bgi.export_v1, blocked)
        self.assertEqual(error.opcode, 0x140)

    def test_old_dialects_stay_blocked_in_both_profiles(self):
        for opcode in (0x145, 0x14E, 0x1B5):
            data = assemble_v1(((3, 'm'), (opcode,), (0x1B,)), {'m': 'Text'})
            for profile in bgi.PROFILES:
                with self.subTest(opcode=hex(opcode), profile=profile):
                    analysis = bgi.scan_v1(data, profile=profile)
                    self.assertTrue(analysis.semantic_diagnostics)
                    self.assertEqual(analysis.events, ())
                    error = self.assert_error('semantic_unsupported', bgi.export_v1, analysis)
                    self.assertEqual(error.opcode, opcode)

    def test_writer_and_export_agree_with_strict_on_plain_literal_scripts(self):
        data = make_v1_fixture((('Alice', 'Hello'), (None, 'Narration')), choices=('Yes', 'No'))
        strict = bgi.scan_v1(data)
        relaxed = bgi.scan_v1(data, profile=bgi.PROFILE_VNTEXTPATCH)
        self.assertEqual(bgi.export_v1(strict)[0], bgi.export_v1(relaxed)[0])
        self.assertEqual([ref.kind for ref in strict.references],
                         [ref.kind for ref in relaxed.references])
        operand = strict.references[0].operand
        self.assertEqual(bgi.patch_v1(data, {operand: 'Longer hello'},
                                      profile=bgi.PROFILE_VNTEXTPATCH),
                         bgi.patch_v1(data, {operand: 'Longer hello'}))

    def test_vntextpatch_profile_keeps_structural_checks(self):
        data = make_v1_fixture(tail=b'opaque')
        self.assertEqual(bgi.scan_v1(data, profile=bgi.PROFILE_VNTEXTPATCH).code_length,
                         bgi.scan_v1(data).code_length)
        unknown = assemble_v1(((0x04,), (0x1B,)))
        error = self.assert_error('unsupported_opcode', bgi.scan_v1, unknown,
                                  profile=bgi.PROFILE_VNTEXTPATCH)
        self.assertEqual(error.opcode, 0x04)
        self.assert_error('malformed', bgi.scan_v1, b'not a bgi script',
                          profile=bgi.PROFILE_VNTEXTPATCH)


class WriterAndPoolTests(BgiCase):
    def test_original_text_writer_roundtrip_is_byte_identical(self):
        data = make_v1_fixture(choices=('Yes', 'No'), tail=b'opaque\xff\0tail')
        analysis = bgi.scan_v1(data)
        replacements = {ref.operand: ref.text for ref in analysis.references if ref.kind != 'internal'}
        self.assertEqual(bgi.patch_v1(data, replacements), data)
        self.assertEqual(bgi.patch_v1(data, {}), data)

    def test_long_and_short_replacements_both_append_only(self):
        data = self.simple('Original text', tail=b'UNKNOWN\xffTAIL')
        old = bgi.scan_v1(data)
        ref = old.references[0]
        for replacement in ('X', 'Much longer translated text'):
            output = bgi.patch_v1(data, {ref.operand: replacement})
            self.assertGreater(len(output), len(data))
            self.assertEqual(output[old.code_base + old.code_length:len(data)],
                             data[old.code_base + old.code_length:])
            changed = set(range(ref.operand, ref.operand + 4))
            self.assertTrue(all(a == b for index, (a, b) in enumerate(zip(data, output)) if index not in changed))
            new = bgi.scan_v1(output).references[0]
            self.assertEqual(new.address, len(data))
            self.assertEqual(new.text, replacement)
            self.assertEqual(struct.unpack_from('<I', output, ref.operand)[0], len(data) - old.code_base)

    def test_shared_and_suffix_aliases_do_not_rewrite_internal_or_other_refs(self):
        data = assemble_v1(((3, 'full'), (0xFE,), (3, ('full', 6)), (0x140,),
                           (3, ('full', 6)), (0x140,), (0x1B,)),
                          {'full': 'PREFIXHello'}, tail=b'\xffopaque')
        old = bgi.scan_v1(data)
        self.assertEqual(old.references[1].address, old.references[2].address)
        self.assertEqual(old.references[1].address, old.references[0].address + 6)
        output = bgi.patch_v1(data, {old.references[1].operand: 'X'})
        new = bgi.scan_v1(output)
        self.assertEqual(new.references[0], old.references[0])
        self.assertEqual(new.references[2], old.references[2])
        self.assertEqual(new.references[1].text, 'X')
        self.assertEqual(output[old.references[0].address:len(data)], data[old.references[0].address:])

    def test_shared_name_message_can_be_changed_independently(self):
        data = assemble_v1(((3, 'same'), (3, 'same'), (0x140,), (0x1B,)), {'same': 'Same'})
        old = bgi.scan_v1(data)
        output = bgi.patch_v1(data, {old.references[0].operand: 'Name', old.references[1].operand: 'Body'})
        self.assertEqual(bgi.export_v1(bgi.scan_v1(output))[0], [{'name': 'Name', 'message': 'Body'}])

    def test_all_text_refs_move_and_repeated_auto_scans_keep_original_boundary(self):
        data = make_v1_fixture(choices=('One', 'Two'), tail=b'preserve trailing bytes')
        old = bgi.scan_v1(data)
        self.assertTrue(all(ref.kind != 'internal' for ref in old.references))
        output = bgi.patch_v1(data, {ref.operand: ref.text + '!' for ref in old.references})
        after = bgi.scan_v1(output)
        self.assertEqual(after.code_length, old.code_length)
        self.assertGreaterEqual(after.boundary['referenced_pool_min'], len(data))
        self.assertEqual(output[old.code_base + old.code_length:len(data)], data[old.code_base + old.code_length:])
        output2 = bgi.patch_v1(output, {ref.operand: ref.text + '?' for ref in after.references})
        self.assertEqual(bgi.scan_v1(output2).code_length, old.code_length)

    def test_writer_reinvokes_public_auto_scanner_without_old_length(self):
        data = self.simple()
        operand = bgi.scan_v1(data).references[0].operand
        for profile in bgi.PROFILES:
            with self.subTest(profile=profile):
                with mock.patch.object(bgi, 'scan_v1', wraps=bgi.scan_v1) as spy:
                    bgi.patch_v1(data, {operand: 'New text'}, profile=profile)
                self.assertEqual(spy.call_count, 2)
                for call in spy.call_args_list:
                    self.assertEqual(len(call.args), 1)
                    self.assertEqual(call.kwargs, {'encoding': 'cp932', 'profile': profile})

    def test_new_ambiguity_exposed_by_append_is_not_bypassed(self):
        # Original pool begins with 001B as a byte string. Moving its last live
        # reference exposes a competing terminal. The writer must reject it.
        data = assemble_v1(((3, 'm'), (0x140,), (0x1B,)), {'m': b'\x1b'}, tail=b'\0\0')
        old = bgi.scan_v1(data)
        self.assert_error('boundary_unknown', bgi.patch_v1, data, {old.references[0].operand: 'New'})

    def test_nul_missing_bad_address_and_strict_decode(self):
        data = self.simple()
        self.assert_error('malformed', bgi.scan_v1, data[:-1])
        self.assert_error('malformed', bgi.scan_v1,
                          assemble_v1(((3, 'm'), (0x140,), (0x1B,)), {'m': b'\x81'}))
        ref = bgi.scan_v1(data).references[0]
        for text in ('bad\0body', None, 10):
            self.assert_error('malformed', bgi.patch_v1, data, {ref.operand: text})
        for operand in (ref.operand + 1, 0, -1, 'x', True):
            self.assert_error('semantic_unsupported', bgi.patch_v1, data, {operand: 'No'})

    def test_encoding_overflow_and_resource_limits(self):
        data = self.simple()
        ref = bgi.scan_v1(data).references[0]
        self.assert_error('encoding_error', bgi.patch_v1, data, {ref.operand: '\U0001f600'})
        self.assert_error('budget_exceeded', bgi.patch_v1, data, {}, max_output_size=len(data) - 1)
        self.assert_error('budget_exceeded', bgi.patch_v1, data, {ref.operand: 'Longer'}, max_output_size=len(data))
        self.assert_error('budget_exceeded', bgi.scan_v1, data, max_string_size=2)
        self.assert_error('budget_exceeded', bgi.scan_v1, data, max_operations=2)
        self.assert_error('budget_exceeded', bgi.scan_v1, data, max_code_size=8)
        self.assertEqual(bgi.scan_v1(data, max_operations=3, max_code_size=16).code_length, 16)
        self.assertEqual(bgi._relative_address(100 + 0xFFFFFFFF, 100, ref.operand), 0xFFFFFFFF)
        for address in (99, 100 + 0x100000000):
            self.assert_error('overflow', bgi._relative_address, address, 100, ref.operand)

    def test_encoding_that_introduces_nul_is_rejected(self):
        # U+4142 encodes as NUL-free bytes under UTF-16BE; ASCII A does not.
        data = self.simple('䅂', encoding='utf-16be')
        ref = bgi.scan_v1(data, encoding='utf-16be').references[0]
        self.assert_error('encoding_error', bgi.patch_v1, data, {ref.operand: 'A'}, encoding='utf-16be')

    def test_emptying_message_or_name_is_not_a_semantics_preserving_edit(self):
        data = make_v1_fixture((('Alice', 'Text'),))
        for ref in bgi.scan_v1(data).references:
            self.assert_error('semantic_unsupported', bgi.patch_v1, data, {ref.operand: ''})

    def test_plain_markup_is_not_subject_to_unproven_game_rules(self):
        data = self.simple('Original')
        operand = bgi.scan_v1(data).references[0].operand
        text = '<unknown $str20> [bracket] \\q'
        output = bgi.patch_v1(data, {operand: text})
        self.assertEqual(bgi.export_v1(bgi.scan_v1(output))[0], [{'message': text}])

    def test_invalid_limits_data_and_replacement_mapping(self):
        data = self.simple()
        for key in ('max_operations', 'max_code_size', 'max_string_size'):
            for value in (0, -1, True, 1.5):
                self.assert_error('malformed', bgi.scan_v1, data, **{key: value})
        self.assert_error('malformed', bgi.scan_v1, bytearray(data))
        self.assert_error('malformed', bgi.patch_v1, data, [])
        self.assert_error('malformed', bgi.patch_v1, data, {}, max_output_size=0)


class ProvenanceAndIndependenceTests(BgiCase):
    def test_exact_568_entry_whitelist_and_known_nonempty_widths(self):
        self.assertEqual(len(OPERAND_TEMPLATES), 568)
        for opcode in (0x461, 0x462, 0x463, 0x464):
            self.assertEqual(OPERAND_TEMPLATES[opcode], '')  # Zero-operand additions.
        for opcode in (0x342, 0x45F, 0x460, 0x465):
            self.assertNotIn(opcode, OPERAND_TEMPLATES)
        expected = {0: 'i', 1: 'c', 2: 'i', 3: 'm', 8: 'i', 9: 'i', 10: 'i',
                    0x17: 'i', 0x19: 'i', 0x3F: 'i', 0x7B: 'iii', 0x7E: 'i', 0x7F: 'ii'}
        self.assertEqual({op: template for op, template in OPERAND_TEMPLATES.items() if template}, expected)
        for opcode in (0x45E, 0x480, 0x4EB):
            self.assertEqual(OPERAND_TEMPLATES[opcode], '')

    def test_every_explicit_template_consumes_its_declared_width(self):
        # Header-only/width-level test does not pretend that all VM operations
        # have known semantic effects. Synthetic operands come from the table,
        # while the expected code size is independently measured as bytes.
        for opcode, template in OPERAND_TEMPLATES.items():
            if opcode in (0x1B, 0xF4):
                continue
            operands = tuple('m' if t == 'm' else 0 for t in template)
            data = assemble_v1(((opcode, *operands), (0x1B,)), {'m': 'text'} if template == 'm' else {})
            base, header = bgi._header(data, 'cp932', 1 << 20)
            operations, _, boundary = bgi._structure(data, base, header, 'cp932', 64 << 20, 1000000, 1 << 20)
            with self.subTest(opcode=opcode):
                self.assertEqual(len(operations), 2)
                self.assertEqual(boundary['code_length'], 8 + 4 * len(template))

    def test_imports_only_stdlib_and_exact_sibling_table(self):
        root = Path(__file__).resolve().parents[1]
        for module in ('bgi.py', 'bgi_v1_opcodes.py'):
            source = (root / 'python' / 'engines' / module).read_text(encoding='utf-8')
            self.assertNotIn('sys.path', source)
            self.assertNotIn('importlib', source)
            self.assertIn('SPDX-License-Identifier:', source)
            for node in ast.walk(ast.parse(source)):
                if isinstance(node, ast.Import):
                    self.assertTrue(all(alias.name in ('struct',) for alias in node.names))
                elif isinstance(node, ast.ImportFrom):
                    if node.level:
                        self.assertEqual((node.level, node.module), (1, 'bgi_v1_opcodes'))
                        self.assertTrue({alias.name for alias in node.names} <=
                                        {'OPERAND_TEMPLATES', 'operand_template', 'LAYOUT_STACK',
                                         'LAYOUT_EXPLICIT', 'LAYOUT_EXPLICIT565'})
                    else:
                        self.assertEqual(node.module, 'dataclasses')

    def test_feedback_manifest_records_exact_sources_and_blockers(self):
        root = Path(__file__).resolve().parents[1]
        manifest = json.loads((root / 'provenance' / 'bgi-feedback-v1.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['profile'], bgi.PROFILE)
        self.assertEqual(manifest['opcode_table']['explicit_entries'], 568)
        additions = manifest['opcode_table']['added_entries']
        self.assertEqual([entry['opcode'] for entry in additions],
                         ['0x0461', '0x0462', '0x0463', '0x0464', '0x0177', '0x0468', '0x04B0'])
        self.assertTrue(all(entry['template'] == '' for entry in additions))
        self.assertEqual(manifest['sources']['vntextpatch']['commit'], 'd9c0fab7b72fdcf87d674ef12a84d3829c9188be')
        self.assertEqual(manifest['sources']['msg_tool']['commit'], 'f72716cee88554d40c1cdface2812493b14ca653')


if __name__ == '__main__':
    unittest.main()
