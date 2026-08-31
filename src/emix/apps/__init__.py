"""Running real historical applications over Emix's host drives.

This package owns the *document session*: the staging area a guest program
sees, the manifest that records what was staged, and the review-and-commit
step that returns changes to the host. Emulation itself belongs to a backend.
"""

from __future__ import annotations

from emix.apps.manifest import Change, ChangeKind, Manifest, StagedFile
from emix.apps.session import DocumentSession

__all__ = ["Change", "ChangeKind", "DocumentSession", "Manifest", "StagedFile"]
