"""Asking the terminal what colour it is, and never guessing."""

from __future__ import annotations

import io

import pytest

from emix.assist import default_colour
from emix.terminal import _from_colorfgbg, _luminance, background_is_dark


class FakeTty(io.StringIO):
    def __init__(self, text: str = "", tty: bool = True) -> None:
        super().__init__(text)
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


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
    assert default_colour(True) == "green"


def test_a_light_or_unknown_screen_gets_something_legible_on_both():
    assert default_colour(False) == "yellow"
    assert default_colour(None) == "yellow"


def test_an_explicit_choice_still_wins(tmp_path, monkeypatch):
    from emix.host import Drive, DriveSet
    from emix.personalities.cpm import CpmShell

    monkeypatch.setenv("COLORFGBG", "15;0")
    drives = DriveSet([Drive.create("A", tmp_path)])

    shell = CpmShell(drives, stdin=FakeTty(), stdout=FakeTty(), hint_colour="magenta")

    assert shell.hint_colour == "magenta"
