from __future__ import annotations

import io
import os
from pathlib import Path
import stat
import sys
import tempfile

import pytest

from emix.host import Drive, DriveSet

#: A file that exists and that the host will agree is executable, for tests
#: that need a plausible program path and do not care which program. The
#: interpreter running the suite is the one binary guaranteed on every host.
ANY_EXECUTABLE = Path(sys.executable)


def _symlinks_work() -> bool:
    """Windows only grants symlink creation under Developer Mode or elevation."""
    if os.name != "nt":
        return True
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / "target"
        target.write_text("")
        try:
            (Path(folder) / "link").symlink_to(target)
        except (OSError, NotImplementedError):
            return False
        return True


#: Containment after symlink resolution is a real guarantee that deserves real
#: tests, but they cannot run where the host will not make a symlink.
needs_symlinks = pytest.mark.skipif(
    not _symlinks_work(), reason="symlink creation is not permitted on this host"
)


def toml_path(path: Path) -> str:
    """A path as a TOML value, correct on any host.

    A Windows path is full of backslashes, and TOML reads those as escapes
    inside a double-quoted string: ``"C:\\Users\\me"`` is not a path, it is an
    invalid ``\\U`` escape. A literal string takes the text as written.
    """
    return f"'{path}'"


#: `termios` and `tty` do not exist on Windows, so a test that reaches for them
#: is testing the POSIX probe and belongs only where that probe runs.
needs_posix_terminal = pytest.mark.skipif(os.name == "nt", reason="termios and tty are POSIX-only")


#: Writing a program that exits with a chosen status means writing a script,
#: and on Windows a script is a batch file — which Emix deliberately refuses to
#: run, because Windows would execute it through the command processor. There
#: is no third option short of shipping a compiled binary, so these tests are
#: Unix-only and the Windows behaviour is covered by `test_windows.py` instead.
needs_written_programs = pytest.mark.skipif(
    os.name == "nt", reason="a written program would be a batch file, which Emix refuses to run"
)


def write_program(folder: Path, name: str, status: int) -> Path:
    """A program that exists, runs, and exits with ``status``, on any host.

    Written rather than found: ``/usr/bin/true`` and ``/usr/bin/false`` are the
    obvious choices and neither exists on Windows.
    """
    if os.name == "nt":
        program = folder / f"{name}.cmd"
        program.write_text(f"@exit /b {status}\r\n")
        return program
    program = folder / name
    program.write_text(f"#!/bin/sh\nexit {status}\n")
    program.chmod(program.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return program


def failing_program(folder: Path) -> Path:
    """A program that exits non-zero. See :func:`write_program`."""
    return write_program(folder, "fails", 1)


def pretend_host(monkeypatch, windows: bool) -> None:
    """Answer :func:`emix.host.on_windows` for every module that asks it.

    Answered per module rather than by patching :data:`os.name`, which would
    also turn every ``Path`` into a ``WindowsPath`` a Unix host cannot build.
    """
    for module in ("config", "host", "shell", "terminal"):
        monkeypatch.setattr(f"emix.{module}.on_windows", lambda: windows, raising=False)


@pytest.fixture
def windows(monkeypatch):
    """Pretend to be Windows, without pretending to have its API."""
    pretend_host(monkeypatch, True)


@pytest.fixture
def unix(monkeypatch):
    """Pretend to be Unix, so the Unix branch is tested *on Windows too*.

    Without this, a test asserting Unix behaviour asserts whatever the host
    happens to be: it passes on the machine that wrote it and fails on the CI
    runner it exists to protect.
    """
    pretend_host(monkeypatch, False)


@pytest.fixture
def drive_root(tmp_path: Path) -> Path:
    root = tmp_path / "diskA"
    root.mkdir()
    return root


@pytest.fixture
def drives(drive_root: Path) -> DriveSet:
    return DriveSet([Drive.create("A", drive_root)])


def make_shell(personality, drives, script: str = ""):
    """Build a personality wired to string buffers, as the tests need it."""
    output = io.StringIO()
    shell = personality(drives, stdin=io.StringIO(script), stdout=output)
    return shell, output


def pytest_addoption(parser):
    parser.addoption(
        "--record-golden",
        action="store_true",
        default=False,
        help="rewrite the golden transcripts from this run",
    )


@pytest.fixture(autouse=True)
def contained_workspaces(tmp_path, monkeypatch):
    """Keep every session workspace under pytest's own temporary directory.

    Retaining a workspace is correct product behaviour whenever a commit
    fails, so the suite deliberately exercises paths that keep one. Without
    this the run would leave a directory in the system temp folder for every
    such test, which is how 1,300 of them accumulated in one afternoon.
    """
    from emix.apps.session import DocumentSession

    original = DocumentSession.create.__func__

    def create(cls, **kwargs):
        kwargs.setdefault("parent", tmp_path)
        return original(cls, **kwargs)

    monkeypatch.setattr(DocumentSession, "create", classmethod(create))
