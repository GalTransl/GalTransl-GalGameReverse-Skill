# SPDX-License-Identifier: GPL-3.0-only
"""Delivery block and state file a workspace extractor finishes with.

The hand-off tells a translator where the files are, what to keep intact
while translating and what is still unverified. The extractor already holds
those facts, so it states them once instead of leaving them to be re-measured
from the workspace. Hashes, encodings and offsets stay in the extraction
report and manifests, where the writeback reads them.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

STATE_FILE = "reports/translation-state.md"
_NEXT = ("Extraction is complete. Hand over gt_input now; pack, JIS/GBK preflight and "
         "repacking need translations in gt_output and are not part of extraction.")


def _cell(value) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _table(header, rows) -> list[str]:
    return ["| " + " | ".join(header) + " |", "|" + "---|" * len(header),
            *("| " + " | ".join(_cell(c) for c in row) + " |" for row in rows), ""]


def handoff(*, workspace: Path, engine: str, json_files: int, rows: int, notes: list[str],
            verified: str, edit_checked: bool, first_json: str | None, first_json_basis: str,
            command: str, open_items: str = "无") -> tuple[dict, bytes]:
    """Return the report's ``delivery`` block and the prefilled state file.

    ``notes`` are the rules a translator must follow plus anything left out of
    the export; ``verified`` is the evidence for the original-text roundtrip.
    """
    root = Path(workspace).resolve()
    gt_input, gt_output = str(root / "gt_input"), str(root / "gt_output")
    unverified = ["游戏内加载与显示"] + ([] if edit_checked else ["试编辑回写（提取时未加 --verify-edits）"])
    delivery = {"engine": engine, "gt_input": gt_input, "gt_output": gt_output,
                "json_files": json_files, "rows": rows,
                "suggested_first_json": {"file": first_json, "basis": first_json_basis},
                "translation_notes": notes, "not_verified": unverified,
                "state_file": STATE_FILE, "next": _NEXT}
    files = f"`{gt_input}`，{json_files} 个 JSON，{rows} 条；译文按同名放回 `{gt_output}`"
    if first_json:
        files += f"；建议先试 {first_json}（{first_json_basis}）"
    lines = ["# 翻译工作状态", "",
             "由提取器生成；后续阶段只更新变化的行。哈希、编码与定位信息见 reports/extraction.json 和 metadata/。", "",
             "## 交付表格", "",
             *_table(("项目", "内容"), [("引擎", engine), ("翻译文件", files),
                                       ("翻译时注意", "；".join(notes) or "无"),
                                       ("尚未验证", "；".join(unverified))]),
             "## 当前状态", "",
             *_table(("项目", "当前事实"), [
                 ("引擎与方言", engine), ("工作区", str(root)), ("已执行的命令", command),
                 ("回填路线与显示方案", "未确定"), ("用户已授权的部署/运行范围", "无"),
                 ("更新时间", datetime.now(timezone.utc).isoformat(timespec="seconds"))]),
             *_table(("阶段", "状态", "证据或剩余条件"), [
                 ("提取与原文往返", "已验证", verified),
                 ("试编辑回写", "已验证" if edit_checked else "未执行",
                  "测试编辑经 writer 回写并重新解析一致" if edit_checked else "提取时加 --verify-edits"),
                 ("译文回填与重封包", "未开始", "译文放入 gt_output 后进行"),
                 ("游戏加载与显示", "未执行", "需用户授权后在副本中试注")]),
             "状态使用未开始、进行中、受阻、已验证或未执行；“已验证”只覆盖列出的范围。", "",
             f"- 未解决的问题：{open_items}",
             "- 下一步：把 gt_input 交给 GalTransl；译文按同名放回 gt_output 后再回填、预检和重封包", ""]
    return delivery, "\n".join(lines).encode("utf-8")
