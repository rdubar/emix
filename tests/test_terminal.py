"""Asking the terminal what colour it is, and never guessing."""

from __future__ import annotations

import io

import pytest

from conftest import needs_posix_terminal
from emix.assist import default_screen
from emix.terminal import Reply, _from_colorfgbg, _luminance, ask_background, background_is_dark


class FakeTty(io.StringIO):
    def __init__(self, text: str = "", tty: bool = True) -> None:
        super().__init__(text)
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty

    def fileno(self) -> int:
        # A real number, so code that asks for one gets past the request. No
        # terminal call in these tests reaches an actual descriptor.
        return 0


# -- the cheap method ---------------------------------------------------


@pytest.mark.parametrize("value,dark", [("15;0", True), ("0;15", False), ("7;0", True)])
def test_colorfgbg_is_read_when_the_terminal_exports_it(monkeypatch, value, dark):
    monkeypatch.setenv("COLORFGBG", value)

    assert background_is_dark(FakeTty(), FakeTty()) is dark


def test_a_malformed_colorfgbg_is_ignored_rather_than_guessed(monkeypatch):
    monkeypatch.setenv("COLORFGBG", "nonsense")

    assert _from_colorfgbg() is None


def test_no_colorfgbg_is_not_an_answer(monkeypatch):
    monkeypatch.delenv("COLORFGBG", raising=False)

    assert _from_colorfgbg() is None


# -- never probe something that is not a terminal ------------------------


def test_a_pipe_is_never_probed(monkeypatch):
    """Writing an escape sequence into a pipe would corrupt the reader."""
    monkeypatch.delenv("COLORFGBG", raising=False)
    sink = FakeTty(tty=False)

    assert background_is_dark(FakeTty(tty=False), sink) is None
    assert sink.getvalue() == ""


def test_a_dumb_terminal_is_never_probed(monkeypatch):
    monkeypatch.delenv("COLORFGBG", raising=False)
    monkeypatch.setenv("TERM", "dumb")
    sink = FakeTty()

    assert background_is_dark(FakeTty(), sink) is None
    assert sink.getvalue() == ""


# -- luminance ----------------------------------------------------------


def test_black_is_dark_and_white_is_not():
    assert _luminance(0, 0, 0) < 0.4
    assert _luminance(1, 1, 1) > 0.4


def test_green_dominates_perceived_brightness():
    assert _luminance(0, 1, 0) > _luminance(1, 0, 0)


# -- what the answer is used for ----------------------------------------


def test_a_dark_screen_gets_green_phosphor():
    assert default_screen(True) == "bright-green"


def test_a_light_or_unknown_screen_is_left_alone():
    # Green on a light ground is unreadable, and a terminal that will not say
    # what it is gets the same benefit of the doubt as one that says "light".
    assert default_screen(False) == "none"
    assert default_screen(None) == "none"


def test_a_dark_screen_lights_the_phosphor_once_and_puts_it_out(tmp_path, monkeypatch):
    from emix.host import Drive, DriveSet
    from emix.personalities.cpm import CpmShell

    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("COLORFGBG", "15;0")
    drives = DriveSet([Drive.create("A", tmp_path)])
    screen = FakeTty()
    shell = CpmShell(drives, stdin=FakeTty(), stdout=screen, history=None)

    shell.run()
    written = screen.getvalue()

    assert shell.screen_colour == "bright-green"
    # Set once at the top, not restated around each line: the machine's own
    # output must not be full of escape sequences.
    assert written.startswith("\033[92m")
    assert written.count("\033[92m") == 1
    assert written.endswith("\033[0m")


def test_a_hint_hands_the_phosphor_back(tmp_path, monkeypatch):
    from emix.host import Drive, DriveSet
    from emix.personalities.cpm import CpmShell

    monkeypatch.delenv("NO_COLOR", raising=False)
    drives = DriveSet([Drive.create("A", tmp_path)])
    shell = CpmShell(drives, stdin=FakeTty(), stdout=FakeTty(), strict=False)
    shell.hint_colour, shell.screen_colour = "yellow", "green"

    shell.execute("ABOUT")
    written = shell.stdout.getvalue()

    # Amber, so it does not read as the screen, and green again afterwards so
    # the rest of the session is not left plain.
    assert "\033[33m" in written
    assert written.rstrip("\n").endswith("\033[0m\033[32m")


def test_a_screen_colour_nobody_wants_is_never_lit(tmp_path, monkeypatch):
    from emix.host import Drive, DriveSet
    from emix.personalities.cpm import CpmShell

    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("COLORFGBG", "15;0")
    drives = DriveSet([Drive.create("A", tmp_path)])

    shell = CpmShell(drives, stdin=FakeTty(), stdout=FakeTty(), screen="green", history=None)
    shell.run()

    assert shell.screen_colour == "none"
    assert "\033[" not in shell.stdout.getvalue()


def test_an_explicit_screen_wins_over_a_light_terminal(tmp_path, monkeypatch):
    from emix.host import Drive, DriveSet
    from emix.personalities.cpm import CpmShell

    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("COLORFGBG", "0;15")
    drives = DriveSet([Drive.create("A", tmp_path)])

    shell = CpmShell(drives, stdin=FakeTty(), stdout=FakeTty(), screen="cyan")

    assert shell.screen_colour == "cyan"


def test_hints_are_amber_against_the_green_phosphor(tmp_path, monkeypatch):
    """Both ends bright, so the two are told apart at a glance not on inspection."""
    from emix.host import Drive, DriveSet
    from emix.personalities.cpm import CpmShell

    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("EMIX_HINT_COLOUR", raising=False)
    monkeypatch.setenv("COLORFGBG", "15;0")
    drives = DriveSet([Drive.create("A", tmp_path)])

    shell = CpmShell(drives, stdin=FakeTty(), stdout=FakeTty())

    assert shell.screen_colour == "bright-green"
    assert shell.hint_colour == "bright-yellow"


def test_an_amber_screen_gives_its_hue_up_rather_than_blur_the_two(tmp_path, monkeypatch):
    from emix.assist import default_hint
    from emix.host import Drive, DriveSet
    from emix.personalities.cpm import CpmShell

    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("EMIX_HINT_COLOUR", raising=False)
    monkeypatch.setenv("COLORFGBG", "0;15")
    drives = DriveSet([Drive.create("A", tmp_path)])

    shell = CpmShell(drives, stdin=FakeTty(), stdout=FakeTty())

    assert shell.screen_colour == "none"
    assert shell.hint_colour == "bright-yellow"
    # An amber screen has no amber left to hint with.
    assert default_hint("bright-yellow") == "bright-white"


def test_an_explicit_choice_still_wins(tmp_path, monkeypatch):
    from emix.host import Drive, DriveSet
    from emix.personalities.cpm import CpmShell

    # The suite must not depend on the caller's environment: an ambient
    # NO_COLOR would otherwise turn this into a contradiction of the test
    # below, which asserts NO_COLOR wins.
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("COLORFGBG", "15;0")
    drives = DriveSet([Drive.create("A", tmp_path)])

    shell = CpmShell(drives, stdin=FakeTty(), stdout=FakeTty(), hint_colour="magenta")

    assert shell.hint_colour == "magenta"


# -- the probe must not cost the user a keystroke ------------------------


def test_a_reply_is_separated_from_what_the_user_typed_around_it():
    """The probe reads the keyboard, so the two arrive down one pipe."""
    from emix.terminal import _REPLY, _RGB

    seen = b"DI\033]11;rgb:0000/0000/0000\033\\R\n"
    reply = _REPLY.search(seen)

    assert reply is not None
    assert seen[: reply.start()] + seen[reply.end() :] == b"DIR\n"
    assert _RGB.search(reply.group()) is not None


def test_a_bel_terminated_reply_is_understood_too():
    from emix.terminal import _REPLY

    assert _REPLY.search(b"\033]11;rgb:ffff/ffff/ffff\a") is not None


def test_the_linux_console_is_known_dark_without_being_asked(unix, monkeypatch):
    """It cannot answer OSC 11, and a Pi's own console is the best screen we get."""
    monkeypatch.delenv("COLORFGBG", raising=False)
    monkeypatch.setenv("TERM", "linux")
    asked = []

    monkeypatch.setattr("emix.terminal._from_osc11", lambda *a: asked.append(True) or Reply())

    assert ask_background(FakeTty(), FakeTty()) == Reply(dark=True)
    assert asked == []


@needs_posix_terminal
def test_the_probe_does_not_flush_what_the_user_already_typed(unix, monkeypatch):
    """The regression: tty.setraw defaults to TCSAFLUSH, which discards a paste.

    Asserted on the flag rather than on a live terminal, because a pty pair
    loops stdout back into stdin and cannot tell a reply from an echo.
    """
    import termios
    import tty

    from emix.terminal import _from_osc11

    monkeypatch.setattr(termios, "tcgetattr", lambda descriptor: [])
    monkeypatch.setattr(termios, "tcsetattr", lambda *arguments: None)
    used = []

    def record(descriptor, when=None):
        used.append(when)
        raise OSError  # stop before touching a terminal that is not there

    monkeypatch.setattr(tty, "setraw", record)
    _from_osc11(FakeTty(), FakeTty())

    assert used == [termios.TCSANOW]


def test_typed_ahead_is_replayed_as_the_first_command(tmp_path):
    from emix.host import Drive, DriveSet
    from emix.personalities.cpm import CpmShell

    drives = DriveSet([Drive.create("A", tmp_path)])
    shell = CpmShell(drives, stdin=FakeTty(), stdout=FakeTty(), history=None)
    shell.typed_ahead = "DIR\nBYE\n"

    assert shell.take_typed_ahead() == "DIR"
    assert shell.take_typed_ahead() == "BYE"
    assert shell.take_typed_ahead() is None


def test_an_unfinished_line_is_never_handed_over_to_be_run(tmp_path):
    """Nothing is executed on a guess, and half a line is a guess.

    `ERA *.TXT` with no Return behind it is a destructive command the user was
    still typing. It stays in `typed_ahead` for the editor, and dispatch never
    sees it.
    """
    from emix.host import Drive, DriveSet
    from emix.personalities.cpm import CpmShell

    drives = DriveSet([Drive.create("A", tmp_path)])
    shell = CpmShell(drives, stdin=FakeTty(), stdout=FakeTty(), history=None)
    shell.typed_ahead = "ERA *.TXT"

    assert shell.take_typed_ahead() is None
    assert shell.typed_ahead == "ERA *.TXT"


def test_a_finished_line_before_an_unfinished_one_still_runs(tmp_path):
    """The paste is not lost — only its last, incomplete line is held back."""
    from emix.host import Drive, DriveSet
    from emix.personalities.cpm import CpmShell

    drives = DriveSet([Drive.create("A", tmp_path)])
    shell = CpmShell(drives, stdin=FakeTty(), stdout=FakeTty(), history=None)
    shell.typed_ahead = "DIR\nERA "

    assert shell.take_typed_ahead() == "DIR"
    assert shell.take_typed_ahead() is None
    assert shell.typed_ahead == "ERA "


@pytest.mark.parametrize("ending", ["\n", "\r", "\r\n"])
def test_every_spelling_of_return_ends_a_line(ending, tmp_path):
    """Raw mode delivers CR, canonical mode LF, and a paste may carry either."""
    from emix.host import Drive, DriveSet
    from emix.personalities.cpm import CpmShell

    drives = DriveSet([Drive.create("A", tmp_path)])
    shell = CpmShell(drives, stdin=FakeTty(), stdout=FakeTty(), history=None)
    shell.typed_ahead = f"DIR{ending}BYE{ending}"

    assert shell.take_typed_ahead() == "DIR"
    assert shell.take_typed_ahead() == "BYE"
    assert shell.take_typed_ahead() is None


def test_a_bare_return_is_a_line_the_user_pressed(tmp_path):
    from emix.host import Drive, DriveSet
    from emix.personalities.cpm import CpmShell

    drives = DriveSet([Drive.create("A", tmp_path)])
    shell = CpmShell(drives, stdin=FakeTty(), stdout=FakeTty(), history=None)
    shell.typed_ahead = "\nDIR\n"

    assert shell.take_typed_ahead() == ""
    assert shell.take_typed_ahead() == "DIR"
