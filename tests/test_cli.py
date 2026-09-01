"""The command line: mounting, personality selection, one-shot commands."""

from __future__ import annotations

import pytest

from emix import __version__
from emix.cli import main


def test_version_is_reported(capsys):
    with pytest.raises(SystemExit) as caught:
        main(["--version"])

    assert caught.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_one_shot_command_runs_and_exits(tmp_path, capsys):
    (tmp_path / "hello.txt").write_text("hi")

    assert main(["cpm", "--mount", str(tmp_path), "-c", "DIR"]) == 0
    assert "HELLO    TXT" in capsys.readouterr().out


def test_several_commands_run_in_order(tmp_path, capsys):
    (tmp_path / "old.txt").write_text("data")

    main(["cpm", "-m", str(tmp_path), "-c", "PIP NEW.TXT=OLD.TXT", "-c", "DIR"])

    assert "NEW      TXT" in capsys.readouterr().out


def test_mounts_become_drives_in_order(tmp_path, capsys):
    first, second = tmp_path / "one", tmp_path / "two"
    first.mkdir()
    second.mkdir()
    (second / "onb.txt").write_text("b side")

    main(["cpm", "-m", str(first), "-m", str(second), "-c", "TYPE B:ONB.TXT"])

    assert "b side" in capsys.readouterr().out


def test_root_is_still_accepted_as_the_first_mount(tmp_path, capsys):
    (tmp_path / "a.txt").write_text("x")

    main(["cpm", "--root", str(tmp_path), "-c", "DIR"])

    assert "A        TXT" in capsys.readouterr().out


def test_each_personality_names_its_drives_its_own_way(tmp_path, capsys):
    (tmp_path / "a.txt").write_text("x")

    main(["vms", "-m", str(tmp_path), "-c", "SHOW DEFAULT"])
    assert "DKA0:" in capsys.readouterr().out

    main(["cms", "-m", str(tmp_path), "-c", "LISTFILE"])
    assert "A1" in capsys.readouterr().out


def test_a_missing_directory_is_a_clean_error(tmp_path, capsys):
    with pytest.raises(SystemExit) as caught:
        main(["cpm", "-m", str(tmp_path / "nope")])

    assert caught.value.code != 0
    assert "not a directory" in capsys.readouterr().err


def test_mounting_a_file_is_a_clean_error(tmp_path, capsys):
    target = tmp_path / "afile"
    target.write_text("x")

    with pytest.raises(SystemExit):
        main(["cpm", "-m", str(target)])

    assert "not a directory" in capsys.readouterr().err


def test_too_many_mounts_for_the_personality_is_refused(tmp_path):
    mounts = []
    for index in range(5):
        directory = tmp_path / f"d{index}"
        directory.mkdir()
        mounts += ["-m", str(directory)]

    # The VMS personality names only four devices.
    with pytest.raises(SystemExit) as caught:
        main(["vms", *mounts])

    assert "at most 4 drives" in str(caught.value)


def test_an_unknown_personality_is_rejected(capsys):
    with pytest.raises(SystemExit):
        main(["altair"])

    assert "invalid choice" in capsys.readouterr().err


def test_one_shot_mode_writes_no_history_file(tmp_path, monkeypatch):
    state = tmp_path / "state"
    monkeypatch.setenv("XDG_STATE_HOME", str(state))
    (tmp_path / "a.txt").write_text("x")

    main(["cpm", "-m", str(tmp_path), "-c", "VER"])

    assert not state.exists()


# -- BECOME: the same files under another vocabulary --------------------


def test_becoming_another_personality_keeps_the_files(tmp_path, capsys):
    """The point of one engine: the language changes, the files do not."""
    (tmp_path / "NOTES.TXT").write_text("hello\n")

    main(["cpm", "-m", str(tmp_path), "-c", "DIR", "-c", "BECOME VMS", "-c", "DIRECTORY"])
    rendered = capsys.readouterr().out

    assert "NOTES    TXT" in rendered  # CP/M said it this way
    assert "NOTES.TXT;1" in rendered  # and DCL says it that way
    assert "DKA0:" in rendered  # under DCL's drive names


def test_the_drive_you_were_on_is_the_drive_you_land_on(tmp_path, capsys):
    """Position carries over, because that is what means the same in all three."""
    first, second = tmp_path / "one", tmp_path / "two"
    for folder in (first, second):
        folder.mkdir()
    (second / "SECOND.TXT").write_text("here\n")

    main(
        [
            "vms",
            "-m",
            str(first),
            "-m",
            str(second),
            "-c",
            "SET DEFAULT DKA100:",
            "-c",
            "BECOME CPM",
            "-c",
            "DIR",
        ]
    )
    rendered = capsys.readouterr().out

    # DKA100: was the second mount, so B: is where CP/M should be looking.
    assert "B: SECOND   TXT" in rendered


def test_becoming_can_be_done_twice(tmp_path, capsys):
    (tmp_path / "NOTES.TXT").write_text("hello\n")

    code = main(
        [
            "cpm",
            "-m",
            str(tmp_path),
            "-c",
            "BECOME VMS",
            "-c",
            "BECOME CMS",
            "-c",
            "LISTFILE",
        ]
    )

    assert code == 0
    assert "NOTES    TXT" in capsys.readouterr().out


def test_becoming_nothing_in_particular_lists_the_choices(tmp_path, capsys):
    main(["cpm", "-m", str(tmp_path), "-c", "BECOME"])
    rendered = capsys.readouterr().out.upper()

    assert "CPM" in rendered and "VMS" in rendered and "CMS" in rendered


def test_becoming_something_that_is_not_a_personality_fails(tmp_path, capsys):
    code = main(["cpm", "-m", str(tmp_path), "-c", "BECOME ATARI"])

    assert code != 0
    assert "ATARI?" in capsys.readouterr().out.upper()


def test_becoming_what_you_already_are_says_so(tmp_path, capsys):
    code = main(["cpm", "-m", str(tmp_path), "-c", "BECOME CPM", "-c", "DIR"])

    assert code == 0
    assert "ALREADY" in capsys.readouterr().out.upper()


def test_more_mounts_than_the_new_system_has_drives_is_refused(tmp_path, capsys):
    """VMS ships four drive names; CP/M ships sixteen."""
    mounts = []
    for index in range(5):
        folder = tmp_path / f"d{index}"
        folder.mkdir()
        mounts += ["-m", str(folder)]

    code = main(["cpm", *mounts, "-c", "BECOME VMS"])

    assert code != 0
    assert "?" in capsys.readouterr().out or code == 1


# -- SETUP: what is configured, and what is missing ----------------------


def test_setup_reports_without_changing_anything(tmp_path, capsys, monkeypatch):
    """It reads. It never writes, prompts, or stores."""
    monkeypatch.setenv("EMIX_CONFIG", str(tmp_path / "none.toml"))
    monkeypatch.setenv("EMIX_APPS", str(tmp_path / "none-either.toml"))

    assert main(["--setup"]) == 0
    rendered = capsys.readouterr().out

    assert "Emix" in rendered
    assert "Settings" in rendered
    assert "not present" in rendered
    assert not list(tmp_path.iterdir())


def test_setup_never_prints_a_key(tmp_path, capsys, monkeypatch):
    """Presence is the answer. The value is a credential."""
    from emix import converse

    monkeypatch.setenv(converse.KEY_VARIABLE, "sk-ant-secret-value-here")
    monkeypatch.setenv("EMIX_CONFIG", str(tmp_path / "none.toml"))

    main(["--setup"])
    rendered = capsys.readouterr().out

    assert "sk-ant-secret-value-here" not in rendered
    assert converse.KEY_VARIABLE in rendered


def test_setup_says_when_no_key_is_named(tmp_path, capsys, monkeypatch):
    from emix import converse

    monkeypatch.delenv(converse.KEY_VARIABLE, raising=False)
    monkeypatch.setenv("EMIX_CONFIG", str(tmp_path / "none.toml"))

    main(["--setup"])

    assert "the SDK will look for its own" in capsys.readouterr().out


@pytest.mark.parametrize("key", ["cpm", "vms", "cms", "wopr"])
def test_every_personality_can_answer_setup(key, tmp_path, capsys):
    """A shared question deserves a shared answer, in all four."""
    main([key, "-m", str(tmp_path), "-c", "SETUP"])

    assert "Emix" in capsys.readouterr().out
