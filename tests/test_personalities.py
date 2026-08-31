"""Each personality's vocabulary and house style."""

from __future__ import annotations

import io

import pytest

from emix.personalities import DRIVE_NAMES, PERSONALITIES
from emix.personalities.cms import CmsShell
from emix.personalities.cpm import CpmShell
from emix.personalities.vms import VmsShell


def run(personality, drives, *lines, answers=""):
    output = io.StringIO()
    shell = personality(drives, stdin=io.StringIO(answers), stdout=output)
    for line in lines:
        shell.execute(line)
    return output.getvalue()


# -- CP/M ----------------------------------------------------------------


def test_cpm_dir_uses_columns_and_no_sizes(drives, drive_root):
    (drive_root / "hello.txt").write_text("hi")

    rendered = run(CpmShell, drives, "DIR")

    assert "A: HELLO    TXT" in rendered
    assert "2" not in rendered.replace("CP/M 2.2", "")  # no size column


def test_cpm_dir_star_dot_star_means_every_file(drives, drive_root):
    (drive_root / "MAKEFILE").write_text("x")
    (drive_root / "a.txt").write_text("x")

    # fnmatch would read "*.*" as "must contain a dot"; CP/M means "all".
    assert "MAKEFILE" in run(CpmShell, drives, "DIR *.*")


def test_cpm_shows_a_long_name_as_a_reversible_8_3_alias(drives, drive_root):
    (drive_root / "pyproject.toml").write_text("x")

    # Not PYPROJECT.TOML (does not fit) and not PYPROJEC.TOM (cannot be typed
    # back). The alias is short, and the next test types it back.
    assert "PYPROJ_1 TOM" in run(CpmShell, drives, "DIR")


def test_cpm_accepts_an_alias_back_without_renaming_the_host_file(drives, drive_root):
    (drive_root / "pyproject.toml").write_text("[project]\n")

    rendered = run(CpmShell, drives, "TYPE PYPROJ_1.TOM")

    assert "[project]" in rendered
    assert (drive_root / "pyproject.toml").exists()


def test_cpm_still_prefers_a_real_host_name_over_an_alias(drives, drive_root):
    (drive_root / "NOTES.TXT").write_text("the real one\n")
    (drive_root / "notes-from-yesterday.txt").write_text("the long one\n")

    assert "the real one" in run(CpmShell, drives, "TYPE NOTES.TXT")


def test_cpm_aliases_are_stable_regardless_of_listing_order(drives, drive_root):
    for name in ["zeta-long-name.txt", "alpha-long-name.txt"]:
        (drive_root / name).write_text("x")

    first = run(CpmShell, drives, "DIR")
    second = run(CpmShell, drives, "DIR")

    assert first == second


def test_cpm_pip_copies_in_destination_first_order(drives, drive_root):
    (drive_root / "OLD.TXT").write_text("data")

    run(CpmShell, drives, "PIP NEW.TXT=OLD.TXT")

    assert (drive_root / "NEW.TXT").read_text() == "data"


def test_cpm_ren_uses_destination_first_order(drives, drive_root):
    (drive_root / "old.txt").write_text("data")

    run(CpmShell, drives, "REN NEW.TXT=OLD.TXT")

    assert (drive_root / "NEW.TXT").read_text() == "data"
    assert not (drive_root / "old.txt").exists()


def test_cpm_era_erases_only_after_an_explicit_yes(drives, drive_root):
    doomed = drive_root / "scratch.txt"
    doomed.write_text("x")

    assert "NOT ERASED" in run(CpmShell, drives, "ERA SCRATCH.TXT", answers="n\n")
    assert doomed.exists()

    assert "1 FILE(S) ERASED" in run(CpmShell, drives, "ERA SCRATCH.TXT", answers="Y\n")
    assert not doomed.exists()


def test_cpm_reports_missing_files_in_house_style(drives):
    assert run(CpmShell, drives, "TYPE NOSUCH.TXT") == "NO FILE\n"


def test_cpm_reports_an_unknown_verb_as_cpm_did(drives):
    from unittest.mock import patch

    with patch("emix.host.subprocess.run", side_effect=FileNotFoundError):
        assert run(CpmShell, drives, "frobnicate") == "FROBNICATE?\n"


def test_cpm_help_separates_builtins_from_emix_extensions(drives):
    rendered = run(CpmShell, drives, "HELP")

    assert "CCP BUILT-IN COMMANDS" in rendered
    assert "SIMULATED TRANSIENT" in rendered
    assert "EMIX EXTENSIONS" in rendered
    # PIP was a transient program, never a CCP built-in.
    builtins = rendered.split("SIMULATED")[0]
    assert "PIP" not in builtins


def test_cpm_drive_prefix_selects_another_drive(drive_root, tmp_path):
    from emix.host import Drive, DriveSet

    other = tmp_path / "diskB"
    other.mkdir()
    (other / "ON_B.TXT").write_text("b side")
    drives = DriveSet([Drive.create("A", drive_root), Drive.create("B", other)])

    assert "b side" in run(CpmShell, drives, "TYPE B:ON_B.TXT")


# -- VMS -----------------------------------------------------------------


def test_vms_delete_requires_an_explicit_version(drives, drive_root):
    target = drive_root / "REPORT.TXT"
    target.write_text("x")

    rendered = run(VmsShell, drives, "DELETE REPORT.TXT")

    assert "NOVER" in rendered
    assert target.exists()


def test_vms_delete_with_a_version_asks_and_erases(drives, drive_root):
    target = drive_root / "REPORT.TXT"
    target.write_text("x")

    rendered = run(VmsShell, drives, "DELETE REPORT.TXT;*", answers="Y\n")

    assert "FILDEL" in rendered
    assert not target.exists()


def test_vms_verbs_abbreviate(drives, drive_root):
    (drive_root / "A.TXT").write_text("x")

    for typed in ("DIRECTORY", "DIRECT", "DIRE", "DIR"):
        assert "A.TXT;1" in run(VmsShell, drives, typed)


def test_vms_size_qualifier_adds_a_block_count(drives, drive_root):
    (drive_root / "A.TXT").write_text("x" * 2000)

    plain = run(VmsShell, drives, "DIRECTORY")
    sized = run(VmsShell, drives, "DIRECTORY/SIZE")

    assert "blocks" not in plain
    assert "blocks" in sized


def test_vms_errors_use_facility_severity_identifier_form(drives):
    rendered = run(VmsShell, drives, "TYPE NOSUCH.TXT")

    assert "%RMS-E-FNF" in rendered


def test_vms_does_not_run_host_commands_implicitly(drives):
    rendered = run(VmsShell, drives, "ls")

    assert "%DCL-W-IVVERB" in rendered


def test_vms_show_default_reports_the_current_device(drives):
    assert "A:[000000]" in run(VmsShell, drives, "SHOW DEFAULT")


# -- CMS -----------------------------------------------------------------


def test_cms_maps_a_three_token_fileid_onto_a_host_name(drives, drive_root):
    (drive_root / "PROFILE.EXEC").write_text("body\n")

    assert "body" in run(CmsShell, drives, "TYPE PROFILE EXEC")


def test_cms_listfile_prints_the_fn_ft_fm_columns(drives, drive_root):
    (drive_root / "PROFILE.EXEC").write_text("x")

    assert "PROFILE  EXEC     A1" in run(CmsShell, drives, "LISTFILE")


def test_cms_answers_ready_after_each_command(drives, drive_root):
    (drive_root / "A.TXT").write_text("x")

    rendered = run(CmsShell, drives, "LISTFILE")

    assert "Ready; T=" in rendered


def test_cms_reports_a_return_code_on_failure(drives):
    rendered = run(CmsShell, drives, "TYPE NOSUCH FILE")

    assert "DMSxxx002E" in rendered
    assert "Ready(00028);" in rendered


def test_cms_copyfile_splits_the_six_token_form(drives, drive_root):
    (drive_root / "OLD.DATA").write_text("payload")

    run(CmsShell, drives, "COPYFILE OLD DATA A NEW DATA A")

    assert (drive_root / "NEW.DATA").read_text() == "payload"


# -- all personalities ----------------------------------------------------


@pytest.mark.parametrize("key", sorted(PERSONALITIES))
def test_every_personality_starts_and_reports_a_banner(key, drives):
    shell = PERSONALITIES[key](drives, stdin=io.StringIO(), stdout=io.StringIO())

    assert shell.banner().strip()
    assert shell.prompt() is not None
    assert key in DRIVE_NAMES


@pytest.mark.parametrize("key", sorted(PERSONALITIES))
def test_every_personality_exposes_the_shared_project_commands(key, drives):
    rendered = run(PERSONALITIES[key], drives, "ABOUT", "CREDIT")

    # Each personality may fold this into its own casing, so compare content.
    shouted = rendered.upper()
    assert "ACTIVE PERSONALITY:" in shouted
    assert f"({key.upper()})" in shouted
    assert "ROGER DUBAR" in shouted
    assert "MIT LICENSE" in shouted


@pytest.mark.parametrize("key", sorted(PERSONALITIES))
def test_no_personality_can_read_outside_its_drive(key, drives, drive_root, tmp_path):
    (tmp_path / "secret.txt").write_text("must not appear")
    (drive_root / "LINK.TXT").symlink_to(tmp_path / "secret.txt")

    shell = PERSONALITIES[key]
    rendered = run(shell, drives, "TYPE LINK.TXT", "TYPE LINK TXT")

    assert "must not appear" not in rendered


@pytest.mark.parametrize(
    ("key", "command"),
    [("cpm", "DIR"), ("vms", "DIRECTORY"), ("cms", "LISTFILE")],
)
def test_listings_distinguish_names_that_differ_only_by_case(
    key, command, drives, drive_root, monkeypatch
):
    # Only reachable on a case-sensitive host, where notes.txt and NOTES.TXT
    # coexist and would otherwise print as two identical rows.
    from emix.host import DriveSet
    from emix.personalities import PERSONALITIES

    both = [drive_root / "notes.txt", drive_root / "NOTES.TXT"]
    for path in both:
        path.write_text("x")
    monkeypatch.setattr(DriveSet, "_iterdir", lambda self, drive: iter(both))

    rendered = run(PERSONALITIES[key], drives, command)

    assert "notes.txt" in rendered
    assert "NOTES.TXT" in rendered
