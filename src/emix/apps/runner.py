"""Driving one document session from the command line."""

from __future__ import annotations

from collections.abc import Callable
import os
from pathlib import Path
import sys
from typing import TextIO

from emix.apps.backends import BACKENDS, Backend, Launch
from emix.apps.manifest import Change, ChangeKind
from emix.apps.profiles import Profile
from emix.apps.session import DocumentSession
from emix.errors import Code, EmixError

Confirm = Callable[[str], str]

#: Shown only with ``--stay``. The guest is a real CP/M 2.2 command processor,
#: not an Emix personality: it has six built-ins, no ``HELP``, and none of the
#: Unix names muscle memory reaches for.
GUEST_HINT = """
When the application exits you will be at a real CP/M 2.2 prompt.
It is not the Emix shell: there is no HELP, no ls, no cat.
  DIR  TYPE  ERA  REN  USER  SAVE     built in
  PIP  STAT  D                        on drive A:
  EXIT                                end the session and return here
"""


def build_backend(profile: Profile) -> Backend:
    try:
        factory = BACKENDS[profile.backend]
    except KeyError:
        known = ", ".join(sorted(BACKENDS))
        raise EmixError(
            Code.NO_DRIVE, profile.backend, f"unknown backend (known: {known})"
        ) from None
    if profile.backend == "runcpm":
        return factory(profile.executable)  # type: ignore[no-any-return]
    return factory()  # type: ignore[no-any-return]


def _geometry_warnings(profile: Profile) -> list[str]:
    """Warn when the terminal is smaller than the application assumes.

    Emix does not resize anything: a program written for 80x24 on hardware
    that could not be resized should meet a terminal the user chose. But a
    silently clipped screen looks like a bug in the emulator, so say it.
    """
    try:
        size = os.get_terminal_size()
    except OSError:
        return []
    warnings = []
    if size.columns < profile.columns or size.lines < profile.rows:
        warnings.append(
            f"This program expects {profile.columns}x{profile.rows}; "
            f"your terminal is {size.columns}x{size.lines}. Expect a clipped display."
        )
    return warnings


def _report(changes: list[Change], stream: TextIO) -> None:
    stream.write("\nDOCUMENT SESSION COMPLETE\n\n")
    pending = DocumentSession.pending(changes)
    auxiliary = [change for change in changes if change.kind is ChangeKind.AUXILIARY]
    if not pending and not auxiliary:
        stream.write("  No changes.\n\n")
        return
    for change in pending:
        stream.write(f"  {change.kind.value:<9} {change.host.name}\n")
    for change in auxiliary:
        # Named, so nothing is hidden; not committed, because it is the
        # application's own housekeeping rather than the user's document.
        stream.write(f"  {'IGNORED':<9} {change.guest}  (the application's own backup)\n")
    stream.write("\n")


def open_document(
    document: Path,
    profile: Profile,
    **kwargs: object,
) -> int:
    """Open an existing host document. See :func:`open_session`."""
    return open_session(profile, document=document, **kwargs)  # type: ignore[arg-type]


def open_session(
    profile: Profile,
    *,
    document: Path | None = None,
    new_name: str | None = None,
    home: Path | None = None,
    backend: Backend | None = None,
    assume_yes: bool = False,
    keep: bool = False,
    stay: bool = False,
    stream: TextIO = sys.stdout,
    confirm: Confirm = input,
) -> int:
    """Run ``profile``'s application over at most one document.

    Three shapes, because that is what people actually do:

    * ``document`` — open an existing host file;
    * ``new_name`` — a file that does not exist yet, created by the guest and
      brought home under that name;
    * neither — start the application with an empty workspace.
    """
    adapter = backend or build_backend(profile)
    adapter.check()

    resolved = document.expanduser().resolve() if document is not None else None
    where = home or (resolved.parent if resolved is not None else Path.cwd())
    session = DocumentSession.create(
        app=profile.name,
        backend=adapter.name,
        home=where,
        layout=adapter.layout,
        alias_suffix=profile.alias_suffix,
        auxiliary=profile.auxiliary,
    )
    try:
        if resolved is not None:
            entry = session.stage([resolved])[0]
        elif new_name is not None:
            entry = session.stage_new(new_name)
        else:
            entry = None
            # The guest still needs somewhere to write, and the launch chain
            # selects this drive before starting the application.
            session.drive_dir(DocumentSession.DOCUMENT_DRIVE)
        session.write_manifest()

        adapter.prepare(
            session,
            profile.application,
            Launch(
                program=profile.program,
                arguments=(entry.guest,) if entry is not None else (),
                exit_after=not stay,
            ),
        )
        stream.write(f"Preparing {profile.name}...\n")
        if entry is None:
            stream.write(f"Empty workspace on {DocumentSession.DOCUMENT_DRIVE}:\n")
        elif resolved is not None:
            stream.write(f"{resolved.name} is available as {entry.drive}:{entry.guest}\n")
        else:
            stream.write(f"New document {entry.drive}:{entry.guest} for {new_name}\n")
        if profile.notes:
            for note in profile.notes.strip().splitlines():
                stream.write(f"  {note}\n")
        for warning in _geometry_warnings(profile):
            stream.write(f"  {warning}\n")
        if profile.exit_hint:
            stream.write(f"\n  TO LEAVE: {profile.exit_hint}\n")
        if stay:
            stream.write(GUEST_HINT)
        stream.write("\n")
        stream.flush()

        # A human at a terminal can always interrupt; an unattended session
        # cannot, so only the latter gets a ceiling.
        unattended = not sys.stdin.isatty()
        try:
            adapter.run(session, timeout=float(profile.timeout) if unattended else None)
        except KeyboardInterrupt:
            stream.write("\nInterrupted. Nothing has been written to the host.\n")
            return 130
        except EmixError as error:
            stream.write(f"\nThe application did not finish: {error}\n")

        changes = session.changes()
        _report(changes, stream)
        pending = DocumentSession.pending(changes)
        if not pending:
            return 0

        clashing = session.conflicts(pending)
        if clashing:
            names = ", ".join(change.host.name for change in clashing)
            stream.write(
                f"Host files changed while the session was running: {names}\n"
                f"Nothing was committed. The workspace is kept at {session.root}\n"
            )
            keep = True
            return 1

        if not assume_yes:
            answer = confirm("Save these changes to the host? [Y/n] ").strip().upper()
            if answer not in {"", "Y", "YES"}:
                stream.write(f"Discarded. The workspace is kept at {session.root}\n")
                keep = True
                return 0

        written = session.commit(pending)
        for path in written:
            stream.write(f"  saved {path}\n")
        return 0
    finally:
        if not keep:
            session.discard()


def describe_profiles(profiles: dict[str, Profile], stream: TextIO = sys.stdout) -> int:
    """Report configured applications and whether their backend is usable."""
    if not profiles:
        from emix.apps.profiles import EXAMPLE, config_path

        stream.write(f"No applications configured. Create {config_path()}:\n\n{EXAMPLE}\n")
        return 1
    for name, profile in sorted(profiles.items()):
        try:
            executable = str(build_backend(profile).check())
        except EmixError as error:
            executable = f"UNAVAILABLE - {error.detail or error.code.value}"
        application = "ok" if profile.application.is_dir() else "MISSING"
        stream.write(
            f"{name}\n"
            f"  backend      {profile.backend} ({executable})\n"
            f"  program      {profile.program}\n"
            f"  application  {profile.application} [{application}]\n"
            f"  terminal     {profile.terminal}\n"
        )
    return 0
