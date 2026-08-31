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
from dataclasses import dataclass
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


@dataclass(frozen=True)
class RollbackOutcome:
    """How much of a failed commit was successfully undone."""

    #: Host files put back as they were.
    restored: tuple[Path, ...] = ()
    #: Host files that could not be restored or removed. These are the ones a
    #: human has to deal with.
    unresolved: tuple[Path, ...] = ()
    #: Backup copies still on disk, for the unresolved targets.
    backups: tuple[Path, ...] = ()

    @property
    def complete(self) -> bool:
        return not self.unresolved


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
        #: Set when a commit failed, describing how far the undo got.
        self.rollback: RollbackOutcome | None = None

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
            staged_path = directory / guest
            try:
                shutil.copy2(resolved, staged_path)
            except OSError as error:
                raise EmixError(Code.IO_ERROR, resolved.name, str(error)) from error
            # Digest the copy, never the source a second time. Reading the
            # source again would record the digest of whatever it says *now*,
            # which is not necessarily what we hold: an edit landing between
            # the copy and the hash would make the manifest describe bytes the
            # session does not have, and the commit-time conflict check would
            # then clear and overwrite that newer file. Hashing the copy makes
            # the check compare the host against what we actually took.
            entry = StagedFile(
                host=str(resolved),
                guest=guest,
                drive=target_drive,
                origin_digest=digest(staged_path),
                size=staged_path.stat().st_size,
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
                # A reserved name that was never written is simply nothing.
                # A staged document that has gone is a deletion, and the user
                # should be told even though Emix will not act on it.
                if entry.origin_digest is not None:
                    found.append(
                        Change(
                            kind=ChangeKind.DELETED,
                            guest=entry.guest,
                            host=Path(entry.host),
                            staged=staged_path,
                        )
                    )
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
            if change.kind not in {ChangeKind.UNCHANGED, ChangeKind.AUXILIARY, ChangeKind.DELETED}
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
        """Write reviewed changes back to the host, all of them or none.

        Replacing one file is atomic; replacing a *set* of them is not, and no
        portable filesystem offers a primitive that does. So this is a small
        transaction written by hand:

        1. refuse outright if anything conflicts, before touching the host;
        2. for each target in turn, copy the file about to be overwritten into
           the session, check that copy still matches what step 1 saw, and
           only then replace it;
        3. on any failure, restore what was replaced and remove what was
           created, and report exactly how much of that succeeded.

        Step 2's re-check is what narrows — **not closes** — the window
        between the conflict check and the write. A host edit landing inside
        the microseconds between the backup and the replace is still lost, and
        no amount of hashing fixes that; only filesystem locking would, and
        that is not portable. See ``docs/APPLICATIONS.md`` for the guarantee
        this does and does not amount to.
        """
        pending = self.pending(changes)
        clashing = self.conflicts(pending)
        if clashing:
            names = ", ".join(change.host.name for change in clashing)
            raise EmixError(Code.EXISTS, names, "host files changed during the session")

        rollback = self.root / "rollback"
        rollback.mkdir(exist_ok=True)
        originals: list[tuple[Path, Path]] = []
        created: list[Path] = []
        written: list[Path] = []
        try:
            for index, change in enumerate(pending):
                entry = self.manifest.by_guest(change.guest)
                expected = entry.origin_digest if entry else None
                if change.host.exists():
                    if expected is None:
                        raise EmixError(Code.EXISTS, change.host.name, "appeared during the commit")
                    keep = rollback / f"{index:03d}-{change.host.name}"
                    shutil.copy2(change.host, keep)
                    originals.append((change.host, keep))
                    # The backup is a snapshot of the host at this instant. If
                    # it no longer matches what the conflict check saw, the
                    # file moved underneath us after preflight.
                    if digest(keep) != expected:
                        raise EmixError(Code.EXISTS, change.host.name, "changed during the commit")
                elif expected is not None:
                    raise EmixError(Code.NO_FILE, change.host.name, "disappeared during the commit")
                else:
                    created.append(change.host)
                self._replace(change.staged, change.host)
                written.append(change.host)
        except (EmixError, OSError) as error:
            self.rollback = self._roll_back(originals, created, written)
            raise self._failure(error, self.rollback) from error
        self.rollback = None
        return written

    @staticmethod
    def _failure(error: Exception, outcome: RollbackOutcome) -> EmixError:
        """Describe a failed commit truthfully, including a failed rollback."""
        if outcome.complete:
            return EmixError(
                Code.IO_ERROR,
                "commit",
                f"commit failed and was rolled back: {error}",
            )
        unresolved = ", ".join(path.name for path in outcome.unresolved)
        kept = ", ".join(str(path) for path in outcome.backups)
        return EmixError(
            Code.IO_ERROR,
            "commit",
            f"commit failed AND could not be fully undone ({error}). "
            f"These host files are in an unknown state: {unresolved}. "
            f"Their originals are kept at: {kept}",
        )

    @staticmethod
    def _roll_back(
        originals: list[tuple[Path, Path]],
        created: list[Path],
        written: list[Path],
    ) -> RollbackOutcome:
        """Undo a partial commit, and say exactly how far it got.

        Suppressing the errors here would be the worst possible silence: it is
        the moment when Emix either did or did not keep its promise about the
        user's documents, and the caller cannot tell the difference without
        being told.
        """
        done = set(written)
        restored: list[Path] = []
        unresolved: list[Path] = []
        backups: list[Path] = []
        for target, keep in originals:
            backups.append(keep)
            if target not in done:
                continue
            try:
                os.replace(keep, target)
                restored.append(target)
                backups.pop()
            except OSError:
                unresolved.append(target)
        for target in created:
            if target not in done:
                continue
            try:
                target.unlink()
            except OSError:
                unresolved.append(target)
        return RollbackOutcome(
            restored=tuple(restored),
            unresolved=tuple(unresolved),
            backups=tuple(backups),
        )

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
