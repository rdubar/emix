"""The host filesystem, projected as a set of bounded drives.

Every personality reaches real files through :class:`DriveSet`. Centralising
it here means the containment rule, the case-insensitive lookup and the
ambiguity check are written once and inherited by CP/M, DCL and CMS alike.

Three rules hold for every path this module hands back:

1. It is inside the drive root *after* symlinks are resolved.
2. It was matched case-insensitively, because historical systems fold case
   and Linux hosts do not.
3. If more than one host file folds to the requested name, the lookup fails
   loudly rather than silently picking whichever ``iterdir()`` yielded first.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
import fnmatch
import os
from pathlib import Path
import shutil
import subprocess

from emix.errors import Code, EmixError

#: Characters that may never appear in a leaf name typed by the user.
_FORBIDDEN = frozenset({"/", "\\", "\0"})


@dataclass(frozen=True)
class Drive:
    """One host directory exposed under a historical drive name."""

    name: str
    root: Path
    label: str = ""

    @classmethod
    def create(cls, name: str, root: Path, label: str = "") -> Drive:
        resolved = root.expanduser().resolve()
        if not resolved.is_dir():
            raise EmixError(Code.NO_DRIVE, name, f"{resolved} is not a directory")
        return cls(name.upper(), resolved, label)


class DriveSet:
    """The mounted drives plus the current default directory."""

    def __init__(self, drives: Iterable[Drive], current: str | None = None) -> None:
        ordered = list(drives)
        if not ordered:
            raise ValueError("a DriveSet needs at least one drive")
        self._drives: dict[str, Drive] = {drive.name: drive for drive in ordered}
        self._current = (current or ordered[0].name).upper()
        if self._current not in self._drives:
            raise EmixError(Code.NO_DRIVE, self._current)
        # Default directory within the current drive, always inside its root.
        self._default: Path = self._drives[self._current].root

    # -- drives ---------------------------------------------------------

    @property
    def names(self) -> list[str]:
        return sorted(self._drives)

    @property
    def current(self) -> str:
        return self._current

    def drive(self, name: str | None = None) -> Drive:
        key = (name or self._current).upper()
        try:
            return self._drives[key]
        except KeyError:
            raise EmixError(Code.NO_DRIVE, key) from None

    def mount(self, drive: Drive) -> None:
        self._drives[drive.name] = drive

    def renamed(self, names: Sequence[str]) -> DriveSet:
        """The same host directories under another system's drive names.

        One engine serving three personalities means these mounts have to be
        able to answer to ``A:``, ``DKA0:`` and filemode ``A`` in turn. What
        carries over is *position*: the second mount stays the second mount,
        and the drive you were on stays the drive you are on.

        The default directory does not carry over, deliberately. The three
        systems disagree about whether directories exist at all — CP/M 2.2 has
        none — so the only thing that means the same in all of them is which
        mount you are looking at.
        """
        existing = list(self._drives.values())
        if len(existing) > len(names):
            raise EmixError(
                Code.NO_DRIVE,
                existing[len(names)].name,
                f"that system has only {len(names)} drive names",
            )
        fresh = [
            Drive(new.upper(), drive.root, drive.label)
            for new, drive in zip(names, existing, strict=False)
        ]
        return DriveSet(fresh, current=fresh[list(self._drives).index(self._current)].name)

    def select(self, name: str) -> None:
        """Make ``name`` the current drive, resetting its default directory."""
        drive = self.drive(name)
        self._current = drive.name
        self._default = drive.root

    # -- the current default directory ----------------------------------

    @property
    def default(self) -> Path:
        """Absolute host directory that unqualified names resolve against."""
        return self._default

    def relative_default(self) -> str:
        """The default directory relative to its drive root, "" at the root."""
        relative = self._default.relative_to(self.drive().root)
        return "" if str(relative) == "." else str(relative)

    def set_default(self, name: str | None = None, *, drive: str | None = None) -> None:
        """Change directory within a drive. ``name`` may be ``..`` to ascend."""
        if drive is not None:
            self.select(drive)
        if name is None:
            return
        base = self.drive().root
        if name in {"", "."}:
            target = self._default
        elif name == "..":
            target = self._default.parent
        else:
            target = self._directory_for(None) / name
        target = self._contain(target, name or ".", base)
        if not target.is_dir():
            raise EmixError(Code.NO_FILE, name)
        self._default = target

    # -- lookups --------------------------------------------------------

    def locate(self, name: str, *, drive: str | None = None) -> Path:
        """Return an existing file, matched without regard to case."""
        path = self._match_one(name, drive=drive)
        if path is None:
            raise EmixError(Code.NO_FILE, name)
        if path.is_dir():
            raise EmixError(Code.NOT_A_FILE, name)
        return path

    def locate_any(self, name: str, *, drive: str | None = None) -> Path:
        """Like :meth:`locate` but accepts directories too."""
        path = self._match_one(name, drive=drive)
        if path is None:
            raise EmixError(Code.NO_FILE, name)
        return path

    def reserve(self, name: str, *, drive: str | None = None) -> Path:
        """Return a contained path for a file that must not yet exist."""
        self._check_leaf(name, wildcards=False)
        target = self._contain(self._directory_for(drive) / name, name, self.drive(drive).root)
        if target.exists() or self._match_one(name, drive=drive) is not None:
            raise EmixError(Code.EXISTS, name)
        return target

    def match(
        self,
        pattern: str,
        *,
        drive: str | None = None,
        files_only: bool = False,
    ) -> list[Path]:
        """Return entries matching a shell-style pattern, folded for case."""
        self._check_leaf(pattern, wildcards=True)
        folded = pattern.casefold()
        root = self.drive(drive).root
        found = []
        for entry in self._iterdir(drive):
            if not fnmatch.fnmatchcase(entry.name.casefold(), folded):
                continue
            if files_only and entry.is_dir():
                continue
            try:
                # A listing must not advertise what `locate` will refuse:
                # a symlink out of the drive is invisible, not merely unreadable.
                self._contain(entry, entry.name, root)
            except EmixError:
                continue
            found.append(entry)
        return sorted(found, key=lambda entry: entry.name.casefold())

    def exists(self, name: str, *, drive: str | None = None) -> bool:
        try:
            return self._match_one(name, drive=drive) is not None
        except EmixError:
            return False

    # -- operations -----------------------------------------------------

    def copy(self, source: Path, destination: Path) -> None:
        try:
            shutil.copy2(source, destination)
        except OSError as error:
            raise EmixError(Code.IO_ERROR, source.name, str(error)) from error

    def rename(self, source: Path, destination: Path) -> None:
        try:
            source.rename(destination)
        except OSError as error:
            raise EmixError(Code.IO_ERROR, source.name, str(error)) from error

    def unlink(self, path: Path) -> None:
        try:
            path.unlink()
        except OSError as error:
            raise EmixError(Code.IO_ERROR, path.name, str(error)) from error

    def read_text(self, path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError as error:
            raise EmixError(Code.IO_ERROR, path.name, str(error)) from error

    def free_space(self, *, drive: str | None = None) -> shutil._ntuple_diskusage:
        return shutil.disk_usage(self.drive(drive).root)

    # -- internals ------------------------------------------------------

    def _directory_for(self, drive: str | None) -> Path:
        """Where an unqualified name resolves for the given drive."""
        if drive is None or drive.upper() == self._current:
            return self._default
        return self.drive(drive).root

    def _iterdir(self, drive: str | None) -> Iterator[Path]:
        try:
            yield from self._directory_for(drive).iterdir()
        except OSError as error:
            raise EmixError(Code.IO_ERROR, str(self._directory_for(drive)), str(error)) from error

    def _match_one(self, name: str, *, drive: str | None) -> Path | None:
        """Resolve one leaf name, rejecting case-ambiguous hosts."""
        self._check_leaf(name, wildcards=False)
        folded = name.casefold()
        matches = [entry for entry in self._iterdir(drive) if entry.name.casefold() == folded]
        if not matches:
            return None
        if len(matches) > 1:
            names = ", ".join(sorted(entry.name for entry in matches))
            raise EmixError(Code.AMBIGUOUS, name, names)
        return self._contain(matches[0], name, self.drive(drive).root)

    @staticmethod
    def _check_leaf(name: str, *, wildcards: bool) -> None:
        if not name or name in {".", ".."}:
            raise EmixError(Code.BAD_NAME, name)
        if _FORBIDDEN & set(name):
            raise EmixError(Code.BAD_NAME, name)
        if not wildcards and ("*" in name or "?" in name):
            raise EmixError(Code.BAD_NAME, name)

    @staticmethod
    def _contain(path: Path, subject: str, root: Path) -> Path:
        """Reject anything that escapes ``root`` once symlinks are followed.

        ``Path.resolve`` walks symlinks, so this is what stops a link such as
        ``LINK.TXT -> ../../etc/passwd`` from being readable through a drive.
        A missing path still resolves, which is what ``reserve`` needs.
        """
        try:
            real = path.resolve()
        except OSError as error:
            raise EmixError(Code.IO_ERROR, subject, str(error)) from error
        if real != root and not real.is_relative_to(root):
            raise EmixError(Code.OUTSIDE_DRIVE, subject, str(real))
        return path


def case_collisions(entries: Iterable[Path]) -> set[str]:
    """Host names in a listing that another entry folds to.

    On a case-sensitive host, ``notes.txt`` and ``NOTES.TXT`` can coexist.
    Both fold to one historical name, so a personality that upper-cases its
    listing would print the same row twice and offer no way to tell them
    apart. Callers show these names verbatim instead.
    """
    counted = Counter(entry.name.casefold() for entry in entries)
    return {entry.name for entry in entries if counted[entry.name.casefold()] > 1}


def run_host_command(argv: list[str], *, cwd: Path, timeout: float | None = None) -> int:
    """Run a host executable directly. No shell is involved, ever.

    ``timeout`` is for guests nobody is watching. An interactive user can
    always press Ctrl-C; an unattended one cannot, and a wedged program with
    no terminal to read from will happily spin forever.
    """
    if not argv:
        return 0
    argv = [_resolve_program(argv[0]), *argv[1:]]
    try:
        completed = subprocess.run(argv, cwd=cwd, check=False, timeout=timeout)  # noqa: S603
    except FileNotFoundError:
        raise EmixError(Code.UNKNOWN_VERB, argv[0]) from None
    except subprocess.TimeoutExpired as error:
        raise EmixError(
            Code.IO_ERROR, argv[0], f"stopped after {timeout:g}s without finishing"
        ) from error
    except OSError as error:
        raise EmixError(Code.IO_ERROR, argv[0], str(error)) from error
    return completed.returncode


def on_windows() -> bool:
    """Whether the host is Windows.

    A function rather than a constant so tests can answer for it without
    patching :data:`os.name`, which would also turn every ``Path`` in the
    process into a ``WindowsPath`` that a Unix host refuses to build.
    """
    return os.name == "nt"


#: Windows runs these through its command processor even when Python is told
#: not to use a shell — the arguments are re-parsed by ``cmd.exe`` rules that
#: Python does not escape, so a file named ``a&b`` becomes a second command.
#: Emix promises no shell, so it declines rather than quietly breaking that.
_BATCH_SUFFIXES = frozenset({".bat", ".cmd"})


def _resolve_program(name: str) -> str:
    """The program to run, resolved the way the host itself would resolve it.

    Windows needs this and Unix does not. ``CreateProcess`` searches ``PATH``
    but only ever appends ``.exe``, so a program on the path is invisible to
    :mod:`subprocess` unless :func:`shutil.which`, which honours ``PATHEXT``,
    finds it first.

    Batch files are the exception, and are refused out loud. Running one is
    running a shell, whatever ``shell=False`` says.
    """
    if not on_windows():
        return name
    spelled = name
    if os.sep not in name and not (os.altsep and os.altsep in name):
        spelled = shutil.which(name) or name
    if Path(spelled).suffix.casefold() in _BATCH_SUFFIXES:
        raise EmixError(Code.NEEDS_SHELL, name, spelled)
    return spelled


def terminal_width(default: int = 80) -> int:
    try:
        return os.get_terminal_size().columns
    except OSError:
        return default
