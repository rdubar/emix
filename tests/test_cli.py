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
