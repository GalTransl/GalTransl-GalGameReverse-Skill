"""A complete synthetic TmrHiro text -> JSON/sidecar -> changed script route."""

import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from python.common.binary import FormatError
from python.common.contract import dump_rows, load_json, make_manifest, validate_translation
from python.common.safety import write_new_tree
from python.engines.tmrhiro import patch_text, read_text, write_text


class RoundtripRecipeTests(unittest.TestCase):
    def test_independent_export_and_changed_length_injection(self):
        original_texts = ("始まり", "同じ", "同じ")
        # Independent hand-assembled fixture, not writer-generated test input.
        raw = b"".join(struct.pack("<h", len(text.encode("cp932"))) + text.encode("cp932")
                       for text in original_texts)
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            game = work / "original"
            game.mkdir()
            original_path = game / "message"
            original_path.write_bytes(raw)
            rows = [{"message": text} for text in read_text(raw)]
            manifest = make_manifest(engine="tmrhiro", variant="signed-i16-text",
                                     reference="python/engines/tmrhiro.py",
                                     sources={"message": raw}, rows=rows,
                                     locators=[{"kind": "record-index", "index": i} for i in range(len(rows))],
                                     encoding="cp932")
            write_new_tree(work / "exported", [
                ("translation/message.json", dump_rows(rows)),
                ("metadata/message.json", json.dumps(manifest, ensure_ascii=False).encode("utf-8")),
            ])
            exported = load_json((work / "exported/translation/message.json").read_bytes())
            metadata = load_json((work / "exported/metadata/message.json").read_bytes())
            self.assertEqual(write_text(read_text(raw)), raw)  # Real writer exercised.
            translated = [{"message": "a longer translated opening"}, {"message": "A"}, {"message": "different"}]
            checked = validate_translation(metadata, {"message": original_path.read_bytes()}, exported, translated)
            rebuilt = patch_text(raw, {i: row["message"] for i, row in enumerate(checked)})
            self.assertEqual(read_text(rebuilt), tuple(row["message"] for row in translated))
            self.assertNotEqual(len(rebuilt), len(raw))
            write_new_tree(work / "rebuilt", [("message", rebuilt)])
            self.assertEqual(original_path.read_bytes(), raw)
            self.assertEqual((work / "rebuilt/message").read_bytes(), rebuilt)

    def test_unrepresentable_translation_is_rejected_before_output(self):
        raw = struct.pack("<h", 3) + b"abc"
        rows = [{"message": "abc"}]
        manifest = make_manifest(engine="tmrhiro", variant="signed-i16-text",
                                 reference="python/engines/tmrhiro.py", sources={"message": raw},
                                 rows=rows, locators=[{"kind": "record-index", "index": 0}], encoding="cp932")
        with self.assertRaises(FormatError):
            validate_translation(manifest, {"message": raw}, rows, [{"message": "汉语"}])


if __name__ == "__main__":
    unittest.main()
