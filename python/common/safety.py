"""Conservative archive path checks and no-overwrite output to a NEW tree.

New implementation for this skill; standard library only. Use a trusted,
user-owned output parent, not a directory another process can maliciously
change during extraction. This is not a filesystem sandbox. Archives that
contain symlinks/hardlinks must be rejected by their parser before calling it.
"""

from dataclasses import dataclass
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import unicodedata

from .binary import FormatError


@dataclass(frozen=True)
class Limits:
    max_entries: int = 100_000
    max_file_bytes: int = 128 * 1024 * 1024
    max_total_bytes: int = 512 * 1024 * 1024
    max_path_chars: int = 4096


_RESERVED = re.compile(
    r"^(?:CON|PRN|AUX|NUL|CLOCK\$|CONIN\$|CONOUT\$|COM[1-9¹²³]|LPT[1-9¹²³])(?:\.|$)",
    re.IGNORECASE,
)


def logical_path(name: str, *, max_chars: int = 4096) -> str:
    """Return a relative slash-separated name; reject ambiguous Windows paths."""
    if not isinstance(name, str) or not name or len(name) > max_chars:
        raise FormatError("empty, non-string or oversized archive path")
    name = name.replace("\\", "/")
    if name.startswith("/") or any(ord(char) < 32 for char in name):
        raise FormatError("absolute path or control character in archive name")
    parts = name.split("/")
    for part in parts:
        if part in ("", ".", "..") or part[-1:] in (".", " "):
            raise FormatError(f"ambiguous path component: {part!r}")
        if any(char in part for char in ':*?"<>|') or _RESERVED.match(part):
            raise FormatError(f"unsafe Windows path component: {part!r}")
    return "/".join(parts)


def validate_names(names: list[str], limits: Limits = Limits()) -> list[str]:
    if len(names) > limits.max_entries:
        raise FormatError("archive entry count exceeds limit")
    paths = [logical_path(name, max_chars=limits.max_path_chars) for name in names]
    files: set[tuple[str, ...]] = set()
    directories: set[tuple[str, ...]] = set()
    for path in paths:
        key = tuple(unicodedata.normalize("NFC", part).casefold() for part in path.split("/"))
        if key in files or key in directories:
            raise FormatError(f"duplicate or file/directory collision: {path}")
        for end in range(1, len(key)):
            if key[:end] in files:
                raise FormatError(f"file used as directory: {path}")
            directories.add(key[:end])
        files.add(key)
    return paths


def _check_existing_ancestors(path: Path) -> None:
    # abspath normalizes '.', but unlike resolve does not hide a symlink.
    path = Path(os.path.abspath(path))
    for component in reversed((path, *path.parents)):
        try:
            info = component.lstat()
        except FileNotFoundError:
            raise FormatError(f"output parent must already exist: {component}") from None
        reparse = getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        if stat.S_ISLNK(info.st_mode) or reparse or not stat.S_ISDIR(info.st_mode):
            raise FormatError(f"output ancestor is not an ordinary directory: {component}")


def write_new_tree(destination: Path, entries: list[tuple[str, bytes]],
                   limits: Limits = Limits()) -> list[str]:
    """Validate all entries, stage them, then publish to a new directory only.

    Returned names are relative to destination. The parent must exist. Never
    point this at a game directory or a previous output. The caller must bound
    decompression BEFORE building entries; these checks cannot undo an earlier
    excessive allocation. No output file is opened in overwrite mode.
    """
    destination = Path(os.path.abspath(destination))
    logical_path(destination.name)
    _check_existing_ancestors(destination.parent)
    if os.path.lexists(destination):
        raise FileExistsError(f"refusing to replace output: {destination}")
    names = validate_names([entry[0] for entry in entries], limits)
    total = 0
    for _, payload in entries:
        if not isinstance(payload, bytes) or len(payload) > limits.max_file_bytes:
            raise FormatError("entry is not bytes or exceeds per-file budget")
        total += len(payload)
        if total > limits.max_total_bytes:
            raise FormatError("archive output exceeds total budget")
    staging = Path(tempfile.mkdtemp(prefix=".galgame-stage-", dir=destination.parent))
    reserved = False
    identity = None
    try:
        for name, (_, payload) in zip(names, entries):
            target = staging.joinpath(*name.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(payload)
        # Reserve with exclusive mkdir so POSIX rename cannot replace somebody
        # else's pre-existing empty directory. Only our empty reservation moves.
        destination.mkdir()
        reserved = True
        info = destination.lstat()
        identity = (info.st_dev, info.st_ino)
        current = destination.lstat()
        if (current.st_dev, current.st_ino) != identity or any(destination.iterdir()):
            raise FormatError("output reservation changed during staging")
        if os.name == "nt":
            # Windows rename does not replace an empty directory. In the trusted
            # parent, remove our reservation; os.rename still refuses collisions.
            destination.rmdir()
            reserved = False
            os.rename(staging, destination)
        else:
            os.replace(staging, destination)
            reserved = False
        return names
    finally:
        if staging.exists():
            shutil.rmtree(staging)
        if reserved:
            try:
                info = destination.lstat()
                if (info.st_dev, info.st_ino) == identity:
                    destination.rmdir()  # Only succeeds if still empty.
            except OSError:
                pass
