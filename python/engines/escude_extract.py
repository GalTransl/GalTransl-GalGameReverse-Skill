"""Escu:de Haison @code/@mess batch export; standard library, GPL-3.0-or-later.

Run from the skill root: python -m python.engines.escude_extract GAME NEW_OUTPUT
Only original script.bin/data.bin are read; PK02 translation patches are excluded.
"""
import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import stat

from python.archives.escude import read_index, read_member
from python.common.contract import dump_rows, make_manifest, validate_translation
from python.common.safety import Limits, validate_names, write_new_tree
from python.engines.escude_mdb import read_names
from python.engines.escude_mess import (
    REFERENCE, extract_pair, patch_mess, protected_tokens, read_code, read_mess,
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def extract(game: Path, output: Path) -> dict:
    """Validate the complete script archive before publishing a new output tree.

    Fixed Haison profile, not automatic discovery of all Escu:de dialects.
    Unknown members, broken pairs and duplicate flat basenames fail closed.
    """
    game, output = Path(game), Path(output)
    if os.path.lexists(output):
        raise FileExistsError(f'refusing to replace output: {output}')
    payloads, sources, inventories, members = [], [], {}, {}
    decoded_total = 0
    for archive_name in ('data.bin', 'script.bin'):
        path = game / archive_name
        info = path.lstat()
        require(stat.S_ISREG(info.st_mode) and not path.is_symlink()
                and not getattr(info, 'st_file_attributes', 0)
                & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400),
                f'not an ordinary archive file: {path}')
        with path.open('rb') as stream:
            index = read_index(stream)
            normalized = validate_names([e.name for e in index.entries])
            require(index.archive_size <= 8 << 20, 'source archive exceeds 8 MiB profile budget')
            stream.seek(0)
            packed = stream.read((8 << 20) + 1)
            require(len(packed) == index.archive_size, 'archive size changed during extraction')
            sources.append(dict(path=str(path), size=len(packed), sha256=digest(packed)))
            payloads.append(('original/archives/' + archive_name, packed))
            inventories[archive_name] = []
            selected = {}
            for entry, name in zip(index.entries, normalized):
                if archive_name == 'data.bin' and name != 'db_scripts.bin':
                    continue
                raw = read_member(stream, entry, max_stored=8 << 20,
                                  max_output=min(16 << 20, (128 << 20) - decoded_total))
                decoded_total += len(raw)
                require(decoded_total <= 128 << 20, 'cumulative decoding budget exceeded')
                selected[name] = raw
                inventories[archive_name].append(dict(
                    **asdict(entry), normalized_name=name, decoded_size=len(raw), sha256=digest(raw)))
                folder = 'data' if archive_name == 'data.bin' else 'script'
                payloads.append((f'original/{folder}/{name}', raw))
            members[archive_name] = selected
    require('db_scripts.bin' in members['data.bin'], 'missing db_scripts.bin character table')
    database = members['data.bin']['db_scripts.bin']
    names = read_names(database)
    scripts = members['script.bin']
    codes, messages = {}, {}
    for name, raw in scripts.items():
        if name.endswith('.bin') and raw.startswith(b'@code:__'):
            codes[name] = read_code(raw)
        elif name.endswith('.001') and raw.startswith(b'@mess:__'):
            messages[name] = raw
        else:
            raise ValueError(f'unclassified script member: {name}')
    for name, code in codes.items():
        partner = name[:-4] + '.001'
        require(partner in messages or code.message_count == 0, f'missing message partner: {name}')
    totals = Counter(code_files=len(codes), message_files=len(messages),
                     archive_members=len(scripts), empty_code_files=sum(c.message_count == 0 for c in codes.values()),
                     json_files=0, rows=0, messages=0, choices=0, named_rows=0,
                     original_roundtrip_pass=0, resized_roundtrip_pass=0)
    exports = []
    for name, raw in messages.items():
        code_name = name[:-4] + '.bin'
        require(code_name in codes, f'missing code partner: {name}')
        code_raw = scripts[code_name]
        records = extract_pair(code_raw, raw, names=names)
        if not records:
            continue
        rows = [dict(message=r.message, **({'name': r.name} if r.name is not None else {})) for r in records]
        locators = [dict(kind=r.kind, pool_index=r.index, code_offset=r.code_offset,
                         source_line=r.line, name_id=r.name_id, name_offset=r.name_offset) for r in records]
        paired_sources = {'original/script/' + name: raw, 'original/script/' + code_name: code_raw,
                          'original/data/db_scripts.bin': database}
        manifest = make_manifest(
            engine='escude', variant='haison-code-mess', reference=REFERENCE,
            sources=paired_sources, rows=rows, locators=locators, encoding='cp932',
            protected_tokens=[list(dict.fromkeys(protected_tokens(r.message))) for r in records],
            settings={'archive': 'script.bin', 'original_member': name, 'paired_code': code_name,
                      'message_xor': 85, 'newline': '<r>', 'speaker_policy': 'explicit-local-context'})
        checked = validate_translation(manifest, paired_sources, rows, rows)
        rebuilt = patch_mess(raw, {r.index: row['message'] for r, row in zip(records, checked)})
        require(rebuilt == raw, f'original roundtrip failed: {name}')
        changed = patch_mess(raw, {0: '検証：' + records[0].message})
        verified = extract_pair(code_raw, changed, names=names)
        require(verified[0].message == '検証：' + records[0].message
                and [asdict(r) | {'message': ''} for r in verified]
                == [asdict(r) | {'message': ''} for r in records]
                and read_mess(changed).strings[1:] == read_mess(raw).strings[1:]
                and len(changed) > len(raw), f'resized roundtrip failed: {name}')
        flat = name.rsplit('/', 1)[-1][:-4] + '.json'
        payloads.extend([('gt_input/' + flat, dump_rows(rows)), ('metadata/' + flat, json_bytes(manifest))])
        exports.append(dict(member=name, code=code_name, json='gt_input/' + flat,
                            manifest='metadata/' + flat, rows=len(records)))
        totals.update(json_files=1, rows=len(records), messages=sum(r.kind == 'message' for r in records),
                      choices=sum(r.kind == 'choice' for r in records), named_rows=sum(r.name is not None for r in records),
                      original_roundtrip_pass=1, resized_roundtrip_pass=1)
    # Re-read only the two bounded inputs; do not hash the game's multimedia archives.
    for source in sources:
        with Path(source['path']).open('rb') as stream:
            require(digest(stream.read((8 << 20) + 1)) == source['sha256'], 'source changed during extraction')
    report = dict(schema='escude-haison-extraction/2', profile=REFERENCE,
                  status='complete-for-original-script-archive', totals=dict(totals),
                  sources=sources, members=inventories, exports=exports, name_table_slots=len(names),
                  empty_code_members=[name for name, code in codes.items() if not code.message_count],
                  limitations=['Japanese original script.bin only; PK02 Chinese patch excluded.',
                               'Names are read-only local context, not full runtime state.',
                               'No repack, deployment, Chinese font/encoding or game execution validation.'])
    payloads.append(('reports/extraction.json', json_bytes(report)))
    payloads.append(('reports/names.json', json_bytes([dict(id=i, name=n) for i, n in enumerate(names)])))
    payloads.append(('reports/说明.txt', (
        f"{totals['json_files']} 个 JSON，{totals['rows']} 条（日文原版）。\n"
        '把 gt_input 导入 GalTransl，译文放入 gt_output，保留文件名、顺序和姓名。\n'
        '保留 <r>、ruby/font 等控制标签。original/metadata 是回填基准。\n'
        '全部导出文件通过原文逐字节往返与首条变长回填检查。未验证游戏运行。\n'
    ).encode('utf-8')))
    write_new_tree(output, payloads, Limits(max_file_bytes=32 << 20, max_total_bytes=256 << 20))
    (output / 'gt_output').mkdir()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('game', type=Path)
    parser.add_argument('output', type=Path, help='new, nonexistent directory; parent must exist')
    args = parser.parse_args()
    report = extract(args.game, args.output)
    print(json.dumps({'output': str(args.output), 'totals': report['totals']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
