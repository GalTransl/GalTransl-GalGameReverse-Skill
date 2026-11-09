import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from python.archives import asar
from python.common.binary import FormatError
from python.common.safety import write_new_tree
from python.engines import tyrano, tyrano_extract


def build_asar(files, *, unpacked=(), integrity=(), extra_header=None):
    """Synthetic asar: files is {path: bytes} in data order."""
    root, data, offset = {"files": {}}, b"", 0
    for path, payload in files.items():
        node = root
        parts = path.split("/")
        for part in parts[:-1]:
            node = node["files"].setdefault(part, {"files": {}})
        entry = {"size": len(payload)}
        if path in unpacked:
            entry["unpacked"] = True
        else:
            entry["offset"] = str(offset)
            data += payload
            offset += len(payload)
        if path in integrity:
            entry["integrity"] = {"algorithm": "SHA256", "hash": "0" * 64, "blockSize": 4, "blocks": []}
        node["files"][parts[-1]] = entry
    if extra_header:
        extra_header(root)
    header = json.dumps(root, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    padding = bytes((-len(header)) % 4)
    payload = 4 + len(header) + len(padding)
    return struct.pack("<4I", 4, payload + 4, payload, len(header)) + header + padding + data


SCENE = (
    ";comment\r\n"
    "[chara_new name=\"hero\" storage=\"h.png\" jname=\"ヒロ\"]\r\n"
    "*start\r\n"
    "#\r\n"
    "地の文です。[p]\r\n"
    "#ヒロ\r\n"
    "一行目[l][r]\r\n"
    "　二行目[p]\r\n"
    "#hero:smile\r\n"
    "キーで話す[p]\r\n"
    "/*\r\n"
    "隠しテキスト[p]\r\n"
    "*/\r\n"
    "[iscript]\r\n"
    "var a = [1, 2];\r\n"
    "[endscript]\r\n"
    "[html]\r\n"
    "<div>表示しないHTML</div>\r\n"
    "[endhtml]\r\n"
    "[macro name=\"m\"]\r\n"
    "テンプレート[p]\r\n"
    "[endmacro]\r\n"
    "_　先頭に空白[p]\r\n"
    "[glink text=\"はい\" target=\"*yes\"]\r\n"
    "[jump storage=\"other.ks\"]\r\n"
)


class AsarTests(unittest.TestCase):
    def test_read_rebuild_and_verify(self):
        files = {"a.txt": b"AAAA", "dir/b.bin": b"B" * 10, "dir/c.ks": b"CC", "z": b"Z"}
        raw = build_asar(files, unpacked={"z"})
        index = asar.read_index(io.BytesIO(raw))
        self.assertEqual([e.path for e in index.entries], list(files))
        self.assertEqual(asar.read_member(io.BytesIO(raw), index, index.member("dir/b.bin")), b"B" * 10)
        with self.assertRaises(FormatError):
            asar.read_member(io.BytesIO(raw), index, index.member("z"))
        same = io.BytesIO()
        asar.write_rebuilt(io.BytesIO(raw), index, {}, same)
        self.assertEqual(same.getvalue(), raw)
        changes = {"dir/b.bin": b"short", "a.txt": "长一些的内容".encode()}
        out = io.BytesIO()
        written = asar.write_rebuilt(io.BytesIO(raw), index, changes, out)
        self.assertEqual(written, asar.rebuilt_size(index, changes))
        report = asar.verify_rebuilt(io.BytesIO(raw), index, io.BytesIO(out.getvalue()), changes)
        self.assertEqual(report["members_compared"], 3)
        rebuilt = asar.read_index(io.BytesIO(out.getvalue()))
        self.assertEqual(asar.read_member(io.BytesIO(out.getvalue()), rebuilt, rebuilt.member("dir/c.ks")), b"CC")

    def test_integrity_is_recomputed(self):
        raw = build_asar({"x": b"123456789"}, integrity={"x"})
        index = asar.read_index(io.BytesIO(raw))
        out = io.BytesIO()
        asar.write_rebuilt(io.BytesIO(raw), index, {"x": b"abcdef"}, out)
        node = asar.read_index(io.BytesIO(out.getvalue())).header["files"]["x"]
        self.assertEqual(node["integrity"]["blocks"], [__import__("hashlib").sha256(b"abcd").hexdigest(),
                                                       __import__("hashlib").sha256(b"ef").hexdigest()])

    def test_rejects_bad_headers(self):
        good = build_asar({"a": b"1"})
        with self.assertRaises(FormatError):
            asar.read_index(io.BytesIO(b"\x05" + good[1:]))
        with self.assertRaises(FormatError):
            asar.read_index(io.BytesIO(build_asar({"a": b"1"}, extra_header=lambda r: r["files"].update(
                {"..": {"size": 0, "offset": "0"}}))))
        def overlap(root):
            root["files"]["b"] = {"size": 1, "offset": "0"}
        with self.assertRaises(FormatError):
            asar.read_index(io.BytesIO(build_asar({"a": b"12"}, extra_header=overlap)))
        with self.assertRaises(FormatError):
            asar.plan_rebuild(asar.read_index(io.BytesIO(good)), {"missing": b""})

    def test_stream_budget_is_enforced(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "out"
            with self.assertRaises(FormatError):
                write_new_tree(target, [], streams=[("big.bin", lambda sink: sink.write(b"x" * 10), 5)])
            self.assertFalse(target.exists())


class TyranoScriptTests(unittest.TestCase):
    def setUp(self):
        self.raw = SCENE.encode("utf-8")
        self.script = tyrano.parse(self.raw)
        self.charas = tyrano.display_names([self.script])
        self.rows, _ = tyrano.export_rows(self.script, self.charas)

    def test_export_follows_engine_dispatch(self):
        self.assertEqual(self.rows, [
            {"message": "地の文です。"},
            {"name": "ヒロ", "message": "一行目[l][r]二行目"},
            {"name": "ヒロ", "message": "キーで話す"},
            {"name": "ヒロ", "message": "　先頭に空白"},
            {"message": "はい"},
        ])
        self.assertEqual(self.script.skipped_block_text, 3)
        self.assertEqual(tyrano.rebuild(self.raw, self.script, self.rows, {}, self.charas, label="t"), self.raw)

    def test_variable_length_writeback_names_and_escape(self):
        translated = [dict(r) for r in self.rows]
        translated[0]["message"] = "#井号开头的长旁白"
        translated[1]["message"] = "第一段[l][r]第二段更长一些"
        translated[3]["message"] = "　保留全角空格"
        translated[4]["message"] = "是的"
        names = tyrano.name_map([("r", "ヒロ", "阿宏")])
        out = tyrano.rebuild(self.raw, self.script, translated, names, self.charas, label="t")
        tyrano.verify(out, self.script, translated, names, self.charas, label="t")
        text = out.decode("utf-8")
        self.assertIn("_#井号开头的长旁白[p]", text)
        self.assertIn("#阿宏\r\n", text)
        self.assertIn('jname="阿宏"', text)
        self.assertIn("#hero:smile", text)          # key lines stay identifiers
        self.assertIn('text="是的"', text)
        # The source indentation before the second line is kept (the engine trims it).
        self.assertIn("第一段[l][r]\r\n　第二段更长一些[p]", text)

    def test_rejections(self):
        def attempt(index, message, names=None):
            rows = [dict(r) for r in self.rows]
            rows[index]["message"] = message
            return tyrano.rebuild(self.raw, self.script, rows, names or {}, self.charas, label="t")
        with self.assertRaises(tyrano.TyranoError):
            attempt(1, "少了标签[r]")
        with self.assertRaises(tyrano.TyranoError):
            attempt(1, "[l][r]开头是标签")
        with self.assertRaises(tyrano.TyranoError):
            attempt(0, "换\n行")
        with self.assertRaises(tyrano.TyranoError):
            attempt(4, "有 空格")
        line_end = "#\nテキスト\n[p]\n".encode()
        script = tyrano.parse(line_end)
        with self.assertRaises(tyrano.TyranoError):
            tyrano.rebuild(line_end, script, [{"message": "行尾空白  "}], {}, {}, label="t")
        with self.assertRaises(tyrano.TyranoError):
            tyrano.name_map([("a", "ヒロ", "甲"), ("b", "ヒロ", "乙")])
        with self.assertRaises(tyrano.TyranoError):
            attempt(0, "旁白", {"ヒロ": "名 字"})

    def test_unterminated_blocks_are_rejected(self):
        for source in ("[iscript]\nvar a;\n", "/*\nx\n", "[macro name=a]\nx\n"):
            with self.assertRaises(tyrano.TyranoError):
                tyrano.parse(source.encode())


class TyranoWorkspaceTests(unittest.TestCase):
    def game(self, root: Path, *, loose=False):
        files = {
            "package.json": b'{"main":"main.js"}',
            "data/system/Config.tjs": b";projectID=demo\n;patch_apply_auto=true\n",
            "data/scenario/first.ks": b"[jump storage=\"scene.ks\"]\n",
            "data/scenario/scene.ks": SCENE.replace("other.ks", "first.ks").encode("utf-8"),
            "data/scenario/spare.ks": "#ヒロ\n予備[p]\n".encode("utf-8"),
            "data/bgm/a.ogg": b"OggS" + bytes(100),
        }
        if loose:
            for name, data in files.items():
                path = root.joinpath(*name.split("/"))
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
        else:
            (root / "resources").mkdir(parents=True)
            (root / "resources" / "app.asar").write_bytes(build_asar(files))
        return files

    def translate(self, workspace: Path):
        rows = json.loads((workspace / "gt_input" / "scene.json").read_text(encoding="utf-8"))
        rows[0]["message"] = "这是更长的中文旁白句子。"
        for row in rows:
            if row.get("name") == "ヒロ":
                row["name"] = "阿宏"
        (workspace / "gt_output" / "scene.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")

    def test_asar_extract_pack_and_tpatch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "game"
            files = self.game(root)
            before = (root / "resources" / "app.asar").read_bytes()
            report = tyrano_extract.extract(root, Path(temp) / "ws")
            ws = Path(temp) / "ws"
            self.assertEqual(sorted(p.name for p in (ws / "gt_input").iterdir()), ["scene.json"])
            self.assertEqual(report["reachability"]["unreferenced"], ["data/scenario/spare.ks"])
            self.translate(ws)
            result = tyrano_extract.pack(ws, Path(temp) / "out")
            self.assertEqual(result["changed_members"], ["data/scenario/scene.ks", "data/scenario/spare.ks"])
            new = (Path(temp) / "out" / "resources" / "app.asar").read_bytes()
            index = asar.read_index(io.BytesIO(new))
            scene = asar.read_member(io.BytesIO(new), index, index.member("data/scenario/scene.ks")).decode()
            self.assertIn("这是更长的中文旁白句子。[p]", scene)
            self.assertIn("#阿宏", asar.read_member(io.BytesIO(new), index, index.member("data/scenario/spare.ks")).decode())
            self.assertEqual(asar.read_member(io.BytesIO(new), index, index.member("data/bgm/a.ogg")), files["data/bgm/a.ogg"])
            self.assertTrue((Path(temp) / "out" / "reports" / "pack.json").is_file())
            patch = tyrano_extract.pack(ws, Path(temp) / "patch", mode="tpatch")
            with zipfile.ZipFile(Path(temp) / "patch" / "demo.tpatch") as archive:
                self.assertEqual(sorted(archive.namelist()), patch["changed_members"])
            self.assertEqual((root / "resources" / "app.asar").read_bytes(), before)

    def test_include_unreferenced_and_source_change(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "game"
            self.game(root)
            tyrano_extract.extract(root, Path(temp) / "ws", include_unreferenced=True)
            ws = Path(temp) / "ws"
            self.assertEqual(sorted(p.name for p in (ws / "gt_input").iterdir()), ["scene.json", "spare.json"])
            self.translate(ws)
            (root / "resources" / "app.asar").write_bytes(build_asar({"data/scenario/scene.ks": b"x"}))
            with self.assertRaises(ValueError):
                tyrano_extract.pack(ws, Path(temp) / "out")

    def test_loose_source_writes_changed_files_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "game"
            self.game(root, loose=True)
            tyrano_extract.extract(root, Path(temp) / "ws")
            ws = Path(temp) / "ws"
            self.translate(ws)
            result = tyrano_extract.pack(ws, Path(temp) / "out")
            self.assertEqual(result["mode"], "loose")
            written = sorted(p.relative_to(Path(temp) / "out").as_posix()
                             for p in (Path(temp) / "out").rglob("*") if p.is_file())
            self.assertEqual(written, ["data/scenario/scene.ks", "data/scenario/spare.ks", "reports/pack.json"])

    def test_unknown_translation_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "game"
            self.game(root)
            tyrano_extract.extract(root, Path(temp) / "ws")
            ws = Path(temp) / "ws"
            (ws / "gt_output" / "guess.json").write_text("[]", encoding="utf-8")
            with self.assertRaises(ValueError):
                tyrano_extract.pack(ws, Path(temp) / "out")


if __name__ == "__main__":
    unittest.main()
