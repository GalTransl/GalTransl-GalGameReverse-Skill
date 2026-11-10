# SPDX-License-Identifier: GPL-3.0-or-later
"""Synthetic Entis NOA / ERISA-N / SRCXML dialect fixtures; no game assets."""

import hashlib
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest

from python.archives import entis_noa as noa
from python.archives.entis_erisa import decode_bshf, decode_nemesis
from python.common.binary import FormatError
from python.engines import entis_extract, entis_srcxml as sx

# Arbitrary bytes that happen to form a valid ERISA-N stream (first 16 bits zero).
# The decoded hash pins the ported decoder; real-archive checksums are covered by
# the manual regression described in engines/entis-gls.md.
NEMESIS_INPUT = b"\0\0" + hashlib.sha256(bytes([0])).digest() * 8
NEMESIS_SIZE = 200
NEMESIS_SHA256 = "741c73eed92e655f0d4b935c3beeac0bdf4aa942f5afc003609dca4bb2265ed7"


def nemesis_member(path="packed.bin"):
    plain = decode_nemesis(NEMESIS_INPUT, NEMESIS_SIZE)
    stored = NEMESIS_INPUT + struct.pack("<I", noa.xor_checksum(plain))
    return noa.NoaMember(path, stored, NEMESIS_SIZE, noa.ENC_ERISA_N), plain


def header(body):
    return (noa.MAGIC + struct.pack("<II", noa.FORMAT_ID, 0)
            + noa.DESCRIPTION.ljust(40, b"\0") + struct.pack("<Q", body))


def entry(size, attr, enc, rel, name, extra=b""):
    raw = name if isinstance(name, bytes) else name.encode("utf-8") + b"\0"
    return (struct.pack("<QIIq", size, attr, enc, rel) + b"\0" * 8
            + struct.pack("<I", len(extra)) + extra + struct.pack("<I", len(raw)) + raw)


def directory(entries):
    payload = struct.pack("<I", len(entries)) + b"".join(entries)
    return noa.DIR_TAG + struct.pack("<Q", len(payload)) + payload


def filedata(data):
    return noa.FILE_TAG + struct.pack("<Q", len(data)) + data


def nested_archive():
    """root: a.txt, sub/ (directory record wrapping a nested DirEntry) -> b.txt."""
    a, b = b"alpha", b"bravo!"
    root_len = len(directory([entry(0, noa.ATTR_UTF8, 0, 0, "a.txt"),
                              entry(0, noa.ATTR_UTF8 | 0x10, 0, 0, "sub")]))
    a_rec = filedata(a)
    nested_len = len(directory([entry(0, noa.ATTR_UTF8, 0, 0, "b.txt")]))
    nested = directory([entry(len(b), noa.ATTR_UTF8, 0, nested_len, "b.txt")]) + filedata(b)
    sub_rec = noa.FILE_TAG + struct.pack("<Q", len(nested)) + nested
    root = directory([entry(len(a), noa.ATTR_UTF8, 0, root_len, "a.txt"),
                      entry(len(nested), noa.ATTR_UTF8 | 0x10, 0, root_len + len(a_rec), "sub")])
    body = root + a_rec + sub_rec
    return header(len(body)) + body


def read(data, **kwargs):
    stream = io.BytesIO(data)
    index = noa.read_index(stream, **kwargs)
    return stream, index


class NoaReaderTests(unittest.TestCase):
    def test_flat_raw_and_erisa_n_roundtrip(self):
        packed, plain = nemesis_member()
        self.assertEqual(hashlib.sha256(plain).hexdigest(), NEMESIS_SHA256)
        data = noa.build_noa([noa.NoaMember.raw("中文.srcxml", b"<xscript/>"), packed])
        self.assertEqual(struct.unpack_from("<Q", data, 0x38)[0], len(data) - 0x40)
        stream, index = read(data)
        self.assertEqual([e.path for e in index.entries], ["中文.srcxml", "packed.bin"])
        self.assertEqual(noa.read_member(stream, index, index.entries[0]), b"<xscript/>")
        self.assertEqual(noa.read_member(stream, index, index.entries[1]), plain)
        self.assertEqual(index.entries[1].encoding_name, "erisa-n")

    def test_nested_directory(self):
        stream, index = read(nested_archive())
        self.assertEqual([e.path for e in index.entries], ["a.txt", "sub/b.txt"])
        self.assertEqual(index.directories, ("sub",))
        self.assertEqual(noa.read_member(stream, index, index.entries[1]), b"bravo!")

    def test_checksum_and_truncation_rejected(self):
        packed, _ = nemesis_member()
        bad = noa.NoaMember(packed.path, packed.stored[:-4] + b"\0\0\0\0", packed.size,
                            packed.encoding)
        stream, index = read(noa.build_noa([bad]))
        with self.assertRaisesRegex(FormatError, "checksum"):
            noa.read_member(stream, index, index.entries[0])
        with self.assertRaises(FormatError):
            decode_nemesis(NEMESIS_INPUT[:6], NEMESIS_SIZE)
        with self.assertRaisesRegex(FormatError, "budget"):
            decode_nemesis(NEMESIS_INPUT, NEMESIS_SIZE, max_output=10)

    def test_encodings_without_support_or_key_are_refused(self):
        for enc in (noa.ENC_BSHF, noa.ENC_ERISA_CRYPT, noa.ENC_SIMPLE32):
            member = noa.NoaMember("x.bin", b"\0" * 40, 36, enc)
            stream, index = read(noa.build_noa([member]))
            with self.assertRaisesRegex(FormatError, "password"):
                noa.read_member(stream, index, index.entries[0])
        member = noa.NoaMember("x.bin", b"\0" * 8, 8, noa.ENC_ERISA_CRYPT32)
        stream, index = read(noa.build_noa([member]))
        with self.assertRaisesRegex(FormatError, "unsupported"):
            noa.read_member(stream, index, index.entries[0], password="key")

    def test_bshf_is_a_per_block_bit_permutation(self):
        plain = bytes(range(64))
        blocks = 2
        # Probe the permutation with unit vectors, then invert it to encrypt.
        perms = []
        for block in range(blocks):
            perm = []
            for bit in range(256):
                probe = bytearray(32 * blocks + 4)
                probe[block * 32 + bit // 8] = 0x80 >> (bit % 8)
                out = decode_bshf(bytes(probe), "pass")[block * 32:block * 32 + 32]
                value = int.from_bytes(out, "big")
                self.assertEqual(bin(value).count("1"), 1)
                perm.append(255 - value.bit_length() + 1)
            self.assertEqual(sorted(perm), list(range(256)))
            perms.append(perm)
        cipher = bytearray(32 * blocks + 4)
        for block, perm in enumerate(perms):
            for src, dst in enumerate(perm):
                if plain[block * 32 + dst // 8] & (0x80 >> (dst % 8)):
                    cipher[block * 32 + src // 8] |= 0x80 >> (src % 8)
        self.assertEqual(decode_bshf(bytes(cipher), "pass"), plain)
        with self.assertRaisesRegex(FormatError, "inside a block"):
            decode_bshf(b"\0" * 40, "pass")

    def test_malformed_archives_rejected(self):
        good = noa.build_noa([noa.NoaMember.raw("a.txt", b"abc")])
        cases = {
            "magic": b"Xntis" + good[5:],
            "format": good[:8] + b"\0\0\0\0" + good[12:],
            "body": good[:0x38] + struct.pack("<Q", len(good)) + good[0x40:],
            "truncated": good[:-1],
        }
        for label, data in cases.items():
            with self.subTest(label), self.assertRaises(FormatError):
                read(data)

    def _single(self, attr=noa.ATTR_UTF8, enc=0, name="a.txt", size=3, tag=noa.FILE_TAG,
                stored=b"abc", rel=None, count=None):
        dir_len = len(directory([entry(0, attr, enc, 0, name)]))
        d = directory([entry(size, attr, enc, dir_len if rel is None else rel, name)])
        if count is not None:
            d = d[:16] + struct.pack("<I", count) + d[20:]
        body = d + tag + struct.pack("<Q", len(stored)) + stored
        return header(len(body)) + body

    def test_entry_level_rejections(self):
        bad = {
            "raw size": dict(size=4),
            "tag": dict(tag=b"notdata\0"),
            "offset": dict(rel=1 << 40),
            "count": dict(count=1000),
            "traversal": dict(name="../evil"),
            "absolute": dict(name="/evil"),
            "drive": dict(name="c:evil"),
            "attr": dict(attr=noa.ATTR_UTF8 | 0x20),
        }
        for label, kwargs in bad.items():
            with self.subTest(label):
                data = self._single(**kwargs)
                if label == "attr":
                    # 0x20/0x40 markers end the listing, leaving no members.
                    self.assertEqual(read(data)[1].entries, ())
                    continue
                with self.assertRaises(FormatError):
                    read(data)

    def test_name_encoding(self):
        sjis = "台詞.txt".encode("cp932") + b"\0"
        data = self._single(attr=0, name=sjis)
        with self.assertRaisesRegex(FormatError, "name_encoding"):
            read(data)
        self.assertEqual(read(data, name_encoding="cp932")[1].entries[0].path, "台詞.txt")
        with self.assertRaises(FormatError):
            read(self._single(name="a.txt\0junk".encode() + b"\0"))

    def test_entry_limit(self):
        data = noa.build_noa([noa.NoaMember.raw(f"{i}.txt", b"x") for i in range(3)])
        with self.assertRaisesRegex(FormatError, "limit"):
            read(data, max_entries=2)

    def test_writer_constraints_and_passthrough(self):
        packed, plain = nemesis_member()
        src_stream, src_index = read(noa.build_noa([packed, noa.NoaMember.raw("b", b"1")]))
        copied = [noa.member_from_entry(src_stream, src_index, e) for e in src_index.entries]
        stream, index = read(noa.build_noa(copied))
        self.assertEqual(noa.read_member(stream, index, index.entries[0]), plain)
        with self.assertRaises(FormatError):
            noa.build_noa([noa.NoaMember.raw("dir/a", b"1")])
        with self.assertRaises(FormatError):
            noa.build_noa([noa.NoaMember.raw("a", b"1"), noa.NoaMember.raw("A", b"2")])
        with self.assertRaises(FormatError):
            noa.build_noa([])
        foreign = read(noa.build_noa([noa.NoaMember.raw("a", b"1")]))[1].entries[0]
        with self.assertRaises(FormatError):
            noa.read_stored(stream, index, foreign)


SAMPLE = (
    '<?xml version="1.0" encoding="utf-8"?>\r\n<xscript>\r\n\t<code>\r\n'
    '\t\t<msg @l="3" name_EN="Ann" name_JA="アン"\r\n\t\t   text_EN="Hi&#32;there&amp;&quot;x&quot;"'
    ' text_JA="こんにちは&#32;%fp\\n:です" voices=""/>\r\n'
    '\t\t<msg @l="4" name_EN="" name_JA="" text_EN="Narration" text_JA="地の文&#8;"/>\r\n'
    '\t\t<msg @l="5" name_EN="%name" name_JA="%name" text_EN="Me" text_JA="俺"/>\r\n'
    '\t\t<open_line_msg @l="6" title_EN="Chat" title_JA="チャット"/>\r\n'
    '\t\t<select @l="7">\r\n\t\t\t<menu goto="A" text="Yes" text_EN="Yes" text_JA="はい"/>\r\n'
    '\t\t</select>\r\n\t\t<eval expr="x[&quot;f&quot;]:=1"/>\r\n\t</code>\r\n</xscript>\r\n'
)


class SrcxmlDialectTests(unittest.TestCase):
    def test_extract(self):
        records = sx.extract_records(SAMPLE, "JA")
        self.assertEqual([r.kind for r in records], ["message"] * 3 + ["title", "choice"])
        self.assertEqual(records[0].message, "こんにちは %fp\\n:です")
        self.assertEqual(records[0].line, "3")
        self.assertEqual(records[1].message, "地の文\b")
        self.assertEqual([sx.name_policy(r) for r in records],
                         ["writable", "absent", "context", "absent", "absent"])
        self.assertEqual(sx.protected_tokens(records[0].message), ["%fp", "\\n"])
        self.assertEqual(sx.languages(SAMPLE), ["EN", "JA"])
        with self.assertRaisesRegex(ValueError, "multiple languages"):
            sx.extract_records(SAMPLE)
        self.assertEqual(sx.escape_convention_mismatches(SAMPLE, "EN"), [])

    def test_patch_preserves_other_bytes(self):
        identity = {r.index: {"message": r.message} for r in sx.extract_records(SAMPLE, "JA")}
        self.assertEqual(sx.patch_records(SAMPLE, identity, "JA"), SAMPLE)
        out = sx.patch_records(SAMPLE, {0: {"message": '你好 & "x" <y> %fp\\n:', "name": "安"},
                                        4: {"message": "是的"}}, "JA")
        self.assertIn('text_JA="你好&#32;&amp;&#32;&quot;x&quot;&#32;&#60;y&#62;&#32;%fp\\n:"', out)
        self.assertIn('name_JA="安"', out)
        self.assertIn('text_EN="Hi&#32;there&amp;&quot;x&quot;"', out)
        self.assertEqual(out.replace('你好&#32;&amp;&#32;&quot;x&quot;&#32;&#60;y&#62;&#32;%fp\\n:',
                                     "こんにちは&#32;%fp\\n:です").replace('"安"', '"アン"')
                         .replace('"是的"', '"はい"'), SAMPLE)
        self.assertEqual(sx.extract_records(out, "JA")[4].message, "是的")

    def test_patch_rejections(self):
        for change in ({1: {"name": "x"}}, {9: {"message": "x"}}, {0: {"voice": "x"}},
                       {0: {"message": "a\nb"}}, {0: {"message": "a\0"}}):
            with self.subTest(change), self.assertRaises(ValueError):
                sx.patch_records(SAMPLE, change, "JA")

    def test_lexical_rejections(self):
        bad = [
            '<!DOCTYPE x><xscript/>', '<xscript><code></xscript>', '<xscript a="1" a="2"/>',
            '<xscript a=1/>', '<xscript a="&foo;"/>', '<xscript a="&#0;"/>', '<a/><b/>',
            '<xscript a="<"/>', '<?xml version="1.0" encoding="shift_jis"?><xscript/>',
            '<xscript><![CDATA[x]]></xscript>', '<xscript', '<xscript/>text',
        ]
        for text in bad:
            with self.subTest(text), self.assertRaises(ValueError):
                sx.parse_document(text)
        with self.assertRaisesRegex(ValueError, "xscript"):
            sx.extract_records("<root/>")
        with self.assertRaisesRegex(ValueError, "missing text_ZH"):
            sx.extract_records(SAMPLE, "ZH")


class WorkflowTests(unittest.TestCase):
    def test_extract_rebuild_readback(self):
        packed, plain = nemesis_member("other.bin")
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            game = tmp / "game"
            game.mkdir()
            base = noa.build_noa([noa.NoaMember.raw("scene.srcxml", SAMPLE.encode("utf-8")),
                                  noa.NoaMember.raw("empty.srcxml",
                                                    b"<xscript><code/></xscript>"), packed])
            (game / "script.noa").write_bytes(base)
            work = tmp / "work"
            summary = entis_extract.extract(game, work, language="JA")
            self.assertEqual((summary["scripts_exported"], summary["empty_scripts"],
                              summary["rows"]), (1, 1, 5))
            rows = json.loads((work / "gt_input/scene.json").read_text("utf-8"))
            self.assertEqual(rows[0], {"name": "アン", "message": "こんにちは %fp\\n:です"})
            self.assertNotIn("name", rows[1])
            rows[0] = {"name": "安", "message": "你好，这是更长的中文译文 %fp\\n:了"}
            rows[4]["message"] = "是"
            (work / "gt_output/scene.json").write_text(json.dumps(rows, ensure_ascii=False),
                                                       "utf-8")
            report = entis_extract.rebuild(work, tmp / "out", base=game / "script.noa")
            self.assertEqual((report["members"], report["replaced_in_base"]), (3, 1))
            built = tmp / "out/script.noa"
            stream, index = read(built.read_bytes())
            self.assertEqual(index.entries[0].encoding, noa.ENC_RAW)
            self.assertEqual(noa.read_member(stream, index, index.entries[2]), plain)
            entis_extract.readback(work, built, tmp / "back")
            back = json.loads((tmp / "back/gt_input/scene.json").read_text("utf-8"))
            self.assertEqual(back, rows)
            only = entis_extract.rebuild(work, tmp / "only", name="patch9.noa")
            self.assertEqual(only["members"], 1)
            # Changing a protected control token or a context-only name is refused.
            bad = list(rows)
            bad[0] = {"name": "安", "message": "没有控制码"}
            (work / "gt_output/scene.json").write_text(json.dumps(bad, ensure_ascii=False),
                                                       "utf-8")
            with self.assertRaises(FormatError):
                entis_extract.rebuild(work, tmp / "bad", name="x.noa")
            self.assertEqual((game / "script.noa").read_bytes(), base)

    def test_mount_order(self):
        text = ('<script src="main.csx">\r\n<archive path="$(CURRENT)\\patch2.noa"/>\r\n'
                '<archive path="$(CURRENT)\\patch1.noa"/>\r\n<archive path="$(CURRENT)\\a.noa"/>'
                '\r\n<file path="$(CURRENT)\\script"/></script>')
        self.assertEqual(entis_extract.mount_order(text),
                         (["patch2.noa", "patch1.noa", "a.noa"], "main.csx"))


if __name__ == "__main__":
    unittest.main()
