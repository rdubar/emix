"""The document session: stage, run, review, commit.

A document session is the answer to a question the roadmap's native-BDOS plan
never had to ask. When Emix owns the BDOS, a guest writes straight through
:class:`~emix.host.DriveSet` and there is nothing to reconcile. When an
external emulator owns the BDOS, it writes into its own tree, and Emix has to
work out afterwards what happened and whether it is safe to keep.

So the shape here is deliberate:

* only the selected document is staged, so a guest cannot read the rest of
  the folder it happened to live in;
* the manifest is written *before* the guest starts, so a crash is
  recoverable rather than mysterious;
* content digests, not mtimes, decide what changed;
* and a commit refuses to overwrite a host file that changed underneath it.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
import fnmatch
import os
from pathlib import Path
import shutil
import tempfile
import uuid

from emix.apps.manifest import Change, ChangeKind, Manifest, StagedFile, digest
from emix.apps.names import DEFAULT_SUFFIX, to_alias
from emix.errors import Code, EmixError

#: Where a drive's files live inside the session root. Backends differ:
#: RunCPM wants ``B/0``, a flat backend wants ``B``.
DriveLayout = Callable[[Path, str], Path]

#: Files applications make for themselves. TE writes ``TE.BKP``; CP/M editors
#: conventionally leave ``.BAK``; ``$$$`` is CP/M's own scratch suffix.
DEFAULT_AUXILIARY: tuple[str, ...] = ("*.BAK", "*.BKP", "*.$$$", "*.TMP", "*.SWP")


def flat_layout(root: Path, drive: str) -> Path:
    return root / drive.upper()


def user_area_layout(root: Path, drive: str) -> Path:
    """RunCPM's layout: drive letter, then CP/M user area."""
    return root / drive.upper() / "0"


class DocumentSession:
    """One staged workspace, its manifest, and the commit that ends it."""

    #: Guest drive the selected documents appear on.
    DOCUMENT_DRIVE = "B"
    #: Guest drive the application itself appears on.
    APPLICATION_DRIVE = "A"

    def __init__(
        self,
        root: Path,
        *,
        app: str,
        backend: str,
        home: Path,
        layout: DriveLayout = flat_layout,
        alias_suffix: str = DEFAULT_SUFFIX,
        auxiliary: Sequence[str] = DEFAULT_AUXILIARY,
    ) -> None:
        self.root = root
        self.app = app
        self.backend = backend
        #: Host directory a newly created guest file returns to.
        self.home = home
        self._layout = layout
        self._alias_suffix = alias_suffix
        self._auxiliary = tuple(auxiliary)
        self._staged: list[StagedFile] = []
        self._manifest: Manifest | None = None

    @classmethod
    def create(
        cls,
        *,
        app: str,
        backend: str,
        home: Path,
        layout: DriveLayout = flat_layout,
        alias_suffix: str = DEFAULT_SUFFIX,
        auxiliary: Sequence[str] = DEFAULT_AUXILIARY,
        parent: Path | None = None,
    ) -> DocumentSession:
        """Make a fresh session directory outside any mounted drive."""
        root = Path(tempfile.mkdtemp(prefix="emix-session-", dir=parent))
        return cls(
            root,
            app=app,
            backend=backend,
            home=home,
            layout=layout,
            alias_suffix=alias_suffix,
            auxiliary=auxiliary,
        )

    # -- layout ---------------------------------------------------------

    def drive_dir(self, drive: str) -> Path:
        path = self._layout(self.root, drive)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def manifest(self) -> Manifest:
        if self._manifest is None:
            raise EmixError(Code.IO_ERROR, "session", "manifest not written yet")
        return self._manifest

    # -- staging --------------------------------------------------------

    def stage(self, documents: Iterable[Path], *, drive: str | None = None) -> list[StagedFile]:
        """Copy host documents into the workspace under 8.3 aliases."""
        target_drive = (drive or self.DOCUMENT_DRIVE).upper()
        directory = self.drive_dir(target_drive)
        staged = []
        for document in documents:
            resolved = document.expanduser().resolve()
            if not resolved.is_file():
                raise EmixError(Code.NO_FILE, document.name)
            guest = to_alias(resolved.name, self._taken(), self._alias_suffix)
            try:
                shutil.copy2(resolved, directory / guest)
            except OSError as error:
                raise EmixError(Code.IO_ERROR, resolved.name, str(error)) from error
            entry = StagedFile(
                host=str(resolved),
                guest=guest,
                drive=target_drive,
                origin_digest=digest(resolved),
                size=resolved.stat().st_size,
            )
            self._staged.append(entry)
            staged.append(entry)
        return staged

    def stage_new(self, name: str, *, drive: str | None = None) -> StagedFile:
        """Reserve a guest name for a document that does not exist yet.

        Nothing is written: the guest creates the file, and the change set
        brings it home under the host name recorded here. This is what makes
        ``TE NEWFILE.TXT`` work without Emix inventing an empty file the user
        never asked for.
        """
        target_drive = (drive or self.DOCUMENT_DRIVE).upper()
        self.drive_dir(target_drive)
        guest = to_alias(name, self._taken(), self._alias_suffix)
        entry = StagedFile(
            host=str(self.home / name),
            guest=guest,
            drive=target_drive,
            origin_digest=None,
            size=0,
        )
        self._staged.append(entry)
        return entry

    def _taken(self) -> set[str]:
        return {entry.guest.upper() for entry in self._staged}

    def write_manifest(self) -> Manifest:
        """Freeze the manifest. Must happen before the guest is launched."""
        self._manifest = Manifest.new(
            session_id=uuid.uuid4().hex[:12],
            app=self.app,
            backend=self.backend,
            files=list(self._staged),
        )
        self._manifest.write(self.root)
        return self._manifest

    # -- review ---------------------------------------------------------

    def changes(self) -> list[Change]:
        """What the guest did, as reviewable differences against the host."""
        manifest = self.manifest
        found: list[Change] = []
        seen: set[str] = set()

        for entry in manifest.files:
            staged_path = self._layout(self.root, entry.drive) / entry.guest
            seen.add(entry.guest.upper())
            if not staged_path.is_file():
                # Either the guest erased it, or a reserved name was never
                # used. Deleting host files is not something a first prototype
                # should do silently, so neither is a change.
                continue
            if entry.origin_digest is None:
                kind = ChangeKind.CREATED
            elif digest(staged_path) == entry.origin_digest:
                kind = ChangeKind.UNCHANGED
            else:
                kind = ChangeKind.MODIFIED
            found.append(
                Change(kind=kind, guest=entry.guest, host=Path(entry.host), staged=staged_path)
            )

        document_dir = self._layout(self.root, self.DOCUMENT_DRIVE)
        if document_dir.is_dir():
            for candidate in sorted(document_dir.iterdir()):
                if not candidate.is_file() or candidate.name.upper() in seen:
                    continue
                found.append(
                    Change(
                        kind=(
                            ChangeKind.AUXILIARY
                            if self.is_auxiliary(candidate.name)
                            else ChangeKind.CREATED
                        ),
                        guest=candidate.name,
                        host=self.home / candidate.name.lower(),
                        staged=candidate,
                    )
                )
        return found

    def is_auxiliary(self, name: str) -> bool:
        upper = name.upper()
        return any(fnmatch.fnmatchcase(upper, pattern.upper()) for pattern in self._auxiliary)

    @staticmethod
    def pending(changes: Sequence[Change]) -> list[Change]:
        """Only the changes a commit would actually act on.

        Auxiliary output is deliberately excluded. It is shown in the report,
        so nothing is hidden, but an editor's own backup file is not something
        the user asked to put in their documents folder.
        """
        return [
            change
            for change in changes
            if change.kind not in {ChangeKind.UNCHANGED, ChangeKind.AUXILIARY}
        ]

    def conflicts(self, changes: Sequence[Change]) -> list[Change]:
        """Changes whose host file moved underneath the session.

        Without this, a document edited in another program while the guest was
        running would be silently clobbered on commit — exactly the data loss
        the whole staging design exists to prevent.
        """
        manifest = self.manifest
        clashing = []
        for change in self.pending(changes):
            if change.kind is ChangeKind.CREATED and manifest.by_guest(change.guest) is None:
                # A file the guest invented, with no reserved name behind it.
                if change.host.exists():
                    clashing.append(change)
                continue
            entry = manifest.by_guest(change.guest)
            if entry is None:
                continue
            if entry.origin_digest is None:
                # A reserved name: the host file must still not be there.
                if change.host.exists():
                    clashing.append(change)
                continue
            if not change.host.exists() or digest(change.host) != entry.origin_digest:
                clashing.append(change)
        return clashing

    # -- commit ---------------------------------------------------------

    def commit(self, changes: Sequence[Change]) -> list[Path]:
        """Write reviewed changes back to the host, atomically.

        Raises before touching anything if any change conflicts, so a commit
        is all-or-nothing rather than half-applied.
        """
        pending = self.pending(changes)
        clashing = self.conflicts(pending)
        if clashing:
            names = ", ".join(change.host.name for change in clashing)
            raise EmixError(Code.EXISTS, names, "host files changed during the session")
        written = []
        for change in pending:
            self._replace(change.staged, change.host)
            written.append(change.host)
        return written

    @staticmethod
    def _replace(source: Path, destination: Path) -> None:
        """Atomic same-filesystem replace, so a failure leaves the original."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(
            dir=destination.parent, prefix=f".emix-{destination.name}-"
        )
        os.close(handle)
        temporary_path = Path(temporary)
        try:
            shutil.copyfile(source, temporary_path)
            shutil.copystat(source, temporary_path)
            os.replace(temporary_path, destination)
        except OSError as error:
            temporary_path.unlink(missing_ok=True)
            raise EmixError(Code.IO_ERROR, destination.name, str(error)) from error

    # -- teardown -------------------------------------------------------

    def discard(self) -> None:
        """Remove the workspace. The host is untouched unless committed."""
        shutil.rmtree(self.root, ignore_errors=True)
