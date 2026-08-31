"""Exit statuses, checked at the process boundary.

A unit test that `open_session()` returns 1 does not prove that `emix` exits
1: the status has to survive `run_app()`, `dispatch()`, `execute()` and the
CLI's aggregation. The implementation review found exactly that gap, so these
run the real executable and read the real status.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


def emix(*arguments: str, apps: Path | None = None, cwd: Path) -> subprocess.CompletedProcess[str]:
    environment = {
        **os.environ,
        "PYTHONPATH": str(ROOT / "src"),
        "NO_COLOR": "1",
        "EMIX_CONFIG": str(cwd / "no-such-config.toml"),
        # A real process is outside the reach of the conftest fixture, and the
        # failing-application test deliberately leaves its workspace behind.
        "TMPDIR": str(cwd),
    }
    if apps is not None:
        environment["EMIX_APPS"] = str(apps)
    return subprocess.run(  # noqa: S603 - fixed argv, no shell, test-local
        [sys.executable, "-m", "emix", *arguments],
        capture_output=True,
        text=True,
        cwd=cwd,
        env=environment,
    )


@pytest.fixture
def drive(tmp_path):
    (tmp_path / "NOTES.TXT").write_text("hello\n")
    return tmp_path


def test_a_command_that_works_exits_zero(drive):
    assert emix("cpm", "--mount", str(drive), "-c", "DIR", cwd=drive).returncode == 0


def test_an_unknown_verb_exits_non_zero(drive):
    assert emix("vms", "--mount", str(drive), "-c", "NOSUCH", cwd=drive).returncode != 0


def test_a_missing_file_exits_non_zero(drive):
    assert emix("cpm", "--mount", str(drive), "-c", "TYPE NOPE.TXT", cwd=drive).returncode != 0


def test_a_failing_host_command_exits_non_zero(drive):
    """I3: host fallthrough discarded the status it was handed."""
    assert emix("cpm", "--mount", str(drive), "-c", "false", cwd=drive).returncode != 0


def test_a_successful_host_command_exits_zero(drive):
    assert emix("cpm", "--mount", str(drive), "-c", "true", cwd=drive).returncode == 0


def test_a_failing_application_exits_non_zero(drive, tmp_path):
    """I3: the inner session reported failure; the process did not."""
    apps = tmp_path / "apps.toml"
    apps.write_text(
        "[app.failing]\n"
        'backend = "runcpm"\n'
        'program = "X.COM"\n'
        f'application = "{drive}"\n'
        'executable = "/usr/bin/false"\n'
        'command = "FAIL"\n'
    )
    result = emix("cpm", "--mount", str(drive), "-c", "FAIL", apps=apps, cwd=drive)

    assert result.returncode != 0, result.stdout


def test_several_commands_fail_if_any_fails(drive):
    result = emix("cpm", "--mount", str(drive), "-c", "DIR", "-c", "NOSUCH", cwd=drive)

    assert result.returncode != 0


def test_malformed_configuration_exits_non_zero_without_a_traceback(drive, tmp_path):
    apps = tmp_path / "apps.toml"
    apps.write_text('[app]\nbad = "not a table"\n')

    result = emix("apps", apps=apps, cwd=drive)

    assert result.returncode != 0
    assert "Traceback" not in result.stderr


def test_save_prints_the_period_answer_and_nothing_else_in_strict_mode(drive):
    """I4: Emix prose must never appear on the native output path."""
    result = emix("cpm", "--mount", str(drive), "--strict", "-c", "SAVE 1 X.COM", cwd=drive)

    assert result.stdout.strip() == "SAVE?"


def test_save_explains_itself_as_marked_assistance_when_assisted(drive):
    result = emix("cpm", "--mount", str(drive), "--no-strict", "-c", "SAVE 1 X.COM", cwd=drive)

    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert lines[0] == "SAVE?"
    assert all(line.startswith("Emix:") for line in lines[1:]), lines


# -- the explicit host wrappers, per personality -------------------------
#
# These are the supported way to reach the host in each vocabulary, and each
# one dropped the status it was handed. A boolean that meant "stop the shell"
# had no room to also mean "this failed", which is why Outcome exists.


@pytest.mark.parametrize(
    "personality,command",
    [
        ("cpm", "UNIX false"),
        ("vms", "SPAWN false"),
        ("vms", "RUN false"),
        ("cms", "CMS false"),
    ],
)
def test_an_explicit_host_wrapper_reports_failure(personality, command, drive):
    result = emix(personality, "--mount", str(drive), "-c", command, cwd=drive)

    assert result.returncode != 0, f"{personality} -c {command!r} reported success"


@pytest.mark.parametrize(
    "personality,command",
    [("cpm", "UNIX true"), ("vms", "SPAWN true"), ("cms", "CMS true")],
)
def test_an_explicit_host_wrapper_reports_success(personality, command, drive):
    assert emix(personality, "--mount", str(drive), "-c", command, cwd=drive).returncode == 0


def test_save_reports_failure_because_it_refuses_the_operation(drive):
    """It prints CP/M's refusal, so it must not tell a script it worked."""
    assert emix("cpm", "--mount", str(drive), "-c", "SAVE 1 X.COM", cwd=drive).returncode != 0


def test_leaving_the_session_is_not_a_failure(drive):
    """Outcome separates 'stop' from 'failed'; EXIT is a stop."""
    for personality, command in [("cpm", "EXIT"), ("vms", "LOGOUT"), ("cms", "LOGOFF")]:
        result = emix(personality, "--mount", str(drive), "-c", command, cwd=drive)
        assert result.returncode == 0, f"{personality} {command}"
