"""Settings that persist between sessions, and the precedence between them."""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import toml_path
from emix import config as module
from emix.errors import EmixError


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "emix.toml"
    path.write_text(text)
    return path


def test_no_configuration_file_is_not_an_error(tmp_path):
    settings = module.load(tmp_path / "absent.toml")

    assert settings.personality == ""
    assert settings.drives == {}
    assert settings.strict is None


def test_settings_are_read(tmp_path):
    path = write(
        tmp_path,
        '[emix]\npersonality = "vms"\nstrict = true\nhint-colour = "cyan"\n'
        '[drives]\ndefault = ["~/Documents"]\n',
    )

    settings = module.load(path)

    assert settings.personality == "vms"
    assert settings.strict is True
    assert settings.hint_colour == "cyan"
    assert settings.drives["default"] == [Path.home() / "Documents"]


def test_a_personality_uses_its_own_drives_before_the_default(tmp_path):
    path = write(tmp_path, '[drives]\ndefault = ["/opt"]\ncpm = ["/usr", "/etc"]\n')

    settings = module.load(path)

    assert settings.mounts_for("cpm") == [Path("/usr"), Path("/etc")]
    assert settings.mounts_for("vms") == [Path("/opt")]


def test_a_single_path_may_be_written_without_a_list(tmp_path):
    path = write(tmp_path, '[drives]\ncpm = "/opt"\n')

    assert module.load(path).mounts_for("cpm") == [Path("/opt")]


def test_the_screen_colour_is_read(tmp_path):
    path = write(tmp_path, '[emix]\nscreen = "green"\n')

    assert module.load(path).screen == "green"


def test_an_unknown_screen_colour_is_refused_by_its_own_name(tmp_path):
    path = write(tmp_path, '[emix]\nscreen = "chartreuse"\n')

    with pytest.raises(EmixError) as caught:
        module.load(path)

    assert "screen" in caught.value.detail


def test_an_unknown_colour_is_refused_with_the_choices(tmp_path):
    path = write(tmp_path, '[emix]\nhint-colour = "chartreuse"\n')

    with pytest.raises(EmixError) as caught:
        module.load(path)

    assert "chartreuse" in caught.value.detail
    assert "yellow" in caught.value.detail


def test_a_windows_path_in_double_quotes_is_explained(tmp_path):
    """TOML says "Invalid hex value", which tells the reader nothing at all.

    `\\U` starts a Unicode escape, so pasting `C:\\Users\\me` into double quotes
    fails in a way that looks like a bug in Emix rather than a quoting rule.
    """
    path = write(tmp_path, '[drives]\ndefault = ["C:\\Users\\me\\Documents"]\n')

    with pytest.raises(EmixError) as caught:
        module.load(path)

    assert "backslashes doubled" in caught.value.detail
    assert "Single quotes" in caught.value.detail


def test_ordinary_toml_mistakes_are_not_blamed_on_windows(tmp_path):
    """The advice must only appear when it is the likely cause."""
    path = write(tmp_path, "[emix\n")

    with pytest.raises(EmixError) as caught:
        module.load(path)

    assert "backslashes" not in caught.value.detail


def test_a_single_quoted_windows_path_is_read_as_written(tmp_path):
    path = write(tmp_path, "[drives]\ndefault = ['C:\\Users\\me']\n")

    assert module.load(path).mounts_for("cpm") == [Path("C:\\Users\\me").expanduser()]


def test_malformed_toml_names_the_file(tmp_path):
    path = write(tmp_path, "[emix\n")

    with pytest.raises(EmixError) as caught:
        module.load(path)

    assert "emix.toml" in caught.value.subject


def test_strict_must_be_a_boolean(tmp_path):
    path = write(tmp_path, '[emix]\nstrict = "yes"\n')

    with pytest.raises(EmixError):
        module.load(path)


def test_drives_must_be_paths(tmp_path):
    path = write(tmp_path, "[drives]\ncpm = [1, 2]\n")

    with pytest.raises(EmixError):
        module.load(path)


# -- precedence ---------------------------------------------------------


def test_the_command_line_beats_the_configuration_file(tmp_path, monkeypatch, capsys):
    from emix.cli import main

    path = write(tmp_path, '[emix]\npersonality = "vms"\n')
    monkeypatch.setenv(module.ENVIRONMENT, str(path))

    main(["cms", "--mount", str(tmp_path), "-c", "ABOUT"])

    assert "(cms)" in capsys.readouterr().out


def test_the_configuration_file_beats_the_built_in_default(tmp_path, monkeypatch, capsys):
    from emix.cli import main

    path = write(tmp_path, '[emix]\npersonality = "vms"\n')
    monkeypatch.setenv(module.ENVIRONMENT, str(path))

    main(["--mount", str(tmp_path), "-c", "ABOUT"])

    assert "(vms)" in capsys.readouterr().out


def test_configured_drives_are_mounted_when_none_are_given(tmp_path, monkeypatch, capsys):
    from emix.cli import main

    drive = tmp_path / "documents"
    drive.mkdir()
    (drive / "HELLO.TXT").write_text("hi\n")
    path = write(tmp_path, f"[drives]\ndefault = [{toml_path(drive)}]\n")
    monkeypatch.setenv(module.ENVIRONMENT, str(path))

    main(["cpm", "-c", "DIR"])

    assert "HELLO" in capsys.readouterr().out
