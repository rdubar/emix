"""Backend adapters: the seam between Emix's session and somebody's emulator.

Emix owns the document session; a backend owns the machine. The protocol is
small on purpose, because the roadmap's long-term plan for CP/M is to stop
using an external process at all and put the BDOS in Python over
:class:`~emix.host.DriveSet`. When that lands, it becomes another backend and
the staging machinery above it simply stops being used for CP/M.

DOS is the opposite case: nobody is writing an x86 in Python, so an external
backend there is permanent. Emix therefore has two backend *classes*, not one
uniform pool, and the protocol exists to let a disposable spike and a
permanent adapter wear the same interface.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
from typing import Protocol

from emix.apps.session import DocumentSession, DriveLayout, flat_layout, user_area_layout
from emix.errors import Code, EmixError
from emix.host import run_host_command


@dataclass(frozen=True)
class Launch:
    """What the guest should do once it is running."""

    #: Program to execute, as the guest names it, e.g. ``TE.COM``.
    program: str
    #: Guest file names passed as arguments.
    arguments: tuple[str, ...] = ()
    #: End the whole guest session when the application exits.
    #:
    #: A document session is about one document, not about operating a CP/M
    #: machine. Without this the user is returned to a bare CCP that has six
    #: built-ins, no ``HELP``, and no obvious way out — authentic, and a bad
    #: place to be dropped by a command that only said "open this file".
    exit_after: bool = True


class Backend(Protocol):
    """The nine-step lifecycle, reduced to what a prototype actually needs."""

    name: str
    layout: DriveLayout

    def check(self) -> Path:
        """Return the emulator executable, or raise if it is unusable."""

    def prepare(self, session: DocumentSession, application: Path, launch: Launch) -> None:
        """Lay out drives and arrange for ``launch`` to run automatically."""

    def run(self, session: DocumentSession, *, timeout: float | None = None) -> int:
        """Attach the terminal, run to exit, and return the exit status."""


def _write_submit(path: Path, commands: list[str]) -> None:
    """Write a CP/M ``$$$.SUB`` batch file.

    The CCP consumes this from the *end*: it reads the last 128-byte record,
    runs it, and truncates. So the records are written in reverse order, and
    each one is a length byte followed by the command text.
    """
    records = b""
    for command in reversed(commands):
        text = command.upper().encode("ascii")
        if len(text) > 127:
            raise EmixError(Code.SYNTAX, command, "command too long for a CP/M batch record")
        records += bytes([len(text)]) + text + b"\x00" * (127 - len(text))
    try:
        path.write_bytes(records)
    except OSError as error:
        raise EmixError(Code.IO_ERROR, path.name, str(error)) from error


class RunCPMBackend:
    """CP/M 2.2 via RunCPM, an external MIT-licensed Z80 emulator.

    RunCPM resolves its drive folders against the *current directory*, so a
    single installed binary serves every session: Emix runs it with the
    session root as ``cwd`` and never copies or modifies the emulator.
    """

    name = "runcpm"
    layout: DriveLayout = staticmethod(user_area_layout)

    #: Environment override, checked before ``PATH``.
    ENVIRONMENT = "EMIX_RUNCPM"

    def __init__(self, executable: Path | None = None) -> None:
        self._executable = executable

    def check(self) -> Path:
        if self._executable is not None:
            candidate = self._executable.expanduser()
            if not os.access(candidate, os.X_OK):
                raise EmixError(Code.NO_FILE, str(candidate), "not an executable RunCPM binary")
            return candidate
        override = os.environ.get(self.ENVIRONMENT)
        if override:
            candidate = Path(override).expanduser()
            if not os.access(candidate, os.X_OK):
                raise EmixError(Code.NO_FILE, override, f"{self.ENVIRONMENT} is not executable")
            return candidate
        found = shutil.which("RunCPM") or shutil.which("runcpm")
        if not found:
            raise EmixError(
                Code.NO_FILE,
                "RunCPM",
                f"not on PATH; set {self.ENVIRONMENT} to the built binary",
            )
        return Path(found)

    def prepare(self, session: DocumentSession, application: Path, launch: Launch) -> None:
        """Copy the CP/M system disk to A: and queue the launch command.

        The application drive is copied rather than linked so a misbehaving
        guest cannot damage the installed system disk. It is small, and a
        session directory that owns all its own bytes is easier to reason
        about when something crashes.
        """
        source = application.expanduser().resolve()
        if not source.is_dir():
            raise EmixError(Code.NO_DRIVE, str(application), "application drive is not a directory")
        target = session.drive_dir(session.APPLICATION_DRIVE)
        shutil.copytree(source, target, dirs_exist_ok=True)

        # The CCP appends ``.COM`` itself. Naming it is redundant for some
        # programs and fatal for others: ``A:TE.COM`` runs, ``A:MBASIC.COM``
        # answers ``A:MBASIC.COM?``. The bare name always works, and is what
        # a period user would have typed.
        program = launch.program
        if program.upper().endswith(".COM"):
            program = program[: -len(".COM")]
        command = " ".join([program, *launch.arguments]).strip()
        commands = [
            f"{session.DOCUMENT_DRIVE}:",
            f"{session.APPLICATION_DRIVE}:{command}",
        ]
        if launch.exit_after and (target / "EXIT.COM").is_file():
            # RunCPM's own terminator. Absent from a hand-built application
            # drive, in which case the user simply lands at the CCP.
            commands.append(f"{session.APPLICATION_DRIVE}:EXIT.COM")
        _write_submit(target / "$$$.SUB", commands)

    def run(self, session: DocumentSession, *, timeout: float | None = None) -> int:
        executable = self.check()
        return run_host_command([str(executable)], cwd=session.root, timeout=timeout)


class FakeBackend:
    """A backend that runs no emulator, for tests and for ``--dry-run``.

    The test suite must never depend on a third-party binary being installed,
    so the adapter protocol is exercised against this instead. ``mutate`` lets
    a test stand in for whatever the guest would have done to the workspace.
    """

    name = "fake"
    layout: DriveLayout = staticmethod(flat_layout)

    def __init__(self, mutate: object = None) -> None:
        self._mutate = mutate
        self.prepared: Launch | None = None
        self.timeout: float | None = None

    def check(self) -> Path:
        return Path("/nonexistent/fake-backend")

    def prepare(self, session: DocumentSession, application: Path, launch: Launch) -> None:
        session.drive_dir(session.APPLICATION_DRIVE)
        self.prepared = launch

    def run(self, session: DocumentSession, *, timeout: float | None = None) -> int:
        self.timeout = timeout
        if callable(self._mutate):
            self._mutate(session)
        return 0


BACKENDS: dict[str, type] = {"runcpm": RunCPMBackend, "fake": FakeBackend}
