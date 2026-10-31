"""Shared delete-only line-break rule used by variable-length text writers."""
import unittest

from python.common.line_layout import drops_only_line_breaks


BREAK = lambda token: token == "\n"


class LineLayoutTests(unittest.TestCase):
    def test_identical_and_fewer_breaks_are_allowed(self):
        before = ["A", "\n", "B", "\n", "C"]
        self.assertTrue(drops_only_line_breaks(before, before, BREAK))
        self.assertTrue(drops_only_line_breaks(before, ["A", "\n", "B", "C"], BREAK))
        self.assertTrue(drops_only_line_breaks(before, ["A", "B", "C"], BREAK))

    def test_added_or_retyped_break_is_rejected(self):
        before = ["A", "B"]
        self.assertFalse(drops_only_line_breaks(before, ["A", "\n", "B"], BREAK))
        self.assertFalse(drops_only_line_breaks(["A", "\n", "B"],
                                                ["A", "\r\n", "B"], BREAK))

    def test_break_may_not_move_across_a_control(self):
        before = ["$v", "\n", "$s"]
        self.assertFalse(drops_only_line_breaks(before, ["\n", "$v", "$s"], BREAK))
        self.assertTrue(drops_only_line_breaks(before, ["$v", "$s"], BREAK))

    def test_changed_control_is_rejected(self):
        before = ["A", "\n", "$v", "B"]
        self.assertFalse(drops_only_line_breaks(before, ["A", "$s", "B"], BREAK))
        self.assertFalse(drops_only_line_breaks(before, ["A", "$v", "$v", "B"], BREAK))


if __name__ == "__main__":
    unittest.main()
