"""Conservative archive path checks and no-overwrite output to a new or existing tree.

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


# Result directories of the standard output layout (SKILL.md). An existing
# output root may hold other entries (a host's scratch tmp/, notes), but
# results already present here mean the root is a previous output.
RESULT_DIRS = ("gt_input", "original", "metadata", "reports")


def _empty_directory(path: Path) -> bool:
    info = path.lstat()
    reparse = getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode) and not reparse \
        and not any(path.iterdir())


def _check_free(destination: Path, names) -> list[str]:
    """Reject top-level names that exist unless they are ordinary empty directories.

    Return the names that exist as empty directories and will be replaced.
    """
    replaced = []
    for name in names:
        target = destination / name
        if not os.path.lexists(target):
            continue
        if not _empty_directory(target):
            raise FileExistsError(f"refusing to replace existing output entry: {target}")
        replaced.append(name)
    return replaced


def validate_new_tree_destination(destination: Path) -> tuple[int, int] | None:
    """Check the output parent and target before parsing or writing resources.

    Return the identity of an existing ordinary directory, or None when the
    target is absent. An existing directory may contain unrelated entries, but
    not a non-empty result directory (RESULT_DIRS). write_new_tree still
    refuses to replace any existing entry it would publish. This check neither
    creates nor removes directories.
    """
    destination = Path(os.path.abspath(destination))
    logical_path(destination.name)
    _check_existing_ancestors(destination.parent)
    if not os.path.lexists(destination):
        return None
    _check_existing_ancestors(destination)
    _check_free(destination, RESULT_DIRS)
    info = destination.lstat()
    return info.st_dev, info.st_ino


class _BoundedWriter:
    """Binary sink that refuses to grow past an explicit byte budget."""

    def __init__(self, stream, limit: int):
        self._stream = stream
        self._limit = limit
        self.written = 0

    def write(self, data) -> int:
        size = len(data)
        if self.written + size > self._limit:
            raise FormatError("streamed output exceeds its byte budget")
        self._stream.write(data)
        self.written += size
        return size


def write_new_tree(destination: Path, entries: list[tuple[str, bytes]],
                   limits: Limits = Limits(), *, streams=()) -> list[str]:
    """Validate all entries, stage them, then publish without replacing anything.

    Returned names are relative to destination. The parent must exist; an
    existing destination must be an ordinary directory in which every
    top-level entry to publish is absent or an ordinary empty directory (see
    validate_new_tree_destination). Never point this at a game directory or a
    previous output. The caller must bound
    decompression BEFORE building entries; these checks cannot undo an earlier
    excessive allocation. No output file is opened in overwrite mode.

    ``streams`` holds ``(name, writer, max_bytes)`` for outputs too large to
    hold in memory: ``writer(sink)`` receives a write-only sink that rejects
    bytes past ``max_bytes``. Streamed files are staged and published together
    with ``entries`` and are budgeted individually, not by ``limits``.
    """
    destination = Path(os.path.abspath(destination))
    identity = validate_new_tree_destination(destination)
    existing = identity is not None
    streams = list(streams)
    names = validate_names([entry[0] for entry in entries] + [item[0] for item in streams], limits)
    tops = list(dict.fromkeys(name.split("/")[0] for name in names))
    if existing:
        _check_free(destination, tops)
    total = 0
    for _, payload in entries:
        if not isinstance(payload, bytes) or len(payload) > limits.max_file_bytes:
            raise FormatError("entry is not bytes or exceeds per-file budget")
        total += len(payload)
        if total > limits.max_total_bytes:
            raise FormatError("archive output exceeds total budget")
    for _, writer, max_bytes in streams:
        if not callable(writer) or type(max_bytes) is not int or max_bytes < 0:
            raise FormatError("streamed entry needs a writer and a nonnegative byte budget")
    staging = Path(tempfile.mkdtemp(prefix=".galgame-stage-", dir=destination.parent))
    reserved = False
    try:
        for name, (_, payload) in zip(names, entries):
            target = staging.joinpath(*name.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(payload)
        for name, (_, writer, max_bytes) in zip(names[len(entries):], streams):
            target = staging.joinpath(*name.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                writer(_BoundedWriter(stream, max_bytes))
        # Reserve absent destinations exclusively; reuse an existing directory
        # only if every published name is still free. Failure cleanup removes
        # only reservations and entries created here.
        if not existing:
            destination.mkdir()
            reserved = True
            info = destination.lstat()
            identity = (info.st_dev, info.st_ino)
        current = destination.lstat()
        if (current.st_dev, current.st_ino) != identity:
            raise FormatError("output reservation changed during staging")
        try:
            replaced = set(_check_free(destination, tops))
        except FileExistsError as error:
            raise FormatError(f"output changed during staging: {error}") from None
        # Move staged top-level entries into the target one by one rather than
        # replacing the target itself: an existing root may hold unrelated
        # entries, and Windows cannot remove a directory that is a process's
        # cwd (agent harnesses run in the output root). Windows rename refuses
        # collisions; elsewhere the free check above guards the same names.
        # A failure moves published entries back and restores emptied
        # directories, so the target is left as it was found.
        moved, removed = [], []
        try:
            for name in tops:
                target = destination / name
                if name in replaced:
                    target.rmdir()
                    removed.append(name)
                os.rename(staging / name, target)
                moved.append(name)
        except BaseException:
            for name in reversed(moved):
                try:
                    os.rename(destination / name, staging / name)
                except OSError:
                    pass
            for name in removed:
                try:
                    (destination / name).mkdir()
                except OSError:
                    pass
            raise
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
