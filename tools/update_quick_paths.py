"""Keep the "快速路径" section at the top of every engine page that documents an extract CLI.

The section repeats the page's own extract commands right under the title, so
the first thing read is the command to run rather than the implementation.
Run without arguments to rewrite stale pages; --check only lists them.
"""
import argparse
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
HEADING = "## 快速路径"
# An extract command is `<module> extract ...`, or a `*_extract` module called
# directly with a path argument (its other stages are subcommands or --readback).
# Interpreter switches such as -B and -X utf8 stay part of the command as documented.
COMMAND = re.compile(r"^python (?:-B |-X utf8 )*-m python\.engines\."
                     r"(?:\w+ extract |\w+_extract (?=[\"/<])(?![^\n]*--readback))[^\n]*$", re.M)
# Ends at its own closing fence: the page may continue with prose, not a heading.
SECTION = re.compile(r"^" + re.escape(HEADING) + r"\n.*?^```text\n.*?^```\n\n?", re.M | re.S)
INTRO = ("识别为本格式后先直接运行提取命令：按实际路径替换占位符，多条命令对应不同方言或来源，按下文的识别条件选一条。"
         "提取器自行校验格式并用原文走真实的解析与回写，结构不符时拒绝并指出失败位置。"
         "命令成功就不必读实现源码或研究资料；失败时再按报错读本页对应章节和 `python/` 中的实现。")


def render(text: str) -> str:
    """Page text with an up-to-date quick-path section, or unchanged without commands."""
    body = SECTION.sub("", text)
    commands = list(dict.fromkeys(COMMAND.findall(body)))
    title = re.match(r"# [^\n]*\n", body)
    if not commands or not title:
        return body
    block = "\n".join([HEADING, "", INTRO, "", "```text", *commands, "```", "", ""])
    return body[:title.end()] + "\n" + block + body[title.end():].lstrip("\n")


def stale_pages(root: Path = ROOT, *, write: bool = False) -> list[str]:
    stale = []
    for path in sorted((root / "engines").rglob("*.md")):
        raw = path.read_bytes()
        text = raw.decode("utf-8").replace("\r\n", "\n")
        updated = render(text)
        if updated != text:
            stale.append(path.relative_to(root).as_posix())
            if write:
                path.write_bytes(updated.replace("\n", "\r\n" if b"\r\n" in raw else "\n").encode("utf-8"))
    return stale


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="list stale pages and exit 1 without writing")
    args = parser.parse_args()
    stale = stale_pages(write=not args.check)
    for page in stale:
        print(("stale: " if args.check else "updated: ") + page)
    if args.check and stale:
        sys.exit(1)


if __name__ == "__main__":
    main()
