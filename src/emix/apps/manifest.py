"""The session manifest: the one durable record of what a guest was given.

Everything else in a document session is code that can be replaced. The
manifest is *state that outlives the process*, so it is written before the
guest starts and carries an explicit :data:`SCHEMA` version. If Emix dies
mid-session, a later version must still be able to read the staging directory
it left behind and tell the user which host files are at risk.

Digests are taken at staging time for two reasons: change detection that does
not trust mtime, and a conflict check that refuses to commit over a host file
somebody else edited while the guest was running.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import os
from pathlib import Path

from emix.errors import Code, EmixError

#: Bumped whenever the on-disk shape changes. Readers refuse what they do not
#: understand rather than guessing.
SCHEMA = 1

_MANIFEST_NAME = "session.json"


def digest(path: Path) -> str:
    """SHA-256 of a file, as hex. Content, never mtime, decides change."""
    hasher = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(65536), b""):
                hasher.update(block)
    except OSError as error:
        raise EmixError(Code.IO_ERROR, path.name, str(error)) from error
    return hasher.hexdigest()


class ChangeKind(Enum):
    """What happened to one file during a session."""

    MODIFIED = "MODIFIED"
    CREATED = "CREATED"
    UNCHANGED = "UNCHANGED"
    #: A backup or scratch file the application made for its own purposes.
    #: Reported so nothing is hidden, but not committed: an editor's ``.BAK``
    #: is part of how it works, not part of what you asked it to do.
    AUXILIARY = "AUXILIARY"


@dataclass(frozen=True)
class Change:
    """One reviewable difference between the workspace and the host."""

    kind: ChangeKind
    guest: str
    #: Where this would land on the host if committed.
    host: Path
    #: The staged file inside the workspace.
    staged: Path


@dataclass(frozen=True)
class StagedFile:
    """One host file placed into the guest workspace."""

    #: Absolute host path this alias came from and returns to.
    host: str
    #: The 8.3 name the guest sees.
    guest: str
    #: Guest drive letter, e.g. ``B``.
    drive: str
    #: SHA-256 of the host file when it was staged, or ``None`` when the
    #: document did not exist yet. A new document is not a modification of
    #: nothing; it is its own case, and the commit rules differ.
    origin_digest: str | None
    size: int


@dataclass(frozen=True)
class Manifest:
    """Everything needed to finish or recover a session."""

    session_id: str
    app: str
    backend: str
    created: str
    files: list[StagedFile]
    schema: int = SCHEMA

    @classmethod
    def new(cls, session_id: str, app: str, backend: str, files: list[StagedFile]) -> Manifest:
        return cls(
            session_id=session_id,
            app=app,
            backend=backend,
            created=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            files=files,
        )

    # -- persistence ----------------------------------------------------

    def write(self, directory: Path) -> Path:
        """Write the manifest and flush it, before any guest runs."""
        path = directory / _MANIFEST_NAME
        payload = asdict(self)
        try:
            with path.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                # The manifest is the recovery record: it must survive a crash
                # that happens one instruction after the guest is launched.
                os.fsync(handle.fileno())
        except OSError as error:
            raise EmixError(Code.IO_ERROR, _MANIFEST_NAME, str(error)) from error
        return path

    @classmethod
    def read(cls, directory: Path) -> Manifest:
        path = directory / _MANIFEST_NAME
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except OSError as error:
            raise EmixError(Code.IO_ERROR, _MANIFEST_NAME, str(error)) from error
        except ValueError as error:
            raise EmixError(
                Code.IO_ERROR, _MANIFEST_NAME, f"malformed manifest: {error}"
            ) from error
        found = payload.get("schema")
        if found != SCHEMA:
            raise EmixError(
                Code.IO_ERROR,
                _MANIFEST_NAME,
                f"manifest schema {found} is not supported (this Emix reads {SCHEMA})",
            )
        payload["files"] = [StagedFile(**entry) for entry in payload.get("files", [])]
        return cls(**payload)

    # -- lookups --------------------------------------------------------

    def by_guest(self, name: str) -> StagedFile | None:
        upper = name.upper()
        for entry in self.files:
            if entry.guest.upper() == upper:
                return entry
        return None

    @property
    def guest_names(self) -> set[str]:
        return {entry.guest.upper() for entry in self.files}
