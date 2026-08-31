"""Driving one document session from the command line."""

from __future__ import annotations

from collections.abc import Callable
import os
from pathlib import Path
import sys
from typing import TextIO

from emix.apps.backends import BACKENDS, Backend, Disposition, Launch, Result
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
    deleted = [change for change in changes if change.kind is ChangeKind.DELETED]
    if not pending and not auxiliary and not deleted:
        stream.write("  No changes.\n\n")
        return
    for change in pending:
        stream.write(f"  {change.kind.value:<9} {change.host.name}\n")
    for change in deleted:
        stream.write(
            f"  {'DELETED':<9} {change.host.name}  "
            "(the application removed it; the host file is untouched)\n"
        )
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
            outcome = adapter.run(session, timeout=float(profile.timeout) if unattended else None)
        except KeyboardInterrupt:
            outcome = Result(Disposition.INTERRUPTED, detail="interrupted")

        if not outcome.succeeded:
            # A guest that crashed, timed out or was killed may have left a
            # half-written file behind. Its output is not evidence of what the
            # user wanted, so the host is not touched and the workspace is
            # kept for them to look at.
            stream.write(f"\nThe application did not finish ({outcome.disposition.value}")
            stream.write(f": {outcome.detail})\n" if outcome.detail else ")\n")
            stream.write("Nothing has been written to the host.\n")
            keep = True
            return 130 if outcome.disposition is Disposition.INTERRUPTED else 1

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
                "Nothing was committed.\n"
            )
            keep = True
            return 1

        if not assume_yes:
            # Only guard the default prompt. A caller that supplied its own
            # confirm — a personality shell, a test — does its own input.
            if confirm is input and not sys.stdin.isatty():
                # Nobody is there to answer, and committing on silence would
                # make an unattended run the least careful path.
                stream.write("Not committed: no terminal to confirm from. Use --yes.\n")
                keep = True
                return 1
            try:
                answer = confirm("Save these changes to the host? [Y/n] ").strip().upper()
            except (EOFError, KeyboardInterrupt):
                stream.write("\nNot committed.\n")
                keep = True
                return 130
            if answer not in {"", "Y", "YES"}:
                stream.write("Discarded.\n")
                keep = True
                return 0

        try:
            written = session.commit(pending)
        except EmixError as error:
            # The workspace holds the rollback copies, so discarding it here
            # would destroy the only evidence of what happened. Keep it on
            # every commit failure, not only the ones we can undo.
            keep = True
            stream.write(f"\n{error.detail or error}\n")
            undone = session.rollback
            if undone is not None and not undone.complete:
                stream.write("These host files need a human:\n")
                for path in undone.unresolved:
                    stream.write(f"  UNRESOLVED  {path}\n")
                for path in undone.backups:
                    stream.write(f"  ORIGINAL AT {path}\n")
            return 1
        for path in written:
            stream.write(f"  saved {path}\n")
        return 0
    finally:
        if keep:
            # M2: a kept workspace is useless if the user cannot find it.
            stream.write(f"Workspace kept at: {session.root}\n")
        else:
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
