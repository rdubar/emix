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
