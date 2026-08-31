from __future__ import annotations

import io
from pathlib import Path

import pytest

from emix.host import Drive, DriveSet


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
