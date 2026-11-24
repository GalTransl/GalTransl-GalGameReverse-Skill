"""QLIE PACK 3.0/3.1 + ImoScripter FormatType=1 extraction recipe.

Run from skill root with python -m python.engines.qlie_extract --help.
Reads the named PACKs (default GameData/*.pack) as data and writes one new
tree via common.safety. Identical copies of a script path share one JSON;
differing copies stay separate; no load-order guessing. Scripts with
unsupported structure are listed as failed and never published.
The key mode is chosen per archive from its footer version and index
structure (or --mode), recorded with its evidence, then proven by decoding.
"""
import argparse
from collections import Counter
from copy import deepcopy
from fnmatch import fnmatchcase
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tempfile

from python.archives.qlie import MODES, external_key_required, infer_mode, member_keys, read_index, read_member
from python.archives.qlie_keys import game_key_from_pe, pe_rcdata
from python.archives.qlie_writer import lookup_version, rebuild
from python.common.contract import dump_rows, make_manifest, validate_translation
from python.common.handoff import STATE_FILE, handoff, source_language_note
from python.common.safety import Limits, validate_names, write_new_tree, validate_new_tree_destination
from python.engines.qlie_imos import REFERENCE, RUBY, scan, patch

SCHEMA = 'qlie-extract/3'
DEFAULT_ARCHIVE_DIR = 'GameData'
PROFILE_FILES = ('avg/projectsetting.txt', 'avg/setting.txt')
DEFAULT_KEY_FILE = 'DLL/key.fkey'
ALL_MODES = ('auto', *MODES['3.0'], *MODES['3.1'])
BOM = b'\xff\xfe'


class QlieInputError(ValueError):
    """Missing/unsuitable user input; reported without a traceback."""


def _json(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _ordinary(path):
    for parent in (path, *path.parents):
        info = parent.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError(f'linked/reparse input: {parent}')
    if not path.is_file():
        raise ValueError(f'not an ordinary input file: {path}')


def _small(path, limit):
    _ordinary(path)
    with path.open('rb') as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f'input exceeds size budget: {path}')
    return data


def decode_script(raw: bytes) -> tuple[str, str, bool]:
    """UTF-16LE when the member starts with FF FE, otherwise strict CP932.

    Returns (text, python encoding, bom). The caller still checks that
    encode_script(text, ...) reproduces the original bytes exactly.
    """
    if raw.startswith(BOM):
        return raw[2:].decode('utf-16-le', errors='strict'), 'utf-16-le', True
    return raw.decode('cp932', errors='strict'), 'cp932', False


def encode_script(text: str, encoding: str, bom: bool) -> bytes:
    return (BOM if bom else b'') + text.encode(encoding, errors='strict')


class KeyMaterial:
    """Lazily load external keys only when an archive's key chain needs them.

    Sources: an explicit key file, DLL/key.fkey, or EXE RCDATA (TFORM1 icon
    for 3.0 keyed; RESKEY for 3.1 method-2 pack_keyfile). Each loaded input
    is recorded with role, size and SHA-256 for repack verification.
    """
    def __init__(self, game: Path, exe: str | None, key_file: str | None):
        self.game, self.exe, self.key_file = game, exe, key_file
        self.sources, self._cache = [], {}

    def _load(self, role, name, limit):
        if (role, name) not in self._cache:
            data = _small(self.game / name, limit)
            self._cache[role, name] = data
            self.sources.append({'role': role, 'path': name, 'size': len(data), 'sha256': _digest(data)})
        return self._cache[role, name]

    def _exe_data(self, purpose):
        if self.exe is None:
            raise QlieInputError(f'{purpose} needs the game EXE; pass --exe (read as data only). '
                                 'If a "<name>.exe.org" backup exists, prefer it as the original.')
        return self._load('exe', self.exe, 64 << 20)

    def external(self, version: str, mode: str):
        """Return (key_file, game_key, evidence) for one archive's mode."""
        if mode in ('legacy', 'default-key'):
            return None, None, 'no external key'
        if mode in ('key-file', 'keyed', 'pack-key'):
            key, evidence = self._external_file(version, mode)
            game_key = None
            if mode == 'keyed':
                data = self._exe_data('3.0 keyed mode (IconKeyImage)')
                try:
                    game_key = game_key_from_pe(data)
                except ValueError as exc:
                    raise QlieInputError(
                        f'cannot read the IconKeyImage statically from {self.exe} ({len(data)} bytes): {exc}. '
                        'The file may be a launcher/stub; the real game PE can carry another name or '
                        'extension in the game folder (check other MZ files there) and pass it with --exe') from None
                evidence += f'; IconKeyImage from {self.exe}'
            return key, game_key, evidence
        raise QlieInputError(f'unknown QLIE mode {mode}')

    def _external_file(self, version, mode):
        name = self.key_file or DEFAULT_KEY_FILE
        if (self.game / name).is_file():
            return self._load('key-file', name, 1 << 20), f'key file {name}'
        if self.key_file is not None:
            raise QlieInputError(f'key file not found: {self.key_file}')
        if version == '3.1' and self.exe is not None:
            data = self._exe_data('3.1 RESKEY')
            try:
                key = pe_rcdata(data, 'RESKEY')
            except ValueError as exc:
                raise QlieInputError(f'{DEFAULT_KEY_FILE} is absent and RESKEY cannot be read '
                                     f'statically from {self.exe}: {exc}') from None
            self.sources.append({'role': 'exe-reskey', 'path': self.exe, 'size': len(key), 'sha256': _digest(key)})
            return key, f'EXE RCDATA RESKEY from {self.exe}'
        hint = ('pass --key-file PATH, or --exe to read RCDATA RESKEY' if version == '3.1'
                else 'pass --key-file PATH, or --mode legacy if the archive has no key chain')
        raise QlieInputError(f'FilePackVer{version} {mode} mode needs an external key file but '
                             f'{DEFAULT_KEY_FILE} was not found; {hint}')


def _exe_original_check(game: Path, exe: str | None) -> dict | None:
    """Record whether a patched EXE has an '.org' original with equal RCDATA."""
    if exe is None:
        return None
    path = game / exe
    result = {'exe': exe}
    if exe.lower().endswith('.org'):
        result['choice'] = 'original-backup-selected'
        return result
    org = Path(str(path) + '.org')
    if not org.is_file():
        result['choice'] = 'no-org-backup'
        return result
    current, original = _small(path, 64 << 20), _small(org, 64 << 20)
    result.update(org=exe + '.org', current_sha256=_digest(current), org_sha256=_digest(original))
    if current == original:
        result['choice'] = 'identical'
        return result
    differing = (sum(a != b for a, b in zip(current, original)) if len(current) == len(original)
                 else 'size differs')
    raise QlieInputError(f'{exe} differs from {exe}.org (differing bytes: {differing}); the .org backup '
                         f'is normally the unmodified original: pass --exe "{exe}.org" explicitly')


def _natural(name: str) -> list:
    return [int(part) if part.isdigit() else part.casefold() for part in re.split(r'(\d+)', name)]


def default_archives(game: Path) -> list[str]:
    """Every GameData/*.pack in natural order (data2 before data10).

    The order only fixes report/manifest numbering; it is not a claim about
    which pack the engine loads last.
    """
    folder = Path(game) / DEFAULT_ARCHIVE_DIR
    if not folder.is_dir():
        raise QlieInputError(f'no --archives given and {DEFAULT_ARCHIVE_DIR}/ was not found under the game '
                             'folder; pass the PACK paths explicitly')
    names = sorted((p.name for p in folder.iterdir() if p.suffix.lower() == '.pack' and p.is_file()), key=_natural)
    if not names:
        raise QlieInputError(f'no --archives given and {DEFAULT_ARCHIVE_DIR}/*.pack is empty')
    return [f'{DEFAULT_ARCHIVE_DIR}/{name}' for name in names]


def _failure(item: dict, exc: Exception) -> str:
    reason = getattr(exc, 'reason', None) or 'roundtrip/structure check failed'
    item.update(status='failed', error=str(exc), error_reason=reason)
    if getattr(exc, 'line', None) is not None:
        item['error_line'] = exc.line
    return reason


def _edit_check(game: Path, archive: str, keys: tuple, item: dict, raw: bytes, text: str, rows: list) -> dict:
    """Write one edited row (and a writable name) through patch -> PACK writer,
    reopen the rebuilt pack and re-parse; every other member must keep its bytes.
    The rebuilt pack goes to an anonymous temporary file and is not published."""
    mode, external, game_key = keys
    changed = deepcopy(rows)
    changed[0]['message'] += ' EditCheck'
    named = next((row for row, record in zip(changed, scan(text))
                  if record.speaker and not record.speaker.raw.startswith('$')), None)
    if named is not None:
        named['name'] = (named['name'] or 'N') + 'EditCheck'
    new = encode_script(patch(text, changed), item['encoding'], item['bom'])
    with (game / archive).open('rb') as source, tempfile.TemporaryFile() as destination:
        index = read_index(source)
        entry = next(e for e in index.entries if e.name.replace('\\', '/') == item['name'])
        rebuild(source, destination, {entry.name: new}, mode=mode, key_file=external, game_key=game_key)
        rebuilt = read_index(destination)
        chain = member_keys(destination, rebuilt, mode=mode, key_file=external, game_key=game_key)
        if [e.name for e in rebuilt.entries] != [e.name for e in index.entries]:
            raise ValueError('edit check: rebuilt PACK index order/names changed')
        for ordinal, (before, after) in enumerate(zip(index.entries, rebuilt.entries)):
            if before.name == entry.name:
                data = read_member(destination, rebuilt, after, mode=mode, key_file=chain[ordinal],
                                   game_key=game_key, max_stored=8 << 20, max_output=8 << 20)
                decoded, _, _ = decode_script(data)
                if data != new or [r.row() for r in scan(decoded)] != changed:
                    raise ValueError('edit check: re-parsed rebuilt script differs from the edited rows')
                continue
            source.seek(before.offset)
            destination.seek(after.offset)
            if source.read(before.size) != destination.read(after.size):
                raise ValueError(f'edit check: untouched member changed: {before.name}')
        destination.seek(0)
        digest = hashlib.file_digest(destination, 'sha256').hexdigest()
    return {'json': item['json'], 'archive': archive, 'member': item['name'],
            'edited_rows': 1 + (named is not None and named is not changed[0]),
            'name_alias_written': named is not None, 'script_size_delta': len(new) - len(raw),
            'reparsed': 'identical', 'other_members': 'stored bytes identical',
            'rebuilt_sha256': digest, 'game_launch_tested': False}


def _notes(report, encodings, failed, differing, shared, warning):
    notes = ['正文里的 [rb,底字,注音] 是注音：可保留、改写或删除整组，保留时两段都不能为空，也不能含逗号或方括号；'
             '[w,数字]、[spd]、[spd,数字] 须原样按顺序保留；不得新增其他方括号标签',
             '同一句的多行正文以换行分隔，译文行数可以减少但不能增加；姓名不得含 ＠、逗号和 【】；'
             '选项、pc 诗句和存档标题不得含半角逗号、换行或方括号']
    if 'cp932' in encodings:
        notes.append('CP932 剧本不能直接写入中文，回填时走 JIS 替换公共流程' +
                     ('；UTF-16LE 剧本可直接写中文' if 'utf-16-le' in encodings else ''))
    elif encodings:
        notes.append('剧本为 UTF-16LE，可直接写中文')
    if failed:
        notes.append(f'{failed} 个脚本含未支持的结构未导出（原因与行号见 reports/extraction.json 的 failed），'
                     '回封时按原样保留，不能为它们提供译文')
    if shared:
        notes.append(f'{shared} 个剧本在多个包中内容相同，只导出一个 JSON，回封时写入全部副本')
    if differing:
        notes.append(f'{differing} 个剧本在多个包中内容不同，各自导出为带 __aNN_mNNNNN 后缀的 JSON；'
                     '游戏实际加载哪一份未确认，先在游戏中核对再翻译')
    if warning:
        notes.insert(0, warning)
    return notes


def extract(game: Path, output: Path, *, archives: list[str] | None = None, exe: str | None = None,
            key_file: str | None = None, mode: str = 'auto', members: list[str] | None = None,
            max_total: int = 64 << 20, verify_edits: bool = False) -> dict:
    """Validate scripts, perform byte roundtrips and publish a flat workspace.

    archives defaults to every GameData/*.pack. The full archive SHA-256 is
    streamed; only .s/.txt payloads plus the internal key are decrypted. A
    script with unsupported structure is listed as failed (no JSON) and later
    copied verbatim; copies with identical bytes under one path share a JSON.
    members: optional case-insensitive glob patterns (POSIX paths) limiting the
    .s scripts; .txt supporting files are always read for profile evidence.
    """
    game, output = Path(os.path.abspath(game)), Path(os.path.abspath(output))
    validate_new_tree_destination(output)
    if mode not in ALL_MODES:
        raise QlieInputError(f'unknown --mode {mode}')
    selection = 'explicit'
    if not archives:
        archives, selection = default_archives(game), f'default {DEFAULT_ARCHIVE_DIR}/*.pack (natural order)'
    archives = validate_names(list(archives))
    exe = validate_names([exe])[0] if exe else None
    key_file = validate_names([key_file])[0] if key_file else None
    keys = KeyMaterial(game, exe, key_file)
    exe_check = _exe_original_check(game, exe)
    report = {'schema': SCHEMA, 'engine': 'qlie', 'variant': REFERENCE, 'requested_mode': mode,
              'archive_selection': selection, 'sources': keys.sources, 'archives': [], 'members': [],
              'counts': {},
              'duplicate_policy': 'identical copies of one path share a JSON; differing copies stay separate; '
                                  'archive-load-priority-unverified',
              'scope': 'PACK scripts; external localization overlays are not parsed',
              'game_launch_tested': False}
    if exe_check:
        report['exe_check'] = exe_check
    patterns = [m.replace('\\', '/').casefold() for m in members or []]
    if patterns:
        report['member_filter'] = patterns
    payloads, scripts, total, configuration = [], [], 0, {}
    owners, archive_keys = {}, {}
    counts, failures = Counter(), Counter()
    for archive_number, name in enumerate(archives):
        path = game / name
        _ordinary(path)
        with path.open('rb') as stream:
            index = read_index(stream)
            if mode == 'auto':
                chosen, evidence = infer_mode(index)
            elif mode in MODES[index.version]:
                chosen, evidence = mode, 'explicit --mode'
            else:
                raise QlieInputError(f'{name} is FilePackVer{index.version}; --mode {mode} applies to the '
                                     f'other version (valid: {", ".join(MODES[index.version])} or auto)')
            needs_external = external_key_required(index, chosen)
            external, game_key, key_evidence = keys.external(index.version, chosen) if needs_external \
                else (None, None, 'no external key required')
            archive_keys[name] = (chosen, external, game_key)
            chain = member_keys(stream, index, mode=chosen, key_file=external, game_key=game_key)
            names = validate_names([e.name for e in index.entries])
            selected = 0
            for ordinal, (entry, logical) in enumerate(zip(index.entries, names)):
                owners.setdefault(logical.casefold(), []).append(name)
                suffix = PurePosixPath(logical).suffix.lower()
                if suffix not in ('.s', '.txt'):
                    continue
                if suffix == '.s' and patterns and not any(fnmatchcase(logical.casefold(), p) for p in patterns):
                    continue
                if total + entry.unpacked_size > max_total:
                    raise ValueError('QLIE total decoded budget exceeded')
                raw = read_member(stream, index, entry, mode=chosen, key_file=chain[ordinal],
                                  game_key=game_key, max_stored=8 << 20, max_output=8 << 20)
                total += len(raw)
                original = f'original/a{archive_number:02d}/{logical}'
                payloads.append((original, raw))
                item = {'archive': name, 'archive_number': archive_number, 'ordinal': ordinal,
                        'name': logical, 'offset': entry.offset, 'stored_size': entry.size,
                        'decoded_size': len(raw), 'stored_checksum': entry.checksum,
                        'decoded_sha256': _digest(raw), 'original': original}
                report['members'].append(item)
                selected += 1
                try:
                    text, encoding, bom = decode_script(raw)
                    if encode_script(text, encoding, bom) != raw:
                        raise ValueError(f'{encoding} cannot preserve original bytes')
                except (UnicodeError, ValueError) as exc:
                    if logical.lower() in PROFILE_FILES:
                        raise ValueError(f'{name}: {logical}: {exc}') from None
                    failures[_failure(item, ValueError(f'script decoding: {exc}'))] += 1
                    item['error_reason'] = 'script decoding failed'
                    continue
                item.update(encoding=encoding, bom=bom)
                if logical.lower() in PROFILE_FILES:
                    configuration.setdefault(logical.lower(), []).append(text)
                if suffix == '.s':
                    scripts.append((item, raw, text))
                else:
                    item['status'] = 'supporting-text'
            stream.seek(0)
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            report['archives'].append({'path': name, 'size': index.file_size, 'sha256': digest,
                                       'pack_version': f'FilePackVer{index.version}', 'version': index.version,
                                       'mode': chosen, 'mode_evidence': evidence, 'key_source': key_evidence,
                                       'entries': len(index.entries), 'selected': selected,
                                       'index_offset': index.index_offset, 'index_end': index.index_end,
                                       'arc_key': index.arc_key,
                                       'hash_version': lookup_version(stream, index)})
    overlaps = {k: v for k, v in owners.items() if len(v) > 1 and not k.endswith('.key')}
    pairs = Counter(' > '.join(v) for v in overlaps.values())
    report['overlaps'] = {'members': len(overlaps), 'archive_sets': dict(pairs),
                          'examples': sorted(overlaps)[:20],
                          'note': 'same path in several selected packs, listed in archive order; which copy '
                                  'the game loads is not established here'}
    for filename, setting in (('avg/projectsetting.txt', 'FormatType=1'), ('avg/setting.txt', 'ReturnCode=[n]')):
        if filename not in configuration or not all(setting in [l.strip() for l in text.splitlines()]
                                                    for text in configuration[filename]):
            raise ValueError(f'required ImoScripter profile evidence missing: {filename}: {setting}')
    planned = []
    for item, raw, text in scripts:
        try:
            records = scan(text)
            rows = [record.row() for record in records]
            rebuilt = encode_script(patch(text, rows), item['encoding'], item['bom'])
            if rebuilt != raw:
                raise ValueError('original text roundtrip is not byte-identical')
            item['original_roundtrip'] = 'byte-identical'
            item['rows'] = len(rows)
            if not rows:
                item['status'] = 'empty'
                counts['empty_scripts'] += 1
                continue
            planned.append((item, raw, text, records, rows))
        except ValueError as exc:
            failures[_failure(item, exc)] += 1
    # One JSON per (path, decoded bytes); differing copies keep separate JSONs.
    groups = {}
    for entry in planned:
        groups.setdefault((entry[0]['name'].casefold(), entry[0]['decoded_sha256']), []).append(entry)
    stems = Counter(PurePosixPath(name).stem for name, _ in groups)
    first_json, encodings, texts = None, set(), []
    for group in groups.values():
        item, raw, text, records, rows = group[0]
        stem = PurePosixPath(item['name']).stem
        if stems[stem.casefold()] > 1:
            stem += f"__a{item['archive_number']:02d}_m{item['ordinal']:05d}"
        json_path = f'gt_input/{stem}.json'
        manifest_path = f'metadata/{stem}.json'
        archive = next(a for a in report['archives'] if a['path'] == item['archive'])
        policies = [('context' if record.speaker.raw.startswith('$') else 'writable')
                    if record.speaker else 'absent' for record in records]
        settings = {'archive': item['archive'], 'member': item['name'], 'bom': item['bom'],
                    'physical_multiline': 'allow-fewer-trailing-message-lines',
                    'name_write': 'preserve-identity-and-write-display-alias',
                    'container_writer': f"template-pack{archive['version']}-{archive['hash_version'].lower()}"}
        if len(group) > 1:
            settings['copies'] = [{'archive': g[0]['archive'], 'member': g[0]['name'], 'original': g[0]['original']}
                                  for g in group]
        manifest = make_manifest(engine='qlie',
                                 variant=f"imos-format1-{item['encoding']}-{archive['mode']}-pack{archive['version']}",
                                 reference=REFERENCE, sources={item['original']: raw}, rows=rows,
                                 encoding=item['encoding'],
                                 locators=[asdict(record) for record in records], name_policies=policies,
                                 settings=settings)
        validate_translation(manifest, {item['original']: raw}, rows, rows)
        payloads.extend(((json_path, dump_rows(rows)), (manifest_path, _json(manifest))))
        for copy, *_ in group:
            copy.update(status='exported', json=json_path, manifest=manifest_path)
            if len(group) > 1:
                copy['shared_json_copies'] = len(group)
        counts['exported_scripts'] += len(group)
        counts['json_files'] += 1
        counts['shared_json'] += len(group) > 1
        counts['rows'] += len(rows)
        counts['named_rows'] += sum('name' in row for row in rows)
        counts['choice_rows'] += sum(r.parts[0].kind == 'choice' for r in records)
        counts['pc_rows'] += sum(any(p.kind == 'pc' for p in r.parts) for r in records)
        counts['ruby_rows'] += sum(bool(RUBY.search(row['message'])) for row in rows)
        encodings.add(item['encoding'])
        texts.extend(row['message'] for row in rows)
        parts = PurePosixPath(item['name'].casefold()).parts
        rank = (0 if len(parts) > 2 else 1, _natural(item['name']))
        if 'scenario' in parts[:-1] and (first_json is None or rank < first_json[0]):
            first_json = (rank, (item, raw, text, rows))
    # Same path, different bytes: list every copy in archive order.
    by_name = {}
    for item, _, _ in scripts:
        by_name.setdefault(item['name'].casefold(), []).append(item)
    differing = []
    for copies in by_name.values():
        if len({c['decoded_sha256'] for c in copies}) > 1:
            differing.append({'name': copies[0]['name'], 'archive_order': [c['archive'] for c in copies],
                              'copies': [{'archive': c['archive'], 'status': c['status'],
                                          'sha256': c['decoded_sha256'], **({'json': c['json']} if 'json' in c else {})}
                                         for c in copies]})
    report['differing_copies'] = differing
    counts['differing_copy_scripts'] = len(differing)
    failed = [{'archive': i['archive'], 'name': i['name'], 'reason': i['error_reason'],
               **({'line': i['error_line']} if 'error_line' in i else {}), 'error': i['error']}
              for i in report['members'] if i.get('status') == 'failed']
    counts['failed_scripts'] = len(failed)
    counts['scripts'] = len(scripts)
    counts['decoded_bytes'] = total
    report['counts'] = {k: v for k, v in counts.items() if v or k in ('failed_scripts', 'exported_scripts')}
    report['failed'] = failed
    report['failure_reasons'] = dict(failures.most_common())
    report['status'] = ('complete' if not failed else 'partial' if counts['exported_scripts'] else 'failed')
    if verify_edits:
        candidates = ([first_json[1]] if first_json else []) + [g[0][:3] + (g[0][4],) for g in groups.values()]
        item, raw, text, rows = candidates[0] if candidates else (None,) * 4
        if item is None:
            raise QlieInputError('--verify-edits needs at least one exported script')
        report['edit_check'] = _edit_check(game, item['archive'], archive_keys[item['archive']],
                                           item, raw, text, rows)
    warning = source_language_note(texts)
    if warning:
        report['warnings'] = [warning]
    versions = '/'.join(sorted({a['version'] for a in report['archives']}))
    chosen_json = first_json[1][0]['json'] if first_json else next(
        (i['json'] for i in report['members'] if i.get('json')), None)
    report['delivery'], state = handoff(
        workspace=output, engine=f'QLIE（PACK {versions} + ImoScripter FormatType=1 剧本）',
        json_files=counts['json_files'], rows=counts['rows'],
        notes=_notes(report, encodings, len(failed), len(differing), counts['shared_json'], warning),
        verified='每个导出剧本经 parser/writer 原文回写后与原字节一致',
        edit_checked='edit_check' in report, first_json=chosen_json and PurePosixPath(chosen_json).name,
        first_json_basis=('scenario 下优先子目录、按文件名自然排序的第一个剧本，未确认是否开场' if first_json
                          else '按包与索引顺序的第一个导出剧本，未确认是否开场'),
        command='qlie_extract --verify-edits' if verify_edits else 'qlie_extract',
        open_items=(f'{len(failed)} 个脚本未导出，见 reports/extraction.json 的 failed' if failed else '无'))
    payloads.append(('reports/extraction.json', _json(report)))
    payloads.append((STATE_FILE, state))
    write_new_tree(output, payloads, Limits(max_file_bytes=16 << 20, max_total_bytes=256 << 20))
    (output / 'gt_output').mkdir()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('game', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--archives', nargs='+',
                        help=f'game-relative PACK paths; default: every {DEFAULT_ARCHIVE_DIR}/*.pack '
                             '(media packs are only indexed)')
    parser.add_argument('--mode', choices=ALL_MODES, default='auto',
                        help='auto: per-archive from footer version and internal pack_keyfile (recorded in report)')
    parser.add_argument('--exe', help='game-relative PE path, read as data only (3.0 keyed / 3.1 RESKEY)')
    parser.add_argument('--key-file', help=f'game-relative external key; default {DEFAULT_KEY_FILE} when needed')
    parser.add_argument('--members', nargs='+', help='optional glob patterns selecting .s scripts (e.g. scenario/*/k01_*.s)')
    parser.add_argument('--verify-edits', action='store_true',
                        help='also write one edited row through the PACK writer and re-parse the rebuilt pack')
    args = parser.parse_args()
    try:
        result = extract(args.game, args.output, archives=args.archives, exe=args.exe,
                         key_file=args.key_file, mode=args.mode, members=args.members,
                         verify_edits=args.verify_edits)
    except (ValueError, OSError, UnicodeError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        raise SystemExit(2)
    for warning in result.get('warnings', []):
        print(f'warning: {warning}', file=sys.stderr)
    print(json.dumps({'status': result['status'], 'counts': result['counts'],
                      'failure_reasons': result['failure_reasons'], 'output': str(args.output),
                      'archives': [{k: a[k] for k in ('path', 'pack_version', 'mode', 'mode_evidence', 'key_source')}
                                   for a in result['archives']],
                      **({'edit_check': result['edit_check']} if 'edit_check' in result else {}),
                      'delivery': result['delivery']},
                     ensure_ascii=False, indent=2))
    # 0 complete, 1 partial (failed scripts listed, others exported), 2 nothing usable.
    raise SystemExit({'complete': 0, 'partial': 1}.get(result['status'], 2))


if __name__ == '__main__':
    main()
