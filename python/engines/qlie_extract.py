"""QLIE PACK 3.0/3.1 + ImoScripter FormatType=1 extraction recipe.

Run from skill root with python -m python.engines.qlie_extract --help.
Reads only explicitly named inputs. Writes one new tree via common.safety.
Archives with duplicate script names remain separate; no load-order guessing.
The key mode is chosen per archive from its footer version and index
structure (or --mode), recorded with its evidence, then proven by decoding.
"""
import argparse
from collections import Counter
from fnmatch import fnmatchcase
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys

from python.archives.qlie import MODES, external_key_required, infer_mode, member_keys, read_index, read_member
from python.archives.qlie_keys import game_key_from_pe, pe_rcdata
from python.common.contract import dump_rows, make_manifest, validate_translation
from python.common.safety import Limits, validate_names, write_new_tree, validate_new_tree_destination
from python.engines.qlie_imos import REFERENCE, scan, patch

SCHEMA = 'qlie-extract/2'
DEFAULT_KEY_FILE = 'DLL/key.fkey'
ALL_MODES = ('auto', *MODES['3.0'], *MODES['3.1'])
HASH_VERSION = {'3.0': 'hash1.3', '3.1': 'hash1.4'}
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
                game_key = game_key_from_pe(self._exe_data('3.0 keyed mode (IconKeyImage)'))
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


def extract(game: Path, output: Path, *, archives: list[str], exe: str | None = None,
            key_file: str | None = None, mode: str = 'auto', members: list[str] | None = None,
            max_total: int = 64 << 20) -> dict:
    """Keep every archive version, validate scripts and perform byte roundtrips.

    The full archive SHA-256 is streamed; only .s/.txt payloads plus the internal
    key are decrypted. The entire batch is bounded before publishing output.
    members: optional case-insensitive glob patterns (POSIX paths) limiting the
    .s scripts; .txt supporting files are always read for profile evidence.
    """
    game, output = Path(os.path.abspath(game)), Path(os.path.abspath(output))
    validate_new_tree_destination(output)
    if mode not in ALL_MODES:
        raise QlieInputError(f'unknown --mode {mode}')
    archives = validate_names(list(archives))
    exe = validate_names([exe])[0] if exe else None
    key_file = validate_names([key_file])[0] if key_file else None
    keys = KeyMaterial(game, exe, key_file)
    exe_check = _exe_original_check(game, exe)
    report = {'schema': SCHEMA, 'engine': 'qlie', 'variant': REFERENCE, 'requested_mode': mode,
              'sources': keys.sources, 'archives': [], 'members': [], 'counts': {},
              'duplicate_policy': 'retain-every-version; archive-load-priority-unverified',
              'scope': 'PACK scripts; external localization overlays are not parsed',
              'game_launch_tested': False}
    if exe_check:
        report['exe_check'] = exe_check
    patterns = [m.replace('\\', '/').casefold() for m in members or []]
    if patterns:
        report['member_filter'] = patterns
    payloads, scripts, total, configuration = [], [], 0, {}
    owners = {}
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
                text, encoding, bom = decode_script(raw)
                if encode_script(text, encoding, bom) != raw:
                    raise ValueError(f'{encoding} cannot preserve original bytes: {logical}')
                original = f'original/a{archive_number:02d}/{logical}'
                payloads.append((original, raw))
                item = {'archive': name, 'archive_number': archive_number, 'ordinal': ordinal,
                        'name': logical, 'offset': entry.offset, 'stored_size': entry.size,
                        'decoded_size': len(raw), 'stored_checksum': entry.checksum,
                        'decoded_sha256': _digest(raw), 'original': original,
                        'encoding': encoding, 'bom': bom}
                report['members'].append(item)
                selected += 1
                if logical.lower() in ('avg/projectsetting.txt', 'avg/setting.txt'):
                    configuration.setdefault(logical.lower(), []).append(text)
                if logical.lower().endswith('.s'):
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
                                       'arc_key': index.arc_key})
    overlaps = {k: v for k, v in owners.items() if len(v) > 1 and not k.endswith('.key')}
    pairs = Counter(' > '.join(v) for v in overlaps.values())
    report['overlaps'] = {'members': len(overlaps), 'archive_sets': dict(pairs),
                          'examples': sorted(overlaps)[:20],
                          'note': 'same path in several selected packs; edit the copy the game loads last'}
    for filename, setting in (('avg/projectsetting.txt', 'FormatType=1'), ('avg/setting.txt', 'ReturnCode=[n]')):
        if filename not in configuration or not all(setting in [l.strip() for l in text.splitlines()]
                                                    for text in configuration[filename]):
            raise ValueError(f'required ImoScripter profile evidence missing: {filename}: {setting}')
    planned = []
    counts = Counter()
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
            planned.append((item, raw, records, rows))
        except ValueError as exc:
            item['status'], item['error'] = 'failed', str(exc)
            counts['failed_scripts'] += 1
    stems = Counter(PurePosixPath(item['name']).stem.casefold() for item, *_ in planned)
    for item, raw, records, rows in planned:
        stem = PurePosixPath(item['name']).stem
        if stems[stem.casefold()] > 1:
            stem += f"__a{item['archive_number']:02d}_m{item['ordinal']:05d}"
        json_path = f'gt_input/{stem}.json'
        manifest_path = f'metadata/{stem}.json'
        archive = next(a for a in report['archives'] if a['path'] == item['archive'])
        policies = [('context' if record.speaker.raw.startswith('$') else 'writable')
                    if record.speaker else 'absent' for record in records]
        manifest = make_manifest(engine='qlie',
                                 variant=f"imos-format1-{item['encoding']}-{archive['mode']}-pack{archive['version']}",
                                 reference=REFERENCE, sources={item['original']: raw}, rows=rows,
                                 encoding=item['encoding'],
                                 locators=[asdict(record) for record in records], name_policies=policies,
                                 settings={'archive': item['archive'], 'member': item['name'], 'bom': item['bom'],
                                           'physical_multiline': 'allow-fewer-trailing-message-lines',
                                           'name_write': 'preserve-identity-and-write-display-alias',
                                           'container_writer': f"template-pack{archive['version']}-"
                                                               f"{HASH_VERSION[archive['version']]}"})
        validate_translation(manifest, {item['original']: raw}, rows, rows)
        payloads.extend(((json_path, dump_rows(rows)), (manifest_path, _json(manifest))))
        item.update(status='exported', json=json_path, manifest=manifest_path)
        counts['exported_scripts'] += 1
        counts['rows'] += len(rows)
        counts['named_rows'] += sum('name' in row for row in rows)
        counts['choice_rows'] += sum(r.parts[0].kind == 'choice' for r in records)
        counts['pc_rows'] += sum(any(p.kind == 'pc' for p in r.parts) for r in records)
    counts['scripts'] = len(scripts)
    counts['decoded_bytes'] = total
    report['counts'] = dict(counts)
    report['status'] = 'partial' if counts['failed_scripts'] else 'complete'
    payloads.append(('reports/extraction.json', _json(report)))
    write_new_tree(output, payloads, Limits(max_file_bytes=16 << 20, max_total_bytes=256 << 20))
    (output / 'gt_output').mkdir()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('game', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--archives', nargs='+', required=True, help='explicit game-relative PACK paths')
    parser.add_argument('--mode', choices=ALL_MODES, default='auto',
                        help='auto: per-archive from footer version and internal pack_keyfile (recorded in report)')
    parser.add_argument('--exe', help='game-relative PE path, read as data only (3.0 keyed / 3.1 RESKEY)')
    parser.add_argument('--key-file', help=f'game-relative external key; default {DEFAULT_KEY_FILE} when needed')
    parser.add_argument('--members', nargs='+', help='optional glob patterns selecting .s scripts (e.g. scenario/*/k01_*.s)')
    args = parser.parse_args()
    try:
        result = extract(args.game, args.output, archives=args.archives, exe=args.exe,
                         key_file=args.key_file, mode=args.mode, members=args.members)
    except (QlieInputError, FileNotFoundError, FileExistsError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        raise SystemExit(2)
    print(json.dumps({'status': result['status'], 'counts': result['counts'], 'output': str(args.output),
                      'archives': [{k: a[k] for k in ('path', 'pack_version', 'mode', 'mode_evidence', 'key_source')}
                                   for a in result['archives']]},
                     ensure_ascii=False, indent=2))
    raise SystemExit(result['status'] != 'complete')


if __name__ == '__main__':
    main()
