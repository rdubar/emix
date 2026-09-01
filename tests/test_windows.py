"""Behaviour that only differs on Windows, checked from wherever you are.

None of this can be proved on a POSIX host — only that the branches are the
ones intended and that nothing POSIX-only is reached unguarded. The real proof
is the `windows-latest` job in CI running the whole suite.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest

from emix.config import config_path
from emix.host import _resolve_program
from emix.shell import default_history_path
from emix.terminal import Reply, ask_background, enable_ansi

ROOT = Path(__file__).resolve().parents[1]


# -- where a Windows user would look for their files --------------------


def test_configuration_lives_in_appdata(windows, monkeypatch, tmp_path):
    monkeypatch.delenv("EMIX_CONFIG", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))

    assert config_path() == tmp_path / "emix" / "emix.toml"


def test_history_lives_in_local_appdata(windows, monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert default_history_path("cpm") == tmp_path / "emix" / "cpm_history"


def test_application_profiles_sit_beside_the_settings(windows, monkeypatch, tmp_path):
    """Two files, one directory, on every host — or nobody finds the second."""
    from emix.apps.profiles import config_path as apps_path

    monkeypatch.delenv("EMIX_CONFIG", raising=False)
    monkeypatch.delenv("EMIX_APPS", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))

    assert apps_path().parent == config_path().parent
    assert apps_path() == tmp_path / "emix" / "apps.toml"


def test_the_environment_variable_still_wins_on_windows(windows, monkeypatch, tmp_path):
    """Precedence is the same everywhere, or a script stops being readable."""
    monkeypatch.setenv("EMIX_CONFIG", str(tmp_path / "chosen.toml"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "ignored"))

    assert config_path() == tmp_path / "chosen.toml"


def test_unix_paths_are_untouched(unix, monkeypatch, tmp_path):
    monkeypatch.delenv("EMIX_CONFIG", raising=False)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

    assert config_path() == Path("~/.config/emix/emix.toml").expanduser()
    assert default_history_path("vms") == tmp_path / "emix" / "vms_history"


# -- the console ---------------------------------------------------------


def test_a_posix_terminal_needs_no_permission_to_obey_escapes(unix):
    """Nothing is called, and nothing can fail: the answer is simply yes."""
    assert enable_ansi() is True


class Tty:
    def isatty(self) -> bool:
        return True


def test_a_windows_background_is_unknown_rather_than_guessed(windows, monkeypatch):
    """Windows offers no answer Emix is willing to act on.

    There is no termios to run an OSC 11 conversation over, and the legacy
    attribute word cannot describe a Windows Terminal profile's arbitrary RGB
    background — a nibble that reads as black may be rendering white. Guessing
    dark would paint green on a light screen, which is the one outcome the
    colour policy exists to prevent.
    """
    from emix.assist import default_screen

    probed = []
    monkeypatch.delenv("COLORFGBG", raising=False)
    monkeypatch.setattr("emix.terminal._from_osc11", lambda *a: probed.append(True) or Reply())

    answer = ask_background(Tty(), Tty())

    assert answer == Reply()
    assert default_screen(answer.dark) == "none"
    # OSC 11 is a POSIX conversation; nothing on Windows should attempt it.
    assert probed == []


def test_a_windows_user_can_still_ask_for_the_phosphor(windows, monkeypatch, tmp_path):
    """Unknown is not a refusal: it only means Emix will not decide for you."""
    from emix.host import Drive, DriveSet
    from emix.personalities.cpm import CpmShell

    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr("emix.shell.enable_ansi", lambda stream=None: True)
    drives = DriveSet([Drive.create("A", tmp_path)])

    shell = CpmShell(drives, stdin=Tty(), stdout=Tty(), screen="bright-green")

    assert shell.screen_colour == "bright-green"


def test_a_console_that_will_not_obey_escapes_gets_none(windows, monkeypatch, tmp_path):
    """Printing escape sequences at someone is worse than printing plain text."""
    from emix.host import Drive, DriveSet
    from emix.personalities.cpm import CpmShell

    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr("emix.shell.enable_ansi", lambda stream=None: False)
    drives = DriveSet([Drive.create("A", tmp_path)])

    shell = CpmShell(drives, stdin=Tty(), stdout=Tty(), screen="bright-green")

    assert shell.screen_colour == "none"
    assert shell.hint_colour == "none"


# -- finding a program to run --------------------------------------------


def test_a_bare_name_is_left_alone_on_unix(unix):
    """The host already searches PATH, and second-guessing it would differ."""
    assert _resolve_program("ls") == "ls"


def test_a_path_is_never_rewritten(windows):
    spelled = str(Path("C:/tools/thing.exe"))

    assert _resolve_program(spelled) == spelled


def test_a_bare_name_resolves_through_pathext_on_windows(windows, monkeypatch):
    """CreateProcess searches PATH but only ever appends .exe itself."""
    monkeypatch.setattr("shutil.which", lambda name: f"C:\\bin\\{name}.exe")

    assert _resolve_program("thing") == "C:\\bin\\thing.exe"


@pytest.mark.parametrize("suffix", [".bat", ".cmd", ".CMD"])
def test_a_batch_file_is_refused_rather_than_run_through_cmd(suffix, windows, monkeypatch):
    """Running one is running a shell, whatever `shell=False` claims.

    Windows hands a batch file to the command processor, which re-parses the
    arguments by its own rules. A file named `a&b` would become a second
    command, so Emix declines — visibly, as Principle 3 requires.
    """
    from emix.errors import Code, EmixError

    monkeypatch.setattr("shutil.which", lambda name: f"C:\\bin\\{name}{suffix}")

    with pytest.raises(EmixError) as caught:
        _resolve_program("build")

    assert caught.value.code is Code.NEEDS_SHELL


def test_a_batch_file_named_by_full_path_is_refused_too(windows):
    """Skipping the PATH search must not skip the reason for the rule."""
    from emix.errors import EmixError

    with pytest.raises(EmixError):
        _resolve_program(str(Path("C:/tools/build.cmd")))


def test_the_reason_reaches_the_user_through_the_shell(windows, monkeypatch, tmp_path):
    """Refusing safely is only half of it — Principle 3 says visibly.

    The house-style error cannot say why: no period system had a concept of
    declining to run a program. So the reason arrives as a marked hint, which
    is exactly what the assistance layer exists for.
    """
    import io

    from emix.host import Drive, DriveSet
    from emix.personalities.cpm import CpmShell

    monkeypatch.setattr("shutil.which", lambda name: f"C:\\bin\\{name}.cmd")
    drives = DriveSet([Drive.create("A", tmp_path)])
    shell = CpmShell(drives, stdin=io.StringIO(), stdout=io.StringIO(), strict=False)

    shell.execute("BUILD")
    rendered = shell.stdout.getvalue()

    assert "BUILD?" in rendered.upper()
    assert "Emix:" in rendered
    assert "batch file" in rendered
    assert "never uses a shell" in rendered


def test_strict_mode_still_refuses_but_says_nothing_extra(windows, monkeypatch, tmp_path):
    """Assistance may be switched off; the safety may not."""
    import io

    from emix.host import Drive, DriveSet
    from emix.personalities.cpm import CpmShell

    monkeypatch.setattr("shutil.which", lambda name: f"C:\\bin\\{name}.bat")
    drives = DriveSet([Drive.create("A", tmp_path)])
    shell = CpmShell(drives, stdin=io.StringIO(), stdout=io.StringIO(), strict=True)

    assert shell.execute("BUILD") is False
    assert "Emix:" not in shell.stdout.getvalue()


def test_an_unfindable_name_is_passed_through_to_fail_normally(windows, monkeypatch):
    """The host's own 'no such program' is the error the user should see."""
    monkeypatch.setattr("shutil.which", lambda name: None)

    assert _resolve_program("nosuch") == "nosuch"


# -- a host missing the modules Windows does not have --------------------


_WITHOUT = """
import sys

class Blocker:
    def find_module(self, name, path=None):
        return self if name in {"readline", "termios", "tty"} else None
    def find_spec(self, name, path=None, target=None):
        if name in {"readline", "termios", "tty"}:
            raise ImportError(name)
        return None

sys.meta_path.insert(0, Blocker())
for name in ("readline", "termios", "tty"):
    sys.modules.pop(name, None)

from emix.cli import main
sys.exit(main(["cpm", "-c", "DIR", "-c", "TYPE NOTES.TXT"]))
"""


def test_emix_runs_where_readline_and_termios_do_not_exist(tmp_path):
    """Windows has none of the three. They are guarded; this proves it.

    Run as a real process, because the guards are import-time and a meta path
    hook inside the suite would outlive the test.
    """
    (tmp_path / "NOTES.TXT").write_text("hello\n")
    result = subprocess.run(  # noqa: S603 - fixed argv, no shell, test-local
        [sys.executable, "-c", _WITHOUT],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src"), "NO_COLOR": "1"},
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert "NOTES" in result.stdout
    assert "hello" in result.stdout
