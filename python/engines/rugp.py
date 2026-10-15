# SPDX-License-Identifier: GPL-3.0-or-later
"""rUGP read-only analysis workspace; candidates are never translation input.

Inspired by huang5-png/rugp-extractor (MIT), author huang5-png & Pair AI Assistant.
The upstream literal-search pattern is not a full VM instruction grammar.
See engines/rugp.md and provenance/rugp-sources.json for scope and attribution.
Run: python -m python.engines.rugp SOURCE.rio -o NEW_ANALYSIS_DIRECTORY
"""

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import stat

from ..archives import rugp as archive
from ..common.binary import FormatError
from ..common.safety import Limits, write_new_tree


@dataclass(frozen=True)
class AnalysisLimits:
    max_input_bytes: int = 4 << 30
    max_block_bytes: int = 16 << 20
    max_header_candidates: int = 20_000
    max_decode_bytes: int = 256 << 20
    max_literal_candidates: int = 100_000
    max_output_bytes: int = 512 << 20
    chunk_bytes: int = 1 << 20

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if type(value) is not int or value < 1:
                raise FormatError(f"invalid analysis budget: {name}")
        if self.max_block_bytes > 0x1FFFFFFF:
            raise FormatError("block budget exceeds ReadEncrypted size field")


def inspect_literals(data: bytes, *, max_bytes: int = 16 << 20,
                     max_candidates: int = 100_000) -> list[dict]:
    """Keep every 60 xx 00 u8-length match, including bad/overlapping candidates.

    Offsets are in the decoded block, NOT RIO offsets. Unknown sub-ops, raw
    controls, resource-like strings, repetitions, ASCII and whitespace survive.
    No name/message roles, instruction boundaries or full-file success inferred.
    """
    if (type(max_bytes) is not int or max_bytes < 0 or len(data) > max_bytes
            or type(max_candidates) is not int or max_candidates < 0):
        raise FormatError("invalid literal analysis budget")
    results = []
    cursor, previous_end = 0, 0
    while True:
        offset = data.find(b"\x60", cursor)
        if offset < 0:
            break
        cursor = offset + 1
        if offset + 2 >= len(data) or data[offset + 2] != 0:
            continue
        if len(results) >= max_candidates:
            raise FormatError("literal candidate budget exceeded")
        item = {"offset": offset, "sub_op": data[offset + 1], "role": "unknown",
                "status": "blocked", "inside_previous_candidate": offset < previous_end}
        results.append(item)
        if offset + 4 > len(data):
            item["reason"] = "truncated length field"
            continue
        length = data[offset + 3]
        end = offset + 4 + length
        item.update({"length": length, "end": end})
        if end > len(data):
            item["reason"] = "candidate extends beyond decoded block"
            continue
        previous_end = max(previous_end, end)
        raw = data[offset + 4:end]
        item["raw_hex"] = raw.hex()
        item["has_controls"] = any(value < 32 for value in raw)
        try:
            text = raw.decode("cp932", errors="strict")
        except UnicodeDecodeError as exc:
            item["reason"] = f"invalid CP932 at payload byte {exc.start}"
            continue
        item.update({"status": "candidate-only", "text": text,
                     "display_hint": text.replace("\x03", "\n"),
                     "resource_hint": text.lower().endswith(
                         (".png", ".wav", ".ogg", ".uuc", ".rpo"))})
    return results


def _json_bytes(value, *, max_bytes: int) -> bytes:
    parts, size = [], 0
    for text in json.JSONEncoder(ensure_ascii=False, indent=2).iterencode(value):
        part = text.encode("utf-8")
        size += len(part)
        if size + 1 > max_bytes:
            raise FormatError("analysis JSON output byte budget exceeded")
        parts.append(part)
    return b"".join(parts) + b"\n"


def analyze_archive(source, output, *, key: int = archive.RIO_KEY,
                    limits: AnalysisLimits = AnalysisLimits()) -> dict:
    """Scan/decode into a NEW tree; diagnostic metadata only, no gt_input/writer.

    Input SHA-256 is streamed. All attempted plaintext sizes (including failed
    checksum attempts) consume the decode budget. Skips/failures stay in report.
    Output budget is enforced as artifacts are accumulated and before publishing.
    """
    source, output = Path(source), Path(output)
    if type(key) is not int or not 0 <= key <= 0xFFFFFFFF:
        raise FormatError("invalid key")
    if os.path.lexists(output):
        raise FileExistsError(output)
    initial = source.lstat()
    if (not stat.S_ISREG(initial.st_mode) or source.is_symlink()
            or getattr(initial, "st_file_attributes", 0) & 0x400):
        raise FormatError("RIO input must be an ordinary file")
    if initial.st_size > limits.max_input_bytes:
        raise FormatError("RIO input byte budget exceeded")
    files = []
    output_bytes = 0

    def add(name, payload):
        nonlocal output_bytes
        output_bytes += len(payload)
        if output_bytes > limits.max_output_bytes:
            raise FormatError("analysis output byte budget exceeded")
        files.append((name, payload))

    members = []
    attempted_bytes, literal_count = 0, 0
    with source.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns) != (
                initial.st_dev, initial.st_ino, initial.st_size, initial.st_mtime_ns):
            raise FormatError("RIO source changed while opening")
        source_hash = hashlib.sha256()
        remaining = initial.st_size
        while remaining:
            chunk = stream.read(min(1 << 20, remaining))
            if not chunk:
                raise FormatError("short RIO source read")
            source_hash.update(chunk)
            remaining -= len(chunk)
        headers = archive.scan_headers(stream, chunk_bytes=limits.chunk_bytes,
                                       max_input_bytes=limits.max_input_bytes,
                                       max_candidates=limits.max_header_candidates)
        for header in headers:
            item = {**asdict(header), "status": "blocked", "script_status": "unverified"}
            members.append(item)
            if header.end > initial.st_size:
                item["reason"] = "candidate extends beyond input"
                continue
            if header.plain_size > limits.max_block_bytes:
                item.update(status="skipped", reason="per-block decode budget exceeded")
                continue
            if attempted_bytes + header.plain_size > limits.max_decode_bytes:
                item.update(status="skipped", reason="cumulative decode budget exceeded")
                continue
            attempted_bytes += header.plain_size
            try:
                block = archive.read_block(stream, header, key=key,
                                           max_plain_bytes=limits.max_block_bytes)
            except FormatError as exc:
                item["reason"] = str(exc)
                continue
            # Exercise the real encoder, retaining the low three header bits.
            encoded = archive.encrypt_block(block.data, key=key, flags=header.flags,
                                             max_plain_bytes=limits.max_block_bytes)
            stream.seek(header.offset)
            if stream.read(header.stored_size) != encoded:
                raise FormatError("ReadEncrypted writer roundtrip disagrees with source")
            candidates = inspect_literals(block.data, max_bytes=limits.max_block_bytes,
                                          max_candidates=limits.max_literal_candidates - literal_count)
            literal_count += len(candidates)
            name = f"block_{header.offset:016x}"
            add(f"original/blocks/{name}.bin", encoded)
            add(f"decoded/{name}.dec", block.data)
            add(f"metadata/{name}.json", _json_bytes({
                "status": "candidate-only", "encoding": "cp932", "block_offset": header.offset,
                "complete_vm_parse": False, "candidates": candidates},
                max_bytes=limits.max_output_bytes - output_bytes))
            item.update(status="decoded", checksum_chunks=block.checksum_chunks,
                        integrity="checksummed-prefix-only" if block.checksum_chunks else "unverified-key",
                        unchecked_tail_bytes=len(block.data) % 32,
                        block_roundtrip=True, decoded_sha256=hashlib.sha256(block.data).hexdigest(),
                        candidate_count=len(candidates), decoded=f"decoded/{name}.dec",
                        metadata=f"metadata/{name}.json")
        final = os.fstat(stream.fileno())
        if (final.st_size, final.st_mtime_ns) != (initial.st_size, initial.st_mtime_ns):
            raise FormatError("RIO input changed during analysis")
    report = {
        "engine": "rugp", "profile": "readencrypted-physical-candidates-v1",
        "status": "candidate-only", "physical_scan_complete": True,
        "source_name": source.name, "source_size": initial.st_size,
        "source_sha256": source_hash.hexdigest(), "key": f"0x{key:08x}",
        "limits": asdict(limits), "header_candidates": len(headers),
        "decoded_blocks": sum(item["status"] == "decoded" for item in members),
        "blocked_blocks": sum(item["status"] == "blocked" for item in members),
        "skipped_blocks": sum(item["status"] == "skipped" for item in members),
        "decode_status": ("no-candidates" if not members else "complete" if all(
            item["status"] == "decoded" for item in members) else "partial"),
        "attempted_plain_bytes": attempted_bytes, "literal_candidates": literal_count,
        "semantic_extraction": "unverified", "script_rebuild": "unsupported",
        "archive_repack": "unsupported", "runtime_verified": False, "members": members}
    add("reports/analysis.json", _json_bytes(report, max_bytes=limits.max_output_bytes - output_bytes))
    add("README.txt", (
        "rUGP 只读分析结果；不是翻译工作区。\n"
        "decoded 为校验后解码的物理块，metadata 为 CP932 字符串候选与失败诊断。\n"
        "候选可能是资源、嵌套数据或误匹配；没有完整 VM 解析及姓名/对白语义保证。\n"
        "未生成 gt_input；请勿把候选清单直接导入翻译器。\n"
        "原文块经过实际编解码往返，但不代表剧本可回填、归档可重封或游戏可加载。\n"
        "original/blocks 仅保留选中的物理帧；回填基准仍需完整原归档与配套文件。\n"
        "32 字节完整块有校验，最后不足 32 字节没有校验，短帧不能验证密钥。\n"
        "详见 reports/analysis.json 的 blocked/skipped 条目；游戏显示未验证。\n"
    ).encode("utf-8"))
    write_new_tree(output, files, Limits(max_entries=3 * limits.max_header_candidates + 2,
                                       max_file_bytes=limits.max_output_bytes,
                                       max_total_bytes=limits.max_output_bytes))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="rUGP read-only block and literal candidate analysis")
    parser.add_argument("source", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True, help="new analysis directory")
    parser.add_argument("-k", "--key", type=lambda value: int(value, 0), default=archive.RIO_KEY)
    parser.add_argument("--max-input-mib", type=int, default=4096)
    parser.add_argument("--max-block-mib", type=int, default=16)
    parser.add_argument("--max-decode-mib", type=int, default=256)
    parser.add_argument("--max-output-mib", type=int, default=512)
    parser.add_argument("--max-header-candidates", type=int, default=20_000)
    parser.add_argument("--max-literal-candidates", type=int, default=100_000)
    parser.add_argument("--chunk-kib", type=int, default=1024)
    args = parser.parse_args()
    try:
        limits = AnalysisLimits(max_input_bytes=args.max_input_mib << 20,
                                max_block_bytes=args.max_block_mib << 20,
                                max_decode_bytes=args.max_decode_mib << 20,
                                max_output_bytes=args.max_output_mib << 20,
                                max_header_candidates=args.max_header_candidates,
                                max_literal_candidates=args.max_literal_candidates,
                                chunk_bytes=args.chunk_kib << 10)
        report = analyze_archive(args.source, args.output, key=args.key, limits=limits)
    except (FormatError, OSError) as exc:
        parser.exit(2, f"rUGP analysis failed: {exc}\n")
    print(json.dumps({k: report[k] for k in ("status", "header_candidates", "decoded_blocks",
                                            "blocked_blocks", "skipped_blocks", "literal_candidates")},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
