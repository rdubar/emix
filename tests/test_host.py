"""The drive layer: containment, case folding, and ambiguity."""

from __future__ import annotations

import pytest

from conftest import needs_symlinks
from emix.errors import Code, EmixError
from emix.host import Drive, DriveSet


@needs_symlinks
def test_symlink_pointing_outside_the_drive_is_refused(drives, drive_root, tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("host data the drive must not expose")
    (drive_root / "LINK.TXT").symlink_to(secret)

    with pytest.raises(EmixError) as caught:
        drives.locate("LINK.TXT")

    assert caught.value.code is Code.OUTSIDE_DRIVE


@needs_symlinks
def test_escaping_symlink_is_absent_from_listings(drives, drive_root, tmp_path):
    (tmp_path / "secret.txt").write_text("data")
    (drive_root / "LINK.TXT").symlink_to(tmp_path / "secret.txt")
    (drive_root / "REAL.TXT").write_text("data")

    listed = [path.name for path in drives.match("*")]

    # A listing must not advertise a file that `locate` will refuse.
    assert listed == ["REAL.TXT"]


@needs_symlinks
def test_symlink_staying_inside_the_drive_is_allowed(drives, drive_root):
    (drive_root / "TARGET.TXT").write_text("fine")
    (drive_root / "LINK.TXT").symlink_to(drive_root / "TARGET.TXT")

    assert drives.locate("LINK.TXT").read_text() == "fine"


@pytest.mark.parametrize("name", ["../secret", "a/b", "..", ".", "", "a\\b"])
def test_traversal_and_malformed_names_are_refused(drives, name):
    with pytest.raises(EmixError) as caught:
        drives.locate(name)

    assert caught.value.code in {Code.BAD_NAME, Code.OUTSIDE_DRIVE}


def test_lookup_ignores_case(drives, drive_root):
    (drive_root / "ReadMe.txt").write_text("hello")

    assert drives.locate("README.TXT").name == "ReadMe.txt"


def test_case_ambiguity_fails_loudly(drives, drive_root, monkeypatch):
    # Two host files folding to one name is possible on Linux and would
    # otherwise be resolved by whichever iterdir() happened to yield first.
    both = [drive_root / "Readme.txt", drive_root / "README.TXT"]
    monkeypatch.setattr(DriveSet, "_iterdir", lambda self, drive: iter(both))

    with pytest.raises(EmixError) as caught:
        drives.locate("readme.txt")

    assert caught.value.code is Code.AMBIGUOUS
    assert "README.TXT" in caught.value.detail


def test_reserve_refuses_an_existing_name_in_any_case(drives, drive_root):
    (drive_root / "notes.txt").write_text("x")

    with pytest.raises(EmixError) as caught:
        drives.reserve("NOTES.TXT")

    assert caught.value.code is Code.EXISTS


def test_reserve_returns_a_contained_path(drives, drive_root):
    assert drives.reserve("NEW.TXT").parent == drive_root


def test_match_folds_case_consistently_with_locate(drives, drive_root):
    (drive_root / "Straße.TXT").write_text("x")

    # locate() casefolds, so match() must too, or a file can be listed and
    # then refused when opened.
    assert [p.name for p in drives.match("*.txt")] == ["Straße.TXT"]


def test_locate_refuses_a_directory(drives, drive_root):
    (drive_root / "SUB").mkdir()

    with pytest.raises(EmixError) as caught:
        drives.locate("SUB")

    assert caught.value.code is Code.NOT_A_FILE


def test_unknown_drive_is_reported(drives):
    with pytest.raises(EmixError) as caught:
        drives.drive("Z")

    assert caught.value.code is Code.NO_DRIVE


def test_second_drive_is_reachable_by_name(drive_root, tmp_path):
    other = tmp_path / "diskB"
    other.mkdir()
    (other / "B.TXT").write_text("on b")
    set_ = DriveSet([Drive.create("A", drive_root), Drive.create("B", other)])

    assert set_.locate("B.TXT", drive="B").read_text() == "on b"
    assert set_.current == "A"


def test_set_default_cannot_climb_out_of_the_drive(drives, drive_root):
    with pytest.raises(EmixError) as caught:
        drives.set_default("..")

    assert caught.value.code is Code.OUTSIDE_DRIVE


def test_set_default_descends_and_reports_position(drives, drive_root):
    (drive_root / "SUB").mkdir()
    drives.set_default("SUB")

    assert drives.relative_default() == "SUB"
    drives.set_default("..")
    assert drives.relative_default() == ""


def test_drive_creation_rejects_a_non_directory(tmp_path):
    file_ = tmp_path / "afile"
    file_.write_text("x")

    with pytest.raises(EmixError) as caught:
        Drive.create("A", file_)

    assert caught.value.code is Code.NO_DRIVE


def test_case_collisions_names_only_the_clashing_entries(tmp_path):
    from emix.host import case_collisions

    entries = [tmp_path / "notes.txt", tmp_path / "NOTES.TXT", tmp_path / "other.txt"]

    assert case_collisions(entries) == {"notes.txt", "NOTES.TXT"}


def test_case_collisions_is_empty_when_nothing_clashes(tmp_path):
    from emix.host import case_collisions

    assert case_collisions([tmp_path / "a.txt", tmp_path / "b.txt"]) == set()


# -- the same mounts under another system's names -----------------------


def test_renaming_keeps_the_roots_in_order(drive_root, tmp_path):
    second = tmp_path / "second"
    second.mkdir()
    drives = DriveSet([Drive.create("A", drive_root), Drive.create("B", second)])

    renamed = drives.renamed(("DKA0", "DKA100", "DKA200"))

    assert renamed.names == ["DKA0", "DKA100"]
    assert renamed.drive("DKA0").root == drives.drive("A").root
    assert renamed.drive("DKA100").root == drives.drive("B").root


def test_renaming_keeps_you_on_the_drive_you_were_on(drive_root, tmp_path):
    """Position is the one thing that means the same in all three systems."""
    second = tmp_path / "second"
    second.mkdir()
    drives = DriveSet([Drive.create("A", drive_root), Drive.create("B", second)])
    drives.select("B")

    assert drives.renamed(("DKA0", "DKA100")).current == "DKA100"


def test_renaming_refuses_when_the_new_system_has_too_few_drives(drive_root, tmp_path):
    """CP/M has sixteen drive names and VMS has four; that is a real limit."""
    extra = tmp_path / "extra"
    extra.mkdir()
    drives = DriveSet([Drive.create("A", drive_root), Drive.create("B", extra)])

    with pytest.raises(EmixError) as caught:
        drives.renamed(("DKA0",))

    assert caught.value.code is Code.NO_DRIVE


def test_renaming_leaves_the_original_alone(drive_root):
    drives = DriveSet([Drive.create("A", drive_root)])

    drives.renamed(("DKA0",))

    assert drives.names == ["A"]
    assert drives.current == "A"
