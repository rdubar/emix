"""Golden sessions: a whole transcript, compared line for line.

Unit tests check that a verb does its job. These check what a *session* looks
like — the banner, the prompts, the spacing, the order things appear in — which
is most of what "feels like the real thing" actually means, and none of which
any single unit test can see.

Strict mode is what makes this possible: it is the deterministic baseline, so
a transcript records authentic behaviour and nothing Emix chose to add. The
one concession is :func:`normalise`, which blanks the clocks and versions that
cannot be the same twice.
"""

from __future__ import annotations

import io
from pathlib import Path
import re

import pytest

from emix.host import Drive, DriveSet
from emix.personalities import PERSONALITIES

GOLDEN = Path(__file__).parent / "golden"

#: Things that legitimately differ between two identical runs.
_VOLATILE = [
    (re.compile(r"\d{2}:\d{2}:\d{2}"), "HH:MM:SS"),
    (re.compile(r"\d{1,2}-[A-Za-z]{3}-\d{4}"), "DD-MMM-YYYY"),
    (re.compile(r"\d{2}/\d{2}/\d{2}"), "MM/DD/YY"),
    (re.compile(r"T=\d+\.\d+/\d+\.\d+"), "T=C/C"),
    (re.compile(r"\d{3}:\d{2}\.\d{2}"), "CPUTIME"),
    (re.compile(r"EMIX \d+\.\d+\.\d+", re.IGNORECASE), "EMIX X.Y.Z"),
    (re.compile(r"Emix \d+\.\d+\.\d+"), "Emix X.Y.Z"),
    (re.compile(r"SPACE: [\d,]+K"), "SPACE: NK"),
    # CMS QUERY DISK reports the real host volume: both the block count and
    # the percentage used vary by machine, which is how this transcript passed
    # locally and failed on CI. Anchored to that line, because VMS's [000000]
    # is a constant and must survive.
    (re.compile(r"(R/W .*?\s)\d+-\s*\d+"), r"\1NNNNNNNN- NN"),
]


def normalise(text: str, root: Path) -> str:
    text = text.replace(str(root), "/DRIVE")
    for pattern, replacement in _VOLATILE:
        text = pattern.sub(replacement, text)
    return text


@pytest.fixture
def drive_root(tmp_path):
    """A fixed, boring drive, so a listing is the same on every machine."""
    root = tmp_path / "drive"
    root.mkdir()
    (root / "NOTES.TXT").write_text("first line\nsecond line\n")
    (root / "REPORT.TXT").write_text("a report\n")
    (root / "pyproject.toml").write_text("[project]\n")
    return root


def play(key: str, root: Path, script: str) -> str:
    """Run a script through a personality and return its whole transcript."""
    drives = DriveSet([Drive.create("A", root)])
    output = io.StringIO()
    shell = PERSONALITIES[key](
        drives,
        stdin=io.StringIO(script),
        stdout=output,
        strict=True,
        hint_colour="none",
    )
    shell.run()
    return normalise(output.getvalue(), root)


SCRIPTS = {
    "cpm": "DIR\nTYPE NOTES.TXT\nSTAT\nNOSUCH.TXT\nDIR *.TXT\nEXIT\n",
    "vms": "DIRECTORY\nTYPE NOTES.TXT\nDELETE NOTES.TXT\nSHOW DEFAULT\nLOGOUT\n",
    "cms": "LISTFILE\nTYPE NOTES TXT A\nQUERY DISK\nERASE NOSUCH TXT A\nEXIT\n",
}


@pytest.mark.parametrize("key", sorted(SCRIPTS))
def test_a_whole_session_matches_its_transcript(key, drive_root, request):
    recorded = play(key, drive_root, SCRIPTS[key])
    expected = GOLDEN / f"{key}.txt"

    if request.config.getoption("--record-golden", default=False):
        expected.write_text(recorded)
        pytest.skip(f"recorded {expected.name}")

    assert expected.exists(), f"missing {expected}; run pytest --record-golden"
    assert recorded == expected.read_text()


@pytest.mark.parametrize("key", sorted(SCRIPTS))
def test_a_transcript_carries_no_emix_assistance(key, drive_root):
    """Strict mode is the baseline, so a golden session is period-only."""
    assert "Emix:" not in play(key, drive_root, SCRIPTS[key])


# -- the normaliser itself ----------------------------------------------


def test_machine_dependent_values_normalise_to_the_same_text(tmp_path):
    """A transcript that passes here and fails on CI is worse than no test.

    CMS QUERY DISK reports the real host volume: both the block count and the
    percentage used differ between machines, which is exactly how the first
    version of this suite passed locally and failed in CI.
    """
    here = "EMIXA 019A A  R/W    500 3390  4096       3 97132541- 81\n"
    elsewhere = "EMIXA 019A A  R/W    500 3390  4096       3 1204- 41\n"

    assert normalise(here, tmp_path) == normalise(elsewhere, tmp_path)


def test_a_constant_that_looks_like_a_number_is_left_alone(tmp_path):
    """VMS's [000000] is part of the directory syntax, not a measurement."""
    assert "[000000]" in normalise("Directory DKA0:[000000]\n", tmp_path)


def test_clocks_and_versions_are_normalised(tmp_path):
    rendered = normalise("EMIX 1.2.3 at 09:41:07 on 31-Aug-2026\n", tmp_path)

    assert "1.2.3" not in rendered
    assert "09:41:07" not in rendered
    assert "31-Aug-2026" not in rendered
